from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter

from app import runtime
from app.services.runtime_config_service import DEFAULT_TRAJECTORY_FORECAST_CONFIG
from app.utils.serialization import serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")
_trajectory_public_cache: tuple[float, dict[str, Any]] | None = None


def _clamp_horizon(value: Any, default: int = 6) -> int:
    try:
        horizon = int(value or default)
    except Exception:
        horizon = default
    return max(1, min(horizon, 12))


def _public_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"false", "0", "no", "off", "disabled"}:
        return False
    if text in {"true", "1", "yes", "on", "enabled"}:
        return True
    return default


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


@router.get("/api/runtime/public-config/trajectory")
async def trajectory_public_config():
    global _trajectory_public_cache
    now = time.monotonic()
    if _trajectory_public_cache and now - _trajectory_public_cache[0] < 300:
        return serialize_doc(_trajectory_public_cache[1])

    cfg = dict(DEFAULT_TRAJECTORY_FORECAST_CONFIG)
    try:
        doc = await runtime.db.col("runtime_configs").find_one({"key": "trajectory_forecast"})
        if doc and isinstance(doc.get("value"), dict):
            cfg.update(doc["value"])
    except Exception as exc:
        logger.warning("load public trajectory config fallback to defaults: %s", exc)

    payload = {
        "code": 0,
        "enabled": _public_bool(cfg.get("enabled"), True),
        "horizon_hours": _clamp_horizon(cfg.get("horizon_hours")),
        "default_codes": [str(code) for code in (cfg.get("default_codes") or [])],
        "cached_seconds": 300,
    }
    _trajectory_public_cache = (now, payload)
    return serialize_doc(payload)
