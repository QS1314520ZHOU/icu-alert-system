from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import runtime
from app.database import DatabaseManager
from app.services.research_export_service import preview_export, run_export_task

router = APIRouter(prefix="/api/research", tags=["research-export"])
API_TZ = ZoneInfo("Asia/Shanghai")


class TimeRange(BaseModel):
    start: str
    end: str


class ExportRequest(BaseModel):
    data_types: list[str] = Field(default_factory=list)
    patient_ids: list[str] | None = None
    cohort_id: str | None = None
    department: str | None = None
    dept_code: str | None = None
    patient_scope: str = "all"
    time_range: TimeRange
    format: str = "csv"
    export_mode: str = "dataset"
    desensitize: bool = True
    include_data_dict: bool = True


def _localize_time(value):
    if not isinstance(value, datetime):
        return value
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(API_TZ).isoformat(timespec="seconds")


def _serialize_export_doc(doc: dict | None) -> dict | None:
    if not isinstance(doc, dict):
        return doc
    data = dict(doc)
    data.pop("_id", None)
    for key in ("created_at", "completed_at", "updated_at"):
        if key in data:
            data[key] = _localize_time(data.get(key))
    return data


@router.post("/export/preview")
async def preview_export_task(req: ExportRequest):
    try:
        return await preview_export(req.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"preview export failed: {exc.__class__.__name__}: {exc}") from exc


@router.post("/export")
async def create_export_task(req: ExportRequest, request: Request, db: DatabaseManager = Depends(runtime.get_db)):
    task_id = str(uuid.uuid4())
    params = req.model_dump()
    created_by = request.headers.get("X-User-Id", "anonymous")

    col = db.col("research_export_tasks")
    await col.insert_one({
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "params": params,
        "file_path": None,
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
        "created_by": created_by,
    })

    asyncio.create_task(run_export_task(task_id, params, created_by))
    return {"task_id": task_id, "status": "pending"}


@router.get("/export/{task_id}/status")
async def get_export_status(task_id: str, db: DatabaseManager = Depends(runtime.get_db)):
    col = db.col("research_export_tasks")
    doc = await col.find_one({"task_id": task_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    doc.pop("file_path", None)
    return _serialize_export_doc(doc)


@router.get("/export/{task_id}/download")
async def download_export(task_id: str, db: DatabaseManager = Depends(runtime.get_db)):
    col = db.col("research_export_tasks")
    doc = await col.find_one({"task_id": task_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    if doc.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"Task is not completed yet (status: {doc.get('status')})")
    file_path = doc.get("file_path")
    target = Path(str(file_path or "")).resolve() if file_path else None
    if not target or not target.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(path=target, filename=target.name, media_type="application/zip")


@router.get("/export/history")
async def export_history(
    request: Request,
    db: DatabaseManager = Depends(runtime.get_db),
    status: str | None = Query(None),
    export_mode: str | None = Query(None),
):
    created_by = request.headers.get("X-User-Id", "anonymous")
    col = db.col("research_export_tasks")
    query: dict[str, object] = {"created_by": created_by}
    if str(status or "").strip():
        query["status"] = str(status).strip()
    if str(export_mode or "").strip():
        query["scope_summary.export_mode"] = str(export_mode).strip()
    cursor = col.find(query, {"_id": 0, "file_path": 0}).sort("created_at", -1).limit(100)
    docs = [_serialize_export_doc(doc) async for doc in cursor]
    return {"history": docs}
