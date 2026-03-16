"""生命体征阈值预警 + 心律/QTc扩展规则"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .base import _eval_condition, _extract_param, _parse_dt


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


class VitalSignsMixin:
    async def _baseline_guard(
        self,
        *,
        pid,
        patient_doc: dict | None,
        param: str,
        value: float,
        direction: str | None,
    ) -> tuple[bool, bool, dict | None]:
        cfg = self._cfg("alert_engine", "patient_baseline", default={}) or {}
        if not bool(cfg.get("enabled", True)):
            return False, False, None
        baseline = await self._get_patient_baseline(
            pid,
            param,
            hours=int(cfg.get("hours", 12)),
            patient_doc=patient_doc,
            prefer_device_types=["monitor"],
        )
        if not baseline or baseline.get("count", 0) < int(cfg.get("min_points", 3)):
            return False, False, baseline
        mean = float(baseline.get("mean") or 0.0)
        std = float(baseline.get("std") or 0.0)
        abs_floor = float(cfg.get("absolute_floor", 2.0))
        rel_floor = abs(mean) * float(cfg.get("relative_tolerance", 0.08))
        tol = max(std * float(cfg.get("zscore_tolerance", 2.0)), abs_floor, rel_floor)
        baseline["tolerance"] = round(tol, 4)
        delta = float(value) - mean
        baseline["delta"] = round(delta, 4)
        baseline["within_baseline"] = False
        baseline["deviation_triggered"] = False
        if direction == "low":
            within = float(value) >= mean - tol
            deviated = float(value) < mean - tol
        elif direction == "high":
            within = float(value) <= mean + tol
            deviated = float(value) > mean + tol
        else:
            within = abs(delta) <= tol
            deviated = abs(delta) > tol
        baseline["within_baseline"] = within
        baseline["deviation_triggered"] = deviated
        return within, deviated, baseline

    async def _confirm_vital_rule(
        self,
        *,
        pid,
        patient_doc: dict | None,
        param: str,
        value: float,
        condition: dict,
        cap: dict,
        now: datetime,
    ) -> tuple[bool, dict[str, Any]]:
        op = str((condition or {}).get("operator") or "")
        threshold = _to_float((condition or {}).get("threshold"))
        detail: dict[str, Any] = {}

        map_codes = set(self._cfg("vital_signs", "map_priority", default=["param_ibp_m", "param_nibp_m"]) or [])
        sbp_codes = set(self._cfg("vital_signs", "sbp_priority", default=["param_ibp_s", "param_nibp_s"]) or [])
        rr = _extract_param(cap, self._cfg("vital_signs", "resp_rate", "code", default="param_resp"))
        hr = _extract_param(cap, self._cfg("vital_signs", "heart_rate", "code", default="param_HR"))
        temp = _extract_param(cap, self._cfg("vital_signs", "temperature", "code", default="param_T"))

        if param in map_codes and op in {"<", "<="} and threshold is not None:
            code = param
            series = await self._get_param_series_by_pid(pid, code, now - timedelta(minutes=20), prefer_device_types=["monitor"], limit=30)
            series = self._filter_series_quality(code, series)
            low_points = [s for s in series[-3:] if _to_float(s.get("value")) is not None and float(s["value"]) < threshold]
            detail["confirm_low_points"] = len(low_points)
            if len(low_points) >= 2:
                return True, detail
            if value < threshold and hr is not None and hr > 100:
                detail["tachycardia_support"] = round(float(hr), 2)
                return True, detail
            return False, detail

        if param in sbp_codes and op in {"<", "<="} and threshold is not None:
            code = param
            series = await self._get_param_series_by_pid(pid, code, now - timedelta(minutes=20), prefer_device_types=["monitor"], limit=30)
            series = self._filter_series_quality(code, series)
            low_points = [s for s in series[-3:] if _to_float(s.get("value")) is not None and float(s["value"]) < threshold]
            detail["confirm_low_points"] = len(low_points)
            if len(low_points) >= 2:
                return True, detail
            if value < threshold and hr is not None and hr > 100:
                detail["tachycardia_support"] = round(float(hr), 2)
                return True, detail
            return False, detail

        if param == self._cfg("vital_signs", "spo2", "code", default="param_spo2") and op in {"<", "<="} and threshold is not None:
            series = await self._get_param_series_by_pid(pid, param, now - timedelta(minutes=15), prefer_device_types=["monitor"], limit=30)
            series = self._filter_series_quality(param, series)
            low_points = [s for s in series[-3:] if _to_float(s.get("value")) is not None and float(s["value"]) < threshold]
            detail["confirm_low_points"] = len(low_points)
            if len(low_points) >= 2:
                return True, detail
            if value < threshold and rr is not None and rr > 25:
                detail["rr_support"] = round(float(rr), 2)
                return True, detail
            return False, detail

        if param == self._cfg("vital_signs", "heart_rate", "code", default="param_HR") and op in {">", ">="}:
            if value >= 130:
                detail["high_hr_direct"] = round(float(value), 2)
                return True, detail
            if value > 110 and temp is not None and 36 <= temp <= 38:
                detail["normothermia_support"] = round(float(temp), 2)
                return True, detail
            return False, detail

        return True, detail

    def _text_has_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

    def _rhythm_text(self, doc: dict) -> str:
        return " ".join(
            str(doc.get(k) or "")
            for k in ("strVal", "value", "name", "paramName", "itemName", "remark", "desc", "text")
        ).lower()

    def _rhythm_point(
        self,
        doc: dict,
        af_keywords: list[str],
        afl_keywords: list[str],
        irregular_keywords: list[str],
        arrhythmia_flag_codes: list[str],
    ) -> dict | None:
        t = _parse_dt(doc.get("time"))
        if not t:
            return None
        code = str(doc.get("code") or "").strip().lower()
        text = self._rhythm_text(doc)

        is_af = self._text_has_any(text, af_keywords)
        is_afl = self._text_has_any(text, afl_keywords)
        irregular = is_af or is_afl or self._text_has_any(text, irregular_keywords)

        if (not irregular) and code and code in {str(c).lower() for c in arrhythmia_flag_codes}:
            flag_val = _to_float(doc.get("fVal"))
            if flag_val is None:
                flag_val = _to_float(doc.get("intVal"))
            if flag_val is None:
                flag_val = _to_float(doc.get("value"))
            if flag_val is None:
                flag_val = _to_float(doc.get("strVal"))
            irregular = flag_val is not None and flag_val > 0

        return {
            "time": t,
            "code": code,
            "text": text,
            "irregular": bool(irregular),
            "is_af": bool(is_af),
            "is_afl": bool(is_afl),
        }

    async def _get_rhythm_points(
        self,
        device_id: str,
        since: datetime,
        rhythm_codes: list[str],
        af_keywords: list[str],
        afl_keywords: list[str],
        irregular_keywords: list[str],
        arrhythmia_flag_codes: list[str],
    ) -> list[dict]:
        query: dict = {"deviceID": device_id, "time": {"$gte": since}}
        use_codes = [str(c).strip() for c in rhythm_codes if str(c).strip()]
        if use_codes:
            query["code"] = {"$in": use_codes}

        cursor = self.db.col("deviceCap").find(
            query,
            {
                "time": 1,
                "code": 1,
                "strVal": 1,
                "value": 1,
                "fVal": 1,
                "intVal": 1,
                "name": 1,
                "paramName": 1,
                "itemName": 1,
                "remark": 1,
                "desc": 1,
                "text": 1,
            },
        ).sort("time", 1).limit(4000)

        points: list[dict] = []
        async for doc in cursor:
            pt = self._rhythm_point(
                doc,
                af_keywords=af_keywords,
                afl_keywords=afl_keywords,
                irregular_keywords=irregular_keywords,
                arrhythmia_flag_codes=arrhythmia_flag_codes,
            )
            if pt:
                points.append(pt)
        return points

    def _find_irregular_segments(self, points: list[dict], max_gap_seconds: int) -> list[dict]:
        irregular_points = [p for p in points if p.get("irregular")]
        if not irregular_points:
            return []

        segments: list[dict] = []
        seg_start = irregular_points[0]["time"]
        seg_end = irregular_points[0]["time"]
        has_af = irregular_points[0].get("is_af", False)
        has_afl = irregular_points[0].get("is_afl", False)
        for p in irregular_points[1:]:
            t = p["time"]
            gap = (t - seg_end).total_seconds()
            if gap <= max_gap_seconds:
                seg_end = t
                has_af = has_af or p.get("is_af", False)
                has_afl = has_afl or p.get("is_afl", False)
                continue
            segments.append(
                {
                    "start": seg_start,
                    "end": seg_end,
                    "duration_seconds": max(0.0, (seg_end - seg_start).total_seconds()),
                    "has_af": has_af,
                    "has_afl": has_afl,
                }
            )
            seg_start = t
            seg_end = t
            has_af = p.get("is_af", False)
            has_afl = p.get("is_afl", False)

        segments.append(
            {
                "start": seg_start,
                "end": seg_end,
                "duration_seconds": max(0.0, (seg_end - seg_start).total_seconds()),
                "has_af": has_af,
                "has_afl": has_afl,
            }
        )
        return segments

    async def _has_prior_af_afl(
        self,
        device_id: str,
        seg_start: datetime,
        lookback_hours: float,
        rhythm_codes: list[str],
        af_keywords: list[str],
        afl_keywords: list[str],
        irregular_keywords: list[str],
        arrhythmia_flag_codes: list[str],
    ) -> bool:
        since = seg_start - timedelta(hours=max(1.0, lookback_hours))
        points = await self._get_rhythm_points(
            device_id=device_id,
            since=since,
            rhythm_codes=rhythm_codes,
            af_keywords=af_keywords,
            afl_keywords=afl_keywords,
            irregular_keywords=irregular_keywords,
            arrhythmia_flag_codes=arrhythmia_flag_codes,
        )
        for p in points:
            t = p.get("time")
            if not isinstance(t, datetime):
                continue
            if t >= seg_start:
                continue
            if p.get("is_af") or p.get("is_afl"):
                return True
        return False

    async def _latest_qtc(self, pid, qtc_codes: list[str], lookback_hours: float) -> tuple[float | None, datetime | None, str | None]:
        since = datetime.now() - timedelta(hours=max(1.0, lookback_hours))
        latest_val = None
        latest_t = None
        latest_code = None
        for code in qtc_codes:
            c = str(code).strip()
            if not c:
                continue
            series = await self._get_param_series_by_pid(pid, c, since, prefer_device_types=["monitor"], limit=2000)
            if not series:
                continue
            t = series[-1].get("time")
            v = _to_float(series[-1].get("value"))
            if v is None or not isinstance(t, datetime):
                continue
            if (latest_t is None) or (t > latest_t):
                latest_t = t
                latest_val = v
                latest_code = c
        return latest_val, latest_t, latest_code

    async def _sbp_drop(self, pid, now: datetime, window_minutes: int) -> dict | None:
        since = now - timedelta(minutes=max(5, int(window_minutes)))
        sbp_codes = self._cfg("vital_signs", "sbp_priority", default=["param_ibp_s", "param_nibp_s"]) or ["param_ibp_s", "param_nibp_s"]

        best_series: list[dict] = []
        best_code = None
        for code in sbp_codes:
            series = await self._get_param_series_by_pid(pid, str(code), since, prefer_device_types=["monitor"], limit=2000)
            if len(series) > len(best_series):
                best_series = series
                best_code = str(code)
        if len(best_series) < 2:
            return None

        latest = _to_float(best_series[-1].get("value"))
        if latest is None:
            return None
        previous_vals = [_to_float(x.get("value")) for x in best_series[:-1]]
        previous_vals = [x for x in previous_vals if x is not None]
        if not previous_vals:
            return None
        baseline = max(previous_vals)
        drop = baseline - latest
        return {
            "latest_sbp": round(latest, 2),
            "baseline_sbp": round(baseline, 2),
            "drop_sbp": round(drop, 2),
            "code": best_code,
            "latest_time": best_series[-1].get("time"),
        }

    async def scan_vital_signs(self) -> None:
        rules = [r async for r in self.db.col("alert_rules").find({"enabled": True, "category": "vital_signs"})]

        binds = [b async for b in self.db.col("deviceBind").find(
            {"unBindTime": None, "type": "monitor"}, {"pid": 1, "deviceID": 1}
        )]
        if not binds:
            binds = [b async for b in self.db.col("deviceBind").find(
                {"unBindTime": None}, {"pid": 1, "deviceID": 1}
            )]
        if not binds:
            return

        now = datetime.now()
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        adv_cfg = self.config.yaml_cfg.get("alert_engine", {}).get("vital_signs_advanced", {})
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
                self._cfg("vital_signs", "rhythm", "code", default="param_xinLvLv"),
                "rhythm_type",
                "param_rhythm_type",
                "arrhythmia_flag",
                "param_arrhythmia_flag",
            ],
        )
        arrhythmia_flag_codes = adv_cfg.get("arrhythmia_flag_codes", ["arrhythmia_flag", "param_arrhythmia_flag"])

        qtc_codes = adv_cfg.get(
            "qtc_codes",
            self._cfg("alert_engine", "data_mapping", "qtc_codes", default=["param_qtc", "param_QTc", "ecg_qtc", "qtc"]),
        )
        if not isinstance(qtc_codes, list):
            qtc_codes = ["param_qtc", "param_QTc", "ecg_qtc", "qtc"]

        triggered = 0
        for b in binds:
            device_id = b.get("deviceID")
            pid = b.get("pid")
            if not device_id or not pid:
                continue

            cap = await self._get_latest_device_cap(device_id)
            if not cap:
                continue

            cap_time = _parse_dt(cap.get("time"))
            if cap_time and (now - cap_time).total_seconds() > 600:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not pid_str:
                continue
            cap, quality_issues = await self._filter_snapshot_quality(
                pid=pid,
                pid_str=pid_str,
                patient_doc=patient_doc,
                cap=cap,
                device_id=device_id,
                same_rule_sec=same_rule_sec,
                max_per_hour=max_per_hour,
            )

            # 现有阈值规则
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
                within_baseline, baseline_deviation, baseline_meta = await self._baseline_guard(
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

                confirmed, confirm_detail = await self._confirm_vital_rule(
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

                if await self._is_suppressed(pid_str, rule.get("rule_id"), same_rule_sec, max_per_hour):
                    continue

                alert = await self._create_alert(
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

            # (1) 新发房颤/房扑: HR>100 + 不规则持续>5分钟
            rhythm_points = await self._get_rhythm_points(
                device_id=device_id,
                since=now - timedelta(minutes=max(af_rhythm_lookback_m, 10)),
                rhythm_codes=rhythm_codes,
                af_keywords=af_keywords,
                afl_keywords=afl_keywords,
                irregular_keywords=irregular_keywords,
                arrhythmia_flag_codes=arrhythmia_flag_codes,
            )
            if rhythm_points:
                segments = self._find_irregular_segments(rhythm_points, af_max_gap_sec)
                long_segments = [s for s in segments if s.get("duration_seconds", 0) >= af_duration_sec]
                if long_segments:
                    seg = long_segments[-1]
                    hr_series = await self._get_param_series_by_pid(
                        pid,
                        self._cfg("vital_signs", "heart_rate", "code", default="param_HR"),
                        now - timedelta(minutes=max(af_rhythm_lookback_m, 10)),
                        prefer_device_types=["monitor"],
                        limit=2000,
                    )
                    hr_peak = None
                    for hp in hr_series:
                        t = hp.get("time")
                        v = _to_float(hp.get("value"))
                        if v is None or not isinstance(t, datetime):
                            continue
                        if seg["start"] <= t <= seg["end"]:
                            hr_peak = v if (hr_peak is None or v > hr_peak) else hr_peak

                    if hr_peak is not None and hr_peak > af_hr_threshold:
                        prior_af = await self._has_prior_af_afl(
                            device_id=device_id,
                            seg_start=seg["start"],
                            lookback_hours=af_new_onset_h,
                            rhythm_codes=rhythm_codes,
                            af_keywords=af_keywords,
                            afl_keywords=afl_keywords,
                            irregular_keywords=irregular_keywords,
                            arrhythmia_flag_codes=arrhythmia_flag_codes,
                        )
                        if not prior_af:
                            rule_id = "VS_NEW_AF_AFL"
                            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                                alert = await self._create_alert(
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
                                    source_time=seg["end"],
                                    extra={
                                        "segment_start": seg["start"],
                                        "segment_end": seg["end"],
                                        "irregular_duration_seconds": round(seg["duration_seconds"], 1),
                                        "has_af_tag": seg.get("has_af"),
                                        "has_afl_tag": seg.get("has_afl"),
                                        "hr_peak_in_segment": round(hr_peak, 2),
                                    },
                                )
                                if alert:
                                    triggered += 1

            # (2) 心动过缓 + SBP下降
            latest_hr = _extract_param(cap, self._cfg("vital_signs", "heart_rate", "code", default="param_HR"))
            if latest_hr is not None and latest_hr < brady_hr_threshold:
                sbp_info = await self._sbp_drop(pid, now, brady_window_minutes)
                if sbp_info and sbp_info.get("drop_sbp", 0) > brady_sbp_drop_threshold:
                    rule_id = "VS_BRADY_HYPOTENSION"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
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

            # (3) 直接QTc延长
            qtc_val, qtc_time, qtc_code = await self._latest_qtc(pid, qtc_codes, qtc_lookback_hours)
            if qtc_val is not None and qtc_val > qtc_threshold_ms:
                rule_id = "VS_QTC_PROLONGED"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    sev = "critical" if qtc_val >= qtc_critical_ms else "high"
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="QTc明显延长风险",
                        category="vital_signs",
                        alert_type="qtc_prolonged",
                        severity=sev,
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
            self._log_info("生命体征", triggered)
