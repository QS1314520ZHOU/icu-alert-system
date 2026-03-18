from __future__ import annotations

import re
from datetime import datetime, timedelta

from app import runtime
from app.alert_engine.acid_base_analyzer import extract_bga_temp_items
from app.utils.patient_helpers import bed_match, normalize_bed, patient_his_pid
from app.utils.serialization import safe_oid


def cap_time(doc: dict) -> datetime | None:
    if not doc:
        return None
    return doc.get("time") or doc.get("recordTime")


def cap_value(doc: dict) -> float | None:
    if not doc:
        return None
    for key in ("fVal", "intVal", "strVal", "value"):
        value = doc.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def lab_time(doc: dict) -> datetime | None:
    return (
        doc.get("authTime")
        or doc.get("collectTime")
        or doc.get("requestTime")
        or doc.get("reportTime")
        or doc.get("resultTime")
        or doc.get("time")
    )


def lab_group_key(doc: dict) -> str:
    return (
        str(doc.get("examID") or "")
        or str(doc.get("orderID") or "")
        or str(doc.get("dataId") or "")
        or str(doc.get("reportID") or "")
        or str(doc.get("_id") or "")
    )


async def fetch_dc_exam_items_by_his_pid(
    his_pid: str | list[str],
    limit_exams: int = 50,
    limit_items: int = 3000,
) -> tuple[list[dict], list[dict]]:
    if isinstance(his_pid, list):
        his_pids = [str(value).strip() for value in his_pid if str(value).strip()]
    else:
        value = str(his_pid).strip() if his_pid is not None else ""
        his_pids = [value] if value else []
    if not his_pids:
        return [], []
    his_pid_query = {"hisPid": his_pids[0]} if len(his_pids) == 1 else {"hisPid": {"$in": his_pids}}

    exam_docs = []
    for col_name in ("VI_ICU_EXAM", "VI_ICU_EXAM_admitted"):
        cursor = runtime.db.dc_col(col_name).find(his_pid_query).sort("authTime", -1).limit(limit_exams)
        exam_docs.extend([doc async for doc in cursor])
    exam_docs = sorted(exam_docs, key=lambda item: lab_time(item) or datetime.min, reverse=True)[:limit_exams]

    report_ids = [doc.get("reportID") for doc in exam_docs if doc.get("reportID")]
    data_ids = [doc.get("dataId") for doc in exam_docs if doc.get("dataId")]
    item_query = {"$or": []}
    if report_ids:
        item_query["$or"].append({"examID": {"$in": report_ids}})
        item_query["$or"].append({"orderID": {"$in": report_ids}})
    if data_ids:
        item_query["$or"].append({"dataId": {"$in": data_ids}})
    item_query["$or"].append(his_pid_query)

    cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(item_query).sort("authTime", -1).limit(limit_items)
    item_docs = [doc async for doc in cursor]
    return exam_docs, item_docs


async def fetch_smartcare_bga_items_by_his_pid(his_pid: str | list[str], limit_docs: int = 80) -> list[dict]:
    if isinstance(his_pid, list):
        pid_values = [str(value).strip() for value in his_pid if str(value).strip()]
    else:
        pid_values = [str(his_pid).strip()] if str(his_pid).strip() else []
    if not pid_values:
        return []

    or_list = []
    for field in ("eventExe.pid", "hisPid", "his_pid", "pid", "patientId", "patient_id"):
        for value in pid_values:
            or_list.append({field: value})
            oid = safe_oid(value)
            if oid is not None:
                or_list.append({field: oid})
    cursor = runtime.db.col("bGATemp").find({"$or": or_list}).sort("inputTime", -1).limit(max(int(limit_docs or 80), 20))
    docs = [doc async for doc in cursor]

    items: list[dict] = []
    for doc in docs:
        items.extend(extract_bga_temp_items(doc))
    items.sort(key=lambda item: lab_time(item) or datetime.min, reverse=True)
    return items


