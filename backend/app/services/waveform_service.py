from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from app.utils.clinical import _cap_time, _cap_value


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _quality_band(score: float) -> str:
    if score >= 0.8:
        return "good"
    if score >= 0.55:
        return "fair"
    return "poor"


class WaveformService:
    def __init__(self, *, db, config, alert_engine) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine

    async def list_channels(self, patient_id: str, *, hours: int = 24) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(hours=max(1, hours))
        cursor = self.db.col("bedside").find(
            {"pid": str(patient_id), "time": {"$gte": since}},
            {"code": 1, "time": 1},
        ).sort("time", -1).limit(6000)
        counter: Counter[str] = Counter()
        latest_time: dict[str, datetime] = {}
        async for row in cursor:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            counter[code] += 1
            point_time = row.get("time")
            if isinstance(point_time, datetime) and (code not in latest_time or point_time > latest_time[code]):
                latest_time[code] = point_time
        rows = []
        for code, count in counter.most_common(50):
            rows.append(
                {
                    "channel": code,
                    "sample_points": int(count),
                    "latest_time": latest_time.get(code),
                }
            )
        return rows

    async def get_series(self, patient_id: str, *, channel: str, hours: int = 6, limit: int = 4000) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(hours=max(1, hours))
        cursor = self.db.col("bedside").find(
            {"pid": str(patient_id), "code": str(channel), "time": {"$gte": since}},
            {"time": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
        ).sort("time", 1).limit(limit)
        rows: list[dict[str, Any]] = []
        async for row in cursor:
            point_time = _cap_time(row)
            point_value = _cap_value(row)
            if point_time is None or point_value is None:
                continue
            rows.append({"time": point_time, "value": point_value})
        return rows

    def assess_quality(self, series: list[dict[str, Any]], *, channel: str) -> dict[str, Any]:
        if not series:
            return {"channel": channel, "score": 0.0, "band": "poor", "issues": ["无可用数据点"]}
        values = [_to_float(row.get("value")) for row in series]
        values = [float(item) for item in values if item is not None]
        if len(values) < 5:
            return {"channel": channel, "score": 0.25, "band": "poor", "issues": ["有效点数不足"]}

        min_value = min(values)
        max_value = max(values)
        span = max_value - min_value
        repeated = 0
        for idx in range(1, len(values)):
            if abs(values[idx] - values[idx - 1]) < 1e-6:
                repeated += 1
        repeated_ratio = repeated / max(len(values) - 1, 1)

        deltas = [abs(values[idx] - values[idx - 1]) for idx in range(1, len(values))]
        spike_ratio = len([item for item in deltas if item > max(span * 0.6, 20)]) / max(len(deltas), 1)
        zero_ratio = len([item for item in values if item == 0]) / max(len(values), 1)
        issues: list[str] = []
        score = 1.0
        if repeated_ratio > 0.6:
            score -= 0.35
            issues.append("长时间平台期/值不变")
        if spike_ratio > 0.2:
            score -= 0.25
            issues.append("跳变过多")
        if zero_ratio > 0.2:
            score -= 0.2
            issues.append("零值占比高")
        if span < 1:
            score -= 0.25
            issues.append("波动幅度过低")
        score = max(0.0, min(score, 1.0))
        return {
            "channel": channel,
            "score": round(score, 3),
            "band": _quality_band(score),
            "issues": issues,
            "point_count": len(values),
            "min": round(min_value, 3),
            "max": round(max_value, 3),
            "span": round(span, 3),
            "repeated_ratio": round(repeated_ratio, 3),
            "spike_ratio": round(spike_ratio, 3),
        }

    def detect_events(self, series: list[dict[str, Any]], *, channel: str) -> list[dict[str, Any]]:
        if len(series) < 6:
            return []
        values = [_to_float(row.get("value")) for row in series]
        points = [(series[idx].get("time"), values[idx]) for idx in range(len(series)) if values[idx] is not None]
        if len(points) < 6:
            return []
        events: list[dict[str, Any]] = []
        channel_lower = str(channel or "").lower()
        window = points[-min(120, len(points)):]
        raw_values = [float(item[1]) for item in window]
        if "spo2" in channel_lower:
            latest = raw_values[-1]
            baseline = max(raw_values[:-1]) if len(raw_values) > 1 else latest
            if latest < 90 or (baseline - latest) >= 4:
                events.append({"type": "desaturation_pattern", "time": window[-1][0], "detail": f"SpO2 {round(latest,1)}，较基线下降 {round(baseline-latest,1)}"})
        elif "hr" in channel_lower:
            latest = raw_values[-1]
            if latest > 130:
                events.append({"type": "tachycardia_pattern", "time": window[-1][0], "detail": f"HR {round(latest,1)}"})
            elif latest < 45:
                events.append({"type": "bradycardia_pattern", "time": window[-1][0], "detail": f"HR {round(latest,1)}"})
        elif "ibp" in channel_lower or "nibp" in channel_lower or "map" in channel_lower:
            latest = raw_values[-1]
            if latest < 60:
                events.append({"type": "hypotension_pattern", "time": window[-1][0], "detail": f"MAP/BP {round(latest,1)}"})
        elif "resp" in channel_lower:
            latest = raw_values[-1]
            if latest > 30:
                events.append({"type": "tachypnea_pattern", "time": window[-1][0], "detail": f"RR {round(latest,1)}"})
        return events[:6]
