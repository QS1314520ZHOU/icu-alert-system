from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.icu_foundation_model_service import ICUFoundationModelService


class _Collection:
    async def find_one(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return None


class _Db:
    def col(self, name: str) -> _Collection:
        return _Collection()


class _Config:
    yaml_cfg = {
        "ai_service": {
            "local_models": {
                "base_dir": "missing-model-root",
                "icarefm_dir": "icarefm",
            }
        }
    }


@pytest.mark.asyncio
async def test_foundation_model_unavailable_returns_zero_embedding(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    service = ICUFoundationModelService(db=_Db(), config=_Config(), alert_engine=None)

    embedding = await service.encode_patient("64f000000000000000000001")
    predictions = await service.zero_shot_predict("64f000000000000000000001")

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (768,)
    assert predictions["available"] is False
    assert "no torch weight found" in predictions["reason"] or "torch unavailable" in predictions["reason"]


def test_foundation_model_path_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    service = ICUFoundationModelService(db=_Db(), config=_Config(), alert_engine=None)

    assert str(service._icarefm_dir()).startswith(str(tmp_path))


def test_foundation_model_knowledge_guided_provider_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    cfg = type(
        "Cfg",
        (),
        {
            "yaml_cfg": {
                "ai_service": {
                    "local_models": {"base_dir": "missing", "knowledge_pretrain_dir": "kgfm"},
                    "foundation_model": {"providers": {"primary": "knowledge_guided", "shadow": ["icarefm"], "mode": "shadow"}},
                }
            }
        },
    )()
    service = ICUFoundationModelService(db=_Db(), config=cfg, alert_engine=None)

    assert service._active_provider() == "knowledge_guided"
    assert str(service._knowledge_guided_dir()).startswith(str(tmp_path))
    assert service.status()["provider"] == "knowledge_guided"
