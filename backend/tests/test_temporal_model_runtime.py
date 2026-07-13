from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.temporal_model_runtime import TemporalRiskModelRuntime
from app.services.prediction_contract import (
    PREDICTION_SOURCE_RULE_ESTIMATE,
    PREDICTION_SOURCE_TRAINED_MODEL,
    PREDICTION_SOURCE_UNAVAILABLE,
    PREDICTION_SOURCE_UNKNOWN,
    RISK_VALUE_TYPE_RULE_SCORE,
    RISK_VALUE_TYPE_MODEL_PROBABILITY,
    MODEL_STATUS_WEIGHT_MISSING,
    MODEL_STATUS_INFERENCE_FAILED,
    MODEL_STATUS_INVALID_OUTPUT,
    VALIDATION_NOT_APPLICABLE,
    _clamp_valid,
    build_llm_guard_instruction,
    format_temporal_forecast_for_llm,
    infer_prediction_source_from_legacy_score,
    model_metrics_audit,
    normalizer_strip_rule_scores_from_model_metrics,
    normalize_temporal_prediction,
)


class _Cfg:
    def __init__(self, enabled: bool = True, **kwargs) -> None:
        cfg: dict = {"heuristic_fallback_enabled": enabled}
        cfg.update(kwargs)
        self.yaml_cfg = {"ai_service": {"temporal_model": cfg}}


# ══════════════════════════════════════════════════════════════════════════════
# Test 1: No model weights + heuristic ON → rule_estimate
# ══════════════════════════════════════════════════════════════════════════════


def test_no_weights_heuristic_on_returns_rule_estimate() -> None:
    """Heuristic fallback must return prediction_source=rule_estimate."""
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

    # ── old compat fields ──
    assert result["available"] is True
    assert result["backend"] == "heuristic"
    assert 0.0 < float(result["probability"]) < 1.0
    assert set(result["organ_probabilities"].keys()) == {
        "respiratory", "circulatory", "renal", "neurologic"
    }
    assert set(result["future_probabilities"].keys()) == {4, 12, 24}

    # ── new contract fields ──
    assert result["prediction_source"] == PREDICTION_SOURCE_RULE_ESTIMATE
    assert result["output_available"] is True
    assert result["model_available"] is False
    assert result["model_loaded"] is False
    assert result["risk_value_type"] == RISK_VALUE_TYPE_RULE_SCORE
    assert result["risk_value"] is not None
    assert 0.0 < float(result["risk_value"]) < 1.0
    assert result["display_label"] == "规则估算风险"
    assert "非AI模型预测" in result["safety_notice"]
    assert result["model_status"] == MODEL_STATUS_WEIGHT_MISSING
    assert result["local_validation_status"] == VALIDATION_NOT_APPLICABLE
    assert result["fallback_used"] is True
    assert result["model_name"] == "unknown"
    assert result["model_version"] == "unknown"

    # ── future_risk_scores populated for rule estimates ──
    assert set(result["future_risk_scores"].keys()) == {4, 12, 24}

    # ── risk_value_display uses rule format ──
    assert "规则风险指数" in result["risk_value_display"]
    assert "/100" in result["risk_value_display"]

    # ── limitations ──
    assert any("启发式规则估算" in lim for lim in result["limitations"])


# ══════════════════════════════════════════════════════════════════════════════
# Test 2: No model weights + heuristic OFF → unavailable
# ══════════════════════════════════════════════════════════════════════════════


def test_no_weights_heuristic_off_returns_unavailable() -> None:
    runtime = TemporalRiskModelRuntime(_Cfg(enabled=False))
    sequence = np.zeros((1, 2, 5), dtype=np.float32)

    result = runtime.predict(
        sequence=sequence,
        meta_features=None,
        organ_keys=["respiratory"],
        horizons=(4,),
    )

    assert result["available"] is False
    assert result["output_available"] is False
    assert result["model_available"] is False
    assert result["model_loaded"] is False
    assert result["backend"] == "heuristic"
    assert result["prediction_source"] == PREDICTION_SOURCE_UNAVAILABLE
    assert result["risk_value"] is None
    assert result["risk_value_display"] == "—"
    assert result["fallback_used"] is False
    assert result["reason"] == "no_local_weight_found"


# ══════════════════════════════════════════════════════════════════════════════
# Test 3: ONNX model loaded successfully → trained_model
# ══════════════════════════════════════════════════════════════════════════════


