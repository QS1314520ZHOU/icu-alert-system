from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class PeRiskScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="pe_detection",
                interval_key="pe_detection",
                default_interval=600,
                initial_delay=44,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.engine._pe_cfg()
        pattern_window_hours = float(cfg.get("pattern_window_hours", 2))
        wells_high_risk_score = float(cfg.get("wells_high_risk_score", 4))

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
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
            pid_str = self.engine._pid_str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()
            device_id = await self.engine._get_device_id_for_patient(patient_doc, ["monitor"])

            latest_cap = await self.engine._get_latest_param_snapshot_by_pid(
                pid,
                codes=["param_HR", "param_spo2", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"],
            )
            if not latest_cap and device_id:
                latest_cap = await self.engine._get_latest_device_cap(
                    device_id,
                    codes=["param_HR", "param_spo2", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"],
                )
            if latest_cap:
                latest_cap, _ = await self.engine._filter_snapshot_quality(
                    pid=pid,
                    pid_str=pid_str,
                    patient_doc=patient_doc,
                    cap=latest_cap,
                    device_id=device_id,
                    same_rule_sec=same_rule_sec,
                    max_per_hour=max_per_hour,
                )

            latest_hr = self.engine._get_priority_param(latest_cap or {}, ["param_HR"]) if latest_cap else None

            spo2_series = await self.engine._get_param_series_by_pid(
                pid,
                "param_spo2",
                pattern_since,
                prefer_device_types=["monitor"],
                limit=300,
            )
            spo2_series = self.engine._filter_series_quality("param_spo2", spo2_series)
            hr_series = await self.engine._get_param_series_by_pid(
                pid,
                "param_HR",
                pattern_since,
                prefer_device_types=["monitor"],
                limit=300,
            )
            hr_series = self.engine._filter_series_quality("param_HR", hr_series)

            labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=72) if his_pid else {}
            ddimer_info = labs.get("ddimer", {}) if labs else {}
            ddimer = ddimer_info.get("value")
            ddimer_elevated = ddimer is not None and float(ddimer) > 0.5

            bnp_series = await self.engine._get_lab_series(his_pid, "bnp", bnp_since, limit=80) if his_pid else []
            bnp_latest = bnp_series[-1]["value"] if bnp_series else None
            bnp_baseline = min((float(x["value"]) for x in bnp_series if x.get("value") is not None), default=None)
            bnp_surge = bool(
                bnp_latest is not None
                and bnp_baseline not in (None, 0)
                and float(bnp_latest) >= float(bnp_baseline) * 1.5
            )

            sudden_hypoxia, hypoxia_meta = self.engine._detect_sudden_hypoxia(spo2_series)
            tachycardia_onset, hr_meta = self.engine._detect_tachycardia_onset(hr_series)
            wells_score, wells_items, immobility_hours = await self.engine._calc_wells_score(patient_doc, pid, now, latest_hr)

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
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    time_candidates = [
                        latest_cap.get("time") if latest_cap else None,
                        ddimer_info.get("time"),
                        bnp_series[-1]["time"] if bnp_series else None,
                    ]
                    source_time = max([t for t in time_candidates if isinstance(t, datetime)] or [now])
                    alert = await self.engine._create_alert(
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
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                source_time = max(
                    [t for t in [latest_cap.get("time") if latest_cap else None, ddimer_info.get("time")] if isinstance(t, datetime)]
                    or [now]
                )
                alert = await self.engine._create_alert(
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
            self.engine._log_info("PE检测", triggered)
