from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger("icu-alert")


class LLMRuntimeUnavailableError(RuntimeError):
    pass


class _LLMFailureTracker:
    def __init__(self) -> None:
        self.failure_count = 0
        self.open_until = 0.0
        self.last_error = ""
        self.half_open_probe_active = False
        self._lock = asyncio.Lock()

    async def before_call(self, *, threshold: int, cooldown_seconds: int) -> tuple[bool, float]:
        async with self._lock:
            now = time.time()
            if self.open_until and now < self.open_until:
                return True, max(0.0, self.open_until - now)
            if self.open_until and now >= self.open_until:
                if self.half_open_probe_active:
                    return True, 0.0
                self.open_until = 0.0
                self.half_open_probe_active = True
                logger.warning("LLM circuit breaker entering half-open probe state")
            return False, 0.0

    async def record_success(self) -> None:
        async with self._lock:
            previous_state = self._state_locked()
            self.failure_count = 0
            self.open_until = 0.0
            self.last_error = ""
            self.half_open_probe_active = False
            if previous_state != "closed":
                logger.info("LLM circuit breaker closed after successful probe/recovery")

    async def record_failure(self, *, threshold: int, cooldown_seconds: int, error: str = "") -> bool:
        async with self._lock:
            self.failure_count += 1
            self.last_error = (error or "")[:200]
            if self.failure_count >= max(1, threshold):
                self.open_until = time.time() + max(10, cooldown_seconds)
                self.half_open_probe_active = False
                logger.warning(
                    "LLM circuit breaker opened after %s consecutive failures, cooldown=%ss, error=%s",
                    self.failure_count,
                    cooldown_seconds,
                    self.last_error,
                )
                return True
            return False

    def _state_locked(self) -> str:
        now = time.time()
        if self.open_until and now < self.open_until:
            return "open"
        if self.half_open_probe_active:
            return "half_open"
        return "closed"

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            now = time.time()
            state = self._state_locked()
            return {
                "failure_count": self.failure_count,
                "open": state == "open",
                "state": state,
                "open_until": self.open_until,
                "retry_after_seconds": max(0.0, self.open_until - now) if self.open_until else 0.0,
                "last_error": self.last_error,
                "half_open_probe_active": self.half_open_probe_active,
            }


_FAILURE_TRACKER = _LLMFailureTracker()
_LLM_SEMAPHORE: asyncio.Semaphore | None = None
_LLM_CONCURRENCY_LIMIT = 0
_LLM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LLM_CACHE_LOCK = asyncio.Lock()


def _prompt_hash(*parts: Any) -> str:
    raw = "\n\n".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _cache_ttl_seconds(runtime_ai: dict[str, Any]) -> int:
    try:
        cache_cfg = runtime_ai.get("cache") if isinstance(runtime_ai.get("cache"), dict) else {}
        if cache_cfg.get("enabled") is False:
            return 0
        return int(cache_cfg.get("ttl_seconds") or runtime_ai.get("cache_ttl_seconds") or 900)
    except Exception:
        return 900


def _concurrency_limit(runtime_ai: dict[str, Any]) -> int:
    try:
        return max(1, int(runtime_ai.get("concurrency_limit") or runtime_ai.get("max_concurrent") or 4))
    except Exception:
        return 4


