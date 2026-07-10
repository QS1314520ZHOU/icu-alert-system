from __future__ import annotations

from datetime import datetime
from typing import Any

from app.utils.parse import _parse_dt, _parse_number


def _extract_param(doc: dict, key: str) -> float | None:
    if doc.get("code") == key:
        for value in (doc.get("fVal"), doc.get("intVal"), doc.get("strVal"), doc.get("value")):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    value = doc.get(key)
    if value is None:
        params = doc.get("params", {})
        if isinstance(params, dict):
            value = params.get(key)
    if isinstance(value, dict):
        value = value.get("value", value.get("v"))
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _eval_condition(value: float | None, condition: dict) -> bool:
    if value is None:
        return False
    op = condition.get("operator")
    thr = condition.get("threshold")
    lo = condition.get("min")
    hi = condition.get("max")
    try:
        if op == ">":
            return value > float(thr)
        if op == ">=":
            return value >= float(thr)
        if op == "<":
            return value < float(thr)
        if op == "<=":
            return value <= float(thr)
        if op in ("==", "="):
            return value == float(thr)
        if op == "!=":
            return value != float(thr)
        if op == "between":
            return float(lo) <= value <= float(hi)
        if op == "outside":
            return value < float(lo) or value > float(hi)
    except Exception:
        return False
    return False


def _detect_trend(values: list[float], window: int = 5) -> dict:
    if len(values) < 2:
        return {"direction": "stable", "slope": 0.0, "volatility": 0.0}

    recent = values[-window:] if len(values) >= window else values
    n = len(recent)

    x_mean = (n - 1) / 2
    y_mean = sum(recent) / n
    num = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0.0
    volatility = (sum((v - y_mean) ** 2 for v in recent) / n) ** 0.5

    if slope > 0.5:
        direction = "rising"
    elif slope < -0.5:
        direction = "falling"
    else:
        direction = "stable"

    return {"direction": direction, "slope": round(slope, 3), "volatility": round(volatility, 2)}


def _cap_time(doc: dict) -> datetime | None:
    return _parse_dt(doc.get("time")) or _parse_dt(doc.get("recordTime"))


def _cap_value(doc: dict) -> float | None:
    for key in ("fVal", "intVal", "strVal", "value"):
        num = _parse_number(doc.get(key))
        if num is not None:
            return num
    return None
