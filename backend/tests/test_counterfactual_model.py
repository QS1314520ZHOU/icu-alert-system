from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.counterfactual_model import SemiMechanisticCounterfactualModel, TransformerCounterfactualModel, get_counterfactual_model, simulate_counterfactual
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
    assert result["model_meta"]["backend"] == "semi_mechanistic"
    assert result["model_meta"]["degraded"] is False
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


@pytest.mark.asyncio
async def test_counterfactual_current_baseline_is_flat_and_allows_six_hours() -> None:
    model = SemiMechanisticCounterfactualModel(db=None, alert_engine=_AlertEngine())

    async def _snapshot(patient_id, patient, *, hours=12):
        del patient_id, patient, hours
        return {
            "map": {"current": 70},
            "hr": {"current": 98},
            "spo2": {"current": 96},
            "lactate": {"current": 1.8},
            "fio2": {"current": 40},
            "peep": {"current": 6},
            "urine_ml_kg_h_6h": 0.8,
            "vasoactive_support": {"current_dose_ug_kg_min": 0.02},
        }

    model.build_snapshot = _snapshot  # type: ignore[method-assign]
    original_get_device_id = counterfactual_module.get_device_id
    counterfactual_module.get_device_id = _fake_get_device_id  # type: ignore[assignment]
    try:
        result = await model.simulate("p1", {"_id": "p1", "hisPid": "H1"}, {"intervention_type": "current_baseline", "horizon_minutes": 999})
    finally:
        counterfactual_module.get_device_id = original_get_device_id  # type: ignore[assignment]

    assert result["intervention_type"] == "current_baseline"
    assert result["delta"]["map_30m"] == 0
    assert result["model_meta"]["horizon_minutes"] == 360
    assert result["response_curve"]["map"][0]["value"] == result["response_curve"]["map"][-1]["value"]
    assert result["confidence_bands"]["map"]


@pytest.mark.asyncio
async def test_transformer_counterfactual_fallback_exposes_model_meta(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = type(
        "Cfg",
        (),
        {"yaml_cfg": {"ai_service": {"local_models": {"base_dir": str(tmp_path), "counterfactual_dir": "counterfactual"}}}},
    )()
    fallback = SemiMechanisticCounterfactualModel(db=None, alert_engine=_AlertEngine())

    async def _snapshot(patient_id, patient, *, hours=12):
        del patient_id, patient, hours
        return {"map": {"current": 60}, "hr": {"current": 110}, "spo2": {"current": 94}, "lactate": {"current": 3.0}}

    fallback.build_snapshot = _snapshot  # type: ignore[method-assign]
    model = TransformerCounterfactualModel(db=None, alert_engine=_AlertEngine(), config=cfg, fallback_model=fallback, allow_fallback=True)
    original_get_device_id = counterfactual_module.get_device_id
    counterfactual_module.get_device_id = _fake_get_device_id  # type: ignore[assignment]
    try:
        result = await model.simulate("p1", {"_id": "p1", "hisPid": "H1"}, {"intervention_type": "vasopressor_up"})
    finally:
        counterfactual_module.get_device_id = original_get_device_id  # type: ignore[assignment]

    assert result["model_meta"]["backend"] == "semi_mechanistic"
    assert result["model_meta"]["requested_backend"] == "transformer"
    assert result["model_meta"]["degraded"] is True
    assert result["model_meta"]["fallback_reason"] in {"weights_missing", "torch_unavailable", "inference_error"}


def test_counterfactual_factory_respects_semi_mechanistic_backend() -> None:
    cfg = type("Cfg", (), {"yaml_cfg": {"ai_service": {"counterfactual": {"backend": "semi_mechanistic"}}}})()
    model = get_counterfactual_model(db=None, alert_engine=_AlertEngine(), config=cfg)
    assert isinstance(model, SemiMechanisticCounterfactualModel)


@pytest.mark.asyncio
async def test_counterfactual_rollout_disabled_uses_semi_mechanistic(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = type(
        "Cfg",
        (),
        {"yaml_cfg": {"ai_service": {"counterfactual": {"backend": "transformer", "allow_fallback": False, "transformer_rollout": {"enabled_cohorts": ["test-ward"], "enabled_percentage": 0}}}}},
    )()
    original_get_device_id = counterfactual_module.get_device_id
    counterfactual_module.get_device_id = _fake_get_device_id  # type: ignore[assignment]
    async def _snapshot(self, patient_id, patient, *, hours=12):
        del self, patient_id, patient, hours
        return {"map": {"current": 60}, "hr": {"current": 110}, "spo2": {"current": 94}, "lactate": {"current": 3.0}}
    monkeypatch.setattr(SemiMechanisticCounterfactualModel, "build_snapshot", _snapshot)
    try:
        result = await simulate_counterfactual(db=None, alert_engine=_AlertEngine(), config=cfg, patient_id="p1", patient={"dept": "ICU"}, payload={"intervention_type": "vasopressor_up"})
    finally:
        counterfactual_module.get_device_id = original_get_device_id  # type: ignore[assignment]

    assert result["model_meta"]["backend"] == "semi_mechanistic"
    assert result["model_meta"]["requested_backend"] == "transformer"
    assert result["model_meta"]["fallback_reason"] == "rollout_not_enabled"


async def _fake_get_device_id(patient_id: str, prefer_type: str | None = None, patient_doc: dict | None = None) -> str | None:
    del patient_id, prefer_type, patient_doc
    return "monitor-1"
