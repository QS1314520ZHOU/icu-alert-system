from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import runtime
from app.config import get_config
from app.services.llm_runtime import call_llm_chat
from app.services.research_platform_service import register_research_artifact
from app.services.research_analytics import (
    correlation_analysis,
    create_materials_bundle,
    descriptive_statistics,
    export_figure,
    export_table,
    generate_table1,
    get_analysis_session,
    list_analysis_sessions,
    regression_analysis,
    roc_analysis,
    save_analysis_session,
    subgroup_analysis,
    survival_analysis,
    trend_analysis,
)
from app.utils.patient_helpers import research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

logger = logging.getLogger("icu-alert")

router = APIRouter(prefix="/api/research", tags=["research-analytics"])


def _sanitize_json_value(value: Any) -> Any:
    base = serialize_doc(value)
    if isinstance(base, float):
        return base if math.isfinite(base) else None
    if isinstance(base, dict):
        return {str(k): _sanitize_json_value(v) for k, v in base.items()}
    if isinstance(base, (list, tuple)):
        return [_sanitize_json_value(v) for v in base]
    if hasattr(base, "item") and callable(getattr(base, "item")):
        try:
            return _sanitize_json_value(base.item())
        except Exception:
            return str(base)
    return base


class ScopeRequest(BaseModel):
    patient_ids: list[str] | None = None
    cohort_id: str | None = None
    department: str | None = None
    dept_code: str | None = None
    patient_scope: str = 'all'
    async_task: bool = False


class Table1Request(ScopeRequest):
    group_by: str = "outcome"
    group_definitions: dict[str, Any] = Field(default_factory=dict)
    variables: list[dict[str, Any]] = Field(default_factory=list)


class SurvivalRequest(ScopeRequest):
    time_field: str = "los_icu_days"
    event_field: str = "icu_mortality"
    group_by: str | None = None
    max_time: int = 28


class RegressionRequest(ScopeRequest):
    outcome: str
    outcome_type: str
    predictors: list[str] = Field(default_factory=list)
    time_field: str | None = None
    confounders: list[str] | None = None


class RocRequest(ScopeRequest):
    outcome: str
    predictors: list[str] = Field(default_factory=list)


class SubgroupRequest(ScopeRequest):
    exposure: str
    outcome: str
    outcome_type: str = "binary"
    subgroups: list[dict[str, Any]] = Field(default_factory=list)
    time_field: str | None = None


class TrendRequest(ScopeRequest):
    indicators: list[str] = Field(default_factory=list)
    time_reference: str = "icu_admission"
    time_range_hours: int = 72
    group_by: str | None = None
    interval_hours: float = 4


class CorrelationRequest(ScopeRequest):
    variables: list[str] = Field(default_factory=list)
    method: str = "auto"


class DescriptiveRequest(ScopeRequest):
    variables: list[dict[str, Any]] | list[str] = Field(default_factory=list)


class ExportFigureRequest(BaseModel):
    chart_type: str
    result: dict[str, Any]
    format: str = "png"
    width_mode: str = "single"
    filename: str | None = None


class ExportTableRequest(BaseModel):
    title: str = "Table"
    table_data: dict[str, Any]
    format: str = "docx"
    filename: str | None = None


class SaveSessionRequest(BaseModel):
    name: str = "未命名分析会话"
    payload: dict[str, Any]


class BundleExportRequest(BaseModel):
    bundle_name: str = "research_figures"
    files: list[dict[str, Any]] = Field(default_factory=list)


class AIInterpretRequest(BaseModel):
    analysis_type: str
    results: dict[str, Any]
    language: str = "zh"

class AIPlanRequest(BaseModel):
    query: str
    scope: dict[str, Any] = Field(default_factory=dict)



class CohortPreviewRequest(ScopeRequest):
    filters: dict[str, Any] = Field(default_factory=dict)


class CohortSaveRequest(CohortPreviewRequest):
    name: str = "未命名队列"


def _actor(request: Request) -> str:
    return (
        request.headers.get("X-User-Id")
        or request.headers.get("x-user-id")
        or request.headers.get("x-operator-id")
        or "anonymous"
    )


