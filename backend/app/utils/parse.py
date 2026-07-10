from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

API_TZ = ZoneInfo("Asia/Shanghai")


def _safe_oid(value: Any) -> ObjectId | None:
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


def _to_output_iso(value: datetime | None) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(API_TZ).isoformat()


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("≥", "").replace("≤", "").replace(">", "").replace("<", "").strip()
    if s.lower() in ("neg", "negative", "trace", "无", "阴性", "阳性"):
        return None
    match = re.search(r"[-+]?\d+(\.\d+)?", s)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None
