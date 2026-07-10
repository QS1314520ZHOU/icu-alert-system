from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.autonomous_agent import AutonomousInvestigationAgent
from app.services.mdt_prompts import validate_specialist_output


def test_specialist_validation_adds_confidence_and_dissent_defaults() -> None:
    payload = validate_specialist_output("renal_agent", {"priority": "bad", "confidence": 2}, set())

    assert payload["priority"] == "medium"
    assert payload["confidence"] == 1.0
    assert payload["dissent_points"] == []


def test_autonomous_agent_caps_rounds_and_timeout() -> None:
    agent = AutonomousInvestigationAgent(db=None, config=None, alert_engine=None, max_rounds=99, timeout_seconds=999)

    assert agent.max_rounds == 8
    assert agent.timeout_seconds == 90
