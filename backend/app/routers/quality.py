"""Bundle 合规评分 API。"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query

from app import runtime
from app.services.bundle_compliance_service import BundleComplianceService
from app.utils.serialization import serialize_doc

router = APIRouter(tags=["quality"])
logger = logging.getLogger("icu-alert")


def _service() -> BundleComplianceService:
    return BundleComplianceService(runtime.db, runtime.config)


@router.get("/api/quality/bundle-compliance")
async def bundle_compliance(
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
):
    service = _service()
    resolved_dept_code = dept_code or deptCode

    try:
        result = await asyncio.wait_for(
            service.daily_summary(dept=dept, dept_code=resolved_dept_code),
            timeout=25.0,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "bundle-compliance daily_summary timeout, falling back to stale cache dept=%s dept_code=%s",
            dept, resolved_dept_code,
        )
        # 尝试读取过期缓存（不限 1 小时）
        from datetime import datetime
        from app.services.bundle_compliance_service import API_TZ, _dt, _as_api_tz
        today = datetime.now(API_TZ).strftime("%Y-%m-%d")
        cache_filter = {"date": today, "dept": dept or "", "deptCode": resolved_dept_code or ""}
        stale = await runtime.db.col("bundle_compliance_daily").find_one(cache_filter)
        if stale:
            stale.pop("_id", None)
            stale["_degraded"] = True
            stale["_degraded_reason"] = "timeout_stale_cache"
            result = stale
        else:
            result = service._empty_summary(today, dept, resolved_dept_code)
            result["_degraded"] = True
            result["_degraded_reason"] = "timeout_no_cache"
    except Exception as exc:
        logger.warning("bundle-compliance error fallback dept=%s error=%s", dept, exc)
        from datetime import datetime
        from app.services.bundle_compliance_service import API_TZ
        today = datetime.now(API_TZ).strftime("%Y-%m-%d")
        result = service._empty_summary(today, dept, resolved_dept_code)
        result["_degraded"] = True
        result["_degraded_reason"] = "exception"

    return {"code": 0, "data": serialize_doc(result)}


@router.get("/api/quality/bundle-compliance/patient/{patient_id}")
async def patient_bundle_compliance(patient_id: str):
    service = _service()

    try:
        result = await asyncio.wait_for(
            service.evaluate_patient(patient_id),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.warning("patient bundle-compliance timeout patient_id=%s", patient_id)
        result = {
            "patient_id": patient_id,
            "_degraded": True,
            "_degraded_reason": "timeout",
            "abcdef": {"items": {}, "compliance": 0, "tone": "red"},
            "vap": {"items": {}, "compliance": 0, "tone": "red"},
            "clabsi": {"items": {}, "compliance": 0, "tone": "red"},
            "cauti": {"items": {}, "compliance": 0, "tone": "red"},
        }
    except Exception as exc:
        logger.warning("patient bundle-compliance error patient_id=%s error=%s", patient_id, exc)
        result = {
            "patient_id": patient_id,
            "_degraded": True,
            "_degraded_reason": "exception",
            "abcdef": {"items": {}, "compliance": 0, "tone": "red"},
            "vap": {"items": {}, "compliance": 0, "tone": "red"},
            "clabsi": {"items": {}, "compliance": 0, "tone": "red"},
            "cauti": {"items": {}, "compliance": 0, "tone": "red"},
        }

    return {"code": 0, "data": serialize_doc(result)}
