from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import runtime

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("icu-alert")


class ScannerTriggerRequest(BaseModel):
    scanner_name: str
    patient_id: str | None = None


@router.post("/scanner/trigger")
async def trigger_scanner(req: ScannerTriggerRequest):
    """
    手动立即触发某个 Scanner 执行一次，忽略调度间隔。
    用于调试或紧急情况。
    """
    alert_engine = runtime.alert_engine
    if alert_engine is None:
        raise HTTPException(status_code=503, detail="AlertEngine not initialized")

    # 从 AlertEngine 的活跃 scanner 列表中查找目标
    active_scanners = alert_engine._active_scanners()
    scanner_map = {s.name: s for s in active_scanners}

    scanner = scanner_map.get(req.scanner_name)
    if scanner is None:
        available = sorted(scanner_map.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Scanner '{req.scanner_name}' not found. Available: {available}"
        )

    try:
        logger.info("[admin] 手动触发 scanner: %s (patient_id=%s)", req.scanner_name, req.patient_id)
        await scanner.scan()
        return {"status": "ok", "scanner": req.scanner_name, "message": "Scanner executed successfully"}
    except Exception as exc:
        logger.exception("[admin] 手动触发 scanner %s 失败: %s", req.scanner_name, exc)
        raise HTTPException(status_code=500, detail=f"Scanner execution failed: {exc}")
