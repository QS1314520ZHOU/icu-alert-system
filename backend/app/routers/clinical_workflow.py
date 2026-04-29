from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.services.clinical_adoption_service import ClinicalAdoptionService
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/clinical-workflow", tags=["clinical-workflow"])


def _service() -> ClinicalAdoptionService:
    return ClinicalAdoptionService(runtime.db, alert_engine=runtime.alert_engine)


def _actor(request: Request) -> str:
    return request.headers.get("X-User-Id") or request.headers.get("x-operator-id") or "anonymous"


@router.get("/role-home")
async def role_home(
    role: str = Query("doctor"),
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
    userName: str | None = Query(None),
):
    result = await _service().role_home(role=role, dept=dept, dept_code=dept_code or deptCode, user_name=userName)
    return {"code": 0, **serialize_doc(result)}


@router.get("/patients/{patient_id}/story")
async def patient_story(patient_id: str, hours: int = Query(24, ge=6, le=72)):
    result = await _service().patient_story(patient_id, hours=hours)
    return {"code": 0, "story": serialize_doc(result)}


@router.get("/patients/{patient_id}/handoff")
async def patient_handoff(patient_id: str, role: str = Query("doctor"), hours: int = Query(12, ge=6, le=48)):
    result = await _service().handoff(patient_id, role=role, hours=hours)
    return {"code": 0, "handoff": serialize_doc(result)}


@router.get("/quality-summary")
async def quality_summary(
    days: int = Query(30, ge=7, le=90),
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
):
    result = await _service().quality_summary(days=days, dept=dept, dept_code=dept_code or deptCode)
    return {"code": 0, "summary": serialize_doc(result)}


@router.post("/tasks")
async def create_task(request: Request, payload: dict = Body(default={})):
    result = await _service().upsert_clinical_task(payload or {}, actor=_actor(request))
    return {"code": 0, **serialize_doc(result)}


@router.post("/tasks/{task_id}/close")
async def close_task(task_id: str, request: Request, payload: dict = Body(default={})):
    result = await _service().close_clinical_task(task_id, payload or {}, actor=_actor(request))
    return {"code": 0, **serialize_doc(result)}
