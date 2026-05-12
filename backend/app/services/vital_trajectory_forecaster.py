"""Lazy local trajectory forecaster for ICU vitals."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.services.local_model_paths import local_model_dir
from app.utils.serialization import serialize_doc


SUPPORTED_CODES = ("HR", "MAP", "SpO2", "RR", "Temp", "Lactate")
CODE_TO_PARAM = {
    "HR": ["param_HR", "param_PR"],
    "MAP": ["param_ibp_m", "param_nibp_m"],
    "SpO2": ["param_spo2"],
    "RR": ["param_resp"],
    "Temp": ["param_T"],
    "Lactate": ["lac", "lactate"],
}


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

    def _candidate_paths(self) -> list[Path]:
        root = self._model_dir()
        return [root / name for name in ("model.pt", "chronos.pt", "timesfm.pt", "model.pth", "pytorch_model.bin", "model.safetensors")]

    def _load_hf_pipeline(self, root: Path) -> bool:
        if not (root / "config.json").exists():
            return False
        try:
            from chronos import ChronosPipeline  # type: ignore

            self._model = ChronosPipeline.from_pretrained(str(root), device_map=self._device)
            self._model_path = root
            self._backend = "chronos"
            self._unavailable_reason = ""
            return True
        except Exception as exc:
            chronos_error = f"{exc.__class__.__name__}: {str(exc)[:80]}"
        try:
            from transformers import pipeline  # type: ignore
        except Exception as exc:
            self._unavailable_reason = f"chronos/transformers unavailable for safetensors model: chronos={chronos_error}; transformers={exc.__class__.__name__}"
            return False
        try:
            self._model = pipeline("time-series-forecasting", model=str(root), device=-1)
            self._model_path = root
            self._backend = "transformers"
            self._unavailable_reason = ""
            return True
        except Exception as exc:
            self._model = None
            self._unavailable_reason = f"load failed: chronos={chronos_error}; transformers={exc.__class__.__name__}: {str(exc)[:80]}"
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
        }

    async def _history(self, patient_id: str, code: str) -> list[dict[str, Any]]:
        from app.utils.patient_data import param_series_by_pid

        since = datetime.now() - timedelta(hours=24)
        points: list[dict[str, Any]] = []
        for param in CODE_TO_PARAM.get(code, []):
            if code == "Lactate":
                continue
            rows = await param_series_by_pid(patient_id, param, since)
            points.extend(rows)
        points = sorted(points, key=lambda item: item.get("time") or datetime.min)
        return points[-48:]

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

    def _model_forecast(self, values: list[float], horizon_hours: int) -> list[float] | None:
        if self._model is None or self._torch is None or not values:
            return None
        try:
            if self._backend == "transformers":
                context = self._torch.tensor(values[-48:], dtype=self._torch.float32)
                out = self._model(context, prediction_length=horizon_hours)
                if isinstance(out, list) and out:
                    row = out[0]
                    if isinstance(row, dict):
                        raw = row.get("mean") or row.get("prediction") or row.get("samples")
                    else:
                        raw = row
                    arr = np.asarray(raw, dtype=float).reshape(-1)
                    return [float(v) for v in arr[:horizon_hours]]
            if self._backend == "chronos":
                context = self._torch.tensor(values[-48:], dtype=self._torch.float32)
                forecast = self._model.predict(context, horizon_hours)
                arr = forecast.detach().cpu().numpy() if hasattr(forecast, "detach") else np.asarray(forecast)
                if arr.ndim >= 3:
                    arr = np.quantile(arr[0], 0.5, axis=0)
                else:
                    arr = arr.reshape(-1)
                return [float(v) for v in arr[:horizon_hours]]
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
        horizon = max(1, min(int(horizon_hours or 6), 12))
        requested = [str(code) for code in (codes or ["HR", "MAP", "SpO2", "RR"]) if str(code) in SUPPORTED_CODES]
        self._ensure_loaded()
        status = self.status()
        if not requested:
            requested = ["HR", "MAP", "SpO2", "RR"]
        series: dict[str, Any] = {}
        for code in requested:
            history = await self._history(patient_id, code)
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
            series[code] = {"history": serialize_doc(history[-24:]), "forecast": forecast_rows}
        return {
            "available": bool(status["available"]),
            "reason": "" if status["available"] else status["reason"],
            "horizon_hours": horizon,
            "codes": requested,
            "series": series,
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
