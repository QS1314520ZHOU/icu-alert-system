"""
Handover — Alert Bridge.

Extracts critical values and unclosed alerts for forced handover in the
Recommendation (R) section. Results are sorted by priority and formatted
for mandatory acknowledgment by the incoming shift.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("icu-alert")


class HandoverAlertBridge:
    """Pulls critical values and unclosed alerts from alert_records for forced handover."""

    def __init__(self, db) -> None:
        self.db = db

    async def get_critical_and_unclosed(
        self,
        patient_id: str,
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        """Return a deduplicated, priority-sorted list of alerts requiring forced handover.

        Filters:
        - In time window [since, until]
        - Active (is_active=True or not set)
        - Unacknowledged OR unclosed
        - Priority p0/p1/p2 (critical/warning)

        Sorted by priority (p0 > p1 > p2), then by recency.
        """
        results: list[dict[str, Any]] = []
        try:
            query: dict[str, Any] = {
                "patient_id": patient_id,
                "created_at": {"$gte": since, "$lte": until},
                "$and": [
                    {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
                    {
                        "$or": [
                            {"acknowledged_at": None},
                            {"acknowledged_at": {"$exists": False}},
                            {"ack_disposition": None},
                            {"ack_disposition": {"$exists": False}},
                            {"ack_disposition": ""},
                        ]
                    },
                ],
            }
            rows = (
                await self.db.col("alert_records")
                .find(query)
                .sort([("priority", 1), ("created_at", -1)])
                .to_list(length=200)
            )

            # Deduplicate by alert_type + value
            seen: set[str] = set()
            for r in (rows or []):
                alert_type = str(r.get("alert_type") or r.get("type") or "")
                alert_value = str(r.get("value") or r.get("alert_value") or "")
                dedup_key = f"{alert_type}:{alert_value}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                priority = str(r.get("priority") or r.get("severity") or "p3").lower()
                results.append({
                    "alert_id": str(r.get("_id", "")),
                    "type": alert_type,
                    "value": alert_value,
                    "priority": priority,
                    "time": self._fmt_time(r.get("created_at")),
                    "is_closed": bool(r.get("acknowledged_at")),
                    "category": self._categorize(alert_type, alert_value),
                })
        except Exception as exc:
            logger.error("alert_bridge: query failed for patient %s: %s", patient_id, exc)

        # Sort: p0 > p1 > p2 > p3
        prio_order = {"p0": 0, "p1": 1, "p2": 2, "critical": 0, "high": 1, "warning": 2}
        results.sort(key=lambda x: prio_order.get(x.get("priority", "p3"), 3))
        return results

    async def build_forced_confirmations(
        self,
        patient_id: str,
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        """Build the forced confirmation list for the acknowledgment step.

        Includes:
        - Critical alerts (p0/critical)
        - High-priority unclosed alerts (p1/high)
        - Results are formatted as acknowledgment checklist items.
        """
        alerts = await self.get_critical_and_unclosed(patient_id, since, until)
        forced: list[dict[str, Any]] = []
        for a in alerts:
            forced.append({
                "item_id": a.get("alert_id", ""),
                "item_type": "critical_value" if a.get("priority") in ("p0", "critical") else "unclosed_alert",
                "description": f"[{a.get('priority', 'p3').upper()}] {a.get('type', '')}: {a.get('value', '')} — {a.get('time', '')}",
                "confirmed": False,
                "confirmed_by": "",
                "confirmed_at": "",
            })
        return forced

    # ── helpers ────────────────────────────────────────────────────

    @staticmethod
    def _fmt_time(val: Any) -> str:
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d %H:%M")
        return str(val or "")

    @staticmethod
    def _categorize(alert_type: str, value: str) -> str:
        """Classify an alert into a handover-relevant category."""
        t = alert_type.lower()
        v = str(value).lower()
        if any(k in t for k in ["lactate", "乳酸", "ph", "potassium", "钾", "sodium", "钠"]):
            return "lab_critical"
        if any(k in t for k in ["hr", "心率", "brady", "tachy", "asystole"]):
            return "vital_critical"
        if any(k in t for k in ["spo2", "血氧", "hypoxia", "desat"]):
            return "vital_critical"
        if any(k in t for k in ["bp", "血压", "hypotension", "hypertension", "map"]):
            return "vital_critical"
        if any(k in t for k in ["sepsis", "脓毒", "infection", "感染"]):
            return "clinical_risk"
        if any(k in t for k in ["aki", "肾", "creatinine", "肌酐", "urine", "尿"]):
            return "clinical_risk"
        if any(k in t for k in ["vent", "呼吸机", "airway", "气道"]):
            return "device_alert"
        if any(k in t for k in ["line", "管路", "tube", "catheter"]):
            return "device_alert"
        return "other"
