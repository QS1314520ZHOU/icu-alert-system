"""SOFA-2 器官支持与临床评估领域模型。

从 critical-care-alert-platform 迁移。完全自包含，无内部依赖。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator


class SupportIndication(StrEnum):
    RESPIRATORY_FAILURE = "respiratory_failure"
    CARDIOVASCULAR = "cardiovascular"
    RENAL_DYSFUNCTION = "renal_dysfunction"
    NON_RENAL = "non_renal"
    DELIRIUM_TREATMENT = "delirium_treatment"
    UNKNOWN = "unknown"


class RespiratorySupportType(StrEnum):
    HFNC = "high_flow_nasal_cannula"
    CPAP = "cpap"
    BIPAP = "bilevel_positive_airway_pressure"
    NIV = "non_invasive_ventilation"
    IMV = "invasive_mechanical_ventilation"
    HOME_VENT = "long_term_home_ventilation"
    ECMO = "ecmo"


class CirculatorySupportType(StrEnum):
    VA_ECMO = "va_ecmo"
    IABP = "iabp"
    LVAD = "lvad"
    MICROAXIAL_FLOW_PUMP = "microaxial_flow_pump"  # e.g., Impella


class RRTModality(StrEnum):
    CRRT = "crrt"
    INTERMITTENT_HD = "intermittent_hd"
    PERITONEAL_DIALYSIS = "peritoneal_dialysis"


class NorepinephrineSaltForm(StrEnum):
    BASE = "base"
    BITARTRATE_MONOHYDRATE = "bitartrate_monohydrate"
    ANHYDROUS_BITARTRATE = "anhydrous_bitartrate"
    HYDROCHLORIDE = "hydrochloride"
    UNKNOWN = "unknown"


class MotorResponseCategory(StrEnum):
    THUMBS_UP_FIST_PEACE = "thumbs_up_fist_peace"  # 0 pt
    LOCALIZING_PAIN = "localizing_pain"  # 1 pt
    WITHDRAWAL_PAIN = "withdrawal_pain"  # 2 pt
    FLEXION_PAIN = "flexion_pain"  # 3 pt
    EXTENSION_NO_RESPONSE_MYOCLONUS = "extension_no_response_myoclonus"  # 4 pt


class RespiratorySupport(BaseModel):
    """呼吸支持记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    support_id: str
    patient_id: str
    encounter_id: str
    organization_id: str
    facility_id: str
    support_type: RespiratorySupportType
    indication: SupportIndication = SupportIndication.RESPIRATORY_FAILURE
    started_at: datetime
    ended_at: datetime | None = None
    fio2: float | None = None
    flow_rate: float | None = None
    flow_unit: str = "L/min"
    active_at_evaluation_time: bool = True
    ceiling_of_treatment: bool = False
    unavailable_due_to_resource: bool = False
    source: str = ""
    evidence_id: str = ""

    @field_validator("support_id", "patient_id", "organization_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ID 字段不能为空")
        return v

    @field_validator("started_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("started_at 必须为 timezone-aware")
        return v

    @field_validator("ended_at")
    @classmethod
    def _tz_aware_opt(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("ended_at 必须为 timezone-aware")
        return v


class MechanicalCirculatorySupport(BaseModel):
    """机械循环支持记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    support_id: str
    patient_id: str
    encounter_id: str
    organization_id: str
    facility_id: str
    support_type: CirculatorySupportType
    indication: SupportIndication = SupportIndication.CARDIOVASCULAR
    started_at: datetime
    ended_at: datetime | None = None
    active_at_evaluation_time: bool = True
    source: str = ""
    evidence_id: str = ""

    @field_validator("support_id", "patient_id", "organization_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ID 字段不能为空")
        return v

    @field_validator("started_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("started_at 必须为 timezone-aware")
        return v

    @field_validator("ended_at")
    @classmethod
    def _tz_aware_opt(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("ended_at 必须为 timezone-aware")
        return v


class RenalReplacementTherapy(BaseModel):
    """肾脏替代治疗记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rrt_id: str
    patient_id: str
    encounter_id: str
    organization_id: str
    facility_id: str
    modality: RRTModality
    indication: SupportIndication = SupportIndication.RENAL_DYSFUNCTION
    chronic_use: bool = False
    intermittent: bool = False
    started_at: datetime
    ended_at: datetime | None = None
    terminated: bool = False
    active_at_evaluation_time: bool = True
    source: str = ""
    evidence_id: str = ""

    @field_validator("rrt_id", "patient_id", "organization_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ID 字段不能为空")
        return v

    @field_validator("started_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("started_at 必须为 timezone-aware")
        return v

    @field_validator("ended_at")
    @classmethod
    def _tz_aware_opt(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("ended_at 避免为 naive datetime")
        return v


class MedicationAdministration(BaseModel):
    """给药记录（血管活性药物、谵妄治疗药物等）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    medication_id: str
    patient_id: str
    encounter_id: str
    organization_id: str
    facility_id: str
    medication: str  # e.g., "norepinephrine", "epinephrine", "dopamine", "haloperidol"
    route: str = "IV"
    infusion_type: str = "continuous"  # "continuous", "bolus", "push"
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: float = 60.0
    dose: float = 0.0
    dose_unit: str = "μg/kg/min"
    weight_basis: str = "actual"
    salt_form: NorepinephrineSaltForm = NorepinephrineSaltForm.BASE
    base_equivalent_dose: float | None = None
    indication: SupportIndication = SupportIndication.CARDIOVASCULAR
    source: str = ""
    evidence_id: str = ""

    @field_validator("medication_id", "patient_id", "organization_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ID 字段不能为空")
        return v

    @field_validator("start_time")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start_time 必须为 timezone-aware")
        return v


class CeilingOfTreatmentContext(BaseModel):
    """治疗上限/资源不可用上下文。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_id: str
    patient_id: str
    encounter_id: str
    organization_id: str
    facility_id: str
    organ_system: str  # "respiratory", "cardiovascular", "renal"
    support_precluded: bool = True
    support_unavailable: bool = False
    reason: str = ""
    effective_time: datetime
    source: str = ""
    evidence_id: str = ""

    @field_validator("context_id", "patient_id", "organization_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ID 字段不能为空")
        return v

    @field_validator("effective_time")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("effective_time 必须为 timezone-aware")
        return v


class GCSAssessment(BaseModel):
    """完整 GCS 评估。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gcs_total: int
    eye: int | None = None
    verbal: int | None = None
    motor: int | None = None
    assessed_at: datetime

    # 范围标识（可选，用于跨患者/跨住院隔离校验）
    patient_id: str | None = None
    encounter_id: str | None = None
    organization_id: str | None = None
    facility_id: str | None = None

    @field_validator("gcs_total")
    @classmethod
    def _valid_gcs(cls, v: int) -> int:
        if not (3 <= v <= 15):
            raise ValueError("gcs_total 必须在 3 至 15 之间")
        return v


class MotorResponseAssessment(BaseModel):
    """Motor 反应替代评估。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    motor_response: MotorResponseCategory
    assessed_at: datetime

    # 范围标识（可选）
    patient_id: str | None = None
    encounter_id: str | None = None
    organization_id: str | None = None
    facility_id: str | None = None


class SedationEpisode(BaseModel):
    """镇静事件记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sedation_id: str
    start_time: datetime
    end_time: datetime | None = None
    pre_sedation_gcs: int | None = None
    pre_sedation_gcs_unknown: bool = False

    # 范围标识（可选）
    patient_id: str | None = None
    encounter_id: str | None = None
    organization_id: str | None = None
    facility_id: str | None = None


class DeliriumTreatmentAdministration(BaseModel):
    """谵妄治疗给药记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    administration_id: str
    medication: str
    administered_at: datetime
    explicit_delirium_indication: bool = True
    is_prescription_only: bool = False  # 医嘱 vs 实际给药

    # 范围标识（可选）
    patient_id: str | None = None
    encounter_id: str | None = None
    organization_id: str | None = None
    facility_id: str | None = None


@runtime_checkable
class OrganSupportSource(Protocol):
    """器官支持数据源 Protocol。"""

    async def get_respiratory_supports(
        self,
        organization_id: str,
        patient_id: str,
        encounter_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[RespiratorySupport]: ...

    async def get_circulatory_supports(
        self,
        organization_id: str,
        patient_id: str,
        encounter_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[MechanicalCirculatorySupport]: ...

    async def get_renal_replacement_therapies(
        self,
        organization_id: str,
        patient_id: str,
        encounter_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[RenalReplacementTherapy]: ...
