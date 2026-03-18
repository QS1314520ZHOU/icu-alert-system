from __future__ import annotations

from .scanners import BaseScanner, ScannerSpec


class AkiScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="aki",
                interval_key="aki",
                default_interval=600,
                initial_delay=25,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "dept": 1,
                "hisDept": 1,
                "weight": 1,
                "bodyWeight": 1,
                "body_weight": 1,
                "weightKg": 1,
                "weight_kg": 1,
            },
        )
        patients = [patient async for patient in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for patient_doc in patients:
            his_pid = patient_doc.get("hisPid")
            if not his_pid:
                continue

            stage = await self.engine._calc_aki_stage(patient_doc, patient_doc.get("_id"), his_pid)
            if not stage:
                continue

            rule_id = f"AKI_STAGE_{stage['stage']}"
            patient_id = str(patient_doc.get("_id"))
            if await self.engine._is_suppressed(patient_id, rule_id, same_rule_sec, max_per_hour):
                continue

            severity = {1: "warning", 2: "high", 3: "critical"}.get(stage["stage"], "warning")
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name=f"急性肾损伤KDIGO {stage['stage']}期",
                category="syndrome",
                alert_type="aki",
                severity=severity,
                parameter="creatinine",
                condition=stage.get("condition", {}),
                value=stage.get("current"),
                patient_id=patient_id,
                patient_doc=patient_doc,
                device_id=None,
                source_time=stage.get("time"),
                extra=stage,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("AKI预警", triggered)
