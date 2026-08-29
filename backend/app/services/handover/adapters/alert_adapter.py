"""Alert data adapter — queries alert_records collection."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .base import AdapterResult, patient_id_or_query

logger = logging.getLogger("icu-alert")


class AlertAdapter:
    """Queries alerts from alert_records."""

    def __init__(self, db) -> None:
        self.db = db

    async def query(
        self,
        patient_id: str,
        start: datetime,
        end: datetime,
    ) -> AdapterResult:
        """Query alerts for the given patient and time range."""
        try:
            pid_query = patient_id_or_query(patient_id, "patient_id")
            rows = await self.db.col("alert_records").find(
                {
                    **pid_query,
                    "created_at": {"$gte": start, "$lte": end},
                    "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
                }
            ).sort("created_at", -1).to_list(length=100)

            if not rows:
                return AdapterResult(
                    status="empty",
                    source="alert_records",
                    patient_match_field="patient_id",
                    time_field="created_at",
                    time_range={"start": start.isoformat(), "end": end.isoformat()},
                    count=0,
                )

            results = []
            for r in rows:
                results.append({
                    "type": str(r.get("alert_type") or r.get("type") or ""),
                    "value": str(r.get("value") or r.get("alert_value") or ""),
                    "time": str(r.get("created_at") or r.get("time") or ""),
                    "closed": bool(r.get("acknowledged_at") or r.get("ack_disposition")),
                    "priority": str(r.get("priority") or r.get("severity") or ""),
                })

            last_time = str(rows[0].get("created_at", "") or rows[0].get("time", ""))

            return AdapterResult(
                status="available",
                source="alert_records",
                patient_match_field="patient_id",
                time_field="created_at",
                time_range={"start": start.isoformat(), "end": end.isoformat()},
                count=len(results),
                last_updated_at=last_time,
                data=results,
            )

        except Exception as exc:
            logger.warning("AlertAdapter: query failed: %s", exc)
            return AdapterResult(
                status="failed",
                source="alert_records",
                error_code="QUERY_FAILED",
                error_message=str(exc),
            )
