"""护理评估提醒"""
from __future__ import annotations

from datetime import datetime, timedelta


class NurseReminderMixin:
    async def scan_nurse_reminders(self) -> None:
        reminders_cfg = self.config.yaml_cfg.get("nurse_reminders", {})
        if not reminders_cfg:
            return

        patient_cursor = self.db.col("patient").find(
            {"isLeave": {"$ne": True}},
            {"name": 1, "hisBed": 1, "icuAdmissionTime": 1}
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        triggered = 0

        for p in patients:
            pid = p.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            pid_candidates = [pid, pid_str]

            for score_type, cfg in reminders_cfg.items():
                code = cfg.get("code")
                interval_hours = float(cfg.get("interval_hours", 4))
                if not code:
                    continue

                last_time = await self._get_latest_score_time(pid_candidates, code)
                if last_time is None:
                    admission = None
                    try:
                        admission = datetime.fromisoformat(str(p.get("icuAdmissionTime")))
                    except Exception:
                        admission = None
                    if admission is None:
                        overdue = True
                        due_at = now
                    else:
                        due_at = admission + timedelta(hours=interval_hours)
                        overdue = now >= due_at
                else:
                    due_at = last_time + timedelta(hours=interval_hours)
                    overdue = now >= due_at

                active = await self.db.col("nurse_reminders").find_one(
                    {"patient_id": pid_str, "score_type": score_type, "is_active": True},
                    sort=[("created_at", -1)]
                )

                if overdue and not active:
                    reminder_doc = {
                        "patient_id": pid_str,
                        "patient_name": p.get("name"),
                        "bed": p.get("hisBed"),
                        "score_type": score_type,
                        "code": code,
                        "last_score_time": last_time,
                        "due_at": due_at,
                        "created_at": now,
                        "is_active": True,
                        "severity": "warning",
                    }
                    res = await self.db.col("nurse_reminders").insert_one(reminder_doc)
                    reminder_doc["_id"] = res.inserted_id
                    await self._create_assessment_alert(reminder_doc)
                    triggered += 1
                elif not overdue and active:
                    await self.db.col("nurse_reminders").update_one(
                        {"_id": active["_id"]},
                        {"$set": {"is_active": False, "resolved_at": now, "last_score_time": last_time}}
                    )

        if triggered > 0:
            self._log_info("护理提醒", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条提醒")