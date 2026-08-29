"""GCS 取值与有效性判定。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import datetime

from ...enums import DataQuality
from ...observation import Observation
from ..score_result import ScoreComponent, ScoreResult
from ..window_spec import ScoreWindowSpec
from .common import filter_by_code, filter_in_window, get_latest, is_stale, make_component, make_missing_component

VERSION = "gcs-1.0"

_UNASSESABLE_TEXTS = {"无法评估", "无法评价", "不能评估", "不可评估", "未评估", "未完成", "未做", "不适用", "intubated"}


def _is_sedated(value_text: str | None) -> bool:
    if not value_text:
        return False
    text = value_text.strip().lower()
    return any(k in text for k in ("镇静", "sedated", "sedation", "rass<-3", "rass < -3"))


def _is_unassessable(value_text: str | None) -> bool:
    if not value_text:
        return False
    text = value_text.strip().lower()
    return any(k in text for k in _UNASSESABLE_TEXTS)


class GCSCalculator:
    @property
    def score_name(self) -> str:
        return "GCS"

    @property
    def rulepack_version(self) -> str:
        return VERSION

    def calculate(self, observations: list[Observation], *, evaluation_time: datetime,
                  window_spec: ScoreWindowSpec, patient_weight_kg: float | None = None) -> ScoreResult:
        components: list[ScoreComponent] = []
        missing_items: list[str] = []
        data_quality_issues: list[str] = []

        specs_by_name = {s.component_name: s for s in window_spec.components}
        gcs_spec = specs_by_name.get("gcs_total") or specs_by_name.get("gcs")

        if gcs_spec:
            filtered = filter_by_code(observations, ["param_score_gcs_obs", "gcsScore", "GCS", "gcs_total"])
            in_window = filter_in_window(filtered, gcs_spec, evaluation_time)
            latest = get_latest(in_window)

            if latest is None:
                components.append(make_missing_component("gcs_total"))
                missing_items.append("gcs_total")
            elif is_stale(latest, gcs_spec.max_staleness, evaluation_time):
                comp = make_component("gcs_total", latest, 0.0, is_stale_flag=True)
                components.append(comp)
                data_quality_issues.append("GCS 超过有效期")
            elif _is_sedated(latest.value_text):
                comp = make_component("gcs_total", latest, latest.value_number or 0.0)
                comp = comp.model_copy(update={"data_quality": DataQuality.IMPLAUSIBLE})
                components.append(comp)
                data_quality_issues.append("GCS sedated - not comparable")
            elif _is_unassessable(latest.value_text):
                comp = make_component("gcs_total", latest, 0.0)
                comp = comp.model_copy(update={"data_quality": DataQuality.MISSING})
                components.append(comp)
                missing_items.append("gcs_total")
                data_quality_issues.append("GCS not assessable")
            else:
                components.append(make_component("gcs_total", latest, latest.value_number or 0.0))

        total = components[0].raw_value if components and not components[0].is_missing else None
        completeness = 1.0 if components and not components[0].is_missing else 0.0
        result_status = "complete" if completeness == 1.0 else ("partial" if components else "insufficient")

        return ScoreResult(
            score_name=self.score_name, rulepack_version=VERSION,
            window_spec_id=window_spec.spec_id, evaluation_time=evaluation_time,
            total_score=total, result_status=result_status, completeness=completeness,
            components=components, missing_items=missing_items, data_quality_issues=data_quality_issues,
        )
