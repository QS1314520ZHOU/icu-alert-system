from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.temporal_model_runtime import TemporalRiskModelRuntime


class _Cfg:
    def __init__(self, enabled: bool = True) -> None:
        self.yaml_cfg = {"ai_service": {"temporal_model": {"heuristic_fallback_enabled": enabled}}}


def test_temporal_runtime_returns_heuristic_prediction_without_local_weights() -> None:
    runtime = TemporalRiskModelRuntime(_Cfg(enabled=True))
    sequence = np.asarray(
        [
            [
                [98.0, 72.0, 96.0, 20.0, 37.0],
                [108.0, 66.0, 94.0, 24.0, 37.8],
                [118.0, 58.0, 90.0, 30.0, 38.6],
            ]
        ],
        dtype=np.float32,
    )
    meta = np.asarray([[73.0, 0.0, 4.0, 1.0, 9.0, 4.2]], dtype=np.float32)

    result = runtime.predict(
        sequence=sequence,
        meta_features=meta,
        organ_keys=["respiratory", "circulatory", "renal", "neurologic"],
        horizons=(4, 12, 24),
    )

    assert result["available"] is True
    assert result["backend"] == "heuristic"
    assert 0.0 < float(result["probability"]) < 1.0
    assert set(result["organ_probabilities"].keys()) == {"respiratory", "circulatory", "renal", "neurologic"}
    assert set(result["future_probabilities"].keys()) == {4, 12, 24}
    assert "components" in result
    assert float(result["organ_probabilities"]["circulatory"]) >= 0.5


def test_temporal_runtime_can_disable_heuristic_fallback() -> None:
    runtime = TemporalRiskModelRuntime(_Cfg(enabled=False))
    sequence = np.zeros((1, 2, 5), dtype=np.float32)

    result = runtime.predict(sequence=sequence, meta_features=None, organ_keys=["respiratory"], horizons=(4,))

    assert result["available"] is False
    assert result["backend"] == "heuristic"
    assert result["reason"] == "no_local_weight_found"

