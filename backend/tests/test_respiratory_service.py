from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import runtime
from app.services.respiratory_service import _parameter_completeness, _safety_score, _worklist_actions, evaluate_sbt_candidate


def test_sbt_candidate_passes_default_thresholds() -> None:
    runtime.config = SimpleNamespace(yaml_cfg={})
    row = {"fio2": 0.4, "peep": 5, "pf_ratio": 220}
    result = evaluate_sbt_candidate(row, hemodynamic_stable=True, rass=0)
    assert result["status"] == "candidate"


def test_sbt_candidate_reports_missing_and_abnormal_values() -> None:
    runtime.config = SimpleNamespace(yaml_cfg={})
    row = {"fio2": 0.8, "peep": None, "pf_ratio": 120}
    result = evaluate_sbt_candidate(row, hemodynamic_stable=False, rass=-4)
    assert result["status"] == "not_suitable"
    assert len(result["reasons"]) >= 4


def test_respiratory_worklist_scores_high_risk_patient() -> None:
    row = {
        "fio2": 0.7,
        "peep": 12,
        "pplat": 30,
        "driving_pressure": 18,
        "pf_ratio": 120,
        "latest_cuff_pressure": None,
        "difficult_airway": True,
        "ventilator_mode": "PCV",
        "vt": 420,
        "spo2": 90,
        "rass": 0,
    }
    row["risk_tags"] = ["高驱动压", "低氧合", "高 FiO2", "高 PEEP", "气囊压待测", "困难气道"]
    row["parameter_completeness"] = _parameter_completeness(row)
    assert _safety_score(row) < 50
    actions = _worklist_actions({**row, "sbt_candidate_status": {"status": "candidate"}})
    assert any(item["title"] == "复核肺保护通气" for item in actions)
    assert any(item["title"] == "确认困难气道预案" for item in actions)


def test_sbt_unverified_conditions_are_not_assumed_met() -> None:
    runtime.config = SimpleNamespace(yaml_cfg={})
    row = {"fio2": 0.4, "peep": 5, "pf_ratio": 220}
    result = evaluate_sbt_candidate(row, hemodynamic_stable=None, rass=None)
    assert result["status"] == "candidate"
    assert result["verified"] is False
    assert "循环稳定性未核实" in result["unverified"] and "RASS 未记录" in result["unverified"]
    assert "核实" in result["recommendation"]


def test_cuff_pressure_due_rules():
    from datetime import datetime, timedelta
    from app.services.respiratory_service import _cuff_pressure_due

    now = datetime(2026, 10, 30, 12, 0)
    base = {"artificial_airway": True, "airway_type": "气管插管"}
    # 快速模式未查询：不下结论
    assert _cuff_pressure_due({**base, "cuff_pressure_queried": False}, now) is False
    # 无人工气道：不提示
    assert _cuff_pressure_due({"artificial_airway": False, "airway_type": "无", "cuff_pressure_queried": True}, now) is False
    # 无记录：提示
    assert _cuff_pressure_due({**base, "cuff_pressure_queried": True}, now) is True
    # 8h 内有记录：不提示；超过 8h：提示
    recent = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    old = (now - timedelta(hours=9)).isoformat()
    assert _cuff_pressure_due({**base, "cuff_pressure_queried": True, "latest_cuff_pressure": 26, "latest_cuff_pressure_time": recent}, now) is False
    assert _cuff_pressure_due({**base, "cuff_pressure_queried": True, "latest_cuff_pressure": 26, "latest_cuff_pressure_time": old}, now) is True