async def _get_cache(cache_key: str, ttl_seconds: int) -> dict[str, Any] | None:
    if ttl_seconds <= 0 or not cache_key:
        return None
    now = time.time()
    async with _LLM_CACHE_LOCK:
        cached = _LLM_CACHE.get(cache_key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= now:
            _LLM_CACHE.pop(cache_key, None)
            return None
        return {**value, "cache_hit": True, "meta": {**(value.get("meta") or {}), "cache_hit": True}}


async def _set_cache(cache_key: str, ttl_seconds: int, value: dict[str, Any]) -> None:
    if ttl_seconds <= 0 or not cache_key:
        return
    async with _LLM_CACHE_LOCK:
        if len(_LLM_CACHE) > 512:
            now = time.time()
            stale = [key for key, (expires_at, _) in _LLM_CACHE.items() if expires_at <= now]
            for key in stale[:128]:
                _LLM_CACHE.pop(key, None)
            if len(_LLM_CACHE) > 512:
                for key in list(_LLM_CACHE.keys())[:128]:
                    _LLM_CACHE.pop(key, None)
        _LLM_CACHE[cache_key] = (time.time() + ttl_seconds, value)


async def _write_llm_call_log(doc: dict[str, Any]) -> None:
    try:
        from app import runtime

        if runtime.db is None:
            return
        await runtime.db.col("llm_call_logs").insert_one(doc)
    except Exception as exc:
        logger.debug("LLM telemetry write failed: %s", exc)


async def _runtime_ai_config() -> dict[str, Any]:
    try:
        from app import runtime

        if runtime.db is None:
            return {}
        doc = await runtime.db.col("runtime_configs").find_one({"key": "ai"})
        value = (doc or {}).get("value") or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


async def _llm_runtime_cfg(cfg) -> tuple[int, int]:
    ai_service = cfg.yaml_cfg.get("ai_service", {}) if isinstance(cfg.yaml_cfg, dict) else {}
    llm_cfg = ai_service.get("llm", {}) if isinstance(ai_service, dict) else {}
    runtime_ai = await _runtime_ai_config()
    if runtime_ai:
        llm_cfg = {**llm_cfg, **runtime_ai}
    breaker_cfg = llm_cfg.get("circuit_breaker", {}) if isinstance(llm_cfg, dict) else {}
    threshold = int(breaker_cfg.get("failure_threshold", 3) or 3)
    cooldown_seconds = int(breaker_cfg.get("cooldown_seconds", 180) or 180)
    return max(1, threshold), max(10, cooldown_seconds)


def _purpose_from_requested_model(requested_model: str | None) -> str:
    text = str(requested_model or "").strip().lower()
    if text in {"fast", "quick", "summary", "handoff"}:
        return "fast"
    if text in {"medical", "clinical", "risk"}:
        return "medical"
    if text in {"reasoning", "推理"}:
        return "reasoning"
    if text in {"long", "long_context", "context"}:
        return "long_context"
    return ""


def _provider_candidates(runtime_ai: dict[str, Any], requested_model: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    providers = [p for p in runtime_ai.get("providers") or [] if isinstance(p, dict) and p.get("enabled", True)]
    if not providers:
        return [], {}
    requested = str(requested_model or "").strip()
    purpose = _purpose_from_requested_model(requested)
    routes = runtime_ai.get("routes") if isinstance(runtime_ai.get("routes"), dict) else {}
    routed_provider_id = str(routes.get(purpose) or "").strip() if purpose else ""
    if routed_provider_id:
        selected = [p for p in providers if str(p.get("id") or "") == routed_provider_id]
    elif purpose:
        selected = [p for p in providers if str(p.get("purpose") or "").strip().lower() == purpose]
    elif requested:
        selected = [p for p in providers if str(p.get("model") or "").strip() == requested or str(p.get("id") or "").strip() == requested]
    else:
        selected = [p for p in providers if str(p.get("purpose") or "").strip().lower() == "fast"]
    fallback_id = str(routes.get("fallback") or "").strip()
    fallback = [p for p in providers if str(p.get("id") or "") == fallback_id] if fallback_id else []
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(selected + fallback + providers, key=lambda row: int(row.get("priority") or 50)):
        key = str(item.get("id") or item.get("model") or item.get("base_url") or "")
        if key and key not in seen:
            seen.add(key)
            merged.append(item)
    meta = {
        "primary_model": str(merged[0].get("model") or "") if merged else "",
        "fallback_model": str(fallback[0].get("model") or "") if fallback else "",
        "provider_pool": True,
        "purpose": purpose or "model",
    }
    return merged, meta


async def resolve_model_candidates(cfg, requested_model: str | None = None) -> tuple[list[Any], bool, dict[str, Any]]:
    runtime_ai = await _runtime_ai_config()
    provider_rows, provider_meta = _provider_candidates(runtime_ai, requested_model)
    if provider_rows:
        return provider_rows, len(provider_rows) > 1, provider_meta

    # Resolve tier keywords ("medical"/"fast"/"reasoning"/"long_context") → real model names.
    # Without this, the keyword literal gets sent to DeepSeek as a model name → 400.
    purpose = _purpose_from_requested_model(requested_model)
    resolved_requested = requested_model
    if purpose:
        tier_map: dict[str, Any] = {
            "fast": cfg.llm_fast_model,
            "medical": cfg.llm_model_medical or cfg.llm_fast_model,
            "reasoning": cfg.llm_reasoning_model or cfg.llm_model_medical or cfg.llm_fast_model,
            "long_context": cfg.llm_model_medical or cfg.llm_fast_model,
        }
        resolved = str(tier_map.get(purpose) or "").strip()
        resolved_requested = resolved or None  # None → falls through to fast_model below

    primary = str(resolved_requested or runtime_ai.get("fast_model") or cfg.llm_fast_model or cfg.settings.LLM_MODEL or "").strip()
    explicit_fallback = str(runtime_ai.get("fallback_model") or cfg.llm_fallback_model or "").strip()
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


def _should_trip_breaker(exc: Exception) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = int(exc.response.status_code)
        # 400/401/403 = persistent config/auth errors — no point retrying; open the breaker
        return status in (400, 401, 403, 408, 429) or status >= 500
    return False


def sanitize_llm_text(text: Any) -> str:
    """Remove model-internal thinking traces before the text reaches UI/storage."""
    cleaned = str(text or "")
    if not cleaned:
        return ""
    cleaned = re.sub(r"<think\b[^>]*>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<reasoning\b[^>]*>[\s\S]*?</reasoning>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<analysis\b[^>]*>[\s\S]*?</analysis>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<think\b[^>]*>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<reasoning\b[^>]*>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<analysis\b[^>]*>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?(?:think|reasoning|analysis)\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&lt;think\b[^&]*&gt;[\s\S]*?&lt;/think&gt;", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&lt;think\b[^&]*&gt;[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&lt;/?(?:think|reasoning|analysis)\b[^&]*&gt;", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<\s*(?:think|reasoning|analysis)\b[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&lt;\s*(?:think|reasoning|analysis)\b[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*&lt;?\s*(?:think|reasoning|analysis)\b.*$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(r"^\s*<\s*(?:think|reasoning|analysis)\b.*$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(
        r"^\s*(?:思考过程|推理过程|内部推理|模型思考|Chain\s*of\s*Thought|Reasoning)\s*[：:]\s*[\s\S]*?(?=(?:\n\s*)?(?:```|\{|\[|#{1,4}\s|结论[：:]|建议[：:]|评估[：:]|摘要[：:]))",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^\s*(?:思考|Thinking|Reasoning)\s*[：:]\s*$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    return cleaned.strip()


async def call_llm_chat(
    *,
    cfg,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    timeout_seconds: float = 60,
    response_format: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    global _LLM_SEMAPHORE, _LLM_CONCURRENCY_LIMIT
    runtime_ai = await _runtime_ai_config()
    if runtime_ai and runtime_ai.get("enabled") is False:
        raise LLMRuntimeUnavailableError("AI能力已在运行时配置中心关闭")
    if runtime_ai:
        temperature = float(runtime_ai.get("temperature", temperature) or temperature)
        max_tokens = int(runtime_ai.get("max_tokens", max_tokens) or max_tokens)
        timeout_seconds = float(runtime_ai.get("timeout", timeout_seconds) or timeout_seconds)
    cache_key = _prompt_hash(model or "", temperature, max_tokens, response_format or {}, system_prompt, user_prompt)
    ttl_seconds = _cache_ttl_seconds(runtime_ai)
    cached = await _get_cache(cache_key, ttl_seconds)
    if cached:
        await _write_llm_call_log(
            {
                "cache_key": cache_key,
                "model": cached.get("model") or model or "",
                "status": "cache_hit",
                "cache_hit": True,
                "duration_ms": 0,
                "degraded_mode": bool(cached.get("degraded_mode")),
                "usage": cached.get("usage"),
                "created_at": datetime.now(),
            }
        )
        return cached
    limit = _concurrency_limit(runtime_ai)
    if _LLM_SEMAPHORE is None:
        _LLM_SEMAPHORE = asyncio.Semaphore(limit)
        _LLM_CONCURRENCY_LIMIT = limit
    threshold, cooldown_seconds = await _llm_runtime_cfg(cfg)
    normal_candidates, has_real_degrade, models_meta = await resolve_model_candidates(cfg, model)
    circuit_open, retry_after_seconds = await _FAILURE_TRACKER.before_call(threshold=threshold, cooldown_seconds=cooldown_seconds)
    if circuit_open:
        raise LLMRuntimeUnavailableError(
            f"LLM runtime circuit breaker open, retry after {retry_after_seconds:.1f}s"
        )
    candidates = normal_candidates
    degraded_mode = False

    candidates = [c for c in candidates if c]
    if not candidates:
        raise LLMRuntimeUnavailableError("LLM runtime has no available model candidates")

    last_exc: Exception | None = None
    used_model = ""
    used_fallback = False
    call_started = time.perf_counter()

    def _candidate_parts(candidate: Any) -> dict[str, Any]:
        if isinstance(candidate, dict):
            return {
                "model": str(candidate.get("model") or "").strip(),
                "base_url": str(candidate.get("base_url") or cfg.settings.LLM_BASE_URL or "").rstrip("/"),
                "api_key": str(candidate.get("api_key") or cfg.settings.LLM_API_KEY or ""),
                "temperature": float(candidate.get("temperature", temperature) or temperature),
                "max_tokens": int(candidate.get("max_tokens", max_tokens) or max_tokens),
                "timeout": float(candidate.get("timeout", timeout_seconds) or timeout_seconds),
                "provider_id": str(candidate.get("id") or ""),
                "provider_name": str(candidate.get("name") or candidate.get("id") or ""),
            }
        return {
            "model": str(candidate or "").strip(),
            "base_url": str(cfg.settings.LLM_BASE_URL or "").rstrip("/"),
            "api_key": str(cfg.settings.LLM_API_KEY or ""),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout_seconds,
            "provider_id": "",
            "provider_name": "",
        }

    async def _send(req_client: httpx.AsyncClient, parts: dict[str, Any]) -> dict[str, Any]:
        llm_url = parts["base_url"] + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {parts['api_key']}",
        }
        payload = {
            "model": parts["model"],
            "temperature": parts["temperature"],
            "max_tokens": parts["max_tokens"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format:
            payload["response_format"] = response_format
        max_retries = 3
        for attempt in range(max_retries + 1):
            resp = await req_client.post(llm_url, json=payload, headers=headers)
            if resp.status_code != 429 or attempt == max_retries:
                if resp.status_code >= 400:
                    # Log the response body so 400/401/403 errors are diagnosable
                    try:
                        body_preview = resp.text[:500]
                    except Exception:
                        body_preview = "<unreadable>"
                    logger.error(
                        "LLM API error: status=%d url=%s model=%s body=%s",
                        resp.status_code, llm_url, parts.get("model", ""), body_preview,
                    )
                resp.raise_for_status()
                return resp.json()
            # Respect Retry-After header; fall back to exponential backoff
            retry_after = resp.headers.get("retry-after")
            if retry_after:
                try:
                    wait = min(float(retry_after), 30.0)
                except (ValueError, TypeError):
                    wait = 2.0 ** (attempt + 1)
            else:
                wait = 2.0 ** (attempt + 1)   # 2s, 4s, 8s
            logger.warning(
                "LLM 429 rate-limited (attempt %d/%d), retrying in %.1fs …",
                attempt + 1, max_retries, wait,
            )
            await asyncio.sleep(wait)
        # Should never reach here, but satisfy type checker
        raise RuntimeError("LLM retry loop exited unexpectedly")

    if client is None:
        req_client_ctx = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
    else:
        req_client_ctx = None

    try:
        req_client = client
        if req_client is None:
            req_client = await req_client_ctx.__aenter__()  # type: ignore[union-attr]
        async with _LLM_SEMAPHORE:
            for idx, candidate in enumerate(candidates):
                try:
                    parts = _candidate_parts(candidate)
                    data = await _send(req_client, parts)
                    used_model = parts["model"]
                    used_fallback = degraded_mode or (idx > 0) or (used_model == models_meta.get("fallback_model") and has_real_degrade)
                    await _FAILURE_TRACKER.record_success()
                    message = data["choices"][0].get("message") or {}
                    text = sanitize_llm_text(message.get("content") or "")
                    usage = data.get("usage") if isinstance(data, dict) else None
                    result = {
                        "text": text,
                        "usage": usage,
                        "model": used_model,
                        "degraded_mode": used_fallback,
                        "cache_hit": False,
                        "meta": {
                            "url": parts["base_url"] + "/chat/completions",
                            "primary_model": models_meta.get("primary_model"),
                            "fallback_model": models_meta.get("fallback_model"),
                            "provider_id": parts.get("provider_id"),
                            "provider_name": parts.get("provider_name"),
                            "provider_pool": models_meta.get("provider_pool", False),
                            "circuit_open": False,
                            "circuit_state": "half_open" if _FAILURE_TRACKER.half_open_probe_active else "closed",
                            "retry_after_seconds": retry_after_seconds,
                            "cache_key": cache_key,
                            "cache_hit": False,
                        },
                    }
                    await _set_cache(cache_key, ttl_seconds, result)
                    await _write_llm_call_log(
                        {
                            "cache_key": cache_key,
                            "model": used_model,
                            "provider_id": parts.get("provider_id"),
                            "provider_name": parts.get("provider_name"),
                            "status": "success",
                            "cache_hit": False,
                            "duration_ms": round((time.perf_counter() - call_started) * 1000, 1),
                            "degraded_mode": used_fallback,
                            "usage": usage,
                            "prompt_hash": cache_key,
                            "created_at": datetime.now(),
                        }
                    )
                    return result
                except Exception as e:
                    last_exc = e
                    if not degraded_mode and idx == 0 and _should_trip_breaker(e):
                        await _FAILURE_TRACKER.record_failure(
                            threshold=threshold,
                            cooldown_seconds=cooldown_seconds,
                            error=str(e),
                        )
                    continue
    finally:
        if req_client_ctx is not None:
            await req_client_ctx.__aexit__(None, None, None)

    if last_exc:
        await _write_llm_call_log(
            {
                "cache_key": cache_key,
                "model": used_model or model or "",
                "status": "error",
                "cache_hit": False,
                "duration_ms": round((time.perf_counter() - call_started) * 1000, 1),
                "degraded_mode": used_fallback,
                "error": str(last_exc)[:500],
                "created_at": datetime.now(),
            }
        )
        raise last_exc
    raise RuntimeError("LLM 调用失败")


async def llm_runtime_snapshot() -> dict[str, Any]:
    snapshot = await _FAILURE_TRACKER.snapshot()
    snapshot["cache_size"] = len(_LLM_CACHE)
    snapshot["concurrency_limit"] = _LLM_CONCURRENCY_LIMIT or None
    return snapshot
