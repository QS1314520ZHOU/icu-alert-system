from __future__ import annotations

import logging
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.config import get_config
from app.services.clinical_knowledge_graph import ClinicalKnowledgeGraph
from app.services.clinical_reasoning_agent import ClinicalReasoningAgent
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


@router.get("/api/ai/risk-forecast/{patient_id}")
async def ai_risk_forecast(patient_id: str):
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


@router.get("/api/ai/proactive-management/{patient_id}")
async def ai_proactive_management(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh and hasattr(runtime.alert_engine, "_latest_proactive_management_record"):
            record = await runtime.alert_engine._latest_proactive_management_record(str(pid), hours=24)
        if not record:
            plan = await runtime.alert_engine.continuous_risk_assessment(str(pid))
            if not plan:
                return {"code": 0, "plan": None}
            record = await runtime.alert_engine._persist_proactive_management_plan(patient, plan, datetime.now())
        return {"code": 0, "plan": serialize_doc(record)}
    except Exception as exc:
        logger.error("AI proactive management error: %s", exc)
        return {"code": 0, "plan": None, "error": f"主动管理方案生成异常: {str(exc)[:120]}"}


@router.post("/api/ai/proactive-management/{patient_id}/interventions/{intervention_id}/feedback")
async def ai_proactive_management_feedback(patient_id: str, intervention_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    record_id = safe_oid((payload or {}).get("record_id"))
    status = str((payload or {}).get("status") or "").strip().lower() or None
    adopted_value = (payload or {}).get("adopted")
    adopted = bool(adopted_value) if isinstance(adopted_value, bool) else None
    note = str((payload or {}).get("note") or "").strip() or None
    actor = str((payload or {}).get("actor") or "").strip() or None

    updated = await runtime.alert_engine.track_intervention_effectiveness(
        str(pid),
        intervention_id,
        record_id=record_id,
        status=status,
        adopted=adopted,
        note=note,
        actor=actor,
    )
    if not updated:
        return {"code": 404, "message": "未找到对应干预记录"}
    return {"code": 0, "record": serialize_doc(updated)}


@router.get("/api/ai/clinical-reasoning/{patient_id}")
async def ai_clinical_reasoning(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh:
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "clinical_reasoning_plan"},
                sort=[("calc_time", -1)],
            )
        if not record:
            agent = ClinicalReasoningAgent(
                db=runtime.db,
                config=get_config(),
                alert_engine=runtime.alert_engine,
                rag_service=runtime.ai_rag_service,
                ai_monitor=runtime.ai_monitor,
                ai_handoff_service=runtime.ai_handoff_service,
            )
            record = await agent.generate_individualized_plan(str(pid))
        return {"code": 0, "plan": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI clinical reasoning error: %s", exc)
        return {"code": 0, "plan": None, "error": f"个体化诊疗推理异常: {str(exc)[:120]}"}


@router.post("/api/ai/causal-analysis/{patient_id}")
async def ai_causal_analysis(patient_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    abnormal_finding = str((payload or {}).get("abnormal_finding") or "").strip()
    if not abnormal_finding:
        return {"code": 400, "message": "abnormal_finding不能为空"}

    service = ClinicalKnowledgeGraph(
        db=runtime.db,
        config=get_config(),
        alert_engine=runtime.alert_engine,
        rag_service=runtime.ai_rag_service,
    )
    try:
        result = await service.causal_chain_analysis(str(pid), abnormal_finding)
        return {"code": 0, "analysis": serialize_doc(result) if result else None}
    except Exception as exc:
        logger.error("AI causal analysis error: %s", exc)
        return {"code": 0, "analysis": None, "error": f"因果链分析异常: {str(exc)[:120]}"}


@router.get("/api/ai/intervention-effects")
async def ai_intervention_effects(intervention: str = Query(..., description="干预键名，例如 norepinephrine_high_dose")):
    service = ClinicalKnowledgeGraph(
        db=runtime.db,
        config=get_config(),
        alert_engine=runtime.alert_engine,
        rag_service=runtime.ai_rag_service,
    )
    try:
        result = await service.predict_downstream_effects(intervention)
        return {"code": 0, "prediction": serialize_doc(result)}
    except Exception as exc:
        logger.error("AI intervention effects error: %s", exc)
        return {"code": 0, "prediction": None, "error": f"干预影响预测异常: {str(exc)[:120]}"}


@router.get("/api/ai/nursing-note-signals/{patient_id}")
async def ai_nursing_note_signals(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh and hasattr(runtime.alert_engine, "latest_nursing_note_analysis"):
            record = await runtime.alert_engine.latest_nursing_note_analysis(str(pid), hours=24)
        if not record and hasattr(runtime.alert_engine, "analyze_nursing_notes"):
            record = await runtime.alert_engine.analyze_nursing_notes(patient, str(pid), hours=12, persist=True)
        return {"code": 0, "analysis": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI nursing note signals error: %s", exc)
        return {"code": 0, "analysis": None, "error": f"护理文本分析异常: {str(exc)[:120]}"}
