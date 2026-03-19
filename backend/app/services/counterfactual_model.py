from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any

from app.config import get_config
from app.utils.patient_data import get_device_id, param_series_by_pid
from app.utils.patient_helpers import patient_his_pid_candidates


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


def _round(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _parse_when(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue
    return None


def _sigmoid(value: float) -> float:
    clipped = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-clipped))


def _curve(current_value: float | None, delta: float, *, tau_minutes: float, horizon_minutes: int = 30, step_minutes: int = 5, digits: int = 1) -> list[dict[str, Any]]:
    if current_value is None:
        return []
    tau = max(tau_minutes, 1.0)
    rows: list[dict[str, Any]] = []
    for minute in range(0, horizon_minutes + 1, step_minutes):
        gain = 1.0 - math.exp(-minute / tau)
        rows.append({"minute": minute, "value": _round(current_value + delta * gain, digits)})
    return rows


class SemiMechanisticCounterfactualModel:
    def __init__(self, *, db, alert_engine) -> None:
        self.db = db
        self.alert_engine = alert_engine

    async def _device_cap_series(self, device_id: str | None, code: str, since: datetime) -> list[dict]:
        if not device_id or not code:
            return []
        cursor = self.db.col("deviceCap").find(
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

    async def _lab_series_by_keywords(self, patient_ids: list[str], keywords: list[str], since: datetime, *, limit: int = 4000) -> list[dict]:
        if not patient_ids or not keywords:
            return []
        his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(limit)
        rows: list[dict] = []
        keyword_list = [str(item).lower() for item in keywords if str(item).strip()]
        async for doc in cursor:
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
            if not name:
                continue
            if keyword_list and not any(keyword in name.lower() for keyword in keyword_list):
                continue
            point_time = _parse_when(doc.get("authTime")) or _parse_when(doc.get("collectTime")) or _parse_when(doc.get("reportTime")) or _parse_when(doc.get("time"))
            if point_time is None or point_time < since:
                continue
            value = _safe_float(doc.get("result") or doc.get("resultValue") or doc.get("value"))
            if value is None:
                continue
            rows.append({"time": point_time, "value": value})
        rows.sort(key=lambda item: item["time"])
        return rows

    def _latest_value(self, rows: list[dict], *, digits: int = 1) -> float | None:
        if not rows:
            return None
        return _round(_safe_float(rows[-1].get("value")), digits)

    async def build_snapshot(self, patient_id: str, patient: dict, *, hours: int = 12) -> dict[str, Any]:
        since = datetime.now() - timedelta(hours=max(2, hours))
        patient_ids = patient_his_pid_candidates(patient)
        map_series = await param_series_by_pid(patient_id, "param_nibp_m", since)
        ibp_map_series = await param_series_by_pid(patient_id, "param_ibp_m", since)
        hr_series = await param_series_by_pid(patient_id, "param_HR", since)
        spo2_series = await param_series_by_pid(patient_id, "param_spo2", since)
        lactate_series = await self._lab_series_by_keywords(patient_ids, ["乳酸", "lactate", "lac"], since)
        merged_map_series = ibp_map_series if ibp_map_series else map_series
        vent_device_id = await get_device_id(patient_id, "vent", patient_doc=patient)
        vent_cfg = (get_config().yaml_cfg or {}).get("ventilator", {})
        fio2_code = ((vent_cfg.get("fio2") or {}).get("code")) or "param_FiO2"
        peep_code = ((vent_cfg.get("peep_measured") or {}).get("code")) or "param_vent_measure_peep"
        fio2_series = await self._device_cap_series(vent_device_id, fio2_code, since)
        peep_series = await self._device_cap_series(vent_device_id, peep_code, since)
        urine_rate = None
        if hasattr(self.alert_engine, "_get_urine_rate"):
            try:
                urine_rate = await self.alert_engine._get_urine_rate(patient_id, patient, hours=6)
            except Exception:
                urine_rate = None
        current_vaso_dose = None
        if hasattr(self.alert_engine, "_get_recent_drug_docs_window"):
            try:
                drug_docs = await self.alert_engine._get_recent_drug_docs_window(patient_id, hours=hours, limit=600)
                weight_kg = self.alert_engine._get_patient_weight(patient) if hasattr(self.alert_engine, "_get_patient_weight") else None
                vaso_rows = []
                for doc in drug_docs:
                    text = " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName", "drugSpec", "route", "routeName")).lower()
                    if not any(token in text for token in ["去甲肾上腺素", "norepinephrine", "noradrenaline", "多巴胺", "dopamine", "肾上腺素", "epinephrine", "血管加压素", "vasopressin"]):
                        continue
                    dose = self.alert_engine._extract_vasopressor_rate_ug_kg_min(doc, weight_kg) if hasattr(self.alert_engine, "_extract_vasopressor_rate_ug_kg_min") else None
                    event_time = _parse_when(doc.get("_event_time")) or _parse_when(doc.get("executeTime")) or _parse_when(doc.get("startTime")) or _parse_when(doc.get("orderTime"))
                    if event_time is None or event_time < since:
                        continue
                    vaso_rows.append({"time": event_time, "dose": dose})
                if vaso_rows:
                    latest_vaso = max(vaso_rows, key=lambda item: item["time"])
                    current_vaso_dose = _round(_safe_float(latest_vaso.get("dose")), 3)
            except Exception:
                current_vaso_dose = None

        return {
            "map": {"current": self._latest_value(merged_map_series, digits=0)},
            "hr": {"current": self._latest_value(hr_series, digits=0)},
            "spo2": {"current": self._latest_value(spo2_series, digits=0)},
            "lactate": {"current": self._latest_value(lactate_series, digits=1)},
            "fio2": {"current": self._latest_value(fio2_series, digits=0)},
            "peep": {"current": self._latest_value(peep_series, digits=0)},
            "urine_ml_kg_h_6h": _round(_safe_float(urine_rate), 2),
            "vasoactive_support": {"current_dose_ug_kg_min": current_vaso_dose},
        }

    async def simulate(self, patient_id: str, patient: dict, payload: dict[str, Any]) -> dict[str, Any]:
        intervention_type = str((payload or {}).get("intervention_type") or "vasopressor_up").strip().lower()
        intervention_label = str((payload or {}).get("intervention_label") or intervention_type).strip()
        horizon_minutes = int((payload or {}).get("horizon_minutes") or 30)
        dose_delta_pct = _safe_float((payload or {}).get("dose_delta_pct"))
        fluid_bolus_ml = _safe_float((payload or {}).get("fluid_bolus_ml"))
        fio2_delta = _safe_float((payload or {}).get("fio2_delta"))
        peep_delta = _safe_float((payload or {}).get("peep_delta"))
        diuretic_intensity = _safe_float((payload or {}).get("diuretic_intensity"))

        snapshot = await self.build_snapshot(patient_id, patient, hours=12)
        current_map = _safe_float((snapshot.get("map") or {}).get("current"))
        current_hr = _safe_float((snapshot.get("hr") or {}).get("current"))
        current_spo2 = _safe_float((snapshot.get("spo2") or {}).get("current"))
        current_lactate = _safe_float((snapshot.get("lactate") or {}).get("current"))
        current_fio2 = _safe_float((snapshot.get("fio2") or {}).get("current"))
        current_peep = _safe_float((snapshot.get("peep") or {}).get("current"))
        urine_rate = _safe_float(snapshot.get("urine_ml_kg_h_6h"))
        current_vaso = _safe_float(((snapshot.get("vasoactive_support") or {}).get("current_dose_ug_kg_min")))

        facts = await self.alert_engine._collect_patient_facts(patient, patient.get("_id")) if hasattr(self.alert_engine, "_collect_patient_facts") else {}
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        wbc = _safe_float(((labs.get("wbc") or {}) if isinstance(labs.get("wbc"), dict) else {}).get("value"))
        his_pid = str(patient.get("hisPid") or "").strip() or None
        device_id = await get_device_id(patient_id, "monitor", patient_doc=patient)
        sofa = await self.alert_engine._calc_sofa(patient, patient.get("_id"), device_id, his_pid) if hasattr(self.alert_engine, "_calc_sofa") else {}
        sofa_score = _safe_float((sofa or {}).get("score"))

        map_fragile = current_map is not None and current_map < 65
        hypoperfusion = bool((current_lactate is not None and current_lactate >= 2.5) or map_fragile or (urine_rate is not None and urine_rate < 0.5))
        oxygenation_gap = current_spo2 is not None and current_spo2 < 92
        fluid_overload_risk = bool((current_spo2 is not None and current_fio2 is not None and current_fio2 >= 50) or (current_peep is not None and current_peep >= 8))
        vasoplegia_burden = _sigmoid(((current_lactate or 1.5) - 2.0) * 0.9 + (0.8 if current_vaso else 0.0) + (0.5 if (wbc or 0) >= 15 else 0.0))
        preload_responsiveness = _sigmoid((0.8 if hypoperfusion else -0.2) + (0.6 if (urine_rate is not None and urine_rate < 0.5) else 0.0) - (0.9 if fluid_overload_risk else 0.0))
        recruitability = _sigmoid((0.8 if oxygenation_gap else 0.0) + (0.6 if (current_fio2 or 21) >= 60 else 0.0) + (0.4 if (current_peep or 5) >= 8 else 0.0))

        map_delta_30m = 0.0
        hr_delta_30m = 0.0
        spo2_delta_30m = 0.0
        lactate_delta_30m = 0.0
        map_tau = 12.0
        spo2_tau = 10.0
        lactate_tau = 22.0
        assumptions: list[str] = ["基于最近 12h 动态数据、器官状态和支持强度构建半机制短时反事实模型。"]
        cautions: list[str] = []
        rationale_bits: list[str] = []
        equation_hints: list[str] = []

        if intervention_type == "vasopressor_up":
            change_pct = dose_delta_pct if dose_delta_pct is not None else 20.0
            emax = 14.0 if hypoperfusion else 10.0
            ec50 = max(12.0, 40.0 - (current_vaso or 0.0) * 80.0)
            response_fraction = (max(change_pct, 0.0) / (max(change_pct, 0.0) + ec50)) if change_pct > 0 else 0.0
            map_delta_30m = emax * response_fraction * (0.65 + 0.55 * vasoplegia_burden)
            hr_delta_30m = -min(8.0, map_delta_30m * 0.55)
            lactate_delta_30m = -0.28 * response_fraction * (1.0 if hypoperfusion else 0.6)
            map_tau = 8.0
            lactate_tau = 26.0
            rationale_bits.append(f"采用 Emax 血管活性反应模型估计：升压药上调 {int(change_pct)}% 后 MAP 将快速上升，随后边际效应递减。")
            equation_hints.append("MAP ~ Emax * dose_change / (dose_change + EC50)")
            assumptions.append("假设主要低灌注机制包含血管张力下降，且当前药泵输入稳定。")
        elif intervention_type == "fluid_bolus":
            bolus = fluid_bolus_ml if fluid_bolus_ml is not None else 250.0
            map_delta_30m = min(10.0, (bolus / 250.0) * 4.2 * preload_responsiveness)
            hr_delta_30m = -min(5.0, map_delta_30m * 0.45)
            spo2_delta_30m = 0.5 - (1.6 * (bolus / 500.0) * (1.0 - preload_responsiveness) if fluid_overload_risk else 0.0)
            lactate_delta_30m = -0.18 * preload_responsiveness
            map_tau = 14.0
            spo2_tau = 18.0
            rationale_bits.append(f"采用容量反应性概率模型估计：当前前负荷反应性约 {int(preload_responsiveness * 100)}%，补液 {int(bolus)} mL 后 MAP 改善幅度受其主导。")
            equation_hints.append("Delta_MAP ~ bolus * preload_responsiveness")
        elif intervention_type == "diuresis":
            intensity = diuretic_intensity if diuretic_intensity is not None else 1.0
            spo2_delta_30m = (1.6 if fluid_overload_risk else 0.6) * intensity
            map_delta_30m = -(1.8 if map_fragile else 0.7) * intensity
            hr_delta_30m = 1.2 * intensity if map_fragile else 0.2 * intensity
            lactate_delta_30m = 0.05 * intensity if map_fragile else -0.04 * intensity
            spo2_tau = 20.0
            map_tau = 18.0
            rationale_bits.append("利尿采用容量卸载模型：更可能先改善氧合/呼吸负担，而不是直接提升灌注。")
            equation_hints.append("Delta_SpO2 ~ fluid_offload - hemodynamic_penalty")
        elif intervention_type == "fio2_up":
            change = fio2_delta if fio2_delta is not None else 10.0
            spo2_ceiling = max(0.0, 100.0 - (current_spo2 or 95.0))
            spo2_delta_30m = min(spo2_ceiling, 0.32 * max(change, 0.0) * (0.6 + 0.6 * recruitability))
            hr_delta_30m = -1.2 if oxygenation_gap else -0.4
            spo2_tau = 6.0
            rationale_bits.append(f"氧合反应采用饱和曲线：FiO2 上调 {int(change)}% 后，SpO2 改善受当前可复张性和天花板效应限制。")
            equation_hints.append("Delta_SpO2 ~ saturation_gap * recruitability")
        elif intervention_type == "peep_up":
            change = peep_delta if peep_delta is not None else 2.0
            spo2_delta_30m = min(6.0, max(change, 0.0) * 1.0 * recruitability)
            map_delta_30m = -min(5.0, max(change, 0.0) * (0.9 + 0.9 * (1.0 - preload_responsiveness)))
            hr_delta_30m = 1.2 if map_fragile else 0.4
            spo2_tau = 10.0
            map_tau = 9.0
            rationale_bits.append(f"PEEP 干预同时考虑肺泡复张收益与静脉回流惩罚，当前可复张性约 {int(recruitability * 100)}%。")
            equation_hints.append("Delta_SpO2 ~ recruitability; Delta_MAP ~ venous_return_penalty")
        else:
            raise ValueError("暂不支持该 intervention_type")

        projected = {
            "map_30m": _round((current_map or 0.0) + map_delta_30m if current_map is not None else None, 0),
            "hr_30m": _round((current_hr or 0.0) + hr_delta_30m if current_hr is not None else None, 0),
            "spo2_30m": _round((current_spo2 or 0.0) + spo2_delta_30m if current_spo2 is not None else None, 0),
            "lactate_30m": _round((current_lactate or 0.0) + lactate_delta_30m if current_lactate is not None else None, 1),
        }
        summary_bits = []
        if current_map is not None and projected["map_30m"] is not None:
            summary_bits.append(f"MAP 预计 {int(current_map)}→{int(projected['map_30m'])} mmHg")
        if current_spo2 is not None and projected["spo2_30m"] is not None and abs(spo2_delta_30m) >= 0.5:
            summary_bits.append(f"SpO2 预计 {int(current_spo2)}→{int(projected['spo2_30m'])}%")
        if current_lactate is not None and projected["lactate_30m"] is not None and abs(lactate_delta_30m) >= 0.1:
            summary_bits.append(f"乳酸趋势 {current_lactate:.1f}→{projected['lactate_30m']:.1f}")

        return {
            "intervention_type": intervention_type,
            "intervention_label": intervention_label,
            "summary": "；".join(summary_bits or rationale_bits) or "模拟已生成",
            "rationale": " ".join(rationale_bits) or "依据近期监测趋势进行短时反事实推演。",
            "current_state": {
                "map": _round(current_map, 0),
                "hr": _round(current_hr, 0),
                "spo2": _round(current_spo2, 0),
                "lactate": _round(current_lactate, 1),
                "fio2": _round(current_fio2, 0),
                "peep": _round(current_peep, 0),
                "urine_ml_kg_h_6h": _round(urine_rate, 2),
                "vaso_dose_ug_kg_min": _round(current_vaso, 3),
            },
            "projected_state": projected,
            "delta": {
                "map_30m": _round(map_delta_30m, 1),
                "hr_30m": _round(hr_delta_30m, 1),
                "spo2_30m": _round(spo2_delta_30m, 1),
                "lactate_30m": _round(lactate_delta_30m, 2),
            },
            "response_curve": {
                "map": _curve(current_map, map_delta_30m, tau_minutes=map_tau, horizon_minutes=horizon_minutes, digits=0),
                "spo2": _curve(current_spo2, spo2_delta_30m, tau_minutes=spo2_tau, horizon_minutes=horizon_minutes, digits=0),
                "lactate": _curve(current_lactate, lactate_delta_30m, tau_minutes=lactate_tau, horizon_minutes=horizon_minutes, digits=1),
            },
            "assumptions": assumptions[:5],
            "cautions": cautions[:5],
            "state_factors": {
                "vasoplegia_burden": round(vasoplegia_burden, 3),
                "preload_responsiveness": round(preload_responsiveness, 3),
                "recruitability": round(recruitability, 3),
                "sofa_score": _round(sofa_score, 0),
            },
            "model_meta": {
                "kind": "semi_mechanistic_counterfactual_model",
                "lookback_hours": 12,
                "horizon_minutes": horizon_minutes,
                "equations": equation_hints[:4],
                "note": "采用半机制 Emax/容量反应性/复张-回流耦合模型；如需真正论文级 PK/PD，需要基于本院连续时序数据完成参数辨识与外部验证。",
            },
        }