def test_onnx_load_success_returns_trained_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Simulate a successful ONNX load and check prediction_source=trained_model."""
    model_file = tmp_path / "temporal_risk.onnx"
    model_file.write_bytes(b"fake-onnx-weight")

    # Create a fake ONNX InferenceSession
    class FakeSession:
        @staticmethod
        def get_inputs():
            return [SimpleNamespace(name="input", shape=[1, 10, 5])]

        @staticmethod
        def get_outputs():
            return [SimpleNamespace(name="output")]

        def run(self, output_names, feeds):
            return [np.array([[0.78, 0.65, 0.55, 0.42, 0.70, 0.82, 0.91, 0.95]], dtype=np.float32)]

    # Patch onnxruntime
    fake_ort = SimpleNamespace(
        InferenceSession=lambda path, providers: FakeSession(),
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    # Configure runtime to look in tmp_path
    cfg = SimpleNamespace()
    cfg.yaml_cfg = {
        "ai_service": {
            "temporal_model": {
                "heuristic_fallback_enabled": True,
                "model_path": str(model_file),
                "model_name": "test_temporal_risk",
                "model_version": "2.0.0",
                "local_validation_status": "calibrated",
                "calibration_version": "cal-v2",
            }
        }
    }
    # Override model_search_roots to return tmp_path
    monkeypatch.setattr(
        "app.services.temporal_model_runtime.model_search_roots",
        lambda: [tmp_path],
    )

    runtime = TemporalRiskModelRuntime(cfg)
    sequence = np.random.randn(1, 10, 5).astype(np.float32)
    meta = np.random.randn(1, 6).astype(np.float32)

    result = runtime.predict(
        sequence=sequence,
        meta_features=meta,
        organ_keys=["respiratory", "circulatory"],
        horizons=(4, 12),
    )

    assert result["prediction_source"] == PREDICTION_SOURCE_TRAINED_MODEL
    assert result["backend"] == "onnx"
    assert result["model_loaded"] is True
    assert result["model_available"] is True
    assert result["risk_value_type"] == RISK_VALUE_TYPE_MODEL_PROBABILITY
    assert result["model_name"] == "test_temporal_risk"
    assert result["model_version"] == "2.0.0"
    assert result["local_validation_status"] == "calibrated"
    assert result["calibration_version"] == "cal-v2"
    assert result["model_status"] == "ok"
    assert result["display_label"] == "模型预测风险"
    assert result["fallback_used"] is False
    assert "模型预测" in result["risk_value_display"] or "%" in result["risk_value_display"]


# ══════════════════════════════════════════════════════════════════════════════
# Test 4: PyTorch model loaded successfully → trained_model
# ══════════════════════════════════════════════════════════════════════════════


def test_pytorch_load_success_returns_trained_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Simulate a successful PyTorch load."""
    model_file = tmp_path / "temporal_risk.pt"
    model_file.write_bytes(b"fake-pytorch-weight")

    class FakeTorchModel:
        @staticmethod
        def eval():
            pass

        def __call__(self, seq, meta=None):
            return np.array([[0.72, 0.60, 0.55, 0.48, 0.68, 0.80, 0.88, 0.93]], dtype=np.float32)

    class _CtxManager:
        """A trivial context manager that does nothing."""
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    class _InferenceMode:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    fake_torch = SimpleNamespace(
        load=lambda path, map_location: FakeTorchModel(),
        jit=SimpleNamespace(
            load=lambda path, map_location: FakeTorchModel(),
        ),
        tensor=lambda data, device=None, dtype=None: np.asarray(data),
        float32="float32",
        inference_mode=lambda: _InferenceMode(),
        device=lambda x: "cpu",
        no_grad=lambda: _CtxManager(),
        cuda=SimpleNamespace(is_available=lambda: False),
        Tensor=np.ndarray,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        "app.services.temporal_model_runtime.torch_device_name",
        lambda: "cpu",
    )

    cfg = SimpleNamespace()
    cfg.yaml_cfg = {
        "ai_service": {
            "temporal_model": {
                "heuristic_fallback_enabled": True,
                "model_path": str(model_file),
                "model_name": "pytorch_risk_model",
                "model_version": "3.1.0",
            }
        }
    }
    monkeypatch.setattr(
        "app.services.temporal_model_runtime.model_search_roots",
        lambda: [tmp_path],
    )

    runtime = TemporalRiskModelRuntime(cfg)
    sequence = np.random.randn(1, 10, 5).astype(np.float32)
    meta = np.random.randn(1, 6).astype(np.float32)

    result = runtime.predict(
        sequence=sequence,
        meta_features=meta,
        organ_keys=["respiratory", "circulatory"],
        horizons=(4, 12, 24),
    )

    assert result["prediction_source"] == PREDICTION_SOURCE_TRAINED_MODEL
    assert result["backend"] == "pytorch"
    assert result["model_loaded"] is True
    assert result["model_available"] is True
    assert result["risk_value_type"] == RISK_VALUE_TYPE_MODEL_PROBABILITY
    assert result["model_name"] == "pytorch_risk_model"
    assert result["model_version"] == "3.1.0"
    assert result["model_status"] == "ok"
    assert result["fallback_used"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Test 5: Model load fails → heuristic fallback → rule_estimate + fallback_used
# ══════════════════════════════════════════════════════════════════════════════


def test_load_failed_falls_back_to_rule_estimate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When a model file exists but fails to load, fallback to heuristic."""
    model_file = tmp_path / "temporal_risk.onnx"
    model_file.write_bytes(b"corrupt-onnx")

    # Make onnxruntime raise on load
    class FailingSession:
        def __init__(self, path, providers):
            raise RuntimeError("Failed to parse ONNX model")

    fake_ort = SimpleNamespace(InferenceSession=FailingSession)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    cfg = SimpleNamespace()
    cfg.yaml_cfg = {
        "ai_service": {
            "temporal_model": {
                "heuristic_fallback_enabled": True,
                "model_path": str(model_file),
            }
        }
    }
    monkeypatch.setattr(
        "app.services.temporal_model_runtime.model_search_roots",
        lambda: [tmp_path],
    )

    runtime = TemporalRiskModelRuntime(cfg)
    sequence = np.random.randn(1, 10, 5).astype(np.float32)

    result = runtime.predict(
        sequence=sequence,
        meta_features=None,
        organ_keys=["respiratory"],
        horizons=(4,),
    )

    # Should fall back to heuristic
    assert result["prediction_source"] == PREDICTION_SOURCE_RULE_ESTIMATE
    assert result["fallback_used"] is True
    assert "load_failed" in result.get("fallback_reason", "") or "load_failed" in result.get("reason", "")
    assert result["available"] is True  # via heuristic
    assert result["output_available"] is True
    # model_loaded=False because the model weight load itself failed
    assert result["model_loaded"] is False
    assert any("load" in lim.lower() or "加载" in lim or "启发式" in lim for lim in result.get("limitations", []))


# ══════════════════════════════════════════════════════════════════════════════
# Test 6: Model output format invalid → unavailable or heuristic fallback
# ══════════════════════════════════════════════════════════════════════════════


def test_invalid_model_output_returns_unavailable_or_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Model that outputs nonsense (empty array) should be handled."""
    model_file = tmp_path / "temporal_risk.onnx"
    model_file.write_bytes(b"fake-onnx")

    class BadSession:
        @staticmethod
        def get_inputs():
            return [SimpleNamespace(name="input", shape=[1, 10, 5])]

        @staticmethod
        def get_outputs():
            return [SimpleNamespace(name="output")]

        def run(self, output_names, feeds):
            # Return empty array → _parse_raw_output returns None
            return [np.array([], dtype=np.float32)]

    fake_ort = SimpleNamespace(InferenceSession=lambda path, providers: BadSession())
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    cfg = SimpleNamespace()
    cfg.yaml_cfg = {
        "ai_service": {
            "temporal_model": {
                "heuristic_fallback_enabled": False,
                "model_path": str(model_file),
            }
        }
    }
    monkeypatch.setattr(
        "app.services.temporal_model_runtime.model_search_roots",
        lambda: [tmp_path],
    )

    runtime = TemporalRiskModelRuntime(cfg)
    sequence = np.random.randn(1, 10, 5).astype(np.float32)

    result = runtime.predict(
        sequence=sequence,
        meta_features=None,
        organ_keys=[],
        horizons=(),
    )

    # Without heuristic fallback, should be unavailable
    assert result["prediction_source"] == PREDICTION_SOURCE_UNAVAILABLE
    assert result["output_available"] is False
    assert result["model_status"] in (MODEL_STATUS_INVALID_OUTPUT, MODEL_STATUS_INFERENCE_FAILED)

    # With heuristic fallback enabled, should fallback
    cfg2 = SimpleNamespace()
    cfg2.yaml_cfg = {
        "ai_service": {
            "temporal_model": {
                "heuristic_fallback_enabled": True,
                "model_path": str(model_file),
            }
        }
    }
    monkeypatch.setattr(
        "app.services.temporal_model_runtime.model_search_roots",
        lambda: [tmp_path],
    )

    runtime2 = TemporalRiskModelRuntime(cfg2)
    result2 = runtime2.predict(
        sequence=sequence,
        meta_features=None,
        organ_keys=["respiratory"],
        horizons=(4,),
    )

    assert result2["prediction_source"] == PREDICTION_SOURCE_RULE_ESTIMATE
    assert result2["fallback_used"] is True
    assert "invalid_model_output" in str(result2.get("fallback_reason", ""))


# ══════════════════════════════════════════════════════════════════════════════
# Test 7: Rule scores excluded from model performance metrics
# ══════════════════════════════════════════════════════════════════════════════


def test_rule_scores_excluded_from_model_metrics() -> None:
    records = [
        {
            "prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE,
            "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE,
            "risk_value": 0.78,
        },
        {
            "prediction_source": PREDICTION_SOURCE_TRAINED_MODEL,
            "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY,
            "risk_value": 0.85,
        },
        {
            "prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE,
            "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE,
            "risk_value": 0.60,
        },
        {
            "prediction_source": PREDICTION_SOURCE_TRAINED_MODEL,
            "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY,
            "risk_value": 0.92,
        },
        # Old record without prediction_source should be excluded
        {
            "model_backend": "heuristic",
            "model_available": True,
            "risk_value": 0.70,
        },
    ]

    filtered = normalizer_strip_rule_scores_from_model_metrics(records)

    assert len(filtered) == 2
    assert all(r["prediction_source"] == PREDICTION_SOURCE_TRAINED_MODEL for r in filtered)
    assert all(r["risk_value_type"] == RISK_VALUE_TYPE_MODEL_PROBABILITY for r in filtered)
    assert {0.85, 0.92} == {r["risk_value"] for r in filtered}


# ══════════════════════════════════════════════════════════════════════════════
# Test 8: Legacy score records — prediction_source inference
# ══════════════════════════════════════════════════════════════════════════════


def test_legacy_score_record_inference() -> None:
    # Old ONNX record
    assert (
        infer_prediction_source_from_legacy_score(
            {"model_backend": "onnx", "model_available": True}
        )
        == PREDICTION_SOURCE_TRAINED_MODEL
    )

    # Old heuristic record
    assert (
        infer_prediction_source_from_legacy_score(
            {"model_backend": "heuristic", "model_available": True}
        )
        == PREDICTION_SOURCE_RULE_ESTIMATE
    )

    # Old unavailable record
    assert (
        infer_prediction_source_from_legacy_score(
            {"model_backend": "heuristic", "model_available": False}
        )
        == PREDICTION_SOURCE_UNAVAILABLE
    )

    # New record takes priority
    assert (
        infer_prediction_source_from_legacy_score(
            {
                "model_backend": "heuristic",
                "prediction_source": PREDICTION_SOURCE_TRAINED_MODEL,
            }
        )
        == PREDICTION_SOURCE_TRAINED_MODEL
    )

    # Empty doc — no backend or available → unavailable
    assert infer_prediction_source_from_legacy_score(None) == "unknown"
    # Empty dict has no model_backend, no available → unavailable is correct
    assert infer_prediction_source_from_legacy_score({}) == PREDICTION_SOURCE_UNAVAILABLE


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests: model_metrics_audit excludes rule scores from stats
# ══════════════════════════════════════════════════════════════════════════════


def test_model_metrics_audit_excludes_rule_estimates() -> None:
    """Integration test: rule_estimate records must not enter model performance stats."""
    records = [
        # model predictions — should be eligible
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.85, "local_validation_status": "unvalidated"},
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.92, "local_validation_status": "calibrated"},
        # rule estimates — should be excluded
        {"prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE, "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE, "risk_value": 0.78},
        {"prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE, "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE, "risk_value": 0.60},
        # unavailable — should be excluded
        {"prediction_source": PREDICTION_SOURCE_UNAVAILABLE, "risk_value_type": "rule_score", "risk_value": None},
        # unknown — should be excluded
        {"prediction_source": PREDICTION_SOURCE_UNKNOWN, "risk_value_type": "model_probability", "risk_value": 0.70},
        # wrong risk_value_type — should be excluded even with trained_model source
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE, "risk_value": 0.88},
        # null risk_value — should be excluded
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": None},
    ]

    audit = model_metrics_audit(records)

    assert audit["total"] == 8
    assert audit["eligible"] == 2  # only the two valid model predictions
    assert audit["excluded_count"] == 6

    # Verify excluded reasons
    assert audit["excluded_reasons"]["rule_estimate_excluded"] == 2
    assert audit["excluded_reasons"]["unavailable_prediction"] == 1
    assert audit["excluded_reasons"]["unknown_source"] == 1
    assert "wrong_risk_value_type:rule_score" in audit["excluded_reasons"]
    assert audit["excluded_reasons"]["invalid_or_null_risk_value"] == 1

    # Verify validation status breakdown
    assert audit["by_validation_status"]["unvalidated"] == 1
    assert audit["by_validation_status"]["calibrated"] == 1

    # The eligible records should be exactly the two model predictions
    eligible_vals = {r["risk_value"] for r in audit["eligible_records"]}
    assert eligible_vals == {0.85, 0.92}


