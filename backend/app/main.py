"""
ICU智能预警系统 - FastAPI 主应用
"""
import json
import logging
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
        {"$match": {"isLeave": {"$ne": True}}},
        {"$group": {
            "_id": {"$ifNull": ["$hisDept", "$dept"]},
            "patientCount": {"$sum": 1},
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"patientCount": -1}},
    ]
    departments = []
    async for doc in col.aggregate(pipeline):
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
    query: dict = {"isLeave": {"$ne": True}}
    if dept:
        query["$or"] = [{"hisDept": dept}, {"dept": dept}]
    elif dept_code:
        query["deptCode"] = dept_code

    col = db.col("patient")
    cursor = col.find(query).sort("hisBed", 1)
    patients = []
    async for doc in cursor:
        patients.append(serialize_doc(doc))
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

    # 优先从 bedside 查最新记录（监护仪实时数据）
    bedside_doc = await db.col("bedside").find_one(
        {"pid": pid},
        sort=[("recordTime", -1)],
    )
    if bedside_doc:
        params = bedside_doc.get("params", {})
        vitals = {
            "time": bedside_doc.get("recordTime").isoformat()
            if isinstance(bedside_doc.get("recordTime"), datetime)
            else str(bedside_doc.get("recordTime")),
            "hr": _pv(params, "param_HR"),
            "spo2": _pv(params, "param_spo2"),
            "rr": _pv(params, "param_resp"),
            "temp": _pv(params, "param_T"),
            "nibp_sys": _pv(params, "param_nibp_s"),
            "nibp_dia": _pv(params, "param_nibp_d"),
            "nibp_map": _pv(params, "param_nibp_m"),
            "ibp_sys": _pv(params, "param_ibp_s"),
            "ibp_dia": _pv(params, "param_ibp_d"),
            "ibp_map": _pv(params, "param_ibp_m"),
            "cvp": _pv(params, "param_cvp"),
            "etco2": _pv(params, "param_ETCO2"),
        }
    else:
        # 退回到 deviceCap（通过 deviceBind 关联）
        bind_doc = await db.col("deviceBind").find_one(
            {"pid": pid, "unBindTime": None}
        )
        if bind_doc:
            device_id = bind_doc.get("deviceID")
            cap_doc = await db.col("deviceCap").find_one(
                {"deviceID": device_id},
                sort=[("time", -1)],
            )
            if cap_doc:
                params = cap_doc.get("params", cap_doc)
                vitals = {
                    "time": cap_doc.get("time").isoformat()
                    if isinstance(cap_doc.get("time"), datetime)
                    else str(cap_doc.get("time")),
                    "hr": _pv(params, "param_HR"),
                    "spo2": _pv(params, "param_spo2"),
                    "rr": _pv(params, "param_resp"),
                    "temp": _pv(params, "param_T"),
                    "nibp_sys": _pv(params, "param_nibp_s"),
                    "nibp_dia": _pv(params, "param_nibp_d"),
                    "nibp_map": _pv(params, "param_nibp_m"),
                    "ibp_sys": _pv(params, "param_ibp_s"),
                    "ibp_dia": _pv(params, "param_ibp_d"),
                    "ibp_map": _pv(params, "param_ibp_m"),
                    "cvp": _pv(params, "param_cvp"),
                    "etco2": _pv(params, "param_ETCO2"),
                }

    return {"code": 0, "vitals": vitals}


