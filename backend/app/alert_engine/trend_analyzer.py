"""趋势恶化检测"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.utils.clinical import _detect_trend, _extract_param


class TrendMixin:
    def _series_std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return ((sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5)

    def _acute_shift(self, values: list[float], multiplier: float, min_delta: float) -> tuple[bool, float]:
        if len(values) < 4:
            return False, 0.0
        pivot = max(2, len(values) // 2)
        before = values[:pivot]
        after = values[pivot:]
        if not before or not after:
            return False, 0.0
        delta = after[-1] - before[0]
        baseline_sd = self._series_std(before)
        threshold = max(min_delta, baseline_sd * multiplier)
        return abs(delta) >= threshold, round(delta, 3)

    def _subacute_shift(self, values: list[float], slope_threshold: float) -> tuple[bool, dict]:
        trend = _detect_trend(values, window=len(values))
        monotonic_up = sum(1 for i in range(1, len(values)) if values[i] >= values[i - 1]) >= max(3, len(values) - 2)
        monotonic_down = sum(1 for i in range(1, len(values)) if values[i] <= values[i - 1]) >= max(3, len(values) - 2)
        ok = abs(trend.get("slope", 0.0)) >= slope_threshold and (monotonic_up or monotonic_down)
        return ok, {"trend": trend, "monotonic_up": monotonic_up, "monotonic_down": monotonic_down}

    def _cyclic_shift(self, values: list[float], amplitude_threshold: float) -> tuple[bool, dict]:
        if len(values) < 6:
            return False, {}
        diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
        sign_changes = sum(1 for i in range(1, len(diffs)) if diffs[i] * diffs[i - 1] < 0)
        amplitude = max(values) - min(values)
        ok = sign_changes >= 3 and amplitude >= amplitude_threshold
        return ok, {"sign_changes": sign_changes, "amplitude": round(amplitude, 3)}

    async def scan_trends(self) -> None:
        from .trend_scanner import TrendScanner

        await TrendScanner(self).scan()

