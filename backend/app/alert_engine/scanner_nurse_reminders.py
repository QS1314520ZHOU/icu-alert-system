from __future__ import annotations

import re
from datetime import datetime, timedelta
def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None
from .scanners import BaseScanner, ScannerSpec


class NurseRemindersScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="nurse_reminders",
                interval_key="assessments",
                default_interval=600,
                initial_delay=17,
            ),
        )

    async def scan(self) -> None:
        reminders_cfg = self.engine.config.yaml_cfg.get("nurse_reminders", {})
        if not reminders_cfg:
            return

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "name": 1,
                "hisBed": 1,
                "icuAdmissionTime": 1,
                "dept": 1,
                "hisDept": 1,
                "deptCode": 1,
                "weight": 1,
                "bodyWeight": 1,
                "body_weight": 1,
                "weightKg": 1,
                "weight_kg": 1,
                "height": 1,
                "bodyHeight": 1,
                "heightCm": 1,
                "height_cm": 1,
                "bmi": 1,
                "BMI": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        triggered = 0

        for p in patients:
            for score_type, cfg in reminders_cfg.items():
                if not isinstance(cfg, dict):
                    continue
                if score_type in ("turning", "early_mobility"):
                    continue
                if await self.engine._process_assessment_reminder(p, now, score_type, cfg):
                    triggered += 1

            turning_cfg = reminders_cfg.get("turning", {}) if isinstance(reminders_cfg, dict) else {}
            if await self.engine._process_turning_reminder(p, now, turning_cfg):
                triggered += 1

            early_mobility_cfg = reminders_cfg.get("early_mobility", {}) if isinstance(reminders_cfg, dict) else {}
            if await self.engine._process_early_mobility_reminder(p, now, early_mobility_cfg):
                triggered += 1

        if triggered > 0:
            self.engine._log_info("护理提醒", triggered)
