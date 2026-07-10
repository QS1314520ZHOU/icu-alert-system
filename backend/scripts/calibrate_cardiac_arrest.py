from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_config
from app.database import DatabaseManager


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _score(alert: dict[str, Any]) -> float:
    try:
        return float(alert.get("value") or 0)
    except Exception:
        return 0.0


def _event(outcome: dict[str, Any] | None) -> bool:
    outcomes = outcome.get("outcomes") if isinstance(outcome, dict) else {}
    return str((outcomes or {}).get("24h") or "").lower() == "event_occurred"


def _grid(defaults: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    w, h, c = defaults
    candidates = set()
    for dw in (-1, 0, 1):
        for dh in (-1, 0, 1):
            for dc in (-1, 0, 1):
                ww = max(0.5, w + dw)
                hh = max(ww, h + dh)
                cc = max(hh, c + dc)
                candidates.add((ww, hh, cc))
    return sorted(candidates)


async def calibrate(days: int, output: Path | None = None) -> dict[str, Any]:
    cfg = get_config()
    db = DatabaseManager(cfg)
    await db.connect()
    try:
        now = datetime.now()
        since = now - timedelta(days=max(int(days or 30), 1))
        cursor = db.col("alert_records").find(
            {"alert_type": "cardiac_arrest_risk", "created_at": {"$gte": since}},
            {"_id": 1, "patient_id": 1, "created_at": 1, "severity": 1, "value": 1, "extra.factors": 1},
        ).sort("created_at", 1)
        alerts = [doc async for doc in cursor]
        outcome_cursor = db.col("alert_outcomes").find({"alert_id": {"$in": [str(a.get("_id")) for a in alerts]}})
        outcomes = {str(doc.get("alert_id")): doc async for doc in outcome_cursor}
        default_cfg = ((cfg.yaml_cfg.get("alert_engine") or {}).get("cardiac_arrest") or {})
        defaults = (
            float(default_cfg.get("warning_score", 4)),
            float(default_cfg.get("high_score", 6)),
            float(default_cfg.get("critical_score", 8)),
        )
        rows = []
        total_patient_days = max((now - since).total_seconds() / 86400.0, 1.0)
        actual_events = sum(1 for alert in alerts if _event(outcomes.get(str(alert.get("_id")))))
        for warning, high, critical in _grid(defaults):
            fired = [a for a in alerts if _score(a) >= warning]
            positives = sum(1 for alert in fired if _event(outcomes.get(str(alert.get("_id")))))
            false_negatives = max(actual_events - positives, 0)
            rows.append(
                {
                    "warning_score": warning,
                    "high_score": high,
                    "critical_score": critical,
                    "alerts": len(fired),
                    "true_positives": positives,
                    "false_negatives_observed_alert_space": false_negatives,
                    "ppv": round(positives / len(fired), 4) if fired else None,
                    "sensitivity_observed_alert_space": round(positives / actual_events, 4) if actual_events else None,
                    "miss_rate_observed_alert_space": round(false_negatives / actual_events, 4) if actual_events else None,
                    "alerts_per_day": round(len(fired) / total_patient_days, 4),
                }
            )
        report = {
            "module": "cardiac_arrest_risk",
            "generated_at": now.isoformat(),
            "window_days": days,
            "note": "Offline calibration report only; it does not change production thresholds automatically.",
            "limitations": [
                "Sensitivity and miss-rate are calculated within observed alert/outcome records unless a separate non-alert outcome cohort is supplied.",
                "Threshold defaults require ICU physician review before production changes.",
            ],
            "default_thresholds": {"warning_score": defaults[0], "high_score": defaults[1], "critical_score": defaults[2]},
            "rows": rows,
        }
        if output:
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate cardiac arrest risk thresholds from historical alerts and inferred outcomes.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = asyncio.run(calibrate(args.days, args.output))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