def _dedupe_patient_ids(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in values or []:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _research_max_patients() -> int:
    cfg = (runtime.config.yaml_cfg or {}) if runtime.config is not None else {}
    research = cfg.get("research", {}) if isinstance(cfg, dict) else {}
    value = int(research.get("max_export_patients", 10000) or 10000)
    return max(1000, value)


def _cohort_query_from_filters(req: CohortPreviewRequest) -> dict[str, Any]:
    query: dict[str, Any] = research_patient_scope_query(req.patient_scope)
    filters = req.filters if isinstance(req.filters, dict) else {}
    and_terms: list[dict[str, Any]] = [query] if query else []

    department = str(req.department or "").strip()
    if department:
        and_terms.append({"$or": [{"hisDept": department}, {"dept": department}]})
    dept_code = str(req.dept_code or "").strip()
    if dept_code:
        and_terms.append({"deptCode": dept_code})

    age_min = filters.get("age_min")
    age_max = filters.get("age_max")
    if age_min is not None or age_max is not None:
        age_filter: dict[str, Any] = {}
        if age_min is not None:
            age_filter["$gte"] = age_min
        if age_max is not None:
            age_filter["$lte"] = age_max
        and_terms.append({"age": age_filter})

    sex = str(filters.get("sex") or "").strip()
    if sex:
        candidates = [sex]
        if sex.upper() == "M":
            candidates.extend(["男", "male", "MALE"])
        elif sex.upper() == "F":
            candidates.extend(["女", "female", "FEMALE"])
        and_terms.append({"$or": [{"sex": {"$in": candidates}}, {"gender": {"$in": candidates}}]})

    outcome = str(filters.get("outcome") or "").strip().lower()
    if outcome in {"dead", "death", "死亡"}:
        and_terms.append(
            {
                "$or": [
                    {"outcome": {"$in": ["dead", "death", "deceased", "死亡"]}},
                    {"status": {"$in": ["dead", "death", "deceased", "死亡"]}},
                    {"icu_mortality": 1},
                    {"mortality": 1},
                ]
            }
        )
    elif outcome in {"alive", "survive", "存活"}:
        and_terms.append(
            {
                "$or": [
                    {"outcome": {"$in": ["alive", "survive", "存活"]}},
                    {"status": {"$in": ["alive", "survive", "存活"]}},
                    {"icu_mortality": 0},
                    {"mortality": 0},
                ]
            }
        )

    diagnosis_contains = str(filters.get("diagnosis_contains") or "").strip()
    if diagnosis_contains:
        pattern = re.escape(diagnosis_contains)
        and_terms.append(
            {
                "$or": [
                    {"clinicalDiagnosis": {"$regex": pattern, "$options": "i"}},
                    {"admissionDiagnosis": {"$regex": pattern, "$options": "i"}},
                    {"diagnosis": {"$regex": pattern, "$options": "i"}},
                ]
            }
        )

    if not and_terms:
        return {}
    if len(and_terms) == 1:
        return and_terms[0]
    return {"$and": and_terms}


async def _resolve_scope_patient_ids(req: ScopeRequest) -> list[str]:
    ids = _dedupe_patient_ids(req.patient_ids)
    if ids:
        return ids
    if req.cohort_id:
        token = str(req.cohort_id).strip()
        query: dict[str, Any] = {"cohort_id": token}
        oid = safe_oid(token)
        if oid is not None:
            query = {"$or": [{"_id": oid}, {"cohort_id": token}]}
        doc = await runtime.db.col("research_cohorts").find_one(query)
        if doc:
            values: list[str] = []
            for key in ("patient_ids", "patients", "members"):
                items = doc.get(key)
                if isinstance(items, list):
                    for item in items:
                        if str(item or "").strip():
                            values.append(str(item).strip())
            return _dedupe_patient_ids(values)
        return []
    department = str(req.department or "").strip()
    dept_code = str(req.dept_code or "").strip()
    if department and not dept_code and department.isdigit():
        dept_code = department
        department = ""
    if department and dept_code and (department == dept_code or department.isdigit()):
        department = ""
    if not department and not dept_code:
        return []
    query = research_patient_scope_query(req.patient_scope)
    clauses: list[dict[str, Any]] = [query] if query else []
    if department:
        clauses.append({"$or": [{"hisDept": department}, {"dept": department}]})
    if dept_code:
        clauses.append({"deptCode": dept_code})
    query = {} if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}
    max_patients = _research_max_patients()
    cursor = runtime.db.col("patient").find(query, {"_id": 1}).limit(max_patients)
    output: list[str] = []
    async for doc in cursor:
        if doc.get("_id") is not None:
            output.append(str(doc["_id"]))
    return _dedupe_patient_ids(output)


