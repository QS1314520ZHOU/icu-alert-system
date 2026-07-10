from __future__ import annotations

import logging
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.alert_engine.scanner_pics_risk import PicsRiskScanner
from app.services.followup_service import FollowupService
from app.utils.serialization import serialize_doc

router = APIRouter(tags=["followup"])
logger = logging.getLogger("icu-alert")


def _service() -> FollowupService:
    return FollowupService(db=runtime.db, config=runtime.config)


def _actor(request: Request, payload: dict[str, Any] | None = None) -> str:
    payload = payload or {}
    return (
        str(payload.get("actor") or "").strip()
        or request.headers.get("X-User-Id")
        or request.headers.get("x-user-id")
        or request.headers.get("x-operator-id")
        or "anonymous"
    )


async def _resolve_patient_doc(patient_id: str) -> dict[str, Any] | None:
    try:
        pid: Any = ObjectId(patient_id)
    except Exception:
        pid = patient_id
    return await runtime.db.col("patient").find_one({"_id": pid})


async def _ensure_pics_followup_case(patient_doc: dict[str, Any], *, refresh_pics: bool = False) -> dict[str, Any] | None:
    patient_id = str(patient_doc.get("_id") or "")
    service = _service()
    if refresh_pics or not await service.latest_pics_record(patient_id):
        scanner = PicsRiskScanner(runtime.alert_engine)
        try:
            await scanner.scan(patient_id)
        except Exception as exc:
            logger.warning("followup ensure pics scan failed patient_id=%s error=%s", patient_id, exc)
    return await service.ensure_case_from_latest_pics(patient_doc=patient_doc)


@router.get("/api/followup_cases")
async def list_followup_cases(
    status: str | None = Query(default=None),
    source_module: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
):
    rows = await _service().list_followup_cases(status=status, source_module=source_module, limit=limit)
    return {"code": 0, "rows": serialize_doc(rows)}


@router.get("/api/followup_cases/patients/{patient_id}")
async def get_patient_followup_case(
    patient_id: str,
    ensure_from_pics: bool = Query(default=True),
    refresh_pics: bool = Query(default=False),
):
    patient_doc = await _resolve_patient_doc(patient_id)
    if not patient_doc:
        return {"code": 404, "message": "患者不存在"}
    if ensure_from_pics:
        await _ensure_pics_followup_case(patient_doc, refresh_pics=refresh_pics)
    case_doc = await _service().get_patient_followup_case(str(patient_doc.get("_id") or ""))
    return {"code": 0, "case": serialize_doc(case_doc) if case_doc else None}


@router.get("/api/followup_cases/patients/{patient_id}/overview")
async def get_patient_followup_overview(
    patient_id: str,
    ensure_from_pics: bool = Query(default=True),
    refresh_pics: bool = Query(default=False),
):
    patient_doc = await _resolve_patient_doc(patient_id)
    if not patient_doc:
        return {"code": 404, "message": "患者不存在"}
    if ensure_from_pics:
        await _ensure_pics_followup_case(patient_doc, refresh_pics=refresh_pics)
    overview = await _service().build_patient_overview(patient_id=str(patient_doc.get("_id") or ""))
    return {"code": 0, **serialize_doc(overview)}


@router.post("/api/followup_cases/patients/{patient_id}")
async def upsert_patient_followup_case(
    patient_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default={}),
):
    patient_doc = await _resolve_patient_doc(patient_id)
    if not patient_doc:
        return {"code": 404, "message": "患者不存在"}
    if bool((payload or {}).get("refresh_pics")):
        await _ensure_pics_followup_case(patient_doc, refresh_pics=True)
    case_doc = await _service().enroll_case(
        patient_doc=patient_doc,
        source_module=str((payload or {}).get("source_module") or "pics_risk"),
        actor=_actor(request, payload),
        note=str((payload or {}).get("note") or "").strip(),
    )
    if not case_doc:
        return {"code": 400, "message": "当前未找到可纳入长期随访池的 PICS 风险记录，请先刷新 PICS 风险评估"}
    return {"code": 0, "case": serialize_doc(case_doc)}


@router.post("/api/followup_cases/{case_id}/status")
async def update_followup_case_status(
    case_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default={}),
):
    try:
        case_doc = await _service().update_case_status(
            case_id,
            status=str((payload or {}).get("status") or ""),
            actor=_actor(request, payload),
            note=str((payload or {}).get("note") or "").strip(),
        )
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    return {"code": 0, "case": serialize_doc(case_doc)}


@router.get("/api/followup_tasks/patients/{patient_id}")
async def get_patient_followup_tasks(
    patient_id: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
):
    patient_doc = await _resolve_patient_doc(patient_id)
    if not patient_doc:
        return {"code": 404, "message": "患者不存在"}
    rows = await _service().list_followup_tasks(patient_id=str(patient_doc.get("_id") or ""), status=status, limit=limit)
    return {"code": 0, "rows": serialize_doc(rows)}


@router.post("/api/followup_tasks/patients/{patient_id}")
async def create_patient_followup_task(
    patient_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default={}),
):
    patient_doc = await _resolve_patient_doc(patient_id)
    if not patient_doc:
        return {"code": 404, "message": "患者不存在"}
    payload = {**(payload or {}), "actor": _actor(request, payload)}
    try:
        task_doc = await _service().create_followup_task(patient_doc=patient_doc, payload=payload)
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    return {"code": 0, "task": serialize_doc(task_doc)}


@router.post("/api/followup_tasks/{task_id}/status")
async def update_followup_task_status(
    task_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default={}),
):
    try:
        task_doc = await _service().update_followup_task_status(
            task_id,
            status=str((payload or {}).get("status") or ""),
            actor=_actor(request, payload),
            note=str((payload or {}).get("note") or "").strip(),
        )
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    return {"code": 0, "task": serialize_doc(task_doc)}


@router.get("/api/rehab_referrals/patients/{patient_id}")
async def get_patient_rehab_referrals(
    patient_id: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
):
    patient_doc = await _resolve_patient_doc(patient_id)
    if not patient_doc:
        return {"code": 404, "message": "患者不存在"}
    rows = await _service().list_rehab_referrals(patient_id=str(patient_doc.get("_id") or ""), status=status, limit=limit)
    return {"code": 0, "rows": serialize_doc(rows)}


@router.post("/api/rehab_referrals/patients/{patient_id}")
async def create_patient_rehab_referral(
    patient_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default={}),
):
    patient_doc = await _resolve_patient_doc(patient_id)
    if not patient_doc:
        return {"code": 404, "message": "患者不存在"}
    payload = {**(payload or {}), "actor": _actor(request, payload)}
    try:
        referral_doc = await _service().create_rehab_referral(patient_doc=patient_doc, payload=payload)
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    return {"code": 0, "referral": serialize_doc(referral_doc)}


@router.post("/api/rehab_referrals/{referral_id}/status")
async def update_rehab_referral_status(
    referral_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default={}),
):
    try:
        referral_doc = await _service().update_rehab_referral_status(
            referral_id,
            status=str((payload or {}).get("status") or ""),
            actor=_actor(request, payload),
            note=str((payload or {}).get("note") or "").strip(),
            scheduled_at=(payload or {}).get("scheduled_at"),
        )
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    return {"code": 0, "referral": serialize_doc(referral_doc)}
