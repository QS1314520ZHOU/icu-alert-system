"""
Clinical Documents — API Router.

Endpoints for generating, viewing, editing, finalizing, and exporting
AI-assisted clinical documents (SOAP progress notes).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.runtime import DbDep, ConfigDep

router = APIRouter(prefix="/api/clinical-documents", tags=["clinical-documents"])

logger = logging.getLogger("icu-alert")

COLLECTION_DRAFTS = "clinical_document_drafts"
COLLECTION_VERSIONS = "clinical_document_versions"


# ── Request / Response models ────────────────────────────────────────

class GenerateRequest(BaseModel):
    patient_id: str
    doc_type: str = "progress_note_24h"
    hours: int = 24


class UpdateDraftRequest(BaseModel):
    content: dict


class FinalizeRequest(BaseModel):
    signer: str


class ExportRequest(BaseModel):
    format: str = "docx"


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/generate")
async def generate(req: GenerateRequest, db: DbDep, cfg: ConfigDep):
    """Generate an AI-drafted progress note for a patient."""
    from app.clinical_documents.context_builder import ProgressNoteContextBuilder
    from app.clinical_documents.document_generator import ProgressNoteGenerator

    try:
        builder = ProgressNoteContextBuilder(db)
        ctx = await builder.build(req.patient_id, req.hours)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("构建病程上下文失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"构建上下文失败: {exc}")

    try:
        generator = ProgressNoteGenerator(cfg)
        result = await generator.generate(ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("LLM 生成病程记录失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI 生成失败: {exc}")

    # Persist draft
    draft_id = str(uuid.uuid4())
    draft_doc = {
        "_id": draft_id,
        "patient_id": req.patient_id,
        "doc_type": req.doc_type,
        "status": "draft",
        "ai_original": result["draft"],
        "current_content": result["draft"],
        "citations": result["citations"],
        "hallucination_warnings": result["hallucination_warnings"],
        "context_snapshot": result["context_snapshot"],
        "model_used": result.get("model", ""),
        "prompt_version": result.get("prompt_version", "v1"),
        "usage": result.get("usage"),
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "finalized_by": None,
        "finalized_at": None,
    }
    await db.col(COLLECTION_DRAFTS).insert_one(draft_doc)

    return {
        "draft_id": draft_id,
        "draft": result["draft"],
        "citations": result["citations"],
        "hallucination_warnings": result["hallucination_warnings"],
        "model": result.get("model", ""),
        "context_snapshot": result["context_snapshot"],
    }


@router.get("/{draft_id}")
async def get_draft(draft_id: str, db: DbDep):
    """Retrieve a saved draft by ID."""
    doc = await db.col(COLLECTION_DRAFTS).find_one({"_id": draft_id})
    if not doc:
        raise HTTPException(status_code=404, detail="草稿不存在")
    doc.pop("_id", None)
    return {"draft_id": draft_id, "draft": doc.get("current_content"), **doc}


@router.put("/{draft_id}")
async def update_draft(draft_id: str, req: UpdateDraftRequest, db: DbDep):
    """Update a draft's content and save a version snapshot."""
    col = db.col(COLLECTION_DRAFTS)
    existing = await col.find_one({"_id": draft_id})
    if not existing:
        raise HTTPException(status_code=404, detail="草稿不存在")
    if existing.get("status") == "finalized":
        raise HTTPException(status_code=409, detail="已定稿的文书不可修改")

    # Save version
    ver_col = db.col(COLLECTION_VERSIONS)
    version_count = await ver_col.count_documents({"draft_id": draft_id})
    await ver_col.insert_one({
        "draft_id": draft_id,
        "version_no": version_count + 1,
        "content": existing.get("current_content"),
        "modified_at": datetime.now(),
    })

    # Update current
    await col.update_one(
        {"_id": draft_id},
        {"$set": {"current_content": req.content, "updated_at": datetime.now()}},
    )
    return {"ok": True, "version": version_count + 1, "updated_at": datetime.now().isoformat()}


@router.post("/{draft_id}/finalize")
async def finalize(draft_id: str, req: FinalizeRequest, db: DbDep):
    """Finalize (sign) a draft — makes it read-only."""
    col = db.col(COLLECTION_DRAFTS)
    existing = await col.find_one({"_id": draft_id})
    if not existing:
        raise HTTPException(status_code=404, detail="草稿不存在")
    if existing.get("status") == "finalized":
        raise HTTPException(status_code=409, detail="已定稿")

    now = datetime.now()
    await col.update_one(
        {"_id": draft_id},
        {"$set": {
            "status": "finalized",
            "finalized_by": req.signer,
            "finalized_at": now,
            "updated_at": now,
        }},
    )

    # Audit log
    try:
        await db.col("audit_logs").insert_one({
            "module": "clinical_documents",
            "action": "finalize",
            "draft_id": draft_id,
            "patient_id": existing.get("patient_id"),
            "actor": req.signer,
            "created_at": now,
        })
    except Exception as exc:
        logger.warning("审计日志写入失败: %s", exc)

    return {"ok": True, "finalized_at": now.isoformat()}


@router.get("/patients/{patient_id}")
async def list_for_patient(patient_id: str, db: DbDep, limit: int = 20):
    """List drafts for a given patient."""
    cursor = db.col(COLLECTION_DRAFTS).find(
        {"patient_id": patient_id},
        {"context_snapshot": 0, "ai_original": 0},
    ).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["draft_id"] = doc.pop("_id", "")
    return {"items": docs}


@router.get("/{draft_id}/versions")
async def list_versions(draft_id: str, db: DbDep):
    """List edit versions for a draft."""
    cursor = db.col(COLLECTION_VERSIONS).find(
        {"draft_id": draft_id},
    ).sort("version_no", -1).limit(50)
    docs = await cursor.to_list(length=50)
    for doc in docs:
        doc.pop("_id", None)
    return {"versions": docs}


@router.post("/{draft_id}/export")
async def export_draft(draft_id: str, req: ExportRequest, db: DbDep):
    """Export a finalized draft as DOCX."""
    from fastapi.responses import StreamingResponse
    import io
    from app.clinical_documents.exporter import export_progress_note_docx

    doc = await db.col(COLLECTION_DRAFTS).find_one({"_id": draft_id})
    if not doc:
        raise HTTPException(status_code=404, detail="草稿不存在")

    if req.format.lower() != "docx":
        raise HTTPException(status_code=400, detail="暂仅支持 docx 格式导出")

    try:
        file_bytes = export_progress_note_docx(doc)
    except Exception as exc:
        logger.exception("导出 DOCX 失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"导出失败: {exc}")

    filename = f"ProgressNote_{doc.get('patient_id') or 'Patient'}_{datetime.now().strftime('%Y%m%d%H%M')}.docx"

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
