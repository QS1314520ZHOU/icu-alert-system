"""
ICU智能预警系统 - 预警规则引擎 & 护理提醒
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.ws_manager import WebSocketManager

logger = logging.getLogger("icu-alert")


def _safe_object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _eval_condition(value: Any, condition: dict) -> bool:
    if value is None:
        return False
    try:
        v = float(value)
    except Exception:
        return False

    op = condition.get("operator")
    thr = condition.get("threshold")
    lo = condition.get("min")
    hi = condition.get("max")

    try:
        if op == ">":
            return v > float(thr)
        if op == ">=":
            return v >= float(thr)
        if op == "<":
            return v < float(thr)
        if op == "<=":
            return v <= float(thr)
        if op in ("==", "="):
            return v == float(thr)
        if op == "!=":
            return v != float(thr)
        if op == "between":
            return float(lo) <= v <= float(hi)
        if op == "outside":
            return v < float(lo) or v > float(hi)
    except Exception:
        return False
    return False


class AlertEngine:
    def __init__(self, db, config, ws_manager: WebSocketManager | None = None) -> None:
        self.db = db
        self.config = config
        self.ws = ws_manager
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._stop_event.clear()
        intervals = self.config.yaml_cfg.get("alert_engine", {}).get("scan_intervals", {})
        vital_interval = int(intervals.get("vital_signs", 60))
        reminder_interval = int(intervals.get("assessments", 600))

        self._tasks = [
            asyncio.create_task(self._run_vital_loop(vital_interval)),
            asyncio.create_task(self._run_reminder_loop(reminder_interval)),
        ]
        logger.info("✅ 预警引擎启动完成")

    async def stop(self) -> None:
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("⏹️ 预警引擎已停止")

    async def _run_vital_loop(self, interval: int) -> None:
        while not self._stop_event.is_set():
            try:
                await self.scan_vital_signs()
            except Exception as e:
                logger.exception(f"预警规则扫描失败: {e}")
            await self._sleep(interval)

    async def _run_reminder_loop(self, interval: int) -> None:
        while not self._stop_event.is_set():
            try:
                await self.scan_nurse_reminders()
            except Exception as e:
                logger.exception(f"护理提醒扫描失败: {e}")
            await self._sleep(interval)

    async def _sleep(self, seconds: int) -> None:
        if seconds <= 0:
            seconds = 1
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    async def scan_vital_signs(self) -> None:
        rule_cursor = self.db.col("alert_rules").find({
            "enabled": True,
            "category": "vital_signs"
        })
        rules = [r async for r in rule_cursor]
        if not rules:
            return

        bind_cursor = self.db.col("deviceBind").find(
            {"unBindTime": None},
            {"pid": 1, "deviceID": 1}
        )
        binds = [b async for b in bind_cursor]
        if not binds:
            return

        now = datetime.now()
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_seconds = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        for b in binds:
            device_id = b.get("deviceID")
            pid = b.get("pid")
            if not device_id or not pid:
                continue

            cap = await self.db.col("deviceCap").find_one(
                {"deviceID": device_id},
                sort=[("time", -1)]
            )
            if not cap:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not pid_str:
                continue

            for rule in rules:
                param = rule.get("parameter")
                if not param:
                    continue
                value = cap.get(param)
                if not _eval_condition(value, rule.get("condition", {})):
                    continue

                if await self._is_suppressed(pid_str, rule.get("rule_id"), same_rule_seconds, max_per_hour):
                    continue

                alert_doc = {
                    "rule_id": rule.get("rule_id"),
                    "name": rule.get("name"),
                    "category": rule.get("category"),
                    "parameter": param,
                    "condition": rule.get("condition", {}),
                    "severity": rule.get("severity", "warning"),
                    "alert_type": "vital_signs",
                    "patient_id": pid_str,
                    "patient_name": patient_doc.get("name") if patient_doc else None,
                    "bed": patient_doc.get("hisBed") if patient_doc else None,
                    "device_id": device_id,
                    "value": value,
                    "source_time": cap.get("time"),
                    "created_at": now,
                    "is_active": True,
                }
                res = await self.db.col("alert_records").insert_one(alert_doc)
                alert_doc["_id"] = res.inserted_id
                await self._broadcast_alert(alert_doc)

    async def scan_nurse_reminders(self) -> None:
        reminders_cfg = self.config.yaml_cfg.get("nurse_reminders", {})
        if not reminders_cfg:
            return

        patient_cursor = self.db.col("patient").find(
            {"status": "admitted"},
            {"name": 1, "hisBed": 1, "icuAdmissionTime": 1}
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()

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
                    admission = _parse_dt(p.get("icuAdmissionTime"))
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
                elif not overdue and active:
                    await self.db.col("nurse_reminders").update_one(
                        {"_id": active["_id"]},
                        {"$set": {"is_active": False, "resolved_at": now, "last_score_time": last_time}}
                    )

    async def _get_latest_score_time(self, pid_candidates: list, code: str) -> datetime | None:
        query = {"pid": {"$in": pid_candidates}, code: {"$exists": True}}
        doc = await self.db.col("bedside").find_one(query, sort=[("recordTime", -1)])
        if not doc:
            return None
        return _parse_dt(doc.get("recordTime"))

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        if not rule_id:
            return False
        now = datetime.now()
        if same_rule_seconds > 0:
            since = now - timedelta(seconds=same_rule_seconds)
            cnt = await self.db.col("alert_records").count_documents({
                "patient_id": patient_id,
                "rule_id": rule_id,
                "created_at": {"$gte": since}
            })
            if cnt > 0:
                return True
        if max_per_hour > 0:
            since = now - timedelta(hours=1)
            cnt = await self.db.col("alert_records").count_documents({
                "patient_id": patient_id,
                "created_at": {"$gte": since}
            })
            if cnt >= max_per_hour:
                return True
        return False

    async def _load_patient(self, pid: Any) -> tuple[dict | None, str | None]:
        oid = _safe_object_id(pid)
        pid_str = str(oid) if oid else str(pid)
        patient = None
        if oid:
            patient = await self.db.col("patient").find_one({"_id": oid})
        if not patient:
            patient = await self.db.col("patient").find_one({"_id": pid})
        return patient, pid_str

    async def _create_assessment_alert(self, reminder_doc: dict) -> None:
        alert_doc = {
            "rule_id": f"NURSE_{reminder_doc.get('score_type')}",
            "name": f"{reminder_doc.get('score_type', '').upper()}评估超时",
            "category": "assessments",
            "parameter": reminder_doc.get("code"),
            "condition": {"operator": "overdue"},
            "severity": reminder_doc.get("severity", "warning"),
            "alert_type": "nurse_reminder",
            "patient_id": reminder_doc.get("patient_id"),
            "patient_name": reminder_doc.get("patient_name"),
            "bed": reminder_doc.get("bed"),
            "value": None,
            "source_time": reminder_doc.get("last_score_time"),
            "created_at": reminder_doc.get("created_at"),
            "is_active": True,
            "related_id": reminder_doc.get("_id"),
        }
        res = await self.db.col("alert_records").insert_one(alert_doc)
        alert_doc["_id"] = res.inserted_id
        await self._broadcast_alert(alert_doc)

    async def _broadcast_alert(self, alert_doc: dict) -> None:
        if not self.ws:
            return
        try:
            await self.ws.broadcast({"type": "alert", "data": alert_doc})
        except Exception as e:
            logger.warning(f"WebSocket 广播失败: {e}")
