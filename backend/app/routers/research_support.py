from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from app import runtime
from app.services.omop_export_service import build_data_quality_report, run_omop_export
from app.services.research_support_service import (
    build_data_governance_recommendations,
    create_project,
    delete_project,
    generate_topic_suggestions,
    list_projects,
    list_topic_suggestions,
    update_project,
)

router = APIRouter(prefix="/api/research", tags=["research-support"])


def _actor(request: Request) -> str:
    return request.headers.get("X-User-Id") or request.headers.get("x-operator-id") or "anonymous"


@router.get("/projects")
async def research_projects():
    return {"code": 0, **await list_projects()}


@router.post("/projects")
async def add_research_project(request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await create_project(payload or {}, _actor(request))}


@router.put("/projects/{project_id}")
async def save_research_project(project_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await update_project(project_id, payload or {}, _actor(request))}


@router.delete("/projects/{project_id}")
async def remove_research_project(project_id: str):
    return {"code": 0, **await delete_project(project_id)}


@router.get("/topic-suggestions")
async def topic_suggestions():
    return {"code": 0, **await list_topic_suggestions()}


@router.post("/topic-suggestions/generate")
async def generate_topics(request: Request):
    return {"code": 0, **await generate_topic_suggestions(_actor(request))}


@router.post("/omop/export")
async def omop_export(request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await run_omop_export(payload or {}, _actor(request))}


@router.get("/omop/export/{task_id}/status")
async def omop_export_status(task_id: str):
    doc = await runtime.db.col("omop_export_tasks").find_one({"task_id": task_id}, {"file_path": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return doc


@router.get("/omop/export/{task_id}/download")
async def omop_export_download(task_id: str):
    doc = await runtime.db.col("omop_export_tasks").find_one({"task_id": task_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    target = Path(str(doc.get("file_path") or "")).resolve()
    if not target.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(path=target, filename=target.name, media_type="application/zip")


@router.get("/data-quality")
async def data_quality():
    report = await build_data_quality_report("all")
    return {"code": 0, "report": report, "recommendations": build_data_governance_recommendations(report)}
