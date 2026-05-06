from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.audit_service import normalize_actor, write_audit_log


CONFIRMABLE_AI_MODULES = {"mdt_workspace"}
AI_CONFIRMATION_STATUSES = {
    "pending_confirmation",
    "doctor_confirmed",
    "rejected",
    "needs_revision",
}


def normalize_ai_decision(item: dict[str, Any], idx: int = 1) -> dict[str, Any]:
    decision = dict(item or {})
    status = str(decision.get("status") or "").strip().lower()
    if status in {"pending", "in_progress", "completed"} and not decision.get("confirmed_at"):
        status = "pending_confirmation"
    if status not in AI_CONFIRMATION_STATUSES and status not in {"in_progress", "completed", "dismissed"}:
        status = "pending_confirmation"
    decision["id"] = str(decision.get("id") or f"decision-{idx}")
    try:
        decision["version"] = max(1, int(decision.get("version") or 1))
    except Exception:
        decision["version"] = 1
    decision["status"] = status
    decision["requires_confirmation"] = bool(decision.get("requires_confirmation", True))
    decision.setdefault("confirmation_status", "confirmed" if decision.get("confirmed_at") else "pending")
    decision.setdefault("source", "ai_mdt")
    decision.setdefault("safety_notice", "AI 生成内容仅为待审核建议草案，不能作为医嘱直接执行；必须由执业医生结合床旁情况确认。")
    return decision


async def confirm_mdt_decision(
    db,
    *,
    patient_id: str,
    session_id: str,
    decision_id: str,
    action: str,
    actor: str,
    note: str = "",
    expected_version: int | None = None,
) -> dict[str, Any] | None:
    actor_name = normalize_actor(actor)
    action_key = str(action or "").strip().lower()
    if action_key not in {"confirm", "reject", "revise"}:
        raise ValueError("action 必须是 confirm、reject 或 revise")

    query = {"patient_id": str(patient_id), "score_type": "mdt_workspace_record", "session_id": str(session_id)}
    if expected_version is not None:
        query["decisions"] = {"$elemMatch": {"id": str(decision_id), "version": int(expected_version)}}
    record = await db.col("score").find_one(query)
    if not record:
        if expected_version is not None:
            stale = await db.col("score").find_one(
                {"patient_id": str(patient_id), "score_type": "mdt_workspace_record", "session_id": str(session_id), "decisions.id": str(decision_id)},
                {"_id": 1},
            )
            if stale:
                raise ValueError("该决议已被他人更新，请刷新后重试")
        return None

    decisions = []
    target: dict[str, Any] | None = None
    now = datetime.now()
    for idx, item in enumerate(record.get("decisions") or [], start=1):
        if not isinstance(item, dict):
            continue
        decision = normalize_ai_decision(item, idx)
        if decision["id"] == str(decision_id):
            target = decision
            decision["confirmed_by"] = actor_name
            decision["confirmed_at"] = now
            decision["confirmation_note"] = str(note or "").strip()
            decision["version"] = int(decision.get("version") or 1) + 1
            if action_key == "confirm":
                decision["status"] = "doctor_confirmed"
                decision["confirmation_status"] = "confirmed"
                decision["requires_confirmation"] = False
            elif action_key == "reject":
                decision["status"] = "rejected"
                decision["confirmation_status"] = "rejected"
                decision["requires_confirmation"] = True
            else:
                decision["status"] = "needs_revision"
                decision["confirmation_status"] = "needs_revision"
                decision["requires_confirmation"] = True
        decisions.append(decision)

    if not target:
        return None

    update_result = await db.col("score").update_one(
        {"_id": record["_id"], **({"decisions": {"$elemMatch": {"id": str(decision_id), "version": int(expected_version)}}} if expected_version is not None else {})},
        {
            "$set": {
                "decisions": decisions,
                "updated_at": now,
                "last_confirmed_at": now,
                "last_confirmed_by": actor_name,
            }
        },
    )
    if update_result.modified_count == 0:
        raise ValueError("该决议已被他人更新，请刷新后重试")
    log_doc = {
        "module": "mdt_workspace",
        "patient_id": str(patient_id),
        "session_id": str(session_id),
        "decision_id": str(decision_id),
        "action": action_key,
        "actor": actor_name,
        "note": str(note or "").strip(),
        "decision": target,
        "created_at": now,
        "updated_at": now,
    }
    await db.col("ai_confirmation_logs").insert_one(log_doc)
    await write_audit_log(
        db,
        action=f"ai_decision_{action_key}",
        module="ai_confirmation",
        actor=actor_name,
        target_type="mdt_decision",
        target_id=f"{session_id}:{decision_id}",
        detail={
            "patient_id": str(patient_id),
            "session_id": str(session_id),
            "decision_id": str(decision_id),
            "note": str(note or "").strip(),
            "status": target.get("status"),
        },
    )
    return target
