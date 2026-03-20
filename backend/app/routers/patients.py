from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.utils.analytics_ai import summarize_weaning_timeline
from app.utils.alerting import derive_sepsis_bundle_status, normalize_sbt_status, normalize_weaning_status
from app.utils.patient_helpers import admitted_patient_query, calculate_age, infer_clinical_tags
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


@router.get("/api/departments")
async def get_departments():
    """获取所有科室及在院患者数量"""
    col = runtime.db.col("patient")
    pipeline = [
        {"$match": admitted_patient_query()},
        {"$group": {"_id": {"$ifNull": ["$hisDept", "$dept"]}, "patientCount": {"$sum": 1}}},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"patientCount": -1}},
    ]
    departments = []
    cursor = await col.aggregate(pipeline)
    async for doc in cursor:
        departments.append({"dept": doc["_id"], "patientCount": doc["patientCount"]})
    return {"code": 0, "departments": departments}


@router.get("/api/patients")
async def get_patients(
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    """获取在院患者列表，可按科室筛选"""
    query: dict = admitted_patient_query()
    if dept:
        query = {"$and": [query, {"$or": [{"hisDept": dept}, {"dept": dept}]}]}
    elif dept_code:
        query = {"$and": [query, {"deptCode": dept_code}]}

    cursor = runtime.db.col("patient").find(query).sort("hisBed", 1)
    patients = []
    async for doc in cursor:
        row = serialize_doc(doc)
        if not row.get("age"):
            row["age"] = calculate_age(doc.get("birthday"))
        row["clinicalTags"] = infer_clinical_tags(doc)
        patients.append(row)
    return {"code": 0, "patients": patients}


@router.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    """获取患者详细信息"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    doc = await runtime.db.col("patient").find_one({"_id": pid})
    if not doc:
        return {"code": 404, "message": "患者不存在"}
    row = serialize_doc(doc)
    if not row.get("age"):
        row["age"] = calculate_age(doc.get("birthday"))
    return {"code": 0, "patient": row}


@router.post("/api/patients/bundle-status")
async def patient_bundle_statuses(patient_ids: list[str] = Body(default=[])):
    """批量获取患者 ABCDEF bundle 状态。"""
    results: dict[str, dict] = {}
    ids = []
    for raw in patient_ids or []:
        try:
            ids.append(ObjectId(str(raw)))
        except Exception:
            continue
    if not ids:
        return {"code": 0, "statuses": results}

    patients = [patient async for patient in runtime.db.col("patient").find({"_id": {"$in": ids}})]
    if not patients:
        return {"code": 0, "statuses": results}

    semaphore = asyncio.Semaphore(12)

    async def build_status(patient: dict) -> tuple[str, dict]:
        patient_id = str(patient["_id"])
        try:
            async with semaphore:
                status = await runtime.alert_engine.get_liberation_bundle_status(patient)
        except Exception as exc:
            logger.warning("bundle status error patient_id=%s: %s", patient_id, exc)
            status = {"lights": {}}
        return patient_id, serialize_doc(status)

    for patient_id, status in await asyncio.gather(*(build_status(patient) for patient in patients)):
        results[patient_id] = status
    return {"code": 0, "statuses": results}


@router.get("/api/patients/{patient_id}/discharge-readiness")
async def patient_discharge_readiness(patient_id: str):
    """转出风险评估。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    result = await runtime.alert_engine.evaluate_discharge_readiness(patient)
    return {"code": 0, "assessment": serialize_doc(result)}


@router.get("/api/patients/{patient_id}/similar-case-outcomes")
async def patient_similar_case_outcomes(
    patient_id: str,
    limit: int = Query(default=10, ge=3, le=20, description="返回相似病例数量"),
):
    """历史相似病例结局回溯。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    try:
        result = await runtime.alert_engine.get_similar_case_outcomes(patient, limit=limit)
    except Exception as exc:
        logger.warning("similar-case-outcomes api fallback patient_id=%s error=%s", patient_id, exc)
        fallback_builder = getattr(runtime.alert_engine, "_degraded_similar_case_result", None)
        if callable(fallback_builder):
            result = fallback_builder(patient, error=str(exc), limit=limit)
        else:
            result = {
                "current_profile": {"patient_id": patient_id},
                "summary": {
                    "matched_cases": 0,
                    "displayed_cases": 0,
                    "degraded": True,
                    "fallback_message": "AI服务暂时繁忙，已自动降级为基础模式，可稍后刷新重试。",
                },
                "cases": [],
                "historical_case_insight": {
                    "summary": "AI服务暂时繁忙，已自动降级为基础模式，可稍后刷新重试。",
                    "pattern_bullets": [],
                    "caution": "当前页面已切换到降级展示。",
                    "degraded": True,
                },
            }
    return {"code": 0, "review": serialize_doc(result)}


@router.get("/api/patients/{patient_id}/personalized-thresholds")
async def patient_personalized_thresholds(
    patient_id: str,
    status: Optional[str] = Query(None, description="状态过滤: pending_review / approved / rejected"),
):
    """获取患者最新个性化报警阈值建议。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    query: dict = {"patient_id": str(pid), "score_type": "personalized_thresholds"}
    if status:
        query["status"] = str(status).strip().lower()
    doc = await runtime.db.col("score_records").find_one(query, sort=[("calc_time", -1)])
    return {"code": 0, "record": serialize_doc(doc) if doc else None}


@router.get("/api/patients/{patient_id}/personalized-thresholds/history")
async def patient_personalized_threshold_history(
    patient_id: str,
    status: Optional[str] = Query(None, description="状态过滤: pending_review / approved / rejected"),
    limit: int = Query(10, ge=1, le=50, description="返回记录数"),
):
    """获取患者个性化报警阈值建议历史。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    query: dict = {"patient_id": str(pid), "score_type": "personalized_thresholds"}
    if status:
        query["status"] = str(status).strip().lower()
    cursor = runtime.db.col("score_records").find(query).sort("calc_time", -1).limit(limit)
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"code": 0, "rows": rows}


@router.post("/api/patients/{patient_id}/personalized-thresholds/{record_id}/review")
async def review_patient_personalized_threshold(
    patient_id: str,
    record_id: str,
    payload: dict = Body(default={}),
):
    """审核个性化报警阈值建议。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    rid = safe_oid(record_id)
    if not rid:
        return {"code": 400, "message": "无效记录ID"}
    status = str((payload or {}).get("status") or "").strip().lower()
    if status not in {"approved", "rejected"}:
        return {"code": 400, "message": "status 仅支持 approved 或 rejected"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    record = await runtime.db.col("score_records").find_one(
        {"_id": rid, "patient_id": str(pid), "score_type": "personalized_thresholds"}
    )
    if not record:
        return {"code": 404, "message": "阈值建议记录不存在"}

    now = datetime.now()
    update_fields = {
        "status": status,
        "updated_at": now,
        "reviewed_at": now,
        "reviewer": str((payload or {}).get("reviewer") or "").strip(),
        "review_comment": str((payload or {}).get("review_comment") or "").strip(),
    }
    await runtime.db.col("score_records").update_one({"_id": rid}, {"$set": update_fields})
    updated = await runtime.db.col("score_records").find_one({"_id": rid})
    return {"code": 0, "record": serialize_doc(updated)}


@router.get("/api/personalized-thresholds/review-center")
async def personalized_threshold_review_center(
    status: Optional[str] = Query(None, description="状态过滤: pending_review / approved / rejected"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数"),
):
    """个性化阈值建议全局审核中心。"""
    normalized_status = str(status or "").strip().lower() or None
    query: dict = {"score_type": "personalized_thresholds"}
    if normalized_status:
        query["status"] = normalized_status

    cursor = runtime.db.col("score_records").find(query).sort("calc_time", -1).limit(min(max(limit * 3, 80), 300))
    docs = [doc async for doc in cursor]

    status_order = {"pending_review": 0, "approved": 1, "rejected": 2}
    def sort_key(doc: dict):
        dt = doc.get("reviewed_at") or doc.get("updated_at") or doc.get("calc_time") or datetime.min
        if not isinstance(dt, datetime):
            dt = datetime.min
        return (status_order.get(str(doc.get("status") or "pending_review").lower(), 9), -dt.timestamp() if dt != datetime.min else 0)

    docs = sorted(docs, key=sort_key)[:limit]
    patient_ids = []
    for doc in docs:
        oid = safe_oid(doc.get("patient_id"))
        if oid is not None:
            patient_ids.append(oid)

    patient_map: dict[str, dict] = {}
    if patient_ids:
        patient_cursor = runtime.db.col("patient").find(
            {"_id": {"$in": patient_ids}},
            {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisDept": 1, "dept": 1},
        )
        async for patient_doc in patient_cursor:
            patient_map[str(patient_doc.get("_id"))] = patient_doc

    rows = []
    for doc in docs:
        patient_doc = patient_map.get(str(doc.get("patient_id") or "")) or {}
        rows.append(
            serialize_doc(
                {
                    **doc,
                    "patient_name": patient_doc.get("name") or patient_doc.get("hisName") or "未知患者",
                    "bed": patient_doc.get("hisBed") or patient_doc.get("bed") or "",
                    "dept": patient_doc.get("hisDept") or patient_doc.get("dept") or "",
                }
            )
        )

    summary = {
        "pending_review": await runtime.db.col("score_records").count_documents({"score_type": "personalized_thresholds", "status": "pending_review"}),
        "approved": await runtime.db.col("score_records").count_documents({"score_type": "personalized_thresholds", "status": "approved"}),
        "rejected": await runtime.db.col("score_records").count_documents({"score_type": "personalized_thresholds", "status": "rejected"}),
    }
    return {"code": 0, "summary": summary, "rows": rows}


@router.get("/api/patients/{patient_id}/ecash-status")
async def patient_ecash_status(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    status = await runtime.alert_engine.get_ecash_status(patient)
    return {"code": 0, "status": serialize_doc(status)}


@router.get("/api/patients/{patient_id}/sepsis-bundle-status")
async def patient_sepsis_bundle_status(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1, "name": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    pid_str = str(pid)
    tracker = await runtime.db.col("score_records").find_one(
        {
            "patient_id": pid_str,
            "score_type": "sepsis_antibiotic_bundle",
            "bundle_type": "sepsis_1h_antibiotic",
            "is_active": True,
        },
        sort=[("bundle_started_at", -1)],
    )
    if not tracker:
        tracker = await runtime.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "sepsis_antibiotic_bundle",
                "bundle_type": "sepsis_1h_antibiotic",
            },
            sort=[("bundle_started_at", -1)],
        )

    return {"code": 0, "status": serialize_doc(derive_sepsis_bundle_status(tracker, now=datetime.now()))}


@router.get("/api/patients/{patient_id}/weaning-status")
async def patient_weaning_status(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1, "name": 1, "hisBed": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    pid_str = str(pid)
    weaning_doc = await runtime.db.col("score_records").find_one(
        {"patient_id": pid_str, "score_type": "weaning_assessment"},
        sort=[("calc_time", -1)],
    )
    sbt_doc = await runtime.db.col("score_records").find_one(
        {"patient_id": pid_str, "score_type": "sbt_assessment"},
        sort=[("trial_time", -1), ("calc_time", -1)],
    )
    post_extub_alert = await runtime.db.col("alert_records").find_one(
        {"patient_id": {"$in": [pid_str, pid]}, "alert_type": "post_extubation_failure_risk"},
        sort=[("created_at", -1)],
    )

    status = {
        "weaning": normalize_weaning_status(weaning_doc),
        "sbt": normalize_sbt_status(sbt_doc),
        "post_extubation_risk": {
            "has_alert": bool(post_extub_alert),
            "severity": (post_extub_alert or {}).get("severity"),
            "created_at": (post_extub_alert or {}).get("created_at"),
            "rr": ((post_extub_alert or {}).get("extra") or {}).get("rr"),
            "spo2": ((post_extub_alert or {}).get("extra") or {}).get("spo2"),
            "hours_since_extubation": ((post_extub_alert or {}).get("extra") or {}).get("hours_since_extubation"),
        },
    }
    return {"code": 0, "status": serialize_doc(status)}


@router.get("/api/patients/{patient_id}/sbt-records")
async def patient_sbt_records(patient_id: str, limit: int = Query(default=20, ge=5, le=100)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1, "name": 1, "hisBed": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    cursor = runtime.db.col("score_records").find(
        {"patient_id": str(pid), "score_type": "sbt_assessment"},
        {
            "patient_id": 1,
            "score_type": 1,
            "result": 1,
            "passed": 1,
            "trial_time": 1,
            "calc_time": 1,
            "source": 1,
            "source_code": 1,
            "duration_minutes": 1,
            "rr": 1,
            "vte_ml": 1,
            "rsbi": 1,
            "fio2": 1,
            "peep": 1,
            "minute_vent": 1,
            "raw_text": 1,
            "created_at": 1,
        },
    ).sort([("trial_time", -1), ("calc_time", -1)]).limit(limit)
    docs = [doc async for doc in cursor]
    records = [normalize_sbt_status(doc) | {"source_code": doc.get("source_code"), "minute_vent": doc.get("minute_vent")} for doc in docs]

    return {
        "code": 0,
        "summary": {
            "total_records": len(records),
            "passed_count": sum(1 for row in records if str(row.get("result") or "") == "passed"),
            "failed_count": sum(1 for row in records if str(row.get("result") or "") == "failed"),
            "documented_count": sum(1 for row in records if str(row.get("result") or "") == "documented"),
            "last_trial_time": records[0].get("trial_time") if records else None,
        },
        "records": serialize_doc(records),
    }


@router.get("/api/patients/{patient_id}/weaning-timeline")
async def patient_weaning_timeline(patient_id: str, limit: int = Query(default=40, ge=10, le=120)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    pid_str = str(pid)
    timeline: list[dict] = []

    sbt_cursor = runtime.db.col("score_records").find(
        {"patient_id": pid_str, "score_type": "sbt_assessment"},
        {
            "result": 1,
            "passed": 1,
            "trial_time": 1,
            "calc_time": 1,
            "source": 1,
            "source_code": 1,
            "duration_minutes": 1,
            "rr": 1,
            "vte_ml": 1,
            "rsbi": 1,
            "fio2": 1,
            "peep": 1,
            "minute_vent": 1,
            "raw_text": 1,
        },
    ).sort([("trial_time", -1), ("calc_time", -1)]).limit(limit)
    sbt_docs = [doc async for doc in sbt_cursor]
    sbt_records = [normalize_sbt_status(doc) | {"source_code": doc.get("source_code"), "minute_vent": doc.get("minute_vent")} for doc in sbt_docs]
    for row in sbt_records:
        timeline.append(
            {
                "time": row.get("trial_time"),
                "event_type": "sbt",
                "title": row.get("label"),
                "status": row.get("result"),
                "severity": "warning" if row.get("result") == "passed" else "high" if row.get("result") == "failed" else "info",
                "source": row.get("source"),
                "detail": {
                    "duration_minutes": row.get("duration_minutes"),
                    "rr": row.get("rr"),
                    "vte_ml": row.get("vte_ml"),
                    "rsbi": row.get("rsbi"),
                    "fio2": row.get("fio2"),
                    "peep": row.get("peep"),
                    "minute_vent": row.get("minute_vent"),
                    "raw_text": row.get("raw_text"),
                },
            }
        )

    weaning_cursor = runtime.db.col("score_records").find(
        {"patient_id": pid_str, "score_type": "weaning_assessment"},
        {
            "risk_score": 1,
            "score": 1,
            "risk_level": 1,
            "severity": 1,
            "recommendation": 1,
            "factors": 1,
            "gate_failures": 1,
            "pf_ratio": 1,
            "fio2": 1,
            "peep": 1,
            "rsbi": 1,
            "rr": 1,
            "vte_ml": 1,
            "map": 1,
            "rass": 1,
            "gcs": 1,
            "fluid_overload_pct": 1,
            "ventilation_days": 1,
            "calc_time": 1,
        },
    ).sort("calc_time", -1).limit(limit)
    async for doc in weaning_cursor:
        row = normalize_weaning_status(doc)
        timeline.append(
            {
                "time": row.get("updated_at"),
                "event_type": "weaning_assessment",
                "title": row.get("recommendation") or "撤机评估",
                "status": row.get("risk_level"),
                "severity": row.get("severity"),
                "source": "score_records",
                "detail": {
                    "risk_score": row.get("risk_score"),
                    "factors": row.get("factors"),
                    "gate_failures": row.get("gate_failures"),
                    "pf_ratio": row.get("pf_ratio"),
                    "fio2": row.get("fio2"),
                    "peep": row.get("peep"),
                    "rsbi": row.get("rsbi"),
                    "rr": row.get("rr"),
                    "vte_ml": row.get("vte_ml"),
                    "map": row.get("map"),
                    "rass": row.get("rass"),
                    "gcs": row.get("gcs"),
                    "fluid_overload_pct": row.get("fluid_overload_pct"),
                    "ventilation_days": row.get("ventilation_days"),
                },
            }
        )

    alert_cursor = runtime.db.col("alert_records").find(
        {
            "patient_id": {"$in": [pid_str, pid]},
            "alert_type": {"$in": ["weaning", "post_extubation_failure_risk", "liberation_bundle"]},
        },
        {"alert_type": 1, "name": 1, "severity": 1, "created_at": 1, "extra": 1, "explanation": 1},
    ).sort("created_at", -1).limit(limit)
    async for doc in alert_cursor:
        extra = doc.get("extra") if isinstance(doc.get("extra"), dict) else {}
        timeline.append(
            {
                "time": doc.get("created_at"),
                "event_type": str(doc.get("alert_type") or "alert"),
                "title": doc.get("name") or "脱机相关预警",
                "status": extra.get("bundle_status") or extra.get("risk_level") or doc.get("severity"),
                "severity": doc.get("severity") or "warning",
                "source": "alert_records",
                "detail": {
                    "explanation": doc.get("explanation"),
                    "hours_since_extubation": extra.get("hours_since_extubation"),
                    "rr": extra.get("rr"),
                    "spo2": extra.get("spo2"),
                    "bundle_lights": extra.get("lights"),
                    "compliance": extra.get("compliance"),
                },
            }
        )

    bind_cursor = runtime.db.col("deviceBind").find(
        {"pid": pid_str},
        {"type": 1, "bindTime": 1, "unBindTime": 1, "deviceName": 1, "name": 1},
    ).sort("bindTime", -1).limit(limit)
    async for doc in bind_cursor:
        dtype = str(doc.get("type") or "").lower()
        device_name = str(doc.get("deviceName") or doc.get("name") or "")
        if not any(key in dtype for key in ["vent", "ett"]) and not any(key in device_name.lower() for key in ["vent", "呼吸", "气管插管"]):
            continue
        if isinstance(doc.get("bindTime"), datetime):
            timeline.append(
                {
                    "time": doc.get("bindTime"),
                    "event_type": "vent_bind",
                    "title": f"建立气道/机械通气: {device_name or dtype or '呼吸支持'}",
                    "status": "started",
                    "severity": "info",
                    "source": "deviceBind",
                    "detail": {"device_type": dtype, "device_name": device_name},
                }
            )
        if isinstance(doc.get("unBindTime"), datetime):
            timeline.append(
                {
                    "time": doc.get("unBindTime"),
                    "event_type": "extubation",
                    "title": f"停止气道/机械通气: {device_name or dtype or '呼吸支持'}",
                    "status": "stopped",
                    "severity": "info",
                    "source": "deviceBind",
                    "detail": {"device_type": dtype, "device_name": device_name},
                }
            )

    sat_events = await runtime.alert_engine._get_recent_text_events(pid, ["sat", "唤醒试验", "停镇静"], hours=168, limit=20)
    for event in sat_events:
        timeline.append(
            {
                "time": event.get("time"),
                "event_type": "sat",
                "title": "SAT/停镇静记录",
                "status": "documented",
                "severity": "info",
                "source": "bedside_text",
                "detail": {
                    "code": event.get("code"),
                    "text": " ".join(str(event.get(k) or "") for k in ("code", "strVal", "value")).strip(),
                },
            }
        )

    liberation_bundle = await runtime.alert_engine.get_liberation_bundle_status(patient)
    latest_weaning_doc = await runtime.db.col("score_records").find_one(
        {"patient_id": pid_str, "score_type": "weaning_assessment"},
        sort=[("calc_time", -1)],
    )
    latest_sbt_doc = await runtime.db.col("score_records").find_one(
        {"patient_id": pid_str, "score_type": "sbt_assessment"},
        sort=[("trial_time", -1), ("calc_time", -1)],
    )

    timeline.sort(key=lambda item: item.get("time") or datetime.min, reverse=True)
    timeline = timeline[:limit]

    summary_payload = {
        "timeline_count": len(timeline),
        "sbt_total": len(sbt_records),
        "sbt_passed_count": sum(1 for row in sbt_records if str(row.get("result") or "") == "passed"),
        "sbt_failed_count": sum(1 for row in sbt_records if str(row.get("result") or "") == "failed"),
        "latest_sbt": serialize_doc(normalize_sbt_status(latest_sbt_doc)),
        "latest_weaning": serialize_doc(normalize_weaning_status(latest_weaning_doc)),
        "liberation_bundle": serialize_doc(liberation_bundle),
    }
    ai_summary = await summarize_weaning_timeline(
        {
            "patient": serialize_doc(patient),
            "summary": summary_payload,
            "timeline": serialize_doc(timeline[:20]),
        }
    )

    return {
        "code": 0,
        "patient": serialize_doc(patient),
        "summary": summary_payload,
        "ai_summary": ai_summary,
        "timeline": serialize_doc(timeline),
    }

