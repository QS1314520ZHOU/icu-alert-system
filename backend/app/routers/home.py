from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.services.home_service import RoleHomeService
from app.services.shift_service import ShiftService
from app.utils.api_llm import call_api_llm
from app.utils.serialization import serialize_doc

router = APIRouter(tags=["role-home"])


def _service() -> RoleHomeService:
    return RoleHomeService(
        runtime.db,
        config=runtime.config,
        ai_handoff_service=runtime.ai_handoff_service,
        llm_call=lambda system_prompt, user_prompt, model=None: call_api_llm(system_prompt, user_prompt, model),
    )


def _actor(request: Request, fallback: str = "") -> str:
    return (
        request.headers.get("X-User-Id")
        or request.headers.get("x-user-id")
        or request.headers.get("x-operator-id")
        or fallback
        or "anonymous"
    )


@router.get("/api/home/doctor")
async def doctor_home(user_id: str = Query(...)):
    result = await _service().doctor_home(user_id)
    return {"code": 0, "data": serialize_doc(result)}


@router.get("/api/home/nurse")
async def nurse_home(
    user_id: str = Query(...),
    shift_code: str = Query("auto"),
    view: str | None = Query(None),
):
    result = await _service().nurse_home(user_id, shift_code=shift_code, view=view)
    return {"code": 0, "data": serialize_doc(result)}


@router.get("/api/home/nurse/timeline")
async def nurse_timeline(user_id: str = Query(...), shift_code: str = Query("auto")):
    result = await _service().nurse_timeline(user_id, shift_code=shift_code)
    return {"code": 0, "data": serialize_doc(result)}


@router.get("/api/home/nurse/bundles")
async def nurse_bundles(patient_ids: str = Query(""), shift_code: str = Query("auto")):
    ids = [item.strip() for item in str(patient_ids or "").split(",") if item.strip()]
    result = await _service().nurse_bundles(ids, shift_code=shift_code)
    return {"code": 0, "data": serialize_doc(result)}


@router.post("/api/home/nurse/task/{task_id}/execute")
async def execute_nurse_task(task_id: str, request: Request, payload: dict = Body(default={})):
    actor = _actor(request, str((payload or {}).get("actor") or ""))
    result = await _service().execute_nurse_task(task_id, payload or {}, actor)
    return {"code": 0, "data": serialize_doc(result)}


@router.post("/api/home/nurse/handoff/generate")
async def generate_nurse_handoff(request: Request, payload: dict = Body(default={})):
    user_id = str((payload or {}).get("user_id") or _actor(request)).strip()
    patient_ids = (payload or {}).get("patient_ids")
    if not isinstance(patient_ids, list):
        patient_ids = []
    result = await _service().generate_nurse_handoff(
        user_id,
        [str(item) for item in patient_ids if str(item or "").strip()],
        shift_code=str((payload or {}).get("shift_code") or "auto"),
    )
    return {"code": 0, "data": serialize_doc(result)}


@router.get("/api/shift/current")
async def current_shift():
    result = await ShiftService(runtime.db).get_current_shift()
    return {"code": 0, "data": serialize_doc(result.to_dict() if result else None)}


@router.get("/api/shift/list")
async def shift_list(refresh: bool = Query(False)):
    service = ShiftService(runtime.db)
    result = await service.refresh_cache() if refresh else await service.list_shifts()
    return {"code": 0, "data": serialize_doc(result)}
