"""临床核心领域层。

独立于 FastAPI/数据库/外部服务，仅依赖 pydantic。
从 critical-care-alert-platform 迁移，保持零基础设施依赖。
"""

from .enums import DataQuality, ObservationCategory, ScoreVariant
from .observation import Observation
from .scoring import (
    # Rulepack
    ThresholdDef, ComponentDef, RulepackConfig,
    compute_content_hash, validate_thresholds, load_rulepack,
    # Score result
    ScoreComponent, ScoreResult,
    # Missing policy
    MissingDataPolicy, MissingDataPolicyConfig, apply_policy,
    # Organ support
    RespiratorySupport, MechanicalCirculatorySupport,
    RenalReplacementTherapy, MedicationAdministration,
    GCSAssessment, SupportIndication, RespiratorySupportType,
    CirculatorySupportType, RRTModality, OrganSupportSource,
    # Window spec
    WindowSpec, ScoreWindowSpec,
    # Protocols
    ScoreCalculator,
    # SOFA router
    calculate_sofa, SOFAVersionMismatchError,
    SOFA2NotReadyError, ProductionExecutionRejectedError,
    # Registry & Service
    ScoreCalculatorRegistry, create_default_registry,
    ClinicalScoringService,
)

__all__ = [
    # Enums
    "DataQuality", "ObservationCategory", "ScoreVariant",
    # Observation
    "Observation",
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
