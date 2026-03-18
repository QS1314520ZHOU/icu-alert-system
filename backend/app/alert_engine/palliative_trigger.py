"""舒缓医疗触发器。"""
from __future__ import annotations

from datetime import datetime, timedelta
import re


class PalliativeTriggerMixin:
    def _palliative_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "palliative_trigger", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _comorbidity_count(self, patient_doc: dict) -> int:
        text = "；".join(
            str(patient_doc.get(k) or "")
            for k in ("clinicalDiagnosis", "admissionDiagnosis", "pastHistory", "medicalHistory", "diagnosis")
        )
        if not text.strip():
            return 0
        chronic_keywords = [
            "高血压", "糖尿病", "冠心病", "慢阻肺", "copd", "肿瘤", "癌", "慢性肾病", "ckd",
            "肝硬化", "心衰", "脑梗", "卒中", "痴呆", "房颤", "免疫抑制", "移植",
        ]
        hits: set[str] = set()
        for part in re.split(r"[；;，,、/\n]+", text):
            seg = str(part).strip().lower()
            if not seg:
                continue
            for keyword in chronic_keywords:
                if keyword.lower() in seg:
                    hits.add(keyword)
        return len(hits)

    async def _has_vasopressor_dependency(self, pid_str: str, days: int = 7) -> bool:
        since = datetime.now() - timedelta(days=max(days, 1))
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {"executeTime": 1, "startTime": 1, "orderTime": 1, "drugName": 1, "orderName": 1},
        ).sort("executeTime", -1).limit(4000)
        keywords = ["去甲肾上腺素", "norepinephrine", "肾上腺素", "epinephrine", "血管加压素", "vasopressin", "多巴胺", "去氧肾上腺素"]
        covered_days: set[str] = set()
        async for doc in cursor:
            t = doc.get("executeTime") or doc.get("startTime") or doc.get("orderTime")
            if not isinstance(t, datetime) or t < since:
                continue
            text = " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName")).lower()
            if any(k.lower() in text for k in keywords):
                covered_days.add(t.strftime("%Y-%m-%d"))
        return len(covered_days) >= max(days, 1)

    async def _organ_failure_flags(self, patient_doc: dict, pid, pid_str: str) -> dict:
        his_pid = patient_doc.get("hisPid")
        aki = await self._calc_aki_stage(patient_doc, pid, his_pid) if his_pid else None
        ards_alert = await self._get_latest_active_alert(pid_str, ["ards"], hours=24 * 7)
        on_vaso = await self._has_vasopressor(pid)
        vaso_dependent_7d = await self._has_vasopressor_dependency(pid_str, days=7)
        gcs = await self._get_latest_assessment(pid, "gcs")
        return {
            "aki_stage": (aki or {}).get("stage"),
            "ards": bool(ards_alert),
            "vasopressor": bool(on_vaso),
            "vasopressor_dependency_7d": vaso_dependent_7d,
            "gcs": gcs,
        }

    async def _composite_high_burden(self, pid_str: str, days: int = 3) -> bool:
        since = datetime.now() - timedelta(days=max(days, 1))
        cnt = await self.db.col("alert_records").count_documents(
            {
                "patient_id": pid_str,
                "alert_type": {"$in": ["multi_organ_deterioration_trend", "cardiac_arrest_risk"]},
                "created_at": {"$gte": since},
                "severity": {"$in": ["high", "critical"]},
            }
        )
        return cnt > 0

    async def scan_palliative_trigger(self) -> None:
        cfg = self._palliative_cfg()
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1},
        )
        patients = [p async for p in patient_cursor]
        now = datetime.now()
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            icu_start = self._patient_icu_start_time(patient_doc)
            icu_days = ((now - icu_start).days + 1) if isinstance(icu_start, datetime) else 0
            age = self._parse_age_years(patient_doc) if hasattr(self, "_parse_age_years") else None
            comorbidity_count = self._comorbidity_count(patient_doc)
            flags = await self._organ_failure_flags(patient_doc, pid, pid_str)
            burden = await self._composite_high_burden(pid_str, days=int(cfg.get("burden_days", 3)))
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
            latest = await self.db.col("score_records").find_one(
                {"patient_id": pid_str, "score_type": "palliative_trigger"},
                sort=[("calc_time", -1)],
            )
            if latest:
                await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
            else:
                payload["created_at"] = now
                await self.db.col("score_records").insert_one(payload)
