from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.vital_trajectory_forecaster import SUPPORTED_CODES, get_vital_trajectory_forecaster

from .scanners import BaseScanner, ScannerSpec


class TrajectoryDriftScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="trajectory_drift_scanner",
                interval_key="trajectory_drift_scanner",
                default_interval=3600,
                initial_delay=75,
            ),
        )

    def _cfg(self) -> dict[str, Any]:
        ai = (self.engine.config.yaml_cfg or {}).get("ai_service", {})
        cfg = (ai.get("trajectory_forecast") if isinstance(ai, dict) else {}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan(self) -> None:
        cfg = self._cfg()
        if cfg.get("enabled") is False:
            return
        service = get_vital_trajectory_forecaster(db=self.engine.db, config=self.engine.config, alert_engine=self.engine)
        codes = cfg.get("drift_codes") if isinstance(cfg.get("drift_codes"), list) else ["HR", "MAP", "SpO2", "RR"]
        codes = [str(code) for code in codes if str(code) in SUPPORTED_CODES]
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        patients = [
            doc
            async for doc in self.engine.db.col("patient").find(
                self.engine._active_patient_query(),
                {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
            )
        ]
        triggered = 0
        now = datetime.now()
        for patient in patients:
            pid = str(patient.get("_id") or "")
            if not pid:
                continue
            for code in codes:
                try:
                    drift = await service.drift(pid, code, horizon_hours=1)
                except Exception:
                    continue
                if not drift.get("drift"):
                    continue
                rule_id = "TRAJECTORY_DRIFT"
                if await self.engine._is_suppressed(pid, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name="生命体征轨迹漂移",
                    category="trajectory_forecast",
                    alert_type="trajectory_drift",
                    severity="high",
                    parameter=code,
                    condition={"expected_interval": drift.get("expected")},
                    value=drift.get("actual"),
                    patient_id=pid,
                    patient_doc=patient,
                    source_time=now,
                    extra={"drift": drift},
                )
                if alert:
                    triggered += 1
                    break
        if triggered:
            self.engine._log_info("生命体征轨迹漂移扫描", triggered)
