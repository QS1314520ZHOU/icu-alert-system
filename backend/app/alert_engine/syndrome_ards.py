"""ARDS 自动识别"""
from __future__ import annotations


class ArdsMixin:
    async def scan_ards(self) -> None:
        binds = [b async for b in self.db.col("deviceBind").find({"unBindTime": None}, {"pid": 1, "deviceID": 1})]
        if not binds:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for b in binds:
            pid = b.get("pid")
            device_id = b.get("deviceID")
            if not pid or not device_id:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not patient_doc or not pid_str:
                continue

            his_pid = patient_doc.get("hisPid")
            if not his_pid:
                continue

            cap = await self._get_latest_device_cap(device_id)
            if not cap:
                continue

            fio2 = self._vent_param(cap, "fio2", "param_FiO2")
            peep = self._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
            if fio2 is None or peep is None or peep < 5:
                continue

            fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=24)
            pao2 = labs.get("pao2", {}).get("value") if labs else None
            if pao2 is None or fio2_frac <= 0:
                continue

            pf = pao2 / fio2_frac
            severity = None
            name = None
            if pf <= 100:
                severity = "critical"
                name = "ARDS重度"
            elif pf <= 200:
                severity = "high"
                name = "ARDS中度"
            elif pf <= 300:
                severity = "warning"
                name = "ARDS轻度"
            else:
                continue

            rule_id = "ARDS_" + severity.upper()
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            alert = await self._create_alert(
                rule_id=rule_id,
                name=name,
                category="syndrome",
                alert_type="ards",
                severity=severity,
                parameter="pf_ratio",
                condition={"pf_ratio": pf, "peep": peep, "fio2": fio2},
                value=round(pf, 1),
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                source_time=labs.get("pao2", {}).get("time") if labs else None,
                extra={"pao2": pao2, "fio2": fio2, "peep": peep},
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("ARDS预警", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条预警")