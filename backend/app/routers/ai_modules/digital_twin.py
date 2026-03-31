from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.config import get_config
from app.routers.ai_modules.common import (
    _build_metric_cards,
    _device_cap_series,
    _hours_from_window,
    _iso,
    _lab_series_by_keywords,
    _latest_metric,
    _merge_time_series,
    _parse_when,
    _persist_ai_score_record,
    _round_number,
    _safe_float,
    _serialize_nullable,
)
from app.services.counterfactual_model import SemiMechanisticCounterfactualModel
from app.services.multi_agent_orchestrator import ICUMultiAgentOrchestrator
from app.services.patient_digital_twin import PatientDigitalTwinService
from app.services.subphenotype_clustering import CohortSubphenotypeProfiler
from app.utils.patient_data import get_device_id, latest_params_by_device, param_series_by_pid
from app.utils.patient_helpers import patient_his_pid_candidates
from app.utils.serialization import serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


async def _build_hemodynamic_panel(patient_id: str, patient: dict, *, hours: int) -> dict:
    since = datetime.now() - timedelta(hours=hours)
    patient_ids = patient_his_pid_candidates(patient)
    map_series = await param_series_by_pid(patient_id, "param_nibp_m", since)
    ibp_map_series = await param_series_by_pid(patient_id, "param_ibp_m", since)
    hr_series = await param_series_by_pid(patient_id, "param_HR", since)
    lactate_series = await _lab_series_by_keywords(patient_ids, ["乳酸", "lactate", "lac"], since)
    merged_map_series = ibp_map_series if ibp_map_series else map_series
    trend_points = _merge_time_series({"map": merged_map_series, "hr": hr_series, "lactate": lactate_series}, bucket_hours=4 if hours > 24 else 2)

    drug_docs = await runtime.alert_engine._get_recent_drug_docs_window(patient_id, hours=hours, limit=1200)
    weight_kg = runtime.alert_engine._get_patient_weight(patient)
    vaso_keywords = {
        "去甲肾上腺素": ["去甲肾上腺素", "norepinephrine", "noradrenaline"],
        "肾上腺素": ["肾上腺素", "epinephrine", "adrenaline"],
        "多巴胺": ["多巴胺", "dopamine"],
        "多巴酚丁胺": ["多巴酚丁胺", "dobutamine"],
        "血管加压素": ["血管加压素", "vasopressin"],
        "去氧肾上腺素": ["去氧肾上腺素", "phenylephrine"],
    }
    vaso_events: list[dict] = []
    latest_by_drug: dict[str, dict] = {}
    for doc in drug_docs:
        text = " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName", "drugSpec", "route", "routeName", "orderType")).lower()
        matched_drug = next((label for label, keywords in vaso_keywords.items() if any(keyword.lower() in text for keyword in keywords)), None)
        if not matched_drug:
            continue
        event_time = _parse_when(doc.get("_event_time")) or _parse_when(doc.get("executeTime")) or _parse_when(doc.get("startTime")) or _parse_when(doc.get("orderTime"))
        if event_time is None or event_time < since:
            continue
        dose = runtime.alert_engine._extract_vasopressor_rate_ug_kg_min(doc, weight_kg)
        row = {
            "drug": matched_drug,
            "time": _iso(event_time),
            "dose_ug_kg_min": _round_number(dose, 3),
            "dose_display": f"{dose:.3f} μg/kg/min" if dose is not None else str(doc.get("dose") or doc.get("drugSpec") or "").strip() or None,
            "route": str(doc.get("routeName") or doc.get("route") or "").strip() or None,
            "frequency": str(doc.get("frequency") or "").strip() or None,
            "order_name": str(doc.get("orderName") or doc.get("drugName") or "").strip() or matched_drug,
        }
        vaso_events.append(row)
        latest_current = latest_by_drug.get(matched_drug)
        if latest_current is None or str(latest_current.get("time") or "") < str(row["time"] or ""):
            latest_by_drug[matched_drug] = row

    intake_events = await runtime.alert_engine._collect_intake_events(patient_id, since)
    output_events = await runtime.alert_engine._collect_output_events(patient_id, since)
    now = datetime.now()
    fluid_windows = []
    for window_hours in (6, 24, 72):
        if window_hours <= hours:
            intake_total = runtime.alert_engine._sum_window(intake_events, window_hours, now)
            output_total = runtime.alert_engine._sum_window(output_events, window_hours, now)
            fluid_windows.append({"label": f"{window_hours}h", "intake_ml": intake_total, "output_ml": output_total, "net_ml": round(intake_total - output_total, 1)})

    latest_map = _latest_metric(merged_map_series, digits=0)
    latest_hr = _latest_metric(hr_series, digits=0)
    latest_lactate = _latest_metric(lactate_series, digits=1)
    net24 = next((item for item in fluid_windows if item.get("label") == "24h"), None)
    summary_parts = []
    if latest_map and latest_map.get("value") is not None:
        summary_parts.append(f"MAP {int(latest_map['value'])} mmHg")
    if latest_hr and latest_hr.get("value") is not None:
        summary_parts.append(f"HR {int(latest_hr['value'])}/min")
    if latest_lactate and latest_lactate.get("value") is not None:
        summary_parts.append(f"乳酸 {latest_lactate['value']} mmol/L")
    if net24 and net24.get("net_ml") is not None:
        summary_parts.append(f"24h净平衡 {int(net24['net_ml'])} mL")

    return {
        "domain": "hemodynamic",
        "summary": "；".join(summary_parts) or "暂无循环系统深度数据",
        "trend_points": trend_points,
        "metric_cards": _build_metric_cards(trend_points, [("map", "MAP", "mmHg"), ("hr", "HR", "/min"), ("lactate", "乳酸", "mmol/L")]),
        "latest": {"map": latest_map, "hr": latest_hr, "lactate": latest_lactate},
        "vasopressor_timeline": vaso_events[-18:],
        "active_vasopressors": list(latest_by_drug.values())[:6],
        "fluid_balance": {
            "windows": fluid_windows,
            "intake_breakdown_24h": {
                "iv_ml": runtime.alert_engine._sum_window(intake_events, min(24, hours), now, category="iv"),
                "enteral_ml": runtime.alert_engine._sum_window(intake_events, min(24, hours), now, category="enteral"),
                "oral_ml": runtime.alert_engine._sum_window(intake_events, min(24, hours), now, category="oral"),
            },
            "output_breakdown_24h": {
                "urine_ml": runtime.alert_engine._sum_window(output_events, min(24, hours), now, category="urine"),
                "drainage_ml": runtime.alert_engine._sum_window(output_events, min(24, hours), now, category="drainage"),
                "ultrafiltration_ml": runtime.alert_engine._sum_window(output_events, min(24, hours), now, category="ultrafiltration"),
                "gi_decompression_ml": runtime.alert_engine._sum_window(output_events, min(24, hours), now, category="gi_decompression"),
            },
        },
    }


