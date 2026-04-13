from __future__ import annotations

import math
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


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    peak = max(scores.values())
    weights = {key: math.exp(value - peak) for key, value in scores.items()}
    total = sum(weights.values()) or 1.0
    return {key: round(weight / total, 4) for key, weight in weights.items()}


class SepsisSubphenotypeScanner(BaseScanner):
    """脓毒症亚表型独立扫描器。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="sepsis_subphenotype",
                interval_key="sepsis_subphenotype",
                default_interval=3600,
                initial_delay=83,
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
        cfg = self.engine._cfg("alert_engine", "sepsis_subphenotype", default={}) or {}
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
            self.engine._log_info("脓毒症亚表型", len(alerts))
        return alerts

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        projection = {
            "_id": 1,
            "name": 1,
            "hisPid": 1,
            "hisBed": 1,
            "dept": 1,
            "hisDept": 1,
            "clinicalDiagnosis": 1,
            "admissionDiagnosis": 1,
            "current_profile": 1,
        }
        if patient_id:
            patient_doc, _ = await self.engine._load_patient(patient_id)
            return [patient_doc] if isinstance(patient_doc, dict) else []
        cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), projection)
        return [row async for row in cursor]

    async def _scan_patient(self, *, patient_doc: dict[str, Any], now: datetime, same_rule_sec: int, max_per_hour: int) -> list[dict[str, Any]]:
        patient_id = patient_doc.get("_id")
        his_pid = str(patient_doc.get("hisPid") or "").strip()
        if not patient_id or not his_pid:
            return []
        patient_id_str = str(patient_id)
        if not await self._is_sepsis_candidate(patient_doc, patient_id_str, now):
            return []

        profile = await self._build_profile(patient_doc=patient_doc, patient_id=patient_id, his_pid=his_pid, now=now)
        if not profile:
            return []
        previous = await self.engine.db.col("score").find_one(
            {
                "patient_id": patient_id_str,
                "score_type": "sepsis_subphenotype_profile",
                "calc_time": {"$gte": now - timedelta(hours=float(self._cfg().get("transition_detection_hours", 12) or 12))},
            },
            sort=[("calc_time", -1)],
        )
        transition = self._transition(previous, profile)
        if transition:
            profile["transition"] = transition

        record = await self._persist_profile(patient_doc=patient_doc, profile=profile, now=now)
        alerts: list[dict[str, Any]] = []
        assigned = profile.get("assigned_label")
        if transition and not await self.engine._is_suppressed(patient_id_str, "SEPSIS_SUBPHENOTYPE_TRANSITION", same_rule_sec, max_per_hour):
            alert = await self.engine._create_alert(
                rule_id="SEPSIS_SUBPHENOTYPE_TRANSITION",
                name="脓毒症亚型转换",
                category="syndrome",
                alert_type="sepsis_subphenotype",
                severity="critical",
                parameter="subphenotype_transition",
                condition={"from": transition.get("from"), "to": transition.get("to")},
                value=round(float((transition.get("to_confidence") or 0.0) * 100.0), 1),
                patient_id=patient_id_str,
                patient_doc=patient_doc,
                device_id=None,
                source_time=now,
                explanation={
                    "summary": f"检测到亚型由 {transition.get('from_label')} 转为 {transition.get('to_label')}，提示宿主反应状态正在切换。",
                    "evidence": profile.get("evidence") or [],
                    "suggestion": "亚型转换检测到，免疫状态可能正在切换，建议紧急重新评估治疗方案。",
                    "text": "",
                },
                extra={"detail": record},
            )
            if alert:
                alerts.append(alert)
        elif assigned == "alpha_hyperinflammatory":
            if not await self.engine._is_suppressed(patient_id_str, "SEPSIS_SUBPHENOTYPE_ALPHA", same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id="SEPSIS_SUBPHENOTYPE_ALPHA",
                    name="脓毒症高炎症亚型",
                    category="syndrome",
                    alert_type="sepsis_subphenotype",
                    severity="warning",
                    parameter="subphenotype_probability",
                    condition={"subphenotype": assigned},
                    value=round(float(profile.get("confidence") or 0.0) * 100.0, 1),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": f"该患者属于高炎症亚型(概率{round(float(profile.get('confidence') or 0.0) * 100.0, 1)}%)。",
                        "evidence": profile.get("evidence") or [],
                        "suggestion": "该患者属于高炎症亚型，可能从糖皮质激素中获益，建议评估氢化可的松使用指征。",
                        "text": "",
                    },
                    extra={"detail": record},
                )
                if alert:
                    alerts.append(alert)
        elif assigned == "beta_immunosuppressed":
            if not await self.engine._is_suppressed(patient_id_str, "SEPSIS_SUBPHENOTYPE_BETA", same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id="SEPSIS_SUBPHENOTYPE_BETA",
                    name="脓毒症免疫抑制亚型",
                    category="syndrome",
                    alert_type="sepsis_subphenotype",
                    severity="high",
                    parameter="subphenotype_probability",
                    condition={"subphenotype": assigned},
                    value=round(float(profile.get("confidence") or 0.0) * 100.0, 1),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": f"该患者属于免疫抑制亚型(概率{round(float(profile.get('confidence') or 0.0) * 100.0, 1)}%)。",
                        "evidence": profile.get("evidence") or [],
                        "suggestion": "该患者属于免疫抑制亚型，淋巴细胞计数持续低下，建议评估免疫增强治疗（如 IFN-γ、胸腺肽）。",
                        "text": "",
                    },
                    extra={"detail": record},
                )
                if alert:
                    alerts.append(alert)
        elif assigned == "gamma_hypercoagulable":
            if not await self.engine._is_suppressed(patient_id_str, "SEPSIS_SUBPHENOTYPE_GAMMA", same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id="SEPSIS_SUBPHENOTYPE_GAMMA",
                    name="脓毒症高凝亚型",
                    category="syndrome",
                    alert_type="sepsis_subphenotype",
                    severity="high",
                    parameter="subphenotype_probability",
                    condition={"subphenotype": assigned},
                    value=round(float(profile.get("confidence") or 0.0) * 100.0, 1),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": f"该患者属于高凝亚型(概率{round(float(profile.get('confidence') or 0.0) * 100.0, 1)}%)。",
                        "evidence": profile.get("evidence") or [],
                        "suggestion": "该患者属于高凝亚型，建议强化凝血-纤溶监测，评估微血栓负荷与抗凝/器官灌注策略。",
                        "text": "",
                    },
                    extra={"detail": record},
                )
                if alert:
                    alerts.append(alert)
        elif assigned == "delta_mixed":
            if not await self.engine._is_suppressed(patient_id_str, "SEPSIS_SUBPHENOTYPE_DELTA", same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id="SEPSIS_SUBPHENOTYPE_DELTA",
                    name="脓毒症混合亚型",
                    category="syndrome",
                    alert_type="sepsis_subphenotype",
                    severity="warning",
                    parameter="subphenotype_probability",
                    condition={"subphenotype": assigned},
                    value=round(float(profile.get("confidence") or 0.0) * 100.0, 1),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": f"该患者属于混合亚型(概率{round(float(profile.get('confidence') or 0.0) * 100.0, 1)}%)。",
                        "evidence": profile.get("evidence") or [],
                        "suggestion": "当前呈多系统混合驱动，建议联合评估炎症、凝血和器官支持策略，避免单一器官导向处置。",
                        "text": "",
                    },
                    extra={"detail": record},
                )
                if alert:
                    alerts.append(alert)
        return alerts

    async def _is_sepsis_candidate(self, patient_doc: dict[str, Any], patient_id: str, now: datetime) -> bool:
        diagnosis = " ".join(str(patient_doc.get(key) or "") for key in ("clinicalDiagnosis", "admissionDiagnosis")).lower()
        keywords = [str(item).lower() for item in self._cfg().get("diagnosis_keywords", ["脓毒", "感染", "sepsis", "菌血症", "肺炎"]) if str(item).strip()]
        if any(keyword in diagnosis for keyword in keywords):
            return True
        alert = await self.engine.db.col("alert_records").find_one(
            {
                "patient_id": patient_id,
                "created_at": {"$gte": now - timedelta(hours=24)},
                "$or": [
                    {"rule_id": {"$in": ["SEPSIS_QSOFA", "SEPSIS_SOFA", "SEPSIS_SHOCK"]}},
                    {"alert_type": {"$in": ["qsofa", "sofa", "septic_shock"]}},
                ],
            },
            sort=[("created_at", -1)],
        )
        return bool(alert)

    async def _build_profile(self, *, patient_doc: dict[str, Any], patient_id: Any, his_pid: str, now: datetime) -> dict[str, Any] | None:
        device_id = await self.engine._get_device_id_for_patient(patient_doc, ["monitor", "vent"])
        sofa = await self.engine._calc_sofa(patient_doc, patient_id, device_id, his_pid)
        if not sofa or _to_float((sofa or {}).get("score")) is None or float(sofa.get("score") or 0) < float(self._cfg().get("min_sofa", 2) or 2):
            return None
        features = await self._collect_features(patient_doc=patient_doc, patient_id=patient_id, his_pid=his_pid, device_id=device_id, sofa=sofa, now=now)
        if not features:
            return None
        feature_order = list(self._cfg().get("feature_order", []))
        references = self._cfg().get("feature_reference", {}) if isinstance(self._cfg().get("feature_reference"), dict) else {}
        centroids = self._cfg().get("centroids", {}) if isinstance(self._cfg().get("centroids"), dict) else {}
        if not feature_order or not references or not centroids:
            return None
        standardized: dict[str, float] = {}
        vector: list[float] = []
        for key in feature_order:
            ref = references.get(key) if isinstance(references.get(key), dict) else {}
            mean = _to_float(ref.get("mean"))
            std = _to_float(ref.get("std"))
            value = _to_float(features.get(key))
            if mean is None or std is None or std <= 0 or value is None:
                return None
            z = (value - mean) / std
            standardized[key] = round(z, 4)
            vector.append(z)
        scores: dict[str, float] = {}
        distances: dict[str, float] = {}
        labels = self._cfg().get("labels", {}) if isinstance(self._cfg().get("labels"), dict) else {}
        suggestions = self._cfg().get("care_implications", {}) if isinstance(self._cfg().get("care_implications"), dict) else {}
        for key, centroid in centroids.items():
            if not isinstance(centroid, list) or len(centroid) != len(vector):
                continue
            distance = math.sqrt(sum((float(v) - float(c)) ** 2 for v, c in zip(vector, centroid)))
            scores[str(key)] = -distance
            distances[str(key)] = round(distance, 4)
        probabilities = _softmax(scores)
        assigned = max(probabilities, key=probabilities.get) if probabilities else ""
        confidence = float(probabilities.get(assigned, 0.0)) if assigned else 0.0
        threshold = float(self._cfg().get("confidence_threshold", 0.6) or 0.6)
        if confidence < threshold:
            assigned = "mixed_uncertain"
        profiles = []
        for key, prob in sorted(probabilities.items(), key=lambda item: item[1], reverse=True):
            profiles.append(
                {
                    "syndrome": "sepsis",
                    "subtype_code": key,
                    "subtype_label": str(labels.get(key) or key),
                    "confidence": round(float(prob), 3),
                    "summary": str((suggestions.get(key) or {}).get("summary") or ""),
                    "evidence": [],
                    "care_implications": list((suggestions.get(key) or {}).get("care_implications") or []),
                    "prototype_distance": distances.get(key),
                    "cohort_centroid": {feature_order[idx]: centroid for idx, centroid in enumerate(centroids.get(key) or [])},
                }
            )
        display = str(labels.get(assigned) or assigned)
        primary = next((row for row in profiles if row.get("subtype_code") == assigned), None)
        evidence = self._build_evidence(features, sofa)
        return {
            "summary": f"当前最可能为 {display}，归属概率 {round(confidence * 100, 1)}%。" if assigned != "mixed_uncertain" else f"当前最高归属概率 {round(confidence * 100, 1)}%，归为混合/不确定。",
            "primary_profile": primary or {
                "syndrome": "sepsis",
                "subtype_code": assigned,
                "subtype_label": display,
                "confidence": round(confidence, 3),
                "summary": "",
                "evidence": evidence,
                "care_implications": list((suggestions.get(assigned) or {}).get("care_implications") or []),
                "prototype_distance": distances.get(assigned),
                "cohort_centroid": None,
            },
            "profiles": profiles,
            "supporting_snapshot": {
                "sofa_score": sofa.get("score"),
                "sofa_delta": sofa.get("delta"),
                "features": features,
            },
            "feature_vector": standardized,
            "model_meta": {
                "kind": "prototype_soft_clustering",
                "generated_at": now,
            },
            "assigned_label": assigned,
            "assigned_display": display,
            "confidence": round(confidence, 4),
            "distances": distances,
            "evidence": evidence,
        }

    async def _collect_features(self, *, patient_doc: dict[str, Any], patient_id: Any, his_pid: str, device_id: str | None, sofa: dict[str, Any], now: datetime) -> dict[str, float | None]:
        labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=48)
        raw_items = await self._load_exam_items(his_pid, since=now - timedelta(hours=48))
        cap = await self.engine._get_latest_device_cap(device_id) if device_id else None
        map_value = self.engine._get_map(cap or {}) if cap else None
        hr = _to_float(((cap or {}).get("params") or {}).get("param_HR")) if isinstance((cap or {}).get("params"), dict) else None
        ne = 0.0
        current_vaso = await self.engine._get_current_vasopressor_snapshot(patient_id, patient_doc, hours=8, max_items=4)
        for row in current_vaso:
            if "去甲肾上腺素" in str(row.get("drug") or ""):
                ne = float(row.get("dose_ug_kg_min") or 0.0)
                break
        pf = None
        pao2 = _to_float(((labs.get("pao2") or {}).get("value")) if isinstance(labs.get("pao2"), dict) else None)
        fio2 = self.engine._vent_param(cap or {}, "fio2", "param_FiO2") if cap else None
        if pao2 is not None and fio2 is not None:
            fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
            if fio2_frac and fio2_frac > 0:
                pf = pao2 / fio2_frac
        temp_series = await self.engine._get_param_series_by_pid(patient_id, self.engine._cfg("vital_signs", "temperature", "code", default="param_T"), now - timedelta(hours=24), prefer_device_types=["monitor"], limit=360)
        temp_values = [float(row.get("value")) for row in temp_series if row.get("value") is not None]
        temp_pattern = 0.0
        if temp_values:
            if max(temp_values) >= float(self._cfg().get("hyperthermia_threshold", 38.3) or 38.3):
                temp_pattern = 1.0
            elif min(temp_values) <= float(self._cfg().get("hypothermia_threshold", 36.0) or 36.0):
                temp_pattern = -1.0
        pct = _to_float(((labs.get("pct") or {}).get("value")) if isinstance(labs.get("pct"), dict) else None)
        crp = self._latest_item(raw_items, self._cfg().get("crp_keywords", ["crp", "c反应蛋白"]))
        il6 = self._latest_item(raw_items, self._cfg().get("il6_keywords", ["il-6", "il6", "白介素6"]))
        ferritin = self._latest_item(raw_items, self._cfg().get("ferritin_keywords", ["铁蛋白", "ferritin"]))
        wbc = self._latest_item(raw_items, self._cfg().get("wbc_keywords", ["wbc", "白细胞"]))
        neut = self._latest_item(raw_items, self._cfg().get("neutrophil_keywords", ["中性粒细胞绝对值", "neut", "anc", "中性粒细胞#"]))
        lymph = self._latest_item(raw_items, self._cfg().get("lymphocyte_keywords", ["淋巴细胞绝对值", "lymph", "alc", "淋巴细胞#"]))
        nlr = neut / lymph if neut is not None and lymph not in (None, 0) else None
        ddimer = _to_float(((labs.get("ddimer") or {}).get("value")) if isinstance(labs.get("ddimer"), dict) else None)
        plt = _to_float(((labs.get("plt") or {}).get("value")) if isinstance(labs.get("plt"), dict) else None)
        inr = _to_float(((labs.get("inr") or {}).get("value")) if isinstance(labs.get("inr"), dict) else None)
        fib = _to_float(((labs.get("fib") or {}).get("value")) if isinstance(labs.get("fib"), dict) else None)
        lactate = _to_float(((labs.get("lac") or {}).get("value")) if isinstance(labs.get("lac"), dict) else None)
        cr = _to_float(((labs.get("cr") or {}).get("value")) if isinstance(labs.get("cr"), dict) else None)
        bil = _to_float(((labs.get("bil") or {}).get("value")) if isinstance(labs.get("bil"), dict) else None)
        sofa_score = _to_float((sofa or {}).get("score"))

        return {
            "inflammation": self._mean([
                self._scale_ratio(pct, 2.0),
                self._scale_ratio(crp, 40.0),
                self._scale_ratio(il6, 100.0),
                self._scale_ratio(ferritin, 500.0),
                self._scale_ratio(wbc, 12.0),
                self._scale_ratio(nlr, 10.0),
                1.5 if temp_pattern > 0 else None,
            ]),
            "immunosuppression": self._mean([
                round(max(0.0, 1.2 / max(float(lymph), 0.2)), 4) if lymph is not None else None,
                1.5 if temp_pattern < 0 else None,
                self._scale_ratio(nlr, 12.0),
            ]),
            "coagulopathy": self._mean([
                self._scale_ratio(ddimer, 5.0),
                self._scale_ratio(inr, 1.5),
                round(max(0.0, (150.0 - float(plt)) / 50.0), 4) if plt is not None else None,
                round(max(0.0, (3.0 - float(fib)) / 1.0), 4) if fib is not None else None,
            ]),
            "organ_dysfunction": self._mean([
                self._scale_ratio(sofa_score, 6.0),
                self._scale_ratio(lactate, 2.5),
                self._scale_ratio(cr, 150.0),
                self._scale_ratio(bil, 50.0),
                round(max(0.0, (200.0 - float(pf)) / 60.0), 4) if pf is not None else None,
            ]),
            "hemodynamic_instability": self._mean([
                self._scale_ratio(ne, 0.15),
                round(max(0.0, (65.0 - float(map_value)) / 10.0), 4) if map_value is not None else None,
                self._scale_ratio(hr, 110.0),
            ]),
            "temperature_pattern": temp_pattern,
        }

    async def _load_exam_items(self, his_pid: str, since: datetime) -> list[dict[str, Any]]:
        cursor = self.engine.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(1600)
        rows: list[dict[str, Any]] = []
        async for doc in cursor:
            time_value = doc.get("authTime") or doc.get("collectTime") or doc.get("reportTime") or doc.get("time")
            if isinstance(time_value, datetime) and time_value < since:
                continue
            rows.append(doc)
        return rows

    def _latest_item(self, items: list[dict[str, Any]], keywords: list[str]) -> float | None:
        lowered = [str(item).lower() for item in keywords if str(item).strip()]
        for doc in items:
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").lower()
            if not name or not any(keyword in name for keyword in lowered):
                continue
            value = _to_float(doc.get("result") or doc.get("resultValue") or doc.get("value"))
            if value is not None:
                return value
        return None

    def _mean(self, values: list[float | None]) -> float | None:
        nums = [float(item) for item in values if item is not None]
        if not nums:
            return None
        return round(sum(nums) / len(nums), 4)

    def _scale_ratio(self, value: float | None, divisor: float) -> float | None:
        if value is None or divisor <= 0:
            return None
        return round(max(0.0, float(value) / float(divisor)), 4)

    def _build_evidence(self, features: dict[str, float | None], sofa: dict[str, Any]) -> list[str]:
        rows = []
        if features.get("inflammation") is not None:
            rows.append(f"炎症轴 {round(float(features['inflammation']), 2)}")
        if features.get("coagulopathy") is not None:
            rows.append(f"凝血轴 {round(float(features['coagulopathy']), 2)}")
        if features.get("organ_dysfunction") is not None:
            rows.append(f"器官功能轴 {round(float(features['organ_dysfunction']), 2)}")
        if features.get("hemodynamic_instability") is not None:
            rows.append(f"血流动力学轴 {round(float(features['hemodynamic_instability']), 2)}")
        if (sofa or {}).get("score") is not None:
            rows.append(f"SOFA {sofa.get('score')}")
        return rows[:5]

    def _transition(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(previous, dict):
            return None
        prev_label = str(previous.get("assigned_label") or previous.get("primary_profile", {}).get("subtype_code") or "").strip()
        curr_label = str(current.get("assigned_label") or "").strip()
        if not prev_label or not curr_label or prev_label == curr_label or "mixed" in prev_label or "mixed" in curr_label:
            return None
        prev_profile = previous.get("primary_profile") if isinstance(previous.get("primary_profile"), dict) else {}
        curr_profile = current.get("primary_profile") if isinstance(current.get("primary_profile"), dict) else {}
        return {
            "from": prev_label,
            "to": curr_label,
            "from_label": str(prev_profile.get("subtype_label") or prev_label),
            "to_label": str(curr_profile.get("subtype_label") or curr_label),
            "from_confidence": previous.get("confidence") or prev_profile.get("confidence"),
            "to_confidence": current.get("confidence") or curr_profile.get("confidence"),
        }

    async def _persist_profile(self, *, patient_doc: dict[str, Any], profile: dict[str, Any], now: datetime) -> dict[str, Any]:
        patient_id_str = str(patient_doc.get("_id") or "")
        doc = {
            "patient_id": patient_id_str,
            "patient_name": patient_doc.get("name") or "",
            "bed": patient_doc.get("hisBed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
            "score_type": "sepsis_subphenotype_profile",
            **profile,
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        result = await self.engine.db.col("score").insert_one(doc)
        doc["_id"] = result.inserted_id
        current_profile = {
            "phenotype": profile.get("assigned_label"),
            "phenotype_display": profile.get("assigned_display"),
            "confidence": profile.get("confidence"),
            "summary": profile.get("summary"),
            "primary_profile": profile.get("primary_profile"),
            "profiles": profile.get("profiles"),
            "transition": profile.get("transition"),
            "updated_at": now,
            "record_id": result.inserted_id,
        }
        await self.engine.db.col("patient").update_one(
            {"_id": patient_doc.get("_id")},
            {"$set": {"current_profile.sepsis_subphenotype": current_profile}},
        )
        return doc
