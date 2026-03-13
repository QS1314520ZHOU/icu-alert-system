"""AKI KDIGO"""
from __future__ import annotations


class AkiMixin:
    async def scan_aki(self) -> None:
        patient_cursor = self.db.col("patient").find(
            {"isLeave": {"$ne": True}},
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
             "weight": 1, "bodyWeight": 1, "body_weight": 1, "weightKg": 1, "weight_kg": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for p in patients:
            his_pid = p.get("hisPid")
            if not his_pid:
                continue

            stage = await self._calc_aki_stage(p, p.get("_id"), his_pid)
            if not stage:
                continue

            rule_id = f"AKI_STAGE_{stage['stage']}"
            if await self._is_suppressed(str(p.get("_id")), rule_id, same_rule_sec, max_per_hour):
                continue

            severity = {1: "warning", 2: "high", 3: "critical"}.get(stage["stage"], "warning")
            alert = await self._create_alert(
                rule_id=rule_id,
                name=f"急性肾损伤KDIGO {stage['stage']}期",
                category="syndrome",
                alert_type="aki",
                severity=severity,
                parameter="creatinine",
                condition=stage.get("condition", {}),
                value=stage.get("current"),
                patient_id=str(p.get("_id")),
                patient_doc=p,
                device_id=None,
                source_time=stage.get("time"),
                extra=stage,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("AKI预警", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条预警")