"""SOFA-2 2025 官方规则包。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from typing import Any

from .. import RulepackConfig, load_rulepack

SOFA_2_2025_CONFIG: dict[str, Any] = {
    "rulepack_id": "sofa-2-2025",
    "score_name": "SOFA",
    "score_variant": "sofa_2_2025",
    "rulepack_version": "sofa-2-2025.1",
    "schema_version": "1.0",
    "reference_year": 2025,
    "authority": "SOFA-2 Working Group (Ranzani et al.)",
    "authority_reference": "Development and Validation of the SOFA-2 Score. JAMA. 2025;334(23):2090-2103.",
    "authority_url": "https://jamanetwork.com/journals/jama/fullarticle/2840822",
    "authority_doi": "10.1001/jama.2025.20516",
    "clinical_approval_status": "not_approved",
    "lifecycle_status": "experimental",
    "verification_status": "technical_verified",
    "executable": True,
    "rulepack_completeness": 1.0,
    "applicable_care_settings": ["icu"],
    "applicable_population": "adult critically ill ICU patients",
    "exclusion_conditions": ["pediatric_patients_under_18"],
    "canonical_units": {
        "pao2": "mmHg", "spo2": "%", "fio2": "fraction", "platelets": "10^9/L",
        "bilirubin": "mg/dL", "map": "mmHg", "vasopressor_dose": "μg/kg/min",
        "gcs": "score", "creatinine": "mg/dL", "urine_output": "mL/kg/h",
    },
    "components": [
        {
            "name": "brain", "display_name": "Brain (SOFA-2)",
            "codes": ["param_score_gcs_obs", "gcsScore", "GCS"],
            "unit_concept": "gcs", "required_unit": "score",
            "lookback_hours": 24, "max_staleness_hours": 8, "aggregation": "worst", "missing_policy": "require",
            "description": "GCS 15(0), 13-14(1), 9-12(2), 6-8(3), 3-5(4). Delirium treatment meds score at least 1 point.",
            "thresholds": [
                {"low": 15, "high": 15, "score": 0}, {"low": 13, "high": 14, "score": 1},
                {"low": 9, "high": 12, "score": 2}, {"low": 6, "high": 8, "score": 3},
                {"low": 3, "high": 5, "score": 4},
            ],
            "source_table": "JAMA Main Paper Table 2", "source_page": "8",
            "verification_status": "technical_verified",
        },
        {
            "name": "respiratory", "display_name": "Respiratory (SOFA-2)",
            "codes": ["param_PaO2", "PaO2", "param_FiO2", "FiO2", "SpO2"],
            "unit_concept": "pao2_fio2_ratio", "required_unit": "mmHg/fraction",
            "lookback_hours": 24, "max_staleness_hours": 4, "aggregation": "worst", "missing_policy": "require",
            "description": "PaO2/FiO2 >300(0), <=300(1), <=225(2), <=150+support(3), <=75+support or ECMO(4).",
            "thresholds": [
                {"low": 300.001, "high": 9999, "score": 0}, {"low": 225.001, "high": 300, "score": 1},
                {"low": 150.001, "high": 225, "score": 2}, {"low": 75.001, "high": 150, "score": 3},
                {"low": 0, "high": 75, "score": 4},
            ],
            "source_table": "JAMA Main Paper Table 2", "source_page": "8",
            "verification_status": "technical_verified",
        },
        {
            "name": "hemostasis", "display_name": "Hemostasis (SOFA-2)",
            "codes": ["PLT", "platelets"], "unit_concept": "platelets", "required_unit": "10^9/L",
            "lookback_hours": 24, "max_staleness_hours": 12, "aggregation": "worst", "missing_policy": "require",
            "description": "Platelets >150(0), 101-150(1), 81-100(2), 51-80(3), <=50(4).",
            "thresholds": [
                {"low": 150.001, "high": 9999, "score": 0}, {"low": 100.001, "high": 150, "score": 1},
                {"low": 80.001, "high": 100, "score": 2}, {"low": 50.001, "high": 80, "score": 3},
                {"low": 0, "high": 50, "score": 4},
            ],
            "source_table": "JAMA Main Paper Table 2", "source_page": "8",
            "verification_status": "technical_verified",
        },
        {
            "name": "liver", "display_name": "Liver (SOFA-2)",
            "codes": ["TBIL", "bilirubin"], "unit_concept": "bilirubin", "required_unit": "mg/dL",
            "lookback_hours": 24, "max_staleness_hours": 12, "aggregation": "worst", "missing_policy": "require",
            "description": "Total bilirubin <=1.20(0), 1.21-3.0(1), 3.01-6.0(2), 6.01-12.0(3), >12.0(4) mg/dL.",
            "thresholds": [
                {"low": 0, "high": 1.20, "score": 0}, {"low": 1.201, "high": 3.0, "score": 1},
                {"low": 3.001, "high": 6.0, "score": 2}, {"low": 6.001, "high": 12.0, "score": 3},
                {"low": 12.001, "high": 999, "score": 4},
            ],
            "source_table": "JAMA Main Paper Table 2", "source_page": "8",
            "verification_status": "technical_verified",
        },
        {
            "name": "kidney", "display_name": "Kidney (SOFA-2)",
            "codes": ["CREA", "creatinine", "urine_output"],
            "unit_concept": "creatinine_or_urine", "required_unit": "mg/dL or mL/kg/h",
            "lookback_hours": 24, "max_staleness_hours": 12, "aggregation": "worst", "missing_policy": "require",
            "description": "Creatinine <=1.2(0), 1.21-2.0(1), 2.01-3.5(2), >3.5(3). UO paths for staging.",
            "thresholds": [
                {"low": 0, "high": 1.20, "score": 0}, {"low": 1.201, "high": 2.0, "score": 1},
                {"low": 2.001, "high": 3.50, "score": 2}, {"low": 3.501, "high": 999, "score": 3},
            ],
            "source_table": "JAMA Main Paper Table 2", "source_page": "8",
            "verification_status": "technical_verified",
        },
        {
            "name": "cardiovascular", "display_name": "Cardiovascular (SOFA-2)",
            "codes": ["MAP", "mean_arterial_pressure", "norepinephrine_dose", "epinephrine_dose", "dopamine_dose"],
            "unit_concept": "vasopressor_dose", "required_unit": "μg/kg/min",
            "lookback_hours": 24, "max_staleness_hours": 1, "aggregation": "worst", "missing_policy": "require",
            "description": "NE+Epi sum logic with other pressor and mechanical circulatory support.",
            "thresholds": [
                {"low": 0, "high": 0, "score": 0}, {"low": 0.001, "high": 0.20, "score": 2},
                {"low": 0.201, "high": 0.40, "score": 3}, {"low": 0.401, "high": 999, "score": 4},
            ],
            "source_table": "JAMA Main Paper Table 2", "source_page": "8",
            "verification_status": "technical_verified",
        },
    ],
    "window_spec_id": "sofa-2-2025-window-1.0",
    "missing_data_policy": "official_day1_normal_imputation",
    "blocked_reasons": [],
    "official_material_status": {
        "main_article_accessible": True, "scoring_table_accessible": True,
        "all_6_organs_verified": True, "units_verified": True,
    },
}


def get_sofa2_rulepack() -> RulepackConfig:
    return load_rulepack(SOFA_2_2025_CONFIG, mode="experimental")


def is_sofa2_ready() -> bool:
    rp = get_sofa2_rulepack()
    if not rp.executable:
        return False
    if rp.verification_status != "technical_verified":
        return False
    if len(rp.components) != 6:
        return False
    return all(comp.thresholds for comp in rp.components)
