"""
ICU智能预警系统 - FastAPI 主应用
"""
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

import httpx
from bson import ObjectId
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# =============================================
# 日志配置
# =============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("icu-alert")

# =============================================
# 模块级变量（在 lifespan 中赋值，端点函数直接使用）
# =============================================
from app.config import AppConfig, get_config
from app.database import DatabaseManager
from app.ws_manager import WebSocketManager
from app.alert_engine import AlertEngine

db: DatabaseManager = None        # type: ignore[assignment]
config: AppConfig = None          # type: ignore[assignment]
ws_mgr: WebSocketManager = None   # type: ignore[assignment]
alert_engine: AlertEngine = None  # type: ignore[assignment]


# =============================================
# Lifespan 生命周期管理
# =============================================
@asynccontextmanager
async def lifespan(application: FastAPI):
    global db, config, ws_mgr, alert_engine

    # 启动
    logger.info("🚀 ICU智能预警系统启动中...")

    config = get_config()
    db = DatabaseManager(config)
    await db.connect()

    ws_mgr = WebSocketManager()

    alert_engine = AlertEngine(db, config, ws_mgr)
    await alert_engine.start()

    # 挂到 app.state 以便需要时通过 request.app.state 访问
    application.state.db = db
    application.state.config = config
    application.state.ws_mgr = ws_mgr
    application.state.alert_engine = alert_engine

    logger.info("✅ ICU智能预警系统启动完成")
    yield

    # 关闭
    logger.info("⏹️ ICU智能预警系统关闭中...")
    await alert_engine.stop()
    await db.disconnect()
    logger.info("✅ ICU智能预警系统已关闭")


