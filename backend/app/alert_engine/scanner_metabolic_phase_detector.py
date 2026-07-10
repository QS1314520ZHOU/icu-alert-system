from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .scanners import BaseScanner, ScannerSpec


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).strip())
    if not match:
        return None
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None


class MetabolicPhaseDetectorScanner(BaseScanner):
    """危重患者代谢阶段与营养时机识别。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="metabolic_phase_detector",
                interval_key="metabolic_phase_detector",
                default_interval=3600,
                initial_delay=102,
            ),
        )

    def is_enabled(self) -> bool:
        return super().is_enabled() and bool(self._cfg().get("enabled", True))

    def interval_seconds(self) -> int:
        value = self._cfg().get("scan_interval")
        try:
            return max(300, int(value))
        except (TypeError, ValueError):
            return super().interval_seconds()

    def _cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "metabolic_phase_detector", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        patients = await self._target_patients(patient_id)
        if not patients:
            return []
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        alerts: list[dict[str, Any]] = []
        for patient_doc in patients:
            alerts.extend(await self._scan_patient(patient_doc=patient_doc, now=now, same_rule_sec=same_rule_sec, max_per_hour=max_per_hour))
        if alerts:
            self.engine._log_info("代谢阶段检测", len(alerts))
        return alerts

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        projection = {
            "_id": 1,
            "name": 1,
            "hisPid": 1,
            "hisBed": 1,
            "dept": 1,
            "hisDept": 1,
            "weight": 1,
            "bodyWeight": 1,
            "body_weight": 1,
            "weightKg": 1,
            "weight_kg": 1,
            "icuAdmissionTime": 1,
            "admissionTime": 1,
            "inTime": 1,
            "admitTime": 1,
            "current_profile": 1,
        }
        if patient_id:
            patient_doc, _ = await self.engine._load_patient(patient_id)
            return [patient_doc] if isinstance(patient_doc, dict) else []
        cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), projection)
        return [row async for row in cursor]

    async def _scan_patient(self, *, patient_doc: dict[str, Any], now: datetime, same_rule_sec: int, max_per_hour: int) -> list[dict[str, Any]]:
        patient_id = patient_doc.get("_id")
        if not patient_id:
            return []
        patient_id_str = str(patient_id)
        weight_kg = self.engine._get_patient_weight(patient_doc)
        if not weight_kg:
            return []
        state = await self._collect_state(patient_doc=patient_doc, patient_id=patient_id, weight_kg=weight_kg, now=now)
        phase_result = self._score_phases(state)
        previous = await self.engine.db.col("score").find_one(
            {"patient_id": patient_id_str, "score_type": "metabolic_phase_detector"},
            sort=[("calc_time", -1)],
        )
        phase_result["previous_phase"] = str((previous or {}).get("phase") or "")
        phase_result["transition_detected"] = phase_result.get("previous_phase") == "ebb" and phase_result.get("phase") == "transition"
        record = await self._persist_phase(patient_doc=patient_doc, state=state, phase_result=phase_result, now=now)
        phase_result["record_id"] = record.get("_id")

        alerts: list[dict[str, Any]] = []
        if phase_result.get("transition_detected"):
            if not await self.engine._is_suppressed(patient_id_str, "METABOLIC_PHASE_TRANSITION", same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id="METABOLIC_PHASE_TRANSITION",
                    name="代谢转变检测",
                    category="nutrition_monitor",
                    alert_type="metabolic_phase_transition",
                    severity="warning",
                    parameter="metabolic_phase",
                    condition={"from": "ebb", "to": "transition"},
                    value=round(float(phase_result.get("phase_scores", {}).get("transition") or 0.0), 1),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": "代谢阶段由急性分解期向稳定过渡期转变，提示可开始逐步增加营养供给。",
                        "evidence": self._phase_evidence_lines(phase_result, "transition"),
                        "suggestion": "建议将热卡逐步提升至 20-25 kcal/kg/d，蛋白提升至 1.0-1.3 g/kg/d，并继续动态观察乳酸、SOFA 与血糖波动。",
                        "text": "",
                    },
                    extra={"detail": {"phase_result": phase_result, "state": state}},
                )
                if alert:
                    alerts.append(alert)

        mismatch = phase_result.get("nutrition_mismatch") if isinstance(phase_result.get("nutrition_mismatch"), dict) else {}
        if mismatch.get("trigger"):
            if not await self.engine._is_suppressed(patient_id_str, "METABOLIC_PHASE_NUTRITION_MISMATCH", same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id="METABOLIC_PHASE_NUTRITION_MISMATCH",
                    name="当前营养供给与代谢阶段不匹配",
                    category="nutrition_monitor",
                    alert_type="metabolic_phase_nutrition_mismatch",
                    severity="high",
                    parameter="metabolic_phase_nutrition_match",
                    condition={"phase": phase_result.get("phase")},
                    value=round(float(mismatch.get("kcal_gap_pct") or 0.0), 1),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": f"当前处于{self._phase_label(str(phase_result.get('phase') or ''))}，但实际营养供给与推荐窗口不匹配。",
                        "evidence": mismatch.get("evidence") or [],
                        "suggestion": mismatch.get("recommendation") or "建议结合代谢阶段调整热卡与蛋白供给。",
                        "text": "",
                    },
                    extra={"detail": {"phase_result": phase_result, "state": state, "nutrition_mismatch": mismatch}},
                )
                if alert:
                    alerts.append(alert)

        return alerts

    async def _collect_state(self, *, patient_doc: dict[str, Any], patient_id: Any, weight_kg: float, now: datetime) -> dict[str, Any]:
        cfg = self._cfg()
        his_pid = str(patient_doc.get("hisPid") or "").strip()
        admission_t = self.engine._admission_time(patient_doc) if hasattr(self.engine, "_admission_time") else None
        icu_days = max(1.0, round((now - admission_t).total_seconds() / 86400.0, 2)) if isinstance(admission_t, datetime) else None
        labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=96) if his_pid else {}
        glucose_points = []
        glucose_codes = self.engine._get_cfg_list(("alert_engine", "data_mapping", "glucose", "codes"), ["param_blood_glucose", "param_glu"])
        glucose_points.extend(await self.engine._get_bedside_glucose_points(str(patient_id), now - timedelta(hours=24), glucose_codes))
        if his_pid:
            glucose_points.extend(await self.engine._get_lab_glucose_points(his_pid, now - timedelta(hours=24)))
        glucose_points.sort(key=lambda row: row.get("time"))
        glucose_cv = self.engine._calc_cv_percent([float(row.get("value")) for row in glucose_points if row.get("value") is not None]) if glucose_points else None

        insulin_keywords = self.engine._get_cfg_list(("alert_engine", "glycemic_control", "insulin_keywords"), ["胰岛素", "insulin"])
        insulin_docs = await self.engine._get_drug_records(str(patient_id), now - timedelta(hours=24))
        insulin_active = len([doc for doc in insulin_docs if self.engine._is_insulin_doc(doc, insulin_keywords)]) > 0

        nutrition_events = await self.engine._get_nutrition_drug_events(str(patient_id), now - timedelta(hours=48), cfg) if hasattr(self.engine, "_get_nutrition_drug_events") else []
        kcal_24h = round(sum(float(item.get("kcal") or 0.0) for item in nutrition_events if isinstance(item.get("time"), datetime) and item["time"] >= now - timedelta(hours=24)), 2)
        protein_24h = round(sum(self._estimate_protein_g((item.get("raw") or {})) or 0.0 for item in nutrition_events if isinstance(item.get("time"), datetime) and item["time"] >= now - timedelta(hours=24)), 2)
        kcal_kg_day = round(kcal_24h / weight_kg, 2) if weight_kg > 0 else None
        protein_kg_day = round(protein_24h / weight_kg, 2) if weight_kg > 0 and protein_24h > 0 else None

        crp_series = await self._raw_lab_series(his_pid, self._keywords("crp", ["crp", "c反应蛋白"]), now - timedelta(days=7)) if his_pid else []
        prealbumin_series = await self._raw_lab_series(his_pid, self._keywords("prealbumin", ["前白蛋白", "prealbumin", "pab"]), now - timedelta(days=7)) if his_pid else []
        bun_series = await self._raw_lab_series(his_pid, self._keywords("bun", ["尿素氮", "bun", "urea nitrogen"]), now - timedelta(days=7)) if his_pid else []

        sofa = await self.engine._calc_sofa(patient_doc, patient_id, await self.engine._get_device_id_for_patient(patient_doc, ["monitor", "vent"]), his_pid) if his_pid else None
        previous_sofa = await self.engine.db.col("score").find_one({"patient_id": str(patient_id), "score_type": {"$in": ["sofa", "sepsis_sofa", "sofa_score"]}}, sort=[("calc_time", -1)])
        current_sofa = _to_float((sofa or {}).get("score"))
        previous_sofa_value = None
        if isinstance(previous_sofa, dict):
            for key in ("score", "sofa_score", "value", "score_value"):
                previous_sofa_value = _to_float(previous_sofa.get(key))
                if previous_sofa_value is not None:
                    break

        current_vasopressors = await self.engine._get_current_vasopressor_snapshot(patient_id, patient_doc, hours=12, max_items=4)
        nurse_cfg = self.engine.config.yaml_cfg.get("nurse_reminders", {}).get("early_mobility", {})
        norepi_keywords = nurse_cfg.get("norepi_keywords", ["去甲肾上腺素", "norepinephrine", "noradrenaline", "去甲"])
        norepi_series = await self.engine._get_norepi_dose_series(str(patient_id), now, float(cfg.get("vasopressor_lookback_hours", 12) or 12), norepi_keywords, weight_kg)
        spontaneous_activity = bool(await self.engine._get_last_activity_time(str(patient_id), now, float(cfg.get("activity_lookback_hours", 48) or 48), cfg.get("activity_keywords", ["活动", "下床", "坐起", "床边活动", "康复"])) if hasattr(self.engine, "_get_last_activity_time") else False)

        return {
            "weight_kg": weight_kg,
            "icu_days": icu_days,
            "lactate": _to_float(((labs.get("lac") or {}).get("value")) if isinstance(labs.get("lac"), dict) else None),
            "glucose_cv": glucose_cv,
            "insulin_active": insulin_active,
            "crp_series": crp_series,
            "prealbumin_series": prealbumin_series,
            "bun_series": bun_series,
            "current_sofa": current_sofa,
            "previous_sofa": previous_sofa_value,
            "current_vasopressors": current_vasopressors,
            "norepi_series": norepi_series,
            "spontaneous_activity": spontaneous_activity,
            "kcal_24h": kcal_24h,
            "protein_24h": protein_24h,
            "kcal_kg_day": kcal_kg_day,
            "protein_kg_day": protein_kg_day,
        }

    def _keywords(self, key: str, default: list[str]) -> list[str]:
        raw = self._cfg().get("lab_keywords", {})
        if isinstance(raw, dict) and isinstance(raw.get(key), list):
            values = [str(item).strip() for item in raw.get(key) if str(item).strip()]
            if values:
                return values
        return default

    async def _raw_lab_series(self, his_pid: str, keywords: list[str], since: datetime) -> list[dict[str, Any]]:
        cursor = self.engine.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(1200)
        rows: list[dict[str, Any]] = []
        lowered = [str(item).lower() for item in keywords if str(item).strip()]
        async for doc in cursor:
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").lower()
            if not name or not any(keyword in name for keyword in lowered):
                continue
            raw_time = doc.get("authTime") or doc.get("collectTime") or doc.get("reportTime") or doc.get("time")
            time_value = raw_time if isinstance(raw_time, datetime) else None
            if not isinstance(time_value, datetime) or time_value < since:
                continue
            value = _to_float(doc.get("result") or doc.get("resultValue") or doc.get("value"))
            if value is None:
                continue
            rows.append({"time": time_value, "value": float(value), "name": name, "unit": str(doc.get("unit") or doc.get("resultUnit") or "")})
        rows.sort(key=lambda row: row["time"])
        return rows

    def _estimate_protein_g(self, doc: dict[str, Any]) -> float | None:
        for key in ("protein", "proteinG", "aminoAcid", "aminoAcidG", "totalProtein"):
            value = _to_float(doc.get(key))
            if value is not None and value > 0:
                return round(value, 2)
        nitrogen = _to_float(doc.get("nitrogen") or doc.get("nitrogenG"))
        if nitrogen is not None and nitrogen > 0:
            return round(nitrogen * 6.25, 2)
        text = " ".join(str(doc.get(key) or "") for key in ("drugName", "orderName", "drugSpec", "remark"))
        match = re.search(r"(\d+(?:\.\d+)?)\s*g\s*(?:蛋白|protein|amino)", text, flags=re.I)
        if match:
            value = _to_float(match.group(1))
            return round(value, 2) if value is not None else None
        return None

    def _series_latest(self, rows: list[dict[str, Any]]) -> float | None:
        return float(rows[-1]["value"]) if rows else None

    def _series_delta(self, rows: list[dict[str, Any]]) -> float | None:
        if len(rows) < 2:
            return None
        return round(float(rows[-1]["value"]) - float(rows[0]["value"]), 3)

    def _score_phases(self, state: dict[str, Any]) -> dict[str, Any]:
        cfg = self._cfg()
        thresholds = cfg.get("thresholds", {}) if isinstance(cfg.get("thresholds"), dict) else {}
        phase_weights = cfg.get("phase_weights", {}) if isinstance(cfg.get("phase_weights"), dict) else {}

        norepi_series = state.get("norepi_series") if isinstance(state.get("norepi_series"), list) else []
        vasopressor_use = bool(state.get("current_vasopressors"))
        vasopressor_weaning = bool(norepi_series and self.engine._is_series_tapering(norepi_series, float(thresholds.get("vasopressor_taper_ratio", 0.1) or 0.1)))
        crp_delta = self._series_delta(state.get("crp_series") if isinstance(state.get("crp_series"), list) else [])
        prealbumin_delta = self._series_delta(state.get("prealbumin_series") if isinstance(state.get("prealbumin_series"), list) else [])
        bun_delta = self._series_delta(state.get("bun_series") if isinstance(state.get("bun_series"), list) else [])
        bun_latest = self._series_latest(state.get("bun_series") if isinstance(state.get("bun_series"), list) else [])
        current_sofa = _to_float(state.get("current_sofa"))
        previous_sofa = _to_float(state.get("previous_sofa"))
        phase_features = {
            "ebb": {
                "lactate_elevated": bool((_to_float(state.get("lactate")) or 0) > float(thresholds.get("lactate_elevated", 2.0) or 2.0)),
                "glucose_cv_high": bool((_to_float(state.get("glucose_cv")) or 0) > float(thresholds.get("glucose_cv_high", 36) or 36)),
                "crp_rising": bool((crp_delta or 0) > float(thresholds.get("crp_rising_delta", 5) or 5)),
                "sofa_unstable": bool(current_sofa is not None and ((previous_sofa is None) or current_sofa >= previous_sofa + float(thresholds.get("sofa_unstable_delta", 1) or 1))),
                "bun_generation_high": bool(((bun_latest or 0) > float(thresholds.get("bun_high_threshold", 12) or 12)) or ((bun_delta or 0) > float(thresholds.get("bun_daily_rise_threshold", 2) or 2))),
                "vasopressor_use": vasopressor_use,
            },
            "transition": {
                "lactate_normalizing": bool((_to_float(state.get("lactate")) or 99) <= float(thresholds.get("lactate_normalizing", 2.0) or 2.0)),
                "glucose_stabilizing": bool((_to_float(state.get("glucose_cv")) or 999) <= float(thresholds.get("glucose_stabilizing_cv", 30) or 30)),
                "crp_falling": bool((crp_delta or 0) < -abs(float(thresholds.get("crp_falling_delta", 5) or 5))),
                "sofa_stable_or_falling": bool(current_sofa is not None and previous_sofa is not None and current_sofa <= previous_sofa),
                "vasopressor_weaning": vasopressor_weaning,
            },
            "anabolic": {
                "crp_normal": bool((self._series_latest(state.get("crp_series") if isinstance(state.get("crp_series"), list) else []) or 999) <= float(thresholds.get("crp_normal_threshold", 10) or 10)),
                "prealbumin_rising": bool((prealbumin_delta or 0) >= float(thresholds.get("prealbumin_rise_delta", 2) or 2)),
                "sofa_low": bool(current_sofa is not None and current_sofa <= float(thresholds.get("sofa_low", 3) or 3)),
                "no_vasopressor": not vasopressor_use,
                "spontaneous_activity": bool(state.get("spontaneous_activity")),
                "positive_nitrogen": bool((prealbumin_delta or 0) >= float(thresholds.get("prealbumin_rise_delta", 2) or 2) and not vasopressor_use and (_to_float(state.get("protein_kg_day")) or 0) >= float(thresholds.get("positive_nitrogen_protein_floor", 1.2) or 1.2)),
            },
        }

        phase_scores: dict[str, float] = {}
        for phase, features in phase_features.items():
            weights = phase_weights.get(phase, {}) if isinstance(phase_weights.get(phase), dict) else {}
            total_weight = sum(float(value) for value in weights.values()) or 1.0
            matched_weight = sum(float(weights.get(name, 0.0)) for name, matched in features.items() if matched)
            phase_scores[phase] = round((matched_weight / total_weight) * 100.0, 2)

        phase = max(phase_scores, key=phase_scores.get)
        kcal_targets = cfg.get("calorie_targets", {}) if isinstance(cfg.get("calorie_targets"), dict) else {}
        protein_targets = cfg.get("protein_targets", {}) if isinstance(cfg.get("protein_targets"), dict) else {}
        kcal_target = kcal_targets.get(phase, [None, None])
        protein_target = protein_targets.get(phase, [None, None])
        kcal_actual = _to_float(state.get("kcal_kg_day"))
        protein_actual = _to_float(state.get("protein_kg_day"))
        kcal_lower = _to_float(kcal_target[0] if isinstance(kcal_target, list) and kcal_target else None)
        kcal_upper = _to_float(kcal_target[1] if isinstance(kcal_target, list) and len(kcal_target) > 1 else None)
        protein_lower = _to_float(protein_target[0] if isinstance(protein_target, list) and protein_target else None)
        protein_upper = _to_float(protein_target[1] if isinstance(protein_target, list) and len(protein_target) > 1 else None)
        mismatch_evidence: list[str] = []
        kcal_gap_pct = 0.0
        mismatch = False
        if kcal_actual is not None and kcal_lower is not None and kcal_upper is not None and not (kcal_lower <= kcal_actual <= kcal_upper):
            mismatch = True
            if kcal_actual < kcal_lower:
                kcal_gap_pct = round(((kcal_lower - kcal_actual) / max(kcal_lower, 1e-6)) * 100.0, 1)
                mismatch_evidence.append(f"实际热卡 {kcal_actual} kcal/kg/d 低于推荐 {kcal_lower}-{kcal_upper}")
            else:
                kcal_gap_pct = round(((kcal_actual - kcal_upper) / max(kcal_upper, 1e-6)) * 100.0, 1)
                mismatch_evidence.append(f"实际热卡 {kcal_actual} kcal/kg/d 高于推荐 {kcal_lower}-{kcal_upper}")
        if protein_actual is not None and protein_lower is not None and protein_upper is not None and not (protein_lower <= protein_actual <= protein_upper):
            mismatch = True
            mismatch_evidence.append(f"实际蛋白 {protein_actual} g/kg/d 偏离推荐 {protein_lower}-{protein_upper}")
        recommendation = f"当前建议热卡 {kcal_lower}-{kcal_upper} kcal/kg/d，蛋白 {protein_lower}-{protein_upper} g/kg/d。"
        return {
            "phase": phase,
            "phase_label": self._phase_label(phase),
            "phase_scores": phase_scores,
            "phase_features": phase_features,
            "nutrition_target": {"kcal": kcal_target, "protein": protein_target},
            "nutrition_mismatch": {
                "trigger": mismatch,
                "kcal_gap_pct": kcal_gap_pct,
                "evidence": mismatch_evidence,
                "recommendation": recommendation,
            },
        }

    def _phase_label(self, phase: str) -> str:
        return {
            "ebb": "急性分解期",
            "transition": "稳定过渡期",
            "anabolic": "合成代谢期",
        }.get(phase, phase)

    def _phase_evidence_lines(self, phase_result: dict[str, Any], phase: str) -> list[str]:
        features = (phase_result.get("phase_features") or {}).get(phase, {})
        return [name for name, matched in features.items() if matched][:5]

    async def _persist_phase(self, *, patient_doc: dict[str, Any], state: dict[str, Any], phase_result: dict[str, Any], now: datetime) -> dict[str, Any]:
        patient_id_str = str(patient_doc.get("_id") or "")
        doc = {
            "patient_id": patient_id_str,
            "patient_name": patient_doc.get("name") or "",
            "bed": patient_doc.get("hisBed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
            "score_type": "metabolic_phase_detector",
            "phase": phase_result.get("phase"),
            "phase_label": phase_result.get("phase_label"),
            "phase_scores": phase_result.get("phase_scores") or {},
            "phase_features": phase_result.get("phase_features") or {},
            "nutrition_target": phase_result.get("nutrition_target") or {},
            "nutrition_mismatch": phase_result.get("nutrition_mismatch") or {},
            "state": state,
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        result = await self.engine.db.col("score").insert_one(doc)
        doc["_id"] = result.inserted_id
        await self.engine.db.col("patient").update_one(
            {"_id": patient_doc.get("_id")},
            {
                "$set": {
                    "current_profile.metabolic_phase": {
                        "phase": phase_result.get("phase"),
                        "phase_label": phase_result.get("phase_label"),
                        "phase_scores": phase_result.get("phase_scores") or {},
                        "nutrition_target": phase_result.get("nutrition_target") or {},
                        "nutrition_mismatch": phase_result.get("nutrition_mismatch") or {},
                        "updated_at": now,
                        "record_id": result.inserted_id,
                    }
                }
            },
        )
        return doc
