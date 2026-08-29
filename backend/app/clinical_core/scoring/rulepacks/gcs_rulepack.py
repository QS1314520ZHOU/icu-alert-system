"""外部 GCS 总分有效性验证规则包。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from typing import Any

from .. import RulepackConfig

GCS_CONFIG: dict[str, Any] = {
    "score_name": "GCS",
    "rulepack_version": "gcs-1.0",
    "schema_version": "1.0",
    "authority": "Teasdale G, Jennett B",
    "authority_reference": "Teasdale G, Jennett B. Lancet. 1974;2:81-84",
    "clinical_approval_status": "not_approved",
    "lifecycle_status": "experimental",
    "applicable_care_settings": ["icu", "ed", "ward", "pacu"],
    "applicable_population": "adult patients",
    "exclusion_conditions": [],
    "canonical_units": {},
    "components": [
        {
            "name": "gcs_total", "display_name": "External GCS Total Score",
            "codes": ["param_score_gcs_obs", "gcsScore", "GCS"],
            "unit_concept": "gcs", "required_unit": "score",
            "lookback_hours": 8, "max_staleness_hours": 8, "aggregation": "latest", "missing_policy": "require",
            "description": "External GCS total. Not E/V/M recalculation. Valid range 3-15.",
            "thresholds": [],
        },
    ],
    "window_spec_id": "gcs-window-1.0",
    "missing_data_policy": "missing → insufficient",
}


def get_gcs_rulepack() -> RulepackConfig:
    from .. import load_rulepack
    return load_rulepack(GCS_CONFIG, mode="experimental")
