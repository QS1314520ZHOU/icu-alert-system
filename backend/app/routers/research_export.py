from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import runtime
from app.services.research_export_service import run_export_task

router = APIRouter(prefix="/api/research", tags=["research-export"])


class TimeRange(BaseModel):
    start: str
    end: str


class ExportRequest(BaseModel):
    data_types: list[str]
    patient_ids: list[str] | None = None
    department: str | None = None
    time_range: TimeRange
    format: str = "csv"
    desensitize: bool = True
    include_data_dict: bool = True


@router.post("/export")
async def create_export_task(req: ExportRequest, request: Request):
    task_id = str(uuid.uuid4())
    params = req.model_dump()
    created_by = request.headers.get("X-User-Id", "anonymous")

    col = runtime.db.col("research_export_tasks")
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

    import asyncio
    asyncio.create_task(run_export_task(task_id, params, created_by))

    return {"task_id": task_id, "status": "pending"}


@router.get("/export/{task_id}/status")
async def get_export_status(task_id: str):
    col = runtime.db.col("research_export_tasks")
    doc = await col.find_one({"task_id": task_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    doc.pop("file_path", None)
    return doc


@router.get("/export/{task_id}/download")
async def download_export(task_id: str):
    col = runtime.db.col("research_export_tasks")
    doc = await col.find_one({"task_id": task_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Task is not completed yet (status: {doc['status']})")
    file_path = doc.get("file_path")
    if not file_path or not __import__('pathlib').Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(path=file_path, filename=__import__('pathlib').Path(file_path).name, media_type="application/zip")


@router.get("/export/history")
async def export_history(request: Request):
    created_by = request.headers.get("X-User-Id", "anonymous")
    col = runtime.db.col("research_export_tasks")
    cursor = col.find({"created_by": created_by}, {"_id": 0, "file_path": 0}).sort("created_at", -1).limit(50)
    docs = [doc async for doc in cursor]
    return {"history": docs}
