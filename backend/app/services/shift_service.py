from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app import runtime

API_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class ShiftInfo:
    code: str
    name: str
    start_time: str
    end_time: str
    start: datetime
    end: datetime
    source: str = "initSystemConfig.banCiInfoList"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_hm(value: Any) -> time | None:
    text = _text(value)
    if not text:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except Exception:
            pass
    return None


def _field(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = _text(row.get(name))
        if value:
            return value
    return ""


def _normalize_shift(row: dict[str, Any], idx: int) -> dict[str, str] | None:
    start = _field(row, "startTime", "start_time", "beginTime", "begin", "start")
    end = _field(row, "endTime", "end_time", "finishTime", "finish", "end")
    if not _parse_hm(start) or not _parse_hm(end):
        return None
    code = _field(row, "shiftCode", "code", "banCiCode", "id", "_id") or f"shift_{idx + 1}"
    name = _field(row, "shiftName", "name", "banCiName", "label", "title") or code
    return {"code": code, "name": name, "start_time": start, "end_time": end}


class ShiftService:
    def __init__(self, db) -> None:
        self.db = db

    async def refresh_cache(self) -> dict[str, Any]:
        rows: list[dict[str, str]] = []
        doc = None
        try:
            doc = await self.db.col("initSystemConfig").find_one({"banCiInfoList": {"$exists": True}})
        except Exception:
            doc = None
        raw_rows = (doc or {}).get("banCiInfoList") if isinstance((doc or {}).get("banCiInfoList"), list) else []
        for idx, row in enumerate(raw_rows):
            if isinstance(row, dict):
                normalized = _normalize_shift(row, idx)
                if normalized:
                    rows.append(normalized)
        runtime.shift_config = {
            "items": rows,
            "raw_count": len(raw_rows),
            "loaded_at": datetime.now(API_TZ),
            "source": "initSystemConfig.banCiInfoList",
        }
        runtime.shift_config_loaded_at = runtime.shift_config["loaded_at"]
        return runtime.shift_config

    async def list_shifts(self) -> dict[str, Any]:
        cfg = runtime.shift_config
        if not cfg:
            cfg = await self.refresh_cache()
        return cfg or {"items": [], "source": "initSystemConfig.banCiInfoList", "loaded_at": datetime.now(API_TZ)}

    async def _items(self) -> list[dict[str, str]]:
        cfg = await self.list_shifts()
        return list(cfg.get("items") or [])

    def _window_for(self, row: dict[str, str], day: date) -> tuple[datetime, datetime]:
        start_t = _parse_hm(row.get("start_time")) or time(0, 0)
        end_t = _parse_hm(row.get("end_time")) or time(23, 59, 59)
        start = datetime.combine(day, start_t).replace(tzinfo=API_TZ)
        end = datetime.combine(day, end_t).replace(tzinfo=API_TZ)
        if start_t > end_t:
            end += timedelta(days=1)
        return start, end

    async def get_shift_window(self, shift_code: str, day: date | None = None, now: datetime | None = None) -> ShiftInfo | None:
        code = _text(shift_code)
        current = now or datetime.now(API_TZ)
        if current.tzinfo is None:
            current = current.replace(tzinfo=API_TZ)
        candidate_days = [day] if day else [current.date(), current.date() - timedelta(days=1), current.date() + timedelta(days=1)]
        for row in await self._items():
            if row.get("code") == code or row.get("name") == code:
                fallback: ShiftInfo | None = None
                for target_day in candidate_days:
                    if target_day is None:
                        continue
                    start, end = self._window_for(row, target_day)
                    info = ShiftInfo(code=row["code"], name=row["name"], start_time=row["start_time"], end_time=row["end_time"], start=start, end=end)
                    if fallback is None:
                        fallback = info
                    if start <= current < end:
                        return info
                return fallback
        return None

    async def get_current_shift(self, now: datetime | None = None) -> ShiftInfo | None:
        current = now or datetime.now(API_TZ)
        if current.tzinfo is None:
            current = current.replace(tzinfo=API_TZ)
        items = await self._items()
        for day in (current.date(), current.date() - timedelta(days=1)):
            for row in items:
                start, end = self._window_for(row, day)
                if start <= current < end:
                    return ShiftInfo(code=row["code"], name=row["name"], start_time=row["start_time"], end_time=row["end_time"], start=start, end=end)
        return None

    async def resolve_shift(self, shift_code: str | None = "auto") -> ShiftInfo | None:
        code = _text(shift_code or "auto")
        if not code or code == "auto":
            return await self.get_current_shift()
        return await self.get_shift_window(code)
