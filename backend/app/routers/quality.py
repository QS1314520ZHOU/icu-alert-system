"""Bundle 合规评分 API。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app import runtime
from app.services.bundle_compliance_service import BundleComplianceService
from app.utils.serialization import serialize_doc

router = APIRouter(tags=["quality"])


def _service() -> BundleComplianceService:
    return BundleComplianceService(runtime.db, runtime.config)


@router.get("/api/quality/bundle-compliance")
async def bundle_compliance(
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
):
    result = await _service().daily_summary(dept=dept, dept_code=dept_code or deptCode)
    return {"code": 0, "data": serialize_doc(result)}


@router.get("/api/quality/bundle-compliance/patient/{patient_id}")
async def patient_bundle_compliance(patient_id: str):
    result = await _service().evaluate_patient(patient_id)
    return {"code": 0, "data": serialize_doc(result)}
