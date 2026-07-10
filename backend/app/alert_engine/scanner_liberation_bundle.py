from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class LiberationBundleScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="liberation_bundle",
                interval_key="liberation_bundle",
                default_interval=900,
                initial_delay=53,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            status = await self.engine.get_liberation_bundle_status(patient_doc)
            lights = status.get("lights", {})
            red_items = [k for k, v in lights.items() if v == "red"]
            if not red_items:
                continue
            pid_str = str(patient_doc.get("_id"))
            rule_id = "LIBERATION_BUNDLE_OVERDUE"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name="ABCDEF Bundle 合规待补全",
                category="bundle",
                alert_type="liberation_bundle",
                severity="warning" if len(red_items) <= 2 else "high",
                parameter="bundle_lights",
                condition={"red_items": red_items},
                value=len(red_items),
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=status.get("updated_at"),
                extra=status,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("Bundle合规", triggered)
