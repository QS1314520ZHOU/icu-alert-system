from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request

from app.services.respiratory_service import (
    create_airway_record,
    get_airway_plan,
    list_airway_records,
    list_sbt_candidates,
    list_ventilated_patients,
    update_sbt_status,
    upsert_airway_plan,
    ventilator_timeline,
)

router = APIRouter(prefix="/api/respiratory", tags=["respiratory"])


def _actor(request: Request) -> str:
    return request.headers.get("X-User-Id") or request.headers.get("x-operator-id") or "anonymous"


@router.get("/ventilated-patients")
async def ventilated_patients():
    return {"code": 0, **await list_ventilated_patients()}


@router.get("/sbt-candidates")
async def sbt_candidates():
    return {"code": 0, **await list_sbt_candidates()}


@router.post("/sbt/{patient_id}/status")
async def sbt_status(patient_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await update_sbt_status(patient_id, payload or {}, _actor(request))}


@router.get("/{patient_id}/ventilator-timeline")
async def patient_ventilator_timeline(patient_id: str, hours: int = Query(72, ge=24, le=168)):
    return await ventilator_timeline(patient_id, hours)


@router.get("/{patient_id}/airway-records")
async def airway_records(patient_id: str):
    return {"code": 0, **await list_airway_records(patient_id)}


@router.post("/{patient_id}/airway-records")
async def add_airway_record(patient_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await create_airway_record(patient_id, payload or {}, _actor(request))}


@router.get("/{patient_id}/airway-plan")
async def airway_plan(patient_id: str):
    return {"code": 0, **await get_airway_plan(patient_id)}


@router.post("/{patient_id}/airway-plan")
async def save_airway_plan(patient_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await upsert_airway_plan(patient_id, payload or {}, _actor(request))}
