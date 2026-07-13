from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Query, Request

from app import runtime
from app.services.clinical_adoption_service import ClinicalAdoptionService, _normalize_role_key
from app.services.workflow_summary_service import build_clinical_summary, build_patient_priority
from app.utils.analytics_ai import summarize_weaning_timeline
from app.utils.alerting import derive_sepsis_bundle_status, normalize_sbt_status, normalize_weaning_status
from app.utils.patient_helpers import admitted_patient_query, calculate_age, infer_clinical_tags, research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


def _patient_diagnosis(doc: dict) -> str:
    for key in (
        "clinicalDiagnosis",
        "admissionDiagnosis",
        "diagnosis",
        "hisDiagnosis",
        "hisDiagnose",
        "mainDiagnosis",
        "primaryDiagnosis",
        "allDiagnosis",
        "dischargedDiagnosis",
    ):
        value = str(doc.get(key) or "").strip()
        if value:
            return value
    return ""


@router.get("/api/departments")
async def get_departments():
    """获取所有科室及在院患者数量"""
    col = runtime.db.col("patient")
    pipeline = [
        {"$match": admitted_patient_query()},
        {
            "$group": {
                "_id": {
                    "dept": {"$ifNull": ["$hisDept", "$dept"]},
                    "deptCode": {"$ifNull": ["$deptCode", ""]},
                },
                "patientCount": {"$sum": 1},
            }
        },
        {"$match": {"_id.dept": {"$ne": None}}},
        {"$sort": {"patientCount": -1}},
    ]
    departments = []
    cursor = await col.aggregate(pipeline)
    async for doc in cursor:
        group = doc.get("_id") or {}
        departments.append(
            {
                "dept": group.get("dept"),
                "deptCode": group.get("deptCode") or "",
                "patientCount": doc["patientCount"],
            }
        )
    return {"code": 0, "departments": departments}


@router.get("/api/patients")
async def get_patients(
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
    patient_scope: Optional[str] = Query('all', description="患者范围: in_dept / out_dept / all"),
):
    """获取患者列表，可按科室与科研范围筛选"""
    query: dict = research_patient_scope_query(patient_scope)
    if dept:
        query = {"$and": [query, {"$or": [{"hisDept": dept}, {"dept": dept}, {"deptName": dept}, {"department": dept}, {"departmentName": dept}]}]}
    elif dept_code:
        query = {"$and": [query, {"$or": [{"deptCode": dept_code}, {"dept_code": dept_code}, {"departmentCode": dept_code}]}]}

    cursor = runtime.db.col("patient").find(query).sort("hisBed", 1).limit(200)
    patients = []
    async for doc in cursor:
        row = serialize_doc(doc)
        row["diagnosis"] = row.get("diagnosis") or _patient_diagnosis(doc)
        if not row.get("age"):
            row["age"] = calculate_age(doc.get("birthday"))
        row["clinicalTags"] = infer_clinical_tags(doc)
        patients.append(row)
    return {"code": 0, "patients": patients}


