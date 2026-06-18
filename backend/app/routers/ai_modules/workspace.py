from __future__ import annotations

import logging
import uuid
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.config import get_config
from app.services.ai_confirmation_service import normalize_ai_decision, confirm_mdt_decision
from app.services.document_generator import ClinicalDocumentGenerator
from app.services.ward_round_generator import WardRoundGenerator
from app.utils.serialization import serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


def _safe_text_list(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows


def _normalize_mdt_decisions(payload: dict | None) -> list[dict]:
    rows = (payload or {}).get("decisions") if isinstance((payload or {}).get("decisions"), list) else []
    normalized = []
    for idx, item in enumerate(rows[:20], start=1):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or item.get("title") or "").strip()
        if not action:
            continue
        normalized.append(
            {
                "id": str(item.get("id") or f"decision-{idx}"),
                "action": action,
                "owner": str(item.get("owner") or "").strip() or "值班医生",
                "deadline": str(item.get("deadline") or "").strip() or "6h",
                "monitoring": str(item.get("monitoring") or "").strip() or "按系统指标复评",
                "review_time": str(item.get("review_time") or "").strip() or "6h",
                "status": str(item.get("status") or "pending_confirmation").strip() or "pending_confirmation",
                "note": str(item.get("note") or "").strip(),
                "requires_confirmation": True if item.get("requires_confirmation") is None else bool(item.get("requires_confirmation")),
                "confirmed_by": item.get("confirmed_by"),
                "confirmed_at": item.get("confirmed_at"),
                "confirmation_note": str(item.get("confirmation_note") or "").strip(),
                "confirmation_status": str(item.get("confirmation_status") or "").strip() or ("confirmed" if item.get("confirmed_at") else "pending"),
                "safety_notice": str(item.get("safety_notice") or "").strip()
                or "AI 生成内容仅为待审核建议草案，不能作为医嘱直接执行；必须由执业医生结合床旁情况确认。",
            }
        )
    return [normalize_ai_decision(item, idx) for idx, item in enumerate(normalized, start=1)]


def _build_order_drafts(*, patient: dict, assessment: dict | None, decisions: list[dict]) -> list[dict]:
    patient_name = str(patient.get("name") or patient.get("hisName") or "当前患者").strip()
    meta_actions = []
    if isinstance(assessment, dict):
        result = assessment.get("result") if isinstance(assessment.get("result"), dict) else assessment
        meta = result.get("meta_agent") if isinstance(result.get("meta_agent"), dict) else {}
        meta_actions = _safe_text_list(meta.get("final_actions"), limit=10)
    base_actions = [row.get("action") for row in decisions if str(row.get("action") or "").strip()]
    actions = list(dict.fromkeys([*base_actions, *meta_actions]))[:8]
    drafts = []
    for idx, action in enumerate(actions, start=1):
        source_decision = next((row for row in decisions if str(row.get("action") or "").strip() == str(action).strip()), None)
        confirmed = _is_confirmed_decision(source_decision)
        drafts.append({
            "id": f"order-{idx}",
            "category": "待审核医嘱建议",
            "order_text": f"{patient_name}：{action}",
            "priority": "high" if idx <= 2 else "medium",
            "status": "doctor_confirmed" if confirmed else "doctor_review_required",
            "source": "mdt_workspace",
            "source_decision_id": source_decision.get("id") if source_decision else "",
            "source_decision_version": source_decision.get("version") if source_decision else None,
            "requires_confirmation": not confirmed,
            "confirmed_at": source_decision.get("confirmed_at") if confirmed else None,
            "confirmed_by": source_decision.get("confirmed_by") if confirmed else None,
        })
    if not drafts:
        drafts.append({"id": "order-1", "category": "待审核医嘱建议", "order_text": f"{patient_name}：等待 MDT 决议后生成待审核医嘱草稿。", "priority": "medium", "status": "doctor_review_required", "source": "mdt_workspace", "requires_confirmation": True})
    return drafts


