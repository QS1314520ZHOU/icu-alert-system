from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.utils.alerting import window_to_hours
from app.utils.patient_helpers import admitted_patient_query
from app.utils.serialization import serialize_doc

router = APIRouter()


def resolve_actor_identity(payload: dict | None, request: Request) -> str:
    body = payload if isinstance(payload, dict) else {}
    candidates = [
        body.get("actor"),
        request.headers.get("x-user-id"),
        request.headers.get("x-actor-id"),
        request.headers.get("x-operator-id"),
        request.headers.get("x-forwarded-user"),
        request.headers.get("x-user-name"),
        request.headers.get("remote-user"),
    ]
    for item in candidates:
        value = runtime.alert_engine._normalize_lifecycle_actor(str(item or "").strip())
        if value:
            return value
    return ""


@router.get("/api/alerts/recent")
async def recent_alerts(
    limit: int = Query(50, ge=1, le=200),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
    patient_id: Optional[str] = Query(None, description="患者ID"),
    bed: Optional[str] = Query(None, description="床号"),
    role: Optional[str] = Query(None, description="角色过滤: nurse/doctor/pharmacist/head_nurse"),
    alert_domain: Optional[str] = Query(None, description="告警领域: physiologic_alarm/clinical_risk/workflow_reminder/quality_gap/data_quality/ai_advisory"),
    priority: Optional[str] = Query(None, description="响应优先级: p0/p1/p2/p3"),
    severity: Optional[str] = Query(None, description="[兼容] 旧严重程度: critical/high/warning/info"),
    fast: bool = Query(False, description="轻量快速查询，优先使用告警记录科室字段"),
    pending: bool = Query(False, description="Only unacknowledged alerts"),
):
    col = runtime.db.col("alert_records")
    query: dict = {"$and": [{"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}]}
    if patient_id or bed:
        scoped_or = []
        if patient_id:
            scoped_or.append({"patient_id": patient_id})
        if bed:
            scoped_or.append({"bed": bed})
        query["$and"].append({"$or": scoped_or})
    if dept:
        query["$and"].append({"dept": dept})
    elif dept_code:
        patient_ids = []
        patient_query = {"$and": [admitted_patient_query(), {"deptCode": dept_code}]}
        cursor_p = runtime.db.col("patient").find(patient_query, {"_id": 1})
        async for patient in cursor_p:
            patient_ids.append(str(patient.get("_id")))
        dept_or = [
            {"deptCode": dept_code},
            {"dept_code": dept_code},
            {"extra.deptCode": dept_code},
            {"extra.dept_code": dept_code},
        ]
        if patient_ids:
            dept_or.append({"patient_id": {"$in": patient_ids}})
        elif not fast:
            dept_or.append(
                {
                    "$and": [
                        {"deptCode": dept_code},
                        {"$or": [{"patient_id": {"$exists": False}}, {"patient_id": None}, {"patient_id": ""}]},
                    ]
                }
            )
        query["$and"].append({"$or": dept_or})
    if role:
        role_str = str(role).lower()
        query["$and"].append(
            {
                "$or": [
                    {"route_targets": role_str},
                    {"route_targets": {"$in": [role_str]}},
                    {"extra.route_targets": role_str},
                    {"extra.route_targets": {"$in": [role_str]}},
                ]
            }
        )
    if alert_domain:
        query["$and"].append({"alert_domain": str(alert_domain).lower()})
    if priority:
        query["$and"].append({"priority": str(priority).lower()})
    if severity:
        query["$and"].append({"severity": str(severity).lower()})

    if pending:
        query["$and"].append(
            {
                "$and": [
                    {"$or": [{"acknowledged_at": None}, {"acknowledged_at": {"$exists": False}}]},
                    {"$or": [{"ack_disposition": None}, {"ack_disposition": ""}, {"ack_disposition": {"$exists": False}}]},
                    {"$or": [{"action_taken": None}, {"action_taken": ""}, {"action_taken": {"$exists": False}}]},
                ]
            }
        )

    total_count = await col.count_documents(query)
    # ── 排序：priority → actionability → created_at ──
    # 使用 priority_sort_key 保证 p0 > p1 > p2 > p3
    priority_order = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
    cursor = col.find(query).sort([("actionability_score", -1), ("created_at", -1)]).limit(limit)
    records_raw = [serialize_doc(doc) async for doc in cursor]
    # 对已加载的记录按 priority_sort_key 稳定排序
    records = sorted(
        records_raw,
        key=lambda r: (priority_order.get(str(r.get("priority", "p2")).lower(), 2), -(r.get("actionability_score") or 0)),
    )
    # Normalize historical records missing alert_domain
    from app.alert_engine.alert_classification import normalize_alert_doc
    records = [normalize_alert_doc(r) for r in records]
    return {"code": 0, "records": records, "total": total_count, "pending_count": total_count if pending else None}


@router.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request, payload: dict = Body(default={})):
    doc = await runtime.alert_engine.acknowledge_alert(
        alert_id,
        actor=resolve_actor_identity(payload, request),
        note=str((payload or {}).get("note") or "").strip(),
        disposition=str((payload or {}).get("disposition") or "").strip(),
        override_reason_code=str((payload or {}).get("override_reason_code") or (payload or {}).get("reason_code") or "").strip(),
        override_reason_text=str((payload or {}).get("override_reason_text") or (payload or {}).get("reason_text") or "").strip(),
    )
    if not doc:
        return {"code": 404, "message": "告警不存在"}
    return {"code": 0, "record": serialize_doc(doc)}


@router.post("/api/alerts/{alert_id}/disposition")
async def disposition_alert(alert_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    doc = await runtime.alert_engine.disposition_alert(
        alert_id,
        action=str(body.get("action") or "handled").strip(),
        reason=str(body.get("reason") or "").strip(),
        actor=resolve_actor_identity(body, request),
        review_after_minutes=int(body.get("review_after_minutes") or 0),
        review_metrics=[str(item).strip() for item in (body.get("review_metrics") or []) if str(item).strip()],
    )
    if not doc:
        return {"code": 404, "message": "告警不存在"}
    return {"code": 0, "record": serialize_doc(doc)}


@router.post("/api/alerts/{alert_id}/review")
async def review_alert(alert_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    doc = await runtime.alert_engine.review_alert(
        alert_id,
        result=str(body.get("result") or "reviewed").strip(),
        evidence=[str(item).strip() for item in (body.get("evidence") or []) if str(item).strip()],
        actor=resolve_actor_identity(body, request),
    )
    if not doc:
        return {"code": 404, "message": "告警不存在"}
    return {"code": 0, "record": serialize_doc(doc)}


@router.post("/api/alerts/{alert_id}/clinical-review")
async def clinical_review_alert(alert_id: str, request: Request, payload: dict = Body(default={})):
    """临床复核端点 — 专用于 ARDS 氧合筛查等需要医生确认的告警。

    请求体:
    {
        "action": "confirm | reject | needs_more_data | alternative_diagnosis",
        "expected_version": 1,           // 乐观锁，不传或 null 表示跳过版本检查
        "alternative_diagnosis": "...",  // action=alternative_diagnosis 时必填
        "review_basis": "影像/超声/临床综合",
        "review_note": "..."
    }
    """
    body = payload or {}
    actor = resolve_actor_identity(body, request)
    if not actor:
        return {"code": 401, "message": "无法识别操作者身份，请通过认证后重试"}

    action = str(body.get("action") or "").strip().lower()
    valid_actions = {"confirm", "reject", "needs_more_data", "alternative_diagnosis"}
    if action not in valid_actions:
        return {"code": 400, "message": f"action 必须为 {' / '.join(sorted(valid_actions))}"}

    if action == "alternative_diagnosis" and not str(body.get("alternative_diagnosis") or "").strip():
        return {"code": 400, "message": "选择替代诊断时必须填写 alternative_diagnosis 字段"}

    expected_version = body.get("expected_version")
    if expected_version is not None:
        try:
            expected_version = int(expected_version)
        except (TypeError, ValueError):
            return {"code": 400, "message": "expected_version 必须为整数"}

    doc = await runtime.alert_engine.clinical_review_alert(
        alert_id,
        action=action,
        actor=actor,
        expected_version=expected_version,
        alternative_diagnosis=str(body.get("alternative_diagnosis") or "").strip() or None,
        review_basis=str(body.get("review_basis") or "").strip() or None,
        review_note=str(body.get("review_note") or "").strip(),
    )
    if not doc:
        return {"code": 404, "message": "告警不存在或操作无效"}
    if isinstance(doc, dict) and doc.get("conflict"):
        return {"code": 409, "message": doc.get("message"), "current_version": doc.get("current_version")}
    return {"code": 0, "record": serialize_doc(doc)}


# ═══════════════════════════════════════════════════════════
# 人工复核 (formal adjudication → alert_adjudications)
# ═══════════════════════════════════════════════════════════

_ADJUDICATION_ROLES = {
    "doctor", "physician", "intensivist", "attending",
    "fellow", "resident", "director", "causal_reviewer",
}


def _resolve_adjudication_role(payload: dict | None, request: Request) -> str:
    body = payload if isinstance(payload, dict) else {}
    role = str(
        body.get("role")
        or request.headers.get("x-user-role")
        or request.headers.get("x-role")
        or "doctor"
    ).strip().lower()
    if role not in _ADJUDICATION_ROLES:
        return "clinician"
    return role


@router.post("/api/alerts/{alert_id}/adjudicate")
async def adjudicate_alert(alert_id: str, request: Request, payload: dict = Body(default={})):
    """提交正式人工复核 → alert_adjudications 集合 (append-only)。

    四维度独立评估：
    - alert_validity: true_positive | false_positive | indeterminate
    - clinical_actionability: actionable | non_actionable | unreviewed
    - workflow_context: already_addressed | new_finding | unreviewed
    - clinical_helpfulness: helpful | neutral | harmful | unreviewed

    如 clinical_helpfulness=harmful，必须同时提供 harm_type 和 harm_description。

    权限：仅临床角色允许复核，管理员不能代替。
    """
    body = payload or {}
    actor = resolve_actor_identity(body, request)
    if not actor:
        return {"code": 401, "message": "无法识别操作者身份，请通过认证后重试"}

    role = _resolve_adjudication_role(body, request)
    if role == "admin":
        return {"code": 403, "message": "管理员不能代替临床人员执行正式复核"}

    expected_version = body.get("expected_version")
    if expected_version is not None:
        try:
            expected_version = int(expected_version)
        except (TypeError, ValueError):
            return {"code": 400, "message": "expected_version 必须为整数"}

    result = await runtime.alert_engine.adjudicate_alert(
        alert_id,
        actor=actor,
        role=role,
        review_tier=str(body.get("review_tier") or "preliminary").strip(),
        alert_validity=str(body.get("alert_validity") or "unreviewed").strip(),
        clinical_actionability=str(body.get("clinical_actionability") or "unreviewed").strip(),
        workflow_context=str(body.get("workflow_context") or "unreviewed").strip(),
        clinical_helpfulness=str(body.get("clinical_helpfulness") or "unreviewed").strip(),
        action_related=body.get("action_related") if "action_related" in body else None,
        harm_type=str(body.get("harm_type") or "").strip(),
        harm_description=str(body.get("harm_description") or "").strip(),
        requires_secondary_review=bool(body.get("requires_secondary_review")),
        missed_by_workflow=bool(body.get("missed_by_workflow")),
        reason_codes=body.get("reason_codes") if isinstance(body.get("reason_codes"), list) else [],
        comment=str(body.get("comment") or "").strip(),
        expected_version=expected_version,
    )
    if result is None:
        return {"code": 404, "message": "告警不存在"}
    if isinstance(result, dict):
        if result.get("error"):
            return {"code": 400, "message": result.get("message")}
        if result.get("conflict"):
            return {
                "code": 409, "message": result.get("message"),
                "current_version": result.get("current_version"),
            }
    return {"code": 0, "record": serialize_doc(result)}


@router.get("/api/alerts/{alert_id}/adjudications")
async def get_adjudication_history(alert_id: str, limit: int = Query(50, ge=1, le=200)):
    """获取告警的完整人工复核历史 (append-only)。"""
    history = await runtime.alert_engine.get_adjudication_history(alert_id, limit=limit)
    return {"code": 0, "adjudications": serialize_doc(history), "count": len(history)}


# ═══════════════════════════════════════════════════════════
# 快速反馈 (→ alert_feedback, 不进入 PPV/FPR 正式统计)
# ═══════════════════════════════════════════════════════════

@router.post("/api/alerts/{alert_id}/feedback")
async def submit_alert_feedback(alert_id: str, request: Request, payload: dict = Body(default={})):
    """提交快速反馈 → alert_feedback 集合。

    快速反馈不进入正式 PPV/误报统计。
    用于护士、药师等非复核角色的即时反馈。
    """
    body = payload or {}
    actor = resolve_actor_identity(body, request)
    result = await runtime.alert_engine.submit_alert_feedback(
        alert_id,
        actor=actor,
        feedback_type=str(body.get("feedback_type") or "").strip(),
        quick_label=str(body.get("quick_label") or "").strip(),
        note=str(body.get("note") or "").strip(),
    )
    if not result:
        return {"code": 404, "message": "告警不存在"}
    return {"code": 0, "feedback": serialize_doc(result), "enters_formal_stats": False}


# ═══════════════════════════════════════════════════════════

@router.get("/api/alerts/lifecycle/analytics")
async def alert_lifecycle_analytics(
    window: str = Query("24h"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    hours = window_to_hours(window, default=24)
    analytics = await runtime.alert_engine.alert_lifecycle_analytics(hours=hours, dept=dept, dept_code=dept_code)
    return {"code": 0, **serialize_doc(analytics)}


@router.get("/api/alerts/stats")
async def alert_stats(
    window: str = Query("24h"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    hours = window_to_hours(window, default=24)
    since = datetime.utcnow() - timedelta(hours=hours)
    match_query: dict = {"created_at": {"$gte": since}}
    if dept:
        match_query["dept"] = dept
    elif dept_code:
        patient_ids = []
        patient_query = {"$and": [admitted_patient_query(), {"deptCode": dept_code}]}
        cursor_p = runtime.db.col("patient").find(patient_query, {"_id": 1})
        async for patient in cursor_p:
            patient_ids.append(str(patient.get("_id")))
        if patient_ids:
            match_query["$or"] = [{"patient_id": {"$in": patient_ids}}, {"deptCode": dept_code}]
        else:
            match_query["deptCode"] = dept_code

    # ── 按 severity 聚合（向后兼容） ──
    severity_pipeline = [
        {"$match": match_query},
        {
            "$group": {
                "_id": {
                    "hour": {"$dateToString": {"format": "%Y-%m-%d %H:00", "date": "$created_at"}},
                    "severity": "$severity",
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.hour": 1}},
    ]

    severity_results: dict[str, dict] = {}
    cursor = await runtime.db.col("alert_records").aggregate(severity_pipeline)
    async for doc in cursor:
        hour = doc["_id"]["hour"]
        sev = doc["_id"].get("severity", "warning")
        if hour not in severity_results:
            severity_results[hour] = {"time": hour, "warning": 0, "high": 0, "critical": 0}
        if sev in severity_results[hour]:
            severity_results[hour][sev] = doc["count"]

    # ── 按 domain 聚合（新） ──
    domain_pipeline = [
        {"$match": match_query},
        {
            "$group": {
                "_id": {
                    "hour": {"$dateToString": {"format": "%Y-%m-%d %H:00", "date": "$created_at"}},
                    "alert_domain": "$alert_domain",
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.hour": 1}},
    ]

    domain_results: dict[str, dict] = {}
    cursor = await runtime.db.col("alert_records").aggregate(domain_pipeline)
    async for doc in cursor:
        hour = doc["_id"]["hour"]
        domain = doc["_id"].get("alert_domain", "unknown")
        if hour not in domain_results:
            domain_results[hour] = {"time": hour}
        domain_results[hour][domain] = doc["count"]

    return {
        "code": 0,
        "severity_series": sorted(severity_results.values(), key=lambda item: item["time"]),
        "domain_series": sorted(domain_results.values(), key=lambda item: item["time"]),
    }
