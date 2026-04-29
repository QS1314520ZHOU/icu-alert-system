from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.counterfactual_model import SemiMechanisticCounterfactualModel
from app.services import counterfactual_model as counterfactual_module


class _AlertEngine:
    async def _collect_patient_facts(self, patient, patient_id):
        del patient, patient_id
        return {"labs": {"wbc": {"value": 17}}}

    async def _calc_sofa(self, patient, patient_id, device_id, his_pid):
        del patient, patient_id, device_id, his_pid
        return {"score": 8}


@pytest.mark.asyncio
async def test_counterfactual_vasopressor_simulation_returns_projected_state() -> None:
    model = SemiMechanisticCounterfactualModel(db=None, alert_engine=_AlertEngine())

    async def _snapshot(patient_id, patient, *, hours=12):
        del patient_id, patient, hours
        return {
            "map": {"current": 58},
            "hr": {"current": 122},
            "spo2": {"current": 91},
            "lactate": {"current": 4.3},
            "fio2": {"current": 60},
            "peep": {"current": 8},
            "urine_ml_kg_h_6h": 0.35,
            "vasoactive_support": {"current_dose_ug_kg_min": 0.12},
        }

    model.build_snapshot = _snapshot  # type: ignore[method-assign]
    original_get_device_id = counterfactual_module.get_device_id
    counterfactual_module.get_device_id = _fake_get_device_id  # type: ignore[assignment]

    try:
        result = await model.simulate("p1", {"_id": "p1", "hisPid": "H1"}, {"intervention_type": "vasopressor_up", "dose_delta_pct": 25})
    finally:
        counterfactual_module.get_device_id = original_get_device_id  # type: ignore[assignment]

    assert result["intervention_type"] == "vasopressor_up"
    assert result["projected_state"]["map_30m"] is not None
    assert result["projected_state"]["map_30m"] > result["current_state"]["map"]
    assert result["delta"]["lactate_30m"] <= 0
    assert result["model_meta"]["kind"] == "semi_mechanistic_counterfactual_model"
    assert len(result["response_curve"]["map"]) >= 2


@pytest.mark.asyncio
async def test_counterfactual_peep_simulation_exposes_competing_effects() -> None:
    model = SemiMechanisticCounterfactualModel(db=None, alert_engine=_AlertEngine())

    async def _snapshot(patient_id, patient, *, hours=12):
        del patient_id, patient, hours
        return {
            "map": {"current": 64},
            "hr": {"current": 108},
            "spo2": {"current": 89},
            "lactate": {"current": 2.9},
            "fio2": {"current": 70},
            "peep": {"current": 10},
            "urine_ml_kg_h_6h": 0.45,
            "vasoactive_support": {"current_dose_ug_kg_min": 0.06},
        }

    model.build_snapshot = _snapshot  # type: ignore[method-assign]
    original_get_device_id = counterfactual_module.get_device_id
    counterfactual_module.get_device_id = _fake_get_device_id  # type: ignore[assignment]

    try:
        result = await model.simulate("p1", {"_id": "p1", "hisPid": "H1"}, {"intervention_type": "peep_up", "peep_delta": 2})
    finally:
        counterfactual_module.get_device_id = original_get_device_id  # type: ignore[assignment]

    assert result["intervention_type"] == "peep_up"
    assert result["delta"]["spo2_30m"] >= 0
    assert result["delta"]["map_30m"] <= 0
    assert "recruitability" in result["state_factors"]


async def _fake_get_device_id(patient_id: str, prefer_type: str | None = None, patient_doc: dict | None = None) -> str | None:
    del patient_id, prefer_type, patient_doc
    return "monitor-1"