async def _create_task_doc(task_type: str, params: dict[str, Any], created_by: str) -> str:
    task_id = str(uuid.uuid4())
    await runtime.db.col("research_analytics_tasks").insert_one(
        {
            "task_id": task_id,
            "task_type": task_type,
            "status": "pending",
            "progress": 0,
            "params": params,
            "result": None,
            "error": None,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    return task_id


async def _run_background_task(
    task_id: str,
    handler: Callable[[], Awaitable[dict[str, Any]]],
) -> None:
    # Essential yield: Give Uvicorn enough event loop ticks to send the HTTP response 
    # { "task_id": ... "async": True } back to the client over TCP before plunging into
    # synchronous data loading (like pandas dataframe creation and db scanning).
    await asyncio.sleep(0.1)

    col = runtime.db.col("research_analytics_tasks")
    try:
        await col.update_one({"task_id": task_id}, {"$set": {"status": "processing", "progress": 10, "updated_at": datetime.now(timezone.utc)}})
        result = _sanitize_json_value(await handler())
        await col.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "completed",
                    "progress": 100,
                    "result": result,
                    "updated_at": datetime.now(timezone.utc),
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )
    except Exception as exc:
        logger.exception("research analytics async task failed: %s", exc)
        await col.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(exc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )


def _should_async(payload: ScopeRequest) -> bool:
    if payload.async_task:
        return True
    
    count = len(payload.patient_ids or [])
    # Lowered threshold to 50 because data aggregation (labs, scores) across
    # patients is completely synchronous-bound and fetches millions of documents.
    # >50 easily exceeds 30 seconds HTTP timeout.
    if count > 50:
        return True
        
    # An empty patient_ids scope unconditionally means an unbounded global query. 
    # In _load_patient_dataframe, this translates to query="{}" which loads up to 
    # 10000 patients and takes > 30s. We must ALWAYS route this to the async queue.
    if count == 0:
        return True
        
    return False


async def _submit_or_run(
    *,
    request: Request,
    payload: ScopeRequest,
    task_type: str,
    handler: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    if _should_async(payload):
        task_id = await _create_task_doc(task_type, payload.model_dump(), _actor(request))
        asyncio.create_task(_run_background_task(task_id, handler))
        return {"task_id": task_id, "status": "pending", "async": True}
    try:
        data = _sanitize_json_value(await handler())
        return {"status": "completed", "async": False, "result": data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("research analytics run failed: %s", task_type)
        raise HTTPException(
            status_code=500,
            detail=f"{task_type} failed: {exc.__class__.__name__}: {exc}",
        ) from exc


def _payload_with_scope(req: ScopeRequest, patient_ids: list[str]) -> ScopeRequest:
    return req.model_copy(update={"patient_ids": patient_ids})


@router.post("/analytics/table1")
async def api_table1(req: Table1Request, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await generate_table1(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            group_by=req.group_by,
            group_definitions=req.group_definitions,
            variables=req.variables,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="table1", handler=_run)


@router.post("/analytics/survival")
async def api_survival(req: SurvivalRequest, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await survival_analysis(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            time_field=req.time_field,
            event_field=req.event_field,
            group_by=req.group_by,
            max_time=req.max_time,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="survival", handler=_run)


@router.post("/analytics/regression")
async def api_regression(req: RegressionRequest, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await regression_analysis(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            outcome=req.outcome,
            outcome_type=req.outcome_type,
            predictors=req.predictors,
            time_field=req.time_field,
            confounders=req.confounders,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="regression", handler=_run)


@router.post("/analytics/roc")
async def api_roc(req: RocRequest, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await roc_analysis(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            outcome=req.outcome,
            predictors=req.predictors,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="roc", handler=_run)


@router.post("/analytics/subgroup")
async def api_subgroup(req: SubgroupRequest, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await subgroup_analysis(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            exposure=req.exposure,
            outcome=req.outcome,
            outcome_type=req.outcome_type,
            subgroups=req.subgroups,
            time_field=req.time_field,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="subgroup", handler=_run)


@router.post("/analytics/trend")
async def api_trend(req: TrendRequest, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await trend_analysis(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            indicators=req.indicators,
            time_reference=req.time_reference,
            time_range_hours=req.time_range_hours,
            group_by=req.group_by,
            interval_hours=req.interval_hours,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="trend", handler=_run)


@router.post("/analytics/correlation")
async def api_correlation(req: CorrelationRequest, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await correlation_analysis(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            variables=req.variables,
            method=req.method,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="correlation", handler=_run)


@router.post("/analytics/descriptive")
async def api_descriptive(req: DescriptiveRequest, request: Request):
    scoped_ids = await _resolve_scope_patient_ids(req)
    scoped_req = _payload_with_scope(req, scoped_ids)

    async def _run():
        return await descriptive_statistics(
            patient_ids=scoped_req.patient_ids or [],
            cohort_id=scoped_req.cohort_id,
            variables=req.variables,
            db=runtime.db,
            config=runtime.config,
        )

    return await _submit_or_run(request=request, payload=scoped_req, task_type="descriptive", handler=_run)


@router.post("/analytics/cohort/preview")
async def api_cohort_preview(req: CohortPreviewRequest):
    explicit_ids = _dedupe_patient_ids(req.patient_ids)
    if explicit_ids:
        preview_ids = explicit_ids[:50]
        oid_values = [oid for oid in (safe_oid(pid) for pid in preview_ids) if oid is not None]
        sample_cursor = runtime.db.col("patient").find(
            {"_id": {"$in": oid_values}},
            {"_id": 1, "hisPid": 1, "name": 1, "sex": 1, "age": 1, "hisDept": 1, "dept": 1, "outcome": 1},
        ).limit(20)
        samples = [serialize_doc(doc) async for doc in sample_cursor]
        return {"n_patients": len(explicit_ids), "patient_ids": explicit_ids, "samples": samples, "source": "explicit"}

    query = _cohort_query_from_filters(req)
    limit = _research_max_patients()
    cursor = runtime.db.col("patient").find(
        query,
        {"_id": 1, "hisPid": 1, "name": 1, "sex": 1, "age": 1, "hisDept": 1, "dept": 1, "outcome": 1},
    ).limit(limit)
    patient_ids: list[str] = []
    samples: list[dict[str, Any]] = []
    async for doc in cursor:
        pid = str(doc.get("_id") or "").strip()
        if pid:
            patient_ids.append(pid)
        if len(samples) < 20:
            samples.append(serialize_doc(doc))
    return {
        "n_patients": len(patient_ids),
        "patient_ids": patient_ids,
        "samples": samples,
        "source": "query",
        "query": query,
    }


@router.post("/analytics/cohort/save")
async def api_cohort_save(req: CohortSaveRequest, request: Request):
    preview = await api_cohort_preview(req)
    patient_ids = _dedupe_patient_ids(preview.get("patient_ids") if isinstance(preview, dict) else [])
    cohort_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "cohort_id": cohort_id,
        "name": str(req.name or "未命名队列"),
        "patient_ids": patient_ids,
        "n_patients": len(patient_ids),
        "filters": req.filters if isinstance(req.filters, dict) else {},
        "department": req.department,
        "dept_code": req.dept_code,
        "patient_scope": req.patient_scope,
        "created_by": _actor(request),
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("research_cohorts").insert_one(doc)
    return {"cohort_id": cohort_id, "name": doc["name"], "n_patients": doc["n_patients"]}


@router.get("/analytics/cohort/list")
async def api_cohort_list(request: Request, limit: int = 50):
    cursor = runtime.db.col("research_cohorts").find(
        {"created_by": _actor(request)},
        {"_id": 0},
    ).sort("updated_at", -1).limit(max(1, min(200, int(limit or 50))))
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"cohorts": rows}


@router.get("/analytics/tasks/{task_id}/status")
async def api_task_status(task_id: str):
    doc = await runtime.db.col("research_analytics_tasks").find_one({"task_id": task_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return serialize_doc(doc)


@router.post("/analytics/export-figure")
async def api_export_figure(req: ExportFigureRequest):
    result = await export_figure(
        chart_type=req.chart_type,
        result=req.result,
        fmt=req.format,
        width_mode=req.width_mode,
        filename=req.filename,
        config=runtime.config,
    )
    await register_research_artifact(
        db=runtime.db,
        created_by="anonymous",
        artifact_type="figure",
        title=str(req.filename or req.chart_type or "research_figure"),
        file_path=str(result["file_path"]),
        file_name=str(result["file_name"]),
        download_url=f"/api/research/analytics/files/{result['file_name']}",
        source="research_analytics_export",
        meta={"chart_type": req.chart_type, "format": req.format, "width_mode": req.width_mode},
    )
    return {
        **result,
        "download_url": f"/api/research/analytics/files/{result['file_name']}",
    }


@router.post("/analytics/export-table")
async def api_export_table(req: ExportTableRequest):
    result = await export_table(
        table_data=req.table_data,
        title=req.title,
        fmt=req.format,
        filename=req.filename,
        config=runtime.config,
    )
    await register_research_artifact(
        db=runtime.db,
        created_by="anonymous",
        artifact_type="table",
        title=str(req.title or req.filename or "research_table"),
        file_path=str(result["file_path"]),
        file_name=str(result["file_name"]),
        download_url=f"/api/research/analytics/files/{result['file_name']}",
        source="research_analytics_export",
        meta={"format": req.format},
    )
    return {
        **result,
        "download_url": f"/api/research/analytics/files/{result['file_name']}",
    }


@router.post("/analytics/export-bundle")
async def api_export_bundle(req: BundleExportRequest):
    result = await create_materials_bundle(bundle_name=req.bundle_name, files=req.files)
    await register_research_artifact(
        db=runtime.db,
        created_by="anonymous",
        artifact_type="bundle",
        title=str(req.bundle_name or result.get("file_name") or "research_bundle"),
        file_path=str(result["file_path"]),
        file_name=str(result["file_name"]),
        download_url=f"/api/research/analytics/files/{result['file_name']}",
        source="research_analytics_export",
        meta={"file_count": len(req.files or [])},
    )
    return {
        **result,
        "download_url": f"/api/research/analytics/files/{result['file_name']}",
    }


@router.get("/analytics/files/{file_name}")
async def api_download_file(file_name: str):
    safe_name = Path(file_name).name
    target = Path("backend/exports/research_analytics") / safe_name
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=target, filename=safe_name)


@router.post("/analytics/session/save")
async def api_session_save(req: SaveSessionRequest, request: Request):
    result = await save_analysis_session(
        db=runtime.db,
        user_id=_actor(request),
        name=req.name,
        payload=req.payload,
    )
    return result


@router.get("/analytics/session/list")
async def api_session_list(request: Request, limit: int = 50):
    rows = await list_analysis_sessions(db=runtime.db, user_id=_actor(request), limit=limit)
    return {"sessions": rows}


@router.get("/analytics/session/{session_id}")
async def api_session_get(session_id: str, request: Request):
    row = await get_analysis_session(db=runtime.db, session_id=session_id, user_id=_actor(request))
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _fallback_ai_text(analysis_type: str, language: str) -> dict[str, str]:
    if str(language).lower().startswith("en"):
        return {
            "interpretation": f"{analysis_type} analysis is completed. Please combine effect size, confidence interval and P-value for clinical interpretation.",
            "methods_text": "Continuous variables are summarized as mean±SD or median(IQR), and categorical variables as n(%). Group comparisons are performed with appropriate parametric/non-parametric tests.",
            "results_text": "Key variables with statistically significant differences (P<0.05) should be highlighted with effect sizes and confidence intervals.",
        }
    return {
        "interpretation": f"已完成 {analysis_type} 分析，请重点结合效应值、95%CI 与 P 值进行临床解读。",
        "methods_text": "连续变量以均数±标准差或中位数(四分位距)表示，分类变量以例数(百分比)表示；根据分布特征选择参数或非参数检验。",
        "results_text": "建议在 Results 段落中优先报告具有统计学意义的指标，并同时给出效应值及95%置信区间。",
    }


_SUPPORTED_ANALYSIS_TYPES = {"table1", "survival", "regression", "roc", "subgroup", "trend", "correlation"}
_SUPPORTED_VARIABLES = {
    "age",
    "sex",
    "sofa_admission",
    "apache2",
    "mechanical_ventilation",
    "crrt",
    "vasopressor",
    "los_icu_days",
    "primary_diagnosis",
    "icu_mortality",
    # 评分类
    "gcs_admission",
    "rass_admission",
    "sofa_max",
    "apache2_max",
    # 检验类
    "lactate_admission",
    "creatinine_admission",
    "albumin_admission",
    "pct_admission",
    "wbc_admission",
    "hemoglobin_admission",
    "platelet_admission",
    "pf_ratio_admission",
    "bnp_admission",
    # 治疗类
    "vasopressor_days",
    "mv_days",
    # 结局类
    "hospital_mortality",
    "mortality_28d",
    "icu_readmission",
}


def _normalize_ai_plan(raw: dict[str, Any]) -> dict[str, Any]:
    plan = raw.get("plan") if isinstance(raw.get("plan"), dict) else raw
    if not isinstance(plan, dict):
        return {}
    cohort = plan.get("cohort") if isinstance(plan.get("cohort"), dict) else {}
    analyses_raw = plan.get("analyses")
    analyses: list[dict[str, Any]] = []
    if isinstance(analyses_raw, list):
        for item in analyses_raw:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type not in _SUPPORTED_ANALYSIS_TYPES:
                continue
            params = item.get("params") if isinstance(item.get("params"), dict) else {}
            analyses.append({"type": item_type, "params": params})
    selected_vars = [
        token
        for token in [str(item).strip() for item in (plan.get("selected_variables") or [])]
        if token in _SUPPORTED_VARIABLES
    ]
    filters = []
    for row in cohort.get("filters") or []:
        if not isinstance(row, dict):
            continue
        field = str(row.get("field") or "").strip()
        operator = str(row.get("operator") or "").strip()
        if not field or not operator:
            continue
        filters.append({"field": field, "operator": operator, "value": row.get("value")})
    group_by_raw = str(plan.get("group_by") or "").strip()
    allowed_group_by = {"outcome", "icu_mortality", "hospital_mortality", "mortality_28d", "discharge_dest", "los_icu_group", "sex"}
    normalized = {
        "prep_mode": str(plan.get("prep_mode") or "").strip() or "dept",
        "cohort": {
            "use_current_dept": bool(cohort.get("use_current_dept")),
            "cohort_id": str(cohort.get("cohort_id") or "").strip() or None,
            "patient_scope": str(cohort.get("patient_scope") or 'all').strip() or 'all',
            "filters": filters,
        },
        "group_by": group_by_raw if group_by_raw in allowed_group_by else "outcome",
        "selected_variables": selected_vars,
        "analyses": analyses,
        "explanation": str(raw.get("explanation") or "").strip() if isinstance(raw, dict) else "",
    }
    return normalized


def _fallback_ai_plan(query: str) -> dict[str, Any]:
    text = str(query or "").lower()
    analyses = [{"type": "table1", "params": {}}]
    if "回归" in text or "regression" in text:
        analyses.append({"type": "regression", "params": {}})
    if "相关" in text or "correlation" in text:
        analyses.append({"type": "correlation", "params": {}})
    if "趋势" in text or "trend" in text:
        analyses.append({"type": "trend", "params": {}})
    return {
        "prep_mode": "dept",
        "cohort": {"use_current_dept": True, "cohort_id": None, "patient_scope": 'all', "filters": []},
        "group_by": "outcome",
        "selected_variables": ["age", "sex", "sofa_admission", "apache2", "los_icu_days", "icu_mortality"],
        "analyses": analyses,
        "explanation": "已按默认科研流程配置：当前科室全部患者 + 结局分组 + 常用变量 + 目标分析。",
    }


@router.post("/ai/plan")
async def api_ai_plan(req: AIPlanRequest):
    cfg = runtime.config or get_config()
    system_prompt = """
你是 ICU 科研分析配置助手。
请把用户自然语言需求拆解为研究工作台可执行 JSON。
只输出 JSON，不要附加文字。
JSON 结构：
{
  "plan": {
    "prep_mode": "saved|dept|builder",
    "cohort": {
      "use_current_dept": true,
      "cohort_id": null,
      "patient_scope": "all",
      "filters": [{"field": "age", "operator": "range", "value": [18, 80]}]
    },
    "group_by": "outcome|icu_mortality|hospital_mortality|mortality_28d|discharge_dest|los_icu_group|sex",
    "selected_variables": ["age", "sex"],
    "analyses": [{"type": "table1", "params": {}}]
  },
  "explanation": "简短中文说明"
}
可用变量字段：age, sex, sofa_admission, apache2, mechanical_ventilation, crrt, vasopressor, los_icu_days, primary_diagnosis, icu_mortality。
过滤字段建议：age, sex, diagnosis, los_icu_days, sofa_max, apache2_max, mechanical_ventilation, crrt, vasopressor, outcome, admission_time, alert_type。
"""
    payload = {"query": req.query, "scope": req.scope}
    try:
        llm_result = await call_llm_chat(
            cfg=cfg,
            system_prompt=system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
            model=cfg.llm_model_medical or cfg.llm_fast_model,
            temperature=0.1,
            max_tokens=2200,
            timeout_seconds=90,
        )
        parsed = _extract_json_object(str(llm_result.get("text") or "")) or {}
        normalized = _normalize_ai_plan(parsed)
        if not normalized:
            normalized = _fallback_ai_plan(req.query)
        return {
            "plan": normalized,
            "model": llm_result.get("model"),
            "degraded_mode": llm_result.get("degraded_mode"),
        }
    except Exception as exc:
        logger.warning("AI plan fallback due to error: %s", exc)
        return {
            "plan": _fallback_ai_plan(req.query),
            "degraded_mode": True,
            "error": str(exc),
        }


@router.post("/ai/interpret")
async def api_ai_interpret(req: AIInterpretRequest):
    cfg = runtime.config or get_config()
    lang = str(req.language or "zh").lower()
    system_prompt = (
        "你是 ICU 医学统计与论文写作助手。"
        "请根据输入的统计结果生成结构化 JSON，字段必须包含 interpretation, methods_text, results_text。"
        "不要输出 JSON 以外的内容。"
    )
    user_payload = {
        "analysis_type": req.analysis_type,
        "language": req.language,
        "results": req.results,
    }
    try:
        llm_result = await call_llm_chat(
            cfg=cfg,
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False, indent=2),
            model=cfg.llm_model_medical or cfg.llm_fast_model,
            temperature=0.2,
            max_tokens=1800,
            timeout_seconds=90,
        )
        parsed = _extract_json_object(str(llm_result.get("text") or ""))
        if not parsed:
            parsed = _fallback_ai_text(req.analysis_type, req.language)
        return {
            "interpretation": str(parsed.get("interpretation") or ""),
            "methods_text": str(parsed.get("methods_text") or ""),
            "results_text": str(parsed.get("results_text") or ""),
            "model": llm_result.get("model"),
            "degraded_mode": llm_result.get("degraded_mode"),
        }
    except Exception as exc:
        logger.warning("AI interpret fallback due to error: %s", exc)
        return _fallback_ai_text(req.analysis_type, req.language)
