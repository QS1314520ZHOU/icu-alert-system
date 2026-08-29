"""SOFA 版本路由。根据 score_variant 选择正确的规则包和计算器。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import datetime

from ..enums import ScoreVariant
from ..observation import Observation
from .calculators.sofa import SOFACalculator
from .calculators.sofa2 import SOFA2Calculator
from .missing_policy import MissingDataPolicy
from .organ_support import (
    CeilingOfTreatmentContext,
    DeliriumTreatmentAdministration,
    GCSAssessment,
    MechanicalCirculatorySupport,
    MedicationAdministration,
    MotorResponseAssessment,
    RenalReplacementTherapy,
    RespiratorySupport,
    SedationEpisode,
)
from .rulepacks.loaded_rulepack import LoadedRulepack
from .score_result import ScoreResult
from .window_spec import ScoreWindowSpec


class SOFAVersionMismatchError(Exception):
    """规则包与请求的版本不匹配。"""

    def __init__(self, requested: str, actual: str) -> None:
        self.requested = requested
        self.actual = actual
        super().__init__(f"SOFA 版本不匹配: 请求 {requested}, 规则包 {actual}")


class SOFA2NotReadyError(Exception):
    """SOFA-2 规则包尚未就绪。"""

    def __init__(self, blocked_reasons: list[str] | None = None) -> None:
        self.blocked_reasons = blocked_reasons or []
        reasons_str = "; ".join(self.blocked_reasons) if self.blocked_reasons else "unknown"
        super().__init__(f"SOFA-2 规则包尚未就绪。阻塞原因: {reasons_str}")


class ProductionExecutionRejectedError(Exception):
    """拒绝在 production 模式下运行未经过临床审批的实验性规则包。"""

    def __init__(self, rulepack_id: str, clinical_approval_status: str) -> None:
        super().__init__(
            f"拒绝运行规则包 '{rulepack_id}'：clinical_approval_status 为 '{clinical_approval_status}'，"
            f"禁止在 production 模式下运行。"
        )


def calculate_sofa(
    *,
    variant: ScoreVariant,
    rulepack: LoadedRulepack,
    observations: list[Observation],
    evaluation_time: datetime,
    window_spec: ScoreWindowSpec,
    respiratory_supports: list[RespiratorySupport] | None = None,
    circulatory_supports: list[MechanicalCirculatorySupport] | None = None,
    rrt_records: list[RenalReplacementTherapy] | None = None,
    medications: list[MedicationAdministration] | None = None,
    ceiling_contexts: list[CeilingOfTreatmentContext] | None = None,
    gcs_assessments: list[GCSAssessment] | None = None,
    motor_assessments: list[MotorResponseAssessment] | None = None,
    sedation_episodes: list[SedationEpisode] | None = None,
    delirium_administrations: list[DeliriumTreatmentAdministration] | None = None,
    patient_weight_kg: float | None = None,
    missing_policy: MissingDataPolicy | str = MissingDataPolicy.STRICT_PARTIAL,
    execution_mode: str = "experimental",
) -> ScoreResult:
    """SOFA 版本路由入口。"""
    # 拒绝在 production 模式运行
    if execution_mode == "production":
        raise ProductionExecutionRejectedError(rulepack.config.rulepack_id, rulepack.config.clinical_approval_status)

    # 验证 variant 与 rulepack 匹配
    expected_variant = variant.value
    actual_variant = rulepack.config.score_variant
    if actual_variant and actual_variant != expected_variant:
        raise SOFAVersionMismatchError(expected_variant, actual_variant)

    if variant == ScoreVariant.SOFA_2_2025:
        if not rulepack.config.executable:
            raise SOFA2NotReadyError(blocked_reasons=rulepack.config.blocked_reasons)
        from .rulepacks.sofa2_rulepack import is_sofa2_ready

        if not is_sofa2_ready():
            raise SOFA2NotReadyError(blocked_reasons=rulepack.config.blocked_reasons)

        calculator2 = SOFA2Calculator(rulepack=rulepack)
        result = calculator2.calculate(
            observations,
            evaluation_time=evaluation_time,
            window_spec=window_spec,
            respiratory_supports=respiratory_supports,
            circulatory_supports=circulatory_supports,
            rrt_records=rrt_records,
            medications=medications,
            ceiling_contexts=ceiling_contexts,
            gcs_assessments=gcs_assessments,
            motor_assessments=motor_assessments,
            sedation_episodes=sedation_episodes,
            delirium_administrations=delirium_administrations,
            patient_weight_kg=patient_weight_kg,
            missing_policy=missing_policy,
        )
    else:
        calculator1 = SOFACalculator(rulepack=rulepack)
        result = calculator1.calculate(
            observations,
            evaluation_time=evaluation_time,
            window_spec=window_spec,
            patient_weight_kg=patient_weight_kg,
        )

    # 确保结果包含正确的版本信息
    return result.model_copy(
        update={
            "score_variant": variant.value,
            "rulepack_id": rulepack.config.rulepack_id,
            "rulepack_version": rulepack.config.rulepack_version,
            "rulepack_content_hash": rulepack.config.content_hash,
            "reference_year": rulepack.config.reference_year,
            "clinical_approval_status": rulepack.config.clinical_approval_status,
            "lifecycle_status": rulepack.config.lifecycle_status,
        }
    )
