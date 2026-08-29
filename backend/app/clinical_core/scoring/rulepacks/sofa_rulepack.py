"""经典 SOFA 1996 规则包配置。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from typing import Any

from .. import RulepackConfig, load_rulepack

CLASSIC_SOFA_1996_CONFIG: dict[str, Any] = {
    "rulepack_id": "classic-sofa-1996",
    "score_name": "SOFA",
    "score_variant": "classic_sofa_1996",
    "rulepack_version": "classic-sofa-1996.1",
    "schema_version": "1.0",
    "reference_year": 1996,
    "authority": "Vincent JL et al., ESICM",
    "authority_reference": "Vincent JL, et al. Intensive Care Medicine, 1996;22:707-710",
    "authority_url": "https://link.springer.com/article/10.1007/BF01709751",
    "clinical_approval_status": "not_approved",
    "lifecycle_status": "experimental",
    "applicable_care_settings": ["icu"],
    "applicable_population": "adult ICU patients",
    "exclusion_conditions": [],
    "canonical_units": {
        "pao2": "mmHg", "fio2": "fraction", "platelets": "10^9/L",
        "bilirubin": "μmol/L", "map": "mmHg", "vasopressor_dose": "μg/kg/min",
        "gcs": "score", "creatinine": "μmol/L", "urine_output": "mL/24h",
    },
    "components": [
        {
            "name": "respiratory", "display_name": "Respiratory (PaO2/FiO2)",
            "codes": ["param_PaO2", "PaO2", "param_FiO2", "FiO2"],
            "unit_concept": "pao2_fio2_ratio", "required_unit": "mmHg/fraction",
            "lookback_hours": 24, "max_staleness_hours": 4, "aggregation": "worst", "missing_policy": "require",
            "description": "PaO2/FiO2 ratio. PaO2 and FiO2 must be paired within 30 minutes.",
            "thresholds": [
                {"low": 400, "high": 99999, "score": 0}, {"low": 300, "high": 399, "score": 1},
                {"low": 200, "high": 299, "score": 2}, {"low": 100, "high": 199, "score": 3},
                {"low": 0, "high": 99, "score": 4},
            ],
            "source_table": "Table 1", "source_page": "708",
        },
        {
            "name": "coagulation", "display_name": "Coagulation (Platelets)",
            "codes": ["PLT", "platelets"], "unit_concept": "platelets", "required_unit": "10^9/L",
            "lookback_hours": 24, "max_staleness_hours": 12, "aggregation": "worst", "missing_policy": "require",
            "thresholds": [
                {"low": 150, "high": 99999, "score": 0}, {"low": 100, "high": 149, "score": 1},
                {"low": 50, "high": 99, "score": 2}, {"low": 20, "high": 49, "score": 3},
                {"low": 0, "high": 19, "score": 4},
            ],
            "source_table": "Table 1", "source_page": "708",
        },
        {
            "name": "liver", "display_name": "Liver (Bilirubin)",
            "codes": ["TBIL", "bilirubin"], "unit_concept": "bilirubin", "required_unit": "μmol/L",
            "lookback_hours": 24, "max_staleness_hours": 12, "aggregation": "worst", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 20, "score": 0}, {"low": 20.1, "high": 33, "score": 1},
                {"low": 33.1, "high": 102, "score": 2}, {"low": 102.1, "high": 204, "score": 3},
                {"low": 204.1, "high": 99999, "score": 4},
            ],
            "source_table": "Table 1", "source_page": "708",
        },
        {
            "name": "cardiovascular", "display_name": "Cardiovascular (MAP and Vasopressors)",
            "codes": ["vasopressor_dose", "norepinephrine_dose", "dopamine_dose", "dobutamine_dose", "epinephrine_dose"],
            "unit_concept": "vasopressor_dose", "required_unit": "μg/kg/min",
            "lookback_hours": 24, "max_staleness_hours": 1, "aggregation": "worst", "missing_policy": "require",
            "description": "Uses MedicationAdministration for vasopressor doses.",
            "thresholds": [
                {"low": 0, "high": 0, "score": 0}, {"low": 0.001, "high": 0.099, "score": 1},
                {"low": 0.1, "high": 0.199, "score": 2}, {"low": 0.2, "high": 0.499, "score": 3},
                {"low": 0.5, "high": 999, "score": 4},
            ],
            "source_table": "Table 1", "source_page": "708",
        },
        {
            "name": "central_nervous_system", "display_name": "CNS (GCS)",
            "codes": ["param_score_gcs_obs", "gcsScore", "GCS"],
            "unit_concept": "gcs", "required_unit": "score",
            "lookback_hours": 24, "max_staleness_hours": 8, "aggregation": "worst", "missing_policy": "require",
            "thresholds": [
                {"low": 15, "high": 15, "score": 0}, {"low": 13, "high": 14, "score": 1},
                {"low": 10, "high": 12, "score": 2}, {"low": 6, "high": 9, "score": 3},
                {"low": 0, "high": 5, "score": 4},
            ],
            "source_table": "Table 1", "source_page": "708",
        },
        {
            "name": "renal_creatinine", "display_name": "Renal - Creatinine",
            "codes": ["CREA", "creatinine"], "unit_concept": "creatinine", "required_unit": "μmol/L",
            "lookback_hours": 24, "max_staleness_hours": 12, "aggregation": "worst", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 110, "score": 0}, {"low": 110.1, "high": 170, "score": 1},
                {"low": 170.1, "high": 299, "score": 2}, {"low": 300, "high": 440, "score": 3},
                {"low": 440.1, "high": 99999, "score": 4},
            ],
            "source_table": "Table 1", "source_page": "708",
        },
        {
            "name": "renal_urine", "display_name": "Renal - Urine Output (24h total)",
            "codes": ["urine_output", "urineVolume"], "unit_concept": "urine_output", "required_unit": "mL/24h",
            "lookback_hours": 24, "max_staleness_hours": 12, "aggregation": "sum", "missing_policy": "require",
            "description": "Classic SOFA urine path uses 24h total mL (NOT mL/kg/h).",
            "thresholds": [
                {"low": 500, "high": 999999, "score": 0}, {"low": 200, "high": 499.99, "score": 3},
                {"low": 0, "high": 199.99, "score": 4},
            ],
            "source_table": "Table 1", "source_page": "708",
        },
    ],
    "window_spec_id": "classic-sofa-1996-window-1.0",
    "missing_data_policy": "any organ missing → partial; all missing → insufficient",
}

SOFA_CONFIG = CLASSIC_SOFA_1996_CONFIG


def get_sofa_rulepack() -> RulepackConfig:
    return load_rulepack(CLASSIC_SOFA_1996_CONFIG, mode="experimental")


def get_classic_sofa_1996_rulepack() -> RulepackConfig:
    return load_rulepack(CLASSIC_SOFA_1996_CONFIG, mode="experimental")
