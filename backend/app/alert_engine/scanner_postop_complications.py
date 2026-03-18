from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from app.utils.clinical import _cap_time, _cap_value
from app.utils.labs import _lab_time
from app.utils.parse import _parse_dt, _parse_number
from .scanners import BaseScanner, ScannerSpec


class PostopComplicationsScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="postop_monitor",
                interval_key="postop_monitor",
                default_interval=1800,
                initial_delay=64,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

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
                "icuAdmissionTime": 1,
                "surgeryTime": 1,
                "operationTime": 1,
                "recentSurgeryTime": 1,
                "lastOperationTime": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "history": 1,
                "diagnosisHistory": 1,
                "surgeryHistory": 1,
                "operationHistory": 1,
                "chiefComplaint": 1,
                "presentIllness": 1,
                "allDiagnosis": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        now = datetime.now()

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = self.engine._pid_str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()
            postop_info = await self.engine._is_postop_patient(patient_doc, now)
            if not postop_info:
                continue

            surgery_time = self.engine._postop_since(postop_info, patient_doc, now)
            hours_since_surgery = float(postop_info.get("hours_since_surgery") or 0.0)
            device_id = await self.engine._get_device_id_for_patient(patient_doc, ["monitor"])

            latest_cap = await self.engine._get_latest_param_snapshot_by_pid(
                pid,
                codes=["param_HR", "param_T", "param_nibp_m", "param_ibp_m", "param_nibp_s", "param_ibp_s"],
            )
            if not latest_cap and device_id:
                latest_cap = await self.engine._get_latest_device_cap(
                    device_id,
                    codes=["param_HR", "param_T", "param_nibp_m", "param_ibp_m", "param_nibp_s", "param_ibp_s"],
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
            latest_map = self.engine._get_map(latest_cap or {}) if latest_cap else None

            # A. 术后出血
            bleed_score = 0.0
            hb_trend = None
            if his_pid:
                hb_series = await self.engine._get_lab_series(his_pid, "hb", surgery_time, limit=120)
                if len(hb_series) >= 2:
                    baseline_hb = float(hb_series[0]["value"])
                    latest_hb = float(hb_series[-1]["value"])
                    hb_drop = baseline_hb - latest_hb
                    hb_trend = {
                        "baseline": baseline_hb,
                        "latest": latest_hb,
                        "drop": round(hb_drop, 1),
                        "time": hb_series[-1]["time"],
                    }
                    if hb_drop >= 20:
                        bleed_score += 3

            if (latest_map is not None and latest_map < 65) or (latest_hr is not None and latest_hr > 110):
                bleed_score += 3

            drain_info = await self.engine._get_postop_drainage(pid_str, now - timedelta(hours=6))
            if drain_info["total_6h_ml"] > 200 or drain_info["max_single_ml"] > 100:
                bleed_score += 2

            if bleed_score >= 5:
                rule_id = "POSTOP_BLEEDING"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    severity = "critical" if bleed_score >= 8 else "high"
                    source_time = max(
                        [
                            t
                            for t in [
                                latest_cap.get("time") if latest_cap else None,
                                hb_trend.get("time") if isinstance(hb_trend, dict) else None,
                                drain_info.get("time"),
                            ]
                            if isinstance(t, datetime)
                        ]
                        or [now]
                    )
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="术后出血风险",
                        category="syndrome",
                        alert_type="postop_bleeding",
                        severity=severity,
                        parameter="postop_bleeding_score",
                        condition={"operator": ">=", "threshold": 5},
                        value=round(bleed_score, 1),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=source_time,
                        extra={
                            "hb_trend": hb_trend,
                            "map": latest_map,
                            "hr": latest_hr,
                            "drain_volume": drain_info,
                            "hours_since_surgery": hours_since_surgery,
                        },
                    )
                    if alert:
                        triggered += 1

            # B. 术后感染二次高峰/吻合口瘘风险
            if hours_since_surgery > 48:
                temp_series = await self.engine._get_param_series_by_pid(pid, "param_T", surgery_time, prefer_device_types=["monitor"], limit=800)
                temp_series = self.engine._filter_series_quality("param_T", temp_series)
                temp_rebound, temp_meta = self.engine._detect_temp_v_rebound(temp_series)

                wbc_series = await self.engine._get_named_lab_series(
                    his_pid,
                    self.engine._get_cfg_list(("alert_engine", "postop_monitor", "wbc_keywords"), ["白细胞", "wbc"]),
                    surgery_time,
                    limit=200,
                    kind="wbc",
                ) if his_pid else []
                crp_series = await self.engine._get_named_lab_series(
                    his_pid,
                    self.engine._get_cfg_list(("alert_engine", "postop_monitor", "crp_keywords"), ["CRP", "C反应蛋白", "c-reactive"]),
                    surgery_time,
                    limit=200,
                    kind="crp",
                ) if his_pid else []

                wbc_latest = wbc_series[-1]["value"] if wbc_series else None
                wbc_min = min((float(x["value"]) for x in wbc_series if x.get("value") is not None), default=None)
                wbc_rise = bool(wbc_latest is not None and wbc_min not in (None, 0) and wbc_latest > 12 and float(wbc_latest) >= float(wbc_min) * 1.5)

                crp_latest = crp_series[-1]["value"] if crp_series else None
                crp_prev = crp_series[-2]["value"] if len(crp_series) >= 2 else None
                crp_doubled = bool(crp_latest is not None and crp_prev not in (None, 0) and float(crp_latest) >= float(crp_prev) * 2)

                if temp_rebound and (wbc_rise or crp_doubled):
                    rule_id = "POSTOP_ANASTOMOTIC_LEAK_RISK"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        source_time = max(
                            [
                                t
                                for t in [
                                    latest_cap.get("time") if latest_cap else None,
                                    wbc_series[-1]["time"] if wbc_series else None,
                                    crp_series[-1]["time"] if crp_series else None,
                                ]
                                if isinstance(t, datetime)
                            ]
                            or [now]
                        )
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="术后感染二次高峰/吻合口瘘风险",
                            category="syndrome",
                            alert_type="postop_infection_resurgence",
                            severity="high",
                            parameter="postop_infection_pattern",
                            condition={"temp_rebound": True, "wbc_rise_or_crp_doubled": True},
                            value=1,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=source_time,
                            extra={
                                "hours_since_surgery": hours_since_surgery,
                                "temperature_pattern": temp_meta,
                                "wbc": {
                                    "latest": wbc_latest,
                                    "postop_min": wbc_min,
                                    "rise_ratio": round(float(wbc_latest) / float(wbc_min), 2) if wbc_latest is not None and wbc_min not in (None, 0) else None,
                                },
                                "crp": {
                                    "latest": crp_latest,
                                    "previous": crp_prev,
                                    "rise_ratio": round(float(crp_latest) / float(crp_prev), 2) if crp_latest is not None and crp_prev not in (None, 0) else None,
                                },
                            },
                        )
                        if alert:
                            triggered += 1

            # C. 术后肠麻痹
            if hours_since_surgery > 24:
                gi_status = await self.engine._get_postop_gi_status(pid_str, surgery_time)
                ileus_reasons: list[str] = []
                if hours_since_surgery > 72 and not gi_status["has_positive_gi_recovery"]:
                    ileus_reasons.append("术后72h仍无排气/排便/肠鸣音恢复记录")
                latest_grv = gi_status.get("latest_grv_ml")
                if latest_grv is not None and latest_grv > 500:
                    ileus_reasons.append("胃残余量>500mL")

                if ileus_reasons:
                    rule_id = "POSTOP_ILEUS"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        source_time = max(
                            [
                                t
                                for t in [gi_status.get("positive_time"), gi_status.get("latest_grv_time"), latest_cap.get("time") if latest_cap else None]
                                if isinstance(t, datetime)
                            ]
                            or [now]
                        )
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="术后肠麻痹",
                            category="syndrome",
                            alert_type="postop_ileus",
                            severity="warning",
                            parameter="postop_ileus",
                            condition={"operator": "postop_gi_recovery_delayed"},
                            value=1,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=source_time,
                            extra={
                                "hours_since_surgery": hours_since_surgery,
                                "reasons": ileus_reasons,
                                "has_positive_gi_recovery": gi_status["has_positive_gi_recovery"],
                                "latest_grv_ml": latest_grv,
                            },
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self.engine._log_info("术后并发症", triggered)
