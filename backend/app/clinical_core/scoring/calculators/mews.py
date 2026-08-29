"""MEWS 评分计算器。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ...observation import Observation
from ..score_result import ScoreComponent, ScoreResult
from ..window_spec import ScoreWindowSpec, WindowSpec
from .common import filter_by_code, filter_in_window, get_latest, is_stale, make_component, make_missing_component

VERSION = "mews-1.0"

_RR_SCORES = [(0, 8, 2), (9, 14, 0), (15, 20, 1), (21, 29, 2), (30, 999, 3)]
_TEMP_SCORES = [(0, 35.0, 2), (35.1, 38.4, 0), (38.5, 999.0, 2)]
_SBP_SCORES = [(0, 70, 3), (71, 80, 2), (81, 100, 1), (101, 199, 0), (200, 999, 2)]
_HR_SCORES = [(0, 40, 2), (41, 50, 1), (51, 100, 0), (101, 110, 1), (111, 129, 2), (130, 999, 3)]


def _lookup(value: float, table: Sequence[tuple[float, float, int]]) -> int:
    for low, high, score in table:
        if low <= value <= high:
            return score
    return 0


def _consciousness_score(value: str | float | None) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return 0 if value >= 15 else 2
    text = str(value).strip().lower()
    if text in ("alert", "清醒", "oriented"):
        return 0
    return 2


class MEWSCalculator:
    @property
    def score_name(self) -> str:
        return "MEWS"

    @property
    def rulepack_version(self) -> str:
        return VERSION

    def calculate(self, observations: list[Observation], *, evaluation_time: datetime,
                  window_spec: ScoreWindowSpec, patient_weight_kg: float | None = None) -> ScoreResult:
        components: list[ScoreComponent] = []
        missing_items: list[str] = []
        specs = {s.component_name: s for s in window_spec.components}

        for name, codes, table in [
            ("respiratory_rate", ["param_resp", "RR"], _RR_SCORES),
            ("temperature", ["param_T", "T"], _TEMP_SCORES),
            ("systolic_bp", ["param_nibp_s", "param_ibp_s", "SBP"], _SBP_SCORES),
            ("heart_rate", ["param_HR", "HR"], _HR_SCORES),
        ]:
            spec = specs.get(name)
            if not spec:
                continue
            obs = self._get_latest(observations, codes, spec, evaluation_time)
            if obs and obs.value_number is not None:
                score = _lookup(obs.value_number, table)
                components.append(make_component(name, obs, float(score)))
            else:
                components.append(make_missing_component(name))
                missing_items.append(name)

        cons_spec = specs.get("consciousness")
        if cons_spec:
            obs = self._get_latest(observations, ["param_score_gcs_obs", "gcsScore"], cons_spec, evaluation_time)
            if obs:
                score = _consciousness_score(obs.value_number or obs.value_text)
                components.append(make_component("consciousness", obs, float(score)))
            else:
                components.append(make_missing_component("consciousness"))
                missing_items.append("consciousness")

        total = sum(c.score_points for c in components if not c.is_missing)
        present = [c for c in components if not c.is_missing]
        completeness = len(present) / len(components) if components else 0.0
        result_status = "insufficient" if completeness < 0.5 else ("partial" if missing_items else "complete")

        return ScoreResult(
            score_name=self.score_name, rulepack_version=VERSION,
            window_spec_id=window_spec.spec_id, evaluation_time=evaluation_time,
            total_score=total, result_status=result_status, completeness=completeness,
            components=components, missing_items=missing_items,
        )

    def _get_latest(self, observations, codes, spec, evaluation_time):
        filtered = filter_by_code(observations, codes)
        in_window = filter_in_window(filtered, spec, evaluation_time)
        latest = get_latest(in_window)
        if latest and is_stale(latest, spec.max_staleness, evaluation_time):
            return None
        return latest
