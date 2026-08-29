"""阈值查找工具。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import ThresholdDef


@dataclass(frozen=True)
class ThresholdEntry:
    low: float
    high: float
    low_inclusive: bool
    high_inclusive: bool
    score: int


def build_lookup(thresholds: list[ThresholdDef]) -> ThresholdLookup:
    entries: list[ThresholdEntry] = []
    for t in thresholds:
        entries.append(ThresholdEntry(low=t.low, high=t.high, low_inclusive=True, high_inclusive=True, score=t.score))
    entries.sort(key=lambda e: e.low)
    return ThresholdLookup(entries)


class ThresholdLookup:
    def __init__(self, entries: list[ThresholdEntry]) -> None:
        self._entries = tuple(entries)

    def lookup(self, value: float) -> int | None:
        for e in self._entries:
            low_ok = value >= e.low if e.low_inclusive else value > e.low
            high_ok = value <= e.high if e.high_inclusive else value < e.high
            if low_ok and high_ok:
                return e.score
        return None

    @property
    def entries(self) -> tuple[ThresholdEntry, ...]:
        return self._entries

    def __len__(self) -> int:
        return len(self._entries)
