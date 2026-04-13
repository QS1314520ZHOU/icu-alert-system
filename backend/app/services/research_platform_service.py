from __future__ import annotations

import importlib.metadata
import importlib.util
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.serialization import serialize_doc

OPTIONAL_RESEARCH_DEPS: list[tuple[str, str]] = [
    ("pandas", "科研表格与数据清洗"),
    ("numpy", "科研数值计算"),
    ("scipy", "统计检验"),
    ("statsmodels", "回归模型"),
    ("lifelines", "生存分析"),
    ("sklearn", "机器学习 / ROC"),
    ("matplotlib", "图表导出"),
    ("docx", "Word 表格导出"),
]


def _safe_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return None


def _dep_state(module_name: str, purpose: str) -> dict[str, Any]:
    found = importlib.util.find_spec(module_name) is not None
    return {
        "module": module_name,
        "purpose": purpose,
        "available": found,
        "version": _safe_version(module_name) if found else None,
    }


async def collect_research_platform_status(*, db, config: Any) -> dict[str, Any]:
    deps = [_dep_state(name, purpose) for name, purpose in OPTIONAL_RESEARCH_DEPS]
    available_count = sum(1 for row in deps if row.get("available"))
    missing = [row for row in deps if not row.get("available")]

    analytics_pending = await db.col("research_analytics_tasks").count_documents({"status": {"$in": ["pending", "processing"]}})
    export_pending = await db.col("research_export_tasks").count_documents({"status": {"$in": ["pending", "processing"]}})
    cohort_count = await db.col("research_cohorts").count_documents({})
    session_count = await db.col("research_analysis_sessions").count_documents({})
    artifact_count = await db.col("research_artifacts").count_documents({})

    export_dir = Path("backend/exports").resolve()
    analytics_export_dir = (export_dir / "research_analytics").resolve()
    export_dir.mkdir(parents=True, exist_ok=True)
    analytics_export_dir.mkdir(parents=True, exist_ok=True)

    healthy = all(row.get("available") for row in deps)
    level = "green" if healthy else ("yellow" if available_count >= len(deps) // 2 else "red")
    summary = (
        "科研平台依赖完整，可稳定执行分析与导出。"
        if healthy
        else f"存在 {len(missing)} 个科研依赖缺失，部分高级分析或导出能力会降级。"
    )
    return {
        "level": level,
        "summary": summary,
        "dependencies": deps,
        "missing_dependencies": missing,
        "counts": {
            "cohorts": cohort_count,
            "sessions": session_count,
            "analytics_jobs_pending": analytics_pending,
            "export_jobs_pending": export_pending,
            "artifacts": artifact_count,
        },
        "paths": {
            "export_dir": str(export_dir),
            "analytics_export_dir": str(analytics_export_dir),
        },
        "checked_at": datetime.now(timezone.utc),
    }


async def persist_research_platform_status(*, db, status: dict[str, Any]) -> dict[str, Any]:
    checked_at = status.get("checked_at")
    if not isinstance(checked_at, datetime):
        checked_at = datetime.now(timezone.utc)
        status["checked_at"] = checked_at
    day = checked_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    document = {
        "date": day,
        "level": status.get("level"),
        "summary": status.get("summary"),
        "dependencies": status.get("dependencies") or [],
        "missing_dependencies": status.get("missing_dependencies") or [],
        "counts": status.get("counts") or {},
        "paths": status.get("paths") or {},
        "checked_at": checked_at,
        "updated_at": checked_at,
    }
    existing = await db.col("research_runtime_checks").find_one({"date": day})
    if existing:
        await db.col("research_runtime_checks").update_one({"_id": existing["_id"]}, {"$set": document})
        existing.update(document)
        return existing
    result = await db.col("research_runtime_checks").insert_one(document)
    document["_id"] = result.inserted_id
    return document


async def list_research_jobs(*, db, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    analytics_cursor = db.col("research_analytics_tasks").find({"created_by": str(user_id or "anonymous")}, {"_id": 0}).sort("created_at", -1).limit(limit)
    async for doc in analytics_cursor:
        rows.append(
            {
                "job_id": str(doc.get("task_id") or ""),
                "kind": "analytics",
                "status": str(doc.get("status") or ""),
                "progress": int(doc.get("progress") or 0),
                "title": str(doc.get("task_type") or "analytics"),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
                "error": doc.get("error"),
                "payload": doc.get("params") or {},
                "result": doc.get("result"),
            }
        )

    export_cursor = db.col("research_export_tasks").find({"created_by": str(user_id or "anonymous")}, {"_id": 0}).sort("created_at", -1).limit(limit)
    async for doc in export_cursor:
        rows.append(
            {
                "job_id": str(doc.get("task_id") or ""),
                "kind": "export",
                "status": str(doc.get("status") or ""),
                "progress": int(doc.get("progress") or 0),
                "title": str(((doc.get("scope_summary") or {}) if isinstance(doc.get("scope_summary"), dict) else {}).get("export_mode") or "export"),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
                "error": doc.get("error"),
                "payload": doc.get("params") or {},
                "result": {
                    "file_path": doc.get("file_path"),
                    "scope_summary": doc.get("scope_summary"),
                    "result_stats": doc.get("result_stats"),
                },
            }
        )

    rows.sort(key=lambda row: row.get("created_at") or datetime.min, reverse=True)
    return [serialize_doc(row) for row in rows[: max(1, min(limit, 200))]]


def _analytics_file_download_url(file_name: str) -> str:
    return f"/api/research/analytics/files/{file_name}"


def _export_task_download_url(task_id: str) -> str:
    return f"/api/research/export/{task_id}/download"


async def register_research_artifact(
    *,
    db,
    created_by: str,
    artifact_type: str,
    title: str,
    file_path: str,
    file_name: str,
    download_url: str,
    source: str,
    meta: dict[str, Any] | None = None,
    source_task_id: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    doc = {
        "artifact_id": f"artifact_{now.strftime('%Y%m%d_%H%M%S_%f')}",
        "artifact_type": str(artifact_type or "file").strip() or "file",
        "title": str(title or file_name or "研究产物").strip() or "研究产物",
        "file_path": str(file_path or "").strip(),
        "file_name": str(file_name or "").strip(),
        "download_url": str(download_url or "").strip(),
        "source": str(source or "").strip(),
        "source_task_id": str(source_task_id or "").strip() or None,
        "created_by": str(created_by or "anonymous"),
        "meta": meta or {},
        "created_at": now,
        "updated_at": now,
    }
    existing = await db.col("research_artifacts").find_one(
        {
            "file_path": doc["file_path"],
            "created_by": doc["created_by"],
        },
        sort=[("created_at", -1)],
    )
    if existing:
        await db.col("research_artifacts").update_one({"_id": existing["_id"]}, {"$set": doc})
        existing.update(doc)
        return existing
    result = await db.col("research_artifacts").insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def list_research_artifacts(*, db, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = db.col("research_artifacts").find({"created_by": str(user_id or "anonymous")}, {"_id": 0}).sort("created_at", -1).limit(limit)
    async for doc in cursor:
        rows.append(serialize_doc(doc))

    if rows:
        return rows

    export_cursor = db.col("research_export_tasks").find(
        {
            "created_by": str(user_id or "anonymous"),
            "status": "completed",
            "file_path": {"$ne": None},
        },
        {"_id": 0},
    ).sort("completed_at", -1).limit(limit)
    async for doc in export_cursor:
        task_id = str(doc.get("task_id") or "")
        file_path = str(doc.get("file_path") or "")
        file_name = Path(file_path).name if file_path else ""
        rows.append(
            serialize_doc(
                {
                    "artifact_id": f"export_{task_id}",
                    "artifact_type": "export_bundle",
                    "title": file_name or "研究导出包",
                    "file_path": file_path,
                    "file_name": file_name,
                    "download_url": _export_task_download_url(task_id),
                    "source": "research_export_tasks",
                    "source_task_id": task_id,
                    "meta": {
                        "scope_summary": doc.get("scope_summary"),
                        "result_stats": doc.get("result_stats"),
                    },
                    "created_at": doc.get("completed_at") or doc.get("created_at"),
                    "updated_at": doc.get("completed_at") or doc.get("created_at"),
                }
            )
        )
    return rows[: max(1, min(limit, 200))]


async def job_summary(*, db, user_id: str) -> dict[str, Any]:
    jobs = await list_research_jobs(db=db, user_id=user_id, limit=200)
    counter = Counter(str(item.get("status") or "unknown") for item in jobs)
    return {
        "total": len(jobs),
        "pending": counter.get("pending", 0),
        "processing": counter.get("processing", 0),
        "completed": counter.get("completed", 0),
        "failed": counter.get("failed", 0),
    }
