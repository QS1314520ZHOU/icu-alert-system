from __future__ import annotations

from datetime import datetime, timedelta

from .scanners import BaseScanner, ScannerSpec


class TrendScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="trend_analysis",
                interval_key="trend_analysis",
                default_interval=900,
                initial_delay=30,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [patient async for patient in patient_cursor]
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

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        adv_cfg = self.engine._cfg("alert_engine", "trend_analysis_advanced", default={}) or {}
        acute_window_minutes = int(adv_cfg.get("acute_window_minutes", 30))
        acute_sd_multiplier = float(adv_cfg.get("acute_sd_multiplier", 3.0))
        subacute_window_hours = float(adv_cfg.get("subacute_window_hours", 6))
        cyclic_window_hours = float(adv_cfg.get("cyclic_window_hours", 2))

        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)

            for trend_rule in trend_rules:
                since = now - timedelta(hours=max(subacute_window_hours, cyclic_window_hours, 2))
                series = await self.engine._get_param_series_by_pid(pid, trend_rule["param"], since, prefer_device_types=["monitor"])
                series = self.engine._filter_series_quality(trend_rule["param"], series)
                values = [float(point["value"]) for point in series if point.get("value") is not None]
                if len(values) < 5:
                    continue

                acute_cutoff = now - timedelta(minutes=acute_window_minutes)
                acute_values = [float(point["value"]) for point in series if point.get("time") and point["time"] >= acute_cutoff]
                subacute_cutoff = now - timedelta(hours=subacute_window_hours)
                subacute_values = [float(point["value"]) for point in series if point.get("time") and point["time"] >= subacute_cutoff]
                cyclic_cutoff = now - timedelta(hours=cyclic_window_hours)
                cyclic_values = [float(point["value"]) for point in series if point.get("time") and point["time"] >= cyclic_cutoff]

                acute_match, acute_delta = self.engine._acute_shift(acute_values, acute_sd_multiplier, trend_rule["acute_min_delta"])
                subacute_match, subacute_detail = self.engine._subacute_shift(subacute_values, trend_rule["subacute_slope"])
                cyclic_match, cyclic_detail = self.engine._cyclic_shift(cyclic_values, trend_rule["cycle_amp"])

                pattern = None
                severity = "warning"
                detail = {"acute_delta": acute_delta, **subacute_detail, **cyclic_detail}
                if acute_match:
                    pattern = "acute"
                    severity = "high" if trend_rule["param"] != "param_spo2" else "critical"
                elif subacute_match:
                    direction = subacute_detail.get("trend", {}).get("direction")
                    if trend_rule["direction"] == direction:
                        pattern = "subacute"
                        severity = "warning" if trend_rule["param"] == "param_T" else "high"
                elif cyclic_match and trend_rule["param"] in {"param_spo2", "param_resp"}:
                    pattern = "cyclic"
                    severity = "warning"

                if not pattern:
                    continue

                rule_id = f"TREND_{trend_rule['param']}_{pattern.upper()}"
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue

                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name=f"{trend_rule['name']}({'急性' if pattern == 'acute' else '亚急性' if pattern == 'subacute' else '周期性'})",
                    category="trend",
                    alert_type="trend_analysis",
                    severity=severity,
                    parameter=trend_rule["param"],
                    condition={"pattern": pattern, "direction": trend_rule["direction"], "points": len(values)},
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
            self.engine._log_info("趋势预警", triggered)
