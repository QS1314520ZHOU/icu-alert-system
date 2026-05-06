from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import runtime
from app.services.admin_quality_service import admin_quality_summary
from app.services.alert_outcome_service import AlertOutcomeService
from app.services.model_calibration_runtime import ModelCalibrationRuntime
from app.services.outcome_inference_worker import OutcomeInferenceWorker
from app.services.runtime_config_service import RuntimeConfigService
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("icu-alert")


class ScannerTriggerRequest(BaseModel):
    scanner_name: str
    patient_id: str | None = None


def _actor() -> str:
    return "admin"


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


@router.get("/scanner-health")
async def scanner_health(
    days: int = 30,
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await AlertOutcomeService(runtime.db).scanner_health(days=max(min(int(days or 30), 90), 1), dept=dept, dept_code=dept_code or deptCode)
    if not result.get("rows") and runtime.alert_engine is not None:
        scanners = []
        for scanner in runtime.alert_engine._active_scanners():
            scanners.append(
                {
                    "scanner_name": getattr(scanner, "name", scanner.__class__.__name__),
                    "fired_count": 0,
                    "ppv": 0,
                    "override_rate": 0,
                    "median_time_to_action_minutes": None,
                    "event_24h_rate": 0,
                    "nnt": None,
                    "drift_status": "green",
                    "review_suggestion": False,
                    "threshold_advice": "",
                    "recent_overrides": [],
                }
            )
        result = {"days": result.get("days") or days, "source": "registered_scanners", "rows": scanners, "total_scanners": len(scanners)}
    return {"code": 0, **serialize_doc(result)}


@router.get("/quality-closed-loop")
async def quality_closed_loop(
    days: int = 30,
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    return {"code": 0, **await admin_quality_summary(runtime.db, days=days, dept=dept, dept_code=dept_code or deptCode)}


@router.post("/scanner-health/recalculate")
async def recalculate_scanner_health(days: int = 30):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await ModelCalibrationRuntime(runtime.db).run_daily(days=max(min(int(days or 30), 90), 1))
    return {"code": 0, "record": serialize_doc(result)}


@router.post("/scanner-health/infer-outcomes")
async def infer_alert_outcomes(limit: int = 200, min_age_minutes: int = 30):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await OutcomeInferenceWorker(runtime.db).run_once(
        limit=max(min(int(limit or 200), 1000), 1),
        min_age_minutes=max(int(min_age_minutes or 30), 0),
    )
    return {"code": 0, "result": serialize_doc(result)}


@router.get("/runtime-config")
async def runtime_config_overview():
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await RuntimeConfigService(runtime.db).overview()
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/modules")
async def update_runtime_modules(payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await RuntimeConfigService(runtime.db).update_modules(payload.get("modules") or [], actor=_actor())
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/ai")
async def update_runtime_ai(payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await RuntimeConfigService(runtime.db).update_ai(payload or {}, actor=_actor())
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/alert-rules/{rule_id}")
async def update_runtime_alert_rule(rule_id: str, payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    result = await RuntimeConfigService(runtime.db).update_alert_rule(rule_id, payload or {}, actor=_actor())
    return {"code": 0, **serialize_doc(result)}


@router.post("/runtime-config/field-mapping")
async def update_runtime_field_mapping(payload: dict):
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    try:
        result = await RuntimeConfigService(runtime.db).update_field_mapping(payload or {}, actor=_actor())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"code": 0, **serialize_doc(result)}
