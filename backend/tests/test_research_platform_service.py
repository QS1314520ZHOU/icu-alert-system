from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.research_platform_service import collect_research_platform_status, list_research_jobs


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key: str, direction: int) -> "_Cursor":
        self._docs.sort(key=lambda row: row.get(key) or datetime.min.replace(tzinfo=timezone.utc), reverse=direction == -1)
        return self

    def limit(self, count: int) -> "_Cursor":
        self._docs = self._docs[:count]
        return self

    def __aiter__(self) -> "_Cursor":
        self._idx = 0
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._idx >= len(self._docs):
            raise StopAsyncIteration
        row = self._docs[self._idx]
        self._idx += 1
        return dict(row)


class _Collection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = [dict(doc) for doc in (docs or [])]

    async def count_documents(self, query: dict[str, Any]) -> int:
        if not query:
            return len(self.docs)
        if "status" in query and isinstance(query["status"], dict) and "$in" in query["status"]:
            allowed = set(query["status"]["$in"])
            return len([row for row in self.docs if row.get("status") in allowed])
        return len(self.docs)

    def find(self, query: dict[str, Any], projection: dict[str, int] | None = None) -> _Cursor:
        rows = [row for row in self.docs if not query or all(row.get(k) == v for k, v in query.items())]
        if projection:
            reduced = []
            for row in rows:
                item = {}
                for key, enabled in projection.items():
                    if enabled and key in row:
                        item[key] = row[key]
                reduced.append(item)
            rows = reduced
        return _Cursor(rows)


class _FakeDb:
    def __init__(self) -> None:
        self.collections = {
            "research_analytics_tasks": _Collection([
                {"task_id": "a1", "created_by": "anonymous", "status": "pending", "progress": 10, "task_type": "table1", "created_at": datetime.now(timezone.utc)},
                {"task_id": "a2", "created_by": "anonymous", "status": "completed", "progress": 100, "task_type": "roc", "created_at": datetime.now(timezone.utc)},
            ]),
            "research_export_tasks": _Collection([
                {"task_id": "e1", "created_by": "anonymous", "status": "processing", "progress": 60, "created_at": datetime.now(timezone.utc)},
            ]),
            "research_cohorts": _Collection([{"cohort_id": "c1"}]),
            "research_analysis_sessions": _Collection([{"session_id": "s1"}]),
            "research_artifacts": _Collection([{"artifact_id": "r1"}]),
        }

    def col(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


@pytest.mark.asyncio
async def test_collect_research_platform_status_returns_dependency_and_count_summary() -> None:
    status = await collect_research_platform_status(db=_FakeDb(), config=None)
    assert "dependencies" in status
    assert "counts" in status
    assert status["counts"]["cohorts"] == 1
    assert status["counts"]["artifacts"] == 1
    assert status["counts"]["analytics_jobs_pending"] == 1


@pytest.mark.asyncio
async def test_list_research_jobs_merges_analytics_and_export_tasks() -> None:
    rows = await list_research_jobs(db=_FakeDb(), user_id="anonymous", limit=20)
    assert len(rows) == 3
    kinds = {row["kind"] for row in rows}
    assert kinds == {"analytics", "export"}
