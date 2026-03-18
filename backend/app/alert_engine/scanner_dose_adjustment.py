from __future__ import annotations

from datetime import datetime
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class DoseAdjustmentScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="dose_adjustment",
                interval_key="dose_adjustment",
                default_interval=1800,
                initial_delay=57,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "gender": 1, "hisSex": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            his_pid = patient_doc.get("hisPid")
            if not pid or not his_pid:
                continue

            pid_str = str(pid)
            labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=72)
            if not labs:
                continue

            aki = await self.engine._calc_aki_stage(patient_doc, pid, his_pid)
            crrt = await self.engine._get_device_id_for_patient(patient_doc, ["crrt"])
            cr = labs.get("cr", {}).get("value")
            egfr = labs.get("egfr", {}).get("value") or self.engine._estimate_egfr(patient_doc, cr)
            renal_risk = bool((egfr is not None and egfr < 30) or (aki and aki.get("stage", 0) >= 2) or crrt)
            hepatic = self.engine._hepatic_risk_summary(labs)

            if not renal_risk and not hepatic["risk"]:
                continue

            recent_docs = await self.engine._get_recent_drug_docs_window(pid, hours=24, limit=800)
            if not recent_docs:
                continue

            if renal_risk:
                for drug in self.engine.RENAL_DRUG_TABLE:
                    matched = self.engine._match_drug_docs(recent_docs, drug["keywords"])
                    if not matched:
                        continue
                    if self.engine._dose_changed_recently(matched):
                        continue
                    latest = matched[-1]
                    rule_id = f"RENAL_DOSE_{drug['name']}"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    if await self.engine._create_dose_adjustment_alert(
                        patient_doc=patient_doc,
                        pid_str=pid_str,
                        latest_doc=latest,
                        rule_id=rule_id,
                        name=f"{drug['name']}需评估肾功能剂量调整",
                        alert_type="renal_dose_adjustment",
                        severity="high",
                        value=egfr if egfr is not None else (aki.get("stage") if aki else None),
                        extra={
                            "drug_name": drug["name"],
                            "current_dose": self.engine._format_current_dose(latest),
                            "suggestion": drug["suggestion"],
                            "reference": drug["reference"],
                            "recent_order_count_24h": len(matched),
                            "recent_adjustment_detected": False,
                            "eGFR": egfr,
                            "aki_stage": aki.get("stage") if aki else None,
                            "on_crrt": bool(crrt),
                            "condition": {"renal_risk": True},
                        },
                    ):
                        triggered += 1

            if hepatic["risk"]:
                for drug in self.engine.HEPATIC_DRUG_TABLE:
                    matched = self.engine._match_drug_docs(recent_docs, drug["keywords"])
                    if not matched:
                        continue
                    if self.engine._dose_changed_recently(matched):
                        continue
                    latest = matched[-1]
                    rule_id = f"HEPATIC_DOSE_{drug['name']}"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    severity = "high" if hepatic["severity"] == "high" else "warning"
                    if await self.engine._create_dose_adjustment_alert(
                        patient_doc=patient_doc,
                        pid_str=pid_str,
                        latest_doc=latest,
                        rule_id=rule_id,
                        name=f"{drug['name']}需评估肝功能相关剂量/停药",
                        alert_type="hepatic_dose_adjustment",
                        severity=severity,
                        value=hepatic["bilirubin"] or hepatic["alt"] or hepatic["ast"],
                        extra={
                            "drug_name": drug["name"],
                            "current_dose": self.engine._format_current_dose(latest),
                            "suggestion": drug["suggestion"],
                            "reference": drug["reference"],
                            "recent_order_count_24h": len(matched),
                            "recent_adjustment_detected": False,
                            "bilirubin": hepatic["bilirubin"],
                            "alt": hepatic["alt"],
                            "ast": hepatic["ast"],
                            "hepatic_severity": hepatic["severity"],
                            "hepatic_reasons": hepatic["reasons"],
                            "condition": {"hepatic_risk": True, "hepatic_severity": hepatic["severity"]},
                        },
                    ):
                        triggered += 1

        if triggered > 0:
            self.engine._log_info("剂量调整", triggered)