@router.get("/api/patients/vitals-batch")
async def batch_vitals(
    dept: Optional[str] = Query(None),
    dept_code: Optional[str] = Query(None),
    patient_scope: Optional[str] = Query("in_dept"),
    debug_patient: Optional[str] = Query(None, description="调试：指定患者 _id，返回详细链路"),
    debug_name: Optional[str] = Query(None, description="调试：按姓名查找患者，返回详细链路"),
):
    """批量获取在科患者最新生命体征。deviceCap 优先，bedside 兜底，alert_snapshot 兜底。"""
    from app.routers.patient_data import _vital_codes, _fallback_vitals_from_alert_snapshot
    from app.utils.patient_data import cap_value, get_device_id_by_bed

    query = research_patient_scope_query(patient_scope)
    if dept_code:
        query = {"$and": [query, {"$or": [{"deptCode": dept_code}, {"dept_code": dept_code}, {"departmentCode": dept_code}]}]}
    elif dept:
        query = {"$and": [query, {"$or": [{"hisDept": dept}, {"dept": dept}]}]}

    # 收集患者 pid/hisPid/deviceId
    pid_map: dict[str, str] = {}
    all_pids: list[str] = []
    patient_docs: dict[str, dict] = {}  # patient_id → patient doc (for bed fallback)
    device_ids: dict[str, str] = {}  # pid → deviceID
    debug_info: dict = {} if debug_patient else None
    cursor = runtime.db.col("patient").find(
        query, {"_id": 1, "hisPid": 1, "hisPID": 1, "hisBed": 1, "bed": 1, "deptCode": 1, "name": 1, "hisName": 1}
    ).limit(200)
    async for doc in cursor:
        patient_id = str(doc.get("_id"))
        pid_map[patient_id] = patient_id
        all_pids.append(patient_id)
        patient_docs[patient_id] = doc
        his_pid = str(doc.get("hisPid") or doc.get("hisPID") or "").strip()
        if his_pid and his_pid != patient_id:
            pid_map[his_pid] = patient_id
            all_pids.append(his_pid)

    if not all_pids:
        logger.info("vitals-batch: 0 patients found, returning empty")
        return {"code": 0, "vitals": {}}

    logger.info("vitals-batch: found %d patients, sample ids: %s", len(pid_map), list(pid_map.keys())[:5])

    # 调试：按姓名解析 patient_id
    if debug_name and not debug_patient:
        for pid, doc in patient_docs.items():
            name = str(doc.get("name") or doc.get("hisName") or "")
            if debug_name in name:
                debug_patient = pid
                logger.info("vitals-batch: debug resolved name '%s' → pid=%s", debug_name, pid)
                break

    # 查 deviceBind 获取 deviceID（用 _id 和 hisPid 两个 pid 匹配）
    bind_cursor = runtime.db.col("deviceBind").find(
        {"pid": {"$in": all_pids}, "unBindTime": None},
        {"pid": 1, "deviceID": 1},
    ).limit(200)
    async for doc in bind_cursor:
        did = str(doc.get("deviceID") or "")
        pid = str(doc.get("pid") or "")
        if did and pid:
            device_ids[pid] = did
    logger.info("vitals-batch: deviceBind matched %d pids: %s", len(device_ids), list(device_ids.keys())[:5])

    # 对没有 deviceBind 的患者，尝试通过床位号从 deviceOnline/deviceInfo 兜底查找
    bound_patient_ids = {pid_map.get(pid, pid) for pid in device_ids}
    for patient_id, doc in patient_docs.items():
        if patient_id in bound_patient_ids:
            continue
        bed = doc.get("hisBed") or doc.get("bed")
        dept = doc.get("deptCode")
        if bed:
            did = await get_device_id_by_bed(bed, dept)
            if did:
                device_ids[patient_id] = did
    logger.info("vitals-batch: total device_ids after bed fallback: %d", len(device_ids))

    code_map = _vital_codes()
    all_codes = list(set(
        code_map.get("hr", []) + code_map.get("spo2", []) +
        code_map.get("rr", []) + code_map.get("temp", []) +
        code_map.get("sbp", []) + code_map.get("dbp", []) + code_map.get("map", [])
    ))
    code_to_vital: dict[str, str] = {}
    for vital, codes in code_map.items():
        for c in codes:
            code_to_vital[c] = vital

    def _extract_latest(rows: list[dict], code_to_vital: dict, id_field: str = "pid") -> dict[str, dict]:
        """从排序好的记录中提取每个 patient_id 每个 vital 的最新值。"""
        result: dict[str, dict] = {}
        for doc in rows:
            key = str(doc.get(id_field) or "")
            patient_id = pid_map.get(key)
            if not patient_id:
                continue
            code = str(doc.get("code") or "")
            vital = code_to_vital.get(code)
            if not vital:
                continue
            val = cap_value(doc)
            if val is None:
                continue
            row = result.setdefault(patient_id, {})
            if vital not in row:
                row[vital] = round(float(val), 1)
                row["time"] = doc.get("time")
                row["source"] = "deviceCap"
        return result

    # 优先查 deviceCap
    device_id_list = list(set(device_ids.values()))
    result: dict[str, dict] = {}
    logger.info("vitals-batch: %d patients, %d device bindings, %d vital codes", len(pid_map), len(device_ids), len(all_codes))
    # deviceCap 优先：加 2 小时时间窗口限制扫描量
    device_id_list = list(set(device_ids.values()))
    result: dict[str, dict] = {}
    did_to_pid = {did: pid for pid, did in device_ids.items()}
    if device_id_list:
        since = datetime.now() - timedelta(hours=2)
        cap_pipeline = [
            {"$match": {"deviceID": {"$in": device_id_list}, "code": {"$in": all_codes}, "time": {"$gte": since}}},
            {"$sort": {"deviceID": 1, "code": 1, "time": -1}},
            {"$group": {
                "_id": {"deviceID": "$deviceID", "code": "$code"},
                "fVal": {"$first": "$fVal"},
                "intVal": {"$first": "$intVal"},
                "strVal": {"$first": "$strVal"},
                "time": {"$first": "$time"},
            }},
        ]
        try:
            async for doc in await runtime.db.col("deviceCap").aggregate(cap_pipeline, allowDiskUse=True):
                did = str((doc.get("_id") or {}).get("deviceID") or "")
                pid = did_to_pid.get(did)
                if not pid:
                    continue
                code = str((doc.get("_id") or {}).get("code") or "")
                vital = code_to_vital.get(code)
                if not vital:
                    continue
                val = cap_value(doc)
                if val is None:
                    continue
                row = result.setdefault(pid, {})
                if vital not in row:
                    row[vital] = round(float(val), 1)
                    row["time"] = doc.get("time")
                    row["source"] = "deviceCap"
        except Exception as e:
            logger.warning("vitals-batch: deviceCap aggregate failed: %s", e)
    logger.info("vitals-batch: deviceCap covered %d patients", len(result))

    # bedside 兜底：只补 deviceCap 没有的患者
    covered_patient_ids = set(result.keys())
    missing_pids: list[str] = []
    seen_missing: set[str] = set()
    for pid in all_pids:
        patient_id = pid_map.get(pid, pid)
        if patient_id in covered_patient_ids:
            continue
        if pid not in seen_missing:
            seen_missing.add(pid)
            missing_pids.append(pid)
    logger.info("vitals-batch: deviceCap covered %d patients, %d missing (pids: %s)", len(covered_patient_ids), len(missing_pids), missing_pids[:5])
    if missing_pids:
        since_bedside = datetime.now() - timedelta(hours=24)
        aggregation_pipeline = [
            {"$match": {"pid": {"$in": missing_pids}, "code": {"$in": all_codes}, "time": {"$gte": since_bedside}}},
            {"$sort": {"pid": 1, "code": 1, "time": -1}},
            {"$group": {
                "_id": {"pid": "$pid", "code": "$code"},
                "fVal": {"$first": "$fVal"},
                "intVal": {"$first": "$intVal"},
                "strVal": {"$first": "$strVal"},
                "time": {"$first": "$time"},
            }},
        ]
        async for doc in await runtime.db.col("bedside").aggregate(aggregation_pipeline, allowDiskUse=True):
            pid_key = str((doc.get("_id") or {}).get("pid") or "")
            patient_id = pid_map.get(pid_key)
            if not patient_id:
                continue
            code = str((doc.get("_id") or {}).get("code") or "")
            vital = code_to_vital.get(code)
            if not vital:
                continue
            val = doc.get("fVal")
            if val is None:
                val = doc.get("intVal")
            if val is None:
                try:
                    val = float(str(doc.get("strVal") or "").strip())
                except Exception:
                    continue
            if val is None:
                continue
            row = result.setdefault(patient_id, {})
            if vital not in row:
                row[vital] = round(float(val), 1)
                row["time"] = doc.get("time")
                row["source"] = "bedside"
        logger.info("vitals-batch: after bedside fallback, covered %d patients", len(result))

    # alert_snapshot 兜底：对仍然没有数据的患者，从最近告警快照提取
    still_missing = [pid for pid in patient_docs if pid not in result]
    logger.info("vitals-batch: before alert_snapshot, %d patients still missing: %s", len(still_missing), still_missing[:5])
    if still_missing:
        # 快照字段名 → 统一内部 vital key（与 deviceCap/bedside 主路径对齐）
        _SNAPSHOT_KEY_MAP = {
            "hr": "hr",
            "spo2": "spo2",
            "rr": "rr",
            "temp": "temp",
            "t": "temp",
            "nibp_sys": "sbp",
            "ibp_sys": "sbp",
            "sbp": "sbp",
            "nibp_dia": "dbp",
            "ibp_dia": "dbp",
            "dbp": "dbp",
            "nibp_map": "map",
            "ibp_map": "map",
            "map": "map",
        }
        for pid in still_missing:
            try:
                snapshot_vitals = await _fallback_vitals_from_alert_snapshot(pid)
                if snapshot_vitals:
                    row: dict = {}
                    for raw_key, vital in _SNAPSHOT_KEY_MAP.items():
                        if vital in row:
                            continue
                        val = snapshot_vitals.get(raw_key)
                        if val is not None:
                            try:
                                row[vital] = round(float(val), 1)
                            except (TypeError, ValueError):
                                continue
                    if row:
                        row["time"] = snapshot_vitals.get("time")
                        row["source"] = "alert_snapshot"
                        result[pid] = row
            except Exception:
                pass
        logger.info("vitals-batch: after alert_snapshot fallback, covered %d/%d patients", len(result), len(pid_map))

    logger.info("vitals-batch: FINAL returning vitals for %d/%d patients", len(result), len(patient_docs))

    # 调试模式：返回指定患者的完整链路
    if debug_patient:
        dpid = debug_patient.strip()
        doc = patient_docs.get(dpid, {})
        dinfo = {
            "patient_id": dpid,
            "name": doc.get("name") or doc.get("hisName"),
            "hisBed": doc.get("hisBed") or doc.get("bed"),
            "hisPid": doc.get("hisPid") or doc.get("hisPID"),
            "in_pid_map": dpid in pid_map,
            "in_device_ids": dpid in device_ids,
            "deviceID": device_ids.get(dpid),
            "in_result": dpid in result,
            "result_vitals": serialize_doc(result.get(dpid, {})),
            "device_bind_pids_sample": list(device_ids.keys())[:10],
            "total_patients": len(patient_docs),
            "total_result": len(result),
        }
        # 查 bedside 原始数据
        bedside_raw = []
        bcursor = runtime.db.col("bedside").find(
            {"pid": {"$in": [dpid, str(doc.get("hisPid") or ""), str(doc.get("hisPID") or "")]}, "time": {"$gte": datetime.now() - timedelta(hours=24)}},
            {"pid": 1, "code": 1, "fVal": 1, "intVal": 1, "strVal": 1, "time": 1},
        ).sort("time", -1).limit(20)
        async for bdoc in bcursor:
            bedside_raw.append({
                "pid": bdoc.get("pid"),
                "code": bdoc.get("code"),
                "fVal": bdoc.get("fVal"),
                "intVal": bdoc.get("intVal"),
                "strVal": bdoc.get("strVal"),
                "time": str(bdoc.get("time")),
            })
        dinfo["bedside_raw_count"] = len(bedside_raw)
        dinfo["bedside_raw_sample"] = bedside_raw[:10]

        # 查 alert_snapshot
        snap = await _fallback_vitals_from_alert_snapshot(dpid)
        dinfo["alert_snapshot"] = serialize_doc(snap) if snap else None

        return {"code": 0, "vitals": {pid: serialize_doc(v) for pid, v in result.items()}, "debug": dinfo}

    return {"code": 0, "vitals": {pid: serialize_doc(v) for pid, v in result.items()}}


