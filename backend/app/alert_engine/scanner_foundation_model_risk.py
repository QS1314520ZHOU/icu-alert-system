from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.icu_foundation_model_service import DEFAULT_FM_TASKS, get_icu_foundation_model_service

from .scanners import BaseScanner, ScannerSpec


class FoundationModelRiskScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="foundation_model_risk_scanner",
                interval_key="foundation_model_risk_scanner",
                default_interval=3600,
                initial_delay=45,
            ),
        )

    def _cfg(self) -> dict[str, Any]:
        ai = (self.engine.config.yaml_cfg or {}).get("ai_service", {})
        cfg = (ai.get("foundation_model") if isinstance(ai, dict) else {}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _thresholds(self) -> dict[str, float]:
        raw = self._cfg().get("thresholds", {})
        defaults = {"mortality": 0.75, "aki": 0.70, "circulation_failure": 0.70}
        if not isinstance(raw, dict):
            return defaults
        return {key: float(raw.get(key, value) or value) for key, value in defaults.items()}

    async def scan(self) -> None:
        cfg = self._cfg()
        if cfg.get("enabled") is False:
            return
        service = get_icu_foundation_model_service(db=self.engine.db, config=self.engine.config, alert_engine=self.engine)
        thresholds = self._thresholds()
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            try:
                predictions = await service.zero_shot_predict(pid_str, list(DEFAULT_FM_TASKS))
            except Exception:
                continue

            tasks = predictions.get("tasks") if isinstance(predictions.get("tasks"), dict) else {}
            await self.engine.db.col("score").insert_one(
                {
                    "patient_id": pid_str,
                    "patient_name": patient_doc.get("name"),
                    "bed": patient_doc.get("hisBed"),
                    "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
                    "score_type": "foundation_model_prediction",
                    "predictions": predictions,
                    "summary": "ICU foundation model risk prediction",
                    "calc_time": now,
                    "updated_at": now,
                }
            )
            if not predictions.get("available"):
                continue

            high_tasks = []
            for task, row in tasks.items():
                if not isinstance(row, dict):
                    continue
                prob = float(row.get("probability") or 0.0)
                if prob >= thresholds.get(str(task), 1.0):
                    high_tasks.append({"task": str(task), "probability": round(prob, 4), "threshold": thresholds.get(str(task))})
            if not high_tasks:
                continue

            top = sorted(high_tasks, key=lambda item: item["probability"], reverse=True)[0]
            severity = self.engine._risk_level_from_probability(float(top["probability"]))
            rule_id = "FM_HIGH_RISK"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name="ICU基础模型高风险预警",
                category="foundation_model",
                alert_type="fm_high_risk",
                severity=severity,
                parameter=str(top["task"]),
                condition={"thresholds": thresholds},
                value=top["probability"],
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=now,
                extra={"high_tasks": high_tasks, "predictions": predictions},
            )
            if alert:
                triggered += 1

        if triggered:
            self.engine._log_info("基础模型风险扫描", triggered)
