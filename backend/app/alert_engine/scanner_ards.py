from __future__ import annotations

from .scanners import BaseScanner, ScannerSpec


class ArdsScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="ards",
                interval_key="ards",
                default_interval=300,
                initial_delay=20,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            device_id = await self.engine._get_device_id_for_patient(patient_doc, ["vent"])
            if not device_id:
                continue

            his_pid = patient_doc.get("hisPid")
            if not his_pid:
                continue

            cap = await self.engine._get_latest_device_cap(device_id)
            if not cap:
                continue

            fio2 = self.engine._vent_param(cap, "fio2", "param_FiO2")
            peep = self.engine._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
            if fio2 is None or peep is None or peep < 5:
                continue

            fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
            labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=24)
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
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            alert = await self.engine._create_alert(
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
            self.engine._log_info("ARDS预警", triggered)
