"""趋势恶化检测"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import _detect_trend, _extract_param


class TrendMixin:
    async def scan_trends(self) -> None:
        binds = [b async for b in self.db.col("deviceBind").find({"unBindTime": None}, {"pid": 1, "deviceID": 1})]
        if not binds:
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
        for b in binds:
            device_id = b.get("deviceID")
            pid = b.get("pid")
            if not device_id or not pid:
                continue

            cursor = self.db.col("deviceCap").find(
                {"deviceID": device_id, "time": {"$gte": since}},
                {"time": 1, "params": 1}
            ).sort("time", 1)
            docs = [d async for d in cursor]
            if len(docs) < 5:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not pid_str:
                continue

            for tr in trend_rules:
                values = [_extract_param(d, tr["param"]) for d in docs]
                values = [v for v in values if v is not None]
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
                    device_id=device_id,
                    source_time=docs[-1].get("time"),
                    extra={"trend": trend, "recent_values": values[-5:]},
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("趋势预警", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条预警")