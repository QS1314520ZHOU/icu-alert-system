from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.clinical_trial_service import RuleEvaluator, candidate_status_flow


def test_rule_evaluator_matches_multiple_trials_style_rules() -> None:
    patient = {"age": 66, "clinicalDiagnosis": "ARDS 合并脓毒症", "hisSex": "男"}
    trial = {
        "trial_name": "ARDS Study",
        "inclusion_rules": [
            {"field": "age", "operator": "between", "value": [18, 80]},
            {"field": "diagnosis", "operator": "contains", "value": "ARDS"},
        ],
        "exclusion_rules": [{"field": "sex", "operator": "eq", "value": "女"}],
    }
    result = RuleEvaluator().explain_match(patient, trial)
    assert result["possible_match"] is True
    assert len(result["matched_inclusion"]) == 2


def test_rule_evaluator_handles_missing_data_as_not_ready() -> None:
    patient = {"clinicalDiagnosis": "休克"}
    trial = {"trial_name": "Shock Study", "inclusion_rules": [{"field": "age", "operator": "gte", "value": 18}], "exclusion_rules": []}
    result = RuleEvaluator().explain_match(patient, trial)
    assert result["possible_match"] is False
    assert result["missing_data"]


def test_rule_evaluator_exclusion_blocks_candidate() -> None:
    patient = {"age": 70, "clinicalDiagnosis": "ARDS"}
    trial = {
        "trial_name": "ARDS Study",
        "inclusion_rules": [{"field": "diagnosis", "operator": "contains", "value": "ARDS"}],
        "exclusion_rules": [{"field": "age", "operator": "gt", "value": 65}],
    }
    result = RuleEvaluator().explain_match(patient, trial)
    assert result["possible_match"] is False
    assert result["triggered_exclusion"]


def test_candidate_status_flow_marks_completed_steps() -> None:
    flow = candidate_status_flow("research_team_contacted")
    assert flow[0]["done"] is True
    assert flow[3]["done"] is True
    assert flow[-1]["done"] is False


def test_rule_evaluator_supports_respiratory_alias_fields() -> None:
    patient = {"latest_pf_ratio": 180, "latest_peep": 6, "clinicalDiagnosis": "ARDS"}
    trial = {
        "trial_name": "ARDS Vent Study",
        "inclusion_rules": [
            {"field": "pf_ratio", "operator": "gte", "value": 150},
            {"field": "peep", "operator": "lte", "value": 8},
        ],
        "exclusion_rules": [],
    }
    result = RuleEvaluator().explain_match(patient, trial)
    assert result["possible_match"] is True
    assert result["human_review_required"] is True
