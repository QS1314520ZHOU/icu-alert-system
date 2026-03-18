from __future__ import annotations

from datetime import datetime, timedelta
import re
from .scanners import BaseScanner, ScannerSpec


class PalliativeTriggerScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="palliative_trigger",
                interval_key="palliative_trigger",
                default_interval=1800,
                initial_delay=58,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._palliative_cfg()
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1},
        )
        patients = [p async for p in patient_cursor]
        now = datetime.now()
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            icu_start = self.engine._patient_icu_start_time(patient_doc)
            icu_days = ((now - icu_start).days + 1) if isinstance(icu_start, datetime) else 0
            age = self.engine._parse_age_years(patient_doc) if hasattr(self, "_parse_age_years") else None
            comorbidity_count = self.engine._comorbidity_count(patient_doc)
            flags = await self.engine._organ_failure_flags(patient_doc, pid, pid_str)
            burden = await self.engine._composite_high_burden(pid_str, days=int(cfg.get("burden_days", 3)))
            score = 0
            if icu_days >= int(cfg.get("icu_days_threshold", 14)):
                score += 2
            if burden:
                score += 2
            if (flags.get("aki_stage") or 0) >= 2:
                score += 2
            if flags.get("ards"):
                score += 2
            if flags.get("vasopressor"):
                score += 1
            if flags.get("vasopressor_dependency_7d"):
                score += 2
            if flags.get("gcs") is not None and float(flags.get("gcs")) <= float(cfg.get("gcs_threshold", 8)):
                score += 1
            if age is not None and age >= float(cfg.get("age_threshold", 80)):
                score += 1
            if comorbidity_count >= int(cfg.get("comorbidity_threshold", 3)):
                score += 1
            if score < int(cfg.get("score_threshold", 5)):
                continue

            payload = {
                "patient_id": pid_str,
                "patient_name": patient_doc.get("name"),
                "bed": patient_doc.get("hisBed"),
                "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
                "score_type": "palliative_trigger",
                "score": score,
                "icu_days": icu_days,
                "flags": flags,
                "comorbidity_count": comorbidity_count,
                "burden": burden,
                "recommendation": "建议考虑家属沟通与舒缓医疗评估。",
                "calc_time": now,
                "updated_at": now,
                "month": now.strftime("%Y-%m"),
                "day": now.strftime("%Y-%m-%d"),
            }
            latest = await self.engine.db.col("score_records").find_one(
                {"patient_id": pid_str, "score_type": "palliative_trigger"},
                sort=[("calc_time", -1)],
            )
            if latest:
                await self.engine.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
            else:
                payload["created_at"] = now
                await self.engine.db.col("score_records").insert_one(payload)
