from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app import runtime

API_TZ = ZoneInfo("Asia/Shanghai")


# ── Business exceptions for shift resolution ─────────────────────────

class ShiftError(Exception):
    """Base exception for all shift-resolution errors."""
    pass


class ShiftQueryFailedError(ShiftError):
    """Database query for shift configuration failed (connection, timeout, auth, etc.)."""
    pass


class ShiftNotConfiguredError(ShiftError):
    """No valid shift configuration found in initSystemConfig.banCiInfoList."""
    pass


class ShiftNotMatchedError(ShiftError):
    """Valid shifts exist in database but current time does not fall within any of them."""
    pass


class ShiftNotFoundError(ShiftError):
    """The requested shift_code is not present in the database shift configuration."""
    pass


class ShiftNotStartedError(ShiftError):
    """The requested shift exists but has not yet started (now < scheduled_start)."""
    pass


# ── Data class ───────────────────────────────────────────────────────

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


# ── Parsing helpers ──────────────────────────────────────────────────

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


def _hour_field(row: dict[str, Any], *names: str) -> str:
    for name in names:
        raw = row.get(name)
        if raw in (None, ""):
            continue
        try:
            hour = int(float(str(raw).strip()))
        except Exception:
            continue
        if 0 <= hour <= 24:
            return f"{hour % 24:02d}:00"
    return ""


def _normalize_shift(row: dict[str, Any], idx: int) -> dict[str, str] | None:
    """Normalize a raw shift config row into {code, name, start_time, end_time}.

    Returns None if the row lacks a parseable start or end time.
    """
    start = _field(row, "startTime", "start_time", "beginTime", "begin", "start") or _hour_field(row, "banCiStartHour", "startHour", "obsStartHour")
    end = _field(row, "endTime", "end_time", "finishTime", "finish", "end") or _hour_field(row, "banCiEndHour", "endHour", "obsEndHour")
    if not _parse_hm(start) or not _parse_hm(end):
        return None
    code = _field(row, "shiftCode", "code", "banCiCode", "id", "_id") or f"shift_{idx + 1}"
    name = _field(row, "shiftName", "name", "banCiName", "label", "title") or code
    return {"code": code, "name": name, "start_time": start, "end_time": end}


# ── Service ──────────────────────────────────────────────────────────

