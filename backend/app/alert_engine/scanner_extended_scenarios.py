from __future__ import annotations

from datetime import datetime

from .scanners import BaseScanner, ScannerSpec


class ExtendedScenariosScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="extended_scenarios",
                interval_key="extended_scenarios",
                default_interval=1800,
                initial_delay=73,
            ),
        )

    def is_enabled(self) -> bool:
        return super().is_enabled() and bool(self.engine._extended_scenario_list())

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1, "history": 1, "diagnosisHistory": 1, "surgeryHistory": 1, "operationHistory": 1, "chiefComplaint": 1, "presentIllness": 1, "allDiagnosis": 1, "pastHistory": 1},
        )
        patients = [p async for p in patient_cursor]
        scenario_defs = self.engine._extended_scenario_list()
        if not patients or not scenario_defs:
            return

        now = datetime.now()
        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = self.engine._pid_str(pid)
            context = await self.engine._extended_snapshot(patient_doc, pid)
            for group, scenario in scenario_defs:
                result = await self.engine._evaluate_extended_scenario(group=group, scenario=scenario, patient_doc=patient_doc, context=context, now=now)
                if not result:
                    continue
                rule_id = f"EXT_{scenario.upper()}"
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                score = float(result.get("score") or 0)
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name=self.engine._scenario_title(scenario),
                    category="extended_scenarios",
                    alert_type=scenario,
                    severity=self.engine._scenario_severity(score),
                    parameter=scenario,
                    condition={"scenario_group": group, "scenario": scenario},
                    value=score,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=context.get("device_id"),
                    source_time=(context.get("vitals") or {}).get("time") or now,
                    extra={"scenario_group": group, "scenario": scenario, **(result.get("extra") if isinstance(result.get("extra"), dict) else {})},
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self.engine._log_info("扩展临床场景", triggered)
