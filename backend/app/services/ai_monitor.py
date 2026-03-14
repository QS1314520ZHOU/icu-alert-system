"""AI monitoring utility for tracing LLM quality/latency."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import Any


class AiMonitor:
    def __init__(self, db, config) -> None:
        self.db = db
        self.config = config

    def is_enabled(self) -> bool:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("monitor", {})
        if isinstance(cfg, dict):
            return bool(cfg.get("enabled", True))
        return True

    async def log_llm_call(
        self,
        *,
        module: str,
        model: str,
        prompt: str,
        output: str,
        latency_ms: float,
        success: bool,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if not self.is_enabled():
            return
        now = datetime.now()
        doc = {
            "module": module,
            "model": model,
            "input_hash": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest(),
            "output_hash": hashlib.sha256((output or "").encode("utf-8")).hexdigest(),
            "latency_ms": round(float(latency_ms), 2),
            "success": bool(success),
            "output_chars": len(output or ""),
            "created_at": now,
            "meta": meta or {},
        }

        try:
            await self.db.col("ai_monitor_logs").insert_one(doc)
        except Exception:
            return

    async def log_prediction_feedback(
        self,
        *,
        module: str,
        prediction_id: str,
        outcome: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not self.is_enabled():
            return
        doc = {
            "module": module,
            "prediction_id": prediction_id,
            "outcome": outcome,
            "detail": detail or {},
            "created_at": datetime.now(),
        }
        try:
            await self.db.col("ai_prediction_feedback").insert_one(doc)
        except Exception:
            return

    @staticmethod
    def now_ms() -> float:
        return time.perf_counter() * 1000.0

