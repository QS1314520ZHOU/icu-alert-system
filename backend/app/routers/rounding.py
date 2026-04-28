from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app import runtime
from app.services.rounding_service import export_rounding_report, generate_ai_focus_points, list_rounding_patients, build_rounding_summary

router = APIRouter(prefix="/api/rounding", tags=["rounding"])


def _actor(request: Request) -> str:
    return request.headers.get("X-User-Id") or request.headers.get("x-operator-id") or "anonymous"


@router.get("/patients")
async def rounding_patients(
    limit: int = Query(200, ge=1, le=500),
    dept: str | None = Query(None, description="科室名称"),
    dept_code: str | None = Query(None, alias="dept_code", description="科室代码"),
    deptCode: str | None = Query(None, description="兼容前端 deptCode 参数"),
):
    return {"code": 0, **await list_rounding_patients(limit=limit, department=dept, dept_code=dept_code or deptCode)}


@router.get("/{patient_id}/summary")
async def rounding_summary(patient_id: str, hours: int = Query(24, ge=8, le=48)):
    return await build_rounding_summary(patient_id, hours)


@router.post("/{patient_id}/ai-insights")
async def rounding_ai_insights(patient_id: str, request: Request, payload: dict = Body(default={})):
    hours = int((payload or {}).get("hours") or 24)
    return await generate_ai_focus_points(patient_id, hours=hours, actor=_actor(request))


@router.post("/export")
async def rounding_export(request: Request, payload: dict = Body(default={})):
    return await export_rounding_report(payload or {}, actor=_actor(request))


@router.get("/export/{task_id}/download")
async def rounding_export_download(task_id: str):
    doc = await runtime.db.col("rounding_export_tasks").find_one({"task_id": task_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    target = Path(str(doc.get("file_path") or "")).resolve()
    if not target.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    media_type = "text/html" if target.suffix.lower() == ".html" else "text/markdown"
    return FileResponse(path=target, filename=target.name, media_type=media_type)
