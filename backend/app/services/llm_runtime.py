from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("icu-alert")


class CircuitBreakerOpenError(RuntimeError):
    pass


class _LLMCircuitBreaker:
    def __init__(self) -> None:
        self.failure_count = 0
        self.open_until = 0.0
        self.last_error = ""
        self._lock = asyncio.Lock()

    async def before_call(self, *, threshold: int, cooldown_seconds: int) -> tuple[bool, float]:
        async with self._lock:
            now = time.time()
            if self.open_until and now < self.open_until:
                return True, max(0.0, self.open_until - now)
            if self.open_until and now >= self.open_until:
                self.open_until = 0.0
                self.failure_count = 0
                self.last_error = ""
            return False, 0.0

    async def record_success(self) -> None:
        async with self._lock:
            self.failure_count = 0
            self.open_until = 0.0
            self.last_error = ""

    async def record_failure(self, *, threshold: int, cooldown_seconds: int, error: str = "") -> bool:
        async with self._lock:
            self.failure_count += 1
            self.last_error = (error or "")[:200]
            if self.failure_count >= max(1, threshold):
                self.open_until = time.time() + max(10, cooldown_seconds)
                logger.warning(
                    "LLM circuit breaker 打开: failures=%s cooldown=%ss error=%s",
                    self.failure_count,
                    cooldown_seconds,
                    self.last_error,
                )
                return True
            return False

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            now = time.time()
            return {
                "failure_count": self.failure_count,
                "open": bool(self.open_until and now < self.open_until),
                "open_until": self.open_until,
                "retry_after_seconds": max(0.0, self.open_until - now) if self.open_until else 0.0,
                "last_error": self.last_error,
            }


_BREAKER = _LLMCircuitBreaker()


def _llm_runtime_cfg(cfg) -> tuple[int, int]:
    ai_service = cfg.yaml_cfg.get("ai_service", {}) if isinstance(cfg.yaml_cfg, dict) else {}
    llm_cfg = ai_service.get("llm", {}) if isinstance(ai_service, dict) else {}
    breaker_cfg = llm_cfg.get("circuit_breaker", {}) if isinstance(llm_cfg, dict) else {}
    threshold = int(breaker_cfg.get("failure_threshold", 3) or 3)
    cooldown_seconds = int(breaker_cfg.get("cooldown_seconds", 180) or 180)
    return max(1, threshold), max(10, cooldown_seconds)


def resolve_model_candidates(cfg, requested_model: str | None = None) -> tuple[list[str], bool, dict[str, Any]]:
    primary = str(requested_model or cfg.llm_model_medical or cfg.settings.LLM_MODEL or "").strip()
    explicit_fallback = str(cfg.llm_fallback_model or "").strip()
    if explicit_fallback:
        fallback = explicit_fallback
    else:
        default_main = str(cfg.settings.LLM_MODEL or "").strip()
        fallback = default_main if (requested_model and default_main and default_main != primary) else ""
    seen: set[str] = set()
    normal_candidates: list[str] = []
    for item in (primary, fallback):
        if item and item not in seen:
            seen.add(item)
            normal_candidates.append(item)
    degraded_candidates: list[str] = []
    if fallback:
        degraded_candidates.append(fallback)
    elif primary:
        degraded_candidates.append(primary)
    degraded_candidates = [m for i, m in enumerate(degraded_candidates) if m and m not in degraded_candidates[:i]]
    degraded = bool(fallback and primary and fallback != primary)
    return normal_candidates, degraded, {"primary_model": primary, "fallback_model": fallback}


async def call_llm_chat(
    *,
    cfg,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    timeout_seconds: float = 60,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    threshold, cooldown_seconds = _llm_runtime_cfg(cfg)
    normal_candidates, has_real_degrade, models_meta = resolve_model_candidates(cfg, model)
    is_open, retry_after = await _BREAKER.before_call(threshold=threshold, cooldown_seconds=cooldown_seconds)
    if is_open:
        candidates = [models_meta.get("fallback_model")] if models_meta.get("fallback_model") else []
        degraded_mode = True
    else:
        candidates = normal_candidates
        degraded_mode = False

    candidates = [c for c in candidates if c]
    if not candidates:
        raise CircuitBreakerOpenError(f"LLM circuit breaker open, retry after {int(retry_after)}s")

    llm_url = cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.settings.LLM_API_KEY}",
    }
    last_exc: Exception | None = None
    used_model = ""
    used_fallback = False

    async def _send(req_client: httpx.AsyncClient, model_name: str) -> dict[str, Any]:
        payload = {
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        resp = await req_client.post(llm_url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    if client is None:
        req_client_ctx = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
    else:
        req_client_ctx = None

    try:
        req_client = client
        if req_client is None:
            req_client = await req_client_ctx.__aenter__()  # type: ignore[union-attr]
        for idx, candidate in enumerate(candidates):
            try:
                data = await _send(req_client, candidate)
                used_model = candidate
                used_fallback = degraded_mode or (idx > 0) or (candidate == models_meta.get("fallback_model") and has_real_degrade)
                if not used_fallback:
                    await _BREAKER.record_success()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage") if isinstance(data, dict) else None
                return {
                    "text": text,
                    "usage": usage,
                    "model": used_model,
                    "degraded_mode": used_fallback,
                    "meta": {
                        "url": llm_url,
                        "primary_model": models_meta.get("primary_model"),
                        "fallback_model": models_meta.get("fallback_model"),
                        "circuit_open": is_open,
                        "retry_after_seconds": retry_after,
                    },
                }
            except Exception as e:
                last_exc = e
                if not degraded_mode and idx == 0:
                    await _BREAKER.record_failure(
                        threshold=threshold,
                        cooldown_seconds=cooldown_seconds,
                        error=str(e),
                    )
                continue
    finally:
        if req_client_ctx is not None:
            await req_client_ctx.__aexit__(None, None, None)

    if last_exc:
        raise last_exc
    raise RuntimeError("LLM 调用失败")


async def breaker_snapshot() -> dict[str, Any]:
    return await _BREAKER.snapshot()