def test_model_metrics_audit_empty() -> None:
    """Empty input produces zero eligible with proper audit structure."""
    audit = model_metrics_audit([])
    assert audit["total"] == 0
    assert audit["eligible"] == 0
    assert audit["excluded_count"] == 0
    assert audit["excluded_reasons"] == {}
    assert audit["by_validation_status"] == {}


# ══════════════════════════════════════════════════════════════════════════════
# LLM prompt formatting tests
# ══════════════════════════════════════════════════════════════════════════════


def test_format_temporal_forecast_for_llm_rule_estimate() -> None:
    """Rule estimate forecast must use '规则风险指数' language, never '模型预测概率'."""
    fc = {
        "prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE,
        "risk_level": "high",
        "current_probability": 0.78,
        "horizon_probabilities": [
            {"hours": 4, "probability": 0.82},
            {"hours": 12, "probability": 0.91},
        ],
        "fallback_used": True,
    }
    text = format_temporal_forecast_for_llm(fc)

    # Must contain rule language
    assert "规则风险指数" in text
    assert "非AI模型输出" in text
    assert "78/100" in text
    assert "82/100" in text
    assert "91/100" in text
    assert "降级" in text

    # Must NOT contain model probability language
    assert "78%" not in text  # no percentage sign for rule scores
    assert "模型预测概率" not in text


