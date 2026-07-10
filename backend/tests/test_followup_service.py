from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.followup_service import FollowupService


class _InsertResult:
    def __init__(self, inserted_id: int) -> None:
        self.inserted_id = inserted_id


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key: str, direction: int) -> "_Cursor":
        self._docs.sort(key=lambda row: row.get(key) or datetime.min, reverse=direction == -1)
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

    def find(self, query: dict[str, Any] | None = None) -> _Cursor:
        query = query or {}
        rows = [doc for doc in self.docs if self._match(doc, query)]
        return _Cursor(rows)

    async def find_one(self, query: dict[str, Any], sort: list[tuple[str, int]] | None = None) -> dict[str, Any] | None:
        rows = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda row: row.get(key) or datetime.min, reverse=direction == -1)
        return dict(rows[0]) if rows else None

    async def insert_one(self, doc: dict[str, Any]) -> _InsertResult:
        row = dict(doc)
        row.setdefault("_id", len(self.docs) + 1)
        self.docs.append(row)
        return _InsertResult(int(row["_id"]))

    async def update_one(self, selector: dict[str, Any], update: dict[str, Any]) -> None:
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    self._assign(doc, key, value)
                return
        row = dict(selector)
        for key, value in update.get("$set", {}).items():
            self._assign(row, key, value)
        self.docs.append(row)

    @classmethod
    def _assign(cls, doc: dict[str, Any], dotted: str, value: Any) -> None:
        target = doc
        parts = dotted.split(".")
        for part in parts[:-1]:
            if not isinstance(target.get(part), dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    @classmethod
    def _match(cls, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, value in query.items():
            if key == "$or":
                if not any(cls._match(doc, item) for item in value):
                    return False
                continue
            current = cls._get(doc, key)
            if isinstance(value, dict):
                if "$in" in value and current not in value["$in"]:
                    return False
            elif current != value:
                return False
        return True

    @staticmethod
    def _get(doc: dict[str, Any], dotted: str) -> Any:
        target: Any = doc
        for part in dotted.split("."):
            if not isinstance(target, dict):
                return None
            target = target.get(part)
        return target


class _FakeDb:
    def __init__(self) -> None:
        self.collections = {
            "patient": _Collection([{"_id": "p1", "name": "张三", "hisBed": "12", "hisDept": "ICU"}]),
            "score": _Collection([]),
            "followup_cases": _Collection([]),
            "followup_tasks": _Collection([]),
            "rehab_referrals": _Collection([]),
        }

    def col(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


@pytest.mark.asyncio
async def test_sync_case_from_pics_creates_followup_case_and_patient_snapshot() -> None:
    db = _FakeDb()
    service = FollowupService(db=db)
    patient_doc = {"_id": "p1", "name": "张三", "hisBed": "12", "hisDept": "ICU"}
    assessment = {
        "overall_score": 76,
        "severity": "high",
        "summary": "PICS 综合风险偏高",
        "suggestion": "建议转入长期随访",
        "dimensions": {"physical": {"score": 80}},
        "evidence": ["机械通气时间长"],
        "transfer_candidate": True,
    }

    case_doc = await service.sync_case_from_pics(patient_doc=patient_doc, assessment=assessment, risk_record_id="r1", now=datetime.now())

    assert case_doc is not None
    assert case_doc["source_module"] == "pics_risk"
    assert case_doc["priority"] == "high"
    patient_doc_after = db.col("patient").docs[0]
    assert patient_doc_after["current_profile"]["followup_case"]["case_id"] == case_doc["case_id"]


@pytest.mark.asyncio
async def test_create_followup_task_and_rehab_referral_promote_case() -> None:
    db = _FakeDb()
    service = FollowupService(db=db)
    patient_doc = {"_id": "p1", "name": "张三", "hisBed": "12", "hisDept": "ICU"}
    assessment = {
        "overall_score": 68,
        "severity": "warning",
        "summary": "存在身体和认知恢复风险",
        "suggestion": "建议启动康复和出院后随访",
        "dimensions": {"physical": {"score": 72}, "cognitive": {"score": 58}},
        "evidence": ["谵妄风险", "长期卧床"],
        "transfer_candidate": True,
    }
    await service.sync_case_from_pics(patient_doc=patient_doc, assessment=assessment, risk_record_id="r2", now=datetime.now())

    task_doc = await service.create_followup_task(
        patient_doc=patient_doc,
        payload={"template_key": "pics_7d_call", "actor": "tester"},
        now=datetime.now(),
    )
    referral_doc = await service.create_rehab_referral(
        patient_doc=patient_doc,
        payload={"template_key": "pics_rehab", "actor": "tester"},
        now=datetime.now(),
    )
    overview = await service.build_patient_overview(patient_id="p1")

    assert task_doc["template_key"] == "pics_7d_call"
    assert referral_doc["template_key"] == "pics_rehab"
    assert overview["case"]["status"] == "active"
    assert overview["summary"]["open_tasks"] == 1
    assert overview["summary"]["pending_referrals"] == 1