# =============================================
# FastAPI 应用创建
# =============================================
app = FastAPI(
    title="ICU智能预警系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（开发环境允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================
# 辅助函数
# =============================================
def serialize_doc(doc: dict) -> dict:
    """将 MongoDB 文档转换为 JSON 可序列化的字典（ObjectId→str，datetime→isoformat）"""
    if doc is None:
        return {}
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = serialize_doc(v)
        elif isinstance(v, list):
            result[k] = [
                serialize_doc(item) if isinstance(item, dict) else
                str(item) if isinstance(item, ObjectId) else
                item.isoformat() if isinstance(item, datetime) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


def _pv(params: dict, key: str):
    """提取参数值，尝试转为数字"""
    v = params.get(key)
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("value", v.get("v"))
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _active_patient_query() -> dict:
    return {
        "$or": [
            {"status": {"$nin": ["discharged", "invalid", "invaild"]}},
            {"status": {"$exists": False}},
        ]
    }


def _safe_oid(value):
    if isinstance(value, ObjectId):
        return value
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _cap_time(doc: dict) -> datetime | None:
    if not doc:
        return None
    return doc.get("time") or doc.get("recordTime")


def _cap_value(doc: dict) -> float | None:
    if not doc:
        return None
    for key in ("fVal", "intVal", "strVal", "value"):
        v = doc.get(key)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _norm_num(v: float | int | None):
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if abs(fv - round(fv)) < 1e-9:
        return int(round(fv))
    return round(fv, 2)


def _parse_number_text(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        pass
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _parse_gcs_text(v) -> int | None:
    if v is None:
        return None
    s = str(v).strip().upper().replace(" ", "")
    if not s:
        return None
    m = re.match(r"^E(\d+)V(T|\d+)M(\d+)$", s)
    if not m:
        return None
    eye = int(m.group(1))
    verbal = 0 if m.group(2) == "T" else int(m.group(2))
    motor = int(m.group(3))
    return eye + verbal + motor


def _patient_his_pid_candidates(patient: dict | None) -> list[str]:
    if not patient:
        return []
    ids: list[str] = []
    for k in ("hisPid", "hisPID", "hisPatientId", "patientId", "mrn", "hisMrn"):
        v = patient.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s and s not in ids:
            ids.append(s)
    return ids


def _patient_his_pid(patient: dict | None) -> str:
    ids = _patient_his_pid_candidates(patient)
    return ids[0] if ids else ""


def _lab_time(doc: dict) -> datetime | None:
    return (
        doc.get("authTime")
        or doc.get("collectTime")
        or doc.get("requestTime")
        or doc.get("reportTime")
        or doc.get("resultTime")
        or doc.get("time")
    )


def _lab_group_key(doc: dict) -> str:
    return (
        str(doc.get("examID") or "")
        or str(doc.get("orderID") or "")
        or str(doc.get("dataId") or "")
        or str(doc.get("reportID") or "")
        or str(doc.get("_id"))
    )


async def _fetch_dc_exam_items_by_his_pid(his_pid: str | list[str], limit_exams: int = 50, limit_items: int = 3000) -> tuple[list[dict], list[dict]]:
    if isinstance(his_pid, list):
        his_pids = [str(x).strip() for x in his_pid if str(x).strip()]
    else:
        hs = str(his_pid).strip() if his_pid is not None else ""
        his_pids = [hs] if hs else []
    if not his_pids:
        return [], []
    his_pid_query = {"hisPid": his_pids[0]} if len(his_pids) == 1 else {"hisPid": {"$in": his_pids}}

    exam_cols = [db.dc_col("VI_ICU_EXAM"), db.dc_col("VI_ICU_EXAM_admitted")]
    exams: list[dict] = []
    for col in exam_cols:
        exam_cursor = col.find(his_pid_query).sort("authTime", -1).limit(limit_exams)
        exams.extend([doc async for doc in exam_cursor])
    if exams:
        exams = sorted(exams, key=lambda x: _lab_time(x) or datetime.min, reverse=True)[:limit_exams]

    report_ids = list({str(e.get("reportID")) for e in exams if e.get("reportID")})
    data_ids = list({str(e.get("dataId")) for e in exams if e.get("dataId")})

    or_list = []
    if report_ids:
        or_list.append({"examID": {"$in": report_ids}})
        or_list.append({"orderID": {"$in": report_ids}})
    if data_ids:
        or_list.append({"dataId": {"$in": data_ids}})
    # 某些数据可直接按 hisPid 关联
    or_list.append(his_pid_query)

    item_cursor = db.dc_col("VI_ICU_EXAM_ITEM").find({"$or": or_list}).sort("authTime", -1).limit(limit_items)
    items = [doc async for doc in item_cursor]
    return exams, items


def _assess_time_key(t) -> str:
    if not t:
        return ""
    s = str(t)
    if "T" in s:
        s = s.split("T")[0] + " " + s.split("T")[1]
    return s[:16]  # YYYY-MM-DD HH:MM


def _merge_assessment_records(records: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for r in records:
        key = _assess_time_key(r.get("time"))
        if key not in merged:
            merged[key] = {"time": r.get("time")}
        for k in ["gcs", "rass", "pain", "delirium", "braden"]:
            if r.get(k) is not None:
                merged[key][k] = r.get(k)
    # 排序：时间降序
    return sorted(merged.values(), key=lambda x: str(x.get("time") or ""), reverse=True)


def _extract_assessment_from_score_doc(doc: dict, kind: str):
    val = doc.get("total")
    if val in (None, ""):
        raw_score = doc.get("score")
        if isinstance(raw_score, (int, float, str)):
            val = raw_score

    if kind == "gcs":
        g = doc.get("gcsScore")
        if isinstance(g, dict):
            if val in (None, ""):
                eye = _parse_number_text(g.get("eye"))
                motor = _parse_number_text(g.get("sport") or g.get("motor"))
                verbal = _parse_number_text(g.get("v") or g.get("verbal"))
                if eye is not None and motor is not None:
                    val = eye + motor + (verbal or 0)
                elif g.get("score"):
                    maybe = _parse_gcs_text(g.get("score"))
                    val = maybe if maybe is not None else g.get("score")

    if kind == "rass" and val in (None, ""):
        val = doc.get("rass")

    if kind == "pain" and val in (None, ""):
        cpot = doc.get("cpotScore")
        if isinstance(cpot, dict):
            if cpot.get("totalScore") is not None:
                val = cpot.get("totalScore")
            else:
                vals = [
                    _parse_number_text(cpot.get("face")),
                    _parse_number_text(cpot.get("bodyActivity")),
                    _parse_number_text(cpot.get("bodyCoordination")),
                    _parse_number_text(cpot.get("muscleTension")),
                ]
                nums = [x for x in vals if x is not None]
                if nums:
                    val = sum(nums)
        if val in (None, ""):
            p = doc.get("painScore")
            if isinstance(p, dict):
                for sec_name in ("cpot", "nrs", "vrs", "frs"):
                    sec = p.get(sec_name)
                    if not isinstance(sec, dict):
                        continue
                    if sec.get("totalScore") is not None:
                        val = sec.get("totalScore")
                        break
                    num = _parse_number_text(sec.get("score") or sec.get("value"))
                    if num is not None:
                        val = num
                        break

    if kind == "delirium":
        d = doc.get("deliriumScore")
        if isinstance(d, dict):
            txt = d.get("conclusion") or d.get("consciousness")
            if txt:
                return str(txt)

    if kind == "braden" and val in (None, ""):
        b = doc.get("bradenScore")
        if isinstance(b, dict):
            vals = [
                _parse_number_text(b.get("feel")),
                _parse_number_text(b.get("damp")),
                _parse_number_text(b.get("activityAbility")),
                _parse_number_text(b.get("moveAbility")),
                _parse_number_text(b.get("nutritionAbility")),
                _parse_number_text(b.get("frictionAndShear")),
            ]
            nums = [x for x in vals if x is not None]
            if nums:
                val = sum(nums)

    if isinstance(val, str):
        n = _parse_number_text(val)
        if n is not None:
            return _norm_num(n)
        s = val.strip()
        return s or None
    if isinstance(val, (int, float)):
        return _norm_num(val)
    return None


def _extract_assessment_from_bedside_doc(kind: str, doc: dict):
    if kind == "gcs":
        score = _parse_gcs_text(doc.get("strVal"))
        if score is not None:
            return score
    n = _cap_value(doc)
    if n is not None:
        return _norm_num(n)

    sv = doc.get("strVal")
    n2 = _parse_number_text(sv)
    if n2 is not None:
        return _norm_num(n2)

    if kind == "delirium":
        s = str(sv or "").strip()
        if s:
            return s
    return None


async def _load_dc_code_map(col_name: str, key_field: str, value_fields: list[str]) -> dict:
    col = db.dc_col(col_name)
    mapping: dict = {}
    cursor = col.find({}, {key_field: 1, **{f: 1 for f in value_fields}})
    async for doc in cursor:
        key = doc.get(key_field)
        if not key:
            continue
        val = None
        for f in value_fields:
            if doc.get(f):
                val = doc.get(f)
                break
        if val:
            mapping[str(key)] = val
    return mapping


async def _load_sc_code_map(col_name: str, key_field: str, value_fields: list[str]) -> dict:
    col = db.col(col_name)
    mapping: dict = {}
    cursor = col.find({}, {key_field: 1, **{f: 1 for f in value_fields}})
    async for doc in cursor:
        key = doc.get(key_field)
        if not key:
            continue
        val = None
        for f in value_fields:
            if doc.get(f):
                val = doc.get(f)
                break
        if val:
            mapping[str(key)] = val
    return mapping


async def _load_dc_doc_map(col_name: str, key_field: str, fields: list[str]) -> dict:
    col = db.dc_col(col_name)
    mapping: dict = {}
    cursor = col.find({}, {key_field: 1, **{f: 1 for f in fields}})
    async for doc in cursor:
        key = doc.get(key_field)
        if not key:
            continue
        mapping[str(key)] = {f: doc.get(f) for f in fields}
    return mapping


async def _load_sc_doc_map(col_name: str, key_field: str, fields: list[str]) -> dict:
    col = db.col(col_name)
    mapping: dict = {}
    cursor = col.find({}, {key_field: 1, **{f: 1 for f in fields}})
    async for doc in cursor:
        key = doc.get(key_field)
        if not key:
            continue
        mapping[str(key)] = {f: doc.get(f) for f in fields}
    return mapping


def _beautify_freq(name: str | None, desc: str | None, fix_times: list | None, per_day: int | None) -> str:
    if desc:
        return str(desc)
    if per_day and per_day > 0:
        return f"每日{per_day}次"
    if fix_times:
        times = []
        for t in fix_times:
            h = t.get("hour") if isinstance(t, dict) else None
            m = t.get("min") if isinstance(t, dict) else None
            if h is not None and m is not None:
                times.append(f"{int(h):02d}:{int(m):02d}")
        if times:
            return f"每日{len(times)}次({', '.join(times)})"

    if not name:
        return ""
    n = str(name).strip()
    nl = n.lower()
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
    if nl in abbr_map:
        return abbr_map[nl]
    m = re.match(r"q(\d+)(h|d)$", nl)
    if m:
        num = int(m.group(1))
        unit = "小时" if m.group(2) == "h" else "天"
        return f"每{num}{unit}一次"
    return n


def _normalize_bed(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.upper().replace("床", "")
    if s.startswith("BED"):
        s = s[3:]
    s = s.strip()
    m = re.search(r"\d+", s)
    if m:
        try:
            return str(int(m.group(0)))
        except Exception:
            return m.group(0)
    return s


def _bed_match(a, b) -> bool:
    na = _normalize_bed(a)
    nb = _normalize_bed(b)
    if not na or not nb:
        return False
    return na == nb


def _infer_device_type(name: str | None) -> str | None:
    if not name:
        return None
    n = str(name)
    if any(k in n for k in ["呼吸机", "vent", "Vent"]):
        return "vent"
    if any(k in n for k in ["监护", "中央站", "monitor", "Monitor", "监视"]):
        return "monitor"
    if any(k in n for k in ["CRRT", "血滤", "血液净化"]):
        return "crrt"
    return None


def _window_to_hours(window: str, default: int = 168) -> int:
    v = str(window or "").strip().lower()
    if not v:
        return default
    fixed = {
        "6h": 6,
        "12h": 12,
        "24h": 24,
        "48h": 48,
        "72h": 72,
        "7d": 168,
        "14d": 336,
        "30d": 720,
    }
    if v in fixed:
        return fixed[v]
    m = re.match(r"^(\d+)\s*([hd])$", v)
    if not m:
        return default
    num = int(m.group(1))
    unit = m.group(2)
    if unit == "h":
        return max(1, min(num, 24 * 90))
    return max(24, min(num * 24, 24 * 180))


def _bucket_dt_format(bucket: str) -> tuple[str, str]:
    b = str(bucket or "").strip().lower()
    if b == "day":
        return "day", "%Y-%m-%d"
    return "hour", "%Y-%m-%d %H:00"


def _severity_projection() -> dict:
    return {
        "warning": {"$sum": {"$cond": [{"$eq": ["$severity", "warning"]}, 1, 0]}},
        "high": {"$sum": {"$cond": [{"$eq": ["$severity", "high"]}, 1, 0]}},
        "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "critical"]}, 1, 0]}},
    }


def _device_type_match(name: str | None, prefer_type: str | None) -> bool:
    if not prefer_type:
        return True
    inferred = _infer_device_type(name)
    if inferred is None:
        return True
    return inferred == prefer_type


async def _get_device_id_by_bed(bed, dept_code: str | None = None, prefer_type: str | None = None) -> str | None:
    norm_bed = _normalize_bed(bed)
    if not norm_bed:
        return None

    query = {"isConnected": True}
    if dept_code:
        query["deptCode"] = dept_code
    cursor = db.col("deviceOnline").find(query, {"deviceID": 1, "curBed": 1, "lastBed": 1})
    candidates = []
    async for doc in cursor:
        if _bed_match(norm_bed, doc.get("curBed")) or _bed_match(norm_bed, doc.get("lastBed")):
            if doc.get("deviceID"):
                candidates.append(doc.get("deviceID"))

    if candidates:
        if not prefer_type:
            return candidates[0]
        for device_id in candidates:
            info = await db.col("deviceInfo").find_one(
                {"_id": _safe_oid(device_id) or device_id},
                {"deviceName": 1},
            )
            if _device_type_match(info.get("deviceName") if info else None, prefer_type):
                return device_id
        return candidates[0]

    query = {"defaultBed": {"$ne": ""}}
    if dept_code:
        query["deptCode"] = dept_code
    cursor = db.col("deviceInfo").find(query, {"_id": 1, "defaultBed": 1, "deviceName": 1})
    async for doc in cursor:
        if _bed_match(norm_bed, doc.get("defaultBed")):
            if _device_type_match(doc.get("deviceName"), prefer_type):
                return str(doc.get("_id"))
    return None


async def _get_device_id(pid_str: str, prefer_type: str | None = None, patient_doc: dict | None = None) -> str | None:
    if not pid_str and not patient_doc:
        return None
    if pid_str:
        query = {"pid": pid_str, "unBindTime": None}
        if prefer_type:
            query["type"] = prefer_type
        doc = await db.col("deviceBind").find_one(query, sort=[("bindTime", -1)])
        if doc:
            return doc.get("deviceID")
        if prefer_type:
            doc = await db.col("deviceBind").find_one({"pid": pid_str, "unBindTime": None}, sort=[("bindTime", -1)])
            if doc:
                return doc.get("deviceID")

    if not patient_doc and pid_str:
        patient_doc = await db.col("patient").find_one(
            {"_id": _safe_oid(pid_str) or pid_str},
            {"hisBed": 1, "bed": 1, "deptCode": 1},
        )
    if patient_doc:
        bed = patient_doc.get("hisBed") or patient_doc.get("bed")
        dept_code = patient_doc.get("deptCode")
        return await _get_device_id_by_bed(bed, dept_code, prefer_type)
    return None


async def _latest_params_by_pid(pid_str: str, codes: list[str], lookback_minutes: int = 60) -> dict | None:
    if not pid_str or not codes:
        return None
    since = datetime.now() - timedelta(minutes=lookback_minutes)
    cursor = db.col("bedside").find(
        {"pid": pid_str, "code": {"$in": codes}, "time": {"$gte": since}},
        {"code": 1, "time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", -1).limit(2000)
    params = {}
    latest_time = None
    async for doc in cursor:
        code = doc.get("code")
        if not code or code in params:
            continue
        v = _cap_value(doc)
        if v is None:
            continue
        params[code] = v
        t = _cap_time(doc)
        if t and (latest_time is None or t > latest_time):
            latest_time = t
        if len(params) >= len(codes):
            break
    if not params:
        return None
    return {"params": params, "time": latest_time}


async def _latest_params_by_device(device_id: str, codes: list[str], lookback_minutes: int = 60) -> dict | None:
    if not device_id or not codes:
        return None
    since = datetime.now() - timedelta(minutes=lookback_minutes)
    cursor = db.col("deviceCap").find(
        {"deviceID": device_id, "code": {"$in": codes}, "time": {"$gte": since}},
        {"code": 1, "time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", -1).limit(2000)
    params = {}
    latest_time = None
    async for doc in cursor:
        code = doc.get("code")
        if not code or code in params:
            continue
        v = _cap_value(doc)
        if v is None:
            continue
        params[code] = v
        t = _cap_time(doc)
        if t and (latest_time is None or t > latest_time):
            latest_time = t
        if len(params) >= len(codes):
            break
    if not params:
        return None
    return {"params": params, "time": latest_time}


async def _param_series_by_pid(pid_str: str, code: str, since: datetime) -> list[dict]:
    if not pid_str or not code:
        return []
    cursor = db.col("bedside").find(
        {"pid": pid_str, "code": code, "time": {"$gte": since}},
        {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", 1).limit(2000)
    points = []
    async for doc in cursor:
        v = _cap_value(doc)
        if v is None:
            continue
        t = _cap_time(doc)
        if t:
            points.append({"time": t, "value": v})
    if points:
        return points

    device_id = await _get_device_id(pid_str, "monitor")
    if not device_id:
        return []
    cursor = db.col("deviceCap").find(
        {"deviceID": device_id, "code": code, "time": {"$gte": since}},
        {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", 1).limit(2000)
    async for doc in cursor:
        v = _cap_value(doc)
        if v is None:
            continue
        t = _cap_time(doc)
        if t:
            points.append({"time": t, "value": v})
    return points


def infer_clinical_tags(doc: dict) -> list:
    """根据诊断、护理级别等信息推断临床标签"""
    tags = []
    diag = (
        str(doc.get("clinicalDiagnosis", ""))
        + str(doc.get("admissionDiagnosis", ""))
    ).lower()
    nursing = str(doc.get("nursingLevel", "")).lower()

    vent_kw = ["呼吸机", "机械通气", "气管插管", "气管切开", "ventilator", "mv"]
    if any(k in diag for k in vent_kw):
        tags.append({"tag": "ventilator", "label": "呼吸机", "icon": "🫁", "color": "#3b82f6"})

    crrt_kw = ["crrt", "血滤", "血液净化", "透析"]
    if any(k in diag for k in crrt_kw):
        tags.append({"tag": "crrt", "label": "CRRT", "icon": "🩸", "color": "#8b5cf6"})

    if "压疮" in diag or "压力性损伤" in diag:
        tags.append({"tag": "pressure_ulcer", "label": "压疮", "icon": "⚠️", "color": "#ef4444"})

    infect_kw = ["脓毒", "感染", "sepsis", "肺炎", "pneumonia"]
    if any(k in diag for k in infect_kw):
        tags.append({"tag": "infection", "label": "感染", "icon": "🦠", "color": "#f59e0b"})

    bleed_kw = ["出血", "hemorrhage", "bleeding"]
    if any(k in diag for k in bleed_kw):
        tags.append({"tag": "bleeding", "label": "出血", "icon": "🩹", "color": "#dc2626"})

    cons_kw = ["昏迷", "意识障碍", "脑出血", "脑梗", "coma"]
    if any(k in diag for k in cons_kw):
        tags.append({"tag": "consciousness", "label": "意识障碍", "icon": "🧠", "color": "#a855f7"})

    if "特级" in nursing or "特护" in nursing:
        tags.append({"tag": "special_care", "label": "特护", "icon": "⭐", "color": "#eab308"})

    mods_kw = ["mods", "多器官", "多脏器"]
    if any(k in diag for k in mods_kw):
        tags.append({"tag": "mods", "label": "MODS", "icon": "💔", "color": "#b91c1c"})

    return tags


async def _call_llm(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """统一调用 LLM"""
    cfg = get_config()
    llm_url = cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    llm_model = model or cfg.settings.LLM_MODEL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.settings.LLM_API_KEY}",
    }
    payload = {
        "model": llm_model,
        "temperature": 0.1,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(llm_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# =============================================
# 健康检查
# =============================================
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok"}


# =============================================
# 科室列表
# =============================================
@app.get("/api/departments")
async def get_departments():
    """获取所有科室及在院患者数量"""
    col = db.col("patient")
    # 获取所有在院患者的科室字段
    pipeline = [
        {"$match": _active_patient_query()},
        {"$group": {
            "_id": {"$ifNull": ["$hisDept", "$dept"]},
            "patientCount": {"$sum": 1},
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"patientCount": -1}},
    ]
    departments = []
    cursor = await col.aggregate(pipeline)
    async for doc in cursor:
        departments.append({
            "dept": doc["_id"],
            "patientCount": doc["patientCount"],
        })
    return {"code": 0, "departments": departments}


# =============================================
# 患者列表
# =============================================
@app.get("/api/patients")
async def get_patients(
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    """获取在院患者列表，可按科室筛选"""
    query: dict = _active_patient_query()
    if dept:
        query = {"$and": [query, {"$or": [{"hisDept": dept}, {"dept": dept}]}]}
    elif dept_code:
        query = {"$and": [query, {"deptCode": dept_code}]}

    col = db.col("patient")
    cursor = col.find(query).sort("hisBed", 1)
    patients = []
    async for doc in cursor:
        p = serialize_doc(doc)
        p["clinicalTags"] = infer_clinical_tags(doc)
        patients.append(p)
    return {"code": 0, "patients": patients}


# =============================================
# 患者详情
# =============================================
@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    """获取患者详细信息"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    doc = await db.col("patient").find_one({"_id": pid})
    if not doc:
        return {"code": 404, "message": "患者不存在"}
    return {"code": 0, "patient": serialize_doc(doc)}


# =============================================
# 当前生命体征
# =============================================
@app.get("/api/patients/{patient_id}/vitals")
async def patient_vitals(patient_id: str):
    """获取患者当前最新生命体征"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    vitals: dict = {}
    pid_str = str(pid)
    codes = [
        "param_HR", "param_spo2", "param_resp", "param_T",
        "param_nibp_s", "param_nibp_d", "param_nibp_m",
        "param_ibp_s", "param_ibp_d", "param_ibp_m",
        "param_cvp", "param_ETCO2",
    ]

    snapshot = await _latest_params_by_pid(pid_str, codes)
    source = None
    if snapshot:
        source = "monitor"
    else:
        device_id = await _get_device_id(pid_str, "monitor")
        if device_id:
            snapshot = await _latest_params_by_device(device_id, codes)
            if snapshot:
                source = "device"

    if snapshot:
        params = snapshot.get("params", {})
        t = snapshot.get("time")
        vitals = {
            "source": source,
            "time": t.isoformat() if isinstance(t, datetime) else str(t),
            "hr": params.get("param_HR"),
            "spo2": params.get("param_spo2"),
            "rr": params.get("param_resp"),
            "temp": params.get("param_T"),
            "nibp_sys": params.get("param_nibp_s"),
            "nibp_dia": params.get("param_nibp_d"),
            "nibp_map": params.get("param_nibp_m"),
            "ibp_sys": params.get("param_ibp_s"),
            "ibp_dia": params.get("param_ibp_d"),
            "ibp_map": params.get("param_ibp_m"),
            "cvp": params.get("param_cvp"),
            "etco2": params.get("param_ETCO2"),
        }

    return {"code": 0, "vitals": vitals}


# =============================================
# 检验结果
# =============================================
@app.get("/api/patients/{patient_id}/labs")
async def patient_labs(patient_id: str):
    """获取患者近期检验结果（DataCenter: EXAM + EXAM_ITEM 联合）"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    # 通过 patient.hisPid 关联到 DataCenter
    patient = await db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    patient_ids = _patient_his_pid_candidates(patient)
    exams = []
    if patient_ids:
        his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
        exam_docs = []
        for col_name in ("VI_ICU_EXAM", "VI_ICU_EXAM_admitted"):
            cursor = db.dc_col(col_name).find(his_pid_query).sort("authTime", -1).limit(80)
            exam_docs.extend([doc async for doc in cursor])
        if exam_docs:
            exam_docs = sorted(exam_docs, key=lambda x: _lab_time(x) or datetime.min, reverse=True)[:80]

        cursor = db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(1800)
        item_docs = [doc async for doc in cursor]

        if not item_docs:
            exam_docs, item_docs = await _fetch_dc_exam_items_by_his_pid(
                patient_ids, limit_exams=60, limit_items=1800
            )

        exam_name_by_report: dict[str, str] = {}
        exam_name_by_data: dict[str, str] = {}
        for ex in exam_docs:
            name = (
                ex.get("code")
                or ex.get("examName")
                or ex.get("requestName")
                or ex.get("orderName")
                or ""
            )
            if isinstance(name, str) and name.isdigit():
                name = ""
            if not name:
                continue
            report_id = str(ex.get("reportID") or "")
            data_id = str(ex.get("dataId") or "")
            if report_id:
                exam_name_by_report[report_id] = str(name)
            if data_id:
                exam_name_by_data[data_id] = str(name)

        grouped: dict = {}
        for doc in item_docs:
            key = _lab_group_key(doc)
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
                    "requestTime": _lab_time(doc),
                    "items": [],
                }
            item = {
                "itemName": doc.get("itemName"),
                "itemCnName": doc.get("itemCnName"),
                "itemCode": doc.get("itemCode"),
                "result": doc.get("result") or doc.get("resultValue") or doc.get("value"),
                "unit": doc.get("unit") or doc.get("resultUnit"),
                "resultFlag": doc.get("resultFlag") or doc.get("abnormalFlag") or doc.get("seriousFlag") or doc.get("resultStatus"),
            }
            grouped[key]["items"].append(item)
            if not grouped[key].get("requestTime"):
                grouped[key]["requestTime"] = _lab_time(doc)

        exams = sorted(grouped.values(), key=lambda x: x.get("requestTime") or datetime.min, reverse=True)
        exams = [serialize_doc(e) for e in exams]

    return {"code": 0, "exams": exams}


# =============================================
# 生命体征趋势
# =============================================
@app.get("/api/patients/{patient_id}/vitals/trend")
async def patient_vitals_trend(
    patient_id: str,
    window: str = Query("24h", regex="^(6h|12h|24h|48h|7d)$"),
):
    """查询患者一段时间内的生命体征趋势数据"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    hours_map = {"6h": 6, "12h": 12, "24h": 24, "48h": 48, "7d": 168}
    hours = hours_map.get(window, 24)
    since = datetime.now() - timedelta(hours=hours)

    pid_str = str(pid)
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
        series = await _param_series_by_pid(pid_str, code, since)
        for s in series:
            t = s.get("time")
            if not t:
                continue
            key = t.isoformat() if isinstance(t, datetime) else str(t)
            if key not in points_map:
                points_map[key] = {"time": t}
            points_map[key][field] = s.get("value")

    points = sorted(points_map.values(), key=lambda x: x.get("time") or datetime.min)

    # 序列化时间字段
    for p in points:
        p["time"] = (
            p["time"].isoformat()
            if isinstance(p["time"], datetime)
            else str(p["time"]) if p["time"] else None
        )

    return {"code": 0, "points": points}


# =============================================
# 用药记录
# =============================================
@app.get("/api/patients/{patient_id}/drugs")
async def patient_drugs(patient_id: str):
    """查询患者的用药执行记录"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    col = db.col("drugExe")
    cursor = col.find(
        {"pid": str(pid)},
        {
            "drugName": 1, "orderName": 1, "dose": 1, "doseUnit": 1, "route": 1,
            "frequency": 1, "executeTime": 1, "status": 1,
            "orderType": 1, "drugSpec": 1, "startTime": 1, "orderTime": 1,
        },
    ).sort("executeTime", -1).limit(50)

    route_map_dc = await _load_dc_doc_map("VI_ICU_YWYF", "code", ["name", "desc"])
    freq_map_dc = await _load_dc_doc_map("VI_ICU_YYPC", "code", ["freqName", "desc"])
    route_map_sc = await _load_sc_doc_map("configDrugMethod", "code", ["name"])
    freq_map_sc = await _load_sc_doc_map("configOrderFreq", "freqCode", ["freqName", "perDay", "freqFixHourMinList"])

    def _map_route(code):
        if code is None or code == "":
            return code
        key = str(code)
        item = route_map_dc.get(key) or route_map_sc.get(key)
        if not item:
            return code
        return item.get("name") or item.get("desc") or code

    def _map_freq(code):
        if code is None or code == "":
            return code
        key = str(code)
        item = freq_map_dc.get(key) or freq_map_sc.get(key)
        if not item:
            return code
        name = item.get("freqName") or item.get("name")
        desc = item.get("desc")
        fix_times = item.get("freqFixHourMinList")
        per_day = item.get("perDay")
        pretty = _beautify_freq(name, desc, fix_times, per_day)
        return pretty or name or code

    def _has_real_name(val) -> bool:
        if val is None:
            return False
        s = str(val).strip()
        if not s:
            return False
        if re.fullmatch(r"\d+(\.\d+)?", s):
            return False
        return True

    records = []
    has_name = False
    async for doc in cursor:
        if not _has_real_name(doc.get("drugName")):
            doc["drugName"] = doc.get("orderName") or doc.get("drugSpec")
        if not doc.get("executeTime"):
            doc["executeTime"] = doc.get("startTime") or doc.get("orderTime")
        if _has_real_name(doc.get("drugName")):
            has_name = True
        if doc.get("route"):
            doc["route"] = _map_route(doc.get("route"))
        if doc.get("frequency"):
            doc["frequency"] = _map_freq(doc.get("frequency"))
        records.append(serialize_doc(doc))

    if records and has_name:
        return {"code": 0, "records": records}
    records = []

    # fallback: DataCenter 用药执行/医嘱
    patient = await db.col("patient").find_one({"_id": pid}, {"hisPid": 1})
    his_pid = patient.get("hisPid") if patient else None
    if not his_pid:
        return {"code": 0, "records": []}

    route_map = route_map_dc
    freq_map = freq_map_dc

    exec_cursor = db.dc_col("VI_ICU_HSZ_YYZXJL").find(
        {"pid": his_pid}
    ).sort("exeTime", -1).limit(100)
    execs = [doc async for doc in exec_cursor]

    if execs:
        order_ids = [e.get("orderID") for e in execs if e.get("orderID")]
        orders = {}
        if order_ids:
            cursor2 = db.dc_col("VI_ICU_ZYYZ").find({"orderID": {"$in": order_ids}})
            async for o in cursor2:
                if o.get("orderID"):
                    orders[str(o.get("orderID"))] = o

        for e in execs:
            order_id = str(e.get("orderID") or "")
            o = orders.get(order_id, {})
            route_code = o.get("exeMethod")
            freq_code = o.get("freq")
            records.append({
                "drugName": o.get("orderName") or e.get("drugName") or e.get("itemName") or e.get("note"),
                "dose": o.get("spec"),
                "doseUnit": "",
                "route": _map_route(route_code),
                "frequency": _map_freq(freq_code),
                "executeTime": e.get("exeTime") or e.get("planTime") or e.get("checkTime"),
                "status": e.get("status"),
                "orderType": o.get("orderType"),
                "drugSpec": o.get("spec"),
            })
        return {"code": 0, "records": [serialize_doc(r) for r in records]}

    # fallback: 仅医嘱
    order_cursor = db.dc_col("VI_ICU_ZYYZ").find(
        {"pid": his_pid}
    ).sort("orderTime", -1).limit(50)
    async for o in order_cursor:
        route_code = o.get("exeMethod")
        freq_code = o.get("freq")
        records.append({
            "drugName": o.get("orderName"),
            "dose": o.get("spec"),
            "doseUnit": "",
            "route": _map_route(route_code),
            "frequency": _map_freq(freq_code),
            "executeTime": o.get("orderTime"),
            "status": "",
            "orderType": o.get("orderType"),
            "drugSpec": o.get("spec"),
        })

    return {"code": 0, "records": [serialize_doc(r) for r in records]}


# =============================================
# 护理评估
# =============================================
@app.get("/api/patients/{patient_id}/assessments")
async def patient_assessments(patient_id: str):
    """查询患者的护理评估记录（GCS/RASS/疼痛/谵妄/Braden等）"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    pid_str = str(pid)
    records: list[dict] = []

    # 从 score_records 集合查（本系统计算）
    col = db.col("score_records")
    cursor = col.find(
        {"patient_id": {"$in": [pid, str(pid)]}}
    ).sort("calc_time", -1).limit(50)

    async for doc in cursor:
        item = {
            "time": doc.get("calc_time") or doc.get("time") or doc.get("recordTime") or doc.get("created_at"),
            "gcs": doc.get("gcs") or doc.get("gcsScore"),
            "rass": doc.get("rass"),
            "pain": doc.get("pain") or doc.get("painScore") or doc.get("cpotScore"),
            "delirium": doc.get("delirium") or doc.get("deliriumScore"),
            "braden": doc.get("braden") or doc.get("bradenScore"),
        }
        if any(v is not None for v in item.values()):
            records.append(serialize_doc(item))

    # SmartCare score 集合（支持复杂结构提取）
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
    score_col = db.col("score")
    cursor2 = score_col.find(
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
        val = _extract_assessment_from_score_doc(doc, kind)
        if val is None:
            continue
        records.append(serialize_doc({"time": doc.get("time"), kind: val}))

    # bedside 单参数补充（含常见别名）
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
    bedside_col = db.col("bedside")
    for kind, codes in code_map.items():
        cursor3 = bedside_col.find(
            {
                "pid": pid_str,
                "code": {"$in": codes},
                "$or": [{"valid": {"$exists": False}}, {"valid": True}],
            },
            {"time": 1, "code": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1},
        ).sort("time", -1).limit(160)
        async for doc in cursor3:
            val = _extract_assessment_from_bedside_doc(kind, doc)
            if val is None:
                continue
            records.append(serialize_doc({"time": doc.get("time"), kind: val}))

    merged = _merge_assessment_records(records)
    return {"code": 0, "records": merged[:400]}


# =============================================
# 预警历史（单个患者）
# =============================================
@app.get("/api/patients/{patient_id}/alerts")
async def patient_alerts(patient_id: str):
    """查询单个患者的预警历史"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    col = db.col("alert_records")
    cursor = col.find(
        {"patient_id": {"$in": [patient_id, pid]}}
    ).sort("created_at", -1).limit(100)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    return {"code": 0, "records": records}


# =============================================
# 最近预警列表（大屏用）
# =============================================
@app.get("/api/alerts/recent")
async def recent_alerts(
    limit: int = Query(50, ge=1, le=200),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    """获取全院最近的预警记录"""
    col = db.col("alert_records")
    query: dict = {"is_active": True}
    if dept:
        query["dept"] = dept
    elif dept_code:
        # 先按 alert_records.deptCode 过滤（新写入的会带）
        patient_ids = []
        cursor_p = db.col("patient").find({"deptCode": dept_code}, {"_id": 1})
        async for p in cursor_p:
            patient_ids.append(str(p.get("_id")))
        if patient_ids:
            query = {
                "is_active": True,
                "$or": [
                    {"deptCode": dept_code},
                    {"patient_id": {"$in": patient_ids}},
                ],
            }
        else:
            query["deptCode"] = dept_code

    cursor = col.find(query).sort("created_at", -1).limit(limit)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    return {"code": 0, "records": records}


# =============================================
# 预警统计（大屏趋势图）
# =============================================
@app.get("/api/alerts/stats")
async def alert_stats(window: str = Query("24h")):
    """按小时统计预警数量趋势"""
    hours_map = {"6h": 6, "12h": 12, "24h": 24, "48h": 48, "7d": 168}
    hours = hours_map.get(window, 24)
    since = datetime.utcnow() - timedelta(hours=hours)

    col = db.col("alert_records")
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": {
                "hour": {"$dateToString": {"format": "%Y-%m-%d %H:00", "date": "$created_at"}},
                "severity": "$severity",
            },
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.hour": 1}},
    ]

    results = {}
    cursor = await col.aggregate(pipeline)
    async for doc in cursor:
        hour = doc["_id"]["hour"]
        sev = doc["_id"]["severity"]
        if hour not in results:
            results[hour] = {"time": hour, "warning": 0, "high": 0, "critical": 0}
        if sev in results[hour]:
            results[hour][sev] = doc["count"]

    series = sorted(results.values(), key=lambda x: x["time"])
    return {"code": 0, "series": series}


# =============================================
# 预警统计分析（质控 Analytics）
# =============================================
@app.get("/api/alerts/analytics/frequency")
async def alerts_analytics_frequency(
    window: str = Query("7d", description="时间窗口: 24h/7d/30d 或 12h/14d"),
    bucket: str = Query("hour", description="聚合粒度: hour/day"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    """按时间维度统计预警触发频率"""
    hours = _window_to_hours(window, default=168)
    bucket_norm, fmt = _bucket_dt_format(bucket)
    since = datetime.utcnow() - timedelta(hours=hours)

    query: dict = {"created_at": {"$gte": since}}
    if dept:
        query["dept"] = dept
    if dept_code:
        query["deptCode"] = dept_code

    col = db.col("alert_records")
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": {
                "time": {"$dateToString": {"format": fmt, "date": "$created_at"}},
                "severity": "$severity",
            },
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.time": 1}},
    ]

    timeline: dict[str, dict] = {}
    cursor = await col.aggregate(pipeline)
    async for doc in cursor:
        t = str(doc.get("_id", {}).get("time") or "")
        if not t:
            continue
        sev = str(doc.get("_id", {}).get("severity") or "")
        cnt = int(doc.get("count", 0) or 0)
        if t not in timeline:
            timeline[t] = {"time": t, "total": 0, "warning": 0, "high": 0, "critical": 0}
        timeline[t]["total"] += cnt
        if sev in ("warning", "high", "critical"):
            timeline[t][sev] += cnt

    series = sorted(timeline.values(), key=lambda x: x["time"])
    return {
        "code": 0,
        "window": window,
        "bucket": bucket_norm,
        "series": series,
    }


@app.get("/api/alerts/analytics/heatmap")
async def alerts_analytics_heatmap(
    window: str = Query("7d", description="时间窗口"),
    top_n: int = Query(12, ge=3, le=30, description="规则类型数量"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    """按规则类型+小时分布生成热力图"""
    hours = _window_to_hours(window, default=168)
    since = datetime.utcnow() - timedelta(hours=hours)
    match_query: dict = {"created_at": {"$gte": since}}
    if dept:
        match_query["dept"] = dept
    if dept_code:
        match_query["deptCode"] = dept_code

    col = db.col("alert_records")
    rule_expr = {"$ifNull": ["$alert_type", {"$ifNull": ["$category", {"$ifNull": ["$rule_id", "unknown"]}]}]}

    pipeline_top = [
        {"$match": match_query},
        {"$group": {"_id": rule_expr, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]
    top_rules: list[str] = []
    cursor_top = await col.aggregate(pipeline_top)
    async for doc in cursor_top:
        top_rules.append(str(doc.get("_id") or "unknown"))

    if not top_rules:
        return {
            "code": 0,
            "window": window,
            "x_labels": [f"{h:02d}" for h in range(24)],
            "y_labels": [],
            "data": [],
        }

    pipeline = [
        {"$match": match_query},
        {"$project": {
            "rule_type": rule_expr,
            "hour": {"$hour": "$created_at"},
        }},
        {"$match": {"rule_type": {"$in": top_rules}}},
        {"$group": {
            "_id": {"rule_type": "$rule_type", "hour": "$hour"},
            "count": {"$sum": 1},
        }},
    ]

    heatmap_data: list[list[int]] = []
    y_index = {rule: idx for idx, rule in enumerate(top_rules)}
    cursor = await col.aggregate(pipeline)
    async for doc in cursor:
        obj = doc.get("_id", {})
        rule = str(obj.get("rule_type") or "unknown")
        hour = int(obj.get("hour", 0) or 0)
        count = int(doc.get("count", 0) or 0)
        if rule not in y_index or hour < 0 or hour > 23:
            continue
        heatmap_data.append([hour, y_index[rule], count])

    return {
        "code": 0,
        "window": window,
        "x_labels": [f"{h:02d}" for h in range(24)],
        "y_labels": top_rules,
        "data": heatmap_data,
    }


@app.get("/api/alerts/analytics/rankings")
async def alerts_analytics_rankings(
    window: str = Query("7d", description="时间窗口"),
    top_n: int = Query(10, ge=3, le=30, description="排名数量"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    """按科室/床位统计高频预警来源"""
    hours = _window_to_hours(window, default=168)
    since = datetime.utcnow() - timedelta(hours=hours)
    match_query: dict = {"created_at": {"$gte": since}}
    if dept:
        match_query["dept"] = dept
    if dept_code:
        match_query["deptCode"] = dept_code

    col = db.col("alert_records")

    dept_pipeline = [
        {"$match": match_query},
        {"$group": {
            "_id": {"$ifNull": ["$dept", "未知科室"]},
            "count": {"$sum": 1},
            **_severity_projection(),
        }},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]

    dept_rankings: list[dict] = []
    dept_cursor = await col.aggregate(dept_pipeline)
    async for doc in dept_cursor:
        dept_rankings.append({
            "dept": str(doc.get("_id") or "未知科室"),
            "count": int(doc.get("count", 0) or 0),
            "warning": int(doc.get("warning", 0) or 0),
            "high": int(doc.get("high", 0) or 0),
            "critical": int(doc.get("critical", 0) or 0),
        })

    bed_pipeline = [
        {"$match": match_query},
        {"$project": {
            "dept": {"$ifNull": ["$dept", "未知科室"]},
            "bed": {"$ifNull": ["$bed", "未标注床位"]},
            "severity": "$severity",
        }},
        {"$group": {
            "_id": {"dept": "$dept", "bed": "$bed"},
            "count": {"$sum": 1},
            **_severity_projection(),
        }},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]

    bed_rankings: list[dict] = []
    bed_cursor = await col.aggregate(bed_pipeline)
    async for doc in bed_cursor:
        key = doc.get("_id", {})
        bed_rankings.append({
            "dept": str(key.get("dept") or "未知科室"),
            "bed": str(key.get("bed") or "未标注床位"),
            "count": int(doc.get("count", 0) or 0),
            "warning": int(doc.get("warning", 0) or 0),
            "high": int(doc.get("high", 0) or 0),
            "critical": int(doc.get("critical", 0) or 0),
        })

    return {
        "code": 0,
        "window": window,
        "dept_rankings": dept_rankings,
        "bed_rankings": bed_rankings,
    }


# =============================================
# AI 辅助接口
# =============================================
@app.get("/api/ai/lab-summary/{patient_id}")
async def ai_lab_summary(patient_id: str):
    """AI分析患者近期检验异常"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    # 获取患者信息
    patient = await db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    # 获取近期检验
    patient_ids = _patient_his_pid_candidates(patient)
    exams = []
    if patient_ids:
        his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
        cursor = db.dc_col("VI_ICU_EXAM_ITEM").find(
            his_pid_query
        ).sort("authTime", -1).limit(300)
        item_docs = [doc async for doc in cursor]
        if not item_docs:
            _, item_docs = await _fetch_dc_exam_items_by_his_pid(
                patient_ids, limit_exams=40, limit_items=300
            )
        exams = [serialize_doc(doc) for doc in item_docs[:120]]

    if not exams:
        return {"code": 0, "summary": "暂无检验数据，无法生成摘要。"}

    exam_text = json.dumps(exams[:30], ensure_ascii=False, default=str)
    system_prompt = (
        "你是ICU临床检验分析专家。请分析以下患者近期检验结果，"
        "重点关注异常指标，给出临床解读和建议。用中文回答，简洁专业。"
    )
    user_prompt = (
        f"患者: {patient.get('name', '未知')}，"
        f"诊断: {patient.get('clinicalDiagnosis', patient.get('admissionDiagnosis', '未知'))}\n"
        f"近期检验数据:\n{exam_text}"
    )

    try:
        cfg = get_config()
        summary = await _call_llm(system_prompt, user_prompt, cfg.llm_model_medical)
        return {"code": 0, "summary": summary}
    except Exception as e:
        logger.error(f"AI lab summary error: {e}")
        return {"code": 0, "summary": "", "error": f"AI服务异常: {str(e)[:100]}"}


@app.get("/api/ai/rule-recommendations/{patient_id}")
async def ai_rule_recommendations(patient_id: str):
    """AI 根据患者病情推荐预警规则"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    system_prompt = (
        "你是ICU预警规则专家。根据患者诊断和当前状态，"
        "推荐个性化的监测指标和预警阈值。输出JSON数组格式，"
        "每条规则包含: parameter(参数名), operator(>/<), threshold(阈值), "
        "severity(warning/high/critical), reason(理由)。用中文回答。"
    )
    user_prompt = (
        f"患者: {patient.get('name', '未知')}\n"
        f"诊断: {patient.get('clinicalDiagnosis', patient.get('admissionDiagnosis', '未知'))}\n"
        f"护理级别: {patient.get('nursingLevel', '未知')}\n"
        f"请推荐针对性预警规则。"
    )

    try:
        text = await _call_llm(system_prompt, user_prompt)
        return {"code": 0, "recommendations": text}
    except Exception as e:
        logger.error(f"AI rule recommendations error: {e}")
        return {"code": 0, "recommendations": "", "error": f"AI服务异常: {str(e)[:100]}"}


@app.get("/api/ai/risk-forecast/{patient_id}")
async def ai_risk_forecast(patient_id: str):
    """AI 恶化风险预测"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    # 收集最近生命体征
    vitals = []
    pid_str = str(pid)
    codes = ["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_T"]
    snapshot = await _latest_params_by_pid(pid_str, codes)
    if not snapshot:
        device_id = await _get_device_id(pid_str, "monitor")
        snapshot = await _latest_params_by_device(device_id, codes) if device_id else None
    if snapshot:
        t = snapshot.get("time")
        vitals.append({
            "time": t.isoformat() if isinstance(t, datetime) else str(t),
            "HR": snapshot.get("params", {}).get("param_HR"),
            "SpO2": snapshot.get("params", {}).get("param_spo2"),
            "RR": snapshot.get("params", {}).get("param_resp"),
            "SBP": snapshot.get("params", {}).get("param_nibp_s") or snapshot.get("params", {}).get("param_ibp_s"),
            "T": snapshot.get("params", {}).get("param_T"),
        })

    vitals_text = json.dumps(vitals[:5], ensure_ascii=False, default=str) if vitals else "无监护数据"

    system_prompt = (
        "你是ICU临床决策支持专家。根据患者的诊断、生命体征趋势、"
        "ICU住院天数等信息，评估未来24小时内的恶化风险。"
        "输出风险等级(低/中/高/极高)、主要风险因素、建议监测重点。用中文回答。"
    )
    user_prompt = (
        f"患者: {patient.get('name', '未知')}\n"
        f"诊断: {patient.get('clinicalDiagnosis', patient.get('admissionDiagnosis', '未知'))}\n"
        f"ICU入科时间: {patient.get('icuAdmissionTime', '未知')}\n"
        f"近期生命体征:\n{vitals_text}"
    )

    try:
        cfg = get_config()
        text = await _call_llm(system_prompt, user_prompt, cfg.llm_model_medical)
        return {"code": 0, "risk_summary": text}
    except Exception as e:
        logger.error(f"AI risk forecast error: {e}")
        return {"code": 0, "risk_summary": "", "error": f"AI服务异常: {str(e)[:100]}"}


# =============================================
# WebSocket 预警推送
# =============================================
@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await ws_mgr.connect(ws)
    try:
        while True:
            # 客户端可发心跳 {"type":"ping"}
            data = await ws.receive_text()
            msg = json.loads(data) if data else {}
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_mgr.disconnect(ws)
    except Exception:
        await ws_mgr.disconnect(ws)