@router.get("/api/patients/priority")
async def get_patient_priority(
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
    limit: int = Query(120, ge=1, le=300, description="返回患者上限"),
):
    """按临床工作流优先级返回今日重点关注患者。"""
    rows = await build_patient_priority(runtime.db, dept=dept, dept_code=dept_code, limit=limit)
    return {"code": 0, "data": rows}


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
    row["diagnosis"] = row.get("diagnosis") or _patient_diagnosis(doc)
    if not row.get("age"):
        row["age"] = calculate_age(doc.get("birthday"))
    return {"code": 0, "patient": row}


@router.get("/api/patients/{patient_id}/clinical-summary")
async def get_patient_clinical_summary(patient_id: str, hours: int = Query(24, ge=1, le=72)):
    """患者工作流摘要：24小时事件、Top风险、恶化指标、待办。"""
    data = await build_clinical_summary(runtime.db, patient_id, hours=hours)
    if data is None:
        return {"code": 404, "message": "患者不存在或ID无效"}
    return {"code": 0, "data": data}


@router.get("/api/patients/{patient_id}/ai-watching")
async def get_ai_watching(patient_id: str, hours: int = Query(1, ge=1, le=24)):
    return await runtime.ai_watching_service.get_watching_summary(patient_id, hours)


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
    if not runtime.alert_engine:
        return {"code": 0, "assessment": None, "error": "预警引擎未就绪"}
    result = await runtime.alert_engine.evaluate_discharge_readiness(patient)
    return {"code": 0, "assessment": serialize_doc(result)}


