"""
ICU智能预警系统 - FastAPI 主入口 (v2 - 专业临床界面)
"""
import asyncio
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId
import httpx

from app.config import get_config
from app.database import DatabaseManager
from app.ws_manager import WebSocketManager
from app.alert_engine import AlertEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("icu-alert")

config = get_config()
db = DatabaseManager(config)
ws_manager = WebSocketManager()
alert_engine = AlertEngine(db, config, ws_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ICU智能预警系统 v2 启动中...")
    await db.connect()
    await alert_engine.start()
    yield
    await alert_engine.stop()
    await db.disconnect()
    logger.info("ICU智能预警系统已关闭")


app = FastAPI(title="ICU智能预警系统", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
#  WebSocket
# ============================================================

@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
    except Exception:
        await ws_manager.disconnect(ws)


# ============================================================
#  工具函数
# ============================================================

def serialize_doc(doc: dict) -> dict:
    if doc is None:
        return {}
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, list):
            result[k] = [
                serialize_doc(i) if isinstance(i, dict)
                else str(i) if isinstance(i, ObjectId)
                else i
                for i in v
            ]
        elif isinstance(v, dict):
            result[k] = serialize_doc(v)
        else:
            result[k] = v
    return result


def calc_age(birthday) -> str:
    if not birthday:
        return ""
    try:
        if isinstance(birthday, datetime):
            bd = birthday
        else:
            bd = datetime.fromisoformat(str(birthday).replace("Z", "+00:00"))
        today = datetime.now()
        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        if age == 0:
            days = (today - bd.replace(tzinfo=None)).days
            if days < 30:
                return f"{days}天"
            return f"{days // 30}月"
        return f"{age}岁"
    except Exception:
        return ""


def calc_icu_days(icu_time) -> int:
    if not icu_time:
        return -1
    try:
        if isinstance(icu_time, str):
            icu_time = datetime.fromisoformat(icu_time)
        return (datetime.now() - icu_time.replace(tzinfo=None)).days
    except Exception:
        return -1


def parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def safe_object_id(value) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def parse_window(window: str) -> tuple[timedelta, str]:
    w = (window or "24h").lower().strip()
    if w.endswith("h"):
        try:
            hours = int(w[:-1])
            return timedelta(hours=hours), f"{hours}h"
        except Exception:
            pass
    if w.endswith("d"):
        try:
            days = int(w[:-1])
            return timedelta(days=days), f"{days}d"
        except Exception:
            pass
    return timedelta(hours=24), "24h"


async def fetch_patient(patient_id: str) -> tuple[dict | None, list]:
    oid = safe_object_id(patient_id)
    patient = None
    if oid:
        patient = await db.col("patient").find_one({"_id": oid})
    if not patient:
        patient = await db.col("patient").find_one({"_id": patient_id})
    pid_candidates = [patient_id]
    if oid:
        pid_candidates.append(oid)
    if patient and patient.get("_id") not in pid_candidates:
        pid_candidates.append(patient.get("_id"))
    return patient, pid_candidates


async def fetch_bind_device_id(pid_candidates: list) -> str | None:
    bind = await db.col("deviceBind").find_one(
        {"pid": {"$in": pid_candidates}, "unBindTime": None},
        {"deviceID": 1}
    )
    if not bind:
        return None
    return bind.get("deviceID")


async def call_llm(messages: list[dict[str, str]], model: str | None = None) -> dict[str, Any]:
    base = (config.settings.LLM_BASE_URL or "").rstrip("/")
    api_key = config.settings.LLM_API_KEY
    if not base:
        return {"error": "LLM_BASE_URL 未配置"}
    model_name = model or config.settings.LLM_MODEL
    if not model_name:
        return {"error": "LLM_MODEL 未配置"}

    ai_cfg = config.yaml_cfg.get("ai_service", {}).get("llm", {})
    timeout = int(ai_cfg.get("timeout", 60))
    temperature = float(ai_cfg.get("temperature", 0.1))
    max_tokens = int(ai_cfg.get("max_tokens", 1024))

    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {"content": content}
    except Exception as e:
        return {"error": f"LLM 调用失败: {e}"}


def infer_clinical_tags(patient: dict, vitals: dict, nursing_level: str = "") -> list:
    """
    根据诊断、护理级别、生命体征推断临床标签
    返回 [{tag, label, color, icon}]
    """
    tags = []
    diag = (patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "").lower()
    nursing = (nursing_level or "").lower()

    # ── 呼吸机 (从诊断/呼吸衰竭推断, 后续可从设备数据获取) ──
    vent_keywords = ["呼吸衰竭", "呼吸机", "机械通气", "气管插管", "气管切开",
                     "ards", "呼吸窘迫", "肺性脑病"]
    if any(kw in diag for kw in vent_keywords):
        tags.append({"tag": "ventilator", "label": "呼吸机", "color": "#1890ff", "icon": "🫁"})

    # ── CRRT ──
    crrt_keywords = ["crrt", "肾功能不全", "肾衰", "肝肾综合征", "血液滤过", "血液净化",
                     "急性肾损伤", "aki"]
    if any(kw in diag for kw in crrt_keywords):
        tags.append({"tag": "crrt", "label": "CRRT", "color": "#722ed1", "icon": "🩸"})

    # ── 压疮风险 (Braden评分 / 长期卧床 / 高龄 / 意识障碍) ──
    pressure_keywords = ["压疮", "褥疮", "皮肤破损", "截瘫", "高位截瘫", "意识障碍",
                         "脑出血", "脑梗", "昏迷"]
    icu_days = calc_icu_days(patient.get("icuAdmissionTime"))
    if any(kw in diag for kw in pressure_keywords) or icu_days > 7:
        tags.append({"tag": "pressure_ulcer", "label": "压疮风险", "color": "#fa541c", "icon": "⚠"})

    # ── 感染/隔离 ──
    infection_keywords = ["败血症", "脓毒", "感染", "sepsis", "多重耐药", "mrsa",
                          "念珠菌", "真菌", "结核"]
    if any(kw in diag for kw in infection_keywords):
        tags.append({"tag": "infection", "label": "感染", "color": "#faad14", "icon": "🦠"})

    # ── 出血风险 ──
    bleed_keywords = ["出血", "消化道出血", "咯血", "血胸", "dic", "弥散性血管内凝血",
                      "凝血功能异常", "低纤维蛋白原"]
    if any(kw in diag for kw in bleed_keywords):
        tags.append({"tag": "bleeding", "label": "出血", "color": "#f5222d", "icon": "🩸"})

    # ── 意识障碍 ──
    conscious_keywords = ["意识障碍", "昏迷", "脑病", "脑出血", "缺氧缺血性脑病",
                          "脑血管意外"]
    if any(kw in diag for kw in conscious_keywords):
        tags.append({"tag": "consciousness", "label": "意识障碍", "color": "#595959", "icon": "🧠"})

    # ── 特级护理 ──
    if "特级" in nursing:
        tags.append({"tag": "special_care", "label": "特级护理", "color": "#eb2f96", "icon": "⭐"})

    # ── 多器官功能障碍 ──
    organ_count = 0
    organ_keywords_map = {
        "respiratory": ["呼吸衰竭", "ards"],
        "cardiac": ["心力衰竭", "心功能不全", "心肌梗死"],
        "renal": ["肾功能不全", "肾衰", "aki"],
        "hepatic": ["肝衰竭", "肝功能不全", "肝硬化失代偿"],
        "coag": ["dic", "凝血功能异常"],
        "neuro": ["意识障碍", "脑病", "昏迷"],
    }
    for sys, kws in organ_keywords_map.items():
        if any(kw in diag for kw in kws):
            organ_count += 1
    if organ_count >= 2:
        tags.append({"tag": "mods", "label": "MODS", "color": "#cf1322", "icon": "💀"})

    # ── 新生儿 ──
    neonatal_keywords = ["新生儿", "早产"]
    if any(kw in diag for kw in neonatal_keywords):
        tags.append({"tag": "neonatal", "label": "新生儿", "color": "#13c2c2", "icon": "👶"})

    # ── 术后 ──
    surgery_keywords = ["术后", "切除术", "手术后"]
    if any(kw in diag for kw in surgery_keywords):
        tags.append({"tag": "post_surgery", "label": "术后", "color": "#2f54eb", "icon": "🔪"})

    return tags


# ============================================================
#  API 接口
# ============================================================

@app.get("/api/departments")
async def get_departments():
    pipeline = [
        {"$match": {"status": "admitted"}},
        {"$group": {
            "_id": {
                "dept": {"$ifNull": ["$dept", "未知科室"]},
                "deptCode": {"$ifNull": ["$deptCode", ""]}
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    departments = []
    cursor = await db.col("patient").aggregate(pipeline)
    async for doc in cursor:
        departments.append({
            "dept": doc["_id"]["dept"],
            "deptCode": doc["_id"]["deptCode"],
            "patientCount": doc["count"]
        })
    return {"total_depts": len(departments), "departments": departments}


@app.get("/api/patients")
async def get_patients(
    dept: str = Query(default=None, description="科室名称"),
    dept_code: str = Query(default=None, description="科室代码")
):
    query = {"status": "admitted"}
    if dept:
        query["dept"] = dept
    elif dept_code:
        query["deptCode"] = dept_code

    patients = []
    cursor = db.col("patient").find(query).sort("hisBed", 1)
    async for p in cursor:
        doc = serialize_doc(p)
        doc["age"] = calc_age(p.get("birthday"))
        gender_map = {"Male": "男", "Female": "女"}
        doc["genderText"] = gender_map.get(doc.get("gender", ""), doc.get("gender", ""))
        icu_days = calc_icu_days(p.get("icuAdmissionTime"))
        doc["icuDays"] = icu_days if icu_days >= 0 else None
        # 临床标签推断
        doc["clinicalTags"] = infer_clinical_tags(p, {}, p.get("nursingLevel", ""))
        patients.append(doc)

    return {"count": len(patients), "dept_filter": dept or dept_code or "全部", "patients": patients}


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    try:
        oid = ObjectId(patient_id)
    except Exception:
        return {"error": "无效的患者ID"}

    p = await db.col("patient").find_one({"_id": oid})
    if not p:
        return {"error": "患者不存在"}

    doc = serialize_doc(p)
    doc["age"] = calc_age(p.get("birthday"))
    gender_map = {"Male": "男", "Female": "女"}
    doc["genderText"] = gender_map.get(doc.get("gender", ""), doc.get("gender", ""))
    icu_days = calc_icu_days(p.get("icuAdmissionTime"))
    doc["icuDays"] = icu_days if icu_days >= 0 else None
    doc["clinicalTags"] = infer_clinical_tags(p, {}, p.get("nursingLevel", ""))

    return {"patient": doc}


@app.get("/api/patients/{patient_id}/vitals")
async def get_patient_vitals(patient_id: str):
    try:
        oid = ObjectId(patient_id)
    except Exception:
        return {"error": "无效的患者ID"}

    patient = await db.col("patient").find_one({"_id": oid}, {"hisBed": 1, "name": 1})
    if not patient:
        return {"error": "患者不存在"}

    pid_candidates = [oid, patient_id]
    bind = await db.col("deviceBind").find_one(
        {"pid": {"$in": pid_candidates}, "unBindTime": None}, {"deviceID": 1}
    )

    vital_data = {}
    if bind and bind.get("deviceID"):
        latest_cap = await db.col("deviceCap").find_one(
            {"deviceID": bind["deviceID"]},
            sort=[("time", -1)]
        )
        if latest_cap:
            vital_data = {
                "source": "monitor",
                "time": str(latest_cap.get("time", "")),
                "hr": latest_cap.get("param_HR"),
                "rr": latest_cap.get("param_resp"),
                "spo2": latest_cap.get("param_spo2"),
                "temp": latest_cap.get("param_T"),
                "nibp_sys": latest_cap.get("param_nibp_s"),
                "nibp_dia": latest_cap.get("param_nibp_d"),
                "nibp_map": latest_cap.get("param_nibp_m"),
                "ibp_sys": latest_cap.get("param_ibp_s"),
                "ibp_dia": latest_cap.get("param_ibp_d"),
                "ibp_map": latest_cap.get("param_ibp_m"),
                "cvp": latest_cap.get("param_cvp"),
                "etco2": latest_cap.get("param_ETCO2"),
            }

    if not vital_data:
        latest_bedside = await db.col("bedside").find_one(
            {"pid": {"$in": pid_candidates}}, sort=[("recordTime", -1)]
        )
        if latest_bedside:
            vital_data = {
                "source": "nurse_manual",
                "time": str(latest_bedside.get("recordTime", "")),
                "data": serialize_doc(latest_bedside),
            }

    return {
        "patient_id": patient_id,
        "name": patient.get("name", ""),
        "bed": patient.get("hisBed", ""),
        "vitals": vital_data
    }


@app.get("/api/patients/{patient_id}/labs")
async def get_patient_labs(patient_id: str):
    try:
        oid = ObjectId(patient_id)
    except Exception:
        return {"error": "无效的患者ID"}

    patient = await db.col("patient").find_one({"_id": oid}, {"hisPid": 1, "name": 1})
    if not patient or "hisPid" not in patient:
        return {"error": "患者不存在或无HIS编号"}

    his_pid = patient["hisPid"]
    exams = []
    cursor = db.dc_col("VI_ICU_EXAM").find(
        {"hisPid": his_pid}
    ).sort("requestTime", -1).limit(10)

    async for exam in cursor:
        exam_doc = serialize_doc(exam)
        items = []
        item_cursor = db.dc_col("VI_ICU_EXAM_ITEM").find({
            "hisPid": his_pid,
            "requestId": exam.get("requestId")
        })
        async for item in item_cursor:
            items.append(serialize_doc(item))
        exam_doc["items"] = items
        exams.append(exam_doc)

    return {
        "patient_id": patient_id,
        "name": patient.get("name", ""),
        "his_pid": his_pid,
        "exams": exams
    }


@app.get("/api/patients/{patient_id}/vitals/trend")
async def get_patient_vitals_trend(
    patient_id: str,
    window: str = Query(default="24h", description="时间窗口: 24h/48h/7d")
):
    patient, pid_candidates = await fetch_patient(patient_id)
    if not patient:
        return {"error": "患者不存在"}

    device_id = await fetch_bind_device_id(pid_candidates)
    if not device_id:
        return {
            "patient_id": patient_id,
            "device_id": None,
            "window": window,
            "points": []
        }

    delta, window_key = parse_window(window)
    start = datetime.now() - delta

    cursor = db.col("deviceCap").find(
        {"deviceID": device_id, "time": {"$gte": start}},
        {
            "time": 1,
            "param_HR": 1,
            "param_resp": 1,
            "param_spo2": 1,
            "param_T": 1,
            "param_nibp_s": 1,
            "param_nibp_d": 1,
            "param_nibp_m": 1,
            "param_ibp_s": 1,
            "param_ibp_d": 1,
            "param_ibp_m": 1,
        }
    ).sort("time", 1).limit(5000)

    points = []
    async for doc in cursor:
        t = doc.get("time")
        if isinstance(t, datetime):
            t = t.isoformat()
        points.append({
            "time": t,
            "hr": doc.get("param_HR"),
            "rr": doc.get("param_resp"),
            "spo2": doc.get("param_spo2"),
            "temp": doc.get("param_T"),
            "nibp_sys": doc.get("param_nibp_s"),
            "nibp_dia": doc.get("param_nibp_d"),
            "nibp_map": doc.get("param_nibp_m"),
            "ibp_sys": doc.get("param_ibp_s"),
            "ibp_dia": doc.get("param_ibp_d"),
            "ibp_map": doc.get("param_ibp_m"),
        })

    return {
        "patient_id": patient_id,
        "device_id": device_id,
        "window": window_key,
        "points": points
    }


@app.get("/api/patients/{patient_id}/drugs")
async def get_patient_drugs(patient_id: str, limit: int = Query(100, ge=1, le=500)):
    patient, pid_candidates = await fetch_patient(patient_id)
    if not patient:
        return {"error": "患者不存在"}

    cursor = db.col("drugExe").find(
        {"pid": {"$in": pid_candidates}}
    ).sort("executeTime", -1).limit(limit)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    return {
        "patient_id": patient_id,
        "records": records
    }


@app.get("/api/patients/{patient_id}/assessments")
async def get_patient_assessments(patient_id: str, limit: int = Query(200, ge=1, le=500)):
    patient, pid_candidates = await fetch_patient(patient_id)
    if not patient:
        return {"error": "患者不存在"}

    assess_cfg = config.yaml_cfg.get("assessments", {})
    if "braden" not in assess_cfg:
        assess_cfg = {
            **assess_cfg,
            "braden": {"code": "param_score_braden", "name": "Braden评分"}
        }

    codes = [v.get("code") for v in assess_cfg.values() if v.get("code")]
    if not codes:
        return {"patient_id": patient_id, "records": []}

    or_query = [{code: {"$exists": True}} for code in codes]
    cursor = db.col("bedside").find(
        {"pid": {"$in": pid_candidates}, "$or": or_query}
    ).sort("recordTime", -1).limit(limit)

    records = []
    async for doc in cursor:
        item = {
            "time": serialize_doc({"t": doc.get("recordTime")}).get("t"),
        }
        for key, cfg in assess_cfg.items():
            code = cfg.get("code")
            if not code:
                continue
            item[key] = doc.get(code)
        records.append(item)

    return {
        "patient_id": patient_id,
        "records": records
    }


@app.get("/api/patients/{patient_id}/alerts")
async def get_patient_alerts(patient_id: str, limit: int = Query(100, ge=1, le=500)):
    oid = safe_object_id(patient_id)
    pid_candidates: list[Any] = [patient_id]
    if oid:
        pid_candidates.extend([str(oid), oid])

    cursor = db.col("alert_records").find(
        {"patient_id": {"$in": pid_candidates}}
    ).sort("created_at", -1).limit(limit)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    return {
        "patient_id": patient_id,
        "records": records
    }


@app.get("/api/alerts/recent")
async def get_recent_alerts(limit: int = Query(50, ge=1, le=200)):
    cursor = db.col("alert_records").find(
        {}
    ).sort("created_at", -1).limit(limit)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    return {
        "records": records
    }


@app.get("/api/alerts/stats")
async def get_alert_stats(window: str = Query(default="24h")):
    delta, window_key = parse_window(window)
    start = datetime.now() - delta

    pipeline = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$project": {
            "hour": {"$dateToString": {"format": "%Y-%m-%d %H:00", "date": "$created_at"}},
            "severity": 1
        }},
        {"$group": {
            "_id": {"hour": "$hour", "severity": "$severity"},
            "count": {"$sum": 1}
        }},
        {"$group": {
            "_id": "$_id.hour",
            "items": {"$push": {"severity": "$_id.severity", "count": "$count"}}
        }},
        {"$sort": {"_id": 1}}
    ]

    cursor = await db.col("alert_records").aggregate(pipeline)
    raw = [doc async for doc in cursor]

    series = []
    for doc in raw:
        row = {"time": doc["_id"], "warning": 0, "high": 0, "critical": 0}
        for item in doc.get("items", []):
            sev = item.get("severity") or "warning"
            row[sev] = item.get("count", 0)
        row["total"] = row["warning"] + row["high"] + row["critical"]
        series.append(row)

    return {
        "window": window_key,
        "series": series
    }


@app.get("/api/ai/lab-summary/{patient_id}")
async def ai_lab_summary(patient_id: str):
    patient, _ = await fetch_patient(patient_id)
    if not patient or "hisPid" not in patient:
        return {"error": "患者不存在或无HIS编号"}

    his_pid = patient["hisPid"]
    exam = await db.dc_col("VI_ICU_EXAM").find_one(
        {"hisPid": his_pid},
        sort=[("requestTime", -1)]
    )
    if not exam:
        return {"error": "暂无检验数据"}

    items = []
    item_cursor = db.dc_col("VI_ICU_EXAM_ITEM").find({
        "hisPid": his_pid,
        "requestId": exam.get("requestId")
    })
    async for item in item_cursor:
        items.append(serialize_doc(item))

    prompt = (
        f"患者: {patient.get('name','')} | 诊断: "
        f"{patient.get('clinicalDiagnosis') or patient.get('admissionDiagnosis') or ''}\n"
        f"最新检验(仅供分析): {items}\n"
        "请找出可能异常或成组异常的指标，给出简洁的临床摘要和建议关注点。"
    )
    messages = [
        {"role": "system", "content": "你是ICU临床智能助手，用中文回答，简洁明确。"},
        {"role": "user", "content": prompt}
    ]
    res = await call_llm(messages, model=config.settings.LLM_MODEL_MEDICAL or None)
    return {
        "patient_id": patient_id,
        "summary": res.get("content"),
        "error": res.get("error"),
        "exam": serialize_doc(exam)
    }


@app.get("/api/ai/rule-recommendations/{patient_id}")
async def ai_rule_recommendations(patient_id: str):
    patient, pid_candidates = await fetch_patient(patient_id)
    if not patient:
        return {"error": "患者不存在"}

    device_id = await fetch_bind_device_id(pid_candidates)
    latest_cap = None
    if device_id:
        latest_cap = await db.col("deviceCap").find_one(
            {"deviceID": device_id},
            sort=[("time", -1)]
        )

    prompt = (
        f"患者: {patient.get('name','')} | 诊断: "
        f"{patient.get('clinicalDiagnosis') or patient.get('admissionDiagnosis') or ''}\n"
        f"最新生命体征: {serialize_doc(latest_cap) if latest_cap else '无'}\n"
        "请根据诊断和体征，推荐应关注的预警规则(格式: 规则名, 参数, 阈值, 严重度)。"
    )
    messages = [
        {"role": "system", "content": "你是ICU临床智能助手，用中文回答，条目化输出。"},
        {"role": "user", "content": prompt}
    ]
    res = await call_llm(messages)
    return {
        "patient_id": patient_id,
        "recommendations": res.get("content"),
        "error": res.get("error")
    }


@app.get("/api/ai/risk-forecast/{patient_id}")
async def ai_risk_forecast(patient_id: str):
    trend = await get_patient_vitals_trend(patient_id, window="24h")
    if trend.get("error"):
        return trend
    points = trend.get("points", [])[-80:]

    prompt = (
        f"患者生命体征趋势(最近24h): {points}\n"
        "请根据趋势判断是否存在恶化风险，并给出简短理由与建议关注的指标。"
    )
    messages = [
        {"role": "system", "content": "你是ICU临床智能助手，用中文回答，简洁判断。"},
        {"role": "user", "content": prompt}
    ]
    res = await call_llm(messages)
    return {
        "patient_id": patient_id,
        "risk_summary": res.get("content"),
        "error": res.get("error")
    }


@app.get("/health")
async def health_check():
    return {
        "status": "running",
        "version": "2.0.0",
        "smartcare": "connected" if db.smartcare_db else "disconnected",
        "datacenter": "connected" if db.datacenter_db else "disconnected",
        "redis": "connected" if db.redis else "disconnected",
    }
