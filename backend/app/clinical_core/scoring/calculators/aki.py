"""AKI 分期计算器。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...observation import Observation
from ..score_result import ScoreComponent, ScoreResult
from ..window_spec import ScoreWindowSpec, WindowSpec
from .common import (
    filter_by_code, filter_in_window, get_latest, is_stale, make_component, make_missing_component,
)

VERSION = "aki-1.0"


def _aki_stage_from_creatinine(current: float, baseline: float) -> int:
    if baseline <= 0:
        return 0
    ratio = current / baseline
    if ratio >= 3.0 or current >= 353.6:
        return 3
    elif ratio >= 2.0:
        return 2
    elif ratio >= 1.5:
        return 1
    return 0


def _aki_stage_from_urine(urine_ml: float, hours: float, weight_kg: float | None) -> int:
    if hours <= 0 or weight_kg is None or weight_kg <= 0:
        return 0
    rate_ml_kg_h = urine_ml / weight_kg / hours
    if rate_ml_kg_h < 0.3:
        return 2
    elif hours >= 6 and rate_ml_kg_h < 0.5:
        return 1
    return 0


class AKICalculator:
    @property
    def score_name(self) -> str:
        return "AKI"

    @property
    def rulepack_version(self) -> str:
        return VERSION

    def calculate(self, observations: list[Observation], *, evaluation_time: datetime,
                  window_spec: ScoreWindowSpec, patient_weight_kg: float | None = None,
                  baseline_creatinine: float | None = None) -> ScoreResult:
        components: list[ScoreComponent] = []
        missing_items: list[str] = []
        data_quality_issues: list[str] = []
        specs = {s.component_name: s for s in window_spec.components}

        crea_spec = specs.get("creatinine")
        if crea_spec:
            if baseline_creatinine is None:
                components.append(make_missing_component("baseline_creatinine"))
                missing_items.append("baseline_creatinine")
                data_quality_issues.append("无基线肌酐，无法判定 AKI 分期")
            else:
                crea_obs = self._get_latest(observations, ["CREA", "creatinine"], crea_spec, evaluation_time)
                if crea_obs and crea_obs.value_number is not None:
                    stage = _aki_stage_from_creatinine(crea_obs.value_number, baseline_creatinine)
                    components.append(make_component("creatinine", crea_obs, float(stage)))
                else:
                    components.append(make_missing_component("creatinine"))
                    missing_items.append("creatinine")

        urine_spec = specs.get("urine_output")
        if urine_spec:
            urine_obs = self._get_sum_in_window(observations, ["urine_output", "urineVolume"], urine_spec, evaluation_time)
            if urine_obs is not None and urine_obs.value_number is not None:
                hours = urine_spec.lookback_window.total_seconds() / 3600
                stage = _aki_stage_from_urine(urine_obs.value_number, hours, patient_weight_kg)
                components.append(make_component("urine_output", urine_obs, float(stage)))
            else:
                components.append(make_missing_component("urine_output"))
                missing_items.append("urine_output")

        total = (
            max(c.score_points for c in components if not c.is_missing)
            if any(not c.is_missing for c in components) else None
        )
        present = [c for c in components if not c.is_missing]
        completeness = len(present) / len(components) if components else 0.0
        result_status = "insufficient" if completeness < 0.5 else ("partial" if missing_items else "complete")

        return ScoreResult(
            score_name=self.score_name, rulepack_version=VERSION,
            window_spec_id=window_spec.spec_id, evaluation_time=evaluation_time,
            total_score=total, result_status=result_status, completeness=completeness,
            components=components, missing_items=missing_items, data_quality_issues=data_quality_issues,
        )

    def _get_latest(self, observations, codes, spec, evaluation_time):
        filtered = filter_by_code(observations, codes)
        in_window = filter_in_window(filtered, spec, evaluation_time)
        latest = get_latest(in_window)
        if latest and is_stale(latest, spec.max_staleness, evaluation_time):
            return None
        return latest

    def _get_sum_in_window(self, observations, codes, spec, evaluation_time):
        filtered = filter_by_code(observations, codes)
        in_window = filter_in_window(filtered, spec, evaluation_time)
        valid = [o for o in in_window if o.value_number is not None]
        if not valid:
            return None
        values = [o.value_number for o in valid if o.value_number is not None]
        total = sum(values)
        latest = max(valid, key=lambda o: o.observed_at or datetime.min.replace(tzinfo=UTC))
        return latest.model_copy(update={"value_number": total})
