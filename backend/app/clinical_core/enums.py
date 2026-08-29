"""领域枚举定义。

从 critical-care-alert-platform/src/ccalert/domain/enums.py 迁移。
仅提取评分核心所需的枚举：DataQuality, ObservationCategory, ScoreVariant。
"""

from __future__ import annotations

from enum import StrEnum


class ObservationCategory(StrEnum):
    """观察值分类。"""

    VITAL_SIGN = "vital_sign"
    LABORATORY = "laboratory"
    DEVICE_PARAMETER = "device_parameter"
    CLINICAL_SCORE = "clinical_score"
    NURSING_ASSESSMENT = "nursing_assessment"


class DataQuality(StrEnum):
    """数据质量状态。"""

    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    DUPLICATED = "duplicated"
    IMPLAUSIBLE = "implausible"
    UNIT_UNKNOWN = "unit_unknown"
    PATIENT_BINDING_SUSPECTED = "patient_binding_suspected"
    SOURCE_UNAVAILABLE = "source_unavailable"


class ScoreVariant(StrEnum):
    """评分变体标识。每种变体对应唯一规则包。"""

    CLASSIC_SOFA_1996 = "classic_sofa_1996"
    SOFA_2_2025 = "sofa_2_2025"
    NEWS2_2017 = "news2_2017"
    QSOFA_SEPSIS3_2016 = "qsofa_sepsis3_2016"
    KDIGO_AKI_2012 = "kdigo_aki_2012"
    EXTERNAL_GCS_TOTAL = "external_gcs_total"
    LEGACY_MEWS_CANDIDATE = "legacy_mews_candidate"
