from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

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

    def _cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("ai_service", {}).get("temporal_model", {})
        return cfg if isinstance(cfg, dict) else {}

    def _discover_candidates(self) -> list[Path]:
        cfg = self._cfg()
        backend_root = Path(__file__).resolve().parents[2]
        configured = str(cfg.get("model_path") or "").strip()
        candidates: list[Path] = []
        if configured:
            p = Path(configured)
            if not p.is_absolute():
                p = backend_root / configured
            candidates.append(p)
        search_dirs = [
            backend_root / "models",
            backend_root / "weights",
            backend_root / "artifacts",
        ]
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

                session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
                self._model = session
                self._backend = "onnx"
                self._input_names = [x.name for x in session.get_inputs()]
                self._output_names = [x.name for x in session.get_outputs()]
                self._reason = "loaded"
            elif suffix in {".pt", ".pth", ".ckpt"}:
                import torch  # type: ignore

                loaded = None
                try:
                    loaded = torch.jit.load(str(model_path), map_location="cpu")
                except Exception:
                    loaded = torch.load(str(model_path), map_location="cpu")
                if hasattr(loaded, "eval"):
                    loaded.eval()
                self._model = loaded
                self._backend = "pytorch"
                self._reason = "loaded"
            else:
                self._backend = "heuristic"
                self._reason = f"unsupported_weight_format:{suffix or 'unknown'}"
                self._model = None
            self._model_path = str(model_path)
            self._mtime = mtime
            self._loaded = True
        except Exception as e:
            self._backend = "heuristic"
            self._model = None
            self._model_path = str(model_path)
            self._mtime = mtime
            self._loaded = True
            self._reason = f"load_failed:{type(e).__name__}:{str(e)[:120]}"
            logger.warning("时序模型加载失败: %s", self._reason)

    def _prepare_onnx_inputs(self, sequence: np.ndarray, meta_features: np.ndarray | None) -> dict[str, np.ndarray]:
        session = self._model
        feeds: dict[str, np.ndarray] = {}
        inputs = session.get_inputs() if session is not None else []
        seq3 = sequence.astype(np.float32)[None, ...]
        seq2 = sequence.astype(np.float32).reshape(1, -1)
        meta2 = meta_features.astype(np.float32).reshape(1, -1) if meta_features is not None else None
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

        seq = torch.tensor(sequence.astype(np.float32)).unsqueeze(0)
        meta = torch.tensor(meta_features.astype(np.float32)).unsqueeze(0) if meta_features is not None else None
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
            return {
                "available": False,
                "backend": self._backend,
                "model_path": self._model_path,
                "reason": self._reason,
            }

        try:
            if self._backend == "onnx":
                feeds = self._prepare_onnx_inputs(sequence, meta_features)
                raw_outputs = self._model.run(self._output_names or None, feeds)
                parsed = self._parse_probability_output(raw_outputs[0] if len(raw_outputs) == 1 else raw_outputs, organ_keys=organ_keys, horizons=horizons)
            else:
                seq, meta = self._prepare_torch_inputs(sequence, meta_features)
                model = self._model
                try:
                    raw = model(seq, meta) if meta is not None else model(seq)
                except TypeError:
                    raw = model(seq)
                parsed = self._parse_probability_output(raw, organ_keys=organ_keys, horizons=horizons)
            if not parsed:
                return {
                    "available": False,
                    "backend": self._backend,
                    "model_path": self._model_path,
                    "reason": "invalid_model_output",
                }
            parsed.update(
                {
                    "available": True,
                    "backend": self._backend,
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
                "model_path": self._model_path,
                "reason": f"inference_failed:{type(e).__name__}:{str(e)[:120]}",
            }

    def meta(self) -> dict[str, Any]:
        self._ensure_loaded()
        return {
            "backend": self._backend,
            "model_path": self._model_path,
            "available": bool(self._backend != "heuristic" and self._model is not None),
            "reason": self._reason,
        }
