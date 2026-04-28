from __future__ import annotations

import logging
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.config import get_config
from app.alert_engine.scanner_beta_blocker_advisor import BetaBlockerAdvisorScanner
from app.alert_engine.scanner_fibrinolysis_monitor import FibrinolysisMonitorScanner
from app.alert_engine.scanner_integrated_risk_reasoning import IntegratedRiskReasoningScanner
from app.alert_engine.scanner_metabolic_phase_detector import MetabolicPhaseDetectorScanner
from app.alert_engine.scanner_pics_risk import PicsRiskScanner
from app.alert_engine.scanner_prone_position_monitor import PronePositionMonitorScanner
from app.services.clinical_knowledge_graph import ClinicalKnowledgeGraph
from app.services.clinical_reasoning_agent import ClinicalReasoningAgent
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


def _fallback_metabolic_phase_record(patient: dict, patient_id: str, error: str | None = None) -> dict:
    now = datetime.now()
    weight = None
    for key in ("weight", "bodyWeight", "body_weight", "weightKg", "weight_kg"):
        try:
            if patient.get(key):
                weight = float(patient.get(key))
                break
        except Exception:
            continue
    weight = weight if weight and weight > 0 else 60.0
    kcal = [15, 20]
    protein = [0.8, 1.2]
    return {
        "patient_id": patient_id,
        "patient_name": patient.get("name") or "",
        "bed": patient.get("hisBed") or patient.get("bed") or "",
        "dept": patient.get("dept") or patient.get("hisDept") or "",
        "score_type": "metabolic_phase_detector",
        "phase": "insufficient_data",
        "phase_label": "数据不足，需床旁确认",
        "phase_scores": {"ebb": 0, "transition": 0, "anabolic": 0},
        "phase_features": {},
        "nutrition_target": {
            "kcal": kcal,
            "protein": protein,
            "estimated_daily_kcal": [round(weight * kcal[0]), round(weight * kcal[1])],
            "estimated_daily_protein": [round(weight * protein[0], 1), round(weight * protein[1], 1)],
        },
        "nutrition_mismatch": {
            "trigger": False,
            "evidence": ["当前缺少足够的代谢阶段评分数据，暂按保守营养目标展示。"],
            "recommendation": "建议补充/核对体重、乳酸、血糖波动、CRP/前白蛋白、SOFA、血管活性药和近24小时热卡/蛋白供给后重新生成。",
        },
        "state": {"weight_kg": weight, "fallback": True},
        "calc_time": now,
        "updated_at": now,
        "degraded": True,
        "error": error or "metabolic phase scanner returned no record",
        "disclaimer": "仅供临床决策支持，不替代医生判断。",
    }


def _fallback_fibrinolysis_record(patient: dict, patient_id: str, error: str | None = None) -> dict:
    now = datetime.now()
    return {
        "patient_id": patient_id,
        "patient_name": patient.get("name") or "",
        "bed": patient.get("hisBed") or patient.get("bed") or "",
        "dept": patient.get("dept") or patient.get("hisDept") or "",
        "score_type": "fibrinolysis_monitor",
        "assessment": {
            "phenotype": "insufficient_data",
            "score": 0,
            "severity": "low",
            "labs": {
                "d_dimer": None,
                "fdp": None,
                "fibrinogen": None,
                "platelet": None,
                "pt": None,
                "aptt": None,
            },
            "lysis_marker": {"ly30": None, "ml": None},
            "bleeding_context": "unknown",
            "sepsis_context": "unknown",
            "evidence": [
                "当前缺少足够的凝血/纤溶证据，暂不能可靠区分高纤溶、纤溶关闭或混合表型。",
                "建议补充或核对 TEG/ROTEM LY30/ML、D-dimer、FDP、纤维蛋白原、血小板、PT/APTT 及活动性出血/感染背景。",
            ],
            "recommendation": "请结合床旁出血表现、血栓风险、感染/休克状态和动态凝血结果复核；系统仅提示需补充证据，不生成强制医嘱。",
            "safety_notice": "仅供临床决策支持，不替代医生判断。",
        },
        "calc_time": now,
        "updated_at": now,
        "degraded": True,
        "error": error or "fibrinolysis monitor scanner returned no record",
        "disclaimer": "仅供临床决策支持，不替代医生判断。",
    }


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


