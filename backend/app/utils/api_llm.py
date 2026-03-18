from __future__ import annotations

import time

from app import runtime
from app.config import get_config
from app.services.llm_runtime import call_llm_chat


async def call_api_llm(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
    """统一调用 API 侧 LLM，并写入监控。"""
    cfg = get_config()
    start = time.perf_counter()
    text = ""
    usage = None
    llm_model = ""
    meta = {}
    try:
        result = await call_llm_chat(
            cfg=cfg,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model or cfg.llm_model_medical or cfg.settings.LLM_MODEL,
            temperature=0.1,
            max_tokens=4096,
            timeout_seconds=60,
        )
        text = str(result.get("text") or "")
        usage = result.get("usage")
        llm_model = str(result.get("model") or "")
        meta = result.get("meta") or {}
    except Exception:
        if runtime.ai_monitor:
            await runtime.ai_monitor.log_llm_call(
                module="api_llm",
                model=llm_model or (model or cfg.llm_model_medical or cfg.settings.LLM_MODEL),
                prompt=(system_prompt or "") + "\n\n" + (user_prompt or ""),
                output=text,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                success=False,
                meta=meta or {"url": cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"},
                usage=usage,
            )
        raise

    if runtime.ai_monitor:
        await runtime.ai_monitor.log_llm_call(
            module="api_llm",
            model=llm_model or (model or cfg.llm_model_medical or cfg.settings.LLM_MODEL),
            prompt=(system_prompt or "") + "\n\n" + (user_prompt or ""),
            output=text,
            latency_ms=(time.perf_counter() - start) * 1000.0,
            success=True,
            meta=meta or {"url": cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"},
            usage=usage,
        )
    return text
