"""Lazy local trajectory forecaster for ICU vitals."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.services.local_model_paths import local_model_dir
from app.services.runtime_config_service import DEFAULT_TRAJECTORY_FORECAST_CONFIG, TRAJECTORY_CODE_OPTIONS
from app.utils.serialization import serialize_doc


SUPPORTED_CODES = tuple(item["code"] for item in TRAJECTORY_CODE_OPTIONS)
DEFAULT_CONTINUOUS_CODES = tuple(DEFAULT_TRAJECTORY_FORECAST_CONFIG["default_codes"])
CODE_META = {item["code"]: item for item in TRAJECTORY_CODE_OPTIONS}
CODE_TO_PARAM_DEFAULTS = {
    "HR": ["param_HR", "param_PR"],
    "MAP": ["param_ibp_m", "param_nibp_m"],
    "SBP": ["param_ibp_s", "param_nibp_s"],
    "DBP": ["param_ibp_d", "param_nibp_d"],
    "SpO2": ["param_spo2", "param_SpO2"],
    "RR": ["param_resp", "param_RR"],
    "Temp": ["param_T", "param_temp"],
    "EtCO2": ["param_ETCO2", "param_etco2"],
    "CVP": ["param_cvp", "param_CVP"],
    "ICP": ["param_ICP", "param_icp"],
    "Lactate": ["lac", "lactate"],
}


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


class VitalTrajectoryForecaster:
    def __init__(self, *, db, config, alert_engine=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self._loaded = False
        self._torch: Any = None
        self._model: Any = None
        self._model_path: Path | None = None
        self._unavailable_reason = ""
        self._device = "cpu"
        self._backend = "torch"

    def _model_dir(self) -> Path:
        return local_model_dir(self.config, "chronos_dir", "chronos")

    async def _runtime_config(self) -> dict[str, Any]:
        cfg = dict(DEFAULT_TRAJECTORY_FORECAST_CONFIG)
        yaml_cfg = ((getattr(self.config, "yaml_cfg", {}) or {}).get("ai_service", {}) or {}).get("trajectory_forecast", {})
        if isinstance(yaml_cfg, dict):
            cfg.update(yaml_cfg)
        try:
            if self.db is not None:
                doc = await self.db.col("runtime_configs").find_one({"key": "trajectory_forecast"})
                if doc and isinstance(doc.get("value"), dict):
                    cfg.update(doc["value"])
        except Exception:
            pass
        return cfg

    def _param_codes(self, code: str) -> list[str]:
        root = getattr(self.config, "yaml_cfg", {}) if self.config is not None else {}
        vitals = root.get("vital_signs", {}) if isinstance(root, dict) else {}

        def _entry(section: str) -> str | None:
            row = vitals.get(section)
            if isinstance(row, dict):
                value = str(row.get("code") or "").strip()
                return value or None
            return None

        mapping = {
            "HR": [_entry("heart_rate"), _entry("pulse_rate")],
            "MAP": list(vitals.get("map_priority") or []) if isinstance(vitals.get("map_priority"), list) else [_entry("ibp_mean"), _entry("nibp_mean")],
            "SBP": list(vitals.get("sbp_priority") or []) if isinstance(vitals.get("sbp_priority"), list) else [_entry("ibp_systolic"), _entry("nibp_systolic")],
            "DBP": list(vitals.get("dbp_priority") or []) if isinstance(vitals.get("dbp_priority"), list) else [_entry("ibp_diastolic"), _entry("nibp_diastolic")],
            "SpO2": [_entry("spo2")],
            "RR": [_entry("resp_rate")],
            "Temp": [_entry("temperature")],
            "EtCO2": [_entry("etco2")],
            "CVP": [_entry("cvp")],
            "ICP": [_entry("icp")],
            "Lactate": CODE_TO_PARAM_DEFAULTS["Lactate"],
        }
        rows = [str(item).strip() for item in (mapping.get(code) or []) if str(item or "").strip()]
        return rows or CODE_TO_PARAM_DEFAULTS.get(code, [])

    def _candidate_paths(self) -> list[Path]:
        root = self._model_dir()
        return [root / name for name in ("model.safetensors", "pytorch_model.bin", "model.pt", "chronos.pt", "timesfm.pt", "model.pth")]

    def _chronos_torch_dtype(self) -> Any:
        if self._torch is None:
            return None
        try:
            if self._device != "cpu" and getattr(self._torch, "cuda", None) and self._torch.cuda.is_available():
                return self._torch.bfloat16
        except Exception:
            pass
        return self._torch.float32

    def _load_hf_pipeline(self, root: Path) -> bool:
        if not (root / "config.json").exists():
            return False
        try:
            from chronos import ChronosPipeline  # type: ignore

            self._model = ChronosPipeline.from_pretrained(str(root), device_map=self._device, torch_dtype=self._chronos_torch_dtype())
            self._model_path = root
            self._backend = "chronos"
            self._unavailable_reason = ""
            return True
        except Exception as exc:
            if isinstance(exc, ModuleNotFoundError):
                self._unavailable_reason = "chronos-forecasting unavailable: install chronos-forecasting package"
                return False
            self._model = None
            self._unavailable_reason = f"load failed: {exc.__class__.__name__}: {str(exc)[:120]}"
            return False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            import torch  # type: ignore
        except Exception as exc:
            self._unavailable_reason = f"torch unavailable: {exc.__class__.__name__}"
            return
        self._torch = torch
        root = self._model_dir()
        for path in self._candidate_paths():
            if not path.exists():
                continue
            if path.suffix == ".safetensors":
                if self._load_hf_pipeline(root):
                    return
                return
            try:
                self._model_path = path
                try:
                    self._model = torch.jit.load(str(path), map_location=self._device)
                except Exception:
                    self._model = torch.load(str(path), map_location=self._device)
                if hasattr(self._model, "eval"):
                    self._model.eval()
                self._unavailable_reason = ""
                return
            except Exception as exc:
                self._model = None
                self._unavailable_reason = f"load failed: {exc.__class__.__name__}: {str(exc)[:120]}"
                return
        if (root / "config.json").exists():
            self._load_hf_pipeline(root)
            return
        self._unavailable_reason = f"no torch or safetensors weight found under {self._model_dir()}"

    def status(self) -> dict[str, Any]:
        if not self._loaded:
            self._ensure_loaded()
        return {
            "available": bool(self._model is not None),
            "reason": self._unavailable_reason,
            "backend": self._backend,
            "model_path": str(self._model_path or ""),
            "supported_codes": list(SUPPORTED_CODES),
            "code_meta": CODE_META,
            "calibration_version": "",
        }

    async def _history(self, patient_id: str, code: str) -> list[dict[str, Any]]:
        from app.utils.patient_data import param_series_by_pid

        since = datetime.now() - timedelta(hours=24)
        points: list[dict[str, Any]] = []
        for param in self._param_codes(code):
            if code == "Lactate":
                continue
            rows = await param_series_by_pid(patient_id, param, since)
            points.extend(rows)
        points = sorted(points, key=lambda item: item.get("time") or datetime.min)
        return points[-48:]

    def _data_quality(self, code: str, points: list[dict[str, Any]]) -> dict[str, Any]:
        values = [_safe_float(row.get("value")) for row in points]
        values = [value for value in values if value is not None]
        if not values:
            return {"ok": False, "reason": "no_history"}
        meta = CODE_META.get(code, {})
        if meta.get("data_quality_gate"):
            ranges = {"CVP": (-5, 35), "ICP": (0, 60)}
            low, high = ranges.get(code, (-1e9, 1e9))
            valid = [value for value in values if low <= value <= high]
            if len(valid) < max(3, int(len(values) * 0.6)):
                return {"ok": False, "reason": "data_quality_gate_failed", "valid_points": len(valid), "total_points": len(values)}
            if len(valid) >= 4 and float(np.nanstd(valid[-6:])) < 0.01:
                return {"ok": False, "reason": "flat_or_disconnected_signal"}
        if meta.get("requires_context") and len(values) < 3:
            return {"ok": False, "reason": "context_signal_missing"}
        return {"ok": True, "reason": ""}

    def _fallback_forecast(self, points: list[dict[str, Any]], horizon_hours: int) -> list[dict[str, Any]]:
        values = [float(row.get("value")) for row in points if row.get("value") is not None]
        last = values[-1] if values else 0.0
        if len(values) >= 2:
            slope = (values[-1] - values[max(0, len(values) - 6)]) / max(1, min(6, len(values) - 1))
            spread = float(np.nanstd(values[-12:])) if len(values) >= 3 else max(abs(last) * 0.03, 1.0)
        else:
            slope = 0.0
            spread = max(abs(last) * 0.05, 1.0)
        now = datetime.now()
        rows = []
        for hour in range(1, horizon_hours + 1):
            mean = last + slope * hour
            width = max(spread * (1 + hour / 12), 0.5)
            rows.append({"time": serialize_doc(now + timedelta(hours=hour)), "mean": round(mean, 3), "lower": round(mean - 1.64 * width, 3), "upper": round(mean + 1.64 * width, 3)})
        return rows

    def threshold_risks(self, series: dict[str, Any], cfg: dict[str, Any], *, model_available: bool = True) -> list[dict[str, Any]]:
        if not model_available or not cfg.get("alert_enabled"):
            return []
        risks = []
        alert_codes = {str(code) for code in cfg.get("alert_codes") or []}
        for threshold in cfg.get("thresholds") or []:
            if not isinstance(threshold, dict):
                continue
            code = str(threshold.get("code") or "")
            if code not in alert_codes or code not in series:
                continue
            horizon = max(1, min(int(threshold.get("horizon_hours") or cfg.get("horizon_hours") or 6), 12))
            forecast_rows = (series.get(code) or {}).get("forecast") or []
            window = forecast_rows[:horizon]
            if not window:
                continue
            operator = str(threshold.get("operator") or "<")
            threshold_value = _safe_float(threshold.get("threshold"))
            trigger_probability = _safe_float(threshold.get("probability"))
            if threshold_value is None or trigger_probability is None:
                continue
            point_probs = []
            ci_low = None
            ci_high = None
            for row in window:
                mean = _safe_float(row.get("mean"))
                low = _safe_float(row.get("lower"))
                high = _safe_float(row.get("upper"))
                if mean is None or low is None or high is None:
                    continue
                width = max((high - low) / 3.28, 0.001)
                if operator in {"<", "<="}:
                    z = max(-60.0, min(60.0, (mean - threshold_value) / width))
                    prob = 1.0 / (1.0 + np.exp(z))
                else:
                    z = max(-60.0, min(60.0, (threshold_value - mean) / width))
                    prob = 1.0 / (1.0 + np.exp(z))
                point_probs.append(float(prob))
                ci_low = low if ci_low is None else min(ci_low, low)
                ci_high = high if ci_high is None else max(ci_high, high)
            if not point_probs:
                continue
            probability = max(point_probs)
            if probability >= trigger_probability:
                risks.append(
                    {
                        "code": code,
                        "label": CODE_META.get(code, {}).get("label", code),
                        "horizon_hours": horizon,
                        "operator": operator,
                        "threshold": threshold_value,
                        "probability": round(probability, 4),
                        "trigger_probability": trigger_probability,
                        "confidence_interval": {"level": 0.8, "low": ci_low, "high": ci_high},
                        "ci80": [ci_low, ci_high],
                        "severity": str(threshold.get("severity") or "warning"),
                    }
                )
        return sorted(risks, key=lambda row: row.get("probability", 0), reverse=True)

    def _model_forecast(self, values: list[float], horizon_hours: int) -> list[float] | None:
        if self._model is None or self._torch is None or not values:
            return None
        try:
            if self._backend == "chronos":
                context = self._torch.tensor(values[-48:], dtype=self._torch.float32).unsqueeze(0)
                forecast = self._model.predict(context, horizon_hours, num_samples=10)
                arr = forecast.detach().cpu().numpy() if hasattr(forecast, "detach") else np.asarray(forecast)
                median = np.quantile(arr[0], 0.5, axis=0)
                return [float(v) for v in np.asarray(median, dtype=float).reshape(-1)[:horizon_hours]]
            with self._torch.no_grad():
                tensor = self._torch.tensor(values[-48:], dtype=self._torch.float32).unsqueeze(0)
                if hasattr(self._model, "forecast"):
                    out = self._model.forecast(tensor, horizon_hours)
                else:
                    out = self._model(tensor)
                arr = out.detach().cpu().numpy().reshape(-1).astype(float)
                return [float(v) for v in arr[:horizon_hours]]
        except Exception:
            return None

    async def forecast(self, patient_id: str, codes: list[str] | None = None, horizon_hours: int = 6) -> dict[str, Any]:
        cfg = await self._runtime_config()
        horizon = max(1, min(int(horizon_hours or cfg.get("horizon_hours") or 6), 12))
        default_codes = cfg.get("default_codes") if isinstance(cfg.get("default_codes"), list) else list(DEFAULT_CONTINUOUS_CODES)
        requested = [str(code) for code in (codes or default_codes) if str(code) in SUPPORTED_CODES]
        if cfg.get("enabled") is False:
            return {
                "available": False,
                "reason": "trajectory forecast disabled by runtime config",
                "horizon_hours": horizon,
                "codes": requested or list(DEFAULT_CONTINUOUS_CODES),
                "series": {},
                "threshold_risks": [],
                "generated_at": serialize_doc(datetime.now()),
                "model_meta": {
                    "available": False,
                    "reason": "trajectory forecast disabled by runtime config",
                    "backend": "disabled",
                    "model_path": "",
                    "supported_codes": list(SUPPORTED_CODES),
                    "code_meta": CODE_META,
                    "calibration_version": str(cfg.get("calibration_version") or "uncalibrated-v1"),
                    "config_version": cfg.get("version"),
                },
            }
        self._ensure_loaded()
        status = self.status()
        if not requested:
            requested = list(DEFAULT_CONTINUOUS_CODES)
        series: dict[str, Any] = {}
        for code in requested:
            history = await self._history(patient_id, code)
            quality = self._data_quality(code, history)
            if not quality.get("ok") and code in {"CVP", "ICP"}:
                series[code] = {"history": serialize_doc(history[-24:]), "forecast": [], "available": False, "reason": quality.get("reason"), "series_type": CODE_META.get(code, {}).get("series_type")}
                continue
            values = [float(row.get("value")) for row in history if row.get("value") is not None]
            forecast_rows = None
            model_values = self._model_forecast(values, horizon) if status["available"] else None
            if model_values:
                base = self._fallback_forecast(history, horizon)
                for idx, value in enumerate(model_values):
                    width = max(abs(value) * 0.04, 1.0)
                    base[idx] = {"time": base[idx]["time"], "mean": round(value, 3), "lower": round(value - width, 3), "upper": round(value + width, 3)}
                forecast_rows = base
            else:
                forecast_rows = self._fallback_forecast(history, horizon)
            series[code] = {"history": serialize_doc(history[-24:]), "forecast": forecast_rows, "available": True, "series_type": CODE_META.get(code, {}).get("series_type"), "data_quality": quality}
        threshold_risks = self.threshold_risks(series, cfg, model_available=bool(status["available"]))
        generated_at = datetime.now()
        status = {**status, "calibration_version": str(cfg.get("calibration_version") or "uncalibrated-v1"), "config_version": cfg.get("version")}
        return {
            "available": bool(status["available"]),
            "reason": "" if status["available"] else status["reason"],
            "horizon_hours": horizon,
            "codes": requested,
            "series": series,
            "threshold_risks": threshold_risks,
            "generated_at": serialize_doc(generated_at),
            "model_meta": status,
        }

    async def drift(self, patient_id: str, code: str, horizon_hours: int = 6) -> dict[str, Any]:
        forecast = await self.forecast(patient_id, [code], horizon_hours)
        row = ((forecast.get("series") or {}).get(code) or {})
        history = row.get("history") or []
        predicted = row.get("forecast") or []
        if not history or not predicted:
            return {"available": forecast.get("available"), "drift": False, "code": code}
        latest = history[-1]
        actual = float(latest.get("value") or 0.0)
        band = predicted[0]
        drift = actual < float(band.get("lower") or actual) or actual > float(band.get("upper") or actual)
        return {"available": forecast.get("available"), "drift": drift, "code": code, "actual": actual, "expected": band, "model_meta": forecast.get("model_meta")}


_FORECASTER_SINGLETON: VitalTrajectoryForecaster | None = None


def get_vital_trajectory_forecaster(*, db=None, config=None, alert_engine=None) -> VitalTrajectoryForecaster:
    from app import runtime

    global _FORECASTER_SINGLETON
    db = db if db is not None else runtime.db
    config = config if config is not None else runtime.config
    alert_engine = alert_engine if alert_engine is not None else getattr(runtime, "alert_engine", None)
    if (
        _FORECASTER_SINGLETON is None
        or _FORECASTER_SINGLETON.db is not db
        or _FORECASTER_SINGLETON.config is not config
        or _FORECASTER_SINGLETON.alert_engine is not alert_engine
    ):
        _FORECASTER_SINGLETON = VitalTrajectoryForecaster(db=db, config=config, alert_engine=alert_engine)
    return _FORECASTER_SINGLETON
