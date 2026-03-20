from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, Query

from app import runtime
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
)
from app.utils.patient_helpers import calculate_age, patient_his_pid, patient_his_pid_candidates
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


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

    hr_codes = []
    for code in [
        _single("heart_rate", "param_HR"),
        _single("pulse_rate", "param_PR"),
    ]:
        if code not in hr_codes:
            hr_codes.append(code)

    return {
        "hr": hr_codes,
        "spo2": [_single("spo2", "param_spo2")],
        "rr": [_single("resp_rate", "param_resp")],
        "temp": [_single("temperature", "param_T")],
        "sbp": _multi("sbp_priority", ["param_ibp_s", "param_nibp_s"]),
        "dbp": _multi("dbp_priority", ["param_ibp_d", "param_nibp_d"]),
        "map": _multi("map_priority", ["param_ibp_m", "param_nibp_m"]),
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
        "nibp_sys": _pick_param(params, codes["sbp"]),
        "nibp_dia": _pick_param(params, codes["dbp"]),
        "nibp_map": _pick_param(params, codes["map"]),
        "ibp_sys": params.get("param_ibp_s"),
        "ibp_dia": params.get("param_ibp_d"),
        "ibp_map": params.get("param_ibp_m"),
        "cvp": params.get("param_cvp"),
        "etco2": params.get("param_ETCO2"),
    }


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

    vitals: dict = {}
    pid_str = str(pid)
    query_pids = [pid_str]
    patient = await runtime.db.col("patient").find_one(
        {"_id": pid},
        {"hisPid": 1, "hisPID": 1, "hisBed": 1, "bed": 1, "deptCode": 1},
    )
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
    source = None
    if snapshot:
        source = "monitor"
    else:
        device_id = await get_device_id(pid_str, "monitor", patient_doc=patient)
        if not device_id:
            device_id = await get_device_id(pid_str, None, patient_doc=patient)
        if device_id:
            snapshot = await latest_params_by_device(device_id, codes)
            if snapshot:
                source = "device"

    if snapshot:
        vitals = _snapshot_to_vitals(snapshot, source)
    fallback_vitals = await _fallback_vitals_from_alert_snapshot(pid_str)
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
        bga_item_docs = await fetch_smartcare_bga_items_by_his_pid(patient_ids, limit_docs=80)
        his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}

        exam_docs = []
        for col_name in ("VI_ICU_EXAM", "VI_ICU_EXAM_admitted"):
            cursor = runtime.db.dc_col(col_name).find(his_pid_query).sort("authTime", -1).limit(80)
            exam_docs.extend([doc async for doc in cursor])
        if exam_docs:
            exam_docs = sorted(exam_docs, key=lambda item: lab_time(item) or datetime.min, reverse=True)[:80]

        cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(1800)
        item_docs = [doc async for doc in cursor]
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
    for code, field in code_field_pairs:
        series = await param_series_by_pid(str(pid), code, since)
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


