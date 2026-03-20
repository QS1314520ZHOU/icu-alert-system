from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.config import get_config
from app.services.clinical_knowledge_graph import ClinicalKnowledgeGraph
from app.services.clinical_reasoning_agent import ClinicalReasoningAgent
from app.services.counterfactual_model import SemiMechanisticCounterfactualModel
from app.services.document_generator import ClinicalDocumentGenerator
from app.services.multi_agent_orchestrator import ICUMultiAgentOrchestrator
from app.services.patient_digital_twin import PatientDigitalTwinService
from app.services.subphenotype_clustering import CohortSubphenotypeProfiler
from app.utils.api_llm import call_api_llm
from app.utils.patient_data import fetch_dc_exam_items_by_his_pid, get_device_id, latest_params_by_device, param_series_by_pid
from app.utils.patient_helpers import patient_his_pid_candidates
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).strip())
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _parse_when(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue
    return None


def _iso(value: object) -> str | None:
    if isinstance(value, datetime):
        return serialize_doc(value)
    if value is None:
        return None
    return str(value)


def _serialize_nullable(value):
    """Serialize nested values while preserving None as JSON null instead of {}."""
    if value is None:
        return None
    if isinstance(value, list):
        return [_serialize_nullable(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_nullable(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_nullable(item) for key, item in value.items()}
    return serialize_doc(value)


def _hours_from_window(window: str) -> int:
    return 72 if str(window or "").strip().lower() == "72h" else 24


def _round_number(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _bucket_time(value: datetime, *, bucket_hours: int) -> datetime:
    hour = (value.hour // max(bucket_hours, 1)) * max(bucket_hours, 1)
    return value.replace(minute=0, second=0, microsecond=0, hour=hour)


def _merge_time_series(
    series_map: dict[str, list[dict]],
    *,
    bucket_hours: int = 2,
    max_points: int = 18,
) -> list[dict]:
    buckets: dict[datetime, dict] = {}
    for field, rows in series_map.items():
        for row in rows:
            point_time = _parse_when(row.get("time"))
            value = _safe_float(row.get("value"))
            if point_time is None or value is None:
                continue
            bucket = _bucket_time(point_time, bucket_hours=bucket_hours)
            current = buckets.setdefault(bucket, {"time": bucket})
            current[field] = value
    merged = [buckets[key] for key in sorted(buckets)]
    if len(merged) > max_points:
        step = max(1, math.ceil(len(merged) / max_points))
        merged = merged[::step][-max_points:]
    for row in merged:
        row["time"] = _iso(row.get("time"))
    return merged


async def _device_cap_series(device_id: str | None, code: str, since: datetime) -> list[dict]:
    if not device_id or not code:
        return []
    cursor = runtime.db.col("deviceCap").find(
        {"deviceID": device_id, "code": code, "time": {"$gte": since}},
        {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", 1).limit(4000)
    rows: list[dict] = []
    async for doc in cursor:
        point_time = _parse_when(doc.get("time"))
        value = doc.get("fVal")
        if value is None:
            value = doc.get("intVal")
        if value is None:
            value = doc.get("strVal")
        if point_time is None or value in (None, ""):
            continue
        rows.append({"time": point_time, "value": value})
    return rows


async def _lab_series_by_keywords(patient_ids: list[str], keywords: list[str], since: datetime, *, limit: int = 4000) -> list[dict]:
    if not patient_ids or not keywords:
        return []
    his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
    cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(limit)
    rows: list[dict] = []
    keyword_list = [str(item).lower() for item in keywords if str(item).strip()]
    async for doc in cursor:
        name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
        if not name:
            continue
        if keyword_list and not any(keyword in name.lower() for keyword in keyword_list):
            continue
        point_time = (
            _parse_when(doc.get("authTime"))
            or _parse_when(doc.get("collectTime"))
            or _parse_when(doc.get("reportTime"))
            or _parse_when(doc.get("time"))
        )
        if point_time is None or point_time < since:
            continue
        value = _safe_float(doc.get("result") or doc.get("resultValue") or doc.get("value"))
        if value is None:
            continue
        rows.append(
            {
                "time": point_time,
                "value": value,
                "unit": str(doc.get("unit") or doc.get("resultUnit") or "").strip(),
                "name": name,
            }
        )
    rows.sort(key=lambda item: item["time"])
    return rows


def _latest_metric(rows: list[dict], *, digits: int = 1) -> dict | None:
    if not rows:
        return None
    latest = rows[-1]
    return {
        "time": _iso(latest.get("time")),
        "value": _round_number(_safe_float(latest.get("value")), digits),
        "unit": latest.get("unit"),
        "name": latest.get("name"),
    }


def _build_metric_cards(trend_points: list[dict], specs: list[tuple[str, str, str]]) -> list[dict]:
    cards: list[dict] = []
    for key, label, unit in specs:
        latest_value = None
        for row in reversed(trend_points):
            value = _safe_float(row.get(key))
            if value is not None:
                latest_value = value
                break
        cards.append(
            {
                "key": key,
                "label": label,
                "value": _round_number(latest_value, 1),
                "unit": unit,
            }
        )
    return cards


def _bounded(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_ratio(numerator: float | None, denominator: float | None, *, default: float | None = None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return default
    try:
        return float(numerator) / float(denominator)
    except Exception:
        return default


def _sigmoid(value: float) -> float:
    clipped = _bounded(value, -30.0, 30.0)
    return 1.0 / (1.0 + math.exp(-clipped))


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    peak = max(scores.values())
    weights = {key: math.exp(value - peak) for key, value in scores.items()}
    total = sum(weights.values()) or 1.0
    return {key: round(val / total, 4) for key, val in weights.items()}


def _feature_distance(feature_values: dict[str, float], centroid: dict[str, Any]) -> float:
    axes = centroid.get("axes") if isinstance(centroid.get("axes"), dict) else {}
    if not axes:
        return 99.0
    total = 0.0
    weight_sum = 0.0
    for axis, spec in axes.items():
        if axis not in feature_values:
            continue
        center = _safe_float((spec or {}).get("center"))
        spread = max(_safe_float((spec or {}).get("spread")) or 1.0, 1e-6)
        weight = max(_safe_float((spec or {}).get("weight")) or 1.0, 1e-6)
        if center is None:
            continue
        total += abs(feature_values[axis] - center) / spread * weight
        weight_sum += weight
    if weight_sum <= 0:
        return 99.0
    return total / weight_sum


def _dynamic_curve(current_value: float | None, delta: float, *, tau_minutes: float, horizon_minutes: int = 30, step_minutes: int = 5, digits: int = 1) -> list[dict[str, Any]]:
    if current_value is None:
        return []
    rows: list[dict[str, Any]] = []
    tau = max(tau_minutes, 1.0)
    for minute in range(0, horizon_minutes + 1, step_minutes):
        gain = 1.0 - math.exp(-minute / tau)
        rows.append({"minute": minute, "value": _round_number(current_value + delta * gain, digits)})
    return rows


def _latest_series_value(rows: list[dict], *, digits: int = 1) -> float | None:
    if not rows:
        return None
    return _round_number(_safe_float(rows[-1].get("value")), digits)


def _series_delta(rows: list[dict], *, digits: int = 1) -> float | None:
    if len(rows) < 2:
        return None
    start = _safe_float(rows[0].get("value"))
    end = _safe_float(rows[-1].get("value"))
    if start is None or end is None:
        return None
    return _round_number(end - start, digits)


async def _build_patient_monitor_snapshot(patient_id: str, patient: dict, *, hours: int = 12) -> dict[str, Any]:
    since = datetime.now() - timedelta(hours=max(2, hours))
    patient_ids = patient_his_pid_candidates(patient)
    map_series = await param_series_by_pid(patient_id, "param_nibp_m", since)
    ibp_map_series = await param_series_by_pid(patient_id, "param_ibp_m", since)
    hr_series = await param_series_by_pid(patient_id, "param_HR", since)
    spo2_series = await param_series_by_pid(patient_id, "param_spo2", since)
    lactate_series = await _lab_series_by_keywords(patient_ids, ["乳酸", "lactate", "lac"], since)
    merged_map_series = ibp_map_series if ibp_map_series else map_series
    vent_device_id = await get_device_id(patient_id, "vent", patient_doc=patient)
    vent_cfg = (get_config().yaml_cfg or {}).get("ventilator", {})
    fio2_code = ((vent_cfg.get("fio2") or {}).get("code")) or "param_FiO2"
    peep_code = ((vent_cfg.get("peep_measured") or {}).get("code")) or "param_vent_measure_peep"
    fio2_series = await _device_cap_series(vent_device_id, fio2_code, since)
    peep_series = await _device_cap_series(vent_device_id, peep_code, since)
    urine_rate = None
    if hasattr(runtime.alert_engine, "_get_urine_rate"):
        try:
            urine_rate = await runtime.alert_engine._get_urine_rate(patient_id, patient, hours=6)
        except Exception:
            urine_rate = None
    vasoactive_count = 0
    current_vaso_dose = None
    if hasattr(runtime.alert_engine, "_get_recent_drug_docs_window"):
        try:
            drug_docs = await runtime.alert_engine._get_recent_drug_docs_window(patient_id, hours=hours, limit=600)
            weight_kg = runtime.alert_engine._get_patient_weight(patient) if hasattr(runtime.alert_engine, "_get_patient_weight") else None
            vaso_rows = []
            for doc in drug_docs:
                text = " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName", "drugSpec", "route", "routeName")).lower()
                if not any(token in text for token in ["去甲肾上腺素", "norepinephrine", "noradrenaline", "多巴胺", "dopamine", "肾上腺素", "epinephrine", "血管加压素", "vasopressin"]):
                    continue
                dose = runtime.alert_engine._extract_vasopressor_rate_ug_kg_min(doc, weight_kg) if hasattr(runtime.alert_engine, "_extract_vasopressor_rate_ug_kg_min") else None
                event_time = _parse_when(doc.get("_event_time")) or _parse_when(doc.get("executeTime")) or _parse_when(doc.get("startTime")) or _parse_when(doc.get("orderTime"))
                if event_time is None or event_time < since:
                    continue
                vaso_rows.append({"time": event_time, "dose": dose})
            vasoactive_count = len(vaso_rows)
            if vaso_rows:
                latest_vaso = max(vaso_rows, key=lambda item: item["time"])
                current_vaso_dose = _round_number(_safe_float(latest_vaso.get("dose")), 3)
        except Exception:
            vasoactive_count = 0
            current_vaso_dose = None

    return {
        "window_hours": hours,
        "map": {
            "current": _latest_series_value(merged_map_series, digits=0),
            "delta_12h": _series_delta(merged_map_series, digits=0),
        },
        "hr": {
            "current": _latest_series_value(hr_series, digits=0),
            "delta_12h": _series_delta(hr_series, digits=0),
        },
        "spo2": {
            "current": _latest_series_value(spo2_series, digits=0),
            "delta_12h": _series_delta(spo2_series, digits=0),
        },
        "lactate": {
            "current": _latest_series_value(lactate_series, digits=1),
            "delta_12h": _series_delta(lactate_series, digits=1),
        },
        "fio2": {
            "current": _latest_series_value(fio2_series, digits=0),
        },
        "peep": {
            "current": _latest_series_value(peep_series, digits=0),
        },
        "urine_ml_kg_h_6h": _round_number(_safe_float(urine_rate), 2),
        "vasoactive_support": {
            "active_count": vasoactive_count,
            "current_dose_ug_kg_min": current_vaso_dose,
        },
    }


def _build_what_if_curve(current_value: float | None, delta_30m: float, *, horizon_minutes: int = 30, step: int = 10, digits: int = 1) -> list[dict[str, Any]]:
    if current_value is None:
        return []
    rows: list[dict[str, Any]] = []
    for minute in range(0, horizon_minutes + 1, step):
        progress = minute / max(horizon_minutes, 1)
        rows.append(
            {
                "minute": minute,
                "value": _round_number(current_value + delta_30m * progress, digits),
            }
        )
    return rows


def _subphenotype_confidence(evidence_count: int, *, strong: bool = False) -> float:
    base = 0.46 + min(max(evidence_count, 0), 5) * 0.08
    if strong:
        base += 0.08
    return _bounded(round(base, 2), 0.35, 0.92)


def _published_subphenotype_prototypes() -> dict[str, list[dict[str, Any]]]:
    return {
        "sepsis": [
            {
                "code": "shock_hyperinflammatory",
                "label": "脓毒症高炎症/休克型",
                "summary": "乳酸、升压药和炎症负荷更突出，接近高炎症循环衰竭表型。",
                "axes": {
                    "lactate": {"center": 4.5, "spread": 1.4, "weight": 1.5},
                    "map_inverse": {"center": 1.0, "spread": 0.5, "weight": 1.2},
                    "vaso_dose": {"center": 0.22, "spread": 0.12, "weight": 1.5},
                    "wbc": {"center": 18.0, "spread": 5.0, "weight": 0.8},
                    "platelet_inverse": {"center": 1.0, "spread": 0.7, "weight": 0.9},
                    "creatinine": {"center": 160.0, "spread": 60.0, "weight": 0.8},
                },
                "care_implications": [
                    "优先按休克路径管理灌注目标、升压药和乳酸清除",
                    "把感染源控制与器官灌注复评放在同一节奏里推进",
                ],
            },
            {
                "code": "organ_dysfunction_dominant",
                "label": "脓毒症器官功能障碍主导型",
                "summary": "炎症存在，但肾脏、凝血或胆红素等器官损伤信号更占主导。",
                "axes": {
                    "lactate": {"center": 2.4, "spread": 1.0, "weight": 0.8},
                    "map_inverse": {"center": 0.4, "spread": 0.5, "weight": 0.8},
                    "creatinine": {"center": 220.0, "spread": 70.0, "weight": 1.4},
                    "bilirubin": {"center": 60.0, "spread": 26.0, "weight": 1.1},
                    "platelet_inverse": {"center": 1.2, "spread": 0.8, "weight": 1.0},
                    "sofa": {"center": 9.0, "spread": 2.5, "weight": 1.0},
                },
                "care_implications": [
                    "更需要器官保护与灌注支持并行，而不是只盯感染与血压",
                    "日内复盘重点应覆盖肾功能、凝血和胆红素轨迹",
                ],
            },
            {
                "code": "moderate_inflammatory",
                "label": "脓毒症中等炎症活动型",
                "summary": "存在感染炎症证据，但暂未进入明显休克或多器官衰竭高负荷模式。",
                "axes": {
                    "lactate": {"center": 2.0, "spread": 0.8, "weight": 1.0},
                    "map_inverse": {"center": 0.2, "spread": 0.3, "weight": 0.8},
                    "vaso_dose": {"center": 0.04, "spread": 0.05, "weight": 0.8},
                    "wbc": {"center": 13.0, "spread": 4.0, "weight": 0.8},
                    "sofa": {"center": 5.0, "spread": 2.0, "weight": 1.0},
                },
                "care_implications": ["更适合强化早期趋势监测与证据闭环，防止后续跨入高危表型"],
            },
        ],
        "ards": [
            {
                "code": "diffuse_recruitable",
                "label": "ARDS 弥漫可复张型",
                "summary": "FiO2/PEEP 需求较高，接近弥漫受累和较高复张潜力表型。",
                "axes": {
                    "sf_inverse": {"center": 1.4, "spread": 0.5, "weight": 1.6},
                    "fio2_fraction": {"center": 0.7, "spread": 0.15, "weight": 1.2},
                    "peep": {"center": 12.0, "spread": 3.0, "weight": 1.0},
                    "vaso_dose": {"center": 0.12, "spread": 0.08, "weight": 0.6},
                },
                "care_implications": [
                    "更适合持续评估俯卧位、PEEP 窗口和肺保护通气",
                    "需要同步评估复张收益与循环代价",
                ],
            },
            {
                "code": "focal_less_recruitable",
                "label": "ARDS 局灶/低复张型",
                "summary": "氧合受损存在，但呼吸机需求不完全呈现弥漫重度复张模式。",
                "axes": {
                    "sf_inverse": {"center": 0.9, "spread": 0.4, "weight": 1.2},
                    "fio2_fraction": {"center": 0.5, "spread": 0.12, "weight": 1.0},
                    "peep": {"center": 8.0, "spread": 2.0, "weight": 0.8},
                },
                "care_implications": [
                    "更应结合影像、体位反应和分泌物负荷判断局灶病灶",
                    "避免机械性上调 PEEP 而忽视循环副作用",
                ],
            },
        ],
        "aki": [
            {
                "code": "hypoperfusion_oliguric",
                "label": "AKI 低灌注少尿型",
                "summary": "少尿与低灌注并存，更接近肾前性/灌注不足驱动模式。",
                "axes": {
                    "creatinine": {"center": 180.0, "spread": 70.0, "weight": 1.2},
                    "urine_inverse": {"center": 1.4, "spread": 0.6, "weight": 1.6},
                    "map_inverse": {"center": 0.8, "spread": 0.5, "weight": 1.0},
                    "lactate": {"center": 3.0, "spread": 1.3, "weight": 0.8},
                },
                "care_implications": ["优先复核灌注压、容量反应性与肾毒性暴露"],
            },
            {
                "code": "nonoliguric_inflammatory",
                "label": "AKI 非少尿/炎症负荷型",
                "summary": "肌酐负荷升高，但并不完全由典型低灌注少尿解释。",
                "axes": {
                    "creatinine": {"center": 200.0, "spread": 75.0, "weight": 1.4},
                    "urine_inverse": {"center": 0.4, "spread": 0.4, "weight": 0.8},
                    "wbc": {"center": 15.0, "spread": 4.0, "weight": 0.8},
                    "bilirubin": {"center": 30.0, "spread": 18.0, "weight": 0.7},
                },
                "care_implications": ["更应同时回顾感染、药物与容量管理对肾功能的共同影响"],
            },
        ],
    }


async def _build_subphenotype_inputs(patient_id: str, patient: dict) -> dict[str, Any]:
    snapshot = await _build_patient_monitor_snapshot(patient_id, patient, hours=24)
    pid_obj = patient.get("_id")
    facts = await runtime.alert_engine._collect_patient_facts(patient, pid_obj) if hasattr(runtime.alert_engine, "_collect_patient_facts") else {}
    labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
    his_pid = str(patient.get("hisPid") or "").strip() or None
    device_id = await get_device_id(patient_id, "monitor", patient_doc=patient)
    sofa = None
    if hasattr(runtime.alert_engine, "_calc_sofa"):
        try:
            sofa = await runtime.alert_engine._calc_sofa(patient, pid_obj, device_id, his_pid)
        except Exception:
            sofa = None
    similar_cases = None
    if hasattr(runtime.alert_engine, "get_similar_case_outcomes"):
        try:
            similar_cases = await runtime.alert_engine.get_similar_case_outcomes(patient, limit=8)
        except Exception:
            similar_cases = None
    return {"snapshot": snapshot, "facts": facts, "labs": labs, "sofa": sofa or {}, "similar_cases": similar_cases or {}}


def _derive_subphenotype_feature_vector(patient: dict, payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    labs = payload.get("labs") if isinstance(payload.get("labs"), dict) else {}
    sofa = payload.get("sofa") if isinstance(payload.get("sofa"), dict) else {}
    age = _safe_float(patient.get("age"))
    lactate = _safe_float(((snapshot.get("lactate") or {}).get("current")))
    map_value = _safe_float(((snapshot.get("map") or {}).get("current")))
    spo2 = _safe_float(((snapshot.get("spo2") or {}).get("current")))
    fio2 = _safe_float(((snapshot.get("fio2") or {}).get("current")))
    peep = _safe_float(((snapshot.get("peep") or {}).get("current")))
    urine_rate = _safe_float(snapshot.get("urine_ml_kg_h_6h"))
    vaso_dose = _safe_float((((snapshot.get("vasoactive_support") or {}).get("current_dose_ug_kg_min"))))
    wbc = _safe_float(((labs.get("wbc") or {}) if isinstance(labs.get("wbc"), dict) else {}).get("value"))
    plt = _safe_float(((labs.get("plt") or {}) if isinstance(labs.get("plt"), dict) else {}).get("value"))
    cr = _safe_float(((labs.get("cr") or {}) if isinstance(labs.get("cr"), dict) else {}).get("value"))
    bili = _safe_float(((labs.get("bil") or labs.get("bilirubin") or {}) if isinstance(labs.get("bil") or labs.get("bilirubin"), dict) else {}).get("value"))
    sf_ratio = _safe_ratio(spo2, (fio2 / 100.0) if fio2 else None)
    sofa_score = _safe_float(sofa.get("score"))
    features = {
        "age": age or 60.0,
        "lactate": lactate or 1.5,
        "map_inverse": max(0.0, (65.0 - (map_value or 65.0)) / 10.0),
        "vaso_dose": vaso_dose or 0.0,
        "wbc": wbc or 10.0,
        "platelet_inverse": max(0.0, (150.0 - (plt or 150.0)) / 100.0),
        "creatinine": cr or 90.0,
        "bilirubin": bili or 18.0,
        "sofa": sofa_score or 4.0,
        "fio2_fraction": (fio2 or 21.0) / 100.0,
        "peep": peep or 5.0,
        "sf_inverse": max(0.0, (315.0 - ((sf_ratio or 3.15) * 100.0)) / 100.0),
        "urine_inverse": max(0.0, (0.8 - (urine_rate or 0.8)) / 0.4),
    }
    snapshot_payload = {
        "map": _round_number(map_value, 0),
        "lactate": _round_number(lactate, 1),
        "spo2": _round_number(spo2, 0),
        "fio2": _round_number(fio2, 0),
        "peep": _round_number(peep, 0),
        "sf_ratio": _round_number((sf_ratio * 100.0) if sf_ratio is not None else None, 1),
        "urine_ml_kg_h_6h": _round_number(urine_rate, 2),
        "vaso_dose_ug_kg_min": _round_number(vaso_dose, 3),
        "wbc": _round_number(wbc, 1),
        "plt": _round_number(plt, 0),
        "creatinine": _round_number(cr, 1),
        "bilirubin": _round_number(bili, 1),
        "sofa": _round_number(sofa_score, 0),
    }
    return features, snapshot_payload


def _similar_case_prior(similar_cases_payload: dict[str, Any], syndrome: str) -> dict[str, float]:
    cases = similar_cases_payload.get("cases") if isinstance(similar_cases_payload.get("cases"), list) else []
    if not cases:
        return {}
    severe = 0.0
    mild = 0.0
    for row in cases[:6]:
        support = float(bool(row.get("vasopressor_used"))) + float(bool(row.get("crrt_used"))) + float(bool(row.get("vent_used")))
        if str(row.get("outcome") or "") == "死亡":
            severe += 1.2 + support * 0.3
        else:
            mild += 1.0 + (0.3 if not row.get("crrt_used") else 0.0)
    if syndrome == "sepsis":
        return {"shock_hyperinflammatory": severe * 0.18, "organ_dysfunction_dominant": severe * 0.12, "moderate_inflammatory": mild * 0.12}
    if syndrome == "ards":
        return {"diffuse_recruitable": severe * 0.16, "focal_less_recruitable": mild * 0.10}
    if syndrome == "aki":
        return {"hypoperfusion_oliguric": severe * 0.14, "nonoliguric_inflammatory": mild * 0.10}
    return {}


async def _persist_ai_score_record(patient: dict, payload: dict[str, Any], *, score_type: str) -> dict[str, Any]:
    now = datetime.now()
    record = {
        "patient_id": str(patient.get("_id") or ""),
        "patient_name": patient.get("name") or patient.get("hisName") or "",
        "bed": patient.get("hisBed") or patient.get("bed") or "",
        "dept": patient.get("dept") or patient.get("hisDept") or "",
        "score_type": score_type,
        "calc_time": now,
        "updated_at": now,
        "month": now.strftime("%Y-%m"),
        "day": now.strftime("%Y-%m-%d"),
        **payload,
    }
    insert_res = await runtime.db.col("score_records").insert_one(record)
    record["_id"] = insert_res.inserted_id
    return record


async def _build_hemodynamic_panel(patient_id: str, patient: dict, *, hours: int) -> dict:
    since = datetime.now() - timedelta(hours=hours)
    patient_ids = patient_his_pid_candidates(patient)
    map_series = await param_series_by_pid(patient_id, "param_nibp_m", since)
    ibp_map_series = await param_series_by_pid(patient_id, "param_ibp_m", since)
    hr_series = await param_series_by_pid(patient_id, "param_HR", since)
    lactate_series = await _lab_series_by_keywords(patient_ids, ["乳酸", "lactate", "lac"], since)

    merged_map_series = ibp_map_series if ibp_map_series else map_series
    trend_points = _merge_time_series(
        {
            "map": merged_map_series,
            "hr": hr_series,
            "lactate": lactate_series,
        },
        bucket_hours=4 if hours > 24 else 2,
    )

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
        matched_drug = None
        for label, keywords in vaso_keywords.items():
            if any(keyword.lower() in text for keyword in keywords):
                matched_drug = label
                break
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
    fluid_windows: list[dict] = []
    for window_hours in (6, 24, 72):
        if window_hours > hours:
            continue
        intake_total = runtime.alert_engine._sum_window(intake_events, window_hours, now)
        output_total = runtime.alert_engine._sum_window(output_events, window_hours, now)
        fluid_windows.append(
            {
                "label": f"{window_hours}h",
                "intake_ml": intake_total,
                "output_ml": output_total,
                "net_ml": round(intake_total - output_total, 1),
            }
        )

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
        "latest": {
            "map": latest_map,
            "hr": latest_hr,
            "lactate": latest_lactate,
        },
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
    culture_records: list[dict] = []
    susceptibility_rows: list[dict] = []
    antibiotic_courses: list[dict] = []
    mismatches: list[dict] = []
    broad_spectrum_names: list[str] = []

    if his_pid:
        culture_records = await runtime.alert_engine._get_culture_records(his_pid, since)
        susceptibility_rows = await runtime.alert_engine._parse_susceptibility_report(his_pid, since)
    antibiotic_names, broad_spectrum_names = await runtime.alert_engine._load_antibiotic_dictionary()
    antibiotic_courses = await runtime.alert_engine._get_current_antibiotic_courses(str(patient.get("_id") or ""), now, antibiotic_names)
    if his_pid:
        mismatches = await runtime.alert_engine._check_coverage_mismatch(str(patient.get("_id") or ""), his_pid, susceptibility_rows, antibiotic_courses)

    latest_culture = culture_records[-1] if culture_records else None
    latest_positive = next((row for row in reversed(culture_records) if row.get("is_positive")), None)
    latest_susceptibility = susceptibility_rows[-1] if susceptibility_rows else None

    broad_current = [
        row for row in antibiotic_courses
        if runtime.alert_engine._match_name_keywords(str(row.get("name") or ""), broad_spectrum_names)
    ]
    if mismatches:
        deescalation = {
            "status": "coverage_gap",
            "title": "当前方案与药敏覆盖不匹配",
            "detail": mismatches[0].get("suggestion") or "建议根据药敏结果调整抗菌药覆盖。",
        }
    elif latest_culture and latest_culture.get("is_final") and broad_current:
        deescalation = {
            "status": "candidate",
            "title": "存在降阶梯评估窗口",
            "detail": "培养结果已回报且仍在使用广谱方案，建议结合药敏与感染灶考虑缩窄覆盖。",
        }
    elif latest_culture and not latest_culture.get("is_final"):
        deescalation = {
            "status": "pending",
            "title": "培养结果待回报",
            "detail": "培养尚未最终回报，当前更适合先维持经验性覆盖并等待证据。",
        }
    else:
        deescalation = {
            "status": "insufficient",
            "title": "暂缺明确降阶梯触发点",
            "detail": "当前未见足够培养/药敏闭环证据，可继续追踪炎症与微生物学结果。",
        }

    timeline: list[dict] = []
    for row in culture_records[-8:]:
        timeline.append(
            {
                "type": "culture",
                "time": _iso(row.get("time")),
                "title": str(row.get("name") or "培养"),
                "detail": str(row.get("result") or row.get("flag") or "培养送检"),
                "status": "positive" if row.get("is_positive") else ("final" if row.get("is_final") else "pending"),
            }
        )
    for row in antibiotic_courses[:8]:
        course = row.get("course") if isinstance(row.get("course"), dict) else {}
        timeline.append(
            {
                "type": "antibiotic",
                "time": _iso(row.get("latest_time") or course.get("last")),
                "title": str(row.get("name") or "抗菌药"),
                "detail": f"疗程 {round(_safe_float(course.get('duration_hours')) or 0)}h",
                "status": "active",
            }
        )
    timeline = sorted(timeline, key=lambda item: str(item.get("time") or ""), reverse=True)[:10]

    return {
        "domain": "infection",
        "summary": deescalation.get("detail") or "暂无感染系统深度数据",
        "deescalation": deescalation,
        "culture_timeline": timeline,
        "latest_culture": serialize_doc(latest_culture) if latest_culture else None,
        "latest_positive_culture": serialize_doc(latest_positive) if latest_positive else None,
        "latest_susceptibility": serialize_doc(latest_susceptibility) if latest_susceptibility else None,
        "current_antibiotics": [
            {
                "name": row.get("name"),
                "latest_time": _iso(row.get("latest_time")),
                "duration_hours": _round_number(_safe_float((row.get("course") or {}).get("duration_hours")), 1),
                "broad_spectrum": runtime.alert_engine._match_name_keywords(str(row.get("name") or ""), broad_spectrum_names),
            }
            for row in antibiotic_courses[:10]
        ],
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
    series_map = {
        "fio2": await _device_cap_series(vent_device_id, code_map["fio2"], since),
        "peep": await _device_cap_series(vent_device_id, code_map["peep"], since),
        "rr": await _device_cap_series(vent_device_id, code_map["rr"], since),
        "vte": await _device_cap_series(vent_device_id, code_map["vte"], since),
        "pip": await _device_cap_series(vent_device_id, code_map["pip"], since),
    }
    trend_points = _merge_time_series(series_map, bucket_hours=4 if hours > 24 else 2)
    latest_snapshot = await latest_params_by_device(vent_device_id, list(code_map.values()), lookback_minutes=max(hours * 60, 120)) if vent_device_id else None
    latest_params = latest_snapshot.get("params") if isinstance(latest_snapshot, dict) else {}
    mode = latest_params.get(code_map["mode"]) if isinstance(latest_params, dict) else None
    pf_trend = None
    if hasattr(runtime.alert_engine, "_get_pf_ratio_trend"):
        try:
            pf_trend = await runtime.alert_engine._get_pf_ratio_trend(patient_his_pid_candidates(patient)[0] if patient_his_pid_candidates(patient) else None, datetime.now(), latest_params.get(code_map["fio2"]), hours=24)
        except Exception:
            pf_trend = None

    latest_rows = {
        "mode": mode,
        "fio2": _round_number(_safe_float(latest_params.get(code_map["fio2"])) if latest_params else None, 0),
        "peep": _round_number(_safe_float(latest_params.get(code_map["peep"])) if latest_params else None, 0),
        "rr": _round_number(_safe_float(latest_params.get(code_map["rr"])) if latest_params else None, 0),
        "vte": _round_number(_safe_float(latest_params.get(code_map["vte"])) if latest_params else None, 0),
        "pip": _round_number(_safe_float(latest_params.get(code_map["pip"])) if latest_params else None, 0),
    }
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
        "ventilator_timeline": [
            {
                "time": row.get("time"),
                "mode": mode if index == len(trend_points) - 1 else None,
                "fio2": row.get("fio2"),
                "peep": row.get("peep"),
                "rr": row.get("rr"),
                "vte": row.get("vte"),
                "pip": row.get("pip"),
            }
            for index, row in enumerate(trend_points[-12:])
        ],
    }


def _safe_text_list(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows


def _normalize_mdt_decisions(payload: dict | None) -> list[dict]:
    rows = (payload or {}).get("decisions") if isinstance((payload or {}).get("decisions"), list) else []
    normalized: list[dict] = []
    for idx, item in enumerate(rows[:20], start=1):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or item.get("title") or "").strip()
        if not action:
            continue
        normalized.append(
            {
                "id": str(item.get("id") or f"decision-{idx}"),
                "action": action,
                "owner": str(item.get("owner") or "").strip() or "值班医生",
                "deadline": str(item.get("deadline") or "").strip() or "6h",
                "monitoring": str(item.get("monitoring") or "").strip() or "按系统指标复评",
                "review_time": str(item.get("review_time") or "").strip() or "6h",
                "status": str(item.get("status") or "pending").strip() or "pending",
                "note": str(item.get("note") or "").strip(),
            }
        )
    return normalized


def _build_order_drafts(*, patient: dict, assessment: dict | None, decisions: list[dict]) -> list[dict]:
    patient_name = str(patient.get("name") or patient.get("hisName") or "当前患者").strip()
    meta_actions = []
    if isinstance(assessment, dict):
        result = assessment.get("result") if isinstance(assessment.get("result"), dict) else assessment
        meta = result.get("meta_agent") if isinstance(result.get("meta_agent"), dict) else {}
        meta_actions = _safe_text_list(meta.get("final_actions"), limit=10)
    base_actions = [row.get("action") for row in decisions if str(row.get("action") or "").strip()]
    actions = list(dict.fromkeys([*base_actions, *meta_actions]))[:8]
    drafts: list[dict] = []
    for idx, action in enumerate(actions, start=1):
        drafts.append(
            {
                "id": f"order-{idx}",
                "category": "医嘱建议",
                "order_text": f"{patient_name}：{action}",
                "priority": "high" if idx <= 2 else "medium",
                "status": "draft",
                "source": "mdt_workspace",
            }
        )
    if not drafts:
        drafts.append(
            {
                "id": "order-1",
                "category": "医嘱建议",
                "order_text": f"{patient_name}：等待 MDT 决议后生成待审核医嘱草稿。",
                "priority": "medium",
                "status": "draft",
                "source": "mdt_workspace",
            }
        )
    return drafts


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


@router.get("/api/ai/feedback/summary")
async def ai_feedback_summary(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
):
    """AI反馈闭环汇总（含近期反馈记录）。"""
    since = datetime.now() - timedelta(days=days)
    cursor = runtime.db.col("ai_prediction_feedback").find({"created_at": {"$gte": since}}).sort("created_at", -1).limit(500)
    docs = [doc async for doc in cursor]

    by_outcome = {"confirmed": 0, "dismissed": 0, "inaccurate": 0}
    by_module: dict[str, int] = {}
    for doc in docs:
        outcome = str(doc.get("outcome") or "").strip().lower()
        module = str(doc.get("module") or "unknown").strip() or "unknown"
        if outcome in by_outcome:
            by_outcome[outcome] += 1
        else:
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        by_module[module] = int(by_module.get(module, 0) or 0) + 1

    recent_docs = docs[:limit]
    alert_ids: list[ObjectId] = []
    alert_map: dict[str, dict] = {}
    for doc in recent_docs:
        oid = safe_oid(doc.get("prediction_id"))
        if oid is not None:
            alert_ids.append(oid)

    if alert_ids:
        alert_cursor = runtime.db.col("alert_records").find({"_id": {"$in": alert_ids}})
        async for alert_doc in alert_cursor:
            alert_map[str(alert_doc.get("_id"))] = alert_doc

    recent_rows = []
    for doc in recent_docs:
        prediction_id = str(doc.get("prediction_id") or "").strip()
        alert_doc = alert_map.get(prediction_id) or {}
        recent_rows.append(
            serialize_doc(
                {
                    "prediction_id": prediction_id,
                    "module": str(doc.get("module") or "ai_risk"),
                    "outcome": str(doc.get("outcome") or ""),
                    "detail": doc.get("detail") or {},
                    "created_at": doc.get("created_at"),
                    "alert_name": alert_doc.get("name") or alert_doc.get("rule_id") or "",
                    "patient_id": alert_doc.get("patient_id") or "",
                    "patient_name": alert_doc.get("patient_name") or alert_doc.get("name") or "",
                    "bed": alert_doc.get("bed") or alert_doc.get("patient_bed") or alert_doc.get("hisBed") or "",
                    "severity": alert_doc.get("severity") or "",
                }
            )
        )

    total = len(docs)
    confirmed = int(by_outcome.get("confirmed") or 0)
    inaccurate = int(by_outcome.get("inaccurate") or 0)
    summary = {
        "total": total,
        "by_outcome": by_outcome,
        "by_module": by_module,
        "confirmed_ratio": round((confirmed / total), 3) if total else 0,
        "inaccurate_ratio": round((inaccurate / total), 3) if total else 0,
    }
    return {"code": 0, "days": days, "summary": summary, "recent": recent_rows}


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


@router.get("/api/ai/proactive-management/{patient_id}")
async def ai_proactive_management(patient_id: str, refresh: bool = Query(default=False)):
    """主动管理闭环方案。"""
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
async def ai_proactive_management_feedback(
    patient_id: str,
    intervention_id: str,
    payload: dict = Body(default={}),
):
    """记录主动管理干预反馈并评估效果。"""
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
    """个体化重症诊疗推理。"""
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
            record = await runtime.db.col("score_records").find_one(
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
    """知识图谱驱动的因果链分析。"""
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
    """干预后的前向影响预测。"""
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
    """护理文本异常信号分析。"""
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


@router.get("/api/ai/digital-twin/{patient_id}")
async def ai_patient_digital_twin(patient_id: str, refresh: bool = Query(default=False), hours: int = Query(default=24, ge=6, le=72)):
    """患者数字孪生快照与全景时间轴。"""
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
    """患者特异的短时反事实模拟。"""
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
    """综合征亚表型识别。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        if not refresh:
            cached = await runtime.db.col("score_records").find_one(
                {"patient_id": str(pid), "score_type": "clinical_subphenotype_profile"},
                sort=[("calc_time", -1)],
            )
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
    """ICU 多智能体协同评估。"""
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
            record = await runtime.db.col("score_records").find_one(
                {"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"},
                sort=[("calc_time", -1)],
            )
        if not record:
            orchestrator = ICUMultiAgentOrchestrator(
                db=runtime.db,
                config=get_config(),
                alert_engine=runtime.alert_engine,
                rag_service=runtime.ai_rag_service,
                ai_monitor=runtime.ai_monitor,
                ai_handoff_service=runtime.ai_handoff_service,
            )
            record = await orchestrator.orchestrated_assessment(str(pid))
        return {"code": 0, "assessment": serialize_doc(record) if record else None}
    except Exception as exc:
        logger.error("AI multi-agent assessment error: %s", exc)
        return {"code": 0, "assessment": None, "error": f"多智能体评估异常: {str(exc)[:120]}"}


@router.get("/api/ai/system-panels/{patient_id}")
async def ai_system_panels(patient_id: str, window: str = Query(default="24h", pattern="^(24h|72h)$")):
    """MDT 专科深度面板数据。"""
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
        return {
            "code": 0,
            "window": window,
            "panels": {
                "hemodynamic": _serialize_nullable(hemodynamic),
                "infection": _serialize_nullable(infection),
                "respiratory": _serialize_nullable(respiratory),
            },
        }
    except Exception as exc:
        logger.error("AI system panels error: %s", exc)
        return {"code": 0, "window": window, "panels": {}, "error": f"系统深度面板异常: {str(exc)[:120]}"}


@router.post("/api/ai/documents/{patient_id}")
async def ai_generate_document(
    patient_id: str,
    payload: dict = Body(default={}),
):
    """生成临床文书。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    doc_type = str((payload or {}).get("doc_type") or "").strip()
    if not doc_type:
        return {"code": 400, "message": "doc_type不能为空"}
    time_range = (payload or {}).get("time_range") if isinstance((payload or {}).get("time_range"), dict) else None

    generator = ClinicalDocumentGenerator(
        db=runtime.db,
        config=get_config(),
        alert_engine=runtime.alert_engine,
        rag_service=runtime.ai_rag_service,
        ai_monitor=runtime.ai_monitor,
        ai_handoff_service=runtime.ai_handoff_service,
    )
    try:
        record = await generator.generate(str(pid), doc_type, time_range=time_range)
        if not record:
            return {"code": 0, "document": None}
        return {"code": 0, "document": serialize_doc(record)}
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    except Exception as exc:
        logger.error("AI document generation error: %s", exc)
        return {"code": 0, "document": None, "error": f"文书生成异常: {str(exc)[:120]}"}


@router.get("/api/ai/mdt-workspace/{patient_id}")
async def ai_mdt_workspace(patient_id: str):
    """获取 MDT 结构化协作记录与文书产物。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1, "name": 1, "hisName": 1, "hisBed": 1, "bed": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    workspace = await runtime.db.col("score_records").find_one(
        {"patient_id": str(pid), "score_type": "mdt_workspace_record"},
        sort=[("updated_at", -1), ("calc_time", -1)],
    )
    documents_cursor = runtime.db.col("score_records").find(
        {"patient_id": str(pid), "score_type": "clinical_document", "doc_type": {"$in": ["mdt_summary", "daily_progress", "consultation_request"]}}
    ).sort("updated_at", -1).limit(20)
    documents = [serialize_doc(doc) async for doc in documents_cursor]
    assessment = await runtime.db.col("score_records").find_one(
        {"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"},
        sort=[("calc_time", -1)],
    )
    decisions = []
    order_drafts = []
    if isinstance(workspace, dict):
        decisions = workspace.get("decisions") if isinstance(workspace.get("decisions"), list) else []
        order_drafts = workspace.get("order_drafts") if isinstance(workspace.get("order_drafts"), list) else []
    if not order_drafts:
        order_drafts = _build_order_drafts(patient=patient, assessment=assessment, decisions=decisions)
    return {
        "code": 0,
        "workspace": serialize_doc(workspace) if workspace else None,
        "documents": documents,
        "order_drafts": serialize_doc(order_drafts),
    }


@router.post("/api/ai/mdt-workspace/{patient_id}")
async def ai_save_mdt_workspace(patient_id: str, payload: dict = Body(default={})):
    """保存 MDT 结构化协作记录。"""
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    assessment = await runtime.db.col("score_records").find_one(
        {"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"},
        sort=[("calc_time", -1)],
    )
    decisions = _normalize_mdt_decisions(payload)
    consult_record = str((payload or {}).get("consult_record") or "").strip()
    progress_record = str((payload or {}).get("progress_record") or "").strip()
    order_drafts = (payload or {}).get("order_drafts") if isinstance((payload or {}).get("order_drafts"), list) else None
    normalized_orders = []
    for idx, item in enumerate(order_drafts or [], start=1):
        if not isinstance(item, dict):
            continue
        order_text = str(item.get("order_text") or item.get("text") or "").strip()
        if not order_text:
            continue
        normalized_orders.append(
            {
                "id": str(item.get("id") or f"order-{idx}"),
                "category": str(item.get("category") or "医嘱建议").strip(),
                "order_text": order_text,
                "priority": str(item.get("priority") or "medium").strip(),
                "status": str(item.get("status") or "draft").strip(),
                "source": str(item.get("source") or "mdt_workspace").strip(),
            }
        )
    if not normalized_orders:
        normalized_orders = _build_order_drafts(patient=patient, assessment=assessment, decisions=decisions)

    now = datetime.now()
    record = {
        "patient_id": str(pid),
        "patient_name": patient.get("name") or patient.get("hisName") or "",
        "bed": patient.get("hisBed") or patient.get("bed") or "",
        "score_type": "mdt_workspace_record",
        "summary": decisions[0].get("action") if decisions else "MDT 工作站结构化记录",
        "decisions": decisions,
        "consult_record": consult_record,
        "progress_record": progress_record,
        "order_drafts": normalized_orders,
        "meta_actions": _safe_text_list((((assessment or {}).get("result") or {}).get("meta_agent") or {}).get("final_actions"), limit=12),
        "updated_at": now,
        "calc_time": now,
    }
    existing = await runtime.db.col("score_records").find_one(
        {"patient_id": str(pid), "score_type": "mdt_workspace_record"},
        sort=[("updated_at", -1), ("calc_time", -1)],
    )
    if existing:
        await runtime.db.col("score_records").update_one({"_id": existing["_id"]}, {"$set": record})
        record["_id"] = existing["_id"]
    else:
        insert_res = await runtime.db.col("score_records").insert_one(record)
        record["_id"] = insert_res.inserted_id
    return {"code": 0, "workspace": serialize_doc(record)}


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

