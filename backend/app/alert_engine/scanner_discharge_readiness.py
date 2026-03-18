from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class DischargeReadinessScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="discharge_readiness",
                interval_key="discharge_readiness",
                default_interval=1800,
                initial_delay=59,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1, "age": 1, "gender": 1, "hisSex": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            now = datetime.now()
            signal = await self.engine._detect_transfer_candidate_signal(patient_doc, pid_str, now)
            if not signal.get("candidate"):
                continue

            result = await self.engine.evaluate_discharge_readiness(patient_doc)
            if result.get("risk") not in {"medium", "high"}:
                continue

            rule_id = f"DISCHARGE_READINESS_{str(result.get('risk')).upper()}"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            severity = "warning" if result.get("risk") == "medium" else "high"
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name="转出前稳定性复核",
                category="discharge_readiness",
                alert_type="discharge_readiness_risk",
                severity=severity,
                parameter="transfer_readiness",
                condition={"transfer_candidate": True, "risk": result.get("risk")},
                value=result.get("score"),
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=signal.get("time") or now,
                extra={
                    "label": result.get("label"),
                    "checks": result.get("checks"),
                    "context": result.get("context"),
                    "transfer_signal": signal,
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("转出风险评估", triggered)