async def _build_infection_panel(patient_id: str, patient: dict, *, hours: int) -> dict:
    del patient_id
    now = datetime.now()
    since = now - timedelta(hours=hours)
    patient_ids = patient_his_pid_candidates(patient)
    his_pid = patient_ids[0] if patient_ids else None
    culture_records = await runtime.alert_engine._get_culture_records(his_pid, since) if his_pid else []
    susceptibility_rows = await runtime.alert_engine._parse_susceptibility_report(his_pid, since) if his_pid else []
    antibiotic_names, broad_spectrum_names = await runtime.alert_engine._load_antibiotic_dictionary()
    antibiotic_courses = await runtime.alert_engine._get_current_antibiotic_courses(str(patient.get("_id") or ""), now, antibiotic_names)
    mismatches = await runtime.alert_engine._check_coverage_mismatch(str(patient.get("_id") or ""), his_pid, susceptibility_rows, antibiotic_courses) if his_pid else []

    latest_culture = culture_records[-1] if culture_records else None
    latest_positive = next((row for row in reversed(culture_records) if row.get("is_positive")), None)
    latest_susceptibility = susceptibility_rows[-1] if susceptibility_rows else None
    broad_current = [row for row in antibiotic_courses if runtime.alert_engine._match_name_keywords(str(row.get("name") or ""), broad_spectrum_names)]
    if mismatches:
        deescalation = {"status": "coverage_gap", "title": "当前方案与药敏覆盖不匹配", "detail": mismatches[0].get("suggestion") or "建议根据药敏结果调整抗菌药覆盖。"}
    elif latest_culture and latest_culture.get("is_final") and broad_current:
        deescalation = {"status": "candidate", "title": "存在降阶梯评估窗口", "detail": "培养结果已回报且仍在使用广谱方案，建议结合药敏与感染灶考虑缩窄覆盖。"}
    elif latest_culture and not latest_culture.get("is_final"):
        deescalation = {"status": "pending", "title": "培养结果待回报", "detail": "培养尚未最终回报，当前更适合先维持经验性覆盖并等待证据。"}
    else:
        deescalation = {"status": "insufficient", "title": "暂缺明确降阶梯触发点", "detail": "当前未见足够培养/药敏闭环证据，可继续追踪炎症与微生物学结果。"}

    timeline = []
    for row in culture_records[-8:]:
        timeline.append({"type": "culture", "time": _iso(row.get("time")), "title": str(row.get("name") or "培养"), "detail": str(row.get("result") or row.get("flag") or "培养送检"), "status": "positive" if row.get("is_positive") else ("final" if row.get("is_final") else "pending")})
    for row in antibiotic_courses[:8]:
        course = row.get("course") if isinstance(row.get("course"), dict) else {}
        timeline.append({"type": "antibiotic", "time": _iso(row.get("latest_time") or course.get("last")), "title": str(row.get("name") or "抗菌药"), "detail": f"疗程 {round(_safe_float(course.get('duration_hours')) or 0)}h", "status": "active"})
    timeline = sorted(timeline, key=lambda item: str(item.get("time") or ""), reverse=True)[:10]

    return {
        "domain": "infection",
        "summary": deescalation.get("detail") or "暂无感染系统深度数据",
        "deescalation": deescalation,
        "culture_timeline": timeline,
        "latest_culture": serialize_doc(latest_culture) if latest_culture else None,
        "latest_positive_culture": serialize_doc(latest_positive) if latest_positive else None,
        "latest_susceptibility": serialize_doc(latest_susceptibility) if latest_susceptibility else None,
        "current_antibiotics": [{"name": row.get("name"), "latest_time": _iso(row.get("latest_time")), "duration_hours": _round_number(_safe_float((row.get("course") or {}).get("duration_hours")), 1), "broad_spectrum": runtime.alert_engine._match_name_keywords(str(row.get("name") or ""), broad_spectrum_names)} for row in antibiotic_courses[:10]],
        "coverage_mismatches": serialize_doc(mismatches[:4]),
    }