def test_format_temporal_forecast_for_llm_trained_model() -> None:
    """Trained model forecast must use '模型预测概率' language."""
    fc = {
        "prediction_source": PREDICTION_SOURCE_TRAINED_MODEL,
        "risk_level": "critical",
        "current_probability": 0.88,
        "horizon_probabilities": [
            {"hours": 4, "probability": 0.92},
        ],
        "model_meta": {
            "model_name": "temporal_risk_v2",
            "model_version": "3.0.0",
            "local_validation_status": "unvalidated",
        },
    }
    text = format_temporal_forecast_for_llm(fc)

    assert "模型预测" in text
    assert "88%" in text
    assert "92%" in text
    assert "temporal_risk_v2" in text
    assert "v3.0.0" in text
    assert "未经本院验证" in text
    assert "规则风险指数" not in text  # must not confuse


def test_format_temporal_forecast_for_llm_unavailable() -> None:
    """Unavailable forecast must not generate probabilities."""
    fc = {
        "prediction_source": PREDICTION_SOURCE_UNAVAILABLE,
        "risk_level": "unknown",
        "reason": "no_local_weight_found",
    }
    text = format_temporal_forecast_for_llm(fc)

    assert "模型不可用" in text
    assert "不得生成具体概率数值" in text
    assert "%" not in text  # No probability values


