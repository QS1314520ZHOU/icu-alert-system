from __future__ import annotations

from fastapi import APIRouter, Body, Request

from app.services.clinical_trial_service import (
    create_trial,
    delete_trial,
    get_trial,
    list_candidates,
    list_trials,
    parse_criteria,
    patient_matches,
    screen_patients,
    set_trial_active,
    update_candidate_status,
    update_trial,
)

router = APIRouter(prefix="/api/clinical-trials", tags=["clinical-trials"])


def _actor(request: Request) -> str:
    return request.headers.get("X-User-Id") or request.headers.get("x-operator-id") or "anonymous"


@router.get("")
async def clinical_trials():
    return {"code": 0, **await list_trials()}


@router.post("")
async def add_clinical_trial(request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await create_trial(payload or {}, _actor(request))}


@router.post("/screen")
async def screen_trials():
    return {"code": 0, **await screen_patients()}


@router.get("/candidates")
async def trial_candidates():
    return {"code": 0, **await list_candidates()}


@router.get("/patients/{patient_id}/matches")
async def trial_patient_matches(patient_id: str):
    return {"code": 0, **await patient_matches(patient_id)}


@router.post("/candidates/{candidate_id}/status")
async def candidate_status(candidate_id: str, request: Request, payload: dict = Body(default={})):
    return await update_candidate_status(candidate_id, payload or {}, _actor(request))


@router.get("/{trial_id}")
async def clinical_trial(trial_id: str):
    return {"code": 0, **await get_trial(trial_id)}


@router.put("/{trial_id}")
async def save_clinical_trial(trial_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await update_trial(trial_id, payload or {}, _actor(request))}


@router.delete("/{trial_id}")
async def remove_clinical_trial(trial_id: str):
    return {"code": 0, **await delete_trial(trial_id)}


@router.post("/{trial_id}/parse-criteria")
async def parse_trial_criteria(trial_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await parse_criteria(trial_id, payload or {}, _actor(request))}


@router.post("/{trial_id}/activate")
async def activate_trial(trial_id: str, request: Request):
    return {"code": 0, **await set_trial_active(trial_id, True, _actor(request))}


@router.post("/{trial_id}/deactivate")
async def deactivate_trial(trial_id: str, request: Request):
    return {"code": 0, **await set_trial_active(trial_id, False, _actor(request))}
