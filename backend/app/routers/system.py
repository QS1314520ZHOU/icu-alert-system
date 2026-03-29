from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter

from app import runtime

router = APIRouter()
logger = logging.getLogger("icu-alert")


async def _check_mongo() -> dict[str, Any]:
    try:
        t0 = time.monotonic()
        await asyncio.wait_for(
            runtime.db.client.admin.command("ping"),
            timeout=3.0,
        )
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_redis() -> dict[str, Any]:
    try:
        redis = getattr(runtime, "redis", None)
        if redis is None:
            return {"status": "unavailable", "detail": "not configured"}
        t0 = time.monotonic()
        await asyncio.wait_for(redis.ping(), timeout=2.0)
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_llm() -> dict[str, Any]:
    try:
        cfg = getattr(runtime, "config", None)
        if cfg is None:
            return {"status": "unknown"}
        base_url = str(getattr(cfg.settings, "LLM_BASE_URL", "") or "")
        api_key = str(getattr(cfg.settings, "LLM_API_KEY", "") or "")
        if not base_url:
            return {"status": "not_configured"}
        import httpx
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=4.0) as client:
            probe_url = base_url.rstrip("/") + "/models"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key not in {"", "your_api_key"} else {}
            r = await client.get(probe_url, headers=headers)
        latency = round((time.monotonic() - t0) * 1000, 1)
        if r.status_code < 500:
            return {"status": "ok", "latency_ms": latency}
        return {"status": "degraded", "http_status": r.status_code, "latency_ms": latency}
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


@router.get("/health")
async def health_check():
    """
    组件健康检查。
    llm.status 为 degraded 时系统以纯规则模式运行，其余功能不受影响。
    """
    mongo, redis, llm = await asyncio.gather(
        _check_mongo(),
        _check_redis(),
        _check_llm(),
        return_exceptions=False,
    )

    engine = getattr(runtime, "alert_engine", None)
    task_list = getattr(engine, "_tasks", None) if engine else None
    scanners_running = bool(task_list and any(not getattr(t, "done", lambda: True)() for t in task_list))

    overall = "ok"
    if mongo["status"] != "ok":
        overall = "degraded"
    if redis["status"] == "error":
        overall = "degraded"

    return {
        "status": overall,
        "components": {
            "api": "ok",
            "mongo": mongo,
            "redis": redis,
            "llm": llm,
        },
        "scanners_running": scanners_running,
    }
