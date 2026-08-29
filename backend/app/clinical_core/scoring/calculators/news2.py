"""NEWS2 评分计算器。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ...observation import Observation
from ..rulepacks.loaded_rulepack import LoadedRulepack
from ..score_result import ScoreComponent, ScoreResult
from ..window_spec import ScoreWindowSpec, WindowSpec
from .common import (
    filter_by_code, filter_in_window, get_latest, is_stale, make_component, make_missing_component,
)

_RR_DEFAULTS: list[tuple[float, float, int]] = [(0, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, 999, 3)]
_SPO2_SCALE1_DEFAULTS: list[tuple[float, float, int]] = [(0, 91, 3), (92, 93, 2), (94, 95, 1), (96, 100, 0)]
_SPO2_SCALE2_DEFAULTS: list[tuple[float, float, int]] = [(0, 83, 3), (84, 85, 2), (86, 87, 1), (88, 92, 0), (93, 94, 1), (95, 96, 2), (97, 100, 3)]
_TEMP_DEFAULTS: list[tuple[float, float, int]] = [(0, 35.0, 3), (35.1, 36.0, 1), (36.1, 38.0, 0), (38.1, 39.0, 1), (39.1, 999, 2)]
_SBP_DEFAULTS: list[tuple[float, float, int]] = [(0, 90, 3), (91, 100, 2), (101, 110, 1), (111, 219, 0), (220, 999, 3)]
_HR_DEFAULTS: list[tuple[float, float, int]] = [(0, 40, 3), (41, 50, 1), (51, 90, 0), (91, 110, 1), (111, 130, 2), (131, 999, 3)]
_CONSCIOUSNESS_DEFAULTS: list[tuple[float, float, int]] = [(0, 0, 0), (1, 1, 1)]
_O2_DEFAULTS: list[tuple[float, float, int]] = [(0, 0, 0), (0.01, 999, 2)]

_DEFAULT_TABLES: dict[str, list[tuple[float, float, int]]] = {
    "respiratory_rate": _RR_DEFAULTS, "spo2_scale1": _SPO2_SCALE1_DEFAULTS,
    "spo2_scale2": _SPO2_SCALE2_DEFAULTS, "spo2": _SPO2_SCALE1_DEFAULTS,
    "supplemental_oxygen": _O2_DEFAULTS, "temperature": _TEMP_DEFAULTS,
    "systolic_bp": _SBP_DEFAULTS, "heart_rate": _HR_DEFAULTS, "consciousness": _CONSCIOUSNESS_DEFAULTS,
}


def _lookup_score(value: float, table: Sequence[tuple[float, float, int]]) -> int:
    for low, high, score in table:
        if low <= value <= high:
            return score
    return 0


class NEWS2Calculator:
    def __init__(self, rulepack: LoadedRulepack | None = None) -> None:
        self._rulepack = rulepack

    @property
    def score_name(self) -> str:
        return self._rulepack.score_name if self._rulepack else "NEWS2"

    @property
    def rulepack_version(self) -> str:
        return self._rulepack.rulepack_version if self._rulepack else "news2-1.0"

    def _get_codes(self, component: str) -> list[str]:
        if self._rulepack:
            codes = self._rulepack.get_component_codes(component)
            if codes:
                return codes
        defaults = {
            "respiratory_rate": ["param_resp", "RR"], "spo2_scale1": ["param_spo2", "SpO2"],
            "spo2_scale2": ["param_spo2", "SpO2"], "supplemental_oxygen": ["supplemental_oxygen", "oxygen_flow", "param_O2_flow"],
            "temperature": ["param_T", "T"], "systolic_bp": ["param_nibp_s", "param_ibp_s", "SBP"],
            "heart_rate": ["param_HR", "HR"], "consciousness": ["param_consciousness", "param_score_gcs_obs"],
        }
        return defaults.get(component, [])

    def _lookup(self, component: str, value: float) -> int | None:
        if self._rulepack:
            tl = self._rulepack.get_threshold_lookup(component)
            if tl:
                result = tl.lookup(value)
                if result is not None:
                    return result
        table = _DEFAULT_TABLES.get(component)
        if table:
            return _lookup_score(value, table)
        return None

    def calculate(self, observations: list[Observation], *, evaluation_time: datetime,
                  window_spec: ScoreWindowSpec, patient_weight_kg: float | None = None,
                  spo2_scale: int = 1) -> ScoreResult:
        components: list[ScoreComponent] = []
        missing_items: list[str] = []
        data_quality_issues: list[str] = []
        specs_by_name = {s.component_name: s for s in window_spec.components}

        for comp_name, table_key in [
            ("respiratory_rate", "respiratory_rate"), ("spo2", f"spo2_scale{spo2_scale}"),
            ("supplemental_oxygen", "supplemental_oxygen"), ("temperature", "temperature"),
            ("systolic_bp", "systolic_bp"), ("heart_rate", "heart_rate"), ("consciousness", "consciousness"),
        ]:
            spec = specs_by_name.get(comp_name)
            if not spec:
                continue
            obs = self._get_latest_in_window(observations, self._get_codes(table_key), spec, evaluation_time)
            if obs is not None and obs.value_number is not None:
                if comp_name == "consciousness":
                    score = self._lookup(table_key, 1.0 if obs.value_number < 15 else 0.0)
                else:
                    score = self._lookup(table_key, obs.value_number)
                if score is not None:
                    components.append(make_component(comp_name, obs, float(score)))
                else:
                    components.append(make_missing_component(comp_name))
                    missing_items.append(comp_name)
            else:
                components.append(make_missing_component(comp_name))
                missing_items.append(comp_name)

        total = sum(c.score_points for c in components if not c.is_missing)
        present = [c for c in components if not c.is_missing]
        completeness = len(present) / len(components) if components else 0.0
        if completeness < 0.5: result_status = "insufficient"
        elif missing_items: result_status = "partial"
        else: result_status = "complete"

        return ScoreResult(
            score_name=self.score_name,
            score_variant=self._rulepack.config.score_variant if self._rulepack else "news2_2017",
            rulepack_id=self._rulepack.config.rulepack_id if self._rulepack else "news2-1.0",
            rulepack_version=self.rulepack_version,
            rulepack_content_hash=self._rulepack.content_hash if self._rulepack else "",
            reference_year=self._rulepack.config.reference_year if self._rulepack else 2017,
            clinical_approval_status=self._rulepack.config.clinical_approval_status if self._rulepack else "not_approved",
            lifecycle_status=self._rulepack.config.lifecycle_status if self._rulepack else "experimental",
            window_spec_id=window_spec.spec_id, evaluation_time=evaluation_time,
            total_score=total, result_status=result_status, completeness=completeness,
            components=components, missing_items=missing_items, data_quality_issues=data_quality_issues,
            content_hash=self._rulepack.content_hash if self._rulepack else "",
        )

    def _get_latest_in_window(self, observations, codes, spec, evaluation_time):
        filtered = filter_by_code(observations, codes)
        in_window = filter_in_window(filtered, spec, evaluation_time)
        latest = get_latest(in_window)
        if latest and is_stale(latest, spec.max_staleness, evaluation_time):
            return None
        return latest
