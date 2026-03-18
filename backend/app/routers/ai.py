from __future__ import annotations

import json
import logging
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.config import get_config
from app.utils.api_llm import call_api_llm
from app.utils.patient_data import fetch_dc_exam_items_by_his_pid
from app.utils.patient_helpers import patient_his_pid_candidates
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


@router.get("/api/patients/{patient_id}/handoff-summary")
async def patient_handoff_summary(patient_id: str):
    """AI 交班摘要（I-PASS）"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        cfg = get_config()
        similar_case_review = await runtime.alert_engine.get_similar_case_outcomes(patient, limit=5)
        nursing_context = (
            await runtime.alert_engine._collect_nursing_context(patient, str(pid), hours=12)
            if hasattr(runtime.alert_engine, "_collect_nursing_context")
            else None
        )
        result = await runtime.ai_handoff_service.generate(
            patient_id=str(pid),
            patient_doc=patient,
            similar_case_review=similar_case_review,
            nursing_context=nursing_context,
            llm_call=call_api_llm,
            model=cfg.llm_model_medical or None,
        )
        return {
            "code": 0,
            "summary": serialize_doc(result.get("summary") or {}),
            "context_snapshot": serialize_doc(result.get("context_snapshot") or {}),
        }
    except Exception as exc:
        logger.error("AI handoff summary error: %s", exc)
        return {"code": 0, "summary": {}, "error": f"AI服务异常: {str(exc)[:120]}"}


@router.post("/api/ai/feedback")
async def ai_feedback(payload: dict = Body(...)):
    """记录AI输出事后反馈，用于准确率闭环。"""
    prediction_id = str(payload.get("prediction_id") or "").strip()
    outcome = str(payload.get("outcome") or "").strip().lower()
    module = str(payload.get("module") or "ai_risk").strip() or "ai_risk"
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}

    if not prediction_id:
        return {"code": 400, "message": "prediction_id不能为空"}
    if outcome not in {"confirmed", "dismissed", "inaccurate"}:
        return {"code": 400, "message": "outcome必须为 confirmed/dismissed/inaccurate"}

    try:
        await runtime.ai_monitor.log_prediction_feedback(
            module=module,
            prediction_id=prediction_id,
            outcome=outcome,
            detail=detail,
        )
    except Exception as exc:
        logger.error("AI feedback log error: %s", exc)

    oid = safe_oid(prediction_id)
    if oid is not None:
        try:
            await runtime.db.col("alert_records").update_one(
                {"_id": oid},
                {
                    "$set": {
                        "ai_feedback.outcome": outcome,
                        "ai_feedback.detail": detail,
                        "ai_feedback.updated_at": datetime.now(),
                    }
                },
            )
        except Exception as exc:
            logger.error("AI feedback alert update error: %s", exc)

    return {"code": 0, "prediction_id": prediction_id, "outcome": outcome}


@router.get("/api/ai/monitor/summary")
async def ai_monitor_summary(date: str | None = Query(default=None)):
    """AI调用监控汇总（含日聚合与活跃告警）。"""
    try:
        summary = await runtime.ai_monitor.get_daily_summary(date=date)
        return {
            "code": 0,
            "date": summary.get("date") or date or datetime.now().strftime("%Y-%m-%d"),
            "stats": [serialize_doc(item) for item in summary.get("stats", [])],
            "active_alerts": [serialize_doc(item) for item in summary.get("active_alerts", [])],
        }
    except Exception as exc:
        logger.error("AI monitor summary error: %s", exc)
        return {
            "code": 0,
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "stats": [],
            "active_alerts": [],
            "error": f"监控汇总异常: {str(exc)[:120]}",
        }


@router.get("/api/ai/rule-recommendations/{patient_id}")
async def ai_rule_recommendations(patient_id: str):
    """AI 根据患者病情推荐预警规则"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
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
        text = await call_api_llm(system_prompt, user_prompt)
        return {"code": 0, "recommendations": text}
    except Exception as exc:
        logger.error("AI rule recommendations error: %s", exc)
        return {"code": 0, "recommendations": "", "error": f"AI服务异常: {str(exc)[:100]}"}


@router.get("/api/ai/risk-forecast/{patient_id}")
async def ai_risk_forecast(patient_id: str):
    """AI 恶化风险预测"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        forecast = await runtime.alert_engine._build_temporal_risk_forecast(
            patient,
            pid,
            lookback_hours=12,
            horizons=(4, 8, 12),
            include_history=True,
        )
        return {
            "code": 0,
            "risk_summary": forecast.get("summary") or "",
            "risk_level": forecast.get("risk_level") or "low",
            "current_probability": forecast.get("current_probability") or 0,
            "horizon_probabilities": forecast.get("horizon_probabilities") or [],
            "risk_curve": forecast.get("risk_curve") or [],
            "history_risk_curve": forecast.get("history_risk_curve") or [],
            "forecast_risk_curve": forecast.get("forecast_risk_curve") or [],
            "threshold_bands": forecast.get("threshold_bands") or [],
            "high_risk_zone": forecast.get("high_risk_zone") or {},
            "top_contributors": forecast.get("top_contributors") or [],
            "organ_risk_scores": forecast.get("organ_risk_scores") or {},
            "organ_risk_curves": forecast.get("organ_risk_curves") or {},
            "model_meta": forecast.get("model_meta") or {},
        }
    except Exception as exc:
        logger.error("AI risk forecast error: %s", exc)
        return {"code": 0, "risk_summary": "", "error": f"AI服务异常: {str(exc)[:100]}"}


@router.get("/api/ai/lab-summary/{patient_id}")
async def ai_lab_summary(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    exams = []
    patient_ids = patient_his_pid_candidates(patient)
    if patient_ids:
        his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
        cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(300)
        item_docs = [doc async for doc in cursor]
        if not item_docs:
            _, item_docs = await fetch_dc_exam_items_by_his_pid(patient_ids, limit_exams=40, limit_items=300)
        exams = [serialize_doc(doc) for doc in item_docs[:120]]

    if not exams:
        return {"code": 0, "summary": "暂无检验数据，无法生成摘要。"}

    system_prompt = "你是ICU临床检验分析专家。请分析以下患者近期检验结果，重点关注异常指标，给出临床解读和建议。用中文回答，简洁专业。"
    user_prompt = (
        f"患者: {patient.get('name', '未知')}，"
        f"诊断: {patient.get('clinicalDiagnosis', patient.get('admissionDiagnosis', '未知'))}\n"
        f"近期检验数据:\n{json.dumps(exams[:30], ensure_ascii=False, default=str)}"
    )
    try:
        cfg = get_config()
        summary = await call_api_llm(system_prompt, user_prompt, cfg.llm_model_medical)
        return {"code": 0, "summary": summary}
    except Exception as exc:
        logger.error("AI lab summary error: %s", exc)
        return {"code": 0, "summary": "", "error": f"AI服务异常: {str(exc)[:100]}"}
