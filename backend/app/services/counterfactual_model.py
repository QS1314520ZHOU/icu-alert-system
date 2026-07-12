from __future__ import annotations

import math
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_config
from app.services.local_model_paths import local_model_dir
from app.services.patient_digital_twin import PatientDigitalTwinService
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


def _unwrap_current(entry: object) -> float | None:
    """entry 可能是裸标量，也可能是 {"current"/"value"/"latest": x}。统一取数值。"""
    if isinstance(entry, dict):
        for k in ("current", "value", "latest"):
            if k in entry:
                v = _unwrap_current(entry[k])
                if v is not None:
                    return v
        return None
    return _safe_float(entry)


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


def _horizon_minutes(payload: dict[str, Any] | None, default: int = 30) -> int:
    try:
        raw = int((payload or {}).get("horizon_minutes") or default)
    except Exception:
        raw = default
    return max(1, min(raw, 360))


def _bands(curve: list[dict[str, Any]], digits: int = 1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in curve:
        value = _safe_float(point.get("value"))
        if value is None:
            continue
        minute = int(point.get("minute") or 0)
        spread = max(abs(value) * 0.015, 1.0) * (1.0 + minute / 360.0)
        rows.append(
            {
                "minute": minute,
                "p50": _round(value, digits),
                "p10": _round(value - spread, digits),
                "p90": _round(value + spread, digits),
                "p025": _round(value - spread * 1.75, digits),
                "p975": _round(value + spread * 1.75, digits),
            }
        )
    return rows


def _cohort_enabled(patient: dict[str, Any], patient_id: str, rollout_cfg: dict[str, Any]) -> bool:
    cohorts = [str(item).strip() for item in rollout_cfg.get("enabled_cohorts") or [] if str(item).strip()]
    if cohorts:
        patient_blob = " ".join(str(patient.get(key) or "") for key in ("ward", "dept", "hisDept", "bed", "hisBed", "bedNo")).lower()
        if any(cohort.lower() in patient_blob for cohort in cohorts):
            return True
    try:
        percentage = max(0, min(100, int(rollout_cfg.get("enabled_percentage") or 0)))
    except Exception:
        percentage = 0
    if percentage <= 0:
        return not cohorts
    bucket = int(hashlib.sha256(str(patient_id).encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < percentage


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

    @staticmethod
    def _snapshot_value(snapshot: dict, key: str) -> float | None:
        """Read a latest value from the known digital-twin snapshot shapes."""
        row = snapshot.get(key) if isinstance(snapshot, dict) else None
        if not isinstance(row, dict):
            return _safe_float(row)
        for candidate in (
            row.get("current"),
            row.get("latest"),
            (row.get("snapshot") or {}).get("latest") if isinstance(row.get("snapshot"), dict) else None,
            ((row.get("snapshot") or {}).get("latest") or {}).get("latest") if isinstance((row.get("snapshot") or {}).get("latest"), dict) else None,
        ):
            val = _safe_float(candidate)
            if val is not None:
                return val
        return None

    @classmethod
    def _normalize_snapshot(cls, snapshot: dict) -> dict[str, Any]:
        """Normalize cached digital-twin snapshots to the What-if current-state contract."""
        if not isinstance(snapshot, dict):
            return {}
        normalized: dict[str, Any] = {
            "map": {"current": _round(cls._snapshot_value(snapshot, "map"), 0)},
            "hr": {"current": _round(cls._snapshot_value(snapshot, "hr"), 0)},
            "spo2": {"current": _round(cls._snapshot_value(snapshot, "spo2"), 0)},
            "lactate": {"current": _round(cls._snapshot_value(snapshot, "lactate") or cls._snapshot_value(snapshot, "lac"), 1)},
            "fio2": {"current": _round(cls._snapshot_value(snapshot, "fio2"), 0)},
            "peep": {"current": _round(cls._snapshot_value(snapshot, "peep"), 0)},
            "urine_ml_kg_h_6h": _round(cls._snapshot_value(snapshot, "urine_ml_kg_h_6h"), 2),
            "vasoactive_support": {
                "current_dose_ug_kg_min": _round(
                    _safe_float(
                        ((snapshot.get("vasoactive_support") or {}).get("current_dose_ug_kg_min"))
                        if isinstance(snapshot.get("vasoactive_support"), dict)
                        else None
                    ),
                    3,
                )
            },
        }
        return normalized

    @staticmethod
    def _has_any_current(snapshot: dict) -> bool:
        return any(
            _safe_float((snapshot.get(key) or {}).get("current")) is not None
            for key in ("map", "hr", "spo2", "lactate")
            if isinstance(snapshot.get(key), dict)
        )

    @staticmethod
    def _twin_latest(twin: dict, vital_key: str) -> float | None:
        """从 twin snapshot 的 latest/vitals 块提取最新值，兼容多种数据结构。

        注意：vitals.latest 来自 _get_latest_vitals_by_patient，其值为裸 float
        （如 {"hr": 85.0}），不能直接用 (x or {}).get(...)，必须经 _unwrap_current 安全取值。
        """
        # twin.vitals.latest — 值可能是裸 float（来自 _get_latest_vitals_by_patient）
        vitals = twin.get("vitals") or {}
        latest = vitals.get("latest") or {}
        result = _unwrap_current(latest.get(vital_key))
        if result is not None:
            return result
        # twin.snapshot.{key} — 由 _snapshot_value 安全提取
        snap = twin.get("snapshot") or {}
        self_val = SemiMechanisticCounterfactualModel._snapshot_value(snap, vital_key)
        if self_val is not None:
            return self_val
        # twin.snapshot.{key}.snapshot.latest (series_snapshot 深层结构)
        key_snap = snap.get(vital_key)
        if isinstance(key_snap, dict):
            ss = key_snap.get("snapshot") if isinstance(key_snap.get("snapshot"), dict) else key_snap.get("snapshot")
            result = _unwrap_current(ss.get("latest") if isinstance(ss, dict) else None)
            if result is not None:
                return result
        return None

    async def build_snapshot(self, patient_id: str, patient: dict, *, hours: int = 12) -> dict[str, Any]:
        twin_service = PatientDigitalTwinService(db=self.db, alert_engine=self.alert_engine, config=get_config())
        twin = await twin_service.get_or_build_snapshot(patient_id, patient, hours=max(hours, 12), refresh=False, persist=True)
        cached_snapshot = twin.get("snapshot")
        if isinstance(cached_snapshot, dict) and cached_snapshot:
            normalized_cached = self._normalize_snapshot(cached_snapshot)
            if self._has_any_current(normalized_cached):
                return normalized_cached

        # 优先从 twin 的 latest 块提取已查到的生命体征
        twin_map = self._twin_latest(twin, "map")
        twin_hr = self._twin_latest(twin, "hr")
        twin_spo2 = self._twin_latest(twin, "spo2")

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

        # twin ventilator 块的 FiO2/PEEP
        twin_vent = (twin.get("vitals") or {}).get("ventilator") or {}
        twin_vent = twin_vent if isinstance(twin_vent, dict) else {}
        twin_fio2 = _unwrap_current(twin_vent.get("fio2"))
        twin_peep = _unwrap_current(twin_vent.get("peep"))

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

        # bedside series 取不到时，回退到 twin latest 块
        final_map = self._latest_value(merged_map_series, digits=0)
        final_hr = self._latest_value(hr_series, digits=0)
        final_spo2 = self._latest_value(spo2_series, digits=0)
        final_fio2 = self._latest_value(fio2_series, digits=0)
        final_peep = self._latest_value(peep_series, digits=0)
        if final_map is None and twin_map is not None:
            final_map = _round(twin_map, 0)
        if final_hr is None and twin_hr is not None:
            final_hr = _round(twin_hr, 0)
        if final_spo2 is None and twin_spo2 is not None:
            final_spo2 = _round(twin_spo2, 0)
        if final_fio2 is None and twin_fio2 is not None:
            final_fio2 = _round(twin_fio2, 0)
        if final_peep is None and twin_peep is not None:
            final_peep = _round(twin_peep, 0)

        return {
            "map": {"current": final_map},
            "hr": {"current": final_hr},
            "spo2": {"current": final_spo2},
            "lactate": {"current": self._latest_value(lactate_series, digits=1)},
            "fio2": {"current": final_fio2},
            "peep": {"current": final_peep},
            "urine_ml_kg_h_6h": _round(_safe_float(urine_rate), 2),
            "vasoactive_support": {"current_dose_ug_kg_min": current_vaso_dose},
        }

    async def simulate(self, patient_id: str, patient: dict, payload: dict[str, Any]) -> dict[str, Any]:
        intervention_type = str((payload or {}).get("intervention_type") or "vasopressor_up").strip().lower()
        intervention_label = str((payload or {}).get("intervention_label") or intervention_type).strip()
        horizon_minutes = _horizon_minutes(payload)
        dose_delta_pct = _safe_float((payload or {}).get("dose_delta_pct"))
        fluid_bolus_ml = _safe_float((payload or {}).get("fluid_bolus_ml"))
        fio2_delta = _safe_float((payload or {}).get("fio2_delta"))
        peep_delta = _safe_float((payload or {}).get("peep_delta"))
        diuretic_intensity = _safe_float((payload or {}).get("diuretic_intensity"))

        snapshot = await self.build_snapshot(patient_id, patient, hours=12)
        current_map = _unwrap_current(snapshot.get("map"))
        current_hr = _unwrap_current(snapshot.get("hr"))
        current_spo2 = _unwrap_current(snapshot.get("spo2"))
        current_lactate = _unwrap_current(snapshot.get("lactate"))
        current_fio2 = _unwrap_current(snapshot.get("fio2"))
        current_peep = _unwrap_current(snapshot.get("peep"))
        urine_rate = _safe_float(snapshot.get("urine_ml_kg_h_6h"))
        vaso_entry = snapshot.get("vasoactive_support")
        current_vaso = _safe_float(
            vaso_entry.get("current_dose_ug_kg_min")
            if isinstance(vaso_entry, dict)
            else vaso_entry
        )

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

        if intervention_type == "current_baseline":
            assumptions.append("当前基线场景假设治疗维持不变，用于与单一干预分支对比。")
            rationale_bits.append("未施加新增干预，曲线代表当前状态的基线延续。")
            equation_hints.append("Delta = 0")
        elif intervention_type == "vasopressor_up":
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

        data_available = any(v is not None for v in (current_map, current_hr, current_spo2, current_lactate))

        return {
            "intervention_type": intervention_type,
            "intervention_label": intervention_label,
            "data_available": data_available,
            "summary": "；".join(summary_bits or rationale_bits) or ("模拟已生成" if data_available else "当前患者暂无可用生命体征数据，无法执行反事实模拟。"),
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
            "confidence_bands": {
                "map": _bands(_curve(current_map, map_delta_30m, tau_minutes=map_tau, horizon_minutes=horizon_minutes, digits=0), digits=0),
                "spo2": _bands(_curve(current_spo2, spo2_delta_30m, tau_minutes=spo2_tau, horizon_minutes=horizon_minutes, digits=0), digits=0),
                "lactate": _bands(_curve(current_lactate, lactate_delta_30m, tau_minutes=lactate_tau, horizon_minutes=horizon_minutes, digits=1), digits=1),
            },
            "ood_warning": self._ood_warning(current_map=current_map, current_spo2=current_spo2, current_lactate=current_lactate, current_vaso=current_vaso),
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
                "backend": "semi_mechanistic",
                "requested_backend": "semi_mechanistic",
                "degraded": False,
                "fallback_reason": None,
                "model_version": "semi-mechanistic-v1",
                "loaded_at": None,
                "lookback_hours": 12,
                "horizon_minutes": horizon_minutes,
                "equations": equation_hints[:4],
                "note": "采用半机制 Emax/容量反应性/复张-回流耦合模型；如需真正论文级 PK/PD，需要基于本院连续时序数据完成参数辨识与外部验证。",
            },
        }

    def _ood_warning(self, *, current_map: float | None, current_spo2: float | None, current_lactate: float | None, current_vaso: float | None) -> dict[str, Any]:
        reasons = []
        if current_map is not None and (current_map < 45 or current_map > 130):
            reasons.append("MAP 超出常见训练范围")
        if current_spo2 is not None and current_spo2 < 80:
            reasons.append("SpO2 极低")
        if current_lactate is not None and current_lactate > 12:
            reasons.append("乳酸极高")
        if current_vaso is not None and current_vaso > 1.0:
            reasons.append("血管活性药剂量极高")
        return {"is_ood": bool(reasons), "method": "range_check_v1", "reasons": reasons}


class TransformerCounterfactualModel:
    """Lazy Torch G-Net/TE-CDE counterfactual runtime with semi-mechanistic fallback."""

    def __init__(self, *, db, alert_engine, config=None, fallback_model: SemiMechanisticCounterfactualModel | None = None, allow_fallback: bool = True) -> None:
        self.db = db
        self.alert_engine = alert_engine
        self.config = config or get_config()
        self.fallback_model = fallback_model or SemiMechanisticCounterfactualModel(db=db, alert_engine=alert_engine)
        self.allow_fallback = bool(allow_fallback)
        self._loaded = False
        self._torch: Any = None
        self._model: Any = None
        self._model_path: Path | None = None
        self._unavailable_reason = ""
        self._fallback_reason_code: str | None = None
        self._loaded_at: datetime | None = None
        self._device = "cpu"

    def _model_dir(self) -> Path:
        return local_model_dir(self.config, "counterfactual_dir", "counterfactual")

    def _candidate_paths(self) -> list[Path]:
        root = self._model_dir()
        return [root / name for name in ("model.pt", "g_net.pt", "te_cde.pt", "counterfactual.pt", "model.pth")]

    def _set_unavailable(self, code: str, reason: str) -> None:
        self._fallback_reason_code = code
        self._unavailable_reason = reason

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            import torch  # type: ignore
        except Exception as exc:
            self._set_unavailable("torch_unavailable", f"torch unavailable: {exc.__class__.__name__}: {str(exc)[:160]}")
            return
        self._torch = torch
        for path in self._candidate_paths():
            if not path.exists():
                continue
            try:
                self._model_path = path
                try:
                    self._model = torch.jit.load(str(path), map_location=self._device)
                except Exception:
                    self._model = torch.load(str(path), map_location=self._device)
                if hasattr(self._model, "eval"):
                    self._model.eval()
                self._unavailable_reason = ""
                self._fallback_reason_code = None
                self._loaded_at = datetime.now()
                return
            except Exception as exc:
                self._model = None
                self._set_unavailable("inference_error", f"load failed: {exc.__class__.__name__}: {str(exc)[:120]}")
                return
        self._set_unavailable("weights_missing", f"no torch weight found under {self._model_dir()}")

    def status(self) -> dict[str, Any]:
        if not self._loaded:
            self._ensure_loaded()
        return {
            "available": bool(self._model is not None),
            "reason": self._unavailable_reason,
            "reason_code": self._fallback_reason_code,
            "backend": "transformer",
            "model_path": str(self._model_path or ""),
            "model_version": self._model_path.stem if self._model_path else "",
            "loaded_at": self._loaded_at,
        }

    def _feature_vector(self, snapshot: dict[str, Any], payload: dict[str, Any]) -> list[float]:
        vaso_entry = snapshot.get("vasoactive_support")
        vaso_val = (
            _safe_float(vaso_entry.get("current_dose_ug_kg_min"))
            if isinstance(vaso_entry, dict)
            else _safe_float(vaso_entry)
        )
        values = [
            _unwrap_current(snapshot.get("map")) or 0.0,
            _unwrap_current(snapshot.get("hr")) or 0.0,
            _unwrap_current(snapshot.get("spo2")) or 0.0,
            _unwrap_current(snapshot.get("lactate")) or 0.0,
            _unwrap_current(snapshot.get("fio2")) or 0.0,
            _unwrap_current(snapshot.get("peep")) or 0.0,
            _safe_float(snapshot.get("urine_ml_kg_h_6h")) or 0.0,
            vaso_val or 0.0,
            _safe_float(payload.get("dose_delta_pct")) or 0.0,
            _safe_float(payload.get("fluid_bolus_ml")) or 0.0,
            _safe_float(payload.get("fio2_delta")) or 0.0,
            _safe_float(payload.get("peep_delta")) or 0.0,
            _safe_float(payload.get("diuretic_intensity")) or 0.0,
        ]
        return values + [0.0] * (32 - len(values))

    def _run_model(self, snapshot: dict[str, Any], payload: dict[str, Any]) -> dict[str, float]:
        self._ensure_loaded()
        if self._model is None or self._torch is None:
            raise RuntimeError(self._fallback_reason_code or self._unavailable_reason or "counterfactual transformer unavailable")
        features = self._feature_vector(snapshot, payload)
        try:
            with self._torch.no_grad():
                tensor = self._torch.tensor(features, dtype=self._torch.float32).unsqueeze(0)
                if hasattr(self._model, "simulate"):
                    output = self._model.simulate(tensor)
                else:
                    output = self._model(tensor)
                arr = output.detach().cpu().numpy().reshape(-1).astype(float)
        except Exception as exc:
            raise RuntimeError(f"inference_error: {exc.__class__.__name__}") from exc
        if arr.size < 4:
            raise ValueError(f"shape_mismatch: expected >=4 values, got {arr.shape}")
        return {"map_30m": float(arr[0]), "hr_30m": float(arr[1]), "spo2_30m": float(arr[2]), "lactate_30m": float(arr[3])}

    @staticmethod
    def _reason_code(exc: Exception) -> str:
        text = str(exc)
        for code in ("weights_missing", "torch_unavailable", "shape_mismatch", "inference_error"):
            if code in text:
                return code
        return "inference_error"

    async def simulate(self, patient_id: str, patient: dict, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            snapshot = await self.fallback_model.build_snapshot(patient_id, patient, hours=12)
            deltas = self._run_model(snapshot, payload or {})
            base = await self.fallback_model.simulate(patient_id, patient, payload or {})
            current = base.get("current_state") or {}
            projected = {
                "map_30m": _round((_safe_float(current.get("map")) or 0.0) + deltas["map_30m"] if current.get("map") is not None else None, 0),
                "hr_30m": _round((_safe_float(current.get("hr")) or 0.0) + deltas["hr_30m"] if current.get("hr") is not None else None, 0),
                "spo2_30m": _round((_safe_float(current.get("spo2")) or 0.0) + deltas["spo2_30m"] if current.get("spo2") is not None else None, 0),
                "lactate_30m": _round((_safe_float(current.get("lactate")) or 0.0) + deltas["lactate_30m"] if current.get("lactate") is not None else None, 1),
            }
            horizon = _horizon_minutes(payload)
            base["projected_state"] = projected
            base["delta"] = {key: _round(value, 2 if "lactate" in key else 1) for key, value in deltas.items()}
            base["response_curve"] = {
                "map": _curve(_safe_float(current.get("map")), deltas["map_30m"], tau_minutes=10, horizon_minutes=horizon, digits=0),
                "spo2": _curve(_safe_float(current.get("spo2")), deltas["spo2_30m"], tau_minutes=10, horizon_minutes=horizon, digits=0),
                "lactate": _curve(_safe_float(current.get("lactate")), deltas["lactate_30m"], tau_minutes=24, horizon_minutes=horizon, digits=1),
            }
            base["confidence_bands"] = {
                "map": _bands(base["response_curve"]["map"], digits=0),
                "spo2": _bands(base["response_curve"]["spo2"], digits=0),
                "lactate": _bands(base["response_curve"]["lactate"], digits=1),
            }
            status = self.status()
            base["model_meta"] = {
                **(base.get("model_meta") or {}),
                "kind": "transformer_counterfactual_model",
                "backend": "transformer",
                "requested_backend": "transformer",
                "degraded": False,
                "fallback_reason": None,
                "model_version": status.get("model_version") or "counterfactual-transformer",
                "loaded_at": status.get("loaded_at"),
                "model_path": status.get("model_path") or "",
            }
            return base
        except Exception as exc:
            if not self.allow_fallback:
                raise
            result = await self.fallback_model.simulate(patient_id, patient, payload or {})
            result["model_meta"] = {
                **(result.get("model_meta") or {}),
                "backend": "semi_mechanistic",
                "requested_backend": "transformer",
                "degraded": True,
                "fallback_reason": self._reason_code(exc),
                "fallback_detail": str(exc)[:180],
                "model_version": "semi-mechanistic-v1",
                "loaded_at": None,
            }
            return result


def get_counterfactual_model(*, db, alert_engine, config=None):
    cfg = config or get_config()
    ai = (getattr(cfg, "yaml_cfg", {}) or {}).get("ai_service", {})
    counterfactual_cfg = (ai.get("counterfactual") if isinstance(ai, dict) else {}) or {}
    backend = str(counterfactual_cfg.get("backend") or "auto").strip().lower()
    allow_fallback = bool(counterfactual_cfg.get("allow_fallback", True))
    fallback = SemiMechanisticCounterfactualModel(db=db, alert_engine=alert_engine)
    if backend in {"semi_mechanistic", "semi", "fallback"}:
        return fallback
    if backend in {"auto", "transformer"}:
        return TransformerCounterfactualModel(db=db, alert_engine=alert_engine, config=cfg, fallback_model=fallback, allow_fallback=allow_fallback)
    return fallback


async def simulate_counterfactual(*, db, alert_engine, config=None, patient_id: str, patient: dict, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = config or get_config()
    ai = (getattr(cfg, "yaml_cfg", {}) or {}).get("ai_service", {})
    counterfactual_cfg = (ai.get("counterfactual") if isinstance(ai, dict) else {}) or {}
    rollout_cfg = counterfactual_cfg.get("transformer_rollout") if isinstance(counterfactual_cfg.get("transformer_rollout"), dict) else {}
    backend = str(counterfactual_cfg.get("backend") or "auto").strip().lower()
    if backend in {"auto", "transformer"} and rollout_cfg and not _cohort_enabled(patient, patient_id, rollout_cfg):
        model = SemiMechanisticCounterfactualModel(db=db, alert_engine=alert_engine)
        result = await model.simulate(patient_id, patient, payload or {})
        result["model_meta"] = {
            **(result.get("model_meta") or {}),
            "requested_backend": backend,
            "degraded": False,
            "fallback_reason": "rollout_not_enabled",
        }
        return result
    model = get_counterfactual_model(db=db, alert_engine=alert_engine, config=cfg)
    return await model.simulate(patient_id, patient, payload or {})
