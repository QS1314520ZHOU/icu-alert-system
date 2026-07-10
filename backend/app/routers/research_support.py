from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
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
from app.services.research_topic_status_service import mdro_control_summary, respiratory_forecast_status

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
async def topic_suggestions(
    department: Optional[str] = Query(None),
    dept: Optional[str] = Query(None),
    dept_code: Optional[str] = Query(None),
    patient_scope: str = Query("in_dept"),
):
    return {"code": 0, **await list_topic_suggestions(department=department or dept, dept_code=dept_code, patient_scope=patient_scope)}


@router.post("/topic-suggestions/generate")
async def generate_topics(request: Request, payload: dict = Body(default={})):
    body = payload or {}
    return {
        "code": 0,
        **await generate_topic_suggestions(
            _actor(request),
            department=body.get("department") or body.get("dept"),
            dept_code=body.get("dept_code"),
            patient_scope=str(body.get("patient_scope") or "in_dept"),
        ),
    }


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
async def data_quality(
    department: Optional[str] = Query(None),
    dept: Optional[str] = Query(None),
    dept_code: Optional[str] = Query(None),
    patient_scope: str = Query("in_dept"),
):
    report = await build_data_quality_report(patient_scope, department=department or dept, dept_code=dept_code)
    return {"code": 0, "report": report, "recommendations": build_data_governance_recommendations(report)}


@router.get("/respiratory-forecast/status")
async def respiratory_forecast_model_status(limit: int = Query(20, ge=1, le=100)):
    return {"code": 0, **await respiratory_forecast_status(db=runtime.db, config=runtime.config, limit=limit)}


@router.get("/mdro-control/summary")
async def mdro_control_analysis_summary(limit: int = Query(20, ge=1, le=100)):
    return {"code": 0, **await mdro_control_summary(db=runtime.db, config=runtime.config, limit=limit)}
