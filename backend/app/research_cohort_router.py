from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import runtime
from app.services.research_analytics import build_custom_cohort, summarize_variables
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/research", tags=["research-cohort"])
logger = logging.getLogger("icu-alert")


class CohortFilterItem(BaseModel):
    field: str
    operator: str = "eq"
    value: Any = None


class CohortBuildRequest(BaseModel):
    filters: list[CohortFilterItem] = Field(default_factory=list)
    patient_ids: list[str] | None = None
    department: str | None = None
    dept_code: str | None = None
    patient_scope: str = 'all'


class CohortPersistRequest(CohortBuildRequest):
    name: str = "未命名队列"


class VariableSummaryRequest(BaseModel):
    patient_ids: list[str] | None = None
    cohort_id: str | None = None
    fields: list[str] = Field(default_factory=list)


class IcdSearchItem(BaseModel):
    code: str
    name: str
    py: str | None = None


def _actor(request: Request) -> str:
    return (
        request.headers.get("X-User-Id")
        or request.headers.get("x-user-id")
        or request.headers.get("x-operator-id")
        or "anonymous"
    )


async def _list_user_cohorts(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    cursor = runtime.db.col("research_cohorts").find(
        {"created_by": user_id},
        {"_id": 0},
    ).sort("updated_at", -1).limit(max(1, min(200, int(limit or 50))))
    return [serialize_doc(doc) async for doc in cursor]


@router.post("/cohort/build")
async def api_research_cohort_build(req: CohortBuildRequest):
    try:
        return await build_custom_cohort(
            db=runtime.db,
            filters=[item.model_dump() for item in req.filters],
            patient_ids=req.patient_ids,
            department=req.department,
            dept_code=req.dept_code,
            patient_scope=req.patient_scope,
            config=runtime.config,
        )
    except Exception as exc:
        logger.exception("cohort/build failed")
        raise HTTPException(status_code=500, detail=f"cohort/build failed: {exc.__class__.__name__}: {exc}") from exc


@router.post("/cohort/save")
async def api_research_cohort_save(req: CohortPersistRequest, request: Request):
    filters = [item.model_dump() for item in req.filters]
    try:
        cohort = await build_custom_cohort(
            db=runtime.db,
            filters=filters,
            patient_ids=req.patient_ids,
            department=req.department,
            dept_code=req.dept_code,
            patient_scope=req.patient_scope,
            config=runtime.config,
        )
    except Exception as exc:
        logger.exception("cohort/save failed while building")
        raise HTTPException(status_code=500, detail=f"cohort/save build failed: {exc.__class__.__name__}: {exc}") from exc
    patient_ids = cohort.get("patient_ids") or []
    cohort_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "cohort_id": cohort_id,
        "name": str(req.name or "未命名队列"),
        "patient_ids": patient_ids,
        "patient_count": len(patient_ids),
        "n_patients": len(patient_ids),
        "filters": filters,
        "department": req.department,
        "dept_code": req.dept_code,
        "patient_scope": req.patient_scope,
        "demographics": cohort.get("demographics"),
        "preview_patients": cohort.get("preview_patients"),
        "created_by": _actor(request),
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("research_cohorts").insert_one(doc)
    return {
        "cohort_id": cohort_id,
        "name": doc["name"],
        "patient_count": doc["patient_count"],
        "patient_ids": patient_ids,
        "demographics": doc.get("demographics"),
        "preview_patients": cohort.get("preview_patients", []),
    }


@router.get("/cohort/list")
async def api_research_cohort_list(request: Request, limit: int = 50):
    user = _actor(request)
    rows = await _list_user_cohorts(user, limit)
    return {"cohorts": rows}


@router.delete("/cohort/{cohort_id}")
async def api_research_cohort_delete(cohort_id: str, request: Request):
    user = _actor(request)
    result = await runtime.db.col("research_cohorts").delete_one({"cohort_id": cohort_id, "created_by": user})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cohort not found")
    return {"deleted": True}


@router.post("/variables/batch-summary")
async def api_research_variable_summary(req: VariableSummaryRequest):
    if not req.fields:
        return {"summaries": {}, "n_patients": 0}
    try:
        return await summarize_variables(
            db=runtime.db,
            patient_ids=req.patient_ids,
            cohort_id=req.cohort_id,
            fields=req.fields,
            config=runtime.config,
        )
    except Exception as exc:
        logger.exception("variables/batch-summary failed")
        # 变量摘要失败不应阻塞主流程，降级返回空摘要并带错误信息。
        return {
            "summaries": {},
            "n_patients": len(req.patient_ids or []),
            "error": f"variables/batch-summary failed: {exc.__class__.__name__}: {exc}",
        }


@router.get("/icd/search")
async def api_research_icd_search(q: str = "", limit: int = 20):
    keyword = str(q or "").strip()
    size = max(1, min(50, int(limit or 20)))
    col = runtime.db.dc_col("VI_ICU_ICD")
    try:
        query: dict[str, Any] = {}
        if keyword:
            regex = {"$regex": keyword, "$options": "i"}
            query = {
                "$or": [
                    {"code": regex},
                    {"icdCode": regex},
                    {"name": regex},
                    {"icdName": regex},
                    {"diagName": regex},
                    {"diagnosisName": regex},
                    {"pinyin": regex},
                    {"py": regex},
                    {"spell": regex},
                    {"abbr": regex},
                    {"initials": regex},
                ]
            }
        cursor = col.find(
            query,
            {
                "_id": 0,
                "code": 1,
                "icdCode": 1,
                "name": 1,
                "icdName": 1,
                "diagName": 1,
                "diagnosisName": 1,
                "pinyin": 1,
                "py": 1,
                "spell": 1,
                "abbr": 1,
                "initials": 1,
            },
        ).limit(size)
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        async for doc in cursor:
            code = str(doc.get("code") or doc.get("icdCode") or "").strip()
            name = str(doc.get("name") or doc.get("icdName") or doc.get("diagName") or doc.get("diagnosisName") or "").strip()
            py = str(doc.get("py") or doc.get("pinyin") or doc.get("spell") or doc.get("abbr") or doc.get("initials") or "").strip() or None
            if not code and not name:
                continue
            key = (code, name)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"code": code, "name": name, "py": py})
            if len(rows) >= size:
                break
        return {"items": rows}
    except Exception as exc:
        logger.exception("icd/search failed")
        raise HTTPException(status_code=500, detail=f"icd/search failed: {exc.__class__.__name__}: {exc}") from exc
