from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class CircadianProtectorScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="circadian_protector",
                interval_key="circadian_protector",
                default_interval=900,
                initial_delay=36,
            ),
        )

    async def scan(self) -> None:
        now = datetime.now()
        cfg = self.engine._circadian_cfg()
        if self.engine._morning_summary_window(now):
            await self.engine._emit_morning_summaries(now)
        if not self.engine._is_night_window(now):
            return
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)

            ops = await self.engine._night_operation_count(pid, now)
            if ops > int(cfg.get("night_operation_threshold", 6)):
                rule_id = "CIRCADIAN_CLUSTER_CARE"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="夜间护理干扰偏多，建议聚集化操作",
                        category="circadian",
                        alert_type="cluster_care_recommendation",
                        severity="warning",
                        parameter="night_operations",
                        condition={"operator": ">", "threshold": int(cfg.get("night_operation_threshold", 6))},
                        value=ops,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=now,
                        extra={"night_operations": ops, "night_window": f"{cfg.get('night_start_hour', 22)}:00-{cfg.get('night_end_hour', 6)}:00"},
                    )
                    if alert:
                        triggered += 1

            ecash_status = await self.engine.get_ecash_status(patient_doc) if hasattr(self, "get_ecash_status") else {}
            latest_rass = ((ecash_status.get("sedation") or {}).get("latest_rass") if isinstance(ecash_status, dict) else None)
            target = ((ecash_status.get("sedation") or {}).get("target_rass_range") if isinstance(ecash_status, dict) else None) or [-1, 0]
            if latest_rass is not None and isinstance(target, list) and len(target) == 2:
                if float(target[0]) <= -1 <= float(target[1]) and abs(float(latest_rass) - float(target[0])) > float(cfg.get("night_rass_fluctuation_threshold", 2)):
                    rule_id = "CIRCADIAN_NIGHT_AWAKENING"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="夜间反复觉醒，建议评估环境干扰",
                            category="circadian",
                            alert_type="night_awakening",
                            severity="warning",
                            parameter="night_rass_variation",
                            condition={"target_range": target, "rass_delta_gt": float(cfg.get("night_rass_fluctuation_threshold", 2))},
                            value=latest_rass,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            source_time=now,
                            extra={"latest_rass": latest_rass, "target_range": target},
                        )
                        if alert:
                            triggered += 1

            night_warnings = await self.engine._night_warning_alerts(pid_str, now)
            if len(night_warnings) >= int(cfg.get("night_warning_summary_threshold", 4)):
                rule_id = "CIRCADIAN_NIGHT_ALERT_SUMMARY"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="夜间非紧急报警较多，建议晨间汇总复盘",
                        category="circadian",
                        alert_type="night_alert_summary",
                        severity="warning",
                        parameter="night_warning_alerts",
                        condition={"operator": ">=", "threshold": int(cfg.get("night_warning_summary_threshold", 4))},
                        value=len(night_warnings),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=now,
                        extra={"night_warning_count": len(night_warnings), "alerts": night_warnings[:10]},
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self.engine._log_info("昼夜节律保护", triggered)
