from __future__ import annotations

from datetime import datetime, timedelta

from app.utils.clinical import _eval_condition, _extract_param
from app.utils.parse import _parse_dt

from .scanners import BaseScanner, ScannerSpec
from .vital_signs import _to_float


class VitalSignsScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="vital_signs",
                interval_key="vital_signs",
                default_interval=60,
                initial_delay=5,
            ),
        )

    async def scan(self) -> None:
        rules = [r async for r in self.engine.db.col("alert_rules").find({"enabled": True, "category": "vital_signs"})]

        binds = [b async for b in self.engine.db.col("deviceBind").find(
            {"unBindTime": None, "type": "monitor"}, {"pid": 1, "deviceID": 1}
        )]
        if not binds:
            binds = [b async for b in self.engine.db.col("deviceBind").find(
                {"unBindTime": None}, {"pid": 1, "deviceID": 1}
            )]
        if not binds:
            return

        now = datetime.now()
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        adv_cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("vital_signs_advanced", {})
        af_hr_threshold = float(adv_cfg.get("af_hr_threshold", 100))
        af_duration_sec = int(adv_cfg.get("af_irregular_duration_seconds", 300))
        af_max_gap_sec = int(adv_cfg.get("af_max_gap_seconds", 120))
        af_new_onset_h = float(adv_cfg.get("af_new_onset_lookback_hours", 6))
        af_rhythm_lookback_m = int(adv_cfg.get("af_rhythm_lookback_minutes", 30))
        brady_hr_threshold = float(adv_cfg.get("brady_hr_threshold", 50))
        brady_sbp_drop_threshold = float(adv_cfg.get("brady_sbp_drop_threshold", 20))
        brady_window_minutes = int(adv_cfg.get("brady_sbp_window_minutes", 30))
        qtc_threshold_ms = float(adv_cfg.get("qtc_threshold_ms", 500))
        qtc_critical_ms = float(adv_cfg.get("qtc_critical_ms", 550))
        qtc_lookback_hours = float(adv_cfg.get("qtc_lookback_hours", 2))

        af_keywords = adv_cfg.get("af_keywords", ["房颤", "af", "atrial fibrillation"])
        afl_keywords = adv_cfg.get("afl_keywords", ["房扑", "afl", "atrial flutter"])
        irregular_keywords = adv_cfg.get("irregular_keywords", ["不规则", "irregular", "arrhythmia", "房颤", "房扑"])
        rhythm_codes = adv_cfg.get(
            "rhythm_codes",
            [
                self.engine._cfg("vital_signs", "rhythm", "code", default="param_xinLvLv"),
                "rhythm_type",
                "param_rhythm_type",
                "arrhythmia_flag",
                "param_arrhythmia_flag",
            ],
        )
        arrhythmia_flag_codes = adv_cfg.get("arrhythmia_flag_codes", ["arrhythmia_flag", "param_arrhythmia_flag"])

        qtc_codes = adv_cfg.get(
            "qtc_codes",
            self.engine._cfg("alert_engine", "data_mapping", "qtc_codes", default=["param_qtc", "param_QTc", "ecg_qtc", "qtc"]),
        )
        if not isinstance(qtc_codes, list):
            qtc_codes = ["param_qtc", "param_QTc", "ecg_qtc", "qtc"]

        triggered = 0
        for bind in binds:
            device_id = bind.get("deviceID")
            pid = bind.get("pid")
            if not device_id or not pid:
                continue

            cap = await self.engine._get_latest_device_cap(device_id)
            if not cap:
                continue

            cap_time = _parse_dt(cap.get("time"))
            if cap_time and (now - cap_time).total_seconds() > 600:
                continue

            patient_doc, pid_str = await self.engine._load_patient(pid)
            if not pid_str:
                continue
            cap, quality_issues = await self.engine._filter_snapshot_quality(
                pid=pid,
                pid_str=pid_str,
                patient_doc=patient_doc,
                cap=cap,
                device_id=device_id,
                same_rule_sec=same_rule_sec,
                max_per_hour=max_per_hour,
            )

            for rule in rules:
                param = rule.get("parameter")
                if not param:
                    continue

                value = _extract_param(cap, param)
                if value is None:
                    continue
                condition = rule.get("condition", {}) or {}
                absolute_match = _eval_condition(value, condition)
                operator = str(condition.get("operator") or "")
                direction = "low" if operator in {"<", "<="} else ("high" if operator in {">", ">="} else None)
                within_baseline, baseline_deviation, baseline_meta = await self.engine._baseline_guard(
                    pid=pid,
                    patient_doc=patient_doc,
                    param=param,
                    value=float(value),
                    direction=direction,
                )
                if absolute_match and within_baseline and direction in {"low", "high"}:
                    continue
                if not absolute_match and not baseline_deviation:
                    continue

                confirmed, confirm_detail = await self.engine._confirm_vital_rule(
                    pid=pid,
                    patient_doc=patient_doc,
                    param=param,
                    value=float(value),
                    condition=condition,
                    cap=cap,
                    now=now,
                )
                if not confirmed:
                    continue

                if await self.engine._is_suppressed(pid_str, rule.get("rule_id"), same_rule_sec, max_per_hour):
                    continue

                alert = await self.engine._create_alert(
                    rule_id=rule.get("rule_id"),
                    name=rule.get("name"),
                    category="vital_signs",
                    alert_type="threshold",
                    severity=rule.get("severity", "warning"),
                    parameter=param,
                    condition={
                        **condition,
                        "trigger_mode": "absolute_or_baseline",
                        "baseline_used": bool(baseline_meta),
                        "confirmed_by_multi_param": bool(confirm_detail),
                    },
                    value=value,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=cap.get("time"),
                    extra={
                        "trigger_reason": "absolute_threshold" if absolute_match else "patient_baseline_deviation",
                        "patient_baseline": baseline_meta,
                        "confirmation": confirm_detail,
                        "data_quality_issues": quality_issues[:3],
                    } if (baseline_meta or confirm_detail or quality_issues) else None,
                )
                if alert:
                    triggered += 1

            rhythm_points = await self.engine._get_rhythm_points(
                device_id=device_id,
                since=now - timedelta(minutes=max(af_rhythm_lookback_m, 10)),
                rhythm_codes=rhythm_codes,
                af_keywords=af_keywords,
                afl_keywords=afl_keywords,
                irregular_keywords=irregular_keywords,
                arrhythmia_flag_codes=arrhythmia_flag_codes,
            )
            if rhythm_points:
                segments = self.engine._find_irregular_segments(rhythm_points, af_max_gap_sec)
                long_segments = [segment for segment in segments if segment.get("duration_seconds", 0) >= af_duration_sec]
                if long_segments:
                    segment = long_segments[-1]
                    hr_series = await self.engine._get_param_series_by_pid(
                        pid,
                        self.engine._cfg("vital_signs", "heart_rate", "code", default="param_HR"),
                        now - timedelta(minutes=max(af_rhythm_lookback_m, 10)),
                        prefer_device_types=["monitor"],
                        limit=2000,
                    )
                    hr_peak = None
                    for point in hr_series:
                        point_time = point.get("time")
                        point_value = _to_float(point.get("value"))
                        if point_value is None or not isinstance(point_time, datetime):
                            continue
                        if segment["start"] <= point_time <= segment["end"]:
                            hr_peak = point_value if (hr_peak is None or point_value > hr_peak) else hr_peak

                    if hr_peak is not None and hr_peak > af_hr_threshold:
                        prior_af = await self.engine._has_prior_af_afl(
                            device_id=device_id,
                            seg_start=segment["start"],
                            lookback_hours=af_new_onset_h,
                            rhythm_codes=rhythm_codes,
                            af_keywords=af_keywords,
                            afl_keywords=afl_keywords,
                            irregular_keywords=irregular_keywords,
                            arrhythmia_flag_codes=arrhythmia_flag_codes,
                        )
                        if not prior_af:
                            rule_id = "VS_NEW_AF_AFL"
                            if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                                alert = await self.engine._create_alert(
                                    rule_id=rule_id,
                                    name="新发房颤/房扑风险",
                                    category="vital_signs",
                                    alert_type="af_afl_new_onset",
                                    severity="high",
                                    parameter="rhythm",
                                    condition={
                                        "hr_gt": af_hr_threshold,
                                        "irregular_duration_seconds_gte": af_duration_sec,
                                        "new_onset_lookback_hours": af_new_onset_h,
                                    },
                                    value=round(hr_peak, 2),
                                    patient_id=pid_str,
                                    patient_doc=patient_doc,
                                    device_id=device_id,
                                    source_time=segment["end"],
                                    extra={
                                        "segment_start": segment["start"],
                                        "segment_end": segment["end"],
                                        "irregular_duration_seconds": round(segment["duration_seconds"], 1),
                                        "has_af_tag": segment.get("has_af"),
                                        "has_afl_tag": segment.get("has_afl"),
                                        "hr_peak_in_segment": round(hr_peak, 2),
                                    },
                                )
                                if alert:
                                    triggered += 1

            latest_hr = _extract_param(cap, self.engine._cfg("vital_signs", "heart_rate", "code", default="param_HR"))
            if latest_hr is not None and latest_hr < brady_hr_threshold:
                sbp_info = await self.engine._sbp_drop(pid, now, brady_window_minutes)
                if sbp_info and sbp_info.get("drop_sbp", 0) > brady_sbp_drop_threshold:
                    rule_id = "VS_BRADY_HYPOTENSION"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="心动过缓合并血压下降风险",
                            category="vital_signs",
                            alert_type="brady_hypotension",
                            severity="high",
                            parameter="param_HR",
                            condition={
                                "hr_lt": brady_hr_threshold,
                                "sbp_drop_gt": brady_sbp_drop_threshold,
                                "window_minutes": brady_window_minutes,
                            },
                            value=round(float(latest_hr), 2),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=sbp_info.get("latest_time") or cap.get("time"),
                            extra={
                                **sbp_info,
                                "latest_hr": round(float(latest_hr), 2),
                                "suggestion": "评估是否需要阿托品/临时起搏支持。",
                            },
                        )
                        if alert:
                            triggered += 1

            qtc_val, qtc_time, qtc_code = await self.engine._latest_qtc(pid, qtc_codes, qtc_lookback_hours)
            if qtc_val is not None and qtc_val > qtc_threshold_ms:
                rule_id = "VS_QTC_PROLONGED"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    severity = "critical" if qtc_val >= qtc_critical_ms else "high"
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="QTc明显延长风险",
                        category="vital_signs",
                        alert_type="qtc_prolonged",
                        severity=severity,
                        parameter="qtc",
                        condition={"operator": ">", "threshold_ms": qtc_threshold_ms},
                        value=round(float(qtc_val), 2),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=qtc_time or cap.get("time"),
                        extra={
                            "qtc_ms": round(float(qtc_val), 2),
                            "qtc_threshold_ms": qtc_threshold_ms,
                            "source_code": qtc_code,
                            "torsades_risk": True,
                        },
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self.engine._log_info("生命体征", triggered)
