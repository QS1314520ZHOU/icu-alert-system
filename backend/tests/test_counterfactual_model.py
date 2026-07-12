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


# ---------------------------------------------------------------------------
# 防御性类型测试：验证裸 float 值不再触发 AttributeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twin_latest_handles_float_values_from_vitals() -> None:
    """_twin_latest 应能处理 vitals.latest 中值为裸 float 的情况。

    这是本次 bug 的精确重现：_get_latest_vitals_by_patient 返回
    {"hr": 85.0, "map": 70.0}（裸 float），而 _twin_latest 之前用
    (latest.get("map") or {}).get("current") 去读，非零 float 是 truthy，
    or 不会短路到空 dict，导致 float.get("current") → AttributeError。
    """
    twin = {
        "vitals": {
            "latest": {
                "hr": 85.0,
                "rr": 18.0,
                "sbp": 120.0,
                "map": 70.0,
                "time": None,
            },
            "snapshot": {},
            "ventilator": {},
        },
        "snapshot": {},
    }
    # 不应抛异常
    hr = SemiMechanisticCounterfactualModel._twin_latest(twin, "hr")
    assert hr == 85.0, f"expected 85.0, got {hr}"
    map_val = SemiMechanisticCounterfactualModel._twin_latest(twin, "map")
    assert map_val == 70.0, f"expected 70.0, got {map_val}"


@pytest.mark.asyncio
async def test_twin_latest_handles_missing_key_gracefully() -> None:
    """_twin_latest 键缺失时返回 None 而不抛异常。"""
    twin = {"vitals": {"latest": {}}, "snapshot": {}}
    result = SemiMechanisticCounterfactualModel._twin_latest(twin, "spo2")
    assert result is None


@pytest.mark.asyncio
async def test_twin_latest_handles_nested_dict_values() -> None:
    """_twin_latest 仍能正常处理嵌套 dict 结构（正常路径不退化）。"""
    twin = {
        "vitals": {
            "latest": {
                "hr": {"current": 88.0, "value": 90.0},
            },
            "snapshot": {},
            "ventilator": {},
        },
        "snapshot": {},
    }
    result = SemiMechanisticCounterfactualModel._twin_latest(twin, "hr")
    assert result == 88.0  # 优先 current


@pytest.mark.asyncio
async def test_simulate_tolerates_flat_float_snapshot() -> None:
    """simulate() 在快照字段为裸 float（而非 {"current": ...}）时不抛异常。"""
    model = SemiMechanisticCounterfactualModel(db=None, alert_engine=_AlertEngine())

    async def _snapshot(patient_id, patient, *, hours=12):
        del patient_id, patient, hours
        return {
            "map": 58.0,       # 裸 float，非 dict
            "hr": 122.0,        # 裸 float，非 dict
            "spo2": 91.0,       # 裸 float，非 dict
            "lactate": 4.3,     # 裸 float，非 dict
            "fio2": 60.0,       # 裸 float，非 dict
            "peep": 8.0,        # 裸 float，非 dict
            "urine_ml_kg_h_6h": 0.35,
            "vasoactive_support": 0.12,  # 裸 float，非 dict
        }

    model.build_snapshot = _snapshot  # type: ignore[method-assign]
    original_get_device_id = counterfactual_module.get_device_id
    counterfactual_module.get_device_id = _fake_get_device_id  # type: ignore[assignment]

    try:
        result = await model.simulate(
            "p1",
            {"_id": "p1", "hisPid": "H1"},
            {"intervention_type": "vasopressor_up", "dose_delta_pct": 25},
        )
    finally:
        counterfactual_module.get_device_id = original_get_device_id  # type: ignore[assignment]

    # 不应抛异常，且当前状态应正确解析为 float
    assert result["current_state"]["map"] == 58
    assert result["current_state"]["lactate"] == 4.3
    assert result["current_state"]["vaso_dose_ug_kg_min"] == 0.12
    assert result["projected_state"]["map_30m"] is not None


@pytest.mark.asyncio
async def test_feature_vector_tolerates_mixed_dict_and_float_snapshot() -> None:
    """TransformerCounterfactualModel._feature_vector 混合 dict/float 时不抛异常。"""
    model = TransformerCounterfactualModel(
        db=None, alert_engine=_AlertEngine(), allow_fallback=True
    )
    # 通过 _feature_vector (是实例方法但只读 snapshot，可以直接调用)
    snapshot = {
        "map": 70.0,            # 裸 float
        "hr": {"current": 110},  # 正常 dict
        "spo2": 96.0,            # 裸 float
        "lactate": 1.5,          # 裸 float
        "fio2": 40.0,            # 裸 float
        "peep": 6.0,             # 裸 float
        "urine_ml_kg_h_6h": 0.8,
        "vasoactive_support": {"current_dose_ug_kg_min": 0.05},  # 正常 dict
    }
    payload = {"intervention_type": "current_baseline"}
    vec = model._feature_vector(snapshot, payload)
    assert len(vec) == 32
    assert vec[0] == 70.0  # map
    assert vec[1] == 110.0  # hr
    assert vec[2] == 96.0  # spo2
    assert vec[7] == 0.05  # vaso_dose


@pytest.mark.asyncio
async def test_simulate_tolerates_zero_float_snapshot() -> None:
    """simulate() 在快照字段为 0.0 时不抛异常（0.0 是 falsy，测试 or {} 短路方向）。"""
    model = SemiMechanisticCounterfactualModel(db=None, alert_engine=_AlertEngine())

    async def _snapshot(patient_id, patient, *, hours=12):
        del patient_id, patient, hours
        return {
            "map": 0.0,
            "hr": 0.0,
            "spo2": 0.0,
            "lactate": 0.0,
            "fio2": 0.0,
            "peep": 0.0,
            "urine_ml_kg_h_6h": 0.0,
            "vasoactive_support": 0.0,
        }

    model.build_snapshot = _snapshot  # type: ignore[method-assign]
    original_get_device_id = counterfactual_module.get_device_id
    counterfactual_module.get_device_id = _fake_get_device_id  # type: ignore[assignment]

    try:
        result = await model.simulate(
            "p1",
            {"_id": "p1", "hisPid": "H1"},
            {"intervention_type": "vasopressor_up", "dose_delta_pct": 25},
        )
    finally:
        counterfactual_module.get_device_id = original_get_device_id  # type: ignore[assignment]

    assert result["current_state"]["map"] == 0
    assert result["current_state"]["hr"] == 0
