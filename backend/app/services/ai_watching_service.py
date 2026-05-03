from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.utils.parse import _parse_dt
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")


class AiWatchingService:
    def __init__(self, db, config) -> None:
        self.db = db
        self.config = config

    def _cfg(self) -> dict[str, Any]:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("watching", {})
        return cfg if isinstance(cfg, dict) else {}

    def _weights(self) -> dict[str, float]:
        weights = self._cfg().get("weights") if isinstance(self._cfg().get("weights"), dict) else {}
        return {
            "scanner_runs": float(weights.get("scanner_runs", 0.05) or 0.05),
            "labs_reviewed": float(weights.get("labs_reviewed", 0.2) or 0.2),
            "drugs_reviewed": float(weights.get("drugs_reviewed", 0.1) or 0.1),
            "imaging_reports_reviewed": float(weights.get("imaging_reports_reviewed", 1.5) or 1.5),
            "alerts_critical": float(weights.get("alerts_critical", 2.0) or 2.0),
        }

    async def get_watching_summary(self, patient_id: str, hours: int = 1) -> dict[str, Any]:
        hours = min(24, max(1, int(hours or 1)))
        cache_key = f"ai_watching:{patient_id}:{hours}"
        ttl = int(self._cfg().get("cache_ttl_seconds", 60) or 60)
        if self.db.redis:
            try:
                cached = await self.db.redis.get(cache_key)
                if cached:
                    logger.info("[ai_watching] cache hit patient_id=%s hours=%s", patient_id, hours)
                    return json.loads(cached)
            except Exception:
                pass

        now = datetime.now()
        since = now - timedelta(hours=hours)
        patient = await self._load_patient(patient_id)
        pid_values: list[Any] = [patient_id]
        if patient and patient.get("_id"):
            pid_values.append(patient.get("_id"))
        his_pid = str((patient or {}).get("hisPid") or "").strip()

        alert_query = {"patient_id": {"$in": pid_values}, "created_at": {"$gte": since}}
        alerts_triggered = await self.db.col("alert_records").count_documents(alert_query)
        alerts_critical = await self.db.col("alert_records").count_documents({**alert_query, "severity": "critical"})
        scanner_runs = await self._count_scanner_runs(patient_id, since, alerts_triggered)
        labs_reviewed = await self._count_labs(his_pid, since)
        drugs_reviewed = await self._count_drugs(pid_values, since)
        imaging_reports_reviewed = await self._count_imaging(his_pid, since)

        stats = {
            "scanner_runs": scanner_runs,
            "labs_reviewed": labs_reviewed,
            "drugs_reviewed": drugs_reviewed,
            "imaging_reports_reviewed": imaging_reports_reviewed,
            "alerts_triggered": alerts_triggered,
            "alerts_critical": alerts_critical,
        }
        findings = await self._findings(patient_id, hours)
        saved = await self.estimate_saved_minutes(stats)
        payload = {
            "patient_id": patient_id,
            "window_hours": hours,
            "stats": stats,
            "findings": findings,
            "saved_minutes_estimate": saved,
            "generated_at": now.isoformat(),
        }
        if self.db.redis:
            try:
                await self.db.redis.set(cache_key, json.dumps(serialize_doc(payload), ensure_ascii=False), ex=ttl)
                logger.info("[ai_watching] cache set patient_id=%s ttl=%ss", patient_id, ttl)
            except Exception:
                pass
        return serialize_doc(payload)

    async def estimate_saved_minutes(self, stats: dict) -> float:
        weights = self._weights()
        cap = float(self._cfg().get("cap_minutes", 60) or 60)
        saved = (
            float(stats.get("scanner_runs") or 0) * weights["scanner_runs"]
            + float(stats.get("labs_reviewed") or 0) * weights["labs_reviewed"]
            + float(stats.get("drugs_reviewed") or 0) * weights["drugs_reviewed"]
            + float(stats.get("imaging_reports_reviewed") or 0) * weights["imaging_reports_reviewed"]
            + float(stats.get("alerts_critical") or 0) * weights["alerts_critical"]
        )
        return round(min(cap, max(0.0, saved)), 1)

    async def _load_patient(self, patient_id: str) -> dict | None:
        try:
            return await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            return await self.db.col("patient").find_one({"_id": patient_id})

    async def _count_scanner_runs(self, patient_id: str, since: datetime, fallback_alerts: int) -> int:
        query = {"patient_id": patient_id, "created_at": {"$gte": since}}
        for col_name in ("scanner_run_logs", "scanner_runs", "alert_outcomes"):
            try:
                count = await self.db.col(col_name).count_documents(query)
                if count:
                    return count
            except Exception:
                continue
        return max(int(fallback_alerts), self._estimate_scanner_runs_from_config(since))

    def _estimate_scanner_runs_from_config(self, since: datetime) -> int:
        window_seconds = max(60, int((datetime.now() - since).total_seconds()))
        schedule = (self.config.yaml_cfg or {}).get("scanner_schedule", {})
        if isinstance(schedule, dict) and schedule:
            scanner_names: set[str] = set()
            for group in schedule.values():
                if not isinstance(group, dict):
                    continue
                interval = int(group.get("interval_seconds") or 0)
                scanners = group.get("scanners") if isinstance(group.get("scanners"), list) else []
                if interval > 0 and scanners:
                    scanner_names.update(str(item) for item in scanners if str(item or "").strip())
            if scanner_names:
                return len(scanner_names)

        intervals = (self.config.yaml_cfg or {}).get("alert_engine", {}).get("scan_intervals", {})
        if isinstance(intervals, dict) and intervals:
            return int(sum(max(1, window_seconds // max(1, int(seconds or window_seconds))) for seconds in intervals.values()))
        return 0

    async def _count_labs(self, his_pid: str, since: datetime) -> int:
        if not his_pid:
            return 0
        query = {"hisPid": his_pid, "$or": [{"authTime": {"$gte": since}}, {"reportTime": {"$gte": since}}, {"time": {"$gte": since}}]}
        try:
            return await self.db.dc_col("VI_ICU_EXAM_ITEM").count_documents(query)
        except Exception:
            cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(1000)
            return sum(1 async for doc in cursor if (_parse_dt(doc.get("authTime")) or datetime.min) >= since)

    async def _count_drugs(self, pid_values: list[Any], since: datetime) -> int:
        query = {
            "pid": {"$in": pid_values},
            "$or": [{"executeTime": {"$gte": since}}, {"startTime": {"$gte": since}}, {"orderTime": {"$gte": since}}],
        }
        return await self.db.col("drugExe").count_documents(query)

    async def _count_imaging(self, his_pid: str, since: datetime) -> int:
        if not his_pid:
            return 0
        query = {"hisPid": his_pid, "$or": [{"reportTime": {"$gte": since}}, {"authTime": {"$gte": since}}, {"time": {"$gte": since}}]}
        try:
            return await self.db.dc_col("VI_ICU_report").count_documents(query)
        except Exception:
            return 0

    async def _findings(self, patient_id: str, hours: int) -> list[dict[str, Any]]:
        max_items = int(self._cfg().get("findings_max", 3) or 3)
        query = {
            "patient_id": patient_id,
            "severity": {"$in": ["critical", "high"]},
            "$and": [{"viewed": {"$ne": True}}, {"viewed_at": {"$in": [None]}}],
            "created_at": {"$gte": datetime.now() - timedelta(hours=hours)},
        }
        cursor = self.db.col("alert_records").find(query).sort("created_at", -1).limit(max_items)
        rows = []
        async for alert in cursor:
            explanation = alert.get("explanation") if isinstance(alert.get("explanation"), dict) else {}
            headline = alert.get("name") or explanation.get("summary") or explanation.get("text") or "发现新的高风险事件"
            rows.append(
                {
                    "key": str(alert.get("alert_type") or alert.get("rule_id") or alert.get("_id")),
                    "headline": str(headline)[:80],
                    "severity": "critical" if alert.get("severity") == "critical" else "warn",
                    "deep_link": f"/patient/{patient_id}?tab={self._tab_for_alert(alert)}",
                    "source_alert_id": str(alert.get("_id")),
                }
            )
        return rows

    @staticmethod
    def _tab_for_alert(alert: dict[str, Any]) -> str:
        category = str(alert.get("category") or "").lower()
        alert_type = str(alert.get("alert_type") or "").lower()
        if "drug" in category or "antibiotic" in category or "vanco" in alert_type:
            return "drugs"
        if "lab" in category:
            return "labs"
        return "alerts"
