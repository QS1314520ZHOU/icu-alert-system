"""趋势恶化检测"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import _detect_trend, _extract_param


class TrendMixin:
    async def scan_trends(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        since = datetime.now() - timedelta(hours=2)

        trend_rules = [
            {"param": "param_HR", "name": "心率持续上升", "direction": "rising", "min_slope": 2.0, "severity": "warning"},
            {"param": "param_HR", "name": "心率持续下降", "direction": "falling", "min_slope": 2.0, "severity": "warning"},
            {"param": "param_spo2", "name": "血氧持续下降", "direction": "falling", "min_slope": 0.5, "severity": "high"},
            {"param": "param_resp", "name": "呼吸频率持续上升", "direction": "rising", "min_slope": 1.5, "severity": "warning"},
            {"param": "param_nibp_s", "name": "收缩压持续下降", "direction": "falling", "min_slope": 3.0, "severity": "high"},
            {"param": "param_T", "name": "体温持续上升", "direction": "rising", "min_slope": 0.2, "severity": "warning"},
        ]

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for p in patients:
            pid = p.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            patient_doc = p

            for tr in trend_rules:
                series = await self._get_param_series_by_pid(pid, tr["param"], since, prefer_device_types=["monitor"])
                values = [v["value"] for v in series if v.get("value") is not None]
                if len(values) < 5:
                    continue

                trend = _detect_trend(values)

                match = False
                if tr["direction"] == "rising" and trend["direction"] == "rising" and trend["slope"] >= tr["min_slope"]:
                    match = True
                elif tr["direction"] == "falling" and trend["direction"] == "falling" and abs(trend["slope"]) >= tr["min_slope"]:
                    match = True

                if not match:
                    continue

                rule_id = f"TREND_{tr['param']}_{tr['direction'].upper()}"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue

                alert = await self._create_alert(
                    rule_id=rule_id,
                    name=tr["name"],
                    category="trend",
                    alert_type="trend_analysis",
                    severity=tr["severity"],
                    parameter=tr["param"],
                    condition={"direction": trend["direction"], "slope": trend["slope"], "points": len(values)},
                    value=values[-1],
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=series[-1]["time"] if series else None,
                    extra={"trend": trend, "recent_values": values[-5:]},
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("趋势预警", triggered)

