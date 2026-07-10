from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rounding_service import (
    _build_clinical_priorities,
    _build_overnight_digest,
    _build_system_assessments,
    _fallback_focus_points,
    _risk_from_alerts,
)


def test_rounding_risk_from_alerts_uses_highest_severity() -> None:
    assert _risk_from_alerts([{"severity": "warning"}, {"severity": "critical"}]) == "critical"
    assert _risk_from_alerts([]) == "low"


def test_rounding_fallback_focus_points_handles_missing_data() -> None:
    points = _fallback_focus_points({"key_events": [], "data_quality": {"data_gaps": ["检验缺失"]}})
    assert points
    assert points[0]["risk_level"] == "low"
    assert "检验缺失" in points[0]["evidence"]


def test_rounding_deep_digest_summarizes_high_risk_data() -> None:
    digest = _build_overnight_digest(
        hours=24,
        alerts=[{"name": "低氧预警", "severity": "high"}],
        labs=[{"name": "PCT", "value": 8, "unit": "ng/mL", "flag": "H"}],
        drugs=[{"name": "去甲肾上腺素", "dose": "0.2"}],
        vitals=[{"label": "SpO2", "first": 96, "latest": 90, "min": 88, "max": 98}],
        bedside=[{"text": "夜间吸痰"}],
        data_gaps=[],
    )
    assert "高危" in digest["headline"]
    assert digest["alerts"]
    assert digest["vitals"]


def test_rounding_system_assessment_and_priorities_handle_missing_and_events() -> None:
    systems = {
        "neuro": [],
        "respiratory": [{"type": "alert", "title": "低氧", "severity": "critical", "time": "2026-01-01"}],
        "circulation": [],
        "renal": [],
        "infection": [],
        "nutrition": [],
        "coagulation": [],
        "others": [],
    }
    assessments = _build_system_assessments(systems)
    assert any(item["system"] == "respiratory" and item["status"] == "critical" for item in assessments)
    assert any(item["system"] == "neuro" and item["status"] == "stable" for item in assessments)

    priorities = _build_clinical_priorities(systems, [], ["检验缺失"])
    assert priorities[0]["title"] == "呼吸系统重点问题"
    assert any(item["title"] == "数据完整性补核" for item in priorities)