async def _build_respiratory_panel(patient_id: str, patient: dict, *, hours: int) -> dict:
    since = datetime.now() - timedelta(hours=hours)
    vent_device_id = await get_device_id(patient_id, "vent", patient_doc=patient)
    vent_cfg = (get_config().yaml_cfg or {}).get("ventilator", {})
    code_map = {
        "fio2": ((vent_cfg.get("fio2") or {}).get("code")) or "param_FiO2",
        "peep": ((vent_cfg.get("peep_measured") or {}).get("code")) or "param_vent_measure_peep",
        "rr": ((vent_cfg.get("rr_measured") or {}).get("code")) or "param_vent_resp",
        "vte": ((vent_cfg.get("vte") or {}).get("code")) or "param_vent_vt",
        "pip": ((vent_cfg.get("pip") or {}).get("code")) or "param_vent_pip",
        "mode": ((vent_cfg.get("vent_mode") or {}).get("code")) or "param_HuXiMoShi",
    }
    series_map = {key: await _device_cap_series(vent_device_id, code, since) for key, code in code_map.items() if key != "mode"}
    trend_points = _merge_time_series(series_map, bucket_hours=4 if hours > 24 else 2)
    latest_snapshot = await latest_params_by_device(vent_device_id, list(code_map.values()), lookback_minutes=max(hours * 60, 120)) if vent_device_id else None
    latest_params = latest_snapshot.get("params") if isinstance(latest_snapshot, dict) else {}
    mode = latest_params.get(code_map["mode"]) if isinstance(latest_params, dict) else None
    patient_ids = patient_his_pid_candidates(patient)
    pf_trend = None
    if hasattr(runtime.alert_engine, "_get_pf_ratio_trend"):
        try:
            pf_trend = await runtime.alert_engine._get_pf_ratio_trend(patient_ids[0] if patient_ids else None, datetime.now(), latest_params.get(code_map["fio2"]), hours=24)
        except Exception:
            pf_trend = None

    latest_rows = {key: _round_number(_safe_float(latest_params.get(code)) if latest_params else None, 0) for key, code in code_map.items() if key != "mode"}
    latest_rows["mode"] = mode
    summary_bits = []
    if latest_rows["mode"]:
        summary_bits.append(f"模式 {latest_rows['mode']}")
    if latest_rows["fio2"] is not None:
        summary_bits.append(f"FiO2 {int(latest_rows['fio2'])}%")
    if latest_rows["peep"] is not None:
        summary_bits.append(f"PEEP {int(latest_rows['peep'])} cmH2O")
    if latest_rows["rr"] is not None:
        summary_bits.append(f"RR {int(latest_rows['rr'])}/min")

    return {
        "domain": "respiratory",
        "summary": "；".join(summary_bits) or "暂无呼吸系统深度数据",
        "trend_points": trend_points,
        "metric_cards": _build_metric_cards(trend_points, [("fio2", "FiO2", "%"), ("peep", "PEEP", "cmH2O"), ("rr", "RR", "/min"), ("vte", "Vte", "mL")]),
        "latest": serialize_doc(latest_rows),
        "pf_trend": serialize_doc(pf_trend) if pf_trend else None,
        "ventilator_timeline": [{"time": row.get("time"), "mode": mode if index == len(trend_points) - 1 else None, "fio2": row.get("fio2"), "peep": row.get("peep"), "rr": row.get("rr"), "vte": row.get("vte"), "pip": row.get("pip")} for index, row in enumerate(trend_points[-12:])],
    }


