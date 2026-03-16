"""肺栓塞（PE）风险识别。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class PeDetectorMixin:
    def _pe_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("pe_detection", {})
        return cfg if isinstance(cfg, dict) else {}

    def _pe_contains_any(self, text: str, keywords: list[str]) -> bool:
        blob = str(text or "").lower()
        return any(str(k).strip().lower() in blob for k in keywords if str(k).strip())

    def _patient_text_blob(self, patient_doc: dict) -> str:
        return " ".join(
            str(patient_doc.get(k) or "")
            for k in (
                "clinicalDiagnosis",
                "admissionDiagnosis",
                "history",
                "diagnosisHistory",
                "surgeryHistory",
                "operationHistory",
                "pastHistory",
                "medicalHistory",
                "chiefComplaint",
                "presentIllness",
                "allDiagnosis",
            )
        ).lower()

    def _safe_float(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _detect_sudden_hypoxia(self, spo2_series: list[dict]) -> tuple[bool, dict]:
        if len(spo2_series) < 2:
            return False, {"drop": None, "from": None, "to": None, "mode": None}

        max_drop: float | None = None
        drop_from: float | None = None
        drop_to: float | None = None
        mode: str | None = None

        prev = None
        for row in spo2_series:
            value = self._safe_float(row.get("value"))
            if value is None:
                continue
            if prev is not None:
                delta = prev - value
                if delta >= 5 and (max_drop is None or delta > max_drop):
                    max_drop = round(delta, 2)
                    drop_from = round(prev, 2)
                    drop_to = round(value, 2)
                    mode = "adjacent_drop"
            prev = value

        high_values = [self._safe_float(x.get("value")) for x in spo2_series if self._safe_float(x.get("value")) is not None and self._safe_float(x.get("value")) >= 95]
        low_values = [self._safe_float(x.get("value")) for x in spo2_series if self._safe_float(x.get("value")) is not None and self._safe_float(x.get("value")) < 90]
        if high_values and low_values:
            start_high = max(high_values)
            end_low = min(low_values)
            long_drop = start_high - end_low
            if long_drop >= 5 and (max_drop is None or long_drop > max_drop):
                max_drop = round(long_drop, 2)
                drop_from = round(start_high, 2)
                drop_to = round(end_low, 2)
                mode = "95_to_below_90"

        return bool(max_drop is not None and max_drop >= 5), {
            "drop": max_drop,
            "from": drop_from,
            "to": drop_to,
            "mode": mode,
        }

    def _detect_tachycardia_onset(self, hr_series: list[dict]) -> tuple[bool, dict]:
        numeric = [self._safe_float(x.get("value")) for x in hr_series if self._safe_float(x.get("value")) is not None]
        if not numeric:
            return False, {"baseline": None, "latest": None, "delta": None}
        baseline = numeric[0]
        latest = numeric[-1]
        matched = baseline < 100 and latest > 100
        delta = latest - baseline if baseline is not None and latest is not None else None
        return matched, {
            "baseline": round(baseline, 2) if baseline is not None else None,
            "latest": round(latest, 2) if latest is not None else None,
            "delta": round(delta, 2) if delta is not None else None,
        }

    async def _calc_wells_score(
        self,
        patient_doc: dict,
        pid,
        now: datetime,
        latest_hr: float | None,
    ) -> tuple[float, dict, float]:
        cfg = self._pe_cfg()
        weights = cfg.get("wells_weights", {}) if isinstance(cfg.get("wells_weights", {}), dict) else {}
        defaults = {
            "dvt_symptoms": 3.0,
            "pe_most_likely": 3.0,
            "hr_gt_100": 1.5,
            "immobilization_or_surgery": 1.5,
            "previous_vte": 1.5,
            "hemoptysis": 1.0,
            "malignancy": 1.0,
        }

        dvt_kw = self._get_cfg_list(("alert_engine", "pe_detection", "dvt_symptom_keywords"), ["下肢肿胀", "小腿疼痛", "dvt", "深静脉"])
        pe_kw = self._get_cfg_list(("alert_engine", "pe_detection", "pe_diagnosis_keywords"), ["肺栓塞", "pe", "肺动脉栓塞"])
        prev_vte_kw = self._get_cfg_list(("alert_engine", "pe_detection", "previous_vte_keywords"), ["静脉血栓", "dvt", "pe", "vte"])
        hemoptysis_kw = self._get_cfg_list(("alert_engine", "pe_detection", "hemoptysis_keywords"), ["咯血", "hemoptysis"])
        malignancy_kw = self._get_cfg_list(("alert_engine", "pe_detection", "malignancy_keywords"), ["恶性肿瘤", "癌", "cancer"])

        text = self._patient_text_blob(patient_doc)
        immobility_hours = await self._immobility_hours(patient_doc, pid, now)
        immobilization_or_surgery = self._has_recent_surgery(patient_doc, now, days=30) or immobility_hours > 72

        items = {
            "dvt_symptoms": self._pe_contains_any(text, dvt_kw),
            "pe_most_likely": self._pe_contains_any(text, pe_kw),
            "hr_gt_100": latest_hr is not None and latest_hr > 100,
            "immobilization_or_surgery": immobilization_or_surgery,
            "previous_vte": self._pe_contains_any(text, prev_vte_kw),
            "hemoptysis": self._pe_contains_any(text, hemoptysis_kw),
            "malignancy": self._pe_contains_any(text, malignancy_kw),
        }

        score = 0.0
        for key, matched in items.items():
            if matched:
                score += float(weights.get(key, defaults.get(key, 0.0)))

        detail = {
            **items,
            "immobility_hours": round(immobility_hours, 2),
            "latest_hr": latest_hr,
        }
        return round(score, 2), detail, immobility_hours

    async def scan_pe_risk(self) -> None:
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self._pe_cfg()
        pattern_window_hours = float(cfg.get("pattern_window_hours", 2))
        wells_high_risk_score = float(cfg.get("wells_high_risk_score", 4))

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "dept": 1,
                "hisDept": 1,
                "deptCode": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "history": 1,
                "diagnosisHistory": 1,
                "surgeryHistory": 1,
                "operationHistory": 1,
                "pastHistory": 1,
                "medicalHistory": 1,
                "chiefComplaint": 1,
                "presentIllness": 1,
                "allDiagnosis": 1,
                "icuAdmissionTime": 1,
                "surgeryTime": 1,
                "operationTime": 1,
                "recentSurgeryTime": 1,
                "lastOperationTime": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        now = datetime.now()
        pattern_since = now - timedelta(hours=pattern_window_hours)
        bnp_since = now - timedelta(hours=72)

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = self._pid_str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()
            device_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])

            latest_cap = await self._get_latest_param_snapshot_by_pid(
                pid,
                codes=["param_HR", "param_spo2", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"],
            )
            if not latest_cap and device_id:
                latest_cap = await self._get_latest_device_cap(
                    device_id,
                    codes=["param_HR", "param_spo2", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"],
                )

            latest_hr = self._get_priority_param(latest_cap or {}, ["param_HR"]) if latest_cap else None

            spo2_series = await self._get_param_series_by_pid(
                pid,
                "param_spo2",
                pattern_since,
                prefer_device_types=["monitor"],
                limit=300,
            )
            hr_series = await self._get_param_series_by_pid(
                pid,
                "param_HR",
                pattern_since,
                prefer_device_types=["monitor"],
                limit=300,
            )

            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72) if his_pid else {}
            ddimer_info = labs.get("ddimer", {}) if labs else {}
            ddimer = ddimer_info.get("value")
            ddimer_elevated = ddimer is not None and float(ddimer) > 0.5

            bnp_series = await self._get_lab_series(his_pid, "bnp", bnp_since, limit=80) if his_pid else []
            bnp_latest = bnp_series[-1]["value"] if bnp_series else None
            bnp_baseline = min((float(x["value"]) for x in bnp_series if x.get("value") is not None), default=None)
            bnp_surge = bool(
                bnp_latest is not None
                and bnp_baseline not in (None, 0)
                and float(bnp_latest) >= float(bnp_baseline) * 1.5
            )

            sudden_hypoxia, hypoxia_meta = self._detect_sudden_hypoxia(spo2_series)
            tachycardia_onset, hr_meta = self._detect_tachycardia_onset(hr_series)
            wells_score, wells_items, immobility_hours = await self._calc_wells_score(patient_doc, pid, now, latest_hr)

            matched_criteria: list[str] = []
            if sudden_hypoxia:
                matched_criteria.append("sudden_hypoxia")
            if tachycardia_onset:
                matched_criteria.append("tachycardia_onset")
            if ddimer_elevated:
                matched_criteria.append("ddimer_elevated")
            if bnp_surge:
                matched_criteria.append("bnp_surge")

            matched_count = len(matched_criteria)
            if matched_count >= 2:
                severity = "critical" if matched_count >= 3 else "high"
                rule_id = "PE_PATTERN_DETECTED"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    time_candidates = [
                        latest_cap.get("time") if latest_cap else None,
                        ddimer_info.get("time"),
                        bnp_series[-1]["time"] if bnp_series else None,
                    ]
                    source_time = max([t for t in time_candidates if isinstance(t, datetime)] or [now])
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="疑似急性肺栓塞",
                        category="syndrome",
                        alert_type="pe_suspected",
                        severity=severity,
                        parameter="pe_pattern_score",
                        condition={
                            "pattern_window_hours": pattern_window_hours,
                            "min_matched": 2,
                            "matched_count": matched_count,
                        },
                        value=matched_count,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=source_time,
                        extra={
                            "matched_criteria": matched_criteria,
                            "spo2_drop": hypoxia_meta,
                            "hr_change": hr_meta,
                            "ddimer": ddimer,
                            "bnp": {
                                "latest": bnp_latest,
                                "baseline_72h_min": bnp_baseline,
                                "surge_ratio": round(float(bnp_latest) / float(bnp_baseline), 2) if bnp_latest is not None and bnp_baseline not in (None, 0) else None,
                            },
                            "wells_score": wells_score,
                            "immobility_hours": immobility_hours,
                            "suggestion": "建议CTPA检查",
                        },
                    )
                    if alert:
                        triggered += 1

            if wells_score >= wells_high_risk_score and ddimer_elevated:
                rule_id = "PE_WELLS_HIGH_RISK"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                source_time = max(
                    [t for t in [latest_cap.get("time") if latest_cap else None, ddimer_info.get("time")] if isinstance(t, datetime)]
                    or [now]
                )
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="PE Wells评分中高危",
                    category="syndrome",
                    alert_type="pe_wells_high",
                    severity="high",
                    parameter="wells_score",
                    condition={"operator": ">=", "threshold": wells_high_risk_score, "requires_ddimer": True},
                    value=round(wells_score, 2),
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=source_time,
                    extra={
                        "wells_score": round(wells_score, 2),
                        "wells_items": wells_items,
                        "ddimer_value": ddimer,
                    },
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("PE检测", triggered)