@router.get("/api/patients/{patient_id}/transfer-handoff")
async def patient_transfer_handoff(patient_id: str):
    """转出交接风险评估（含 72h 验证）。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    if not runtime.alert_engine:
        return {"code": 0, "handoff": None, "error": "预警引擎未就绪"}
    doc = await runtime.alert_engine.get_latest_transfer_handoff(str(pid))
    if not doc:
        return {"code": 0, "handoff": None}
    return {"code": 0, "handoff": serialize_doc(doc)}


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
        result = await asyncio.wait_for(
            runtime.alert_engine.get_similar_case_outcomes(patient, limit=limit),
            timeout=8.0,
        )
    except asyncio.TimeoutError:
        logger.warning("similar-case-outcomes api timeout fallback patient_id=%s", patient_id)
        fallback_builder = getattr(runtime.alert_engine, "_degraded_similar_case_result", None)
        if callable(fallback_builder):
            result = fallback_builder(patient, error="timeout", limit=limit)
        else:
            result = {
                "current_profile": {"patient_id": patient_id},
                "summary": {
                    "matched_cases": 0,
                    "displayed_cases": 0,
                    "degraded": True,
                    "fallback_message": "相似病例分析超时，已降级为基础模式。",
                },
                "cases": [],
            }
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
    doc = await runtime.db.col("score").find_one(query, sort=[("calc_time", -1)])
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
    cursor = runtime.db.col("score").find(query).sort("calc_time", -1).limit(limit)
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

    record = await runtime.db.col("score").find_one(
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
    await runtime.db.col("score").update_one({"_id": rid}, {"$set": update_fields})
    updated = await runtime.db.col("score").find_one({"_id": rid})
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

    cursor = runtime.db.col("score").find(query).sort("calc_time", -1).limit(min(max(limit * 3, 80), 300))
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
        "pending_review": await runtime.db.col("score").count_documents({"score_type": "personalized_thresholds", "status": "pending_review"}),
        "approved": await runtime.db.col("score").count_documents({"score_type": "personalized_thresholds", "status": "approved"}),
        "rejected": await runtime.db.col("score").count_documents({"score_type": "personalized_thresholds", "status": "rejected"}),
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
    if not runtime.alert_engine:
        return {"code": 0, "status": None, "error": "预警引擎未就绪"}
    status = await runtime.alert_engine.get_ecash_status(patient)
    return {"code": 0, "status": serialize_doc(status)}


def _resolve_clinical_actor_role(request: Request, payload: dict | None = None) -> tuple[str, str, str]:
    """解析临床操作者身份 — actor/role/dept。

    actor 来自认证身份（X-User-Id header），role 来自 X-User-Role header 或 account 解析。
    仅 doctor / director 可确认适用性和个体目标；
    nurse 只能记录执行；
    admin 不能替代临床确认。
    """
    body = payload if isinstance(payload, dict) else {}
    actor = str(
        body.get("actor") or request.headers.get("x-user-id") or request.headers.get("X-User-Id") or ""
    ).strip()
    role_raw = str(
        body.get("role") or request.headers.get("x-user-role") or request.headers.get("X-User-Role") or ""
    ).strip()
    role = _normalize_role_key(role_raw or "doctor", "doctor")
    dept = str(
        body.get("dept") or request.headers.get("x-user-dept") or request.headers.get("X-User-Dept") or ""
    ).strip()
    if not actor:
        raise HTTPException(status_code=401, detail="需要认证身份（actor/x-user-id）")
    return actor, role, dept


def _require_clinician_role(role: str) -> None:
    """仅 doctor/director 可通过临床确认。"""
    if role not in ("doctor", "director"):
        raise HTTPException(
            status_code=403,
            detail=f"临床确认需要医生或主任角色，当前角色: {role}。护士可记录执行，管理员不能替代临床确认。",
        )


def _require_clinical_staff_role(role: str) -> None:
    """doctor/director/nurse/head_nurse 均可记录执行。"""
    if role not in ("doctor", "director", "nurse", "head_nurse"):
        raise HTTPException(
            status_code=403,
            detail=f"记录执行需要临床角色，当前角色: {role}",
        )


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
    # 查询 v2 tracker 优先，回退到旧版
    tracker = await runtime.db.col("score").find_one(
        {
            "patient_id": pid_str,
            "score_type": {"$in": ["sepsis_bundle_tracker", "sepsis_antibiotic_bundle"]},
            "bundle_type": {"$in": ["sepsis_hour1_bundle_v2", "sepsis_hour1_bundle", "sepsis_1h_antibiotic"]},
            "is_active": True,
        },
        sort=[("bundle_started_at", -1)],
    )
    if not tracker:
        tracker = await runtime.db.col("score").find_one(
            {
                "patient_id": pid_str,
                "score_type": {"$in": ["sepsis_bundle_tracker", "sepsis_antibiotic_bundle"]},
                "bundle_type": {"$in": ["sepsis_hour1_bundle_v2", "sepsis_hour1_bundle", "sepsis_1h_antibiotic"]},
            },
            sort=[("bundle_started_at", -1)],
        )

    return {"code": 0, "status": serialize_doc(derive_sepsis_bundle_status(tracker, now=datetime.now()))}


# ---- 临床确认端点 ----

@router.patch("/api/patients/{patient_id}/sepsis-bundle/element-review")
async def sepsis_bundle_element_clinical_review(
    patient_id: str,
    request: Request,
    payload: dict = Body(...),
):
    """医生/主任确认 Bundle 元素的适用性和个体化目标。

    RBAC: 仅 doctor / director 角色。
    payload:
      - element_key: 元素键名 (e.g. "fluid_resuscitation")
      - applicability: 确认的适用性 (required/not_applicable/contraindicated/individualized)
      - individualized_target_ml: 个体化目标（individualized 时必填）
      - reason: 确认原因
      - version: 乐观锁版本号
      - actor: 操作者（可选，优先取 header）
    """
    actor, role, dept = _resolve_clinical_actor_role(request, payload)
    _require_clinician_role(role)

    element_key = str(payload.get("element_key") or "").strip()
    if not element_key:
        return {"code": 400, "message": "缺少 element_key"}
    allowed_applicability = {"required", "not_applicable", "contraindicated", "individualized"}
    applicability = str(payload.get("applicability") or "").strip().lower()
    if applicability not in allowed_applicability:
        return {"code": 400, "message": f"applicability 必须是 {allowed_applicability} 之一"}

    if applicability == "individualized" and not payload.get("individualized_target_ml"):
        return {"code": 400, "message": "individualized 模式需提供 individualized_target_ml"}

    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return {"code": 400, "message": "必须提供确认原因 (reason)"}

    expected_version = int(payload.get("version") or -1)

    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    pid_str = str(pid)
    tracker = await runtime.db.col("score").find_one(
        {"patient_id": pid_str, "score_type": "sepsis_bundle_tracker", "is_active": True},
        sort=[("bundle_started_at", -1)],
    )
    if not tracker:
        return {"code": 404, "message": "未找到活跃的脓毒症 Bundle"}

    elements = tracker.get("bundle_elements") if isinstance(tracker.get("bundle_elements"), dict) else {}
    item = elements.get(element_key)
    if not isinstance(item, dict):
        return {"code": 404, "message": f"未知元素: {element_key}"}

    # 乐观锁
    review = item.get("clinical_review") if isinstance(item.get("clinical_review"), dict) else {}
    current_version = int(review.get("version") or 0)
    if expected_version >= 0 and expected_version != current_version:
        return {"code": 409, "message": f"版本冲突: 期望 v{expected_version}，当前 v{current_version}，请刷新重试"}

    now = datetime.now()
    new_version = current_version + 1

    # 更新 clinical_review
    item["clinical_review"] = {
        "status": "confirmed",
        "confirmed_by": actor,
        "confirmed_at": now,
        "role": role,
        "reason": reason,
        "version": new_version,
    }

    # 更新 applicability
    old_applicability = item.get("applicability")
    item["applicability"] = applicability

    # 更新 target（如果是 individualized 且有补液目标）
    if applicability == "individualized" and element_key == "fluid_resuscitation":
        target_data = item.get("target") if isinstance(item.get("target"), dict) else {}
        target_data["individualized_target_ml"] = float(payload.get("individualized_target_ml", 0))
        item["target"] = target_data

    # 更新执行状态（适用性变更只影响 applicability，不污染 execution.status）
    exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else {}
    if applicability in ("not_applicable", "contraindicated"):
        exec_data["status"] = "cancelled"
    # individualized 不在 execution.status 中出现 — execution 保持 pending/met/met_late
    if old_applicability in ("not_applicable", "contraindicated") and applicability not in ("not_applicable", "contraindicated"):
        # 从禁忌/不适用恢复 → 重置为 pending
        exec_data["status"] = "pending"
    item["execution"] = exec_data

    # 审计日志
    audit_entry = {
        "action": "element_clinical_review",
        "element_key": element_key,
        "actor": actor,
        "role": role,
        "dept": dept,
        "old_applicability": old_applicability,
        "new_applicability": applicability,
        "reason": reason,
        "version": new_version,
        "timestamp": now,
    }
    audit_log = list(tracker.get("audit_log") or [])
    audit_log.append(audit_entry)

    elements[element_key] = item

    # 如果医生确认进入脓毒症路径，记录 clinician_confirmed_at
    set_fields: dict = {
        "bundle_elements": elements,
        "audit_log": audit_log,
        "updated_at": now,
    }
    if element_key == "clinician_path_confirmation":
        set_fields["clinician_confirmed_at"] = now

    await runtime.db.col("score").update_one(
        {"_id": tracker["_id"]},
        {"$set": set_fields},
    )

    return {
        "code": 0,
        "message": "临床确认已记录",
        "element_key": element_key,
        "applicability": applicability,
        "clinical_review_version": new_version,
        "audit_entry": audit_entry,
    }


@router.patch("/api/patients/{patient_id}/sepsis-bundle/record-execution")
async def sepsis_bundle_record_execution(
    patient_id: str,
    request: Request,
    payload: dict = Body(...),
):
    """记录 Bundle 元素执行（护士/医生均可）。

    RBAC: doctor/director/nurse/head_nurse。
    payload:
      - element_key: 元素键名
      - status: 执行状态 (met/met_late/completed_before)
      - completed_at: 完成时间 (ISO8601)
      - value: 执行值（如乳酸数值）
      - reason: 备注
      - actor: 操作者（可选，优先取 header）
    """
    actor, role, dept = _resolve_clinical_actor_role(request, payload)
    _require_clinical_staff_role(role)

    element_key = str(payload.get("element_key") or "").strip()
    if not element_key:
        return {"code": 400, "message": "缺少 element_key"}
    allowed_status = {"met", "met_late", "completed_before"}
    exec_status = str(payload.get("status") or "").strip()
    if exec_status not in allowed_status:
        return {"code": 400, "message": f"status 必须是 {allowed_status} 之一"}

    completed_at_raw = payload.get("completed_at")
    completed_at = None
    if completed_at_raw:
        try:
            completed_at = datetime.fromisoformat(str(completed_at_raw).replace("Z", "+00:00"))
        except Exception:
            return {"code": 400, "message": "completed_at 格式无效，需 ISO8601"}

    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    pid_str = str(pid)
    tracker = await runtime.db.col("score").find_one(
        {"patient_id": pid_str, "score_type": "sepsis_bundle_tracker", "is_active": True},
        sort=[("bundle_started_at", -1)],
    )
    if not tracker:
        return {"code": 404, "message": "未找到活跃的脓毒症 Bundle"}

    elements = tracker.get("bundle_elements") if isinstance(tracker.get("bundle_elements"), dict) else {}
    item = elements.get(element_key)
    if not isinstance(item, dict):
        return {"code": 404, "message": f"未知元素: {element_key}"}

    # 检查适用性
    applicability = str(item.get("applicability") or "")
    if applicability in ("not_applicable", "contraindicated"):
        return {"code": 400, "message": f"元素已标记为 {applicability}，不能记录执行"}

    now = datetime.now()
    reason = str(payload.get("reason") or "").strip()

    # 更新执行状态
    exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else {}
    exec_data["status"] = exec_status
    exec_data["completed_at"] = completed_at or now
    exec_data["recorded_by"] = actor
    exec_data["recorded_at"] = now
    exec_data["value"] = payload.get("value")
    item["execution"] = exec_data

    # completed_before 额外信息
    if exec_status == "completed_before" and payload.get("completed_before_info"):
        exec_data["completed_before_info"] = payload["completed_before_info"]

    # 审计日志
    audit_entry = {
        "action": "record_execution",
        "element_key": element_key,
        "actor": actor,
        "role": role,
        "dept": dept,
        "execution_status": exec_status,
        "completed_at": completed_at or now,
        "reason": reason,
        "timestamp": now,
    }
    audit_log = list(tracker.get("audit_log") or [])
    audit_log.append(audit_entry)

    elements[element_key] = item

    await runtime.db.col("score").update_one(
        {"_id": tracker["_id"]},
        {"$set": {"bundle_elements": elements, "audit_log": audit_log, "updated_at": now}},
    )

    return {
        "code": 0,
        "message": "执行记录已保存",
        "element_key": element_key,
        "execution_status": exec_status,
        "audit_entry": audit_entry,
    }


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
    weaning_doc = await runtime.db.col("score").find_one(
        {"patient_id": pid_str, "score_type": "weaning_assessment"},
        sort=[("calc_time", -1)],
    )
    sbt_doc = await runtime.db.col("score").find_one(
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

    cursor = runtime.db.col("score").find(
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

    sbt_cursor = runtime.db.col("score").find(
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

    weaning_cursor = runtime.db.col("score").find(
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
                "source": "score",
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

    sat_events = []
    if runtime.alert_engine:
        try:
            sat_events = await runtime.alert_engine._get_recent_text_events(pid, ["sat", "唤醒试验", "停镇静"], hours=168, limit=20)
        except Exception:
            pass
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

    liberation_bundle = {}
    if runtime.alert_engine:
        try:
            liberation_bundle = await runtime.alert_engine.get_liberation_bundle_status(patient)
        except Exception:
            pass
    latest_weaning_doc = await runtime.db.col("score").find_one(
        {"patient_id": pid_str, "score_type": "weaning_assessment"},
        sort=[("calc_time", -1)],
    )
    latest_sbt_doc = await runtime.db.col("score").find_one(
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

