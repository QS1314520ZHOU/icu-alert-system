"""NEWS2 规则包配置。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from .. import RulepackConfig

NEWS2_CONFIG = {
    "score_name": "NEWS2",
    "rulepack_version": "news2-1.0",
    "schema_version": "1.0",
    "authority": "Royal College of Physicians",
    "authority_reference": "NEWS2: National Early Warning Score 2, December 2017",
    "clinical_approval_status": "not_approved",
    "lifecycle_status": "experimental",
    "applicable_care_settings": ["icu", "ed", "ward", "pacu"],
    "applicable_population": "adult patients",
    "exclusion_conditions": [],
    "canonical_units": {
        "respiratory_rate": "/min", "spo2": "%", "temperature": "°C",
        "systolic_bp": "mmHg", "heart_rate": "bpm",
    },
    "components": [
        {
            "name": "respiratory_rate", "display_name": "Respiratory Rate",
            "codes": ["param_resp", "RR"], "unit_concept": "respiratory_rate", "required_unit": "/min",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 8, "score": 3}, {"low": 9, "high": 11, "score": 1},
                {"low": 12, "high": 20, "score": 0}, {"low": 21, "high": 24, "score": 2},
                {"low": 25, "high": 999, "score": 3},
            ],
        },
        {
            "name": "spo2_scale1", "display_name": "SpO2 Scale 1",
            "codes": ["param_spo2", "SpO2"], "unit_concept": "spo2", "required_unit": "%",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 91, "score": 3}, {"low": 92, "high": 93, "score": 2},
                {"low": 94, "high": 95, "score": 1}, {"low": 96, "high": 100, "score": 0},
            ],
        },
        {
            "name": "spo2_scale2", "display_name": "SpO2 Scale 2 (hypercapnic respiratory failure)",
            "codes": ["param_spo2", "SpO2"], "unit_concept": "spo2", "required_unit": "%",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 83, "score": 3}, {"low": 84, "high": 85, "score": 2},
                {"low": 86, "high": 87, "score": 1}, {"low": 88, "high": 92, "score": 0},
                {"low": 93, "high": 94, "score": 1}, {"low": 95, "high": 96, "score": 2},
                {"low": 97, "high": 100, "score": 3},
            ],
        },
        {
            "name": "supplemental_oxygen", "display_name": "Supplemental Oxygen",
            "codes": ["supplemental_oxygen", "oxygen_flow", "param_O2_flow"],
            "unit_concept": "boolean", "required_unit": "",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [{"low": 0, "high": 0, "score": 0}, {"low": 1, "high": 1, "score": 2}],
        },
        {
            "name": "temperature", "display_name": "Temperature",
            "codes": ["param_T", "T"], "unit_concept": "temperature", "required_unit": "°C",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 35.0, "score": 3}, {"low": 35.1, "high": 36.0, "score": 1},
                {"low": 36.1, "high": 38.0, "score": 0}, {"low": 38.1, "high": 39.0, "score": 1},
                {"low": 39.1, "high": 999, "score": 2},
            ],
        },
        {
            "name": "systolic_bp", "display_name": "Systolic BP",
            "codes": ["param_nibp_s", "param_ibp_s", "SBP"], "unit_concept": "blood_pressure", "required_unit": "mmHg",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 90, "score": 3}, {"low": 91, "high": 100, "score": 2},
                {"low": 101, "high": 110, "score": 1}, {"low": 111, "high": 219, "score": 0},
                {"low": 220, "high": 999, "score": 3},
            ],
        },
        {
            "name": "heart_rate", "display_name": "Heart Rate",
            "codes": ["param_HR", "HR"], "unit_concept": "heart_rate", "required_unit": "bpm",
            "lookback_hours": 4, "max_staleness_hours": 1, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [
                {"low": 0, "high": 40, "score": 3}, {"low": 41, "high": 50, "score": 1},
                {"low": 51, "high": 90, "score": 0}, {"low": 91, "high": 110, "score": 1},
                {"low": 111, "high": 130, "score": 2}, {"low": 131, "high": 999, "score": 3},
            ],
        },
        {
            "name": "consciousness", "display_name": "Consciousness (ACVPU)",
            "codes": ["param_consciousness", "param_score_gcs_obs", "consciousness"],
            "unit_concept": "consciousness", "required_unit": "",
            "lookback_hours": 8, "max_staleness_hours": 4, "aggregation": "latest", "missing_policy": "require",
            "thresholds": [{"low": 0, "high": 0, "score": 0}, {"low": 1, "high": 1, "score": 3}],
        },
    ],
    "window_spec_id": "news2-window-1.0",
    "missing_data_policy": "key components missing → insufficient",
}


def get_news2_rulepack() -> RulepackConfig:
    from .. import load_rulepack
    return load_rulepack(NEWS2_CONFIG, mode="experimental")
