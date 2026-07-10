from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.data_adapters.base import ClinicalDataAdapter, StandardizedObservation

RESPIRATORY_FEATURE_SCHEMA_VERSION = "respiratory_forecast_features.v1"


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fio2_fraction(value: Any) -> float | None:
    num = _num(value)
    if num is None or num <= 0:
        return None
    frac = num / 100.0 if num > 1 else num
    return round(frac, 4) if 0 < frac <= 1 else None


def _nearest_prior(rows: list[StandardizedObservation], target: datetime, max_gap_minutes: int) -> StandardizedObservation | None:
    best: tuple[float, StandardizedObservation] | None = None
    for row in rows:
        if not isinstance(row.timestamp, datetime) or row.timestamp > target:
            continue
        gap = (target - row.timestamp).total_seconds() / 60.0
        if gap < 0 or gap > max_gap_minutes:
            continue
        if _num(row.value) is None:
            continue
        if best is None or gap < best[0]:
            best = (gap, row)
    return best[1] if best else None


def _completeness(required: list[str], present: list[str]) -> dict[str, Any]:
    present_unique = list(dict.fromkeys(present))
    missing = [item for item in required if item not in present_unique]
    return {
        "required": required,
        "present": present_unique,
        "missing": missing,
        "completeness_ratio": round(len(present_unique) / len(required), 4) if required else 1.0,
    }


async def build_respiratory_forecast_features(
    adapter: ClinicalDataAdapter,
    patient: dict[str, Any],
    *,
    now: datetime,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or {}
    history_hours = int(cfg.get("history_hours", 12) or 12)
    pairing_gap = int(cfg.get("pairing_gap_minutes", 20) or 20)
    min_points = int(cfg.get("min_points", 4) or 4)
    since = now - timedelta(hours=max(1, history_hours))
    spo2_rows = await adapter.get_vitals_series(patient, "spo2", since, now)
    fio2_rows = await adapter.get_devices(patient, ["fio2"], since, now)
    if not fio2_rows:
        fio2_rows = await adapter.get_vitals_series(patient, "fio2", since, now)

    paired: list[dict[str, Any]] = []
    for spo2 in spo2_rows:
        t = spo2.timestamp
        spo2_value = _num(spo2.value)
        if not isinstance(t, datetime) or spo2_value is None or spo2_value <= 0 or spo2_value > 100:
            continue
        fio2 = _nearest_prior(fio2_rows, t, pairing_gap)
        fio2_fraction = _fio2_fraction(fio2.value if fio2 else None)
        if fio2_fraction is None:
            continue
        paired.append(
            {
                "time": t,
                "spo2": round(spo2_value, 1),
                "fio2": fio2_fraction,
                "sf_ratio": round(spo2_value / fio2_fraction, 1),
                "source": {"spo2": spo2.source, "fio2": fio2.source if fio2 else ""},
                "match_method": {"spo2": spo2.match_method, "fio2": fio2.match_method if fio2 else "none"},
            }
        )

    required = ["spo2", "fio2", "paired_sf_ratio"]
    present: list[str] = []
    if spo2_rows:
        present.append("spo2")
    if fio2_rows:
        present.append("fio2")
    if len(paired) >= min_points:
        present.append("paired_sf_ratio")
    completeness = _completeness(required, present)
    completeness.update(
        {
            "spo2_points": len(spo2_rows),
            "fio2_points": len(fio2_rows),
            "paired_points": len(paired),
            "minimum_paired_points": min_points,
        }
    )
    features: dict[str, Any] = {
        "feature_schema_version": RESPIRATORY_FEATURE_SCHEMA_VERSION,
        "data_source": getattr(adapter, "data_source", "unknown"),
        "validation_status": "internal_only",
        "data_completeness": completeness,
        "series": paired[-24:],
        "feature_vector": {},
    }
    if len(paired) >= min_points:
        latest = paired[-1]
        baseline = paired[0]
        elapsed_h = max(1e-6, (latest["time"] - baseline["time"]).total_seconds() / 3600.0)
        latest_sf = float(latest["sf_ratio"])
        baseline_sf = float(baseline["sf_ratio"])
        features["feature_vector"] = {
            "latest_spo2": latest["spo2"],
            "latest_fio2": latest["fio2"],
            "latest_sf_ratio": latest_sf,
            "baseline_sf_ratio": baseline_sf,
            "sf_drop": round(max(0.0, baseline_sf - latest_sf), 1),
            "sf_slope_per_hour": round((latest_sf - baseline_sf) / elapsed_h, 2),
            "paired_points": len(paired),
            "history_hours": history_hours,
        }
    return features
