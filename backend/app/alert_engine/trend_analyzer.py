"""趋势恶化检测"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import _detect_trend, _extract_param


class TrendMixin:
    def _series_std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return ((sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5)

    def _acute_shift(self, values: list[float], multiplier: float, min_delta: float) -> tuple[bool, float]:
        if len(values) < 4:
            return False, 0.0
        pivot = max(2, len(values) // 2)
        before = values[:pivot]
        after = values[pivot:]
        if not before or not after:
            return False, 0.0
        delta = after[-1] - before[0]
        baseline_sd = self._series_std(before)
        threshold = max(min_delta, baseline_sd * multiplier)
        return abs(delta) >= threshold, round(delta, 3)

    def _subacute_shift(self, values: list[float], slope_threshold: float) -> tuple[bool, dict]:
        trend = _detect_trend(values, window=len(values))
        monotonic_up = sum(1 for i in range(1, len(values)) if values[i] >= values[i - 1]) >= max(3, len(values) - 2)
        monotonic_down = sum(1 for i in range(1, len(values)) if values[i] <= values[i - 1]) >= max(3, len(values) - 2)
        ok = abs(trend.get("slope", 0.0)) >= slope_threshold and (monotonic_up or monotonic_down)
        return ok, {"trend": trend, "monotonic_up": monotonic_up, "monotonic_down": monotonic_down}

    def _cyclic_shift(self, values: list[float], amplitude_threshold: float) -> tuple[bool, dict]:
        if len(values) < 6:
            return False, {}
        diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
        sign_changes = sum(1 for i in range(1, len(diffs)) if diffs[i] * diffs[i - 1] < 0)
        amplitude = max(values) - min(values)
        ok = sign_changes >= 3 and amplitude >= amplitude_threshold
        return ok, {"sign_changes": sign_changes, "amplitude": round(amplitude, 3)}

    async def scan_trends(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        trend_rules = [
            {"param": "param_HR", "name": "心率急性恶化", "direction": "rising", "acute_min_delta": 20.0, "subacute_slope": 3.0, "cycle_amp": 25.0},
            {"param": "param_spo2", "name": "血氧恶化趋势", "direction": "falling", "acute_min_delta": 4.0, "subacute_slope": 1.0, "cycle_amp": 5.0},
            {"param": "param_resp", "name": "呼吸频率恶化趋势", "direction": "rising", "acute_min_delta": 6.0, "subacute_slope": 1.5, "cycle_amp": 8.0},
            {"param": "param_nibp_m", "name": "平均动脉压下降趋势", "direction": "falling", "acute_min_delta": 12.0, "subacute_slope": 2.0, "cycle_amp": 10.0},
            {"param": "param_T", "name": "体温异常趋势", "direction": "rising", "acute_min_delta": 0.8, "subacute_slope": 0.15, "cycle_amp": 1.0},
        ]

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        adv_cfg = self._cfg("alert_engine", "trend_analysis_advanced", default={}) or {}
        acute_window_minutes = int(adv_cfg.get("acute_window_minutes", 30))
        acute_sd_multiplier = float(adv_cfg.get("acute_sd_multiplier", 3.0))
        subacute_window_hours = float(adv_cfg.get("subacute_window_hours", 6))
        cyclic_window_hours = float(adv_cfg.get("cyclic_window_hours", 2))

        triggered = 0
        for p in patients:
            pid = p.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            patient_doc = p

            for tr in trend_rules:
                since = now - timedelta(hours=max(subacute_window_hours, cyclic_window_hours, 2))
                series = await self._get_param_series_by_pid(pid, tr["param"], since, prefer_device_types=["monitor"])
                series = self._filter_series_quality(tr["param"], series)
                values = [float(v["value"]) for v in series if v.get("value") is not None]
                if len(values) < 5:
                    continue

                acute_cutoff = now - timedelta(minutes=acute_window_minutes)
                acute_values = [float(x["value"]) for x in series if x.get("time") and x["time"] >= acute_cutoff]
                subacute_cutoff = now - timedelta(hours=subacute_window_hours)
                subacute_values = [float(x["value"]) for x in series if x.get("time") and x["time"] >= subacute_cutoff]
                cyclic_cutoff = now - timedelta(hours=cyclic_window_hours)
                cyclic_values = [float(x["value"]) for x in series if x.get("time") and x["time"] >= cyclic_cutoff]

                acute_match, acute_delta = self._acute_shift(acute_values, acute_sd_multiplier, tr["acute_min_delta"])
                subacute_match, subacute_detail = self._subacute_shift(subacute_values, tr["subacute_slope"])
                cyclic_match, cyclic_detail = self._cyclic_shift(cyclic_values, tr["cycle_amp"])

                pattern = None
                severity = "warning"
                detail = {"acute_delta": acute_delta, **subacute_detail, **cyclic_detail}
                if acute_match:
                    pattern = "acute"
                    severity = "high" if tr["param"] != "param_spo2" else "critical"
                elif subacute_match:
                    direction = subacute_detail.get("trend", {}).get("direction")
                    if tr["direction"] == direction:
                        pattern = "subacute"
                        severity = "warning" if tr["param"] == "param_T" else "high"
                elif cyclic_match and tr["param"] in {"param_spo2", "param_resp"}:
                    pattern = "cyclic"
                    severity = "warning"

                if not pattern:
                    continue

                rule_id = f"TREND_{tr['param']}_{pattern.upper()}"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue

                alert = await self._create_alert(
                    rule_id=rule_id,
                    name=f"{tr['name']}({ '急性' if pattern == 'acute' else '亚急性' if pattern == 'subacute' else '周期性' })",
                    category="trend",
                    alert_type="trend_analysis",
                    severity=severity,
                    parameter=tr["param"],
                    condition={"pattern": pattern, "direction": tr["direction"], "points": len(values)},
                    value=values[-1],
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=series[-1]["time"] if series else None,
                    extra={
                        "pattern": pattern,
                        "recent_values": values[-6:],
                        "acute_window_minutes": acute_window_minutes,
                        "subacute_window_hours": subacute_window_hours,
                        "cyclic_window_hours": cyclic_window_hours,
                        **detail,
                    },
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("趋势预警", triggered)