@router.get("/api/ai/digital-twin/{patient_id}")
async def ai_patient_digital_twin(patient_id: str, refresh: bool = Query(default=False), hours: int = Query(default=24, ge=6, le=72)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    try:
        service = PatientDigitalTwinService(db=runtime.db, config=get_config(), alert_engine=runtime.alert_engine)
        record = await service.get_or_build_snapshot(str(pid), patient, hours=hours, refresh=refresh, persist=True)
        return {"code": 0, "record": serialize_doc(record)}
    except Exception as exc:
        logger.error("AI patient digital twin error: %s", exc)
        return {"code": 0, "record": None, "error": f"数字孪生快照异常: {str(exc)[:120]}"}


@router.post("/api/ai/what-if/{patient_id}")
async def ai_what_if_simulation(patient_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    try:
        model = SemiMechanisticCounterfactualModel(db=runtime.db, alert_engine=runtime.alert_engine)
        result = await model.simulate(str(pid), patient, payload or {})
        record = await _persist_ai_score_record(patient, result, score_type="patient_what_if_simulation")
        return {"code": 0, "simulation": serialize_doc(record)}
    except Exception as exc:
        logger.error("AI what-if simulation error: %s", exc)
        return {"code": 0, "simulation": None, "error": f"What-if 模拟异常: {str(exc)[:120]}"}


@router.get("/api/ai/subphenotype/{patient_id}")
async def ai_subphenotype_profile(patient_id: str, refresh: bool = Query(default=False)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    try:
        if not refresh:
            cached = await runtime.db.col("score").find_one({"patient_id": str(pid), "score_type": "clinical_subphenotype_profile"}, sort=[("calc_time", -1)])
            if cached:
                return {"code": 0, "profile": serialize_doc(cached)}
        profiler = CohortSubphenotypeProfiler(db=runtime.db, alert_engine=runtime.alert_engine)
        result = await profiler.profile(patient)
        record = await _persist_ai_score_record(patient, result, score_type="clinical_subphenotype_profile")
        return {"code": 0, "profile": serialize_doc(record)}
    except Exception as exc:
        logger.error("AI subphenotype error: %s", exc)
        return {"code": 0, "profile": None, "error": f"亚表型识别异常: {str(exc)[:120]}"}


@router.get("/api/ai/multi-agent/{patient_id}")
async def ai_multi_agent_assessment(patient_id: str, refresh: bool = Query(default=False)):
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
            record = await runtime.db.col("score").find_one({"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"}, sort=[("calc_time", -1)])
        if not record:
            orchestrator = ICUMultiAgentOrchestrator(db=runtime.db, config=get_config(), alert_engine=runtime.alert_engine, rag_service=runtime.ai_rag_service, ai_monitor=runtime.ai_monitor, ai_handoff_service=runtime.ai_handoff_service)
            record = await orchestrator.orchestrated_assessment(str(pid))
        return {"code": 0, "assessment": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI multi-agent assessment error: %s", exc)
        return {"code": 0, "assessment": None, "error": f"多智能体评估异常: {str(exc)[:120]}"}


@router.get("/api/ai/system-panels/{patient_id}")
async def ai_system_panels(patient_id: str, window: str = Query(default="24h", pattern="^(24h|72h)$")):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    hours = _hours_from_window(window)
    try:
        hemodynamic, infection, respiratory = await asyncio.gather(
            _build_hemodynamic_panel(str(pid), patient, hours=hours),
            _build_infection_panel(str(pid), patient, hours=hours),
            _build_respiratory_panel(str(pid), patient, hours=hours),
        )
        return {"code": 0, "window": window, "panels": {"hemodynamic": _serialize_nullable(hemodynamic), "infection": _serialize_nullable(infection), "respiratory": _serialize_nullable(respiratory)}}
    except Exception as exc:
        logger.error("AI system panels error: %s", exc)
        return {"code": 0, "window": window, "panels": {}, "error": f"系统深度面板异常: {str(exc)[:120]}"}
