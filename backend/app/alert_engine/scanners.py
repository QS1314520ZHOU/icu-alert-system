from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Coroutine, TypeVar

if TYPE_CHECKING:
    from . import AlertEngine

logger = logging.getLogger("icu-alert")

T = TypeVar("T")


@dataclass(frozen=True)
class ScannerSpec:
    name: str
    interval_key: str
    default_interval: int
    initial_delay: int


class BaseScanner(ABC):
    def __init__(self, engine: AlertEngine, spec: ScannerSpec) -> None:
        self.engine = engine
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    def interval_seconds(self) -> int:
        intervals = self.engine.config.yaml_cfg.get("alert_engine", {}).get("scan_intervals", {})
        return int(intervals.get(self.spec.interval_key, self.spec.default_interval))

    @property
    def initial_delay(self) -> int:
        return int(self.spec.initial_delay)

    def is_enabled(self) -> bool:
        cfg = self.engine.config.yaml_cfg.get("alert_engine", {})
        disabled = cfg.get("disabled_scanners", []) if isinstance(cfg, dict) else []
        disabled_names = {str(name).strip() for name in disabled if str(name).strip()}
        return self.name not in disabled_names

    async def record_run_telemetry(
        self,
        *,
        status: str,
        duration_ms: float,
        error: str = "",
    ) -> None:
        try:
            now = datetime.now()
            mesh_metrics = {}
            try:
                mesh = getattr(self.engine, "scanner_mesh", None)
                mesh_metrics = mesh.telemetry() if mesh is not None and hasattr(mesh, "telemetry") else {}
            except Exception:
                mesh_metrics = {}
            await self.engine.db.col("scanner_runs").insert_one(
                {
                    "scanner_name": self.name,
                    "status": status,
                    "duration_ms": round(float(duration_ms or 0), 2),
                    "error": str(error or "")[:500],
                    "mesh_metrics": mesh_metrics,
                    "runtime_role": getattr(self.engine, "runtime_role", "api"),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except Exception as exc:
            logger.debug("[%s] scanner telemetry write failed: %s", self.name, exc)

    async def run_with_telemetry(self) -> None:
        started = time.perf_counter()
        status = "success"
        error = ""
        try:
            await self.scan()
        except Exception as exc:
            status = "error"
            error = str(exc)
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            await self.record_run_telemetry(status=status, duration_ms=duration_ms, error=error)

    def _llm_timeout(self) -> float:
        """从配置读取 LLM 超时秒数，默认 45s。"""
        try:
            cfg = self.engine.config.yaml_cfg.get("alert_engine", {}) or {}
            return float(cfg.get("llm_timeout", 45) or 45)
        except Exception:
            return 45.0

    async def _safe_llm_call(
        self,
        coro: Coroutine[Any, Any, T],
        *,
        fallback: T | None = None,
        timeout: float | None = None,
    ) -> T | None:
        """
        统一的 LLM 调用安全包装。

        当 LLM 超时或抛出任何异常时，记录 WARNING 并返回 fallback，
        使调用方可以无缝降级到纯规则模式，不影响基础预警的发出。

        用法示例:
            result = await self._safe_llm_call(
                call_llm_chat(system_prompt, user_prompt, model),
                fallback=None,
            )
            if result:
                # AI 增强路径
            else:
                # 纯规则路径
        """
        t = timeout if timeout is not None else self._llm_timeout()
        try:
            return await asyncio.wait_for(coro, timeout=t)
        except asyncio.TimeoutError:
            logger.warning("[%s] LLM 调用超时（%.0fs），降级到规则模式", self.name, t)
            return fallback
        except Exception as exc:
            logger.warning("[%s] LLM 调用异常: %s，降级到规则模式", self.name, exc)
            return fallback

    @abstractmethod
    async def scan(self) -> None:
        raise NotImplementedError
