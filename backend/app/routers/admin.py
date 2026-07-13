from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.prediction_contract import (
    query_model_scores,
    model_metrics_audit,
    normalizer_strip_rule_scores_from_model_metrics,
    PREDICTION_SOURCE_TRAINED_MODEL,
    RISK_VALUE_TYPE_MODEL_PROBABILITY,
    infer_prediction_source_from_legacy_score,
)

from app import runtime
from app.services.admin_quality_service import admin_quality_summary
from app.services.alert_outcome_service import AlertOutcomeService
from app.services.model_calibration_runtime import ModelCalibrationRuntime
from app.services.outcome_inference_worker import OutcomeInferenceWorker
from app.services.runtime_config_service import RuntimeConfigService
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("icu-alert")


class ScannerTriggerRequest(BaseModel):
    scanner_name: str
    patient_id: str | None = None


def _actor() -> str:
    return "admin"


def _runtime_actor_role(request: Request, payload: dict[str, Any] | None = None) -> tuple[str, str]:
    body = payload if isinstance(payload, dict) else {}
    actor = str(body.get("actor") or request.headers.get("x-user-id") or request.headers.get("x-operator-id") or "admin").strip() or "admin"
    role = str(body.get("role") or request.headers.get("x-user-role") or request.headers.get("x-role") or "admin").strip().lower() or "admin"
    return actor, role


def _require_runtime_admin(request: Request, payload: dict[str, Any] | None = None) -> tuple[str, str]:
    actor, role = _runtime_actor_role(request, payload)
    if role != "admin":
        raise HTTPException(status_code=403, detail="runtime config requires admin role")
    return actor, role


def _admin_role(request: Request, payload: dict[str, Any] | None = None) -> str:
    body = payload if isinstance(payload, dict) else {}
    role = str(body.get("role") or request.headers.get("x-user-role") or request.headers.get("x-role") or "").strip().lower()
    actor = str(body.get("actor") or request.headers.get("x-user-id") or "").strip()
    if not role or not actor:
        raise HTTPException(status_code=403, detail="causal discovery review requires authenticated actor and role")
    if role not in {"admin", "causal_reviewer"}:
        raise HTTPException(status_code=403, detail="causal discovery review requires admin or causal_reviewer role")
    return role


def _oid_or_text(value: str) -> Any:
    text = str(value or "").strip()
    try:
        return ObjectId(text)
    except Exception:
        return text


@router.post("/scanner/trigger")
async def trigger_scanner(req: ScannerTriggerRequest):
    """
    手动立即触发某个 Scanner 执行一次，忽略调度间隔。
    用于调试或紧急情况。
    """
    alert_engine = runtime.alert_engine
    if alert_engine is None:
        raise HTTPException(status_code=503, detail="AlertEngine not initialized")

    # 从 AlertEngine 的活跃 scanner 列表中查找目标
    active_scanners = alert_engine._active_scanners()
    scanner_map = {s.name: s for s in active_scanners}

    scanner = scanner_map.get(req.scanner_name)
    if scanner is None:
        available = sorted(scanner_map.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Scanner '{req.scanner_name}' not found. Available: {available}"
        )

    try:
        logger.info("[admin] 手动触发 scanner: %s (patient_id=%s)", req.scanner_name, req.patient_id)
        await scanner.scan()
        return {"status": "ok", "scanner": req.scanner_name, "message": "Scanner executed successfully"}
    except Exception as exc:
        logger.exception("[admin] 手动触发 scanner %s 失败: %s", req.scanner_name, exc)
        raise HTTPException(status_code=500, detail=f"Scanner execution failed: {exc}")


