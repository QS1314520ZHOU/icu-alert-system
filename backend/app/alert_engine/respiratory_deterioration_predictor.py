from __future__ import annotations

from datetime import datetime
from typing import Any

from app.alert_engine.features.respiratory_features import RESPIRATORY_FEATURE_SCHEMA_VERSION, build_respiratory_forecast_features
from app.data_adapters.mongo_adapter import MongoClinicalDataAdapter
from app.services.local_model_paths import local_model_dir
from app.utils.parse import _safe_oid
from app.utils.serialization import serialize_doc


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


class RespiratoryDeteriorationPredictorMixin:
    def _resp_deterioration_cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("respiratory_deterioration", {})
        return cfg if isinstance(cfg, dict) else {}

    def _resp_forecast_model_meta(self) -> dict[str, Any]:
        cfg = self._resp_deterioration_cfg()
        model_dir = local_model_dir(self.config, "respiratory_forecast_dir", "respiratory-forecast")
        candidate_names = cfg.get("candidate_model_files") or [
            "respiratory_forecast.onnx",
            "respiratory_forecast.pt",
            "model.onnx",
            "model.pt",
            "model.pkl",
        ]
        candidates = [model_dir / str(name) for name in candidate_names if str(name or "").strip()]
        model_path = next((path for path in candidates if path.exists() and path.is_file()), None)
        meta_path = model_dir / "metadata.json"
        return {
            "available": bool(model_path),
            "model_dir": str(model_dir),
            "model_path": str(model_path or ""),
            "metadata_path": str(meta_path) if meta_path.exists() else "",
            "backend": "artifact" if model_path else "unavailable",
            "reason": "" if model_path else f"no model artifact under {model_dir}",
        }

    async def build_respiratory_deterioration_forecast(self, patient_doc: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now()
        cfg = self._resp_deterioration_cfg()
        sf_warning = float(cfg.get("sf_warning_threshold", 235) or 235)
        sf_high = float(cfg.get("sf_high_threshold", 190) or 190)
        sf_drop_warning = float(cfg.get("sf_drop_warning", 30) or 30)
        sf_drop_high = float(cfg.get("sf_drop_high", 60) or 60)
        horizon_hours = int(cfg.get("horizon_hours", 6) or 6)
        history_hours = int(cfg.get("history_hours", 12) or 12)
        adapter = MongoClinicalDataAdapter(db=self.db, engine=self)
        feature_bundle = await build_respiratory_forecast_features(adapter, patient_doc, now=now, cfg=cfg)
        features = feature_bundle.get("feature_vector") or {}
        paired = feature_bundle.get("series") or []
        data_completeness = feature_bundle.get("data_completeness") or {}
        model_meta = self._resp_forecast_model_meta()
        model_meta["feature_schema_version"] = RESPIRATORY_FEATURE_SCHEMA_VERSION
        model_meta["data_source"] = feature_bundle.get("data_source") or "mongo"
        model_meta["validation_status"] = "internal_only"
        base = {
            "available": False,
            "maturity": "experimental",
            "generated_at": now,
            "patient_id": str(patient_doc.get("_id") or ""),
            "feature_schema_version": RESPIRATORY_FEATURE_SCHEMA_VERSION,
            "data_source": feature_bundle.get("data_source") or "mongo",
            "validation_status": "internal_only",
            "data_completeness": data_completeness,
            "model_meta": model_meta,
            "evidence": [],
            "features": {},
            "forecast": {},
            "unavailable_reason": "",
        }
        if not features:
            base["unavailable_reason"] = "insufficient paired SpO2/FiO2 data"
            return serialize_doc(base)
        if not model_meta.get("available"):
            base.update(
                {
                    "features": {
                        **features,
                        "feature_schema_version": RESPIRATORY_FEATURE_SCHEMA_VERSION,
                        "data_source": feature_bundle.get("data_source") or "mongo",
                        "validation_status": "internal_only",
                    },
                    "series": serialize_doc(paired[-24:]),
                    "unavailable_reason": model_meta.get("reason") or "respiratory forecast model artifact unavailable",
                }
            )
            return serialize_doc(base)

        latest_sf = float(features.get("latest_sf_ratio") or 0)
        baseline_sf = float(features.get("baseline_sf_ratio") or latest_sf)
        drop = float(features.get("sf_drop") or 0)
        slope_per_hour = float(features.get("sf_slope_per_hour") or 0)
        projected_sf = round(latest_sf + slope_per_hour * horizon_hours, 1)
        severity = None
        if latest_sf <= sf_high or drop >= sf_drop_high or projected_sf <= sf_high:
            severity = "high"
        elif latest_sf <= sf_warning or drop >= sf_drop_warning or projected_sf <= sf_warning:
            severity = "warning"

        evidence = [
            f"Latest S/F ratio {latest_sf:.1f}",
            f"Baseline S/F ratio {baseline_sf:.1f}",
            f"Change over {history_hours}h window {drop:.1f}",
            f"Projected {horizon_hours}h S/F ratio {projected_sf:.1f}",
        ]
        result = {
            **base,
            "available": True,
            "severity": severity or "none",
            "risk_level": severity or "none",
            "data_completeness": data_completeness,
            "evidence": evidence,
            "features": {
                **features,
                "feature_schema_version": RESPIRATORY_FEATURE_SCHEMA_VERSION,
                "data_source": feature_bundle.get("data_source") or "mongo",
                "validation_status": "internal_only",
            },
            "forecast": {
                "horizon_hours": horizon_hours,
                "projected_sf_ratio": projected_sf,
                "source": "heuristic_trend_with_model_artifact_gate",
            },
            "series": serialize_doc(paired[-24:]),
            "thresholds": {
                "sf_warning_threshold": sf_warning,
                "sf_high_threshold": sf_high,
                "sf_drop_warning": sf_drop_warning,
                "sf_drop_high": sf_drop_high,
            },
            "unavailable_reason": "" if model_meta.get("available") else model_meta.get("reason", ""),
        }
        return serialize_doc(result)

    async def latest_respiratory_deterioration_forecast(self, patient_id: str) -> dict[str, Any]:
        patient = await self.db.col("patient").find_one({"_id": _safe_oid(patient_id) or patient_id})
        if not patient:
            return {"available": False, "maturity": "experimental", "unavailable_reason": "patient not found"}
        latest = await self.db.col("score").find_one(
            {"patient_id": str(patient.get("_id")), "score_type": "respiratory_deterioration_forecast"},
            sort=[("calc_time", -1)],
        )
        if latest:
            doc = serialize_doc(latest)
            doc.setdefault("available", True)
            doc.setdefault("maturity", "experimental")
            return doc
        return await self.build_respiratory_deterioration_forecast(patient)

    async def persist_respiratory_deterioration_forecast(self, patient_doc: dict[str, Any], forecast: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now()
        doc = {
            "patient_id": str(patient_doc.get("_id") or ""),
            "score_type": "respiratory_deterioration_forecast",
            "calc_time": now,
            "available": bool(forecast.get("available")),
            "maturity": "experimental",
            "severity": forecast.get("severity") or forecast.get("risk_level"),
            "features": forecast.get("features") or {},
            "forecast": forecast.get("forecast") or {},
            "evidence": forecast.get("evidence") or [],
            "data_completeness": forecast.get("data_completeness") or {},
            "model_meta": forecast.get("model_meta") or {},
            "unavailable_reason": forecast.get("unavailable_reason") or "",
            "series": forecast.get("series") or [],
            "thresholds": forecast.get("thresholds") or {},
            "created_at": now,
            "updated_at": now,
        }
        await self.db.col("score").insert_one(doc)
        return serialize_doc(doc)
