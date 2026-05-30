from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.config import get_config
from app.services.patient_narrative_service import PatientNarrativeService
from app.services.vital_trajectory_forecaster import SUPPORTED_CODES, get_vital_trajectory_forecaster
from app.alert_engine.acid_base_analyzer import (
    SUPPORTIVE_FALLBACK_FIELDS,
    extract_acid_base_snapshot,
    interpret_acid_base,
    is_blood_gas_snapshot,
)
from app.utils.patient_data import (
    beautify_freq,
    extract_assessment_from_bedside_doc,
    extract_assessment_from_score_doc,
    fetch_dc_exam_items_by_his_pid,
    fetch_smartcare_bga_items_by_his_pid,
    get_device_id,
    infer_device_type,
    lab_group_key,
    lab_time,
    latest_params_by_device,
    latest_params_by_pid,
    load_dc_doc_map,
    load_sc_doc_map,
    merge_assessment_records,
    param_series_by_pid,
    param_series_by_pids,
)
from app.utils.patient_helpers import calculate_age, patient_his_pid, patient_his_pid_candidates
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()


class _AsyncListCursor:
    """将 list 包装为 async cursor，兼容 `async for row in cursor` 模式。"""
    def __init__(self, rows: list):
        self._rows = rows
        self._idx = 0

    def sort(self, *_a, **_kw):
        return self

    def limit(self, _n):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return row


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
logger = logging.getLogger("icu-alert")

BEDCARD_OPTIONAL_TIMEOUT_SECONDS = 0.12
_BEDCARD_CACHE_TTL_SECONDS = 8.0
_bedcard_cache: dict[str, tuple[datetime, dict]] = {}


async def _optional(coro, default, *, timeout: float = BEDCARD_OPTIONAL_TIMEOUT_SECONDS):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
        return default


def _vital_codes() -> dict[str, list[str]]:
    cfg = (runtime.config.yaml_cfg or {}) if getattr(runtime, "config", None) is not None else {}
    vital_cfg = cfg.get("vital_signs", {}) if isinstance(cfg, dict) else {}

    def _single(section: str, default: str) -> str:
        row = vital_cfg.get(section)
        if isinstance(row, dict):
            value = str(row.get("code") or "").strip()
            if value:
                return value
        return default

    def _multi(section: str, default: list[str]) -> list[str]:
        rows = vital_cfg.get(section)
        if isinstance(rows, list):
            cleaned = [str(item).strip() for item in rows if str(item).strip()]
            if cleaned:
                return cleaned
        return default

    def _ordered_unique(*groups: list[str] | str) -> list[str]:
        values: list[str] = []
        for group in groups:
            rows = group if isinstance(group, list) else [group]
            for item in rows:
                value = str(item or "").strip()
                if value and value not in values:
                    values.append(value)
        return values

    hr_codes = []
    for code in [
        _single("heart_rate", "param_HR"),
        _single("pulse_rate", "param_PR"),
    ]:
        if code not in hr_codes:
            hr_codes.append(code)

    return {
        # 2026-05-22 实库核对：bedside/deviceCap 生命体征使用以下 code。
        "hr": _ordered_unique(hr_codes, ["param_HR", "param_PR"]),
        "spo2": _ordered_unique(_single("spo2", "param_spo2"), "param_spo2"),
        "rr": _ordered_unique(_single("resp_rate", "param_resp"), "param_resp"),
        "temp": _ordered_unique(_single("temperature", "param_T"), "param_T"),
        "sbp": _ordered_unique(_multi("sbp_priority", ["param_ibp_s", "param_nibp_s"]), ["param_ibp_s", "param_nibp_s"]),
        "dbp": _ordered_unique(_multi("dbp_priority", ["param_ibp_d", "param_nibp_d"]), ["param_ibp_d", "param_nibp_d"]),
        "map": _ordered_unique(_multi("map_priority", ["param_ibp_m", "param_nibp_m"]), ["param_ibp_m", "param_nibp_m"]),
    }


def _pick_param(params: dict, codes: list[str]) -> float | int | str | None:
    if not isinstance(params, dict):
        return None
    for code in codes:
        value = params.get(code)
        if value is not None and value != "":
            return value
    return None


def _snapshot_to_vitals(snapshot: dict | None, source: str | None) -> dict:
    if not isinstance(snapshot, dict):
        return {}
    params = snapshot.get("params")
    if not isinstance(params, dict) or not params:
        return {}

    codes = _vital_codes()
    point_time = snapshot.get("time")
    return {
        "source": source,
        "time": serialize_doc(point_time) if isinstance(point_time, datetime) else str(point_time) if point_time else None,
        "hr": _pick_param(params, codes["hr"]),
        "spo2": _pick_param(params, codes["spo2"]),
        "rr": _pick_param(params, codes["rr"]),
        "temp": _pick_param(params, codes["temp"]),
        "sbp": _pick_param(params, codes["sbp"]),
        "dbp": _pick_param(params, codes["dbp"]),
        "map": _pick_param(params, codes["map"]),
        "nibp_sys": params.get("param_nibp_s"),
        "nibp_dia": params.get("param_nibp_d"),
        "nibp_map": params.get("param_nibp_m"),
        "ibp_sys": params.get("param_ibp_s"),
        "ibp_dia": params.get("param_ibp_d"),
        "ibp_map": params.get("param_ibp_m"),
        "cvp": params.get("param_cvp"),
        "etco2": params.get("param_ETCO2"),
    }