def assert_decision_confirmed(decision: dict) -> None:
    if not _is_confirmed_decision(decision):
        raise PermissionError(f"决议 {decision.get('id') or ''} 未经医生确认，不能转为正式医嘱")


def _is_confirmed_decision(decision: dict | None) -> bool:
    if not isinstance(decision, dict):
        return False
    return bool(decision.get("confirmed_at")) or str(decision.get("confirmation_status") or "").strip().lower() == "confirmed" or str(decision.get("status") or "").strip().lower() == "doctor_confirmed" or decision.get("requires_confirmation") is False


def _decision_map(decisions: list[dict]) -> dict[str, dict]:
    return {str(item.get("id") or ""): item for item in decisions if isinstance(item, dict) and str(item.get("id") or "").strip()}


def _normalize_order_draft(item: dict, idx: int, decisions_by_id: dict[str, dict]) -> dict:
    order_text = str(item.get("order_text") or item.get("text") or "").strip()
    if not order_text:
        return {}
    source_decision_id = str(item.get("source_decision_id") or item.get("decision_id") or "").strip()
    source_decision = decisions_by_id.get(source_decision_id) if source_decision_id else None
    confirmed = _is_confirmed_decision(source_decision)
    status = str(item.get("status") or "").strip() or ("doctor_confirmed" if confirmed else "doctor_review_required")
    requires_confirmation = True if item.get("requires_confirmation") is None else bool(item.get("requires_confirmation"))
    if source_decision:
        requires_confirmation = not confirmed
    elif not item.get("confirmed_at"):
        requires_confirmation = True
    return {
        "id": str(item.get("id") or f"order-{idx}"),
        "category": str(item.get("category") or "待审核医嘱建议").strip(),
        "order_text": order_text,
        "priority": str(item.get("priority") or "medium").strip(),
        "status": status if confirmed else "doctor_review_required",
        "source": str(item.get("source") or "mdt_workspace").strip(),
        "source_decision_id": source_decision_id,
        "source_decision_version": source_decision.get("version") if source_decision else item.get("source_decision_version"),
        "requires_confirmation": requires_confirmation,
        "confirmed_at": source_decision.get("confirmed_at") if confirmed else item.get("confirmed_at"),
        "confirmed_by": source_decision.get("confirmed_by") if confirmed else item.get("confirmed_by"),
    }


def assert_order_draft_can_be_used(order_draft: dict, decisions_by_id: dict[str, dict] | None = None) -> None:
    source_decision_id = str(order_draft.get("source_decision_id") or order_draft.get("decision_id") or "").strip()
    if decisions_by_id and source_decision_id:
        decision = decisions_by_id.get(source_decision_id)
        if not decision:
            raise PermissionError(f"医嘱草稿 {order_draft.get('id')} 未找到来源 MDT 决议，不能转为正式医嘱")
        assert_decision_confirmed(decision)
    elif not order_draft.get("confirmed_at"):
        raise PermissionError(f"医嘱草稿 {order_draft.get('id')} 缺少已确认的来源 MDT 决议，不能转为正式医嘱")
    if order_draft.get("requires_confirmation") and not order_draft.get("confirmed_at"):
        raise PermissionError(f"医嘱草稿 {order_draft.get('id')} 未经医生确认，不能转为正式医嘱")


