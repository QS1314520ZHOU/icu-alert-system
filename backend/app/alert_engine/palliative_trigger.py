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
        from .scanner_palliative_trigger import PalliativeTriggerScanner

        await PalliativeTriggerScanner(self).scan()