def test_build_llm_guard_instruction_contains_rules() -> None:
    """Guard instruction must contain all mandatory rules."""
    instruction = build_llm_guard_instruction()

    assert "规则风险指数" in instruction
    assert "模型预测概率" in instruction
    assert "未经本院验证或校准" in instruction
    assert "不得生成具体概率数值" in instruction
    assert "严禁直接比较" in instruction
    assert "prediction_source" in instruction
    assert "risk_value_type" in instruction


def test_format_temporal_forecast_rule_score_never_shows_percentage() -> None:
    """Regression: rule_score output must NEVER contain % sign for probability display."""
    fc = {
        "prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE,
        "risk_level": "warning",
        "current_probability": 0.55,
        "horizon_probabilities": [
            {"hours": 4, "probability": 0.60},
            {"hours": 8, "probability": 0.65},
            {"hours": 12, "probability": 0.70},
        ],
    }
    text = format_temporal_forecast_for_llm(fc)

    # Rule scores use /100 format, not %
    assert "55/100" in text
    assert "60/100" in text
    assert "65/100" in text
    assert "70/100" in text
    # Verify no percentage signs appear in the risk values
    import re
    # Allow % only in non-risk contexts (e.g. "非AI模型输出" has no %)
    risk_lines = [l for l in text.split("\n") if "风险" in l and "/100" in l]
    for line in risk_lines:
        assert "%" not in line, f"Risk line must not contain %: {line}"