@router.get("/api/ai/integrated-risk/{patient_id}")
async def ai_integrated_risk_report(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh:
            record = await runtime.db.col("integrated_risk_reports").find_one(
                {"patient_id": str(pid)},
                sort=[("created_at", -1)],
            )
        if not record:
            scanner = IntegratedRiskReasoningScanner(runtime.alert_engine)
            reports = await scanner.scan(str(pid))
            record = reports[0] if reports else await runtime.db.col("integrated_risk_reports").find_one(
                {"patient_id": str(pid)},
                sort=[("created_at", -1)],
            )
        return {"code": 0, "report": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI integrated risk error: %s", exc)
        return {"code": 0, "report": None, "error": f"综合风险推理异常: {str(exc)[:120]}"}


@router.get("/api/ai/metabolic-phase/{patient_id}")
async def ai_metabolic_phase(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh:
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "metabolic_phase_detector"},
                sort=[("calc_time", -1)],
            )
        scanner_error = ""
        if not record:
            try:
                scanner = MetabolicPhaseDetectorScanner(runtime.alert_engine)
                await scanner.scan(str(pid))
                record = await runtime.db.col("score").find_one(
                    {"patient_id": str(pid), "score_type": "metabolic_phase_detector"},
                    sort=[("calc_time", -1)],
                )
            except Exception as scan_exc:
                scanner_error = str(scan_exc)[:160]
                logger.warning("metabolic phase scanner degraded patient_id=%s error=%s", patient_id, scanner_error)
        if not record:
            record = _fallback_metabolic_phase_record(patient, str(pid), scanner_error or None)
        return {"code": 0, "record": serialize_doc(record), "error": scanner_error}
    except Exception as exc:
        logger.error("AI metabolic phase error: %s", exc)
        return {
            "code": 0,
            "record": serialize_doc(_fallback_metabolic_phase_record(patient, str(pid), str(exc)[:160])),
            "error": f"代谢阶段检测异常，已展示基础兜底评估: {str(exc)[:120]}",
        }


@router.get("/api/ai/beta-blocker-advisor/{patient_id}")
async def ai_beta_blocker_advisor(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh:
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "beta_blocker_advisor"},
                sort=[("calc_time", -1)],
            )
        if not record:
            scanner = BetaBlockerAdvisorScanner(runtime.alert_engine)
            await scanner.scan(str(pid))
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "beta_blocker_advisor"},
                sort=[("calc_time", -1)],
            )
        return {"code": 0, "record": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI beta blocker advisor error: %s", exc)
        return {"code": 0, "record": None, "error": f"β受体阻滞剂辅助决策异常: {str(exc)[:120]}"}


@router.get("/api/ai/fibrinolysis-monitor/{patient_id}")
async def ai_fibrinolysis_monitor(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh:
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "fibrinolysis_monitor"},
                sort=[("calc_time", -1)],
            )
        scanner_error = ""
        if not record:
            try:
                scanner = FibrinolysisMonitorScanner(runtime.alert_engine)
                await scanner.scan(str(pid))
                record = await runtime.db.col("score").find_one(
                    {"patient_id": str(pid), "score_type": "fibrinolysis_monitor"},
                    sort=[("calc_time", -1)],
                )
            except Exception as scan_exc:
                scanner_error = str(scan_exc)[:160]
                logger.warning("fibrinolysis monitor scanner degraded patient_id=%s error=%s", patient_id, scanner_error)
        if not record:
            record = _fallback_fibrinolysis_record(patient, str(pid), scanner_error or None)
        return {"code": 0, "record": serialize_doc(record), "error": scanner_error}
    except Exception as exc:
        logger.error("AI fibrinolysis monitor error: %s", exc)
        return {
            "code": 0,
            "record": serialize_doc(_fallback_fibrinolysis_record(patient, str(pid), str(exc)[:160])),
            "error": f"纤溶功能监测异常，已展示基础兜底评估: {str(exc)[:120]}",
        }


@router.get("/api/ai/prone-position/{patient_id}")
async def ai_prone_position_monitor(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh:
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "prone_position_monitor"},
                sort=[("calc_time", -1)],
            )
        if not record:
            scanner = PronePositionMonitorScanner(runtime.alert_engine)
            await scanner.scan(str(pid))
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "prone_position_monitor"},
                sort=[("calc_time", -1)],
            )
        return {"code": 0, "record": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI prone position monitor error: %s", exc)
        return {"code": 0, "record": None, "error": f"俯卧位治疗监测异常: {str(exc)[:120]}"}


@router.get("/api/ai/pics-risk/{patient_id}")
async def ai_pics_risk(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        record = None
        if not refresh:
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "pics_risk_assessment"},
                sort=[("calc_time", -1)],
            )
        if not record:
            scanner = PicsRiskScanner(runtime.alert_engine)
            await scanner.scan(str(pid))
            record = await runtime.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": "pics_risk_assessment"},
                sort=[("calc_time", -1)],
            )
        return {"code": 0, "record": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI pics risk error: %s", exc)
        return {"code": 0, "record": None, "error": f"PICS 风险预警异常: {str(exc)[:120]}"}


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
