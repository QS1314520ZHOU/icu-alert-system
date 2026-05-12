from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
import builtins

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.vital_trajectory_forecaster import VitalTrajectoryForecaster
from app.services.local_model_paths import local_model_dir


class _Db:
    def col(self, name: str) -> Any:
        raise AssertionError("db should not be touched for empty history fallback")


class _Config:
    yaml_cfg = {"ai_service": {"local_models": {"base_dir": "missing-model-root", "chronos_dir": "chronos"}}}


@pytest.mark.asyncio
async def test_trajectory_forecast_unavailable_and_horizon_clamped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))

    async def fake_history(self, patient_id: str, code: str) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(VitalTrajectoryForecaster, "_history", fake_history)
    service = VitalTrajectoryForecaster(db=_Db(), config=_Config(), alert_engine=None)

    result = await service.forecast("p1", ["HR", "BAD"], horizon_hours=99)

    assert result["available"] is False
    assert result["horizon_hours"] == 12
    assert result["codes"] == ["HR"]
    assert len(result["series"]["HR"]["forecast"]) == 12


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
    assert "pip install chronos-forecasting" in status["reason"]
