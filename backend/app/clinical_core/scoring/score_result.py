"""评分结果模型。

从 critical-care-alert-platform/src/ccalert/domain/scoring/score_result.py 迁移。
导入路径已调整为 ..enums。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from ..enums import DataQuality


class ScoreComponent(BaseModel):
    """单个分项结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    raw_value: float | None = None
    raw_unit: str = ""
    canonical_value: float | None = None
    canonical_unit: str = ""
    observed_at: datetime | None = None
    source_record_id: str = ""
    score_points: float = 0.0
    is_missing: bool = False
    is_stale: bool = False
    unit_source: str = ""  # reported, configured
    conversion_rule_id: str = ""
    data_quality: DataQuality = DataQuality.VALID
    data_quality_flags: list[str] = []

    @field_validator("observed_at")
    @classmethod
    def _tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime 必须为 timezone-aware")
        return v


class ScoreResult(BaseModel):
    """评分结果。版本化，不可变。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # 核心标识
    score_name: str
    score_variant: str = ""  # ScoreVariant 值
    rulepack_id: str = ""
    rulepack_version: str
    rulepack_content_hash: str = ""  # 完整 SHA-256 (64字符)

    # 规则来源
    reference_year: int = 0
    clinical_approval_status: str = "not_approved"
    lifecycle_status: str = "experimental"
    source_provenance: str = ""  # 来源追溯
    algorithm_provenance: str = ""  # 算法追溯

    # 评估
    window_spec_id: str
    evaluation_time: datetime
    total_score: float | None = None
    result_status: str  # complete, partial, insufficient
    completeness: float  # 0.0 ~ 1.0
    components: list[ScoreComponent]
    missing_items: list[str] = []
    data_quality_issues: list[str] = []
    missing_data_policy_id: str = ""
    missing_data_policy_hash: str = ""

    # 元数据
    schema_version: str = "1.0"
    content_hash: str = ""  # deprecated alias for rulepack_content_hash
    is_estimated: bool = False
    confidence: str = "high"

    @field_validator("evaluation_time")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("evaluation_time 必须为 timezone-aware")
        return v

    @field_validator("completeness")
    @classmethod
    def _range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("completeness 必须在 0~1 范围内")
        return v

    @field_validator("result_status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in {"complete", "partial", "insufficient"}:
            raise ValueError("result_status 必须是 complete/partial/insufficient")
        return v

    @field_validator("score_variant")
    @classmethod
    def _non_empty_variant(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("score_variant 不能为空")
        return v
