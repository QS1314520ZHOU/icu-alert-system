from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.alert_outcome_service import AlertOutcomeService


class ModelCalibrationRuntime:
    """Daily calibration facade for scanner outcome metrics.

    The runtime stores recommendations for human review only. It deliberately
    does not mutate scanner thresholds.
    """

    def __init__(self, db) -> None:
        self.db = db
        self.outcomes = AlertOutcomeService(db)

    async def run_daily(self, *, days: int = 30) -> dict[str, Any]:
        health = await self.outcomes.scanner_health(days=days)
        now = datetime.now()
        rows = health.get("rows") or []
        doc = {
            "job_type": "scanner_model_calibration",
            "days": days,
            "rows": rows,
            "summary": {
                "scanner_count": len(rows),
                "review_suggestion_count": sum(1 for row in rows if row.get("review_suggestion")),
            },
            "created_at": now,
            "updated_at": now,
        }
        await self.db.col("model_calibration_runs").insert_one(doc)
        for row in rows:
            if not row.get("review_suggestion"):
                continue
            await self.db.col("adaptive_threshold_reviews").update_one(
                {"scanner_name": row.get("scanner_name"), "status": "pending_review"},
                {
                    "$set": {
                        "scanner_name": row.get("scanner_name"),
                        "status": "pending_review",
                        "source": "model_calibration_runtime",
                        "reason": row.get("threshold_advice"),
                        "metrics": row,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        return doc
