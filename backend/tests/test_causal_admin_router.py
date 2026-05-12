from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest
from bson import ObjectId
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import admin


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def sort(self, *args, **kwargs):
        return self

    def limit(self, count: int):
        self.rows = self.rows[:count]
        return self

    def __aiter__(self):
        self.idx = 0
        return self

    async def __anext__(self):
        if self.idx >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self.idx]
        self.idx += 1
        return row


class _Col:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.inserted: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any]):
        return _Cursor([row for row in self.rows if all(row.get(k) == v for k, v in query.items())])

    async def find_one(self, query: dict[str, Any], *args, **kwargs):
        del args, kwargs
        for row in self.rows + self.inserted:
            if all(str(row.get(k)) == str(v) for k, v in query.items()):
                return row
        return None

    async def insert_one(self, record: dict[str, Any]):
        record = dict(record)
        record["_id"] = ObjectId()
        self.inserted.append(record)
        return type("Result", (), {"inserted_id": record["_id"]})()

    async def update_one(self, *args, **kwargs):
        return None


class _Db:
    def __init__(self) -> None:
        self.candidate = {"_id": ObjectId(), "candidate_id": "c1", "status": "pending", "finding_key": "lactate_rise", "cause_node": {"key": "x"}}
        self.cols = {
            "kg_causal_candidates": _Col([self.candidate]),
            "kg_causal_approvals": _Col([]),
        }

    def col(self, name: str):
        return self.cols[name]


def _request(role: str = "causal_reviewer") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"x-user-role", role.encode()), (b"x-user-id", b"reviewer-a")]})


@pytest.mark.asyncio
async def test_causal_discovery_approve_writes_versioned_record(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _Db()
    monkeypatch.setattr(admin.runtime, "db", db, raising=False)

    result = await admin.causal_discovery_approve(_request(), {"candidate_id": "c1", "approved": True, "actor": "reviewer-a"})

    assert result["code"] == 0
    assert result["record"]["version"] == 1
    assert result["record"]["enabled"] is True


@pytest.mark.asyncio
async def test_causal_discovery_requires_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin.runtime, "db", _Db(), raising=False)
    with pytest.raises(Exception):
        await admin.causal_discovery_candidates(_request("doctor"), status="pending", limit=10)
