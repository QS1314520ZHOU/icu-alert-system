"""生命体征阈值预警"""
from __future__ import annotations

from datetime import datetime

from .base import _eval_condition, _extract_param, _parse_dt


class VitalSignsMixin:
    async def scan_vital_signs(self) -> None:
        rules = [r async for r in self.db.col("alert_rules").find({"enabled": True, "category": "vital_signs"})]
        if not rules:
            return

        binds = [b async for b in self.db.col("deviceBind").find({"unBindTime": None}, {"pid": 1, "deviceID": 1})]
        if not binds:
            return

        now = datetime.now()
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for b in binds:
            device_id = b.get("deviceID")
            pid = b.get("pid")
            if not device_id or not pid:
                continue

            cap = await self.db.col("deviceCap").find_one({"deviceID": device_id}, sort=[("time", -1)])
            if not cap:
                continue

            cap_time = _parse_dt(cap.get("time"))
            if cap_time and (now - cap_time).total_seconds() > 600:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not pid_str:
                continue

            for rule in rules:
                param = rule.get("parameter")
                if not param:
                    continue

                value = _extract_param(cap, param)
                if not _eval_condition(value, rule.get("condition", {})):
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
                    condition=rule.get("condition", {}),
                    value=value,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=cap.get("time"),
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("阈值预警", triggered)

