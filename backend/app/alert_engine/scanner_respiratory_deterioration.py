from __future__ import annotations

from datetime import datetime

from .scanners import BaseScanner, ScannerSpec


class RespiratoryDeteriorationScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="respiratory_deterioration",
                interval_key="respiratory_deterioration",
                default_interval=900,
                initial_delay=75,
                maturity="experimental",
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("respiratory_deterioration", {})
        if isinstance(cfg, dict) and cfg.get("enabled") is False:
            return
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1},
        ).limit(int((cfg or {}).get("max_patients", 120) or 120))
        triggered = 0
        async for patient in cursor:
            pid = str(patient.get("_id") or "")
            if not pid:
                continue
            bind = await self.engine._get_active_vent_bind(pid)
            if not bind:
                continue
            forecast = await self.engine.build_respiratory_deterioration_forecast(patient, now=now)
            await self.engine.persist_respiratory_deterioration_forecast(patient, forecast, now=now)
            severity = str(forecast.get("severity") or "none").lower()
            if severity not in {"warning", "high", "critical"}:
                continue
            rule_id = "RESPIRATORY_DETERIORATION_FORECAST"
            if await self.engine._is_suppressed(pid, rule_id, same_rule_sec, max_per_hour):
                continue
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name="Respiratory deterioration forecast",
                category="respiratory",
                alert_type="respiratory_deterioration_forecast",
                severity=severity,
                parameter="spo2_fio2_trend",
                condition=forecast.get("thresholds") or {},
                value=(forecast.get("features") or {}).get("latest_sf_ratio"),
                patient_id=pid,
                patient_doc=patient,
                device_id=bind.get("deviceID"),
                source_time=now,
                extra={
                    "maturity": "experimental",
                    "forecast": forecast.get("forecast") or {},
                    "features": forecast.get("features") or {},
                    "data_completeness": forecast.get("data_completeness") or {},
                    "model_meta": forecast.get("model_meta") or {},
                    "evidence": forecast.get("evidence") or [],
                },
                explanation={
                    "summary": "SpO2/FiO2 trend suggests possible respiratory deterioration.",
                    "evidence": forecast.get("evidence") or [],
                    "suggestion": "Review ventilator settings, oxygenation trend, airway status, and bedside condition. Experimental signal only; clinician confirmation required.",
                    "text": "",
                },
            )
            if alert:
                triggered += 1
        if triggered:
            self.engine._log_info("respiratory_deterioration", triggered)
