"""Unified prediction contract normalizer.

Shared by TemporalRiskModelRuntime, VitalTrajectoryForecaster (Chronos),
and ICUFoundationModelService so every predictor uses the same
prediction_source / risk_value_type / local_validation_status semantics.

Rationale
---------
- ``prediction_source`` answers *who produced this number*.
- ``risk_value_type`` answers *what kind of number it is*.
- ``local_validation_status`` answers *whether it has been verified locally*.

These three dimensions are orthogonal and must not be conflated.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


# ── constants ────────────────────────────────────────────────────────────────

PREDICTION_SOURCE_RULE_ESTIMATE = "rule_estimate"
PREDICTION_SOURCE_TRAINED_MODEL = "trained_model"
PREDICTION_SOURCE_UNAVAILABLE = "unavailable"
PREDICTION_SOURCE_UNKNOWN = "unknown"

PREDICTION_SOURCES = frozenset(
    {
        PREDICTION_SOURCE_RULE_ESTIMATE,
        PREDICTION_SOURCE_TRAINED_MODEL,
        PREDICTION_SOURCE_UNAVAILABLE,
        PREDICTION_SOURCE_UNKNOWN,
    }
)

RISK_VALUE_TYPE_RULE_SCORE = "rule_score"
RISK_VALUE_TYPE_MODEL_PROBABILITY = "model_probability"

VALIDATION_NOT_APPLICABLE = "not_applicable"
VALIDATION_UNVALIDATED = "unvalidated"
VALIDATION_CALIBRATED = "calibrated"
VALIDATION_VALIDATED = "validated"

MODEL_STATUS_OK = "ok"
MODEL_STATUS_WEIGHT_MISSING = "weight_missing"
MODEL_STATUS_LOAD_FAILED = "load_failed"
MODEL_STATUS_INFERENCE_FAILED = "inference_failed"
MODEL_STATUS_INVALID_OUTPUT = "invalid_output"
MODEL_STATUS_DISABLED = "disabled"
MODEL_STATUS_TIMEOUT = "timeout"
MODEL_STATUS_UNKNOWN = "unknown"

# ── helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_finite_float(value: Any) -> bool:
    """Return True when *value* is a finite float in [0, 1]."""
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and 0.0 <= v <= 1.0


def _clamp_valid(value: Any) -> float | None:
    """Return a finite float in [0, 1] or None."""
    if not _is_finite_float(value):
        return None
    v = float(value)
    if math.isnan(v) or math.isinf(v):
        return None
    if v < 0.0 or v > 1.0:
        return None
    return v


def _clean_map(mapping: dict | None, *, key_type=str, value_type=float) -> dict:
    """Return a cleaned shallow copy with finite values only."""
    if not isinstance(mapping, dict):
        return {}
    out: dict = {}
    for k, v in mapping.items():
        try:
            vv = value_type(v)
        except (TypeError, ValueError):
            continue
        if isinstance(vv, float) and (math.isnan(vv) or math.isinf(vv)):
            continue
        out[key_type(k)] = vv
    return out


def _derive_model_name_version(
    *,
    model_path: str,
    configured_name: str | None = None,
    configured_version: str | None = None,
    config_version: str | None = None,
    calibration_version: str | None = None,
) -> tuple[str, str]:
    """Derive model_name / model_version from available metadata.

    Priority:
    1. Explicit config fields (model_name, model_version).
    2. File-name stem from model_path (e.g. "temporal_risk.onnx" → "temporal_risk").
    3. config_version or calibration_version as version hint.
    4. Fall back to "unknown".
    """
    import os

    name = (configured_name or "").strip()
    version = (configured_version or "").strip()

    if not name and model_path:
        try:
            stem = os.path.splitext(os.path.basename(model_path))[0]
            name = stem.strip() or ""
        except Exception:
            pass
    if not version:
        version = (calibration_version or config_version or "").strip()
    if not name:
        name = "unknown"
    if not version:
        version = "unknown"
    return name, version


# ── display helpers ──────────────────────────────────────────────────────────


def _display_label(prediction_source: str, risk_value_type: str) -> str:
    if prediction_source == PREDICTION_SOURCE_TRAINED_MODEL:
        return "模型预测风险"
    if prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE:
        return "规则估算风险"
    if prediction_source == PREDICTION_SOURCE_UNAVAILABLE:
        return "模型当前不可用"
    if prediction_source == PREDICTION_SOURCE_UNKNOWN:
        return "历史风险记录"
    return "风险预测"


def _safety_notice(
    prediction_source: str,
    risk_value_type: str,
    local_validation_status: str,
) -> str:
    if prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE:
        return "当前风险指数由临床规则计算，非AI模型预测，仅供临床参考"
    if prediction_source == PREDICTION_SOURCE_TRAINED_MODEL:
        if local_validation_status in (VALIDATION_UNVALIDATED,):
            return "该模型未经本院校准验证，预测概率需结合临床判断使用"
        return "模型预测结果仅供临床决策支持，不替代医生判断"
    if prediction_source == PREDICTION_SOURCE_UNAVAILABLE:
        return "AI模型当前不可用，系统无法提供模型预测"
    return "预测来源未知，请核实数据来源后使用"


def _risk_value_display(
    risk_value: float | None,
    risk_value_type: str,
) -> str:
    """Format risk_value for UI display.

    - model_probability: "78%" (percentage)
    - rule_score: "规则风险指数 78/100"
    - None / unavailable: "—"
    """
    if risk_value is None:
        return "—"
    if not _is_finite_float(risk_value):
        return "—"
    v = float(risk_value)
    if risk_value_type == RISK_VALUE_TYPE_MODEL_PROBABILITY:
        return f"{round(v * 100)}%"
    # rule_score or unknown
    return f"规则风险指数 {round(v * 100)}/100"


# ── normalizer ───────────────────────────────────────────────────────────────


def normalize_temporal_prediction(
    *,
    # raw output from the runtime / forecaster
    available: bool,
    backend: str,
    probability: float | None,
    organ_probabilities: dict | None,
    future_probabilities: dict | None,
    reason: str = "",
    model_path: str = "",
    device: str = "cpu",
    # model metadata
    model_name: str = "",
    model_version: str = "",
    configured_name: str | None = None,
    configured_version: str | None = None,
    config_version: str | None = None,
    calibration_version: str = "",
    local_validation_status: str = "",
    # extra context
    model_loaded: bool | None = None,
    fallback_used: bool = False,
    fallback_reason: str = "",
    model_status: str = "",
    limitations: list[str] | None = None,
    missing_features: list[str] | None = None,
    data_window: dict | None = None,
    # legacy compatibility
    legacy_result: dict | None = None,
) -> dict[str, Any]:
    """Normalize a temporal/Chronos prediction into the unified contract.

    Returns a dict suitable for API responses and score persistence.
    """

    # ── determine prediction_source ──────────────────────────────────────
    if not available:
        prediction_source = PREDICTION_SOURCE_UNAVAILABLE
    elif backend in ("onnx", "pytorch", "chronos") and model_loaded is not False:
        prediction_source = PREDICTION_SOURCE_TRAINED_MODEL
    elif backend == "heuristic":
        prediction_source = PREDICTION_SOURCE_RULE_ESTIMATE
    else:
        prediction_source = PREDICTION_SOURCE_UNKNOWN

    # ── determine risk_value and risk_value_type ─────────────────────────
    # unknown source: do NOT write the old value into risk_value.
    # preserve it in legacy_raw_value / legacy_raw_value_type instead.
    legacy_raw_value = None
    legacy_raw_value_type = None
    if prediction_source == PREDICTION_SOURCE_TRAINED_MODEL:
        risk_value_type = RISK_VALUE_TYPE_MODEL_PROBABILITY
        risk_value = _clamp_valid(probability)
    elif prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE:
        risk_value_type = RISK_VALUE_TYPE_RULE_SCORE
        risk_value = _clamp_valid(probability)
    elif prediction_source == PREDICTION_SOURCE_UNAVAILABLE:
        risk_value_type = None
        risk_value = None
    else:  # unknown
        risk_value_type = None
        legacy_raw_value = _clamp_valid(probability)
        legacy_raw_value_type = RISK_VALUE_TYPE_RULE_SCORE  # best guess from legacy
        risk_value = None

    # ── derive model_name / model_version ────────────────────────────────
    derived_name, derived_version = _derive_model_name_version(
        model_path=model_path,
        configured_name=configured_name or model_name or None,
        configured_version=configured_version or model_version or None,
        config_version=config_version,
        calibration_version=calibration_version,
    )
    if not model_name:
        model_name = derived_name
    if not model_version:
        model_version = derived_version

    # ── model_loaded ─────────────────────────────────────────────────────
    if model_loaded is None:
        model_loaded = prediction_source == PREDICTION_SOURCE_TRAINED_MODEL

    # ── model_status ─────────────────────────────────────────────────────
    if not model_status:
        if not available:
            model_status = _infer_unavailable_model_status(reason, fallback_reason)
        elif prediction_source == PREDICTION_SOURCE_TRAINED_MODEL:
            model_status = MODEL_STATUS_OK
        elif prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE:
            model_status = MODEL_STATUS_WEIGHT_MISSING
        elif prediction_source == PREDICTION_SOURCE_UNKNOWN:
            model_status = MODEL_STATUS_UNKNOWN
        else:
            model_status = MODEL_STATUS_DISABLED

    # ── local_validation_status ──────────────────────────────────────────
    if not local_validation_status:
        if prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE:
            local_validation_status = VALIDATION_NOT_APPLICABLE
        elif prediction_source == PREDICTION_SOURCE_TRAINED_MODEL:
            local_validation_status = calibration_version or VALIDATION_UNVALIDATED
            if local_validation_status not in (
                VALIDATION_UNVALIDATED,
                VALIDATION_CALIBRATED,
                VALIDATION_VALIDATED,
            ):
                local_validation_status = VALIDATION_UNVALIDATED
        else:
            local_validation_status = VALIDATION_NOT_APPLICABLE

    # ── limitations ──────────────────────────────────────────────────────
    if limitations is None:
        limitations = []
    if prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE:
        if "未接入本地模型权重，当前为启发式规则估算" not in limitations:
            limitations.insert(0, "未接入本地模型权重，当前为启发式规则估算")
    if prediction_source == PREDICTION_SOURCE_TRAINED_MODEL and local_validation_status == VALIDATION_UNVALIDATED:
        if "模型未经本院校准验证" not in limitations:
            limitations.append("模型未经本院校准验证")

    # ── fallback_used / fallback_reason ──────────────────────────────────
    if prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE and not fallback_used:
        fallback_used = True
    if not fallback_reason and fallback_used:
        fallback_reason = reason or ""

    # ── build normalized result ──────────────────────────────────────────
    display_label = _display_label(prediction_source, risk_value_type)
    safety_notice = _safety_notice(prediction_source, risk_value_type, local_validation_status)

    # Separate future_risk_scores (rule) from future_probabilities (model)
    future_risk_scores: dict[int, float] = {}
    future_probs_clean: dict[int, float] = {}
    if future_probabilities:
        cleaned = _clean_map(future_probabilities, key_type=int, value_type=float)
        if prediction_source == PREDICTION_SOURCE_RULE_ESTIMATE:
            future_risk_scores = cleaned
            future_probs_clean = {}  # rule scores don't get probability semantics
        else:
            future_probs_clean = cleaned
            future_risk_scores = {}

    organ_probs_clean: dict[str, float] = {}
    if organ_probabilities and prediction_source == PREDICTION_SOURCE_TRAINED_MODEL:
        organ_probs_clean = _clean_map(organ_probabilities, key_type=str, value_type=float)

    # ── validated evidence ────────────────────────────────────────────────
    validated_evidence = None
    if local_validation_status == VALIDATION_VALIDATED:
        validated_evidence = {
            "protocol_id": "",
            "report_id": "",
            "site": "",
            "population": "",
            "endpoint": "",
            "approved_by": "",
            "approved_at": "",
            "_note": "validated status requires these fields to be populated; empty values indicate unverified claims",
        }

    result: dict[str, Any] = {
        # ── new contract fields ──────────────────────────────────────
        "available": available,  # backward compat – overall output availability
        "output_available": available,
        "model_available": model_loaded,
        "model_loaded": model_loaded,
        "prediction_source": prediction_source,
        "backend": backend,
        "model_name": model_name,
        "model_version": model_version,
        "model_status": model_status,
        "local_validation_status": local_validation_status,
        "calibration_version": calibration_version or "",
        "validated_evidence": validated_evidence,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason or "",
        "risk_value": risk_value,
        "risk_value_type": risk_value_type,
        "risk_value_display": _risk_value_display(risk_value, risk_value_type),
        "future_risk_scores": future_risk_scores,
        "future_probabilities": future_probs_clean or (future_probabilities or {}),  # legacy compat
        "organ_probabilities": organ_probs_clean or (organ_probabilities or {}),
        "generated_at": _now_iso(),
        "data_window": data_window or {},
        "missing_features": missing_features or [],
        "limitations": limitations,
        "display_label": display_label,
        "safety_notice": safety_notice,
        "device": device,
        "model_path": model_path,
        "reason": reason,
    }

    # ── unknown source: preserve old value in legacy fields ────────────────
    if prediction_source == PREDICTION_SOURCE_UNKNOWN:
        result["legacy_raw_value"] = legacy_raw_value
        result["legacy_raw_value_type"] = legacy_raw_value_type

    # forward legacy probability field for backward compat
    if probability is not None and _is_finite_float(probability):
        result["probability"] = round(float(probability), 4)
    else:
        result["probability"] = None

    return result


def _infer_unavailable_model_status(reason: str, fallback_reason: str = "") -> str:
    """Infer model_status from reason string."""
    combined = f"{reason} {fallback_reason}".lower()
    if "no_local_weight" in combined or "no torch" in combined or "no safetensors" in combined:
        return MODEL_STATUS_WEIGHT_MISSING
    if "load_failed" in combined or "load failed" in combined:
        return MODEL_STATUS_LOAD_FAILED
    if "inference_failed" in combined or "invalid_model_output" in combined:
        return MODEL_STATUS_INFERENCE_FAILED
    if "invalid" in combined or "output" in combined:
        return MODEL_STATUS_INVALID_OUTPUT
    if "timeout" in combined:
        return MODEL_STATUS_TIMEOUT
    if "disabled" in combined:
        return MODEL_STATUS_DISABLED
    return MODEL_STATUS_WEIGHT_MISSING


def normalize_foundation_model_prediction(
    *,
    available: bool,
    provider: str = "",
    tasks: dict | None = None,
    reason: str = "",
    model_path: str = "",
    model_loaded: bool = False,
    model_status: str = "",
    fallback_used: bool = False,
    legacy_result: dict | None = None,
) -> dict[str, Any]:
    """Normalize a foundation-model zero_shot_predict result.

    Key rule: if the model is unavailable and the fallback produces
    fixed / empty-shell / simulated probabilities, the result MUST be
    marked ``prediction_source = "unavailable"`` with ``risk_value = null``.
    Only a genuine rule-based computation may be marked ``rule_estimate``.
    """

    if not available:
        prediction_source = PREDICTION_SOURCE_UNAVAILABLE
        risk_value_type = RISK_VALUE_TYPE_RULE_SCORE
        risk_value = None
        tasks_clean: dict[str, dict] = {}
        if tasks:
            for task_name, row in tasks.items():
                if isinstance(row, dict):
                    tasks_clean[str(task_name)] = {
                        "probability": None,
                        "risk_level": "unknown",
                    }
        return {
            "available": False,
            "output_available": False,
            "model_available": False,
            "model_loaded": False,
            "prediction_source": prediction_source,
            "backend": "torch",
            "model_name": "icu_foundation_model",
            "model_version": "unknown",
            "model_status": model_status or MODEL_STATUS_WEIGHT_MISSING,
            "local_validation_status": VALIDATION_NOT_APPLICABLE,
            "calibration_version": "",
            "fallback_used": False,
            "fallback_reason": reason or "",
            "risk_value": None,
            "risk_value_type": risk_value_type,
            "risk_value_display": "—",
            "future_risk_scores": {},
            "future_probabilities": {},
            "organ_probabilities": {},
            "generated_at": _now_iso(),
            "data_window": {},
            "missing_features": [],
            "limitations": ["ICU基础模型未加载，无法提供预测"],
            "display_label": "模型当前不可用",
            "safety_notice": "AI模型当前不可用，系统无法提供模型预测",
            "provider": provider,
            "tasks": tasks_clean,
        }

    # Model *is* available and actually produced output
    prediction_source = PREDICTION_SOURCE_TRAINED_MODEL
    risk_value_type = RISK_VALUE_TYPE_MODEL_PROBABILITY

    tasks_out: dict[str, dict] = {}
    first_prob: float | None = None
    if tasks:
        for task_name, row in tasks.items():
            if not isinstance(row, dict):
                continue
            prob = _clamp_valid(row.get("probability"))
            tasks_out[str(task_name)] = {
                "probability": round(float(prob), 4) if prob is not None else None,
                "risk_level": str(row.get("risk_level", "unknown")),
            }
            if prob is not None and first_prob is None:
                first_prob = prob

    return {
        "available": True,
        "output_available": True,
        "model_available": True,
        "model_loaded": True,
        "prediction_source": prediction_source,
        "backend": "torch",
        "model_name": "icu_foundation_model",
        "model_version": "unknown",
        "model_status": MODEL_STATUS_OK,
        "local_validation_status": VALIDATION_UNVALIDATED,
        "calibration_version": "",
        "fallback_used": False,
        "fallback_reason": "",
        "risk_value": first_prob,
        "risk_value_type": risk_value_type,
        "risk_value_display": _risk_value_display(first_prob, risk_value_type),
        "future_risk_scores": {},
        "future_probabilities": {},
        "organ_probabilities": {},
        "generated_at": _now_iso(),
        "data_window": {},
        "missing_features": [],
        "limitations": ["ICU基础模型未经本院校准验证"],
        "display_label": "模型预测风险",
        "safety_notice": "模型预测结果仅供临床决策支持，不替代医生判断",
        "provider": provider,
        "tasks": tasks_out,
    }


def normalizer_strip_rule_scores_from_model_metrics(
    records: list[dict],
) -> list[dict]:
    """Filter out rule_estimate records for model performance metrics.

    Use this before computing AUROC, AUPRC, calibration curves, or model drift.
    Only ``prediction_source == "trained_model"`` records should enter those stats.
    """
    return [
        r
        for r in records
        if r.get("prediction_source") == PREDICTION_SOURCE_TRAINED_MODEL
        and r.get("risk_value_type") == RISK_VALUE_TYPE_MODEL_PROBABILITY
        and _is_finite_float(r.get("risk_value"))
    ]


def model_metrics_audit(
    records: list[dict],
) -> dict[str, Any]:
    """Audit a batch of score/prediction records and return inclusion/exclusion stats.

    Returns:
        dict with:
        - ``total``: total records examined
        - ``eligible``: records qualifying for model performance metrics
        - ``excluded_count``: total excluded
        - ``excluded_reasons``: dict mapping reason labels → counts
        - ``by_validation_status``: breakdown of eligible records by local_validation_status
    """
    total = len(records)
    eligible = normalizer_strip_rule_scores_from_model_metrics(records)
    excluded_count = total - len(eligible)

    reasons: dict[str, int] = {}
    for r in records:
        if r in eligible:
            continue
        ps = str(r.get("prediction_source") or "unknown")
        rvt = str(r.get("risk_value_type") or "unknown")
        has_value = _is_finite_float(r.get("risk_value"))
        if ps == PREDICTION_SOURCE_RULE_ESTIMATE:
            reasons["rule_estimate_excluded"] = reasons.get("rule_estimate_excluded", 0) + 1
        elif ps == PREDICTION_SOURCE_UNAVAILABLE:
            reasons["unavailable_prediction"] = reasons.get("unavailable_prediction", 0) + 1
        elif ps == PREDICTION_SOURCE_UNKNOWN:
            reasons["unknown_source"] = reasons.get("unknown_source", 0) + 1
        elif rvt != RISK_VALUE_TYPE_MODEL_PROBABILITY:
            reasons[f"wrong_risk_value_type:{rvt}"] = reasons.get(f"wrong_risk_value_type:{rvt}", 0) + 1
        elif not has_value:
            reasons["invalid_or_null_risk_value"] = reasons.get("invalid_or_null_risk_value", 0) + 1
        else:
            reasons["other"] = reasons.get("other", 0) + 1

    by_validation: dict[str, int] = {}
    for r in eligible:
        vs = str(r.get("local_validation_status") or VALIDATION_UNVALIDATED)
        by_validation[vs] = by_validation.get(vs, 0) + 1

    return {
        "total": total,
        "eligible": len(eligible),
        "excluded_count": excluded_count,
        "excluded_reasons": dict(sorted(reasons.items(), key=lambda x: -x[1])),
        "by_validation_status": dict(sorted(by_validation.items())),
        "eligible_records": eligible,
    }


async def query_model_scores(
    db,
    *,
    score_type: str | None = None,
    since: Any = None,
    patient_id: str | None = None,
    limit: int = 5000,
    extra_query: dict | None = None,
) -> dict[str, Any]:
    """Query the ``score`` collection for model performance metrics.

    **Query order**: fetch all candidate records first → infer prediction_source
    for legacy docs → filter to trained_model + model_probability → audit.

    This ensures old ONNX/heuristic records without ``prediction_source``
    still pass through ``infer_prediction_source_from_legacy_score`` before
    filtering, rather than being silently excluded by a MongoDB query filter.
    """
    # ── Phase 1: fetch all candidate records (no prediction_source filter) ─
    query: dict[str, Any] = {}
    if score_type:
        query["score_type"] = score_type
    if patient_id:
        query["patient_id"] = str(patient_id)
    if since is not None:
        query["calc_time"] = {"$gte": since}
    if extra_query and isinstance(extra_query, dict):
        query.update(extra_query)

    cursor = db.col("score").find(query).sort("calc_time", -1).limit(limit)
    raw_records = [doc async for doc in cursor]

    # ── Phase 2: normalize / infer prediction_source for legacy docs ─────
    normalized: list[dict] = []
    for doc in raw_records:
        ps = doc.get("prediction_source")
        if ps not in PREDICTION_SOURCES:
            ps = infer_prediction_source_from_legacy_score(doc)
        rvt = doc.get("risk_value_type") or ""
        rv = doc.get("risk_value")
        # If the doc has risk_value but no risk_value_type, infer from prediction_source
        if not rvt and ps == PREDICTION_SOURCE_TRAINED_MODEL:
            rvt = RISK_VALUE_TYPE_MODEL_PROBABILITY
        elif not rvt and ps == PREDICTION_SOURCE_RULE_ESTIMATE:
            rvt = RISK_VALUE_TYPE_RULE_SCORE
        normalized.append({
            "prediction_source": ps,
            "risk_value_type": rvt,
            "risk_value": rv,
            "local_validation_status": doc.get("local_validation_status") or "",
            "_original": doc,
        })

    # ── Phase 3: filter → only trained_model + model_probability ─────────
    audit = model_metrics_audit(normalized)
    vs_summary = _build_validation_status_summary(audit["eligible_records"])
    vs_summary["total_candidates"] = audit["total"]
    vs_summary["excluded_from_technical_metrics"] = audit["excluded_count"]

    return {
        "records": [r["_original"] for r in audit["eligible_records"]],
        "audit": {
            "total_candidates": audit["total"],
            "eligible": audit["eligible"],
            "excluded_count": audit["excluded_count"],
            "excluded_reasons": audit["excluded_reasons"],
            "by_validation_status": audit["by_validation_status"],
            "stat_split": vs_summary,
        },
        "query_summary": {
            "score_type": score_type,
            "limit": limit,
            "query_order": "candidate → infer → filter → audit",
        },
    }


def _build_validation_status_summary(
    eligible_records: list[dict],
) -> dict[str, Any]:
    """Group eligible records by local_validation_status.

    Stat split (item 4):
    - technical_prediction_eligible: all trained_model records (includes unvalidated + calibrated + validated)
    - clinical_metrics_eligible: calibrated + validated only (has some verification evidence)
    - validated_metrics_eligible: validated only (has full clinical evidence)
    - unvalidated/calibrated must NOT be merged into validated aggregate
    - calibrated → exploratory stats only, NOT clinical validation
    """
    groups: dict[str, list[dict]] = {}
    for r in eligible_records:
        vs = str(r.get("local_validation_status") or VALIDATION_UNVALIDATED)
        groups.setdefault(vs, []).append(r)

    calibrated_count = len(groups.get(VALIDATION_CALIBRATED, []))
    validated_count = len(groups.get(VALIDATION_VALIDATED, []))
    unvalidated_count = len(groups.get(VALIDATION_UNVALIDATED, []))

    technical_eligible = len(eligible_records)
    clinical_eligible = calibrated_count + validated_count
    validated_eligible = validated_count

    by_status = {}
    for vs, recs in sorted(groups.items()):
        by_status[vs] = {"count": len(recs)}
        if vs == VALIDATION_CALIBRATED:
            by_status[vs]["enters"] = "calibration_exploratory_only"
            by_status[vs]["note"] = "统计校准已完成，可进入校准和探索性统计；不等同于临床验证，不得与 validated 合并为临床性能"
        elif vs == VALIDATION_VALIDATED:
            by_status[vs]["enters"] = "clinical_metrics"
            by_status[vs]["note"] = "已通过临床验证（需 protocol_id/report_id/site/population/endpoint/approved_by/approved_at 证据）"
            by_status[vs]["requires_evidence"] = ["protocol_id", "report_id", "site", "population", "endpoint", "approved_by", "approved_at"]
        elif vs == VALIDATION_UNVALIDATED:
            by_status[vs]["enters"] = "technical_only"
            by_status[vs]["note"] = "未经本院校准或验证，仅计入 technical_prediction_eligible，不计入临床指标"
        else:
            by_status[vs]["enters"] = "none"
            by_status[vs]["note"] = "未知验证状态，不计入任何模型性能统计"

    return {
        "total_candidates": -1,  # filled by caller
        "technical_prediction_eligible": technical_eligible,
        "clinical_metrics_eligible": clinical_eligible,
        "validated_metrics_eligible": validated_eligible,
        "excluded_from_technical_metrics": -1,  # filled by caller
        "excluded_from_clinical_metrics": (technical_eligible - clinical_eligible),
        "by_status": by_status,
    }


# ── LLM prompt formatting ────────────────────────────────────────────────────
# These helpers ensure that downstream LLM prompts always label prediction
# sources correctly, preventing heuristic scores from being called "model
# probabilities" in generated clinical text.

LLM_PROMPT_SOURCE_RULES = (
    "【风险预测来源标注规则，必须遵守】\n"
    "1. 当 prediction_source=\"rule_estimate\" 时，只能称为“规则风险指数”或“临床规则评估”，"
    "严禁称为“模型预测概率”“AI预测概率”“已验证预测概率”。\n"
    "2. 当 prediction_source=\"trained_model\" 时，才可称为“模型预测概率”。\n"
    "3. 当 local_validation_status=\"unvalidated\" 时，必须明确注明“该模型未经本院验证或校准”。\n"
    "4. 当 prediction_source=\"unavailable\" 时，不得生成具体概率数值。\n"
    "5. rule_score（规则风险指数）与 model_probability（模型预测概率）得分含义不同，"
    "严禁直接比较两者的数值大小。\n"
    "6. 引用未来时间窗（4/12/24小时）数值时，必须同时标注 prediction_source "
    "和 risk_value_type。\n"
    "7. current_probability 字段仅存在于 trained_model 预测中；"
    "current_risk_score 字段仅存在于 rule_estimate 预测中；"
    "两者语义不可互换，严禁将 rule_score 称为“概率”或填入 probability 字段。\n"
)


def format_temporal_forecast_for_llm(
    temporal_forecast: dict | None,
) -> str:
    """Format temporal forecast data for LLM prompt injection.

    Returns a plain-text description suitable for inclusion in a user prompt.
    """
    if not temporal_forecast or not isinstance(temporal_forecast, dict):
        return "时序恶化风险评估：数据不可用。\n"

    ps = str(temporal_forecast.get("prediction_source") or "unknown")
    risk_level = str(temporal_forecast.get("risk_level") or "unknown")
    # Unified extraction: trained_model -> current_probability; rule_estimate -> current_risk_score
    current_prob = (
        temporal_forecast.get("current_probability")
        or temporal_forecast.get("current_risk_score")
        or temporal_forecast.get("risk_value")
    )
    # Unified extraction: trained_model -> horizon_probabilities; rule_estimate -> future_risk_scores
    horizon_probs = (
        temporal_forecast.get("horizon_probabilities")
        or temporal_forecast.get("future_risk_scores")
        or []
    )
    model_meta = temporal_forecast.get("model_meta") or {}
    model_name = str(model_meta.get("model_name") or "")
    model_version = str(model_meta.get("model_version") or "")
    validation = str(model_meta.get("local_validation_status") or "")
    fallback_used = bool(temporal_forecast.get("fallback_used") or model_meta.get("fallback_used"))

    lines = []

    if ps == PREDICTION_SOURCE_TRAINED_MODEL:
        lines.append("【模型预测】（来源：已训练AI模型）")
        if model_name and model_name != "unknown":
            ver_str = f" v{model_version}" if model_version and model_version != "unknown" else ""
            lines.append(f"模型: {model_name}{ver_str}")
        if validation == VALIDATION_UNVALIDATED:
            lines.append("⚠ 该模型未经本院验证或校准，预测概率需结合临床判断。")
        lines.append(f"风险等级: {risk_level}")
        if current_prob is not None:
            lines.append(f"模型预测概率: {round(float(current_prob) * 100)}%")
        if horizon_probs:
            h_items = []
            for item in horizon_probs:
                if isinstance(item, dict):
                    h = item.get("hours") or item.get("offset_hours")
                    p = item.get("probability")
                    if h is not None and p is not None:
                        h_items.append(f"+{h}h {round(float(p) * 100)}%")
            if h_items:
                lines.append(f"未来预测概率: {', '.join(h_items)}")

    elif ps == PREDICTION_SOURCE_RULE_ESTIMATE:
        lines.append("【规则风险指数】（来源：临床启发式规则评估，非AI模型输出）")
        if fallback_used:
            lines.append("说明: AI模型未就绪，已降级为规则估算。")
        lines.append(f"风险等级: {risk_level}")
        if current_prob is not None:
            lines.append(f"规则风险指数: {round(float(current_prob) * 100)}/100")
        if horizon_probs:
            h_items = []
            for item in horizon_probs:
                if isinstance(item, dict):
                    h = item.get("hours") or item.get("offset_hours")
                    p = item.get("probability")
                    if h is not None and p is not None:
                        h_items.append(f"+{h}h {round(float(p) * 100)}/100")
            if h_items:
                lines.append(f"未来风险指数: {', '.join(h_items)}")

    elif ps == PREDICTION_SOURCE_UNAVAILABLE:
        lines.append("【模型不可用】（AI时序风险评估不可用）")
        reason = str(temporal_forecast.get("reason") or model_meta.get("reason") or "")
        if reason:
            lines.append(f"原因: {reason}")
        lines.append("注意: 不得生成具体概率数值。")

    else:
        lines.append("【风险评估】（预测来源未知）")
        lines.append(f"风险等级: {risk_level}")
        if current_prob is not None:
            lines.append(f"风险评分: {round(float(current_prob) * 100)}/100 (来源未知)")

    return "\n".join(lines) + "\n"


def build_llm_guard_instruction() -> str:
    """Return the system-prompt guard instruction for prediction source labeling.

    Insert this into the system prompt of any LLM call that may receive
    or generate temporal risk forecast text.
    """
    return LLM_PROMPT_SOURCE_RULES


def infer_prediction_source_from_legacy_score(doc: dict | None) -> str:
    """Infer prediction_source from an old score document that lacks the field."""
    if not isinstance(doc, dict):
        return PREDICTION_SOURCE_UNKNOWN

    # Check newer fields first
    ps = doc.get("prediction_source")
    if ps in PREDICTION_SOURCES:
        return str(ps)

    # Legacy inference
    backend = str(doc.get("model_backend") or doc.get("backend") or "").lower()
    available = bool(doc.get("model_available") or doc.get("available"))

    if backend in ("onnx", "pytorch", "chronos") and available:
        return PREDICTION_SOURCE_TRAINED_MODEL
    if not available:
        return PREDICTION_SOURCE_UNAVAILABLE
    if backend == "heuristic":
        return PREDICTION_SOURCE_RULE_ESTIMATE

    # Can't determine
    return PREDICTION_SOURCE_UNKNOWN