@router.get("/scanner-health")
async def scanner_health(
    days: int = 30,
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await AlertOutcomeService(runtime.db).scanner_health(days=max(min(int(days or 30), 90), 1), dept=dept, dept_code=dept_code or deptCode)
    if not result.get("rows") and runtime.alert_engine is not None:
        scanners = []
        for scanner in runtime.alert_engine._active_scanners():
            scanners.append(
                {
                    "scanner_name": getattr(scanner, "name", scanner.__class__.__name__),
                    "fired_count": 0,
                    "ppv": 0,
                    "override_rate": 0,
                    "median_time_to_action_minutes": None,
                    "event_24h_rate": 0,
                    "nnt": None,
                    "drift_status": "green",
                    "review_suggestion": False,
                    "threshold_advice": "",
                    "recent_overrides": [],
                }
            )
        result = {"days": result.get("days") or days, "source": "registered_scanners", "rows": scanners, "total_scanners": len(scanners)}
    return {"code": 0, **serialize_doc(result)}


@router.get("/quality-closed-loop")
async def quality_closed_loop(
    days: int = 30,
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    return {"code": 0, **await admin_quality_summary(runtime.db, days=days, dept=dept, dept_code=dept_code or deptCode)}


@router.post("/scanner-health/recalculate")
async def recalculate_scanner_health(days: int = 30):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await ModelCalibrationRuntime(runtime.db).run_daily(days=max(min(int(days or 30), 90), 1))
    return {"code": 0, "record": serialize_doc(result)}


@router.post("/scanner-health/infer-outcomes")
async def infer_alert_outcomes(limit: int = 200, min_age_minutes: int = 30):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await OutcomeInferenceWorker(runtime.db).run_once(
        limit=max(min(int(limit or 200), 1000), 1),
        min_age_minutes=max(int(min_age_minutes or 30), 0),
    )
    return {"code": 0, "result": serialize_doc(result)}


@router.get("/model-prediction-stats")
async def model_prediction_stats(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    score_type: str | None = Query(default="temporal_risk_scanner"),
    limit: int = Query(default=5000, ge=1, le=20000),
    include_patient_detail: bool = Query(default=False),
):
    """Return model prediction performance statistics with audit trail.

    **Permission**: requires x-user-id and x-user-role=admin headers.
    This is a **temporary header-based check**, NOT real authentication.
    x-user-id / x-user-role can be forged by any caller.  Do NOT rely on
    this for production access control until SSO/JWT is implemented.

    **Patient detail**: ``include_patient_detail`` is disabled until
    SSO/JWT is in place.  When enabled in future, it will require a
    signed JWT with admin scope.

    Only ``prediction_source = "trained_model"`` records with
    ``risk_value_type = "model_probability"`` are included in model
    performance metrics.
    """
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")

    # ── permission check (temporary header-based, NOT real auth) ─────────
    # SECURITY NOTE: x-user-id and x-user-role are plain HTTP headers.
    # Any caller can set them to arbitrary values.  This is a stop-gap
    # until SSO/JWT is integrated.  Do not treat as authenticated.
    role = str(
        request.headers.get("x-user-role")
        or request.headers.get("x-role")
        or ""
    ).strip().lower()
    actor = str(
        request.headers.get("x-user-id")
        or request.headers.get("x-operator-id")
        or ""
    ).strip()
    if not actor:
        raise HTTPException(status_code=401, detail="authentication required: provide x-user-id header")
    if role != "admin":
        raise HTTPException(status_code=403, detail="model prediction stats require admin role")

    # ── patient detail disabled until SSO/JWT ────────────────────────────
    if include_patient_detail:
        raise HTTPException(
            status_code=501,
            detail="include_patient_detail is disabled until SSO/JWT authentication is implemented. "
                   "Header-based x-user-id/x-user-role is not sufficient for patient data access.",
        )

    since = datetime.now() - timedelta(days=max(int(days), 1))

    result = await query_model_scores(
        runtime.db,
        score_type=score_type,
        since=since,
        limit=max(int(limit), 1),
    )

    stat_split = result["audit"]["stat_split"]

    response: dict[str, Any] = {
        "code": 0,
        "days": days,
        "score_type": score_type,
        "requested_by": actor,
        "_auth_note": "Header-based identity check only; NOT cryptographically authenticated. SSO/JWT pending.",
        "stat_split": {
            "total_candidates": stat_split["total_candidates"],
            "technical_prediction_eligible": stat_split["technical_prediction_eligible"],
            "clinical_metrics_eligible": stat_split["clinical_metrics_eligible"],
            "validated_metrics_eligible": stat_split["validated_metrics_eligible"],
            "excluded_from_technical_metrics": stat_split["excluded_from_technical_metrics"],
            "excluded_from_clinical_metrics": stat_split["excluded_from_clinical_metrics"],
        },
        "excluded_reasons": result["audit"]["excluded_reasons"],
        "by_validation_status": result["audit"]["by_validation_status"],
        "validation_status_detail": stat_split["by_status"],
        "generated_at": datetime.now().isoformat(),
    }

    # ── access audit log ─────────────────────────────────────────────────
    try:
        await runtime.db.col("model_stats_access_audit").insert_one({
            "actor": actor,
            "role": role,
            "endpoint": "/api/admin/model-prediction-stats",
            "score_type": score_type,
            "days": days,
            "ip": request.client.host if request.client else "",
            "accessed_at": datetime.now(),
        })
    except Exception:
        pass  # audit failure must not block the response

    return response


@router.get("/runtime-config")
async def runtime_config_overview():
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await RuntimeConfigService(runtime.db).overview()
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/modules")
async def update_runtime_modules(request: Request, payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    actor, _role = _require_runtime_admin(request, payload)
    result = await RuntimeConfigService(runtime.db).update_modules(payload.get("modules") or [], actor=actor)
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/ai")
async def update_runtime_ai(request: Request, payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    actor, _role = _require_runtime_admin(request, payload)
    result = await RuntimeConfigService(runtime.db).update_ai(payload or {}, actor=actor)
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/trajectory-forecast")
async def update_runtime_trajectory_forecast(request: Request, payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    actor, _role = _require_runtime_admin(request, payload)
    try:
        result = await RuntimeConfigService(runtime.db).update_trajectory_forecast(payload or {}, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/alert-rules/{rule_id}")
async def update_runtime_alert_rule(rule_id: str, payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await RuntimeConfigService(runtime.db).update_alert_rule(rule_id, payload or {}, actor=_actor())
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/field-mapping")
async def update_runtime_field_mapping(payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    try:
        result = await RuntimeConfigService(runtime.db).update_field_mapping(payload or {}, actor=_actor())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"code": 0, **serialize_doc(result)}


@router.get("/runtime-config/history")
async def runtime_config_history(key: str | None = Query(None), limit: int = Query(50, ge=1, le=200)):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    rows = await RuntimeConfigService(runtime.db).history(key=key, limit=limit)
    return {"code": 0, "items": serialize_doc(rows)}


@router.get("/runtime-config/export")
async def runtime_config_export():
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    snapshot = await RuntimeConfigService(runtime.db).export_snapshot()
    return {"code": 0, "snapshot": serialize_doc(snapshot)}


@router.post("/runtime-config/import")
async def runtime_config_import(request: Request, payload: dict = Body(default={})):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    actor, role = _require_runtime_admin(request, payload)
    try:
        result = await RuntimeConfigService(runtime.db).import_snapshot(payload.get("snapshot") or {}, actor=actor, role=role, reason=str(payload.get("reason") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/{key}/rollback")
async def runtime_config_rollback(key: str, request: Request, payload: dict = Body(default={})):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    actor, role = _require_runtime_admin(request, payload)
    try:
        result = await RuntimeConfigService(runtime.db).rollback(key, int(payload.get("version") or 0), actor=actor, role=role, reason=str(payload.get("reason") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"code": 0, **serialize_doc(result)}


@router.get("/causal-discovery/candidates")
async def causal_discovery_candidates(
    request: Request,
    status: str = Query("pending"),
    limit: int = Query(100, ge=1, le=500),
):
    _admin_role(request)
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    query: dict[str, Any] = {}
    if status and status != "all":
        query["status"] = status
    rows = [
        serialize_doc(row)
        async for row in runtime.db.col("kg_causal_candidates").find(query).sort("created_at", -1).limit(limit)
    ]
    return {"code": 0, "status": status, "items": rows}


@router.post("/causal-discovery/approve")
async def causal_discovery_approve(request: Request, payload: dict[str, Any] = Body(default={})):
    role = _admin_role(request, payload)
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    candidate_id = str(payload.get("candidate_id") or "").strip()
    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id required")
    actor = str(payload.get("actor") or request.headers.get("x-user-id") or _actor()).strip()[:120]
    approved = bool(payload.get("approved"))
    reason = str(payload.get("reason") or "").strip()[:500]
    prev_version = int(payload.get("prev_version") or 0)
    candidate = await runtime.db.col("kg_causal_candidates").find_one({"_id": _oid_or_text(candidate_id)})
    if not candidate:
        candidate = await runtime.db.col("kg_causal_candidates").find_one({"candidate_id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate not found")
    latest = await runtime.db.col("kg_causal_approvals").find_one({"candidate_id": candidate_id}, sort=[("version", -1)])
    latest_version = int((latest or {}).get("version") or 0)
    if prev_version and latest_version and prev_version != latest_version:
        raise HTTPException(status_code=409, detail=f"candidate version changed: latest={latest_version}")
    idem = await runtime.db.col("kg_causal_approvals").find_one(
        {"candidate_id": candidate_id, "actor": actor, "prev_version": prev_version, "approved": approved}
    )
    if idem:
        return {"code": 0, "idempotent": True, "record": serialize_doc(idem)}

    edits = payload.get("edits") if isinstance(payload.get("edits"), dict) else {}
    cause_node = dict(candidate.get("cause_node") or {})
    if isinstance(edits.get("cause_node"), dict):
        cause_node.update(edits["cause_node"])
    evidence = edits.get("evidence") if isinstance(edits.get("evidence"), list) else candidate.get("evidence") or []
    now = datetime.now()
    record = {
        "candidate_id": candidate_id,
        "candidate_ref": candidate.get("_id"),
        "finding_key": str(edits.get("finding_key") or candidate.get("finding_key") or "").strip(),
        "cause_node": cause_node,
        "evidence": evidence,
        "approved": approved,
        "enabled": approved,
        "reason": reason,
        "actor": actor,
        "role": role,
        "prev_version": prev_version,
        "version": latest_version + 1,
        "created_at": now,
        "updated_at": now,
    }
    inserted = await runtime.db.col("kg_causal_approvals").insert_one(record)
    await runtime.db.col("kg_causal_candidates").update_one(
        {"_id": candidate.get("_id")},
        {"$set": {"status": "approved" if approved else "revoked", "updated_at": now, "reviewed_by": actor}},
    )
    record["_id"] = inserted.inserted_id
    return {"code": 0, "idempotent": False, "record": serialize_doc(record)}


# ---------------------------------------------------------------------------
# Subphenotype × Treatment Stratified Outcome Signals
# ---------------------------------------------------------------------------


@router.get("/subphenotype-signals")
async def list_subphenotype_signals(
    status: Optional[str] = Query(None, description="状态过滤: pending_review / approved / rejected"),
    subphenotype: Optional[str] = Query(None, description="亚表型过滤"),
    treatment_class: Optional[str] = Query(None, description="处置类型过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数"),
):
    """获取亚表型分层处置信号列表。"""
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    query: dict[str, Any] = {"score_type": "subphenotype_treatment_signal"}
    if status:
        query["status"] = str(status).strip().lower()
    if subphenotype:
        query["subphenotype"] = str(subphenotype).strip()
    if treatment_class:
        query["treatment_class"] = str(treatment_class).strip()
    cursor = runtime.db.col("score").find(query).sort("calc_time", -1).limit(limit)
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"code": 0, "rows": rows}


@router.post("/subphenotype-signals/{signal_id}/approve")
async def approve_subphenotype_signal(signal_id: str, request: Request, payload: dict[str, Any] = Body(default={})):
    """审批通过亚表型分层处置信号。"""
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    rid = _oid_or_text(signal_id)
    record = await runtime.db.col("score").find_one(
        {"_id": rid, "score_type": "subphenotype_treatment_signal"}
    )
    if not record:
        raise HTTPException(status_code=404, detail="信号记录不存在")
    now = datetime.now()
    actor = str(payload.get("actor") or request.headers.get("x-user-id") or _actor()).strip()[:120]
    update_fields = {
        "status": "approved",
        "updated_at": now,
        "reviewed_at": now,
        "reviewer": actor,
        "review_comment": str(payload.get("review_comment") or "").strip()[:500],
    }
    await runtime.db.col("score").update_one({"_id": rid}, {"$set": update_fields})
    updated = await runtime.db.col("score").find_one({"_id": rid})
    return {"code": 0, "record": serialize_doc(updated)}


@router.post("/subphenotype-signals/{signal_id}/reject")
async def reject_subphenotype_signal(signal_id: str, payload: dict[str, Any] = Body(default={})):
    """拒绝亚表型分层处置信号。"""
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    rid = _oid_or_text(signal_id)
    record = await runtime.db.col("score").find_one(
        {"_id": rid, "score_type": "subphenotype_treatment_signal"}
    )
    if not record:
        raise HTTPException(status_code=404, detail="信号记录不存在")
    now = datetime.now()
    actor = str(payload.get("actor") or "").strip()[:120]
    update_fields = {
        "status": "rejected",
        "updated_at": now,
        "reviewed_at": now,
        "reviewer": actor,
        "review_comment": str(payload.get("review_comment") or "").strip()[:500],
    }
    await runtime.db.col("score").update_one({"_id": rid}, {"$set": update_fields})
    updated = await runtime.db.col("score").find_one({"_id": rid})
    return {"code": 0, "record": serialize_doc(updated)}


# ---------------------------------------------------------------------------
# Rule Calibration
# ---------------------------------------------------------------------------


@router.get("/rule-calibration")
async def list_rule_calibration(
    status: Optional[str] = Query(None, description="状态过滤: pending_review / approved / rejected"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取规则自校准建议列表。"""
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    query: dict[str, Any] = {"score_type": "rule_calibration"}
    if status:
        query["status"] = str(status).strip().lower()
    cursor = runtime.db.col("score").find(query).sort("created_at", -1).limit(limit)
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"code": 0, "rows": rows}


@router.post("/rule-calibration/{score_id}/approve")
async def approve_rule_calibration(score_id: str, request: Request, payload: dict[str, Any] = Body(default={})):
    """审批通过规则校准建议。"""
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    rid = _oid_or_text(score_id)
    record = await runtime.db.col("score").find_one(
        {"_id": rid, "score_type": "rule_calibration"}
    )
    if not record:
        raise HTTPException(status_code=404, detail="校准记录不存在")
    now = datetime.now()
    actor = str(payload.get("actor") or request.headers.get("x-user-id") or _actor()).strip()[:120]
    update_fields = {
        "status": "approved",
        "updated_at": now,
        "reviewed_at": now,
        "reviewed_by": actor,
    }
    await runtime.db.col("score").update_one({"_id": rid}, {"$set": update_fields})

    # 清除 engine 缓存
    if runtime.alert_engine and hasattr(runtime.alert_engine, "invalidate_calibration_cache"):
        runtime.alert_engine.invalidate_calibration_cache(record.get("rule_id"))

    updated = await runtime.db.col("score").find_one({"_id": rid})
    return {"code": 0, "record": serialize_doc(updated)}


@router.post("/rule-calibration/{score_id}/reject")
async def reject_rule_calibration(score_id: str, payload: dict[str, Any] = Body(default={})):
    """拒绝规则校准建议。"""
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    rid = _oid_or_text(score_id)
    record = await runtime.db.col("score").find_one(
        {"_id": rid, "score_type": "rule_calibration"}
    )
    if not record:
        raise HTTPException(status_code=404, detail="校准记录不存在")
    now = datetime.now()
    actor = str(payload.get("actor") or "").strip()[:120]
    update_fields = {
        "status": "rejected",
        "updated_at": now,
        "reviewed_at": now,
        "reviewed_by": actor,
    }
    await runtime.db.col("score").update_one({"_id": rid}, {"$set": update_fields})

    # 清除 engine 缓存
    if runtime.alert_engine and hasattr(runtime.alert_engine, "invalidate_calibration_cache"):
        runtime.alert_engine.invalidate_calibration_cache(record.get("rule_id"))

    updated = await runtime.db.col("score").find_one({"_id": rid})
    return {"code": 0, "record": serialize_doc(updated)}


# ================================================================
# 语音查房错例 Review
# ================================================================


@router.get("/voice-correction-candidates")
async def voice_correction_candidates(
    request: Request,
    status: str = Query("pending", description="候选状态过滤"),
    limit: int = Query(200, ge=1, le=500),
):
    """列出语音查房纠错候选（只读），药名严审区置顶。"""
    from app.services.voice_rounding_review import list_candidates

    _require_runtime_admin(request)
    results = await list_candidates(runtime.db, status=status, limit=limit)
    return {"code": 0, "candidates": results}


@router.post("/voice-correction-candidates/{candidate_id}/decision")
async def voice_correction_decision(
    candidate_id: str,
    request: Request,
    payload: dict = Body(default={}),
):
    """
    采纳或驳回纠错候选。
    accept：写回 yaml + 热重载 + 审计。
    reject：标记状态 + 审计。
    药名相关候选禁止 accept（医疗安全红线）。
    """
    from app.services.voice_rounding_review import decide_candidate

    actor, role = _require_runtime_admin(request, payload)
    action = str((payload or {}).get("action") or "").strip().lower()
    target_category = str((payload or {}).get("target_category") or "").strip()
    reviewer = actor or "admin"

    # 获取 VoiceRoundingService 实例（用于热重载）
    vr_svc = None
    if hasattr(runtime, "voice_rounding_service"):
        vr_svc = runtime.voice_rounding_service

    result = await decide_candidate(
        runtime.db,
        runtime.config,
        candidate_id,
        action=action,
        reviewer=reviewer,
        target_category=target_category,
        voice_rounding_service=vr_svc,
    )

    if result.get("code") and result["code"] != 0:
        raise HTTPException(status_code=result["code"], detail=result["message"])
    return result


@router.post("/voice-correction-candidates/reload-hints")
async def voice_correction_reload_hints(request: Request):
    """手动触发在线服务重载 correction_hints（兜底接口）。"""
    _require_runtime_admin(request)

    if not hasattr(runtime, "voice_rounding_service") or not runtime.voice_rounding_service:
        raise HTTPException(status_code=503, detail="VoiceRoundingService 未初始化")

    ok = await runtime.voice_rounding_service.reload_correction_hints()
    if not ok:
        raise HTTPException(status_code=500, detail="重载失败")
    return {"code": 0, "message": "correction_hints 已重载"}
