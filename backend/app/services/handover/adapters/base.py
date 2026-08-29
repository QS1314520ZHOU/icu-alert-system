"""Base adapter class for handover data sources."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("icu-alert")


class AdapterResult:
    """Standardized result from a data adapter query."""

    def __init__(
        self,
        status: str = "empty",  # available | empty | failed | stale
        source: str = "",
        source_database: str = "",
        patient_match_field: str = "",
        time_field: str = "",
        time_range: dict[str, str] | None = None,
        count: int = 0,
        last_updated_at: str = "",
        data: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        error_code: str | None = None,
        error_message: str = "",
    ) -> None:
        self.status = status
        self.source = source
        self.source_database = source_database
        self.patient_match_field = patient_match_field
        self.time_field = time_field
        self.time_range = time_range or {}
        self.count = count
        self.last_updated_at = last_updated_at
        self.data = data or []
        self.warnings = warnings or []
        self.error_code = error_code
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "source_database": self.source_database,
            "patient_match_field": self.patient_match_field,
            "time_field": self.time_field,
            "time_range": self.time_range,
            "count": self.count,
            "last_updated_at": self.last_updated_at,
            "data": self.data,
            "warnings": self.warnings,
            "error_code": self.error_code,
        }


def safe_oid(value: Any):
    """Convert to ObjectId, return None if invalid."""
    try:
        from bson import ObjectId
        return ObjectId(str(value))
    except Exception:
        return None


def patient_id_or_query(patient_id: str, field: str = "patient_id") -> dict[str, Any]:
    """Build a query matching patient_id as both ObjectId and string."""
    oid = safe_oid(patient_id)
    if oid:
        return {"$or": [{field: oid}, {field: patient_id}]}
    return {field: patient_id}


def parse_datetime(value: Any) -> datetime | None:
    """Parse various datetime formats."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None
