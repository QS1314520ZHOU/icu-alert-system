from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.alert_engine.features.mdro_features import MDRO_FEATURE_SCHEMA_VERSION
from app.alert_engine.features.respiratory_features import RESPIRATORY_FEATURE_SCHEMA_VERSION
from app.services.local_model_paths import local_model_dir
from app.utils.serialization import serialize_doc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists() and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


async def respiratory_forecast_status(*, db: Any, config: Any, limit: int = 20) -> dict[str, Any]:
    model_dir = local_model_dir(config, "respiratory_forecast_dir", "respiratory-forecast")
    metadata = _read_json(model_dir / "metadata.json")
    candidates = ["respiratory_forecast.onnx", "respiratory_forecast.pt", "model.onnx", "model.pt", "model.pkl"]
    model_path = next((model_dir / name for name in candidates if (model_dir / name).exists()), None)
    cursor = db.col("research_artifacts").find(
        {"$or": [{"source": "respiratory_forecast"}, {"meta.topic": "respiratory_forecast"}]},
        {"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(limit, 100)))
    artifacts = [serialize_doc(doc) async for doc in cursor]
    performance = metadata.get("performance") if isinstance(metadata.get("performance"), dict) else {}
    return {
        "available": bool(model_path or metadata or artifacts),
        "maturity": "experimental",
        "generated_at": datetime.now(timezone.utc),
        "feature_schema_version": RESPIRATORY_FEATURE_SCHEMA_VERSION,
        "data_source": "mongo",
        "validation_status": str(metadata.get("validation_status") or "internal_only"),
        "model_meta": {
            "model_dir": str(model_dir),
            "model_path": str(model_path or ""),
            "metadata": metadata,
            "feature_schema_version": metadata.get("feature_schema_version") or RESPIRATORY_FEATURE_SCHEMA_VERSION,
        },
        "data_completeness": {
            "required": ["model_artifact_or_metadata", "performance_summary"],
            "present": [item for item, ok in [("model_artifact_or_metadata", bool(model_path or metadata)), ("performance_summary", bool(performance))] if ok],
            "missing": [item for item, ok in [("model_artifact_or_metadata", bool(model_path or metadata)), ("performance_summary", bool(performance))] if not ok],
            "completeness_ratio": round((int(bool(model_path or metadata)) + int(bool(performance))) / 2, 4),
        },
        "performance": performance,
        "shap": metadata.get("shap") if isinstance(metadata.get("shap"), (dict, list)) else {},
        "artifacts": artifacts,
        "unavailable_reason": "" if (model_path or metadata or artifacts) else f"no respiratory forecast artifact under {model_dir}",
    }


async def mdro_control_summary(*, db: Any, config: Any, limit: int = 20) -> dict[str, Any]:
    base_dir = local_model_dir(config, "mdro_control_dir", "mdro-control")
    metadata = _read_json(base_dir / "summary.json")
    cursor = db.col("research_artifacts").find(
        {"$or": [{"source": "mdro_control"}, {"meta.topic": "mdro_control"}]},
        {"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(limit, 100)))
    artifacts = [serialize_doc(doc) async for doc in cursor]
    analyses = metadata.get("analyses") if isinstance(metadata.get("analyses"), dict) else {}
    return {
        "available": bool(metadata or artifacts),
        "maturity": "experimental",
        "generated_at": datetime.now(timezone.utc),
        "feature_schema_version": MDRO_FEATURE_SCHEMA_VERSION,
        "data_source": "mongo",
        "validation_status": str(metadata.get("validation_status") or "internal_only"),
        "analysis_meta": {
            "analysis_dir": str(base_dir),
            "metadata": metadata,
            "feature_schema_version": metadata.get("feature_schema_version") or MDRO_FEATURE_SCHEMA_VERSION,
        },
        "data_completeness": {
            "required": ["retrospective_cohort", "transmission_network", "cost_effectiveness"],
            "present": [key for key in ("retrospective_cohort", "transmission_network", "cost_effectiveness") if key in analyses],
            "missing": [key for key in ("retrospective_cohort", "transmission_network", "cost_effectiveness") if key not in analyses],
            "completeness_ratio": round(sum(1 for key in ("retrospective_cohort", "transmission_network", "cost_effectiveness") if key in analyses) / 3, 4),
        },
        "analyses": analyses,
        "wgs": {
            "available": False,
            "reason": "requires external microbiology WGS data; not implemented in this phase",
        },
        "artifacts": artifacts,
        "unavailable_reason": "" if (metadata or artifacts) else f"no MDRO control artifact under {base_dir}",
    }
