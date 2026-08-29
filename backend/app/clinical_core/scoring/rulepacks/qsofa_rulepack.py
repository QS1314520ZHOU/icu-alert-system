"""qSOFA 规则包配置。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from .. import RulepackConfig

QSOFA_CONFIG = {
    "score_name": "qSOFA",
    "rulepack_version": "qsofa-1.0",
    "schema_version": "1.0",
    "authority": "Singer M et al., Sepsis-3",
    "authority_reference": "Singer M, et al. JAMA. 2016;315(8):801-810",
    "clinical_approval_status": "not_approved",
    "lifecycle_status": "experimental",
    "applicable_care_settings": ["ed", "ward", "icu"],
    "applicable_population": "adult patients with suspected infection",
    "exclusion_conditions": ["not a diagnostic tool for sepsis"],
    "canonical_units": {"respiratory_rate": "/min", "systolic_bp": "mmHg", "consciousness": "score"},
    "components": [
        {
            "name": "respiratory_rate", "display_name": "Respiratory Rate ≥22",
            "codes": ["param_resp", "RR"], "unit_concept": "respiratory_rate", "required_unit": "/min",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [{"low": 0, "high": 21.9, "score": 0}, {"low": 22, "high": 999, "score": 1}],
        },
        {
            "name": "systolic_bp", "display_name": "Systolic BP ≤100",
            "codes": ["param_nibp_s", "param_ibp_s", "SBP"], "unit_concept": "blood_pressure", "required_unit": "mmHg",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [{"low": 100.1, "high": 999, "score": 0}, {"low": 0, "high": 100, "score": 1}],
        },
        {
            "name": "consciousness", "display_name": "Altered Consciousness (GCS <15)",
            "codes": ["param_score_gcs_obs", "gcsScore", "GCS"], "unit_concept": "gcs", "required_unit": "score",
            "lookback_hours": 4, "max_staleness_hours": 2, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [{"low": 15, "high": 15, "score": 0}, {"low": 0, "high": 14, "score": 1}],
        },
    ],
    "window_spec_id": "qsofa-window-1.0",
    "missing_data_policy": "any component missing → insufficient",
}


def get_qsofa_rulepack() -> RulepackConfig:
    from .. import load_rulepack
    return load_rulepack(QSOFA_CONFIG, mode="experimental")
