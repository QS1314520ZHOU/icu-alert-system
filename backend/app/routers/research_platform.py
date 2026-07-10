from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app import runtime
from app.services.research_platform_service import (
    collect_research_platform_status,
    job_summary,
    list_research_artifacts,
    list_research_jobs,
    persist_research_platform_status,
)
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/research/platform", tags=["research-platform"])


def _actor(request: Request) -> str:
    return (
        request.headers.get("X-User-Id")
        or request.headers.get("x-user-id")
        or request.headers.get("x-operator-id")
        or "anonymous"
    )


@router.get("/status")
async def research_platform_status():
    status = await collect_research_platform_status(db=runtime.db, config=runtime.config)
    return {"status": serialize_doc(status)}


@router.post("/check")
async def research_platform_check():
    status = await collect_research_platform_status(db=runtime.db, config=runtime.config)
    record = await persist_research_platform_status(db=runtime.db, status=status)
    return {"status": serialize_doc(status), "record": serialize_doc(record)}


@router.get("/jobs")
async def research_platform_jobs(request: Request, limit: int = Query(50, ge=1, le=200)):
    user_id = _actor(request)
    rows = await list_research_jobs(db=runtime.db, user_id=user_id, limit=limit)
    summary = await job_summary(db=runtime.db, user_id=user_id)
    return {"rows": rows, "summary": serialize_doc(summary)}


@router.get("/artifacts")
async def research_platform_artifacts(request: Request, limit: int = Query(50, ge=1, le=200)):
    user_id = _actor(request)
    rows = await list_research_artifacts(db=runtime.db, user_id=user_id, limit=limit)
    return {"rows": rows}