class ShiftService:
    """Resolves shift windows from initSystemConfig.banCiInfoList.

    Caches the parsed configuration in runtime.shift_config with a
    configurable TTL (default 60 s).  All shift names, codes, and times
    are driven exclusively by the database — nothing is hard-coded.
    """

    def __init__(self, db, config=None) -> None:
        self.db = db
        self.config = config

    # ── Cache helpers ────────────────────────────────────────────────

    def _ttl_seconds(self) -> int:
        """Read shift cache TTL from config; defaults to 60, clamped to [1, 3600].

        Returns 60 when the config key is missing, ``None``, zero, negative,
        or a non-numeric string.  Only ``ValueError`` and ``TypeError`` from
        ``int()`` conversion are caught — structural errors (e.g. a
        mis-configured config object) propagate naturally.
        """
        try:
            if self.config is None:
                return 60
            # Support both AppConfig (has yaml_cfg) and plain dicts (tests)
            if hasattr(self.config, 'yaml_cfg'):
                d = self.config.yaml_cfg
            elif isinstance(self.config, dict):
                d = self.config
            else:
                return 60
            raw = d.get("handover", {}).get("shift_cache_ttl_seconds")
            if raw is None or isinstance(raw, bool):
                return 60
            ttl = int(raw)
        except (ValueError, TypeError):
            return 60
        if ttl < 1 or ttl > 3600:
            return 60
        return ttl

    def _cache_is_fresh(self) -> bool:
        """Return True if the in-memory cache exists and TTL has not expired."""
        cfg = runtime.shift_config
        loaded_at = runtime.shift_config_loaded_at
        if not cfg or not loaded_at:
            return False
        ttl = self._ttl_seconds()
        elapsed = (datetime.now(API_TZ) - loaded_at).total_seconds()
        return elapsed <= ttl

    # ── Refresh ──────────────────────────────────────────────────────

    async def refresh_cache(self) -> dict[str, Any]:
        """Query initSystemConfig.banCiInfoList from the database.

        Raises:
            ShiftQueryFailedError: if the database query itself fails.
                The original driver exception is preserved as ``__cause__``
                so logs retain the full stack trace.
        """
        rows: list[dict[str, str]] = []
        try:
            doc = await self.db.col("initSystemConfig").find_one(
                {"banCiInfoList": {"$exists": True}}
            )
        except ShiftError:
            raise
        except Exception as exc:
            raise ShiftQueryFailedError("查询数据库班次配置失败") from exc
        raw_rows = (
            (doc or {}).get("banCiInfoList")
            if isinstance((doc or {}).get("banCiInfoList"), list)
            else []
        )
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

    # ── List / cache access ──────────────────────────────────────────

    async def list_shifts(self, force_refresh: bool = False) -> dict[str, Any]:
        """Return the parsed shift configuration.

        Re-queries the database when:
        - force_refresh is True
        - the in-memory cache is empty
        - the cache TTL has expired
        """
        if force_refresh or not self._cache_is_fresh():
            return await self.refresh_cache()
        cfg = runtime.shift_config
        return cfg or {
            "items": [],
            "source": "initSystemConfig.banCiInfoList",
            "loaded_at": datetime.now(API_TZ),
        }

    async def _items(self) -> list[dict[str, str]]:
        cfg = await self.list_shifts()
        return list(cfg.get("items") or [])

    # ── Time window math ─────────────────────────────────────────────

    def _window_for(self, row: dict[str, str], day: date) -> tuple[datetime, datetime]:
        """Compute the absolute [start, end] window for *row* on *day*.

        Cross-midnight shifts (e.g. 20:00–08:00) are handled by adding
        one day to *end* when start_time >= end_time.
        """
        start_t = _parse_hm(row.get("start_time")) or time(0, 0)
        end_t = _parse_hm(row.get("end_time")) or time(23, 59, 59)
        start = datetime.combine(day, start_t).replace(tzinfo=API_TZ)
        end = datetime.combine(day, end_t).replace(tzinfo=API_TZ)
        if start_t >= end_t:
            end += timedelta(days=1)
        return start, end

    # ── Resolution ───────────────────────────────────────────────────

    async def resolve_shift(
        self, shift_code: str | None = "auto", now: datetime | None = None
    ) -> ShiftInfo:
        """Resolve a shift window.

        Args:
            shift_code: ``"auto"`` for auto-detection, or a specific code / name.
            now:       reference datetime (default: now in Asia/Shanghai).

        Returns:
            ShiftInfo with absolute start/end datetimes.

        Raises:
            ShiftQueryFailedError:   database query failed.
            ShiftNotConfiguredError: no valid shift rows in database.
            ShiftNotMatchedError:    auto-detection found no matching window.
            ShiftNotFoundError:      the requested *shift_code* is not configured.
            ShiftNotStartedError:    the requested shift has not started yet.
        """
        code = _text(shift_code or "auto")
        current = now or datetime.now(API_TZ)
        if current.tzinfo is None:
            current = current.replace(tzinfo=API_TZ)

        items = await self._items()

        if not items:
            raise ShiftNotConfiguredError("数据库未配置班次信息")

        if not code or code == "auto":
            # ── Auto-detect: find the first shift whose window contains *current* ──
            for day in (current.date(), current.date() - timedelta(days=1)):
                for row in items:
                    start, end = self._window_for(row, day)
                    if start <= current < end:
                        return ShiftInfo(
                            code=row["code"],
                            name=row["name"],
                            start_time=row["start_time"],
                            end_time=row["end_time"],
                            start=start,
                            end=end,
                        )
            raise ShiftNotMatchedError("当前时间不在任何班次范围内")

        # ── Specific shift code / name ───────────────────────────────
        for row in items:
            if row.get("code") == code or row.get("name") == code:
                candidate_days = [
                    current.date(),
                    current.date() - timedelta(days=1),
                    current.date() + timedelta(days=1),
                ]
                fallback: ShiftInfo | None = None
                for target_day in candidate_days:
                    start, end = self._window_for(row, target_day)
                    info = ShiftInfo(
                        code=row["code"],
                        name=row["name"],
                        start_time=row["start_time"],
                        end_time=row["end_time"],
                        start=start,
                        end=end,
                    )
                    if fallback is None:
                        fallback = info
                    if start <= current < end:
                        return info
                # Shift definition found, but current time is outside all
                # candidate windows — return the nearest window.
                # The caller (router) checks SHIFT_NOT_STARTED separately.
                return fallback  # type: ignore[return-value]

        raise ShiftNotFoundError(f'未找到班次"{code}"')

    # ── Convenience methods (kept for backward compatibility) ────────

    async def get_shift_window(
        self, shift_code: str, day: date | None = None, now: datetime | None = None
    ) -> ShiftInfo | None:
        """Look up a specific shift_code.  Returns None when not found."""
        code = _text(shift_code)
        current = now or datetime.now(API_TZ)
        if current.tzinfo is None:
            current = current.replace(tzinfo=API_TZ)
        candidate_days = (
            [day]
            if day
            else [
                current.date(),
                current.date() - timedelta(days=1),
                current.date() + timedelta(days=1),
            ]
        )
        for row in await self._items():
            if row.get("code") == code or row.get("name") == code:
                fallback: ShiftInfo | None = None
                for target_day in candidate_days:
                    if target_day is None:
                        continue
                    start, end = self._window_for(row, target_day)
                    info = ShiftInfo(
                        code=row["code"],
                        name=row["name"],
                        start_time=row["start_time"],
                        end_time=row["end_time"],
                        start=start,
                        end=end,
                    )
                    if fallback is None:
                        fallback = info
                    if start <= current < end:
                        return info
                return fallback
        return None

    async def get_current_shift(self, now: datetime | None = None) -> ShiftInfo | None:
        """Auto-detect the current shift.  Returns None when nothing matches."""
        current = now or datetime.now(API_TZ)
        if current.tzinfo is None:
            current = current.replace(tzinfo=API_TZ)
        items = await self._items()
        for day in (current.date(), current.date() - timedelta(days=1)):
            for row in items:
                start, end = self._window_for(row, day)
                if start <= current < end:
                    return ShiftInfo(
                        code=row["code"],
                        name=row["name"],
                        start_time=row["start_time"],
                        end_time=row["end_time"],
                        start=start,
                        end=end,
                    )
        return None
