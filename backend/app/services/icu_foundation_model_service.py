"""Local ICU foundation model runtime.

The runtime is intentionally conservative: model files are discovered lazily
from config/env and missing dependencies never block API startup.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from bson import ObjectId

from app.services.local_model_paths import local_model_dir, local_models_base_dir


DEFAULT_FM_TASKS = ("mortality", "aki", "circulation_failure")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


class ICUFoundationModelService:
    def __init__(self, *, db, config, alert_engine=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self._loaded = False
        self._model: Any = None
        self._torch: Any = None
        self._device = "cpu"
        self._unavailable_reason = ""
        self._model_path: Path | None = None
        self._provider = "icarefm"

    def _cfg(self) -> dict[str, Any]:
        ai = (getattr(self.config, "yaml_cfg", {}) or {}).get("ai_service", {})
        return ai if isinstance(ai, dict) else {}

    def _local_models_dir(self) -> Path:
        return local_models_base_dir(self.config)

    def _icarefm_dir(self) -> Path:
        return local_model_dir(self.config, "icarefm_dir", "icarefm")

    def _knowledge_guided_dir(self) -> Path:
        return local_model_dir(self.config, "knowledge_pretrain_dir", "knowledge-guided-pretrain")

    def _provider_cfg(self) -> dict[str, Any]:
        providers = self._cfg().get("foundation_model", {}).get("providers", {})
        return providers if isinstance(providers, dict) else {}

    def _active_provider(self) -> str:
        primary = str(self._provider_cfg().get("primary") or "icarefm").strip().lower()
        return "knowledge_guided" if primary in {"knowledge_guided", "knowledge-guided"} else "icarefm"

    def _candidate_paths(self) -> list[Path]:
        self._provider = self._active_provider()
        root = self._knowledge_guided_dir() if self._provider == "knowledge_guided" else self._icarefm_dir()
        names = ["model.pt", "icarefm.pt", "pytorch_model.bin", "model.pth"]
        if self._provider == "knowledge_guided":
            names = ["model.pt", "knowledge_guided.pt", "pytorch_model.bin", "model.pth"]
        return [root / name for name in names]

    def status(self) -> dict[str, Any]:
        if not self._loaded:
            self._ensure_loaded()
        return {
            "available": bool(self._model is not None),
            "reason": self._unavailable_reason,
            "model_path": str(self._model_path or ""),
            "backend": "torch",
            "provider": self._provider,
            "shadow_providers": list(self._provider_cfg().get("shadow") or []),
            "routing_mode": str(self._provider_cfg().get("mode") or "primary"),
            "embedding_dim": 768,
        }

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
        for path in self._candidate_paths():
            if not path.exists():
                continue
            try:
                self._model_path = path
                if path.suffix.lower() in {".pt", ".pth"}:
                    try:
                        self._model = torch.jit.load(str(path), map_location=self._device)
                    except Exception:
                        self._model = torch.load(str(path), map_location=self._device)
                else:
                    self._model = torch.load(str(path), map_location=self._device)
                if hasattr(self._model, "eval"):
                    self._model.eval()
                self._unavailable_reason = ""
                return
            except Exception as exc:
                self._model = None
                self._unavailable_reason = f"load failed: {exc.__class__.__name__}: {str(exc)[:120]}"
                return
        model_dir = self._knowledge_guided_dir() if self._provider == "knowledge_guided" else self._icarefm_dir()
        self._unavailable_reason = f"no torch weight found under {model_dir}"

    async def _load_patient_state(self, patient_id: str) -> dict[str, Any]:
        patient = None
        try:
            patient = await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            patient = await self.db.col("patient").find_one({"_id": patient_id})
        if not patient:
            return {}
        facts = {}
        if self.alert_engine is not None and hasattr(self.alert_engine, "_collect_patient_facts"):
            try:
                facts = await self.alert_engine._collect_patient_facts(patient, patient.get("_id"))
            except Exception:
                facts = {}
        return {"patient": patient, "facts": facts or {}}

    def _feature_vector(self, state: dict[str, Any]) -> np.ndarray:
        patient = state.get("patient") if isinstance(state.get("patient"), dict) else {}
        facts = state.get("facts") if isinstance(state.get("facts"), dict) else {}
        vitals = facts.get("vitals") if isinstance(facts.get("vitals"), dict) else {}
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}

        def lab(key: str) -> float:
            item = labs.get(key)
            if isinstance(item, dict):
                return _safe_float(item.get("value")) or 0.0
            return _safe_float(item) or 0.0

        raw = [
            _safe_float(patient.get("age") or patient.get("hisAge")) or 0.0,
            _safe_float(vitals.get("hr")) or 0.0,
            _safe_float(vitals.get("map")) or 0.0,
            _safe_float(vitals.get("spo2")) or 0.0,
            _safe_float(vitals.get("rr")) or 0.0,
            lab("lac") or lab("lactate"),
            lab("cr"),
            lab("wbc"),
            lab("plt"),
        ]
        vec = np.zeros(64, dtype=np.float32)
        vec[: len(raw)] = np.asarray(raw, dtype=np.float32)
        return vec

    async def encode_patient(self, patient_id) -> np.ndarray:
        self._ensure_loaded()
        state = await self._load_patient_state(str(patient_id))
        features = self._feature_vector(state)
        if self._model is None or self._torch is None:
            embedding = np.zeros(768, dtype=np.float32)
            embedding[: min(features.size, 768)] = features[: min(features.size, 768)]
            return embedding
        try:
            with self._torch.no_grad():
                tensor = self._torch.tensor(features, dtype=self._torch.float32).unsqueeze(0)
                if hasattr(self._model, "encode_patient"):
                    output = self._model.encode_patient(tensor)
                else:
                    output = self._model(tensor)
                arr = output.detach().cpu().numpy().reshape(-1).astype(np.float32)
        except Exception:
            arr = features
        embedding = np.zeros(768, dtype=np.float32)
        embedding[: min(arr.size, 768)] = arr[: min(arr.size, 768)]
        return embedding

    async def zero_shot_predict(self, patient_id, tasks: list[str] | None = None) -> dict:
        task_list = [str(t) for t in (tasks or list(DEFAULT_FM_TASKS)) if str(t).strip()]
        self._ensure_loaded()
        embedding = await self.encode_patient(patient_id)
        status = self.status()
        if not status["available"]:
            return {
                "available": False,
                "reason": status["reason"],
                "provider": status.get("provider"),
                "tasks": {task: {"probability": None, "risk_level": "unknown"} for task in task_list},
                "model_meta": status,
                "generated_at": datetime.now(),
            }
        probs: dict[str, float] = {}
        if hasattr(self._model, "zero_shot_predict"):
            try:
                raw = self._model.zero_shot_predict(embedding, task_list)
                if isinstance(raw, dict):
                    probs = {str(k): float(v) for k, v in raw.items() if k in task_list}
            except Exception:
                probs = {}
        if not probs:
            head = embedding[:16] if embedding.size else np.asarray([0.0], dtype=np.float32)
            score = float(1 / (1 + np.exp(-float(np.nanmean(head)) / 100.0)))
            probs = {task: score for task in task_list}
        return {
            "available": True,
            "provider": status.get("provider"),
            "tasks": {task: {"probability": round(float(probs.get(task, 0.0)), 4), "risk_level": self._risk_level(probs.get(task, 0.0))} for task in task_list},
            "model_meta": status,
            "generated_at": datetime.now(),
        }

    @staticmethod
    def _risk_level(probability: float) -> str:
        p = float(probability or 0.0)
        if p >= 0.85:
            return "critical"
        if p >= 0.7:
            return "high"
        if p >= 0.45:
            return "warning"
        return "low"


_FM_SINGLETON: ICUFoundationModelService | None = None


def get_icu_foundation_model_service(*, db, config, alert_engine=None) -> ICUFoundationModelService:
    global _FM_SINGLETON
    if (
        _FM_SINGLETON is None
        or _FM_SINGLETON.db is not db
        or _FM_SINGLETON.config is not config
        or _FM_SINGLETON.alert_engine is not alert_engine
    ):
        _FM_SINGLETON = ICUFoundationModelService(db=db, config=config, alert_engine=alert_engine)
    return _FM_SINGLETON
