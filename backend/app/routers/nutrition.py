from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request

from app.services.nutrition_service import (
    close_nutrition_task,
    create_nutrition_task,
    list_nutrition_tasks,
    nutrition_ai_advice,
    nutrition_dashboard,
    nutrition_patient_detail,
)

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


def _actor(request: Request) -> str:
    return request.headers.get("X-User-Id") or request.headers.get("x-operator-id") or "anonymous"


@router.get("/dashboard")
async def dashboard(
    dept: str | None = Query(None, description="科室名称"),
    dept_code: str | None = Query(None, description="科室代码"),
    deptCode: str | None = Query(None, description="兼容前端 deptCode 参数"),
    patient_scope: str = Query("in_dept", description="患者范围"),
    detail: bool = Query(False, description="是否计算详情级营养数据"),
):
    return {"code": 0, **await nutrition_dashboard(department=dept, dept_code=dept_code or deptCode, patient_scope=patient_scope, detail=detail)}


@router.get("/{patient_id}")
async def patient_detail(patient_id: str):
    return {"code": 0, **await nutrition_patient_detail(patient_id)}


@router.post("/{patient_id}/task")
async def create_task(patient_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await create_nutrition_task(patient_id, payload or {}, _actor(request))}


@router.get("/{patient_id}/tasks")
async def patient_tasks(patient_id: str):
    return {"code": 0, **await list_nutrition_tasks(patient_id)}


@router.post("/tasks/{task_id}/close")
async def close_task(task_id: str, request: Request, payload: dict = Body(default={})):
    return {"code": 0, **await close_nutrition_task(task_id, payload or {}, _actor(request))}


@router.post("/{patient_id}/ai-advice")
async def ai_advice(patient_id: str, refresh: bool = Query(False)):
    return {"code": 0, **await nutrition_ai_advice(patient_id, refresh=refresh)}
