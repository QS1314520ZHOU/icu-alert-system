"""Outcome inference worker v2 — observation-only (no causal conclusions).

This worker records observed post-alert signals and SOFA changes,
but does NOT auto-write accepted/overridden/averted dispositions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.services.alert_outcome_service import AlertOutcomeService

logger = logging.getLogger("icu-alert")


class OutcomeInferenceWorker:
    """Batch worker that records observations (NOT causal inferences)."""

    def __init__(self, db, *, service: AlertOutcomeService | None = None) -> None:
        self.db = db
        self.service = service or AlertOutcomeService(db)

    def _alert_selector(self, alert_id: Any) -> dict[str, Any]:
        text = str(alert_id or "").strip()
        if not text:
            return {"_id": None}
        try:
            return {"_id": ObjectId(text)}
        except Exception:
            return {"_id": text}

    async def _load_alert(self, alert_id: Any) -> dict[str, Any] | None:
        return await self.db.col("alert_records").find_one(self._alert_selector(alert_id))

    async def seed_missing_outcomes(
        self, *, since_hours: int = 72, limit: int = 500,
    ) -> int:
        since = datetime.now() - timedelta(hours=max(int(since_hours or 72), 1))
        cursor = self.db.col("alert_records").find(
            {"created_at": {"$gte": since}},
            {
                "_id": 1, "patient_id": 1, "alert_type": 1, "rule_id": 1,
                "severity": 1, "created_at": 1, "viewed_at": 1,
                "acknowledged_at": 1, "ack_disposition": 1, "override_reason": 1,
            },
        ).sort("created_at", -1).limit(max(int(limit or 500), 1))
        created = 0
        async for alert_doc in cursor:
            alert_id = str(alert_doc.get("_id") or "")
            existing = await self.db.col("alert_outcomes").find_one(
                {"alert_id": alert_id}, {"_id": 1},
            )
            if existing:
                continue
            await self.service.ensure_for_alert(alert_doc)
            created += 1
        return created

    async def run_once(
        self,
        *,
        limit: int = 200,
        min_age_minutes: int = 30,
        seed_since_hours: int = 72,
    ) -> dict[str, Any]:
        """Run one batch of observation recording.

        Only records observations (suspected signals, SOFA delta).
        Does NOT auto-write accepted/overridden/averted.
        """
        started_at = datetime.now()
        seeded = await self.seed_missing_outcomes(
            since_hours=seed_since_hours, limit=limit * 3,
        )
        cutoff = started_at - timedelta(minutes=max(int(min_age_minutes or 30), 0))
        query = {
            "fired_at": {"$lte": cutoff},
            "$or": [
                {"inference.status": {"$ne": "completed"}},
                {"inference.updated_at": {"$lte": started_at - timedelta(hours=6)}},
                {"manual_review_required": True},
            ],
        }
        cursor = (
            self.db.col("alert_outcomes")
            .find(query)
            .sort("fired_at", 1)
            .limit(max(int(limit or 200), 1))
        )
        processed = 0
        missing_alerts = 0
        failed = 0
        for_update: list[str] = []
        async for outcome_doc in cursor:
            alert_id = str(outcome_doc.get("alert_id") or "")
            alert_doc = await self._load_alert(alert_id)
            if not alert_doc:
                missing_alerts += 1
                await self.db.col("alert_outcomes").update_one(
                    {"_id": outcome_doc.get("_id")},
                    {
                        "$set": {
                            "inference.status": "missing_alert",
                            "inference.updated_at": datetime.now(),
                            "updated_at": datetime.now(),
                        },
                    },
                )
                continue
            try:
                # infer_outcome now only records observations (no auto-disposition)
                await self.service.infer_outcome(alert_doc)
                processed += 1
                for_update.append(alert_id)
            except Exception as exc:
                failed += 1
                logger.exception(
                    "outcome inference failed alert_id=%s error=%s", alert_id, exc,
                )
                await self.db.col("alert_outcomes").update_one(
                    {"_id": outcome_doc.get("_id")},
                    {
                        "$set": {
                            "inference.status": "failed",
                            "inference.error": str(exc),
                            "inference.updated_at": datetime.now(),
                            "updated_at": datetime.now(),
                        },
                    },
                )

        return {
            "started_at": started_at,
            "finished_at": datetime.now(),
            "seeded": seeded,
            "processed": processed,
            "missing_alerts": missing_alerts,
            "failed": failed,
            "alert_ids": for_update[:20],
            "note": "Observation recording only — no auto disposition/causal inference.",
        }
