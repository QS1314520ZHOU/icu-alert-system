"""监控路由。"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.monitoring import get_metrics

router = APIRouter(prefix="/monitoring", tags=["监控"])


@router.get("/metrics")
async def metrics():
    """Prometheus 指标端点。"""
    return Response(
        content=get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@router.get("/health")
async def health_check():
    """健康检查。"""
    return {
        "status": "healthy",
        "service": "icu-alert-system",
        "version": "1.0.0",
    }


@router.get("/ready")
async def readiness_check():
    """就绪检查。"""
    # TODO: 检查数据库连接、Redis 连接等
    return {
        "status": "ready",
        "checks": {
            "database": "ok",
            "redis": "ok",
        }
    }
