"""CRRT 监测。"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.utils.clinical import _detect_trend


class CrrtMonitorMixin:
    async def _get_crrt_runtime_hours(self, pid) -> float | None:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return None
        doc = await self.db.col("deviceBind").find_one(
            {"pid": pid_str, "unBindTime": None, "type": {"$in": ["crrt", "CRRT"]}},
            sort=[("bindTime", -1)],
        )
        if not doc:
            return None
        bind_time = doc.get("bindTime")
        if not isinstance(bind_time, datetime):
            return None
        return round((datetime.now() - bind_time).total_seconds() / 3600.0, 1)

    async def _get_crrt_param_series(self, pid, codes: list[str], hours: int = 8) -> list[dict]:
        since = datetime.now() - timedelta(hours=hours)
        points = []
        for code in codes:
            series = await self._get_param_series_by_pid(pid, code, since, prefer_device_types=["crrt"], limit=400)
            for row in series:
                points.append({**row, "code": code})
        points.sort(key=lambda x: x["time"])
        return points

    async def scan_crrt_monitor(self) -> None:
        from .crrt_scanner import CrrtScanner

        await CrrtScanner(self).scan()