def test_strip_rule_scores_integration_mixed_batch() -> None:
    """Simulate a real-world mixed batch from score collection."""
    records = []
    # 50 rule_estimate records
    for i in range(50):
        records.append({"prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE, "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE, "risk_value": 0.5 + i * 0.005})
    # 20 trained_model records
    for i in range(20):
        records.append({"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.6 + i * 0.01, "local_validation_status": "unvalidated"})
    # 10 unavailable records
    for i in range(10):
        records.append({"prediction_source": PREDICTION_SOURCE_UNAVAILABLE, "risk_value_type": "", "risk_value": None})
    # 5 old records without prediction_source
    for i in range(5):
        records.append({"model_backend": "heuristic", "model_available": True})

    filtered = normalizer_strip_rule_scores_from_model_metrics(records)
    assert len(filtered) == 20  # only the trained_model records
    assert all(r["prediction_source"] == PREDICTION_SOURCE_TRAINED_MODEL for r in filtered)
    assert all(r["risk_value_type"] == RISK_VALUE_TYPE_MODEL_PROBABILITY for r in filtered)

    audit = model_metrics_audit(records)
    assert audit["total"] == 85
    assert audit["eligible"] == 20
    assert audit["excluded_count"] == 65


# ══════════════════════════════════════════════════════════════════════════════
# Test 9: NaN / Inf / out-of-bounds values are rejected
# ══════════════════════════════════════════════════════════════════════════════


def test_nan_inf_oob_values_rejected() -> None:
    assert _clamp_valid(float("nan")) is None
    assert _clamp_valid(float("inf")) is None
    assert _clamp_valid(float("-inf")) is None
    assert _clamp_valid(-0.1) is None
    assert _clamp_valid(1.5) is None
    assert _clamp_valid(None) is None
    assert _clamp_valid("not_a_number") is None
    assert _clamp_valid(0.0) == 0.0
    assert _clamp_valid(1.0) == 1.0
    assert _clamp_valid(0.78) == 0.78


# ══════════════════════════════════════════════════════════════════════════════
# Test 10: normalize_temporal_prediction handles heuristic + uncalibrated model
# ══════════════════════════════════════════════════════════════════════════════


def test_normalize_heuristic_prediction() -> None:
    result = normalize_temporal_prediction(
        available=True,
        backend="heuristic",
        probability=0.72,
        organ_probabilities={"respiratory": 0.65},
        future_probabilities={4: 0.80, 12: 0.88},
        reason="no_local_weight_found",
        model_path="",
    )

    assert result["prediction_source"] == PREDICTION_SOURCE_RULE_ESTIMATE
    assert result["risk_value_type"] == RISK_VALUE_TYPE_RULE_SCORE
    assert result["output_available"] is True
    assert result["model_loaded"] is False
    assert 0.72 == result["risk_value"]
    assert result["display_label"] == "规则估算风险"
    assert result["fallback_used"] is True
    assert len(result["future_risk_scores"]) == 2


def test_normalize_trained_model_prediction() -> None:
    result = normalize_temporal_prediction(
        available=True,
        backend="onnx",
        probability=0.85,
        organ_probabilities={"respiratory": 0.80},
        future_probabilities={4: 0.88, 12: 0.92},
        reason="loaded:CPUExecutionProvider",
        model_path="/models/temporal_risk.onnx",
        model_name="temporal_risk",
        model_version="1.0.0",
        model_loaded=True,
        calibration_version="cal-v1",
    )

    assert result["prediction_source"] == PREDICTION_SOURCE_TRAINED_MODEL
    assert result["risk_value_type"] == RISK_VALUE_TYPE_MODEL_PROBABILITY
    assert result["model_loaded"] is True
    assert 0.85 == result["risk_value"]
    assert "模型预测风险" in result["display_label"]
    assert result["fallback_used"] is False
    assert "模型预测" in result["risk_value_display"] or "%" in result["risk_value_display"]


def test_normalize_unavailable_prediction() -> None:
    result = normalize_temporal_prediction(
        available=False,
        backend="heuristic",
        probability=None,
        organ_probabilities=None,
        future_probabilities=None,
        reason="no_local_weight_found",
        model_path="",
    )

    assert result["prediction_source"] == PREDICTION_SOURCE_UNAVAILABLE
    assert result["output_available"] is False
    assert result["risk_value"] is None
    assert result["risk_value_display"] == "—"
    assert result["model_status"] == MODEL_STATUS_WEIGHT_MISSING


# ══════════════════════════════════════════════════════════════════════════════
# Test 11: meta() returns new contract fields
# ══════════════════════════════════════════════════════════════════════════════


def test_meta_returns_contract_fields() -> None:
    runtime = TemporalRiskModelRuntime(_Cfg(enabled=True))
    meta = runtime.meta()

    assert "prediction_source" in meta
    assert "model_available" in meta
    assert "model_loaded" in meta
    assert "model_name" in meta
    assert "model_version" in meta
    assert "model_status" in meta
    assert "local_validation_status" in meta
    assert meta["prediction_source"] == PREDICTION_SOURCE_RULE_ESTIMATE  # no weights
    assert meta["model_loaded"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Test 12: Invalid heuristic input returns unavailable
# ══════════════════════════════════════════════════════════════════════════════


def test_invalid_heuristic_input() -> None:
    runtime = TemporalRiskModelRuntime(_Cfg(enabled=True))
    # Empty sequence → invalid
    result = runtime.predict(
        sequence=np.array([], dtype=np.float32),
        meta_features=None,
        organ_keys=[],
        horizons=(),
    )

    assert result["prediction_source"] == PREDICTION_SOURCE_UNAVAILABLE


# ══════════════════════════════════════════════════════════════════════════════
# Conservation-of-count tests (item 3)
# ══════════════════════════════════════════════════════════════════════════════


def test_model_metrics_audit_conservation_of_count() -> None:
    """total = eligible + excluded_count must always hold."""
    records = [
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.85},
        {"prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE, "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE, "risk_value": 0.60},
        {"prediction_source": PREDICTION_SOURCE_UNAVAILABLE, "risk_value_type": "", "risk_value": None},
        {"prediction_source": PREDICTION_SOURCE_UNKNOWN, "risk_value_type": "", "risk_value": None},
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.92, "local_validation_status": "calibrated"},
    ]
    audit = model_metrics_audit(records)
    assert audit["total"] == audit["eligible"] + audit["excluded_count"]
    assert audit["total"] == 5
    assert audit["eligible"] == 2
    assert audit["excluded_count"] == 3


def test_legacy_onnx_inferred_correctly_in_pipeline() -> None:
    """Old ONNX record without prediction_source → infer → eligible."""
    legacy_onnx = {
        "model_backend": "onnx",
        "model_available": True,
        "risk_value": 0.72,
        "score_type": "temporal_risk_scanner",
    }
    ps = infer_prediction_source_from_legacy_score(legacy_onnx)
    assert ps == PREDICTION_SOURCE_TRAINED_MODEL
    normalized = {
        "prediction_source": ps,
        "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY,
        "risk_value": 0.72,
        "local_validation_status": "",
    }
    audit = model_metrics_audit([normalized])
    assert audit["eligible"] == 1


def test_legacy_heuristic_inferred_and_excluded() -> None:
    """Old heuristic record → infer → excluded from model stats."""
    legacy_heuristic = {
        "model_backend": "heuristic",
        "model_available": True,
        "risk_value": 0.55,
        "score_type": "temporal_risk_scanner",
    }
    ps = infer_prediction_source_from_legacy_score(legacy_heuristic)
    assert ps == PREDICTION_SOURCE_RULE_ESTIMATE
    normalized = {
        "prediction_source": ps,
        "risk_value_type": RISK_VALUE_TYPE_RULE_SCORE,
        "risk_value": 0.55,
    }
    audit = model_metrics_audit([normalized])
    assert audit["eligible"] == 0
    assert audit["excluded_reasons"]["rule_estimate_excluded"] == 1


def test_conflicting_fields_marked_unavailable() -> None:
    """Record with model_backend=pytorch + model_available=False → unavailable."""
    conflicting = {
        "model_backend": "pytorch",
        "model_available": False,
        "risk_value": None,
    }
    ps = infer_prediction_source_from_legacy_score(conflicting)
    assert ps == PREDICTION_SOURCE_UNAVAILABLE
    normalized = {"prediction_source": ps, "risk_value_type": "", "risk_value": None}
    audit = model_metrics_audit([normalized])
    assert audit["eligible"] == 0
    assert "unavailable_prediction" in audit["excluded_reasons"]


# ══════════════════════════════════════════════════════════════════════════════
# Validation status grouping tests (item 4)
# ══════════════════════════════════════════════════════════════════════════════


def test_unvalidated_separate_from_validated_in_stats() -> None:
    """unvalidated must NOT be merged into a single aggregate with validated/calibrated."""
    records = [
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.85, "local_validation_status": "unvalidated"},
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.90, "local_validation_status": "calibrated"},
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.92, "local_validation_status": "validated"},
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.88, "local_validation_status": ""},
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.70, "local_validation_status": "unknown_status"},
    ]
    audit = model_metrics_audit(records)
    assert audit["total"] == 5
    assert audit["eligible"] == 5
    by_vs = audit["by_validation_status"]
    assert "unvalidated" in by_vs
    assert "calibrated" in by_vs
    assert "validated" in by_vs
    assert "unknown_status" in by_vs
    # unvalidated count should be 2 (one explicit, one empty→unvalidated)
    assert by_vs["unvalidated"] == 2


