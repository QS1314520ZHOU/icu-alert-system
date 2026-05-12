from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any
import builtins
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.vital_trajectory_forecaster import VitalTrajectoryForecaster, DEFAULT_CONTINUOUS_CODES
from app.services.local_model_paths import local_model_dir


class _Db:
    def col(self, name: str) -> Any:
        raise AssertionError("db should not be touched for empty history fallback")


class _Config:
    yaml_cfg = {"ai_service": {"local_models": {"base_dir": "missing-model-root", "chronos_dir": "chronos"}}}


def test_trajectory_forecast_unavailable_and_horizon_clamped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))

    async def fake_history(self, patient_id: str, code: str) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(VitalTrajectoryForecaster, "_history", fake_history)
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)

    result = asyncio.run(service.forecast("p1", ["HR", "BAD"], horizon_hours=99))

    assert result["available"] is False
    assert result["horizon_hours"] == 12
    assert result["codes"] == ["HR"]
    assert len(result["series"]["HR"]["forecast"]) == 12


def test_trajectory_forecast_defaults_to_continuous_eight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))

    async def fake_history(self, patient_id: str, code: str) -> list[dict[str, Any]]:
        return [{"time": None, "value": 70}]

    monkeypatch.setattr(VitalTrajectoryForecaster, "_history", fake_history)
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)

    result = asyncio.run(service.forecast("p1", None, horizon_hours=6))

    assert tuple(result["codes"]) == DEFAULT_CONTINUOUS_CODES


def test_trajectory_forecast_disabled_by_runtime_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)

    async def fake_runtime_config() -> dict[str, Any]:
        return {"enabled": False, "default_codes": ["HR", "MAP"], "version": 7}

    monkeypatch.setattr(service, "_runtime_config", fake_runtime_config)

    result = asyncio.run(service.forecast("p1", None, horizon_hours=6))

    assert result["available"] is False
    assert result["reason"] == "trajectory forecast disabled by runtime config"
    assert result["threshold_risks"] == []
    assert result["model_meta"]["backend"] == "disabled"
    assert result["model_meta"]["config_version"] == 7


def test_trajectory_threshold_risk_probability_detects_map_breach() -> None:
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)
    series = {
        "MAP": {
            "forecast": [
                {"mean": 62, "lower": 58, "upper": 66},
                {"mean": 60, "lower": 55, "upper": 65},
            ]
        }
    }
    cfg = {
        "alert_enabled": True,
        "alert_codes": ["MAP"],
        "thresholds": [{"code": "MAP", "operator": "<", "threshold": 65, "probability": 0.7, "severity": "high", "horizon_hours": 4}],
    }

    risks = service.threshold_risks(series, cfg, model_available=True)

    assert risks
    assert risks[0]["code"] == "MAP"
    assert risks[0]["probability"] >= 0.7


def test_trajectory_forecast_path_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)

    assert str(service._model_dir()).startswith(str(tmp_path))


def test_trajectory_forecast_finds_safetensors_weight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "chronos"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_bytes(b"placeholder")
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)

    assert model_dir / "model.safetensors" in service._candidate_paths()


def test_local_model_dir_env_override_strips_windows_path_on_linux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))

    class Config:
        yaml_cfg = {"ai_service": {"local_models": {"chronos_dir": "D:\\icu-models\\chronos"}}}

    assert local_model_dir(Config(), "chronos_dir", "chronos") == tmp_path / "chronos"


def test_safetensors_missing_chronos_dependency_has_actionable_reason(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "chronos"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_bytes(b"placeholder")
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "chronos":
            raise ModuleNotFoundError("No module named 'chronos'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)

    status = service.status()

    assert status["available"] is False
    assert "install chronos-forecasting package" in status["reason"]


def test_chronos_pipeline_load_success_sets_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "chronos"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_bytes(b"placeholder")
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class FakeTorch:
        float32 = "float32"
        bfloat16 = "bfloat16"
        cuda = FakeCuda()

    class FakeChronosPipeline:
        calls: list[dict[str, Any]] = []

        @classmethod
        def from_pretrained(cls, path: str, **kwargs):
            cls.calls.append({"path": path, **kwargs})
            return object()

    monkeypatch.setitem(sys.modules, "chronos", types.SimpleNamespace(ChronosPipeline=FakeChronosPipeline))
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)
    service._torch = FakeTorch()

    assert service._load_hf_pipeline(model_dir) is True
    service._loaded = True
    assert service._backend == "chronos"
    assert service.status()["available"] is True
    assert FakeChronosPipeline.calls[0]["torch_dtype"] == "float32"