def assess_time_key(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def merge_assessment_records(records: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in records:
        time_key = assess_time_key(row.get("time"))
        if not time_key:
            continue
        if time_key not in merged:
            merged[time_key] = {"time": row.get("time")}
        for key, value in row.items():
            if key != "time" and value is not None:
                merged[time_key][key] = value
    return sorted(merged.values(), key=lambda item: item.get("time") or datetime.min, reverse=True)


def _parse_number_text(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _parse_gcs_text(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    score_match = re.search(r"(?:总分|gcs)?\s*[:：]?\s*(\d{1,2})", text, re.I)
    if score_match:
        try:
            score = int(score_match.group(1))
            if 3 <= score <= 15:
                return score
        except Exception:
            pass
    numbers = [int(n) for n in re.findall(r"\d{1,2}", text)]
    if len(numbers) >= 3:
        total = sum(numbers[:3])
        if 3 <= total <= 15:
            return total
    return None


def extract_assessment_from_score_doc(doc: dict, kind: str):
    if kind == "gcs":
        score = doc.get("score")
        if isinstance(score, dict):
            total = score.get("totalScore")
            if total is not None:
                parsed = _parse_number_text(total)
                return int(parsed) if parsed is not None else None
        return _parse_gcs_text(doc.get("scoreDesc") or doc.get("score") or doc.get("value"))
    if kind in {"rass", "pain", "delirium", "braden"}:
        score = doc.get("score")
        if isinstance(score, dict):
            for key in ("score", "totalScore", "value"):
                parsed = _parse_number_text(score.get(key))
                if parsed is not None:
                    return int(parsed) if kind != "pain" else parsed
        parsed = _parse_number_text(doc.get("scoreDesc") or doc.get("score") or doc.get("value"))
        if parsed is None:
            return None
        return int(parsed) if kind != "pain" else parsed
    return None


def extract_assessment_from_bedside_doc(kind: str, doc: dict):
    value = doc.get("intVal")
    if value is None:
        value = doc.get("fVal")
    if value is None:
        value = doc.get("strVal")

    if kind == "gcs":
        return _parse_gcs_text(value)
    parsed = _parse_number_text(value)
    if parsed is None:
        return None
    return int(parsed) if kind != "pain" else parsed


async def load_dc_doc_map(col_name: str, key_field: str, fields: list[str]) -> dict:
    mapping = {}
    projection = {key_field: 1}
    for field in fields:
        projection[field] = 1
    cursor = runtime.db.dc_col(col_name).find({}, projection)
    async for doc in cursor:
        key = doc.get(key_field)
        if key is None:
            continue
        mapping[str(key)] = {field: doc.get(field) for field in fields}
    return mapping


async def load_sc_doc_map(col_name: str, key_field: str, fields: list[str]) -> dict:
    mapping = {}
    projection = {key_field: 1}
    for field in fields:
        projection[field] = 1
    cursor = runtime.db.col(col_name).find({}, projection)
    async for doc in cursor:
        key = doc.get(key_field)
        if key is None:
            continue
        mapping[str(key)] = {field: doc.get(field) for field in fields}
    return mapping


def beautify_freq(name: str | None, desc: str | None, fix_times: list | None, per_day: int | None) -> str:
    if fix_times and isinstance(fix_times, list):
        pretty_times = []
        for item in fix_times:
            if isinstance(item, dict):
                value = item.get("hourMin") or item.get("time") or item.get("value")
            else:
                value = item
            if value:
                pretty_times.append(str(value))
        if pretty_times:
            return "、".join(pretty_times)
    if per_day and isinstance(per_day, (int, float)) and per_day > 0:
        try:
            per_day_int = int(per_day)
            if per_day_int == 1:
                return "每日一次"
            return f"每日{per_day_int}次"
        except Exception:
            pass
    if desc:
        return str(desc)
    if not name:
        return ""
    text = str(name).strip()
    lower = text.lower()
    abbr_map = {
        "qd": "每日一次",
        "bid": "每日两次",
        "tid": "每日三次",
        "qid": "每日四次",
        "qod": "隔日一次",
        "qn": "每晚一次",
        "hs": "睡前一次",
        "prn": "必要时",
        "stat": "立即一次",
        "st": "立即一次",
        "once": "一次",
    }
    if lower in abbr_map:
        return abbr_map[lower]
    match = re.match(r"q(\d+)(h|d)$", lower)
    if match:
        num = int(match.group(1))
        unit = "小时" if match.group(2) == "h" else "天"
        return f"每{num}{unit}一次"
    return text


def infer_device_type(name: str | None) -> str | None:
    if not name:
        return None
    text = str(name)
    if any(key in text for key in ["呼吸机", "vent", "Vent"]):
        return "vent"
    if any(key in text for key in ["监护", "monitor", "Mindray", "迈瑞"]):
        return "monitor"
    if any(key in text for key in ["CRRT", "血滤", "血液净化"]):
        return "crrt"
    return None


def _device_type_match(name: str | None, prefer_type: str | None) -> bool:
    if not prefer_type:
        return True
    inferred = infer_device_type(name)
    if inferred is None:
        return True
    return inferred == prefer_type


async def get_device_id_by_bed(bed, dept_code: str | None = None, prefer_type: str | None = None) -> str | None:
    norm_bed = normalize_bed(bed)
    if not norm_bed:
        return None

    query = {"isConnected": True}
    if dept_code:
        query["deptCode"] = dept_code
    cursor = runtime.db.col("deviceOnline").find(query, {"deviceID": 1, "curBed": 1, "lastBed": 1})
    candidates = []
    async for doc in cursor:
        if bed_match(norm_bed, doc.get("curBed")) or bed_match(norm_bed, doc.get("lastBed")):
            if doc.get("deviceID"):
                candidates.append(doc.get("deviceID"))

    if candidates:
        if not prefer_type:
            return candidates[0]
        for device_id in candidates:
            info = await runtime.db.col("deviceInfo").find_one(
                {"_id": safe_oid(device_id) or device_id},
                {"deviceName": 1},
            )
            if _device_type_match(info.get("deviceName") if info else None, prefer_type):
                return device_id
        return candidates[0]

    query = {"defaultBed": {"$ne": ""}}
    if dept_code:
        query["deptCode"] = dept_code
    cursor = runtime.db.col("deviceInfo").find(query, {"_id": 1, "defaultBed": 1, "deviceName": 1})
    async for doc in cursor:
        if bed_match(norm_bed, doc.get("defaultBed")) and _device_type_match(doc.get("deviceName"), prefer_type):
            return str(doc.get("_id"))
    return None


async def get_device_id(pid_str: str, prefer_type: str | None = None, patient_doc: dict | None = None) -> str | None:
    if not pid_str and not patient_doc:
        return None
    if pid_str:
        query = {"pid": pid_str, "unBindTime": None}
        if prefer_type:
            query["type"] = prefer_type
        doc = await runtime.db.col("deviceBind").find_one(query, sort=[("bindTime", -1)])
        if doc:
            return doc.get("deviceID")
        if prefer_type:
            doc = await runtime.db.col("deviceBind").find_one({"pid": pid_str, "unBindTime": None}, sort=[("bindTime", -1)])
            if doc:
                return doc.get("deviceID")

    if not patient_doc and pid_str:
        patient_doc = await runtime.db.col("patient").find_one(
            {"_id": safe_oid(pid_str) or pid_str},
            {"hisBed": 1, "bed": 1, "deptCode": 1},
        )
    if patient_doc:
        bed = patient_doc.get("hisBed") or patient_doc.get("bed")
        dept_code = patient_doc.get("deptCode")
        return await get_device_id_by_bed(bed, dept_code, prefer_type)
    return None


async def latest_params_by_pid(pid_input: str | list[str], codes: list[str], lookback_minutes: int = 10080) -> dict | None:
    if not pid_input or not codes:
        return None

    if isinstance(pid_input, list):
        pids = [str(value) for value in pid_input]
    else:
        pids = [str(pid_input)]
        patient_doc = await runtime.db.col("patient").find_one({"_id": safe_oid(pid_input)}, {"hisPid": 1, "hisPID": 1})
        if patient_doc:
            his_pid = patient_doc.get("hisPid") or patient_doc.get("hisPID")
            if his_pid and str(his_pid) not in pids:
                pids.append(str(his_pid))

    since = datetime.now() - timedelta(minutes=lookback_minutes)
    cursor = runtime.db.col("bedside").find(
        {"pid": {"$in": pids}, "code": {"$in": codes}, "time": {"$gte": since}},
        {"code": 1, "time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", -1).limit(2000)
    params = {}
    latest_time = None
    async for doc in cursor:
        code = doc.get("code")
        if not code or code in params:
            continue
        value = cap_value(doc)
        if value is None:
            continue
        params[code] = value
        point_time = cap_time(doc)
        if point_time and (latest_time is None or point_time > latest_time):
            latest_time = point_time
        if len(params) >= len(codes):
            break
    if not params:
        return None
    return {"params": params, "time": latest_time}


async def latest_params_by_device(device_id: str, codes: list[str], lookback_minutes: int = 60) -> dict | None:
    if not device_id or not codes:
        return None
    since = datetime.now() - timedelta(minutes=lookback_minutes)
    cursor = runtime.db.col("deviceCap").find(
        {"deviceID": device_id, "code": {"$in": codes}, "time": {"$gte": since}},
        {"code": 1, "time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", -1).limit(2000)
    params = {}
    latest_time = None
    async for doc in cursor:
        code = doc.get("code")
        if not code or code in params:
            continue
        value = cap_value(doc)
        if value is None:
            continue
        params[code] = value
        point_time = cap_time(doc)
        if point_time and (latest_time is None or point_time > latest_time):
            latest_time = point_time
        if len(params) >= len(codes):
            break
    if not params:
        return None
    return {"params": params, "time": latest_time}


async def param_series_by_pid(pid_str: str, code: str, since: datetime) -> list[dict]:
    if not pid_str or not code:
        return []
    pids = [pid_str]
    patient_doc = await runtime.db.col("patient").find_one({"_id": safe_oid(pid_str)}, {"hisPid": 1, "hisPID": 1})
    his_pid = patient_his_pid(patient_doc)
    if his_pid and his_pid not in pids:
        pids.append(his_pid)

    cursor = runtime.db.col("bedside").find(
        {"pid": {"$in": pids}, "code": code, "time": {"$gte": since}},
        {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", 1).limit(2000)
    points = []
    async for doc in cursor:
        value = cap_value(doc)
        if value is None:
            continue
        point_time = cap_time(doc)
        if point_time:
            points.append({"time": point_time, "value": value})
    if points:
        return points

    device_id = await get_device_id(pid_str, "monitor")
    if not device_id:
        return []

    cursor = runtime.db.col("deviceCap").find(
        {"deviceID": device_id, "code": code, "time": {"$gte": since}},
        {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", 1).limit(2000)
    async for doc in cursor:
        value = cap_value(doc)
        if value is None:
            continue
        point_time = cap_time(doc)
        if point_time:
            points.append({"time": point_time, "value": value})
    return points
