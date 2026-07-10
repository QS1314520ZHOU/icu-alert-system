from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.alert_engine.base import BaseEngine


class _Collection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query: dict[str, Any], sort: list[tuple[str, int]] | None = None) -> dict[str, Any] | None:
        rows = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda row: row.get(key), reverse=direction == -1)
        return dict(rows[0]) if rows else None

    def find(self, query: dict[str, Any] | None = None, projection: dict[str, int] | None = None):
        del query, projection
        return _Cursor([])

    @classmethod
    def _match(cls, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            current = doc.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and current not in expected["$in"]:
                    return False
                if "$gte" in expected and (current is None or current < expected["$gte"]):
                    return False
            elif current != expected:
                return False
        return True


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def sort(self, key: str, direction: int) -> "_Cursor":
        del key, direction
        return self

    def limit(self, count: int) -> "_Cursor":
        del count
        return self

    def __aiter__(self) -> "_Cursor":
        return self

    async def __anext__(self) -> dict[str, Any]:
        raise StopAsyncIteration


class _Db:
    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self.collections = {name: _Collection(rows) for name, rows in collections.items()}

    def col(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


def _engine(score_docs: list[dict[str, Any]] | None = None, bedside_docs: list[dict[str, Any]] | None = None) -> BaseEngine:
    config = SimpleNamespace(
        yaml_cfg={
            "assessments": {
                "cam_icu": {"code": "param_delirium_score"},
                "delirium": {"code": "param_delirium_score"},
            }
        }
    )
    return BaseEngine(_Db({"score": score_docs or [], "bedside": bedside_docs or []}), config)


def test_cam_icu_text_result_treats_unassessable_as_unknown() -> None:
    engine = _engine()

    assert engine._is_positive_text_result("无法评估") is None
    assert engine._is_positive_text_result("CAM-ICU 无法评估，RASS不满足") is None
    assert engine._is_positive_text_result("RASS -4，CAM-ICU不能评估") is None
    assert engine._is_positive_text_result("谵妄") is None
    assert engine._is_positive_text_result("是") is True
    assert engine._is_positive_text_result("CAM-ICU 阳性：谵妄已发生") is True
    assert engine._is_positive_text_result("CAM-ICU 阴性") is False


@pytest.mark.asyncio
async def test_latest_cam_icu_status_ignores_unassessable_score_record() -> None:
    engine = _engine(
        [
            {
                "patient_id": "p1",
                "score_type": "cam_icu",
                "calc_time": datetime.now(),
                "result": "谵妄无法评估",
            }
        ]
    )

    status = await engine._get_latest_cam_icu_status("p1")
    assert status is not None
    assert status["positive"] is None
    assert status["assessable"] is False