@router.get("/api/patients/{patient_id}/drugs")
async def patient_drugs(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    cursor = runtime.db.col("drugExe").find(
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
    ).sort("executeTime", -1).limit(50)

    route_map_dc = await load_dc_doc_map("VI_ICU_YWYF", "code", ["name", "desc"])
    freq_map_dc = await load_dc_doc_map("VI_ICU_YYPC", "code", ["freqName", "desc"])
    route_map_sc = await load_sc_doc_map("configDrugMethod", "code", ["name"])
    freq_map_sc = await load_sc_doc_map("configOrderFreq", "freqCode", ["freqName", "perDay", "freqFixHourMinList"])

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

    cursor = runtime.db.col("score_records").find({"patient_id": {"$in": [pid, pid_str]}}).sort("calc_time", -1).limit(50)
    async for doc in cursor:
        item = {
            "time": doc.get("calc_time") or doc.get("time") or doc.get("recordTime") or doc.get("created_at"),
            "gcs": doc.get("gcs") or doc.get("gcsScore"),
            "rass": doc.get("rass"),
            "pain": doc.get("pain") or doc.get("painScore") or doc.get("cpotScore"),
            "delirium": doc.get("delirium") or doc.get("deliriumScore"),
            "braden": doc.get("braden") or doc.get("bradenScore"),
        }
        if any(value is not None for value in item.values()):
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
    for kind, codes in code_map.items():
        cursor3 = runtime.db.col("bedside").find(
            {
                "pid": pid_str,
                "code": {"$in": codes},
                "$or": [{"valid": {"$exists": False}}, {"valid": True}],
            },
            {"time": 1, "code": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1},
        ).sort("time", -1).limit(160)
        async for doc in cursor3:
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

    cursor = runtime.db.col("alert_records").find({"patient_id": {"$in": [patient_id, pid]}}).sort("created_at", -1).limit(100)
    return {"code": 0, "records": [serialize_doc(doc) async for doc in cursor]}


@router.get("/api/patients/{patient_id}/bedcard")
async def patient_bedcard(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

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

    active_devices = []
    device_binds = runtime.db.col("deviceBind").find({"pid": pid_str, "unBindTime": None})
    async for bind in device_binds:
        device_id = bind.get("deviceID")
        if not device_id:
            continue
        info = await runtime.db.col("deviceInfo").find_one({"_id": safe_oid(device_id) or device_id})
        device_name = info.get("deviceName", "") if info else bind.get("type", "")
        device_type = infer_device_type(device_name) or bind.get("type", "unknown")
        device_row = {"name": device_name, "type": device_type, "bindTime": bind.get("bindTime")}
        caps = await latest_params_by_device(device_id, ["param_vent_mode", "param_fio2", "param_peep", "param_crrt_mode"])
        if caps and caps.get("params"):
            params = caps["params"]
            if device_type == "vent":
                details = []
                if params.get("param_vent_mode"):
                    details.append(str(params.get("param_vent_mode")))
                if params.get("param_fio2"):
                    details.append(f"FiO2 {params.get('param_fio2')}%")
                if params.get("param_peep"):
                    details.append(f"PEEP {params.get('param_peep')}")
                if details:
                    device_row["details"] = " ".join(details)
            elif device_type == "crrt" and params.get("param_crrt_mode"):
                device_row["details"] = f"模式:{params.get('param_crrt_mode')}"
        active_devices.append(device_row)

    active_tubes = []
    now = datetime.now()
    tubes_cursor = runtime.db.col("tubeExe").find({"pid": pid_str, "stopTime": None}).sort("startTime", 1)
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
        active_tubes.append(
            {
                "name": tube.get("name") or tube.get("type") or "未知管路",
                "category": category,
                "site": tube.get("body") or "",
                "dwellDays": dwell_days,
                "startTime": start_time,
            }
        )

    metrics = {"sofa": None, "netFluid24h": None, "glucose": None, "vitals": {}}
    sofa_doc = await runtime.db.col("score_records").find_one({"patient_id": pid_str, "score_type": "sofa"}, sort=[("calc_time", -1)])
    if sofa_doc:
        metrics["sofa"] = sofa_doc.get("score")

    query_pids = [pid_str]
    his_pid = patient_his_pid(patient)
    if his_pid and his_pid not in query_pids:
        query_pids.append(his_pid)
    code_map = _vital_codes()
    cap_codes = [
        *code_map["hr"],
        *code_map["sbp"],
        *code_map["dbp"],
        *code_map["spo2"],
        *code_map["temp"],
        "param_glu_lab",
        "param_glu_poc",
    ]
    cap_res = await latest_params_by_pid(query_pids, cap_codes, lookback_minutes=10080)
    if not cap_res:
        monitor_device_id = await get_device_id(pid_str, "monitor", patient_doc=patient)
        if not monitor_device_id:
            monitor_device_id = await get_device_id(pid_str, None, patient_doc=patient)
        if monitor_device_id:
            cap_res = await latest_params_by_device(
                monitor_device_id,
                cap_codes,
                lookback_minutes=10080,
            )
    if cap_res and cap_res.get("params"):
        params = cap_res["params"]
        metrics["vitals"] = {
            "hr": _pick_param(params, code_map["hr"]),
            "sbp": _pick_param(params, code_map["sbp"]),
            "dbp": _pick_param(params, code_map["dbp"]),
            "spo2": _pick_param(params, code_map["spo2"]),
            "t": _pick_param(params, code_map["temp"]),
        }
        metrics["glucose"] = params.get("param_glu_lab") or params.get("param_glu_poc")
    fallback_vitals = await _fallback_vitals_from_alert_snapshot(pid_str)
    if fallback_vitals:
        merged_fallback = {
            "hr": fallback_vitals.get("hr"),
            "sbp": fallback_vitals.get("ibp_sys") or fallback_vitals.get("nibp_sys"),
            "dbp": fallback_vitals.get("ibp_dia") or fallback_vitals.get("nibp_dia"),
            "spo2": fallback_vitals.get("spo2"),
            "t": fallback_vitals.get("temp"),
            "map": fallback_vitals.get("ibp_map") or fallback_vitals.get("nibp_map"),
            "time": fallback_vitals.get("time"),
            "source": fallback_vitals.get("source"),
        }
        if not metrics["vitals"]:
            metrics["vitals"] = merged_fallback
        else:
            for key, value in merged_fallback.items():
                if metrics["vitals"].get(key) in (None, "") and value not in (None, ""):
                    metrics["vitals"][key] = value

    fluid_alert = await runtime.db.col("alert_records").find_one({"patient_id": pid_str, "alert_type": "fluid_balance"}, sort=[("created_at", -1)])
    if fluid_alert and fluid_alert.get("extra"):
        metrics["netFluid24h"] = ((fluid_alert["extra"].get("windows") or {}).get("24h") or {}).get("net_ml")

    notes = []
    alert_notes = []
    alert_summary_card = None
    since_24h = datetime.now() - timedelta(hours=24)
    alert_cursor = runtime.db.col("alert_records").find(
        {"patient_id": pid_str, "is_active": True, "severity": {"$in": ["high", "critical"]}, "created_at": {"$gte": since_24h}}
    ).sort("created_at", -1).limit(5)
    async for alert in alert_cursor:
        name = alert.get("name") or alert.get("rule_id", "高危预警")
        notes.append(name)
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
        if alert_summary_card is None:
            alert_summary_card = {
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
        alert_notes.append(
            {
                "title": name,
                "severity": alert.get("severity") or "high",
                "summary": explanation_summary,
                "suggestion": explanation_suggestion,
                "evidence": explanation_evidence[:2],
                "context_snapshot": extra.get("context_snapshot") if isinstance(extra.get("context_snapshot"), dict) else None,
                "alert_type": alert.get("alert_type") or "",
                "category": alert.get("category") or "",
                "rule_id": alert.get("rule_id") or "",
                "created_at": alert.get("created_at"),
                "post_extubation_snapshot": post_extubation_snapshot,
            }
        )

    dedup_alert_notes = []
    seen_note_keys = set()
    for item in alert_notes:
        key = (item.get("title") or "", item.get("summary") or "", item.get("severity") or "")
        if key in seen_note_keys:
            continue
        seen_note_keys.add(key)
        dedup_alert_notes.append(item)

    return {
        "code": 0,
        "data": serialize_doc(
            {
                "identity": identity,
                "devices": active_devices,
                "tubes": active_tubes,
                "metrics": metrics,
                "notes": list(dict.fromkeys(notes)),
                "alert_notes": dedup_alert_notes,
                "alert_summary_card": alert_summary_card,
            }
        ),
    }
