"""
Handover — API Router.

Endpoints for generating, editing, confirming, acknowledging, and reviewing
AI-assisted ISBAR structured handover documents.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from app.runtime import ConfigDep, DbDep
from app.services.handover.alert_bridge import HandoverAlertBridge
from app.services.handover.audit_service import HandoverAuditService
from app.services.handover.brief_renderer import HandoverBriefRenderer
from app.services.handover.context_service import HandoverContextService
from app.services.handover.generation_service import HandoverGenerationService
from app.services.handover.schemas import (
    AcknowledgeRequest,
    ConfirmRequest,
    GenerateRequest,
    HandoverDocument,
    HandoverStatus,
    ISbarSections,
    RejectRequest,
    UpdateContentRequest,
)
from app.services.shift_service import ShiftService
from app.utils.serialization import serialize_doc

API_TZ = ZoneInfo("Asia/Shanghai")
router = APIRouter(prefix="/api/handover", tags=["handover"])
logger = logging.getLogger("icu-alert")

COLLECTION = "handover_documents"


def _now() -> str:
    return datetime.now(API_TZ).isoformat()


# ── Generate Draft ──────────────────────────────────────────────────

@router.post("/generate")
async def generate_handover(req: GenerateRequest, db: DbDep, cfg: ConfigDep):
    """Generate an AI-drafted ISBAR handover document for a patient.

    Flow: query DB context → call LLM → save draft → return document.
    """
    context_svc = HandoverContextService(db)
    gen_svc = HandoverGenerationService(db, cfg)
    shift_svc = ShiftService(db)

    # Resolve shift time window
    shift = None
    time_start: datetime
    time_end: datetime
    try:
        resolved = await shift_svc.resolve_shift(req.shift_code or "auto")
        if resolved:
            time_start = resolved.start.replace(tzinfo=None)
            time_end = resolved.end.replace(tzinfo=None)
            shift = resolved.to_dict()
        else:
            # Fallback: last 8 hours
            now_dt = datetime.now()
            time_end = now_dt
            time_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            shift = {"code": "auto", "name": "自动", "start_time": time_start.strftime("%H:%M"), "end_time": time_end.strftime("%H:%M")}
    except Exception:
        now_dt = datetime.now()
        time_end = now_dt
        time_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        shift = {"code": "auto", "name": "自动"}

    # Build context (query DB first — 先查后写)
    try:
        context = await context_svc.build(req.patient_id, time_start, time_end, shift)
    except Exception as exc:
        logger.exception("Failed to build handover context for patient %s", req.patient_id)
        raise HTTPException(status_code=500, detail=f"数据查询失败: {exc}")

    # Generate AI draft
    try:
        doc = await gen_svc.generate(context, req.handover_type)
    except Exception as exc:
        logger.exception("LLM generation failed for patient %s", req.patient_id)
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {exc}")

    # Persist
    doc_dict = doc.model_dump()
    doc_dict["_created"] = _now()
    try:
        await db.col(COLLECTION).insert_one(doc_dict)
    except Exception as exc:
        logger.exception("Failed to save handover document")
        raise HTTPException(status_code=500, detail=f"保存失败: {exc}")

    return {"code": 0, "handover": serialize_doc(doc_dict)}


# ── Get Single Handover ─────────────────────────────────────────────

@router.get("/{handover_id}")
async def get_handover(handover_id: str, db: DbDep):
    """Retrieve a single handover document by ID."""
    doc = await db.col(COLLECTION).find_one({"handover_id": handover_id})
    if not doc:
        raise HTTPException(status_code=404, detail="交班记录不存在")
    return {"code": 0, "handover": serialize_doc(doc)}


# ── Patient History ─────────────────────────────────────────────────

@router.get("/patients/{patient_id}/history")
async def get_patient_history(
    patient_id: str,
    db: DbDep,
    limit: int = Query(20, ge=1, le=100),
    handover_type: Optional[str] = Query(None),
):
    """List handover history for a patient."""
    query: dict = {"patient_id": patient_id}
    if handover_type:
        query["handover_type"] = handover_type
    cursor = db.col(COLLECTION).find(query).sort("created_at", -1).limit(limit)
    docs = [serialize_doc(d) async for d in cursor]
    return {"code": 0, "handovers": docs, "total": len(docs)}


# ── Edit Content ────────────────────────────────────────────────────

@router.put("/{handover_id}/content")
async def update_handover_content(handover_id: str, req: UpdateContentRequest, db: DbDep):
    """Manually edit handover content (AI draft → human modified)."""
    doc = await db.col(COLLECTION).find_one({"handover_id": handover_id})
    if not doc:
        raise HTTPException(status_code=404, detail="交班记录不存在")

    handover = HandoverDocument(**doc)
    if handover.status == HandoverStatus.ACKNOWLEDGED:
        raise HTTPException(status_code=400, detail="已签收的交班记录不可直接修改，请重新生成新版本")

    # Update sections
    try:
        new_sections = ISbarSections(**req.sections)
        handover.sections = new_sections
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"字段格式错误: {exc}")

    # Track field sources
    audit = HandoverAuditService(db)
    operator = ""  # Could extract from auth context
    audit.mark_field_sources(handover, req.edited_fields, operator)

    handover.updated_at = _now()

    update_dict = handover.model_dump()
    await db.col(COLLECTION).replace_one({"handover_id": handover_id}, update_dict)

    return {"code": 0, "handover": serialize_doc(update_dict)}


# ── Confirm / Submit ────────────────────────────────────────────────

@router.post("/{handover_id}/confirm")
async def confirm_handover(handover_id: str, req: ConfirmRequest, db: DbDep):
    """Submit handover for acknowledgment (draft → submitted)."""
    doc = await db.col(COLLECTION).find_one({"handover_id": handover_id})
    if not doc:
        raise HTTPException(status_code=404, detail="交班记录不存在")

    handover = HandoverDocument(**doc)
    audit = HandoverAuditService(db)

    try:
        # Save version snapshot
        data_snapshot = {
            "sections": handover.sections.model_dump(),
            "data_snapshot_at": handover.data_snapshot_at,
        }
        audit.append_version(handover, data_snapshot, None, req.operator, "提交确认")
        audit.transition(handover, HandoverStatus.SUBMITTED, operator=req.operator)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    handover.updated_at = _now()
    update_dict = handover.model_dump()
    await db.col(COLLECTION).replace_one({"handover_id": handover_id}, update_dict)

    await audit.log_event(handover_id, handover.patient_id, "confirmed", req.operator)

    return {"code": 0, "handover": serialize_doc(update_dict)}


# ── Acknowledge ─────────────────────────────────────────────────────

@router.post("/{handover_id}/acknowledge")
async def acknowledge_handover(handover_id: str, req: AcknowledgeRequest, db: DbDep):
    """Acknowledge handover (submitted → acknowledged). Freezes content."""
    doc = await db.col(COLLECTION).find_one({"handover_id": handover_id})
    if not doc:
        raise HTTPException(status_code=404, detail="交班记录不存在")

    handover = HandoverDocument(**doc)
    audit = HandoverAuditService(db)

    # Update forced confirmations
    audit.update_forced_confirmations(handover, req.forced_confirmations, req.operator)

    # Check all forced items confirmed
    if not audit.all_forced_confirmed(handover):
        raise HTTPException(status_code=400, detail="请先确认所有强制交接项（危急值/高危管路/血管活性药/特殊隔离/未处理预警/紧急升级条件）")

    try:
        audit.transition(handover, HandoverStatus.ACKNOWLEDGED, operator=req.operator)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    handover.updated_at = _now()
    update_dict = handover.model_dump()
    await db.col(COLLECTION).replace_one({"handover_id": handover_id}, update_dict)

    await audit.log_event(handover_id, handover.patient_id, "acknowledged", req.operator)

    return {"code": 0, "handover": serialize_doc(update_dict)}


# ── Reject / Return ─────────────────────────────────────────────────

@router.post("/{handover_id}/reject")
async def reject_handover(handover_id: str, req: RejectRequest, db: DbDep):
    """Reject a submitted handover back to draft for revision."""
    doc = await db.col(COLLECTION).find_one({"handover_id": handover_id})
    if not doc:
        raise HTTPException(status_code=404, detail="交班记录不存在")

    handover = HandoverDocument(**doc)
    audit = HandoverAuditService(db)

    try:
        audit.transition(handover, HandoverStatus.DRAFT, operator=req.operator, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    handover.updated_at = _now()
    update_dict = handover.model_dump()
    await db.col(COLLECTION).replace_one({"handover_id": handover_id}, update_dict)

    await audit.log_event(handover_id, handover.patient_id, "rejected", req.operator, {"reason": req.reason})

    return {"code": 0, "handover": serialize_doc(update_dict)}


# ── Deterministic Brief ─────────────────────────────────────────────

@router.get("/{handover_id}/brief")
async def get_handover_brief(
    handover_id: str,
    db: DbDep,
    mode: str = Query("full", description="full | compact | ward"),
):
    """Render a deterministic handover brief (no LLM involved)."""
    doc = await db.col(COLLECTION).find_one({"handover_id": handover_id})
    if not doc:
        raise HTTPException(status_code=404, detail="交班记录不存在")

    handover = HandoverDocument(**doc)
    renderer = HandoverBriefRenderer()
    brief = renderer.render(handover.sections, mode=mode, handover_type=handover.handover_type)

    return {
        "code": 0,
        "handover_id": handover_id,
        "patient_id": handover.patient_id,
        "mode": mode,
        "brief": brief,
    }


# ── Alert Bridge ────────────────────────────────────────────────────

@router.get("/patients/{patient_id}/forced-alerts")
async def get_forced_alerts(
    patient_id: str,
    db: DbDep,
    since: Optional[str] = Query(None, description="ISO datetime start"),
    until: Optional[str] = Query(None, description="ISO datetime end"),
):
    """Get critical/unclosed alerts that must be forced into handover R section."""
    bridge = HandoverAlertBridge(db)

    # Default to last 8 hours if no time range given
    now_dt = datetime.now()
    start = datetime.fromisoformat(since) if since else now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end = datetime.fromisoformat(until) if until else now_dt

    forced = await bridge.build_forced_confirmations(patient_id, start, end)

    return {"code": 0, "patient_id": patient_id, "forced_confirmations": forced, "total": len(forced)}
