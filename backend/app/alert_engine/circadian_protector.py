"""昼夜节律与睡眠保护。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class CircadianProtectorMixin:
    def _circadian_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "circadian_protector", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _is_night_window(self, now: datetime) -> bool:
        cfg = self._circadian_cfg()
        start_hour = int(cfg.get("night_start_hour", 22))
        end_hour = int(cfg.get("night_end_hour", 6))
        return now.hour >= start_hour or now.hour < end_hour

    def _night_window_bounds(self, now: datetime) -> tuple[datetime, datetime]:
        cfg = self._circadian_cfg()
        start_hour = int(cfg.get("night_start_hour", 22))
        end_hour = int(cfg.get("night_end_hour", 6))
        if now.hour < end_hour:
            start = (now - timedelta(days=1)).replace(hour=start_hour, minute=0, second=0, microsecond=0)
            end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        else:
            start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            end = (now + timedelta(days=1)).replace(hour=end_hour, minute=0, second=0, microsecond=0)
        return start, end

    def _morning_summary_window(self, now: datetime) -> bool:
        cfg = self._circadian_cfg()
        end_hour = int(cfg.get("night_end_hour", 6))
        return end_hour <= now.hour < min(end_hour + 1, 24)

    async def _circadian_apply_alert_policy(self, alert_doc: dict, patient_doc: dict | None) -> dict:
        cfg = self._circadian_cfg()
        if not bool(cfg.get("enabled", True)):
            return alert_doc
        now = datetime.now()
        severity = str(alert_doc.get("severity") or "").lower()
        category = str(alert_doc.get("category") or "").lower()
        alert_type = str(alert_doc.get("alert_type") or "").lower()
        if severity != "warning" or not self._is_night_window(now):
            return alert_doc
        if category in {"circadian", "assessments"} or alert_type in {"night_alert_summary", "nurse_reminder"}:
            return alert_doc

        _, delayed_until = self._night_window_bounds(now)
        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
        extra["delivery_mode"] = "night_batch"
        extra["delayed_until"] = delayed_until
        extra["suppressed_at_night"] = True
        alert_doc["extra"] = extra
        return alert_doc

    def _should_broadcast_alert(self, alert_doc: dict) -> bool:
        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
        delayed_until = extra.get("delayed_until")
        if isinstance(delayed_until, datetime):
            return delayed_until <= datetime.now()
        return True

    async def _get_delayed_night_alerts(self, pid_str: str, now: datetime) -> list[dict]:
        if not pid_str:
            return []
        start, _ = self._night_window_bounds(now)
        cursor = self.db.col("alert_records").find(
            {
                "patient_id": pid_str,
                "created_at": {"$gte": start, "$lte": now},
                "severity": "warning",
                "extra.delivery_mode": "night_batch",
                "extra.delayed_until": {"$lte": now},
                "extra.delayed_broadcasted": {"$ne": True},
            },
            {"name": 1, "alert_type": 1, "created_at": 1, "extra.route_targets": 1},
        ).sort("created_at", 1).limit(100)
        return [doc async for doc in cursor]

    async def _night_operation_count(self, pid, now: datetime) -> int:
        start, end = self._night_window_bounds(now)
        pid_str = self._pid_str(pid)
        if not pid_str:
            return 0
        return await self.db.col("bedside").count_documents({"pid": pid_str, "time": {"$gte": start, "$lt": end}})

    async def _night_warning_alerts(self, pid_str: str, now: datetime) -> list[dict]:
        since = now - timedelta(hours=8)
        cursor = self.db.col("alert_records").find(
            {"patient_id": pid_str, "created_at": {"$gte": since}, "severity": "warning"},
            {"name": 1, "alert_type": 1, "created_at": 1},
        ).sort("created_at", -1).limit(50)
        return [doc async for doc in cursor]

    async def scan_circadian_protector(self) -> None:
        from .scanner_circadian_protector import CircadianProtectorScanner

        await CircadianProtectorScanner(self).scan()
    async def _emit_morning_summaries(self, now: datetime) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            delayed_alerts = await self._get_delayed_night_alerts(pid_str, now)
            if not delayed_alerts:
                continue
            rule_id = "CIRCADIAN_MORNING_WARNING_SUMMARY"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            names: list[str] = []
            targets: set[str] = set()
            for row in delayed_alerts:
                name = str(row.get("name") or "").strip()
                if name and name not in names:
                    names.append(name)
                extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
                for target in extra.get("route_targets") or []:
                    targets.add(str(target))

            alert = await self._create_alert(
                rule_id=rule_id,
                name="夜间非紧急报警晨间汇总",
                category="circadian",
                alert_type="night_warning_morning_summary",
                severity="warning",
                parameter="night_warning_batch",
                condition={"operator": ">=", "threshold": 1},
                value=len(delayed_alerts),
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=now,
                extra={
                    "night_warning_count": len(delayed_alerts),
                    "alert_names": names[:12],
                    "route_targets": sorted(targets) or ["nurse"],
                    "source_alert_ids": [row.get("_id") for row in delayed_alerts if row.get("_id") is not None][:50],
                },
            )
            if alert:
                triggered += 1
                source_ids = [row.get("_id") for row in delayed_alerts if row.get("_id") is not None]
                if source_ids:
                    await self.db.col("alert_records").update_many(
                        {"_id": {"$in": source_ids}},
                        {"$set": {"extra.delayed_broadcasted": True, "extra.broadcasted_at": now}},
                    )

        if triggered > 0:
            self._log_info("昼夜节律晨间汇总", triggered)
