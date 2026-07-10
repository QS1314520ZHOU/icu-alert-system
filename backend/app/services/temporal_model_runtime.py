from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from app.utils.ai_acceleration import onnx_providers, torch_device_name
from app.utils.runtime_paths import model_search_roots

logger = logging.getLogger("icu-alert")


class TemporalRiskModelRuntime:
    def __init__(self, config) -> None:
        self.config = config
        self._loaded = False
        self._backend = "heuristic"
        self._model = None
        self._model_path = ""
        self._mtime = 0.0
        self._reason = "uninitialized"
        self._input_names: list[str] = []
        self._output_names: list[str] = []
        self._device = "cpu"

    def _cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("ai_service", {}).get("temporal_model", {})
        return cfg if isinstance(cfg, dict) else {}

    def _heuristic_enabled(self) -> bool:
        cfg = self._cfg()
        value = cfg.get("heuristic_fallback_enabled", True)
        return bool(value)

    def _discover_candidates(self) -> list[Path]:
        cfg = self._cfg()
        root = model_search_roots()[0].parent
        configured = str(cfg.get("model_path") or "").strip()
        candidates: list[Path] = []
        if configured:
            p = Path(configured)
            if not p.is_absolute():
                p = root / configured
            candidates.append(p)
        search_dirs = model_search_roots()
        search_names = cfg.get(
            "candidate_names",
            [
                "temporal_risk.onnx",
                "temporal_risk.pt",
                "temporal_risk.pth",
                "temporal_risk_model.onnx",
                "temporal_risk_model.pt",
            ],
        )
        for folder in search_dirs:
            for name in search_names if isinstance(search_names, list) else []:
                candidates.append(folder / str(name))
        dedup: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            dedup.append(path)
        return dedup

    def _ensure_loaded(self) -> None:
        candidates = self._discover_candidates()
        model_path = next((p for p in candidates if p.exists() and p.is_file()), None)
        if model_path is None:
            self._loaded = True
            self._backend = "heuristic"
            self._model = None
            self._model_path = ""
            self._device = "cpu"
            self._reason = "no_local_weight_found"
            return

        try:
            mtime = model_path.stat().st_mtime
        except Exception:
            mtime = 0.0
        if self._loaded and self._model_path == str(model_path) and self._mtime == mtime:
            return

        self._model = None
        self._input_names = []
        self._output_names = []
        suffix = model_path.suffix.lower()
        try:
            if suffix == ".onnx":
                import onnxruntime as ort  # type: ignore

                providers = onnx_providers()
                session = ort.InferenceSession(str(model_path), providers=providers)
                self._model = session
                self._backend = "onnx"
                self._input_names = [x.name for x in session.get_inputs()]
                self._output_names = [x.name for x in session.get_outputs()]
                self._device = "cuda" if providers and providers[0] == "CUDAExecutionProvider" else "cpu"
                self._reason = f"loaded:{','.join(providers)}"
            elif suffix in {".pt", ".pth", ".ckpt"}:
                import torch  # type: ignore

                device_name = torch_device_name()
                map_location = torch.device(device_name)
                loaded = None
                try:
                    loaded = torch.jit.load(str(model_path), map_location=map_location)
                except Exception:
                    loaded = torch.load(str(model_path), map_location=map_location)
                if hasattr(loaded, "to"):
                    loaded = loaded.to(map_location)
                if hasattr(loaded, "eval"):
                    loaded.eval()
                self._model = loaded
                self._backend = "pytorch"
                self._device = device_name
                self._reason = f"loaded:{device_name}"
            else:
                self._backend = "heuristic"
                self._reason = f"unsupported_weight_format:{suffix or 'unknown'}"
                self._model = None
                self._device = "cpu"
            self._model_path = str(model_path)
            self._mtime = mtime
            self._loaded = True
        except Exception as e:
            self._backend = "heuristic"
            self._model = None
            self._model_path = str(model_path)
            self._mtime = mtime
            self._loaded = True
            self._device = "cpu"
            self._reason = f"load_failed:{type(e).__name__}:{str(e)[:120]}"
            logger.warning("时序模型加载失败: %s", self._reason)

    def _prepare_onnx_inputs(self, sequence: np.ndarray, meta_features: np.ndarray | None) -> dict[str, np.ndarray]:
        session = self._model
        feeds: dict[str, np.ndarray] = {}
        inputs = session.get_inputs() if session is not None else []
        seq = sequence.astype(np.float32)
        if seq.ndim == 2:
            seq3 = seq[None, ...]
        elif seq.ndim == 3:
            seq3 = seq
        else:
            seq3 = seq.reshape(1, -1, 1)
        seq2 = seq.reshape(1, -1)
        meta2 = None
        if meta_features is not None:
            meta = meta_features.astype(np.float32)
            meta2 = meta if meta.ndim == 2 else meta.reshape(1, -1)
        for idx, input_meta in enumerate(inputs):
            shape = getattr(input_meta, "shape", None) or []
            rank = len(shape)
            name = input_meta.name
            if idx == 0:
                feeds[name] = seq3 if rank >= 3 else seq2
            elif meta2 is not None:
                feeds[name] = meta2
            else:
                feeds[name] = seq2
        return feeds

    def _prepare_torch_inputs(self, sequence: np.ndarray, meta_features: np.ndarray | None):
        import torch  # type: ignore

        device = torch.device(self._device if self._device == "cuda" and torch.cuda.is_available() else "cpu")
        seq_arr = sequence.astype(np.float32)
        if seq_arr.ndim == 2:
            seq = torch.tensor(seq_arr, device=device).unsqueeze(0)
        elif seq_arr.ndim == 3:
            seq = torch.tensor(seq_arr, device=device)
        else:
            seq = torch.tensor(seq_arr.reshape(1, -1, 1), device=device)
        meta = None
        if meta_features is not None:
            meta_arr = meta_features.astype(np.float32)
            meta = torch.tensor(meta_arr if meta_arr.ndim == 2 else meta_arr.reshape(1, -1), device=device)
        return seq, meta

    def _to_numpy(self, obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, np.ndarray):
            return obj
        if isinstance(obj, (list, tuple)):
            return [self._to_numpy(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self._to_numpy(v) for k, v in obj.items()}
        try:
            import torch  # type: ignore

            if isinstance(obj, torch.Tensor):
                return obj.detach().cpu().numpy()
        except Exception:
            pass
        return obj

    def _parse_probability_output(
        self,
        output: Any,
        *,
        organ_keys: list[str],
        horizons: tuple[int, ...],
    ) -> dict[str, Any] | None:
        output = self._to_numpy(output)
        if isinstance(output, dict):
            prob = output.get("probability")
            organ_probs = output.get("organ_probabilities") if isinstance(output.get("organ_probabilities"), dict) else {}
            horizon_probs = output.get("horizon_probabilities") if isinstance(output.get("horizon_probabilities"), dict) else {}
            if prob is not None:
                return {
                    "probability": float(prob),
                    "organ_probabilities": {str(k): float(v) for k, v in organ_probs.items() if v is not None},
                    "future_probabilities": {int(k): float(v) for k, v in horizon_probs.items() if v is not None},
                }
            return None

        arr = np.asarray(output, dtype=np.float32).reshape(-1)
        if arr.size == 0:
            return None
        probability = float(arr[0])
        cursor = 1
        organ_probabilities: dict[str, float] = {}
        for key in organ_keys:
            if cursor >= arr.size:
                break
            organ_probabilities[key] = float(arr[cursor])
            cursor += 1
        future_probabilities: dict[int, float] = {}
        for hour in horizons:
            if cursor >= arr.size:
                break
            future_probabilities[int(hour)] = float(arr[cursor])
            cursor += 1
        return {
            "probability": probability,
            "organ_probabilities": organ_probabilities,
            "future_probabilities": future_probabilities,
        }

    def _heuristic_predict(
        self,
        *,
        sequence: np.ndarray,
        meta_features: np.ndarray | None,
        organ_keys: list[str],
        horizons: tuple[int, ...],
    ) -> dict[str, Any]:
        seq = np.asarray(sequence, dtype=np.float32)
        if seq.ndim == 3:
            seq = seq[0]
        elif seq.ndim == 1:
            seq = seq.reshape(-1, 1)
        if seq.ndim != 2 or seq.size == 0:
            return {
                "available": False,
                "backend": "heuristic",
                "device": "cpu",
                "model_path": "",
                "reason": "invalid_heuristic_input",
            }

        latest = seq[-1]
        reference = seq[max(0, len(seq) - min(4, len(seq)))]
        latest_meta = None
        if meta_features is not None:
            meta = np.asarray(meta_features, dtype=np.float32)
            latest_meta = meta.reshape(-1) if meta.size else None

        def _col(index: int, default: float) -> float:
            if index < latest.shape[0]:
                return float(latest[index])
            return float(default)

        def _delta(index: int) -> float:
            if index < latest.shape[0] and index < reference.shape[0]:
                return float(latest[index] - reference[index])
            return 0.0

        hr = _col(0, 88.0)
        map_value = _col(1, 75.0)
        spo2 = _col(2, 97.0)
        rr = _col(3, 19.0)
        temp = _col(4, 36.8)

        age = float(latest_meta[0]) if latest_meta is not None and latest_meta.size >= 1 else 65.0
        on_vent = float(latest_meta[3]) if latest_meta is not None and latest_meta.size >= 4 else 0.0
        sofa = float(latest_meta[4]) if latest_meta is not None and latest_meta.size >= 5 else 5.0
        lactate = float(latest_meta[5]) if latest_meta is not None and latest_meta.size >= 6 else 1.6

        map_drop = -_delta(1)
        spo2_drop = -_delta(2)
        rr_rise = _delta(3)
        hr_rise = _delta(0)
        temp_rise = _delta(4)

        circulatory_score = (
            max(0.0, (65.0 - map_value) / 12.0) * 1.4 +
            max(0.0, (lactate - 2.0) / 2.5) * 1.1 +
            max(0.0, map_drop / 8.0) * 0.8 +
            max(0.0, (hr - 110.0) / 25.0) * 0.35
        )
        respiratory_score = (
            max(0.0, (93.0 - spo2) / 5.0) * 1.2 +
            max(0.0, (rr - 24.0) / 8.0) * 0.6 +
            max(0.0, spo2_drop / 3.0) * 0.8 +
            max(0.0, on_vent) * 0.35
        )
        renal_score = (
            max(0.0, (lactate - 2.2) / 3.0) * 0.35 +
            max(0.0, (sofa - 6.0) / 4.0) * 0.75 +
            max(0.0, (age - 75.0) / 15.0) * 0.15
        )
        neurologic_score = (
            max(0.0, (sofa - 7.0) / 4.0) * 0.55 +
            max(0.0, (temp - 38.2) / 1.2) * 0.15 +
            max(0.0, (35.8 - temp) / 1.0) * 0.2 +
            max(0.0, hr_rise / 18.0) * 0.15
        )

        global_logit = (
            circulatory_score * 0.42 +
            respiratory_score * 0.34 +
            renal_score * 0.16 +
            neurologic_score * 0.08 +
            max(0.0, temp_rise / 0.8) * 0.08 -
            1.55
        )
        probability = 1.0 / (1.0 + np.exp(-np.clip(global_logit, -8.0, 8.0)))

        organ_lookup = {
            "respiratory": 1.0 / (1.0 + np.exp(-np.clip(respiratory_score - 0.8, -8.0, 8.0))),
            "circulatory": 1.0 / (1.0 + np.exp(-np.clip(circulatory_score - 0.8, -8.0, 8.0))),
            "renal": 1.0 / (1.0 + np.exp(-np.clip(renal_score - 0.8, -8.0, 8.0))),
            "neurologic": 1.0 / (1.0 + np.exp(-np.clip(neurologic_score - 0.8, -8.0, 8.0))),
        }
        organ_probabilities = {
            key: round(float(organ_lookup.get(key, probability)), 4)
            for key in organ_keys
        }

        trend_pressure = max(
            0.0,
            max(0.0, map_drop / 10.0) +
            max(0.0, spo2_drop / 4.0) +
            max(0.0, rr_rise / 10.0) +
            max(0.0, hr_rise / 20.0)
        )
        future_probabilities: dict[int, float] = {}
        for hour in horizons:
            horizon_weight = min(float(hour) / 24.0, 1.0)
            adjusted = probability + (1.0 - probability) * trend_pressure * 0.16 * horizon_weight
            future_probabilities[int(hour)] = round(float(np.clip(adjusted, 0.01, 0.99)), 4)

        return {
            "available": True,
            "backend": "heuristic",
            "device": "cpu",
            "model_path": "",
            "reason": f"{self._reason or 'heuristic'}:trend_inferred",
            "probability": round(float(np.clip(probability, 0.01, 0.99)), 4),
            "organ_probabilities": organ_probabilities,
            "future_probabilities": future_probabilities,
            "components": {
                "circulatory": round(float(circulatory_score), 4),
                "respiratory": round(float(respiratory_score), 4),
                "renal": round(float(renal_score), 4),
                "neurologic": round(float(neurologic_score), 4),
                "trend_pressure": round(float(trend_pressure), 4),
            },
        }

    def predict(
        self,
        *,
        sequence: np.ndarray,
        meta_features: np.ndarray | None = None,
        organ_keys: list[str] | None = None,
        horizons: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        self._ensure_loaded()
        organ_keys = organ_keys or []
        if self._backend == "heuristic" or self._model is None:
            if self._heuristic_enabled():
                return self._heuristic_predict(
                    sequence=sequence,
                    meta_features=meta_features,
                    organ_keys=organ_keys,
                    horizons=horizons,
                )
            return {
                "available": False,
                "backend": self._backend,
                "device": self._device,
                "model_path": self._model_path,
                "reason": self._reason,
            }

        try:
            if self._backend == "onnx":
                feeds = self._prepare_onnx_inputs(sequence, meta_features)
                raw_outputs = self._model.run(self._output_names or None, feeds)
                parsed = self._parse_probability_output(raw_outputs[0] if len(raw_outputs) == 1 else raw_outputs, organ_keys=organ_keys, horizons=horizons)
            else:
                import torch  # type: ignore

                seq, meta = self._prepare_torch_inputs(sequence, meta_features)
                model = self._model
                with torch.inference_mode():
                    try:
                        raw = model(seq, meta) if meta is not None else model(seq)
                    except TypeError:
                        raw = model(seq)
                parsed = self._parse_probability_output(raw, organ_keys=organ_keys, horizons=horizons)
            if not parsed:
                return {
                    "available": False,
                    "backend": self._backend,
                    "device": self._device,
                    "model_path": self._model_path,
                    "reason": "invalid_model_output",
                }
            parsed.update(
                {
                    "available": True,
                    "backend": self._backend,
                    "device": self._device,
                    "model_path": self._model_path,
                    "reason": self._reason,
                }
            )
            return parsed
        except Exception as e:
            logger.warning("时序模型推理失败: %s", e)
            return {
                "available": False,
                "backend": self._backend,
                "device": self._device,
                "model_path": self._model_path,
                "reason": f"inference_failed:{type(e).__name__}:{str(e)[:120]}",
            }

    def meta(self) -> dict[str, Any]:
        self._ensure_loaded()
        return {
            "backend": self._backend,
            "device": self._device,
            "model_path": self._model_path,
            "available": bool((self._backend != "heuristic" and self._model is not None) or (self._backend == "heuristic" and self._heuristic_enabled())),
            "reason": self._reason,
        }