def _merge_confirmed_decisions(incoming: list[dict], existing: dict | None) -> list[dict]:
    existing_rows = existing.get("decisions") if isinstance(existing, dict) and isinstance(existing.get("decisions"), list) else []
    existing_by_id = {
        str(item.get("id") or ""): normalize_ai_decision(item, idx)
        for idx, item in enumerate(existing_rows, start=1)
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    merged: list[dict] = []
    for idx, item in enumerate(incoming, start=1):
        row = normalize_ai_decision(item, idx)
        prev = existing_by_id.get(str(row.get("id") or ""))
        if prev:
            prev_version = int(prev.get("version") or 1)
            row_version = int(row.get("version") or 1)
            prev_confirmed = bool(prev.get("confirmed_at")) or str(prev.get("confirmation_status") or "") in {"confirmed", "rejected", "needs_revision"}
            row_stale = row_version < prev_version
            if prev_confirmed and (row_stale or not row.get("confirmed_at")):
                merged.append(prev)
                continue
            row["version"] = max(prev_version, row_version)
        merged.append(row)
    incoming_ids = {str(item.get("id") or "") for item in merged}
    for key, prev in existing_by_id.items():
        if key and key not in incoming_ids and (prev.get("confirmed_at") or str(prev.get("confirmation_status") or "") in {"confirmed", "rejected", "needs_revision"}):
            merged.append(prev)
    return merged


def _workspace_phase(payload: dict | None) -> str:
    phase = str((payload or {}).get("phase") or "").strip().lower()
    if phase in {"collecting", "conflict_review", "finalizing", "closed"}:
        return phase
    return "finalizing"


def _workspace_title(patient: dict, decisions: list[dict], phase: str) -> str:
    patient_name = str(patient.get("name") or patient.get("hisName") or "患者").strip()
    if decisions:
        return f"{patient_name} MDT会话 · {str(decisions[0].get('action') or '')[:16]}"
    return f"{patient_name} MDT会话 · {phase}"


def _safe_string_list(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value[:limit]:
        text = str(item or '').strip()
        if text:
            rows.append(text)
    return rows


def _normalize_activity_log(value: object, *, limit: int = 80) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows: list[dict] = []
    for idx, item in enumerate(value[:limit], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or f"会诊动作{idx}").strip()
        detail = str(item.get("detail") or "").strip()
        created_at = item.get("created_at")
        rows.append(
            {
                "id": str(item.get("id") or f"activity-{idx}"),
                "title": title,
                "detail": detail,
                "created_at": created_at if isinstance(created_at, str) and created_at.strip() else datetime.now().isoformat(),
            }
        )
    return rows


@router.post("/api/ai/documents/{patient_id}")
async def ai_generate_document(patient_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    doc_type = str((payload or {}).get("doc_type") or "").strip()
    if not doc_type:
        return {"code": 400, "message": "doc_type不能为空"}
    time_range = (payload or {}).get("time_range") if isinstance((payload or {}).get("time_range"), dict) else None

    generator = ClinicalDocumentGenerator(
        db=runtime.db,
        config=get_config(),
        alert_engine=runtime.alert_engine,
        rag_service=runtime.ai_rag_service,
        ai_monitor=runtime.ai_monitor,
        ai_handoff_service=runtime.ai_handoff_service,
    )
    try:
        if doc_type == "ward_round":
            round_generator = WardRoundGenerator(
                db=runtime.db,
                config=get_config(),
                alert_engine=runtime.alert_engine,
                rag_service=runtime.ai_rag_service,
                ai_handoff_service=runtime.ai_handoff_service,
                document_generator=generator,
            )
            record = await round_generator.generate(
                str(pid),
                round_level=str((payload or {}).get("round_level") or "attending"),
                doctor=str((payload or {}).get("doctor") or ""),
                hours=int((payload or {}).get("hours") or (time_range or {}).get("hours") or 24),
                time_range=time_range,
            )
        else:
            record = await generator.generate(str(pid), doc_type, time_range=time_range)
        return {"code": 0, "document": serialize_doc(record) if record else None}
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    except Exception as exc:
        logger.error("AI document generation error: %s", exc)
        return {"code": 0, "document": None, "error": f"文书生成异常: {str(exc)[:120]}"}


@router.get("/api/ai/mdt-workspace/{patient_id}")
async def ai_mdt_workspace(patient_id: str, session_id: str | None = Query(None)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1, "name": 1, "hisName": 1, "hisBed": 1, "bed": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    workspace_query: dict = {"patient_id": str(pid), "score_type": "mdt_workspace_record"}
    if str(session_id or "").strip():
        workspace_query["session_id"] = str(session_id).strip()
    workspace = await runtime.db.col("score").find_one(workspace_query, sort=[("updated_at", -1), ("calc_time", -1)])
    documents_cursor = runtime.db.col("score").find({"patient_id": str(pid), "score_type": "clinical_document", "doc_type": {"$in": ["mdt_summary", "daily_progress", "consultation_request", "ward_round"]}}).sort("updated_at", -1).limit(20)
    documents = [serialize_doc(doc) async for doc in documents_cursor]
    assessment = await runtime.db.col("score").find_one({"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"}, sort=[("calc_time", -1)])
    decisions = [normalize_ai_decision(item, idx) for idx, item in enumerate(workspace.get("decisions") if isinstance(workspace, dict) and isinstance(workspace.get("decisions"), list) else [], start=1)]
    if isinstance(workspace, dict):
        workspace = {**workspace, "decisions": decisions}
    order_drafts = workspace.get("order_drafts") if isinstance(workspace, dict) and isinstance(workspace.get("order_drafts"), list) else []
    if not order_drafts:
        order_drafts = _build_order_drafts(patient=patient, assessment=assessment, decisions=decisions)
    sessions_cursor = runtime.db.col("score").find(
        {"patient_id": str(pid), "score_type": "mdt_workspace_record"},
        {"session_id": 1, "title": 1, "phase": 1, "updated_at": 1, "summary": 1, "final_summary": 1, "decisions": 1, "tags": 1, "template_name": 1},
    ).sort("updated_at", -1).limit(20)
    sessions = [serialize_doc(doc) async for doc in sessions_cursor]
    return {"code": 0, "workspace": serialize_doc(workspace) if workspace else None, "documents": documents, "order_drafts": serialize_doc(order_drafts), "sessions": sessions}


@router.get("/api/ai/mdt-workspace/{patient_id}/sessions")
async def ai_mdt_workspace_sessions(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    cursor = runtime.db.col("score").find(
        {"patient_id": str(pid), "score_type": "mdt_workspace_record"},
        {"session_id": 1, "title": 1, "phase": 1, "updated_at": 1, "summary": 1, "final_summary": 1, "decisions": 1, "tags": 1, "template_name": 1},
    ).sort("updated_at", -1).limit(50)
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"code": 0, "sessions": rows}


@router.post("/api/ai/mdt-workspace/{patient_id}")
async def ai_save_mdt_workspace(patient_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    assessment = await runtime.db.col("score").find_one({"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"}, sort=[("calc_time", -1)])
    decisions = _normalize_mdt_decisions(payload)
    consult_record = str((payload or {}).get("consult_record") or "").strip()
    progress_record = str((payload or {}).get("progress_record") or "").strip()
    final_summary = str((payload or {}).get("final_summary") or "").strip()
    participants = _safe_string_list((payload or {}).get("participants"), limit=12)
    tags = _safe_string_list((payload or {}).get("tags"), limit=12)
    template_name = str((payload or {}).get("template_name") or "").strip()
    activity_log = _normalize_activity_log((payload or {}).get("activity_log"), limit=80)
    order_drafts = (payload or {}).get("order_drafts") if isinstance((payload or {}).get("order_drafts"), list) else None
    decisions_by_id = _decision_map(decisions)
    normalized_orders = []
    for idx, item in enumerate(order_drafts or [], start=1):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_order_draft(item, idx, decisions_by_id)
        if normalized:
            normalized_orders.append(normalized)
    if not normalized_orders:
        normalized_orders = _build_order_drafts(patient=patient, assessment=assessment, decisions=decisions)

    now = datetime.now()
    session_id = str((payload or {}).get("session_id") or "").strip() or str(uuid.uuid4())
    phase = _workspace_phase(payload)
    existing = await runtime.db.col("score").find_one({"patient_id": str(pid), "score_type": "mdt_workspace_record", "session_id": session_id}, sort=[("updated_at", -1), ("calc_time", -1)])
    decisions = _merge_confirmed_decisions(decisions, existing)
    decisions_by_id = _decision_map(decisions)
    normalized_orders = [_normalize_order_draft(item, idx, decisions_by_id) for idx, item in enumerate(normalized_orders, start=1)]
    normalized_orders = [item for item in normalized_orders if item]
    record = {
        "session_id": session_id,
        "title": _workspace_title(patient, decisions, phase),
        "phase": phase,
        "patient_id": str(pid),
        "patient_name": patient.get("name") or patient.get("hisName") or "",
        "bed": patient.get("hisBed") or patient.get("bed") or "",
        "score_type": "mdt_workspace_record",
        "summary": decisions[0].get("action") if decisions else "MDT 工作站结构化记录",
        "decisions": decisions,
        "consult_record": consult_record,
        "progress_record": progress_record,
        "final_summary": final_summary,
        "participants": participants,
        "tags": tags,
        "template_name": template_name,
        "activity_log": activity_log,
        "order_drafts": normalized_orders,
        "meta_actions": _safe_text_list((((assessment or {}).get("result") or {}).get("meta_agent") or {}).get("final_actions"), limit=12),
        "updated_at": now,
        "calc_time": now,
    }
    if existing:
        await runtime.db.col("score").update_one({"_id": existing["_id"]}, {"$set": record})
        record["_id"] = existing["_id"]
    else:
        insert_res = await runtime.db.col("score").insert_one(record)
        record["_id"] = insert_res.inserted_id
    return {"code": 0, "workspace": serialize_doc(record)}


@router.post("/api/ai/mdt-workspace/{patient_id}/sessions/{session_id}/decisions/{decision_id}/confirm")
async def ai_confirm_mdt_decision(patient_id: str, session_id: str, decision_id: str, payload: dict = Body(default={})):
    try:
        ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    try:
        decision = await confirm_mdt_decision(
            runtime.db,
            patient_id=patient_id,
            session_id=session_id,
            decision_id=decision_id,
            action=str((payload or {}).get("action") or "confirm"),
            actor=str((payload or {}).get("actor") or "doctor"),
            note=str((payload or {}).get("note") or ""),
            expected_version=int((payload or {}).get("expected_version")) if (payload or {}).get("expected_version") is not None else None,
        )
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    if not decision:
        return {"code": 404, "message": "未找到待确认的 MDT 决议"}
    return {"code": 0, "decision": serialize_doc(decision)}


@router.post("/api/ai/mdt-workspace/{patient_id}/sessions/{session_id}/order-drafts/{order_id}/release")
async def ai_release_mdt_order_draft(patient_id: str, session_id: str, order_id: str, payload: dict = Body(default={})):
    try:
        ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    record = await runtime.db.col("score").find_one(
        {"patient_id": str(patient_id), "score_type": "mdt_workspace_record", "session_id": str(session_id)}
    )
    if not record:
        return {"code": 404, "message": "未找到 MDT 会话"}
    decisions = [normalize_ai_decision(item, idx) for idx, item in enumerate(record.get("decisions") or [], start=1) if isinstance(item, dict)]
    decisions_by_id = _decision_map(decisions)
    order_drafts = record.get("order_drafts") if isinstance(record.get("order_drafts"), list) else []
    target = next((item for item in order_drafts if str(item.get("id") or "") == str(order_id)), None)
    if not target:
        return {"code": 404, "message": "未找到医嘱草稿"}
    try:
        assert_order_draft_can_be_used(target, decisions_by_id)
    except PermissionError as exc:
        return {"code": 409, "message": str(exc)}

    now = datetime.now()
    actor = str((payload or {}).get("actor") or "doctor").strip() or "doctor"
    released = {
        **target,
        "status": "released_for_order_entry",
        "released_at": now,
        "released_by": actor,
        "requires_confirmation": False,
    }
    next_orders = [released if str(item.get("id") or "") == str(order_id) else item for item in order_drafts]
    await runtime.db.col("score").update_one(
        {"_id": record["_id"]},
        {"$set": {"order_drafts": next_orders, "updated_at": now}},
    )
    await runtime.db.col("mdt_order_release_logs").insert_one(
        {
            "patient_id": str(patient_id),
            "session_id": str(session_id),
            "order_id": str(order_id),
            "actor": actor,
            "order_draft": released,
            "created_at": now,
            "updated_at": now,
        }
    )
    return {"code": 0, "order_draft": serialize_doc(released)}
