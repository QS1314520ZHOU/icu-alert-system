"""MEWS 候选规则包配置。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from .. import RulepackConfig

MEWS_CONFIG = {
    "score_name": "MEWS",
    "rulepack_version": "mews-candidate-1.0",
    "schema_version": "1.0",
    "authority": "unverified",
    "authority_reference": "Multiple versions exist. Current thresholds source unverified.",
    "clinical_approval_status": "not_approved",
    "lifecycle_status": "experimental",
    "applicable_care_settings": ["ward"],
    "applicable_population": "adult patients",
    "exclusion_conditions": ["not for production use without clinical approval"],
    "canonical_units": {
        "respiratory_rate": "/min", "temperature": "°C",
        "systolic_bp": "mmHg", "heart_rate": "bpm",
    },
    "components": [
        {
            "name": "respiratory_rate", "display_name": "Respiratory Rate",
            "codes": ["param_resp", "RR"], "unit_concept": "respiratory_rate", "required_unit": "/min",
            "lookback_hours": 4, "max_staleness_hours": 2, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 8, "score": 2}, {"low": 9, "high": 14, "score": 0},
                {"low": 15, "high": 20, "score": 1}, {"low": 21, "high": 29, "score": 2},
                {"low": 30, "high": 999, "score": 3},
            ],
        },
        {
            "name": "temperature", "display_name": "Temperature",
            "codes": ["param_T", "T"], "unit_concept": "temperature", "required_unit": "°C",
            "lookback_hours": 4, "max_staleness_hours": 2, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 35.0, "score": 2}, {"low": 35.1, "high": 38.4, "score": 0},
                {"low": 38.5, "high": 999, "score": 2},
            ],
        },
        {
            "name": "systolic_bp", "display_name": "Systolic BP",
            "codes": ["param_nibp_s", "param_ibp_s", "SBP"], "unit_concept": "blood_pressure", "required_unit": "mmHg",
            "lookback_hours": 4, "max_staleness_hours": 2, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 70, "score": 3}, {"low": 71, "high": 80, "score": 2},
                {"low": 81, "high": 100, "score": 1}, {"low": 101, "high": 199, "score": 0},
                {"low": 200, "high": 999, "score": 2},
            ],
        },
        {
            "name": "heart_rate", "display_name": "Heart Rate",
            "codes": ["param_HR", "HR"], "unit_concept": "heart_rate", "required_unit": "bpm",
            "lookback_hours": 4, "max_staleness_hours": 2, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 40, "score": 2}, {"low": 41, "high": 50, "score": 1},
                {"low": 51, "high": 100, "score": 0}, {"low": 101, "high": 110, "score": 1},
                {"low": 111, "high": 129, "score": 2}, {"low": 130, "high": 999, "score": 3},
            ],
        },
        {
            "name": "consciousness", "display_name": "Consciousness",
            "codes": ["param_score_gcs_obs", "gcsScore"], "unit_concept": "consciousness", "required_unit": "score",
            "lookback_hours": 8, "max_staleness_hours": 4, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [{"low": 15, "high": 15, "score": 0}, {"low": 0, "high": 14, "score": 2}],
        },
    ],
    "window_spec_id": "mews-window-1.0",
    "missing_data_policy": "any component missing → insufficient",
}


def get_mews_rulepack() -> RulepackConfig:
    from .. import load_rulepack
    return load_rulepack(MEWS_CONFIG, mode="experimental")
