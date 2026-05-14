from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.services.clinical_adoption_service import ClinicalAdoptionService
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/clinical-workflow", tags=["clinical-workflow"])
_ACCOUNT_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
_ACCOUNT_CACHE_TTL = timedelta(minutes=5)


def _service() -> ClinicalAdoptionService:
    return ClinicalAdoptionService(runtime.db, alert_engine=runtime.alert_engine)


def _actor(request: Request) -> str:
    return request.headers.get("X-User-Id") or request.headers.get("x-operator-id") or "anonymous"


def _account_cache_key(user_name: str | None, role: str | None, dept: str | None, dept_code: str | None) -> str:
    return "|".join([str(user_name or ""), str(role or ""), str(dept or ""), str(dept_code or "")])


def _fallback_account(user_name: str | None, role: str | None, dept: str | None, dept_code: str | None) -> dict[str, Any]:
    account = {
        "userName": user_name or "",
        "display_name": user_name or "",
        "role": role or "doctor",
        "found": False,
        "fast_fallback": True,
    }
    if dept_code:
        account["dept_code"] = dept_code
    if dept:
        account["dept"] = dept
    return account


async def _resolve_account_fast(user_name: str | None, role: str | None, dept: str | None, dept_code: str | None, timeout: float = 0.12) -> dict[str, Any]:
    key = _account_cache_key(user_name, role, dept, dept_code)
    cached = _ACCOUNT_CACHE.get(key)
    now = datetime.now()
    if cached and cached[0] > now:
        return dict(cached[1])
    fallback = _fallback_account(user_name, role, dept, dept_code)
    if runtime.db is None or not user_name:
        return fallback
    try:
        account = await asyncio.wait_for(_service().resolve_account(user_name, fallback_role=role or "doctor"), timeout=timeout)
    except Exception:
        return fallback
    if dept_code and not account.get("dept_code"):
        account["dept_code"] = dept_code
    if dept and not account.get("dept"):
        account["dept"] = dept
    account["fast_fallback"] = False
    _ACCOUNT_CACHE[key] = (now + _ACCOUNT_CACHE_TTL, dict(account))
    return account


@router.get("/role-home")
async def role_home(
    role: str | None = Query(None),
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
    userName: str | None = Query(None),
):
    result = await _service().role_home(role=role, dept=dept, dept_code=dept_code or deptCode, user_name=userName)
    return {"code": 0, **serialize_doc(result)}


@router.get("/account")
async def account(
    role: str | None = Query(None),
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
    userName: str | None = Query(None),
):
    fallback_dept_code = dept_code or deptCode
    account = await _resolve_account_fast(userName, role or "doctor", dept, fallback_dept_code, timeout=1.2)
    return {"code": 0, "account": serialize_doc(account)}


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
