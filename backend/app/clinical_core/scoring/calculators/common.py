"""评分计算公共工具。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ...enums import DataQuality
from ...observation import Observation
from ..score_result import ScoreComponent
from ..window_spec import WindowSpec


def filter_in_window(
    observations: list[Observation],
    spec: WindowSpec,
    evaluation_time: datetime,
) -> list[Observation]:
    """按时间窗过滤观测值。左开右闭 (evaluation_time - lookback, evaluation_time]。"""
    window_start = evaluation_time - spec.lookback_window
    return [obs for obs in observations if obs.observed_at > window_start and obs.observed_at <= evaluation_time]


def filter_by_code(observations: list[Observation], codes: list[str]) -> list[Observation]:
    """按代码过滤。"""
    return [obs for obs in observations if obs.code in codes]


def get_latest(observations: list[Observation]) -> Observation | None:
    """获取最新一条。"""
    if not observations:
        return None
    return max(observations, key=lambda o: o.observed_at or datetime.min.replace(tzinfo=UTC))


def get_worst(observations: list[Observation], *, reverse: bool = False) -> Observation | None:
    """获取最差值（最大或最小）。"""
    valid = [o for o in observations if o.value_number is not None]
    if not valid:
        return None
    if reverse:
        return min(valid, key=lambda o: o.value_number or 0.0)
    return max(valid, key=lambda o: o.value_number or 0.0)


def get_min(observations: list[Observation]) -> Observation | None:
    valid = [o for o in observations if o.value_number is not None]
    if not valid:
        return None
    return min(valid, key=lambda o: o.value_number or 0.0)


def get_max(observations: list[Observation]) -> Observation | None:
    valid = [o for o in observations if o.value_number is not None]
    if not valid:
        return None
    return max(valid, key=lambda o: o.value_number or 0.0)


def get_sum(observations: list[Observation]) -> float | None:
    valid = [o.value_number for o in observations if o.value_number is not None]
    if not valid:
        return None
    return sum(valid)


def is_stale(obs: Observation, max_staleness: timedelta, evaluation_time: datetime) -> bool:
    """判断观测值是否超过最大陈旧度。"""
    return (evaluation_time - obs.observed_at) > max_staleness


def make_missing_component(name: str, reason: str = "missing") -> ScoreComponent:
    """创建缺失分项。"""
    return ScoreComponent(
        name=name,
        is_missing=True,
        data_quality=DataQuality.MISSING,
    )


def make_component(
    name: str,
    obs: Observation,
    score_points: float,
    *,
    canonical_value: float | None = None,
    canonical_unit: str = "",
    is_stale_flag: bool = False,
) -> ScoreComponent:
    """创建正常分项。"""
    return ScoreComponent(
        name=name,
        raw_value=obs.value_number,
        raw_unit=obs.unit,
        canonical_value=canonical_value or obs.value_number,
        canonical_unit=canonical_unit or obs.unit,
        observed_at=obs.observed_at,
        source_record_id=obs.source_record_id,
        score_points=score_points,
        is_missing=False,
        is_stale=is_stale_flag,
        unit_source="reported",
        data_quality=DataQuality.STALE if is_stale_flag else DataQuality.VALID,
    )
