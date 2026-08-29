"""评分时间窗规格。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, field_validator


class WindowSpec(BaseModel):
    """单个分项的时间窗规格。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str
    lookback_window: timedelta
    max_staleness: timedelta
    aggregation: str  # latest, worst, min, max, mean, delta, sum
    boundary: str = "left_open_right_closed"  # 统一为左开右闭
    tie_breaker: str = "latest"  # 同一时刻多条记录的取舍
    source_priority: list[str] = []  # 多来源优先级
    required_unit: str = ""
    required: bool = True

    @field_validator("aggregation")
    @classmethod
    def _valid_aggregation(cls, v: str) -> str:
        valid = {"latest", "worst", "min", "max", "mean", "delta", "sum"}
        if v not in valid:
            raise ValueError(f"aggregation 必须是 {valid} 之一")
        return v


class ScoreWindowSpec(BaseModel):
    """评分完整窗口规格。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_id: str
    score_name: str
    rulepack_version: str
    components: list[WindowSpec]
    description: str = ""
    clinical_reference: str = ""

    @field_validator("spec_id", "score_name", "rulepack_version")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("字段不能为空")
        return v