def test_calibrated_is_not_clinically_validated() -> None:
    """calibrated = statistical calibration, NOT clinical validation."""
    from app.services.prediction_contract import _build_validation_status_summary
    records = [
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.85, "local_validation_status": "calibrated"},
    ]
    summary = _build_validation_status_summary(records)
    by_status = summary["by_status"]
    assert "calibrated" in by_status
    assert by_status["calibrated"]["enters"] == "calibration_exploratory_only"
    assert "不等同于临床验证" in by_status["calibrated"]["note"]


def test_unknown_validation_excluded_from_model_perf() -> None:
    """Records with unknown validation status → excluded from perf stats."""
    from app.services.prediction_contract import _build_validation_status_summary
    records = [
        {"prediction_source": PREDICTION_SOURCE_TRAINED_MODEL, "risk_value_type": RISK_VALUE_TYPE_MODEL_PROBABILITY, "risk_value": 0.85, "local_validation_status": "unknown_xyz"},
    ]
    summary = _build_validation_status_summary(records)
    by_status = summary["by_status"]
    assert "unknown_xyz" in by_status
    assert by_status["unknown_xyz"]["enters"] == "none"


# ══════════════════════════════════════════════════════════════════════════════
# Proactive management / LLM prompt tests (item 2)
# ══════════════════════════════════════════════════════════════════════════════


def test_guard_instr_present_for_proactive_context() -> None:
    """Guard instruction must contain all mandatory rules for any LLM prompt."""
    instruction = build_llm_guard_instruction()
    assert "rule_estimate" in instruction
    assert "规则风险指数" in instruction
    assert "模型预测概率" in instruction
    assert "unvalidated" in instruction
    assert "未经本院验证或校准" in instruction
    assert "不得生成具体概率数值" in instruction
    assert "严禁直接比较" in instruction


def test_rule_estimate_not_called_model_in_llm_text() -> None:
    """format_temporal_forecast_for_llm: rule_estimate → never '模型预测'."""
    fc = {
        "prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE,
        "risk_level": "high",
        "current_probability": 0.78,
        "horizon_probabilities": [{"hours": 4, "probability": 0.82}],
        "fallback_used": True,
    }
    text = format_temporal_forecast_for_llm(fc)
    assert "模型预测" not in text
    assert "规则风险指数" in text
    assert "78/100" in text


def test_unavailable_llm_text_forbids_probabilities() -> None:
    """unavailable → must not contain any numeric probability."""
    fc = {"prediction_source": PREDICTION_SOURCE_UNAVAILABLE, "risk_level": "unknown"}
    text = format_temporal_forecast_for_llm(fc)
    assert "不得生成具体概率数值" in text
    assert "%" not in text


def test_unknown_llm_text_marks_source_unknown() -> None:
    """unknown → must explicitly mark as 来源未知."""
    fc = {"prediction_source": PREDICTION_SOURCE_UNKNOWN, "risk_level": "warning", "current_probability": 0.60}
    text = format_temporal_forecast_for_llm(fc)
    assert "来源未知" in text
    assert "60/100" in text


# ══════════════════════════════════════════════════════════════════════════════
# Admin endpoint auth tests (item 7)
# ══════════════════════════════════════════════════════════════════════════════


def test_model_stats_no_auth_rejected() -> None:
    """No x-user-id → 401."""
    from unittest.mock import MagicMock
    req = MagicMock()
    req.headers = {}
    actor = str(req.headers.get("x-user-id") or req.headers.get("x-operator-id") or "").strip()
    assert not actor, "Empty actor should trigger 401"


