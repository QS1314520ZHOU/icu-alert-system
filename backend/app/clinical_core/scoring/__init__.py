"""临床评分引擎。"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
import hashlib
import json


# ──────────────────────────────────────────────────────────────────────
# Rulepack models (migrated from critical-care-alert-platform)
# ──────────────────────────────────────────────────────────────────────


class ThresholdDef(BaseModel):
    """单个阈值区间。"""
    model_config = {"frozen": True, "extra": "forbid"}

    low: float
    high: float
    score: int


class ComponentDef(BaseModel):
    """组件定义。"""
    model_config = {"frozen": True, "extra": "allow"}

    name: str
    display_name: str
    codes: list[str]
    unit_concept: str
    required_unit: str
    lookback_hours: float
    max_staleness_hours: float
    aggregation: str
    missing_policy: str
    thresholds: list[ThresholdDef] = Field(default_factory=list)
    description: str = ""


class RulepackConfig(BaseModel):
    """规则包配置。"""
    model_config = {"frozen": True, "extra": "allow"}

    score_name: str
    rulepack_version: str
    schema_version: str = "1.0"
    authority: str = ""
    authority_reference: str = ""
    clinical_approval_status: str = "not_approved"
    lifecycle_status: str = "experimental"
    applicable_care_settings: list[str] = Field(default_factory=list)
    applicable_population: str = ""
    exclusion_conditions: list[str] = Field(default_factory=list)
    canonical_units: dict[str, str] = Field(default_factory=dict)
    components: list[ComponentDef] = Field(default_factory=list)
    window_spec_id: str = ""
    missing_data_policy: str = ""
    content_hash: str = ""
    # Extra fields allowed for source-specific metadata
    rulepack_id: str = ""
    score_variant: str = ""
    reference_year: int = 0
    authority_url: str = ""
    authority_doi: str = ""


def compute_content_hash(data: dict[str, Any]) -> str:
    """计算规则包内容哈希。"""
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def validate_thresholds(thresholds: list[ThresholdDef]) -> None:
    """验证阈值区间连续性。"""
    if not thresholds:
        return
    sorted_thresholds = sorted(thresholds, key=lambda t: t.low)
    for i in range(len(sorted_thresholds) - 1):
        current = sorted_thresholds[i]
        next_t = sorted_thresholds[i + 1]
        if abs(current.high - next_t.low) > 0.001:
            raise ValueError(
                f"Threshold gap/overlap detected: [{current.low}, {current.high}] "
                f"and [{next_t.low}, {next_t.high}]"
            )


def load_rulepack(data: dict[str, Any], mode: str = "strict") -> RulepackConfig:
    """加载规则包。"""
    config = RulepackConfig(**data)
    if mode == "strict":
        for comp in config.components:
            validate_thresholds(comp.thresholds)
    return config


# ──────────────────────────────────────────────────────────────────────
# Scoring submodules
# ──────────────────────────────────────────────────────────────────────

from .score_result import ScoreComponent, ScoreResult
from .missing_policy import MissingDataPolicy, MissingDataPolicyConfig, apply_policy
from .organ_support import (
    RespiratorySupport,
    MechanicalCirculatorySupport,
    RenalReplacementTherapy,
    MedicationAdministration,
    GCSAssessment,
    SupportIndication,
    RespiratorySupportType,
    CirculatorySupportType,
    RRTModality,
    OrganSupportSource,
)
from .window_spec import WindowSpec, ScoreWindowSpec
from .protocols import ScoreCalculator
from .sofa_router import calculate_sofa, SOFAVersionMismatchError, SOFA2NotReadyError, ProductionExecutionRejectedError
from .registry import ScoreCalculatorRegistry, create_default_registry
from .clinical_scoring_service import ClinicalScoringService

__all__ = [
    # Rulepack
    "ThresholdDef", "ComponentDef", "RulepackConfig",
    "compute_content_hash", "validate_thresholds", "load_rulepack",
    # Score result
    "ScoreComponent", "ScoreResult",
    # Missing policy
    "MissingDataPolicy", "MissingDataPolicyConfig", "apply_policy",
    # Organ support
    "RespiratorySupport", "MechanicalCirculatorySupport",
    "RenalReplacementTherapy", "MedicationAdministration",
    "GCSAssessment", "SupportIndication", "RespiratorySupportType",
    "CirculatorySupportType", "RRTModality", "OrganSupportSource",
    # Window spec
    "WindowSpec", "ScoreWindowSpec",
    # Protocols
    "ScoreCalculator",
    # SOFA router
    "calculate_sofa", "SOFAVersionMismatchError",
    "SOFA2NotReadyError", "ProductionExecutionRejectedError",
    # Registry & Service
    "ScoreCalculatorRegistry", "create_default_registry",
    "ClinicalScoringService",
]
