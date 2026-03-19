from __future__ import annotations

from datetime import datetime

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
            spo2 = self.engine._vent_param_priority(cap, ["spo2"], ["param_spo2"]) or self.engine._vent_param(cap, "spo2", "param_spo2")
            if fio2_frac <= 0:
                continue

            ratio_value = None
            ratio_type = None
            severity = None
            name = None
            if pao2 is not None:
                ratio_value = pao2 / fio2_frac
                ratio_type = "pf_ratio"
                if ratio_value <= 100:
                    severity = "critical"
                    name = "ARDS重度"
                elif ratio_value <= 200:
                    severity = "high"
                    name = "ARDS中度"
                elif ratio_value <= 300:
                    severity = "warning"
                    name = "ARDS轻度"
            elif spo2 is not None and float(spo2) <= 97:
                ratio_value = float(spo2) / fio2_frac
                ratio_type = "sf_ratio"
                if ratio_value <= 148:
                    severity = "critical"
                    name = "ARDS重度(SF替代)"
                elif ratio_value <= 235:
                    severity = "high"
                    name = "ARDS中度(SF替代)"
                elif ratio_value <= 315:
                    severity = "warning"
                    name = "ARDS轻度(SF替代)"
            if ratio_value is None or severity is None or not name:
                continue

            bnp_trend = await self.engine._get_bnp_trend(his_pid, datetime.now(), hours=72) if hasattr(self.engine, "_get_bnp_trend") else {}
            cardiogenic_flag = (bnp_trend.get("ratio") or 0) >= 1.5 or (bnp_trend.get("latest") or 0) >= 1000
            explanation = await self.engine._polish_structured_alert_explanation(
                {
                    "summary": f"{name} 风险，当前依据为 {ratio_type.upper()} {round(ratio_value, 1)}、PEEP {peep} cmH2O。",
                    "evidence": [
                        f"FiO2 {fio2}",
                        f"PEEP {peep}",
                        f"PaO2 {pao2}" if pao2 is not None else f"SpO2 {spo2}",
                        "BNP/容量状态提示需排除心源性肺水肿" if cardiogenic_flag else "请临床结合影像和容量状态排除心源性肺水肿",
                    ],
                    "suggestion": "若无动脉血气，可结合 SF ratio 连续复评；若 BNP 升高或容量负荷偏高，请谨慎解释 ARDS 结论。",
                    "text": "",
                }
            )

            effective_severity = severity
            if cardiogenic_flag and severity == "critical":
                effective_severity = "high"
            elif cardiogenic_flag and severity == "high":
                effective_severity = "warning"

            rule_id = "ARDS_" + effective_severity.upper()
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name=name,
                category="syndrome",
                alert_type="ards",
                severity=effective_severity,
                parameter=ratio_type,
                condition={ratio_type: round(ratio_value, 1), "peep": peep, "fio2": fio2},
                value=round(ratio_value, 1),
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                source_time=labs.get("pao2", {}).get("time") if pao2 is not None and labs else datetime.now(),
                explanation=explanation,
                extra={
                    "pao2": pao2,
                    "spo2": spo2,
                    "fio2": fio2,
                    "peep": peep,
                    "ratio_type": ratio_type,
                    "cardiogenic_overlap_risk": cardiogenic_flag,
                    "bnp_trend": bnp_trend,
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("ARDS预警", triggered)