# =============================================
# 检验结果
# =============================================
@app.get("/api/patients/{patient_id}/labs")
async def patient_labs(patient_id: str):
    """获取患者近期检验结果（从 DataCenter VI_ICU_EXAM_ITEM）"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    # 通过 patient.hisPid 关联到 DataCenter
    patient = await db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    his_pid = patient.get("hisPid")
    exams = []
    if his_pid:
        cursor = db.dc_col("VI_ICU_EXAM_ITEM").find(
            {"hisPid": his_pid}
        ).sort("requestTime", -1).limit(100)
        async for doc in cursor:
            exams.append(serialize_doc(doc))

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
    since = datetime.utcnow() - timedelta(hours=hours)

    # 优先从 bedside 查（监护仪实时数据）
    col = db.col("bedside")
    cursor = col.find(
        {"pid": pid, "recordTime": {"$gte": since}},
        {"recordTime": 1, "params": 1},
    ).sort("recordTime", 1)

    points = []
    async for doc in cursor:
        params = doc.get("params", {})
        points.append({
            "time": doc.get("recordTime"),
            "hr": _pv(params, "param_HR"),
            "spo2": _pv(params, "param_spo2"),
            "rr": _pv(params, "param_resp"),
            "temp": _pv(params, "param_T"),
            "nibp_sys": _pv(params, "param_nibp_s"),
            "nibp_dia": _pv(params, "param_nibp_d"),
            "nibp_map": _pv(params, "param_nibp_m"),
            "ibp_sys": _pv(params, "param_ibp_s"),
            "ibp_dia": _pv(params, "param_ibp_d"),
            "ibp_map": _pv(params, "param_ibp_m"),
        })

    # 如果监护仪无数据，退回到 deviceCap
    if not points:
        cap_col = db.col("deviceCap")
        cursor2 = cap_col.find(
            {"pid": pid, "time": {"$gte": since}},
            {"time": 1, "params": 1},
        ).sort("time", 1)
        async for doc in cursor2:
            params = doc.get("params", {})
            points.append({
                "time": doc.get("time"),
                "hr": _pv(params, "param_HR"),
                "spo2": _pv(params, "param_spo2"),
                "rr": _pv(params, "param_resp"),
                "temp": _pv(params, "param_T"),
                "nibp_sys": _pv(params, "param_nibp_s"),
                "nibp_dia": _pv(params, "param_nibp_d"),
                "nibp_map": _pv(params, "param_nibp_m"),
                "ibp_sys": _pv(params, "param_ibp_s"),
                "ibp_dia": _pv(params, "param_ibp_d"),
                "ibp_map": _pv(params, "param_ibp_m"),
            })

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
        {"pid": pid},
        {
            "drugName": 1, "dose": 1, "doseUnit": 1, "route": 1,
            "frequency": 1, "executeTime": 1, "status": 1,
            "orderType": 1, "drugSpec": 1,
        },
    ).sort("executeTime", -1).limit(50)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    return {"code": 0, "records": records}


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

    # 从 score_records 集合查
    col = db.col("score_records")
    cursor = col.find(
        {"patient_id": pid}
    ).sort("calc_time", -1).limit(50)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    # 如果score_records无数据，尝试从bedside提取评估参数
    if not records:
        bedside_col = db.col("bedside")
        cursor2 = bedside_col.find(
            {"pid": pid, "params.param_score_gcs_obs": {"$exists": True}},
            {"recordTime": 1, "params": 1},
        ).sort("recordTime", -1).limit(50)

        async for doc in cursor2:
            params = doc.get("params", {})
            records.append({
                "time": doc.get("recordTime").isoformat() if doc.get("recordTime") else None,
                "gcs": _pv(params, "param_score_gcs_obs"),
                "rass": _pv(params, "param_score_rass_obs"),
                "pain": _pv(params, "param_tengTong_score"),
                "delirium": _pv(params, "param_delirium_score"),
                "braden": None,  # 需要根据实际字段名补充
            })

    return {"code": 0, "records": records}


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
        {"patient_id": pid}
    ).sort("created_at", -1).limit(100)

    records = []
    async for doc in cursor:
        records.append(serialize_doc(doc))

    return {"code": 0, "records": records}


# =============================================
# 最近预警列表（大屏用）
# =============================================
@app.get("/api/alerts/recent")
async def recent_alerts(limit: int = Query(50, ge=1, le=200)):
    """获取全院最近的预警记录"""
    col = db.col("alert_records")
    cursor = col.find(
        {"is_active": True}
    ).sort("created_at", -1).limit(limit)

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
    async for doc in col.aggregate(pipeline):
        hour = doc["_id"]["hour"]
        sev = doc["_id"]["severity"]
        if hour not in results:
            results[hour] = {"time": hour, "warning": 0, "high": 0, "critical": 0}
        if sev in results[hour]:
            results[hour][sev] = doc["count"]

    series = sorted(results.values(), key=lambda x: x["time"])
    return {"code": 0, "series": series}


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
    his_pid = patient.get("hisPid")
    exams = []
    if his_pid:
        cursor = db.dc_col("VI_ICU_EXAM_ITEM").find(
            {"hisPid": his_pid}
        ).sort("requestTime", -1).limit(50)
        async for doc in cursor:
            exams.append(serialize_doc(doc))

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
    cursor = db.col("bedside").find(
        {"pid": pid}
    ).sort("recordTime", -1).limit(10)
    async for doc in cursor:
        vitals.append(serialize_doc(doc))

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
