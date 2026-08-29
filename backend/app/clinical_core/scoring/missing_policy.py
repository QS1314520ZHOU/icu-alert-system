"""SOFA-2 缺失数据策略定义与执行。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .score_result import ScoreComponent


class MissingDataPolicy(StrEnum):
    """SOFA-2 缺失数据策略枚举。"""

    OFFICIAL_DAY1_NORMAL_IMPUTATION = "official_day1_normal_imputation"
    STRICT_PARTIAL = "strict_partial"
    COMPLETE_CASE = "complete_case"
    SEQUENTIAL_LOCF = "sequential_locf"


class MissingDataPolicyConfig(BaseModel):
    """缺失数据策略配置模型。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: MissingDataPolicy
    day_number: int = 1
    icu_stay_start: str | None = None
    icu_stay_end: str | None = None

    @property
    def policy_id(self) -> str:
        return self.policy.value

    @property
    def policy_hash(self) -> str:
        content = f"{self.policy.value}:{self.day_number}:{self.icu_stay_start}:{self.icu_stay_end}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Policy execution
# ---------------------------------------------------------------------------


def apply_policy(
    policy: MissingDataPolicy,
    components: list[ScoreComponent],
    missing_items: list[str],
    *,
    day_number: int = 1,
    locf_source_times: dict[str, datetime] | None = None,
    locf_components: dict[str, ScoreComponent] | None = None,
) -> tuple[list[ScoreComponent], float | None, str]:
    """Apply missing-data policy to scored components."""
    if policy == MissingDataPolicy.OFFICIAL_DAY1_NORMAL_IMPUTATION:
        if day_number == 1:
            return _apply_day1_imputation(components)
        return _apply_strict_partial(components, missing_items)

    if policy == MissingDataPolicy.STRICT_PARTIAL:
        return _apply_strict_partial(components, missing_items)

    if policy == MissingDataPolicy.COMPLETE_CASE:
        return _apply_complete_case(components, missing_items)

    if policy == MissingDataPolicy.SEQUENTIAL_LOCF:
        return _apply_sequential_locf(components, missing_items, locf_source_times, locf_components)

    msg = f"Unknown missing-data policy: {policy!r}"
    raise ValueError(msg)


def _apply_day1_imputation(
    components: list[ScoreComponent],
) -> tuple[list[ScoreComponent], float | None, str]:
    """Day 1: impute missing organs as score 0 with imputed_normal_zero tag."""
    final: list[ScoreComponent] = []
    for comp in components:
        if comp.is_missing:
            imputed = comp.model_copy(
                update={
                    "score_points": 0.0,
                    "is_missing": False,
                    "data_quality_flags": list(comp.data_quality_flags) + ["imputed_normal_zero"],
                }
            )
            final.append(imputed)
        else:
            final.append(comp)

    present = [c for c in final if not c.is_missing]
    total = sum(c.score_points for c in present) if present else 0.0
    return final, total, "complete"


def _apply_strict_partial(
    components: list[ScoreComponent],
    missing_items: list[str],
) -> tuple[list[ScoreComponent], float | None, str]:
    """Strict partial: return total=None if any organ is missing."""
    if missing_items:
        return components, None, "partial"

    present = [c for c in components if not c.is_missing]
    total = sum(c.score_points for c in present) if present else 0.0
    return components, total, "complete"


def _apply_complete_case(
    components: list[ScoreComponent],
    missing_items: list[str],
) -> tuple[list[ScoreComponent], float | None, str]:
    """Complete case: return total=None with status=insufficient if any organ missing."""
    if missing_items:
        return components, None, "insufficient"

    present = [c for c in components if not c.is_missing]
    total = sum(c.score_points for c in present) if present else 0.0
    return components, total, "complete"


def _apply_sequential_locf(
    components: list[ScoreComponent],
    missing_items: list[str],
    locf_source_times: dict[str, datetime] | None,
    locf_components: dict[str, ScoreComponent] | None,
) -> tuple[list[ScoreComponent], float | None, str]:
    """Sequential LOCF: carry forward last observation within ICU stay."""
    if not missing_items:
        present = [c for c in components if not c.is_missing]
        total = sum(c.score_points for c in present) if present else 0.0
        return components, total, "complete"

    lct = locf_source_times or {}
    locf_values = locf_components or {}
    final: list[ScoreComponent] = []
    for comp in components:
        source = locf_values.get(comp.name)
        if comp.is_missing and comp.name in lct and source is not None and not source.is_missing:
            src_time = lct[comp.name]
            locf_comp = source.model_copy(
                update={
                    "name": comp.name,
                    "is_missing": False,
                    "data_quality_flags": list(source.data_quality_flags)
                    + [f"locf_source_time:{src_time.isoformat()}"],
                }
            )
            final.append(locf_comp)
        else:
            final.append(comp)

    still_missing = [c for c in final if c.is_missing]
    if still_missing:
        return final, None, "partial"

    present = [c for c in final if not c.is_missing]
    total = sum(c.score_points for c in present) if present else 0.0
    return final, total, "complete"
