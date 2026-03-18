from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class DeviceManagementScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="device_management",
                interval_key="device_management",
                default_interval=3600,
                initial_delay=37,
            ),
        )

    async def scan(self) -> None:
        now = datetime.now()
        if not (7 <= now.hour <= 9):
            return

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "clinicalDiagnosis": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for patient_doc in patients:
            summary = await self.engine._device_management_summary(patient_doc)
            pid_str = str(patient_doc.get("_id"))
            for device in summary.get("devices", []):
                if device["type"] == "cvc" and device.get("can_remove"):
                    rule_id = "DEVICE_CVC_REVIEW"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="CVC必要性评估",
                        category="device_management",
                        alert_type="cvc_review",
                        severity="high" if device.get("line_days", 0) >= 7 else "warning",
                        parameter="cvc_line_days",
                        condition={"operator": ">=", "threshold": 3},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device,
                    )
                    if alert:
                        triggered += 1

                if device["type"] == "foley" and device.get("can_remove"):
                    rule_id = "DEVICE_FOLEY_REVIEW"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="导尿管必要性评估",
                        category="device_management",
                        alert_type="foley_review",
                        severity="warning",
                        parameter="foley_line_days",
                        condition={"operator": ">=", "threshold": 1},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device,
                    )
                    if alert:
                        triggered += 1

                if device["type"] == "ett" and device.get("sbt_passed_no_extubation"):
                    rule_id = "DEVICE_ETT_EXTUBATION_DELAY"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="SBT通过后24h未尝试拔管",
                        category="device_management",
                        alert_type="ett_extubation_delay",
                        severity="high",
                        parameter="ett_line_days",
                        condition={"operator": ">=", "threshold_hours": 24},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device,
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self.engine._log_info("装置管理", triggered)