async def _latest_bedside_vitals(pid_str: str, codes: list[str]) -> dict | None:
    """Read the most recent bedside charted vital rows directly by patient id."""
    if not pid_str or not codes:
        return None
    cursor = runtime.db.col("bedside").find(
        {"pid": pid_str, "code": {"$in": codes}, "valid": {"$ne": False}},
        {"code": 1, "time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", -1).limit(1200)
    params: dict = {}
    latest_time = None
    async for row in cursor:
        code = row.get("code")
        if not code or code in params:
            continue
        value = row.get("fVal")
        if value is None or value == "":
            value = row.get("intVal")
        if value is None or value == "":
            value = row.get("strVal")
        if value is None or value == "":
            continue
        params[code] = value
        row_time = row.get("time")
        if isinstance(row_time, datetime) and (latest_time is None or row_time > latest_time):
            latest_time = row_time
        if len(params) >= len(codes):
            break
    if not params:
        return None
    return {"params": params, "time": latest_time}


async def _fallback_vitals_from_alert_snapshot(pid_str: str) -> dict | None:
    if not pid_str:
        return None
    alert = await runtime.db.col("alert_records").find_one(
        {
            "patient_id": pid_str,
            "extra.context_snapshot.vitals": {"$exists": True},
        },
        sort=[("created_at", -1)],
    )
    if not alert:
        return None
    snapshot = ((alert.get("extra") or {}).get("context_snapshot") or {}) if isinstance(alert.get("extra"), dict) else {}
    vitals = snapshot.get("vitals") if isinstance(snapshot.get("vitals"), dict) else {}
    if not vitals:
        return None

    def _value(*keys: str) -> float | None:
        for key in keys:
            row = vitals.get(key)
            if isinstance(row, (int, float)):
                return float(row)
            if not isinstance(row, dict):
                continue
            for raw in (row.get("value"), row.get("fVal"), row.get("intVal"), row.get("strVal")):
                if raw is None or raw == "":
                    continue
                try:
                    return float(raw)
                except Exception:
                    continue
        return None

    hr = _value("hr", "heart_rate", "pulse", "pr")
    spo2 = _value("spo2", "SpO2")
    rr = _value("rr", "resp")
    sbp = _value("sbp", "sys", "systolic")
    dbp = _value("dbp", "dia", "diastolic")
    map_value = _value("map")
    temp = _value("temp", "t", "temperature")
    snapshot_time = snapshot.get("snapshot_time")

    if all(value is None for value in [hr, spo2, rr, sbp, dbp, map_value, temp]):
        return None
    return {
        "source": "alert_snapshot",
        "time": serialize_doc(snapshot_time) if isinstance(snapshot_time, datetime) else str(snapshot_time) if snapshot_time else None,
        "hr": hr,
        "spo2": spo2,
        "rr": rr,
        "temp": temp,
        "nibp_sys": sbp,
        "nibp_dia": dbp,
        "nibp_map": map_value,
        "ibp_sys": sbp,
        "ibp_dia": dbp,
        "ibp_map": map_value,
        "cvp": None,
        "etco2": None,
    }


@router.get("/api/patients/{patient_id}/vitals")
async def patient_vitals(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    pid_str = str(pid)
    patient = await runtime.db.col("patient").find_one(
        {"_id": pid},
        {"hisPid": 1, "hisPID": 1, "hisBed": 1, "bed": 1, "deptCode": 1},
    )
    his_pid = patient_his_pid(patient)
    query_pids = [pid_str]
    if his_pid:
        query_pids.append(his_pid)

    code_map = _vital_codes()
    codes = [
        *code_map["hr"],
        *code_map["spo2"],
        *code_map["rr"],
        *code_map["temp"],
        *code_map["sbp"],
        *code_map["dbp"],
        *code_map["map"],
        "param_cvp",
        "param_ETCO2",
    ]

    # 并行查询三个数据源
    async def _fetch_monitor():
        return await latest_params_by_pid(query_pids, codes)

    async def _fetch_bedside():
        return await _latest_bedside_vitals(pid_str, codes)

    async def _fetch_alert_fallback():
        return await _fallback_vitals_from_alert_snapshot(pid_str)

    monitor_snap, bedside_snap, fallback_vitals = await asyncio.gather(
        _fetch_monitor(), _fetch_bedside(), _fetch_alert_fallback(),
        return_exceptions=True,
    )
    monitor_snap = monitor_snap if not isinstance(monitor_snap, Exception) else None
    bedside_snap = bedside_snap if not isinstance(bedside_snap, Exception) else None
    fallback_vitals = fallback_vitals if not isinstance(fallback_vitals, Exception) else None

    # 合并结果：monitor 优先，bedside 补充，alert 兜底
    vitals: dict = {}
    source = None
    if monitor_snap:
        vitals = _snapshot_to_vitals(monitor_snap, "monitor")
        source = "monitor"
    elif not isinstance(monitor_snap, Exception):
        # monitor 无数据，尝试设备
        device_id = await get_device_id(pid_str, "monitor", patient_doc=patient)
        if not device_id:
            device_id = await get_device_id(pid_str, None, patient_doc=patient)
        if device_id:
            device_snap = await latest_params_by_device(device_id, codes)
            if device_snap:
                vitals = _snapshot_to_vitals(device_snap, "device")
                source = "device"

    if bedside_snap:
        bedside_vitals = _snapshot_to_vitals(bedside_snap, "nurse_manual")
        if not vitals:
            vitals = bedside_vitals
        else:
            for key, value in bedside_vitals.items():
                if vitals.get(key) in (None, "") and value not in (None, ""):
                    vitals[key] = value
    if fallback_vitals:
        if not vitals:
            vitals = fallback_vitals
        else:
            for key, value in fallback_vitals.items():
                if vitals.get(key) in (None, "") and value not in (None, ""):
                    vitals[key] = value

    return {"code": 0, "vitals": vitals}


@router.get("/api/patients/{patient_id}/labs")
async def patient_labs(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    patient_ids = patient_his_pid_candidates(patient)
    exams = []
    if patient_ids:
        his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}

        # 并行查询 BGA、exam、item
        async def _fetch_bga():
            return await fetch_smartcare_bga_items_by_his_pid(patient_ids, limit_docs=80)

        async def _fetch_exams():
            docs = []
            for col_name in ("VI_ICU_EXAM", "VI_ICU_EXAM_admitted"):
                cursor = runtime.db.dc_col(col_name).find(his_pid_query).sort("authTime", -1).limit(80)
                docs.extend([doc async for doc in cursor])
            if docs:
                docs = sorted(docs, key=lambda item: lab_time(item) or datetime.min, reverse=True)[:80]
            return docs

        async def _fetch_items():
            cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(1800)
            return [doc async for doc in cursor]

        bga_item_docs, exam_docs, item_docs = await asyncio.gather(
            _fetch_bga(), _fetch_exams(), _fetch_items(),
            return_exceptions=True,
        )
        bga_item_docs = bga_item_docs if not isinstance(bga_item_docs, Exception) else []
        exam_docs = exam_docs if not isinstance(exam_docs, Exception) else []
        item_docs = item_docs if not isinstance(item_docs, Exception) else []

        if not item_docs:
            exam_docs, item_docs = await fetch_dc_exam_items_by_his_pid(patient_ids, limit_exams=60, limit_items=1800)

        exam_name_by_report: dict[str, str] = {}
        exam_name_by_data: dict[str, str] = {}
        for exam in exam_docs:
            name = exam.get("code") or exam.get("examName") or exam.get("requestName") or exam.get("orderName") or ""
            if isinstance(name, str) and name.isdigit():
                name = ""
            if not name:
                continue
            report_id = str(exam.get("reportID") or "")
            data_id = str(exam.get("dataId") or "")
            if report_id:
                exam_name_by_report[report_id] = str(name)
            if data_id:
                exam_name_by_data[data_id] = str(name)

        grouped: dict[str, dict] = {}
        global_snapshot = extract_acid_base_snapshot(bga_item_docs + item_docs, {})
        acid_fallback = {
            key: {
                "value": value.get("value"),
                "unit": value.get("unit", ""),
                "raw_name": value.get("source_name", key),
                "time": value.get("time"),
            }
            for key, value in (global_snapshot.get("fields") or {}).items()
            if key in SUPPORTIVE_FALLBACK_FIELDS
        }

        for index, doc in enumerate(bga_item_docs):
            request_time = lab_time(doc)
            key = f"bGATemp:{request_time.isoformat() if isinstance(request_time, datetime) else 'na'}:{index}"
            if key not in grouped:
                grouped[key] = {
                    "requestId": key,
                    "examName": doc.get("examName") or "SmartCare 血气(bGATemp)",
                    "requestTime": request_time,
                    "items": [],
                    "_raw_docs": [],
                }
            grouped[key]["items"].append(
                {
                    "itemName": doc.get("itemName"),
                    "itemCnName": doc.get("itemCnName"),
                    "itemCode": doc.get("itemCode"),
                    "result": doc.get("result") or doc.get("resultValue") or doc.get("value"),
                    "unit": doc.get("unit") or doc.get("resultUnit"),
                    "resultFlag": doc.get("resultFlag") or doc.get("sourceTable") or "bGATemp",
                }
            )
            grouped[key]["_raw_docs"].append(doc)

        for doc in item_docs:
            key = lab_group_key(doc)
            report_id = str(doc.get("examID") or doc.get("orderID") or "")
            data_id = str(doc.get("dataId") or "")
            exam_name = exam_name_by_report.get(report_id) or exam_name_by_data.get(data_id) or ""
            if not exam_name:
                exam_name = doc.get("examName") or doc.get("examCode") or doc.get("code") or ""
            if isinstance(exam_name, str) and exam_name.isdigit():
                exam_name = ""
            if not exam_name:
                exam_name = doc.get("itemName") or doc.get("itemCnName") or "检验"

            if key not in grouped:
                grouped[key] = {
                    "requestId": key,
                    "examName": exam_name,
                    "requestTime": lab_time(doc),
                    "items": [],
                    "_raw_docs": [],
                }
            grouped[key]["items"].append(
                {
                    "itemName": doc.get("itemName"),
                    "itemCnName": doc.get("itemCnName"),
                    "itemCode": doc.get("itemCode"),
                    "result": doc.get("result") or doc.get("resultValue") or doc.get("value"),
                    "unit": doc.get("unit") or doc.get("resultUnit"),
                    "resultFlag": doc.get("resultFlag") or doc.get("abnormalFlag") or doc.get("seriousFlag") or doc.get("resultStatus"),
                }
            )
            grouped[key]["_raw_docs"].append(doc)
            if not grouped[key].get("requestTime"):
                grouped[key]["requestTime"] = lab_time(doc)

        exams = sorted(grouped.values(), key=lambda item: item.get("requestTime") or datetime.min, reverse=True)
        for exam in exams:
            snapshot = extract_acid_base_snapshot(exam.get("_raw_docs") or [], acid_fallback)
            interpretation = interpret_acid_base(snapshot) if is_blood_gas_snapshot(snapshot, exam.get("_raw_docs") or [], exam.get("examName")) else None
            if interpretation:
                interpretation["snapshot_time"] = exam.get("requestTime") or interpretation.get("snapshot_time")
                exam["acidBaseInterpretation"] = serialize_doc(interpretation)
            exam.pop("_raw_docs", None)
        exams = [serialize_doc(exam) for exam in exams]

    return {"code": 0, "exams": exams}


@router.get("/api/patients/{patient_id}/vitals/trend")
async def patient_vitals_trend(
    patient_id: str,
    window: str = Query("24h", pattern="^(6h|12h|24h|48h|7d)$"),
):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    hours_map = {"6h": 6, "12h": 12, "24h": 24, "48h": 48, "7d": 168}
    since = datetime.now() - timedelta(hours=hours_map.get(window, 24))

    # 预解析 hisPid，避免 10 次重复查询
    pid_str = str(pid)
    patient_doc = await runtime.db.col("patient").find_one({"_id": pid}, {"hisPid": 1, "hisPID": 1})
    query_pids = [pid_str]
    his_pid = patient_his_pid(patient_doc)
    if his_pid and his_pid not in query_pids:
        query_pids.append(his_pid)

    code_field_pairs = [
        ("param_HR", "hr"),
        ("param_spo2", "spo2"),
        ("param_resp", "rr"),
        ("param_T", "temp"),
        ("param_nibp_s", "nibp_sys"),
        ("param_nibp_d", "nibp_dia"),
        ("param_nibp_m", "nibp_map"),
        ("param_ibp_s", "ibp_sys"),
        ("param_ibp_d", "ibp_dia"),
        ("param_ibp_m", "ibp_map"),
    ]

    points_map: dict[str, dict] = {}
    series_results = await asyncio.gather(
        *(param_series_by_pids(query_pids, code, since) for code, _field in code_field_pairs),
        return_exceptions=True,
    )
    for (_code, field), series in zip(code_field_pairs, series_results):
        if isinstance(series, Exception):
            logger.warning("vitals trend series query failed patient_id=%s field=%s error=%s", patient_id, field, series)
            continue
        for item in series:
            point_time = item.get("time")
            if not point_time:
                continue
            key = point_time.isoformat() if isinstance(point_time, datetime) else str(point_time)
            if key not in points_map:
                points_map[key] = {"time": point_time}
            points_map[key][field] = item.get("value")

    points = sorted(points_map.values(), key=lambda item: item.get("time") or datetime.min)
    for point in points:
        point["time"] = serialize_doc(point["time"]) if isinstance(point.get("time"), datetime) else (str(point["time"]) if point.get("time") else None)
    return {"code": 0, "points": points}


@router.get("/api/patients/{patient_id}/vitals/forecast")
async def patient_vitals_forecast(
    patient_id: str,
    codes: str = Query(""),
    horizon_hours: int = Query(6, ge=1, le=12),
    hours: int | None = Query(default=None, ge=1, le=240),
):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    requested = [part.strip() for part in str(codes or "").split(",") if part.strip() in SUPPORTED_CODES] if str(codes or "").strip() else None
    service = get_vital_trajectory_forecaster(db=runtime.db, config=runtime.config, alert_engine=runtime.alert_engine)
    try:
        result = await asyncio.wait_for(service.forecast(str(pid), requested, horizon_hours, history_hours=hours), timeout=7.5)
    except asyncio.TimeoutError:
        logger.warning("vitals forecast timeout patient_id=%s codes=%s horizon=%s", patient_id, codes, horizon_hours)
        return {
            "available": False,
            "reason": "forecast_timeout",
            "source": "",
            "fallback_reason": "forecast_timeout",
            "horizon_hours": horizon_hours,
            "codes": requested or [],
            "series": {},
            "threshold_risks": [],
            "generated_at": serialize_doc(datetime.now()),
            "model_meta": {"available": False, "reason": "forecast_timeout", "backend": "timeout"},
        }
    return serialize_doc(result)


@router.get("/api/patients/{patient_id}/narrative")
async def patient_narrative(patient_id: str, days: int = Query(default=7, ge=1, le=30)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    try:
        service = PatientNarrativeService(db=runtime.db, config=get_config(), alert_engine=runtime.alert_engine)
        narratives = await service.list_recent(str(pid), days=days)
        latest_context_text = await service.latest_context_text(str(pid), days=days)
        return {"code": 0, "patient_id": str(pid), "days": days, "narratives": serialize_doc(narratives), "latest_context_text": latest_context_text}
    except Exception as exc:
        logger.error("Patient narrative query error: %s", exc)
        return {"code": 0, "patient_id": str(pid), "days": days, "narratives": [], "latest_context_text": "", "error": str(exc)[:160]}


@router.post("/api/patients/{patient_id}/narrative/generate")
async def generate_patient_narrative(patient_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    try:
        service = PatientNarrativeService(db=runtime.db, config=get_config(), alert_engine=runtime.alert_engine)
        record = await service.generate_daily(str(pid), patient, narrative_date=(payload or {}).get("narrative_date"), refresh=True)
        return {"code": 0, "patient_id": str(pid), "narrative": serialize_doc(record)}
    except Exception as exc:
        logger.error("Patient narrative generate error: %s", exc)
        return {"code": 0, "patient_id": str(pid), "narrative": None, "error": str(exc)[:160]}


@router.get("/api/patients/{patient_id}/drugs")
async def patient_drugs(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    # 并行获取药物记录和映射表
    cursor_task = runtime.db.col("drugExe").find(
        {"pid": str(pid)},
        {
            "drugName": 1,
            "orderName": 1,
            "dose": 1,
            "doseUnit": 1,
            "route": 1,
            "frequency": 1,
            "executeTime": 1,
            "status": 1,
            "orderType": 1,
            "drugSpec": 1,
            "startTime": 1,
            "orderTime": 1,
        },
    ).sort("executeTime", -1).limit(50).to_list(50)

    route_dc_task = load_dc_doc_map("VI_ICU_YWYF", "code", ["name", "desc"])
    freq_dc_task = load_dc_doc_map("VI_ICU_YYPC", "code", ["freqName", "desc"])
    route_sc_task = load_sc_doc_map("configDrugMethod", "code", ["name"])
    freq_sc_task = load_sc_doc_map("configOrderFreq", "freqCode", ["freqName", "perDay", "freqFixHourMinList"])

    drug_rows, route_map_dc, freq_map_dc, route_map_sc, freq_map_sc = await asyncio.gather(
        cursor_task, route_dc_task, freq_dc_task, route_sc_task, freq_sc_task,
        return_exceptions=True,
    )
    drug_rows = drug_rows if not isinstance(drug_rows, Exception) else []
    route_map_dc = route_map_dc if not isinstance(route_map_dc, Exception) else {}
    freq_map_dc = freq_map_dc if not isinstance(freq_map_dc, Exception) else {}
    route_map_sc = route_map_sc if not isinstance(route_map_sc, Exception) else {}
    freq_map_sc = freq_map_sc if not isinstance(freq_map_sc, Exception) else {}

    cursor = _AsyncListCursor(drug_rows)

    def map_route(code):
        if code is None or code == "":
            return code
        item = route_map_dc.get(str(code)) or route_map_sc.get(str(code))
        if not item:
            return code
        return item.get("name") or item.get("desc") or code

    def map_freq(code):
        if code is None or code == "":
            return code
        item = freq_map_dc.get(str(code)) or freq_map_sc.get(str(code))
        if not item:
            return code
        name = item.get("freqName") or item.get("name")
        return beautify_freq(name, item.get("desc"), item.get("freqFixHourMinList"), item.get("perDay")) or name or code

    def has_real_name(value) -> bool:
        if value is None:
            return False
        text = str(value).strip()
        if not text:
            return False
        return re.fullmatch(r"\d+(\.\d+)?", text) is None

    records = []
    has_name = False
    async for doc in cursor:
        if not has_real_name(doc.get("drugName")):
            doc["drugName"] = doc.get("orderName") or doc.get("drugSpec")
        if not doc.get("executeTime"):
            doc["executeTime"] = doc.get("startTime") or doc.get("orderTime")
        if has_real_name(doc.get("drugName")):
            has_name = True
        if doc.get("route"):
            doc["route"] = map_route(doc.get("route"))
        if doc.get("frequency"):
            doc["frequency"] = map_freq(doc.get("frequency"))
        records.append(serialize_doc(doc))

    if records and has_name:
        return {"code": 0, "records": records}

    records = []
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"hisPid": 1})
    his_pid = patient.get("hisPid") if patient else None
    if not his_pid:
        return {"code": 0, "records": []}

    exec_cursor = runtime.db.dc_col("VI_ICU_HSZ_YYZXJL").find({"pid": his_pid}).sort("exeTime", -1).limit(100)
    execs = [doc async for doc in exec_cursor]
    if execs:
        order_ids = [doc.get("orderID") for doc in execs if doc.get("orderID")]
        orders = {}
        if order_ids:
            cursor2 = runtime.db.dc_col("VI_ICU_ZYYZ").find({"orderID": {"$in": order_ids}})
            async for order in cursor2:
                if order.get("orderID"):
                    orders[str(order.get("orderID"))] = order

        for item in execs:
            order = orders.get(str(item.get("orderID") or ""), {})
            records.append(
                {
                    "drugName": order.get("orderName") or item.get("drugName") or item.get("itemName") or item.get("note"),
                    "dose": order.get("spec"),
                    "doseUnit": "",
                    "route": map_route(order.get("exeMethod")),
                    "frequency": map_freq(order.get("freq")),
                    "executeTime": item.get("exeTime") or item.get("planTime") or item.get("checkTime"),
                    "status": item.get("status"),
                    "orderType": order.get("orderType"),
                    "drugSpec": order.get("spec"),
                }
            )
        return {"code": 0, "records": [serialize_doc(row) for row in records]}

    order_cursor = runtime.db.dc_col("VI_ICU_ZYYZ").find({"pid": his_pid}).sort("orderTime", -1).limit(50)
    async for order in order_cursor:
        records.append(
            {
                "drugName": order.get("orderName"),
                "dose": order.get("spec"),
                "doseUnit": "",
                "route": map_route(order.get("exeMethod")),
                "frequency": map_freq(order.get("freq")),
                "executeTime": order.get("orderTime"),
                "status": "",
                "orderType": order.get("orderType"),
                "drugSpec": order.get("spec"),
            }
        )

    return {"code": 0, "records": [serialize_doc(row) for row in records]}


@router.get("/api/patients/{patient_id}/assessments")
async def patient_assessments(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    pid_str = str(pid)
    records: list[dict] = []

    cursor = runtime.db.col("score").find({"patient_id": {"$in": [pid, pid_str]}}).sort("calc_time", -1).limit(50)
    async for doc in cursor:
        item = {
            "time": doc.get("calc_time") or doc.get("time") or doc.get("recordTime") or doc.get("created_at"),
            "gcs": doc.get("gcs") or doc.get("gcsScore"),
            "rass": doc.get("rass"),
            "pain": doc.get("pain") or doc.get("painScore") or doc.get("cpotScore"),
            "delirium": doc.get("delirium") or doc.get("deliriumScore"),
            "braden": doc.get("braden") or doc.get("bradenScore"),
        }
        metrics = (item.get("gcs"), item.get("rass"), item.get("pain"), item.get("delirium"), item.get("braden"))
        if any(value is not None for value in metrics):
            records.append(serialize_doc(item))

    score_types = {
        "gcsScore": "gcs",
        "rass": "rass",
        "painScore": "pain",
        "cpotScore": "pain",
        "cpotScoreV2": "pain",
        "deliriumScore": "delirium",
        "bradenScore": "braden",
        "bradenNurseScore": "braden",
    }
    cursor2 = runtime.db.col("score").find(
        {
            "pid": {"$in": [pid_str, pid]},
            "scoreType": {"$in": list(score_types.keys())},
            "$or": [{"valid": {"$exists": False}}, {"valid": True}],
        }
    ).sort("time", -1).limit(300)
    async for doc in cursor2:
        kind = score_types.get(doc.get("scoreType"))
        if not kind:
            continue
        value = extract_assessment_from_score_doc(doc, kind)
        if value is not None:
            records.append(serialize_doc({"time": doc.get("time"), kind: value}))

    code_map = {
        "gcs": ["param_score_gcs_obs"],
        "rass": ["param_score_rass_obs", "param_score_rass_obs_Q4H"],
        "pain": [
            "param_tengTong_score",
            "param_tengTong_score_Q4H",
            "param_zhenTong_NRS_score",
            "param_analgesia_nrs_score",
            "param_analgesia_cpot_score",
            "param_score_bps",
        ],
        "delirium": ["param_delirium_score"],
        "braden": ["param_score_braden", "param_score_braden_Q24H"],
    }
    # 合并所有 codes 为一次查询
    all_codes = [code for codes in code_map.values() for code in codes]
    code_to_kind: dict[str, str] = {}
    for kind, codes in code_map.items():
        for code in codes:
            code_to_kind[code] = kind
    cursor3 = runtime.db.col("bedside").find(
        {
            "pid": pid_str,
            "code": {"$in": all_codes},
            "$or": [{"valid": {"$exists": False}}, {"valid": True}],
        },
        {"time": 1, "code": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1},
    ).sort("time", -1).limit(500)
    async for doc in cursor3:
        kind = code_to_kind.get(doc.get("code"))
        if kind:
            value = extract_assessment_from_bedside_doc(kind, doc)
            if value is not None:
                records.append(serialize_doc({"time": doc.get("time"), kind: value}))

    return {"code": 0, "records": merge_assessment_records(records)[:400]}


@router.get("/api/patients/{patient_id}/alerts")
async def patient_alerts(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    cursor = runtime.db.col("alert_records").find(
        {"patient_id": {"$in": [patient_id, str(pid), pid]}},
        {
            "_id": 1,
            "patient_id": 1,
            "rule_id": 1,
            "name": 1,
            "category": 1,
            "alert_type": 1,
            "severity": 1,
            "parameter": 1,
            "condition": 1,
            "value": 1,
            "extra": 1,
            "created_at": 1,
            "viewed_at": 1,
            "view_source": 1,
            "view_actor": 1,
            "acknowledged_at": 1,
            "ack_actor": 1,
            "ack_note": 1,
            "actionability_score": 1,
            "actionability_level": 1,
            "actionability_factors": 1,
            "action_taken": 1,
            "outcome_delta": 1,
            "lifecycle_updated_at": 1,
            "ai_feedback": 1,
            "is_active": 1,
        },
    ).sort("created_at", -1).limit(100)
    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))
    return {"code": 0, "records": records}


@router.post("/api/patients/{patient_id}/alerts/view")
async def patient_alerts_viewed(patient_id: str, request: Request, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    raw_ids = payload.get("alert_ids") if isinstance(payload.get("alert_ids"), list) else []
    alert_ids = [str(item) for item in raw_ids if str(item or "").strip()]
    if not alert_ids:
        cursor = runtime.db.col("alert_records").find({"patient_id": {"$in": [patient_id, str(pid), pid]}}, {"_id": 1}).sort("created_at", -1).limit(50)
        alert_ids = [str(doc.get("_id")) async for doc in cursor if doc.get("_id") is not None]
    modified = await runtime.alert_engine.mark_alerts_viewed(
        alert_ids,
        actor=resolve_actor_identity(payload, request),
        source=str((payload or {}).get("source") or "patient_detail").strip() or "patient_detail",
    )
    return {"code": 0, "modified": modified}


@router.get("/api/patients/{patient_id}/bedcard")
async def patient_bedcard(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    cache_key = str(pid)
    cached = _bedcard_cache.get(cache_key)
    if cached and (datetime.now() - cached[0]).total_seconds() < _BEDCARD_CACHE_TTL_SECONDS:
        return {"code": 0, "data": serialize_doc(cached[1])}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "未找到患者"}

    pid_str = str(pid)
    identity = {
        "name": patient.get("name", ""),
        "gender": patient.get("gender", ""),
        "age": patient.get("age") or calculate_age(patient.get("birthday")),
        "bed": patient.get("hisBed") or patient.get("bed", ""),
        "allergies": patient.get("allergies") or patient.get("allergyHistory", ""),
        "diagnosis": patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis", ""),
        "isolation": "保护性隔离" if "特级" in str(patient.get("nursingLevel", "")) else "",
    }

    async def load_devices() -> list[dict]:
        active_devices = []
        device_binds = runtime.db.col("deviceBind").find({"pid": pid_str, "unBindTime": None}, {"deviceID": 1, "type": 1, "bindTime": 1}).sort("bindTime", -1).limit(6)
        binds = [bind async for bind in device_binds]
        ids = [bind.get("deviceID") for bind in binds if bind.get("deviceID")]
        info_by_id = {}
        if ids:
            info_cursor = runtime.db.col("deviceInfo").find({"_id": {"$in": [safe_oid(item) or item for item in ids]}}, {"deviceName": 1})
            info_by_id = {str(info.get("_id")): info async for info in info_cursor}
        for bind in binds:
            device_id = bind.get("deviceID")
            info = info_by_id.get(str(device_id)) if device_id else None
            device_name = info.get("deviceName", "") if info else bind.get("type", "")
            active_devices.append({"name": device_name, "type": infer_device_type(device_name) or bind.get("type", "unknown"), "bindTime": bind.get("bindTime")})
        return active_devices

    async def load_tubes() -> list[dict]:
        active_tubes = []
        now = datetime.now()
        tubes_cursor = runtime.db.col("tubeExe").find(
            {
                "pid": pid_str,
                "$and": [
                    {"$or": [{"stopTime": None}, {"stopTime": {"$exists": False}}]},
                    {"$or": [{"endTime": None}, {"endTime": {"$exists": False}}]},
                    {"$or": [{"removeTime": None}, {"removeTime": {"$exists": False}}]},
                ],
            },
            {"name": 1, "type": 1, "body": 1, "startTime": 1},
        ).sort("startTime", 1).limit(24)
        async for tube in tubes_cursor:
            start_time = tube.get("startTime")
            dwell_days = 0
            if start_time:
                try:
                    if isinstance(start_time, datetime):
                        parsed = start_time
                    else:
                        value = str(start_time).replace("Z", "+00:00")
                        parsed = datetime.fromisoformat(value) if "." in value or "+" in value else datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
                    dwell_days = max(0, (now - parsed).days)
                except Exception as exc:
                    logger.warning("Failed to parse tube startTime %s: %s", start_time, exc)
            tube_name = str(tube.get("name") or tube.get("type") or "").lower()
            category = "other"
            if any(key in tube_name for key in ["气管", "插管", "气切", "ett", "tracheo"]):
                category = "airway"
            elif any(key in tube_name for key in ["cvc", "picc", "动脉", "静脉", "导管", "穿刺", "swan", "留置针"]):
                category = "vascular"
            elif any(key in tube_name for key in ["引流", "胸管", "胃管", "t管", "造瘘", "鼻肠"]):
                category = "drain"
            elif any(key in tube_name for key in ["导尿", "尿管", "foley"]):
                category = "urinary"
            active_tubes.append({"name": tube.get("name") or tube.get("type") or "未知管路", "category": category, "site": tube.get("body") or "", "dwellDays": dwell_days, "startTime": start_time})
        return active_tubes

    def _overview_vitals(vitals: dict | None) -> dict:
        if not isinstance(vitals, dict) or not vitals:
            return {}
        return {
            "hr": vitals.get("hr"),
            "rr": vitals.get("rr"),
            "sbp": vitals.get("sbp") or vitals.get("ibp_sys") or vitals.get("nibp_sys"),
            "dbp": vitals.get("dbp") or vitals.get("ibp_dia") or vitals.get("nibp_dia"),
            "map": vitals.get("map") or vitals.get("ibp_map") or vitals.get("nibp_map"),
            "spo2": vitals.get("spo2"),
            "t": vitals.get("temp") or vitals.get("t"),
            "temp": vitals.get("temp") or vitals.get("t"),
            "time": vitals.get("time"),
            "source": vitals.get("source"),
        }

    async def load_latest_vitals() -> dict:
        query_pids = [pid_str]
        his_pid = patient_his_pid(patient)
        if his_pid:
            query_pids.append(his_pid)
        code_map = _vital_codes()
        codes = [
            *code_map["hr"],
            *code_map["spo2"],
            *code_map["rr"],
            *code_map["temp"],
            *code_map["sbp"],
            *code_map["dbp"],
            *code_map["map"],
            "param_cvp",
            "param_ETCO2",
        ]
        snapshot = await latest_params_by_pid(query_pids, codes)
        source = "bedside"
        if not snapshot:
            device_id = await get_device_id(pid_str, "monitor", patient_doc=patient)
            if not device_id:
                device_id = await get_device_id(pid_str, None, patient_doc=patient)
            if device_id:
                snapshot = await latest_params_by_device(device_id, codes)
                source = "device"
        vitals = _snapshot_to_vitals(snapshot, source) if snapshot else {}
        bedside_snapshot = await _latest_bedside_vitals(pid_str, codes)
        if bedside_snapshot:
            bedside_vitals = _snapshot_to_vitals(bedside_snapshot, "bedside")
            for key, value in bedside_vitals.items():
                if vitals.get(key) in (None, "") and value not in (None, ""):
                    vitals[key] = value
        fallback_vitals = await _fallback_vitals_from_alert_snapshot(pid_str)
        if fallback_vitals:
            for key, value in fallback_vitals.items():
                if vitals.get(key) in (None, "") and value not in (None, ""):
                    vitals[key] = value
        return _overview_vitals(vitals)

    async def load_metrics() -> dict:
        metrics = {"sofa": None, "netFluid24h": None, "glucose": None, "vitals": {}}
        sofa_doc, fluid_alert, latest_vitals = await asyncio.gather(
            _optional(runtime.db.col("score").find_one({"patient_id": pid_str, "score_type": "sofa"}, {"score": 1}, sort=[("calc_time", -1)]), None, timeout=0.04),
            _optional(runtime.db.col("alert_records").find_one({"patient_id": pid_str, "alert_type": "fluid_balance"}, {"extra.windows.24h.net_ml": 1}, sort=[("created_at", -1)]), None, timeout=0.04),
            _optional(load_latest_vitals(), {}, timeout=0.35),
        )
        if sofa_doc:
            metrics["sofa"] = sofa_doc.get("score")
        if fluid_alert and fluid_alert.get("extra"):
            metrics["netFluid24h"] = ((fluid_alert["extra"].get("windows") or {}).get("24h") or {}).get("net_ml")
        if latest_vitals:
            metrics["vitals"] = latest_vitals
        return metrics

    def build_alert_card(alert: dict) -> tuple[str, dict]:
        name = alert.get("name") or alert.get("rule_id", "高危预警")
        explanation = alert.get("explanation")
        explanation_summary = ""
        explanation_suggestion = ""
        explanation_evidence = []
        if isinstance(explanation, dict):
            explanation_summary = str(explanation.get("summary") or explanation.get("text") or "").strip()
            explanation_suggestion = str(explanation.get("suggestion") or "").strip()
            raw_evidence = explanation.get("evidence") or []
            if isinstance(raw_evidence, list):
                explanation_evidence = [str(item).strip() for item in raw_evidence if str(item).strip()]
        elif isinstance(explanation, str):
            explanation_summary = explanation.strip()
        if not explanation_summary:
            explanation_summary = str(alert.get("explanation_text") or "").strip()

        extra = alert.get("extra") if isinstance(alert.get("extra"), dict) else {}
        post_extubation_snapshot = None
        if str(alert.get("alert_type") or "") == "post_extubation_failure_risk":
            post_extubation_snapshot = {
                "rr": extra.get("rr"),
                "spo2": extra.get("spo2"),
                "hours_since_extubation": extra.get("hours_since_extubation"),
                "accessory_muscle_use": extra.get("accessory_muscle_use"),
            }
        return name, {
            "title": name,
            "severity": alert.get("severity") or "high",
            "summary": explanation_summary,
            "suggestion": explanation_suggestion,
            "evidence": explanation_evidence[:3],
            "clinical_chain": extra.get("clinical_chain") if isinstance(extra.get("clinical_chain"), dict) else None,
            "aggregated_groups": extra.get("aggregated_groups")[:3] if isinstance(extra.get("aggregated_groups"), list) else [],
            "context_snapshot": extra.get("context_snapshot") if isinstance(extra.get("context_snapshot"), dict) else None,
            "alert_type": alert.get("alert_type") or "",
            "category": alert.get("category") or "",
            "rule_id": alert.get("rule_id") or "",
            "created_at": alert.get("created_at"),
            "post_extubation_snapshot": post_extubation_snapshot,
        }

    async def load_alerts() -> tuple[list[str], list[dict], dict | None]:
        since_24h = datetime.now() - timedelta(hours=24)
        cursor = runtime.db.col("alert_records").find(
            {"patient_id": pid_str, "is_active": True, "severity": {"$in": ["high", "critical"]}, "created_at": {"$gte": since_24h}},
            {"name": 1, "rule_id": 1, "severity": 1, "explanation": 1, "explanation_text": 1, "extra": 1, "alert_type": 1, "category": 1, "created_at": 1},
        ).sort("created_at", -1).limit(5)
        rows = [row async for row in cursor]
        notes = []
        alert_notes = []
        seen_note_keys = set()
        for alert in rows:
            name, card = build_alert_card(alert)
            notes.append(name)
            key = (card.get("title") or "", card.get("summary") or "", card.get("severity") or "")
            if key not in seen_note_keys:
                seen_note_keys.add(key)
                alert_notes.append({**card, "evidence": (card.get("evidence") or [])[:2]})
        return list(dict.fromkeys(notes)), alert_notes, alert_notes[0] if alert_notes else None

    active_devices, active_tubes, metrics, alert_payload = await asyncio.gather(
        _optional(load_devices(), [], timeout=0.08),
        _optional(load_tubes(), [], timeout=0.08),
        _optional(load_metrics(), {"sofa": None, "netFluid24h": None, "glucose": None, "vitals": {}}, timeout=0.5),
        _optional(load_alerts(), ([], [], None), timeout=0.08),
    )
    notes, dedup_alert_notes, alert_summary_card = alert_payload
    payload = {
        "identity": identity,
        "devices": active_devices,
        "tubes": active_tubes,
        "metrics": metrics,
        "notes": notes,
        "alert_notes": dedup_alert_notes,
        "alert_summary_card": alert_summary_card,
    }
    _bedcard_cache[cache_key] = (datetime.now(), payload)
    if len(_bedcard_cache) > 1024:
        for key, (created_at, _) in list(_bedcard_cache.items())[:128]:
            if (datetime.now() - created_at).total_seconds() >= _BEDCARD_CACHE_TTL_SECONDS:
                _bedcard_cache.pop(key, None)

    return {
        "code": 0,
        "data": serialize_doc(payload),
    }
