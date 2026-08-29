"""Vital signs data adapter — queries deviceCap and bedside collections."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .base import AdapterResult, patient_id_or_query, parse_datetime

logger = logging.getLogger("icu-alert")

VITAL_CODES = {
    "HR": ["param_HR", "param_PR", "HR", "心率"],
    "SpO2": ["param_spo2", "SpO2", "血氧"],
    "RR": ["param_resp", "RR", "呼吸"],
    "T": ["param_T", "T", "体温"],
    "SBP": ["param_ibp_s", "param_nibp_s", "nibp_s", "无创收缩压"],
    "DBP": ["param_ibp_d", "param_nibp_d", "nibp_d", "无创舒张压"],
    "MAP": ["param_ibp_m", "param_nibp_m", "nibp_m", "平均动脉压"],
    "CVP": ["param_cvp", "CVP", "中心静脉压"],
}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _row_value(row: dict) -> Any:
    for key in ("fVal", "intVal", "strVal", "value"):
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


class VitalAdapter:
    """Queries vital signs from deviceCap (primary) and bedside (fallback)."""

    def __init__(self, db) -> None:
        self.db = db

    async def query(
        self,
        bedside_pids: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, AdapterResult]:
        """Query all vital sign types. Returns dict keyed by vital label."""
        results: dict[str, AdapterResult] = {}

        for label, codes in VITAL_CODES.items():
            try:
                result = await self._query_single(bedside_pids, codes, label, start, end)
                results[label] = result
            except Exception as exc:
                logger.warning("VitalAdapter: %s query failed: %s", label, exc)
                results[label] = AdapterResult(
                    status="failed",
                    source="deviceCap/bedside",
                    error_code="QUERY_FAILED",
                    error_message=str(exc),
                )

        return results

    async def _query_single(
        self,
        bedside_pids: list[str],
        codes: list[str],
        label: str,
        start: datetime,
        end: datetime,
    ) -> AdapterResult:
        """Query a single vital sign type from deviceCap with bedside fallback."""
        # Try deviceCap first
        rows = await self.db.col("deviceCap").find(
            {"deviceID": {"$in": bedside_pids}, "code": {"$in": codes}, "time": {"$gte": start, "$lte": end}}
        ).sort("time", 1).to_list(length=500)

        source = "deviceCap"
        time_field = "time"

        if not rows:
            # Fallback to bedside
            rows = await self.db.col("bedside").find(
                {"pid": {"$in": bedside_pids}, "code": {"$in": codes}, "time": {"$gte": start, "$lte": end}}
            ).sort("time", 1).to_list(length=500)
            source = "bedside"

        if not rows:
            return AdapterResult(
                status="empty",
                source=source,
                patient_match_field="deviceID" if source == "deviceCap" else "pid",
                time_field=time_field,
                time_range={"start": start.isoformat(), "end": end.isoformat()},
                count=0,
            )

        values = [_safe_float(_row_value(r)) for r in rows if _row_value(r) is not None]
        if not values:
            return AdapterResult(
                status="empty",
                source=source,
                patient_match_field="deviceID" if source == "deviceCap" else "pid",
                time_field=time_field,
                time_range={"start": start.isoformat(), "end": end.isoformat()},
                count=len(rows),
                warnings=["rows exist but no parseable values"],
            )

        last_row = rows[-1]
        last_time = str(last_row.get("time", ""))

        return AdapterResult(
            status="available",
            source=source,
            patient_match_field="deviceID" if source == "deviceCap" else "pid",
            time_field=time_field,
            time_range={"start": start.isoformat(), "end": end.isoformat()},
            count=len(values),
            last_updated_at=last_time,
            data=[{
                "label": label,
                "min": min(values),
                "max": max(values),
                "latest": values[-1],
                "latest_time": last_time,
                "unit": str(last_row.get("unit", "")),
                "source": source,
                "count": len(values),
            }],
        )