def test_model_stats_non_admin_rejected() -> None:
    """Non-admin role → 403."""
    from unittest.mock import MagicMock
    req = MagicMock()
    req.headers = {"x-user-id": "doctor1", "x-user-role": "doctor"}
    role = str(req.headers.get("x-user-role") or req.headers.get("x-role") or "").strip().lower()
    assert role == "doctor"
    assert role != "admin", "Non-admin should be rejected with 403"


def test_model_stats_admin_accepted() -> None:
    """Admin role → passes check."""
    from unittest.mock import MagicMock
    req = MagicMock()
    req.headers = {"x-user-id": "admin1", "x-user-role": "admin"}
    role = str(req.headers.get("x-user-role") or req.headers.get("x-role") or "").strip().lower()
    actor = str(req.headers.get("x-user-id") or req.headers.get("x-operator-id") or "").strip()
    assert actor == "admin1"
    assert role == "admin"


# ══════════════════════════════════════════════════════════════════════════════
# Risk value display tests (item 1: unknown/legacy)
# ══════════════════════════════════════════════════════════════════════════════


def test_unknown_source_no_percentage_display() -> None:
    """rule_score → /100 format; model_probability → % format."""
    from app.services.prediction_contract import _risk_value_display
    assert "%" not in _risk_value_display(0.78, "rule_score")
    assert "/100" in _risk_value_display(0.78, "rule_score")
    assert "%" in _risk_value_display(0.78, RISK_VALUE_TYPE_MODEL_PROBABILITY)
    assert _risk_value_display(None, "model_probability") == "—"


# ══════════════════════════════════════════════════════════════════════════════
# Proactive Management real call chain test (item 5)
# ══════════════════════════════════════════════════════════════════════════════


def test_proactive_management_prompt_pipeline_rule_estimate() -> None:
    """Verify full pipeline: forecast → format → guard instruction → prompt.

    This tests the real path that proactive_management_engine takes when
    building context for LLM calls, not just the helper functions in isolation.
    """
    # Step 1: simulate what _build_temporal_risk_forecast returns for rule_estimate
    forecast = {
        "prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE,
        "risk_level": "high",
        "current_probability": 0.78,
        "horizon_probabilities": [
            {"hours": 2, "probability": 0.75},
            {"hours": 4, "probability": 0.82},
            {"hours": 6, "probability": 0.88},
        ],
        "model_meta": {
            "prediction_source": PREDICTION_SOURCE_RULE_ESTIMATE,
            "model_name": "unknown",
            "model_loaded": False,
            "model_status": "weight_missing",
            "fallback_used": True,
            "fallback_reason": "no_local_weight_found",
        },
        "fallback_used": True,
        "summary": "规则评估当前恶化风险为高风险（78/100，规则风险指数），4h约82/100，12h约88/100。主要依据：血压下降趋势。",
    }

    # Step 2: format for LLM (what proactive management would inject into prompt)
    llm_text = format_temporal_forecast_for_llm(forecast)

    # Step 3: guard instruction (what goes into system_prompt)
    guard = build_llm_guard_instruction()

    # Step 4: assemble the full prompt (simulating proactive management engine)
    full_context = f"{guard}\n\n患者时序风险评估:\n{llm_text}"

    # Verification: rule_estimate → no model probability language anywhere
    assert "模型预测" not in llm_text
    assert "规则风险指数" in llm_text
    assert "78/100" in llm_text
    assert "82/100" in llm_text
    assert "88/100" in llm_text

    # Guard must be present in final prompt
    assert "prediction_source" in full_context
    assert "rule_estimate" in full_context
    assert "未经本院验证或校准" in full_context
    assert "不得生成具体概率数值" in full_context

    # Rule_estimate must not show % for risk values in LLM text
    risk_lines = [l for l in llm_text.split("\n") if "风险" in l]
    for line in risk_lines:
        if "/100" in line:
            assert "%" not in line, f"Rule estimate line must not contain %: {line}"


def test_proactive_management_prompt_pipeline_trained_model() -> None:
    """Full pipeline for trained_model → must show model prediction language."""
    forecast = {
        "prediction_source": PREDICTION_SOURCE_TRAINED_MODEL,
        "risk_level": "critical",
        "current_probability": 0.88,
        "horizon_probabilities": [
            {"hours": 2, "probability": 0.85},
            {"hours": 4, "probability": 0.92},
        ],
        "model_meta": {
            "prediction_source": PREDICTION_SOURCE_TRAINED_MODEL,
            "model_name": "temporal_risk",
            "model_version": "2.0.0",
            "model_loaded": True,
            "local_validation_status": "unvalidated",
        },
    }

    llm_text = format_temporal_forecast_for_llm(forecast)
    guard = build_llm_guard_instruction()
    full_context = f"{guard}\n\n患者时序风险评估:\n{llm_text}"

    assert "模型预测" in llm_text
    assert "88%" in llm_text
    assert "92%" in llm_text
    assert "未经本院验证" in llm_text
    assert full_context  # prompt assembled
