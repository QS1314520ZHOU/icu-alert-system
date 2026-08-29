"""qSOFA 评分计算器。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import datetime

from ...observation import Observation
from ..score_result import ScoreComponent, ScoreResult
from ..window_spec import ScoreWindowSpec, WindowSpec
from .common import filter_by_code, filter_in_window, get_latest, is_stale, make_component, make_missing_component

VERSION = "qsofa-1.0"


class qSOFACalculator:
    @property
    def score_name(self) -> str:
        return "qSOFA"

    @property
    def rulepack_version(self) -> str:
        return VERSION

    def calculate(self, observations: list[Observation], *, evaluation_time: datetime,
                  window_spec: ScoreWindowSpec, patient_weight_kg: float | None = None) -> ScoreResult:
        components: list[ScoreComponent] = []
        missing_items: list[str] = []
        specs_by_name = {s.component_name: s for s in window_spec.components}

        rr_spec = specs_by_name.get("respiratory_rate")
        if rr_spec:
            rr_obs = self._get_latest(observations, ["param_resp", "RR"], rr_spec, evaluation_time)
            if rr_obs is not None and rr_obs.value_number is not None:
                score = 1.0 if rr_obs.value_number >= 22 else 0.0
                components.append(make_component("respiratory_rate", rr_obs, score))
            else:
                components.append(make_missing_component("respiratory_rate"))
                missing_items.append("respiratory_rate")

        sbp_spec = specs_by_name.get("systolic_bp")
        if sbp_spec:
            sbp_obs = self._get_latest(observations, ["param_nibp_s", "param_ibp_s", "SBP"], sbp_spec, evaluation_time)
            if sbp_obs is not None and sbp_obs.value_number is not None:
                score = 1.0 if sbp_obs.value_number <= 100 else 0.0
                components.append(make_component("systolic_bp", sbp_obs, score))
            else:
                components.append(make_missing_component("systolic_bp"))
                missing_items.append("systolic_bp")

        gcs_spec = specs_by_name.get("consciousness")
        if gcs_spec:
            gcs_obs = self._get_latest(observations, ["param_score_gcs_obs", "gcsScore"], gcs_spec, evaluation_time)
            if gcs_obs is not None and gcs_obs.value_number is not None:
                score = 1.0 if gcs_obs.value_number < 15 else 0.0
                components.append(make_component("consciousness", gcs_obs, score))
            else:
                components.append(make_missing_component("consciousness"))
                missing_items.append("consciousness")

        total = sum(c.score_points for c in components if not c.is_missing)
        present = [c for c in components if not c.is_missing]
        completeness = len(present) / len(components) if components else 0.0
        if completeness < 0.5: result_status = "insufficient"
        elif missing_items: result_status = "partial"
        else: result_status = "complete"

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
