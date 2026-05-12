from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import patient_data, treatment_policy
from app.routers.ai_modules import autonomous


class _InsertResult:
    inserted_id = ObjectId()


class _FeedbackCollection:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []

    async def insert_one(self, record: dict[str, Any]) -> _InsertResult:
        self.inserted.append(record)
        return _InsertResult()


class _Db:
    def __init__(self) -> None:
        self.feedback = _FeedbackCollection()

    def col(self, name: str) -> Any:
        if name == "treatment_policy_feedback":
            return self.feedback
        raise AssertionError(f"unexpected collection: {name}")


@pytest.mark.asyncio
async def test_treatment_recommend_router_returns_public_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Service:
        async def recommend_action(self, patient_id: str) -> dict[str, Any]:
            assert patient_id == "p1"
            return {
                "available": False,
                "recommendation": None,
                "current_orders": {"norepinephrine_ug_kg_min": None, "fluid_24h_ml": 0},
                "q_value_delta": 0.1,
                "safety_validation": {"passed": False, "checks": []},
                "model_meta": {"available": False},
            }

    monkeypatch.setattr(treatment_policy.runtime, "db", object(), raising=False)
    monkeypatch.setattr(treatment_policy.runtime, "config", object(), raising=False)
    monkeypatch.setattr(treatment_policy.runtime, "alert_engine", None, raising=False)
    monkeypatch.setattr(treatment_policy, "get_treatment_policy_service", lambda **kwargs: _Service())

    result = await treatment_policy.treatment_recommend("p1")

    assert set(result) >= {"available", "recommendation", "current_orders", "q_value_delta", "safety_validation", "model_meta"}
    assert result["available"] is False


@pytest.mark.asyncio
async def test_treatment_feedback_persists_training_log(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _Db()
    monkeypatch.setattr(treatment_policy.runtime, "db", db, raising=False)

    result = await treatment_policy.treatment_feedback(
        {
            "patient_id": "p1",
            "recommendation_id": "cql-abc",
            "adopted": False,
            "reason": "MAP improved without bolus",
            "actor": "doctor-a",
        }
    )

    assert result["code"] == 0
    assert db.feedback.inserted[0]["patient_id"] == "p1"
    assert db.feedback.inserted[0]["recommendation_id"] == "cql-abc"
    assert db.feedback.inserted[0]["adopted"] is False


@pytest.mark.asyncio
async def test_autonomous_sse_error_safe_when_patient_missing() -> None:
    response = await autonomous.autonomous_investigate({"question": "排查休克风险"})
    body = ""
    async for chunk in response.body_iterator:
        body += chunk.decode() if isinstance(chunk, bytes) else chunk

    assert "event: error" in body
    assert "patient_id required" in body


@pytest.mark.asyncio
async def test_vitals_forecast_router_filters_codes_and_clamps_horizon(monkeypatch: pytest.MonkeyPatch) -> None:
    patient_id = str(ObjectId())
    captured: dict[str, Any] = {}

    class _Service:
        async def forecast(self, pid: str, codes: list[str], horizon_hours: int) -> dict[str, Any]:
            captured.update({"pid": pid, "codes": codes, "horizon_hours": horizon_hours})
            return {
                "available": False,
                "horizon_hours": horizon_hours,
                "codes": codes,
                "series": {},
                "model_meta": {"available": False},
            }

    monkeypatch.setattr(patient_data.runtime, "db", object(), raising=False)
    monkeypatch.setattr(patient_data.runtime, "config", object(), raising=False)
    monkeypatch.setattr(patient_data.runtime, "alert_engine", None, raising=False)
    monkeypatch.setattr(patient_data, "get_vital_trajectory_forecaster", lambda **kwargs: _Service())

    result = await patient_data.patient_vitals_forecast(patient_id, codes="HR,BAD,Lactate", horizon_hours=12)

    assert result["available"] is False
    assert captured == {"pid": patient_id, "codes": ["HR", "Lactate"], "horizon_hours": 12}
