"""
ICU智能预警系统 - FastAPI 主入口 (v2 - 专业临床界面)
"""
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId

from app.config import get_config
from app.database import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("icu-alert")

config = get_config()
db = DatabaseManager(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ICU智能预警系统 v2 启动中...")
    await db.connect()
    yield
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


@app.get("/health")
async def health_check():
    return {
        "status": "running",
        "version": "2.0.0",
        "smartcare": "connected" if db.smartcare_db else "disconnected",
        "datacenter": "connected" if db.datacenter_db else "disconnected",
        "redis": "connected" if db.redis else "disconnected",
    }
