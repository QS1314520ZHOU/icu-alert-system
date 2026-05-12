from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.treatment_policy_service import TreatmentPolicyService


class _Collection:
    async def find_one(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return {"_id": "p1", "allergies": ""}


class _Db:
    def col(self, name: str) -> _Collection:
        return _Collection()


class _Config:
    yaml_cfg = {"ai_service": {"local_models": {"base_dir": "missing-model-root", "cql_sepsis_dir": "cql-sepsis"}}}


@pytest.mark.asyncio
async def test_treatment_policy_unavailable_when_weight_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    service = TreatmentPolicyService(db=_Db(), config=_Config(), alert_engine=None)

    result = await service.recommend_action("64f000000000000000000001")

    assert result["available"] is False
    assert result["recommendation"] is None
    assert result["safety_validation"]["passed"] in {True, False}
    assert "no torch weight found" in result["reason"] or "torch unavailable" in result["reason"] or "安全红线" in result["reason"]


def test_treatment_policy_path_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ICU_MODELS_DIR", str(tmp_path))
    service = TreatmentPolicyService(db=_Db(), config=_Config(), alert_engine=None)

    assert str(service._model_dir()).startswith(str(tmp_path))
