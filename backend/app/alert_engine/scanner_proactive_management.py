from __future__ import annotations

from datetime import datetime

from .scanners import BaseScanner, ScannerSpec


class ProactiveManagementScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="proactive_management",
                interval_key="proactive_management",
                default_interval=300,
                initial_delay=42,
            ),
        )

    def is_enabled(self) -> bool:
        if not super().is_enabled():
            return False
        cfg = self.engine._proactive_management_cfg()
        return bool(cfg.get("enabled", True))

    async def scan(self) -> None:
        cfg = self.engine._proactive_management_cfg()
        alert_probability = float(cfg.get("alert_probability", 0.45) or 0.45)
        max_patients = int(cfg.get("max_patients_per_cycle", 60) or 60)
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "hisPid": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        now = datetime.now()
        for patient_doc in patients[:max_patients]:
            plan = await self.engine.continuous_risk_assessment(patient_doc.get("_id"))
            if not plan:
                continue
            persisted = await self.engine._persist_proactive_management_plan(patient_doc, plan, now)
            probability = float(((plan.get("risk_profile") or {}).get("deterioration_probability")) or 0.0)
            if probability < alert_probability:
                continue
            pid_str = str(patient_doc.get("_id"))
            rule_id = "PROACTIVE_MANAGEMENT_PLAN"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            explanation = {
                "summary": plan.get("summary") or "患者进入主动管理闭环，建议尽早执行预防性干预。",
                "evidence": [str(item.get("evidence") or item.get("label") or "") for item in (plan.get("risk_profile", {}).get("drivers") or [])[:4]],
                "suggestion": "请优先查看主动管理计划中的前 1-2 项干预建议，并在执行后回填效果。",
                "text": "",
            }
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name="主动管理闭环计划",
                category="proactive_management",
                alert_type="proactive_management_plan",
                severity="critical" if probability >= 0.7 else "high",
                parameter="deterioration_probability",
                condition={"operator": ">=", "threshold": alert_probability},
                value=probability,
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=now,
                extra={
                    "score_record_id": persisted.get("_id"),
                    "plan_id": plan.get("plan_id"),
                    "risk_level": (plan.get("risk_profile") or {}).get("risk_level"),
                    "drivers": (plan.get("risk_profile") or {}).get("drivers") or [],
                    "interventions": (plan.get("interventions") or [])[:4],
                },
                explanation=explanation,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("主动管理闭环", triggered)
