"""AKI 分期规则包配置。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from .. import RulepackConfig

AKI_CONFIG = {
    "score_name": "AKI",
    "rulepack_version": "aki-1.0",
    "schema_version": "1.0",
    "authority": "KDIGO",
    "authority_reference": "KDIGO Clinical Practice Guideline for AKI. Kidney Int Suppl. 2012;2:1-138",
    "clinical_approval_status": "not_approved",
    "lifecycle_status": "experimental",
    "applicable_care_settings": ["icu", "ward", "ed"],
    "applicable_population": "adult patients",
    "exclusion_conditions": [],
    "canonical_units": {"creatinine": "μmol/L", "urine_output": "mL/kg/h"},
    "components": [
        {
            "name": "creatinine", "display_name": "Creatinine staging",
            "codes": ["CREA", "creatinine"], "unit_concept": "creatinine", "required_unit": "μmol/L",
            "lookback_hours": 168, "max_staleness_hours": 24, "aggregation": "worst", "missing_policy": "require",
            "description": "Requires baseline creatinine. Stage based on ratio to baseline.",
            "thresholds": [],
        },
        {
            "name": "urine_output", "display_name": "Urine output staging",
            "codes": ["urine_output", "urineVolume"], "unit_concept": "urine_output", "required_unit": "mL",
            "lookback_hours": 24, "max_staleness_hours": 6, "aggregation": "sum", "missing_policy": "require",
            "description": "Requires weight for normalization.",
            "thresholds": [],
        },
    ],
    "window_spec_id": "aki-window-1.0",
    "missing_data_policy": "baseline missing → insufficient; weight missing → urine path unavailable",
}


def get_aki_rulepack() -> RulepackConfig:
    from .. import load_rulepack
    return load_rulepack(AKI_CONFIG, mode="experimental")
