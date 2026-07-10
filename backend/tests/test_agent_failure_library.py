from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.agent_failure_library import AgentFailureLibrary


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def sort(self, *args: Any, **kwargs: Any) -> "_Cursor":
        return self

    def limit(self, *args: Any, **kwargs: Any) -> "_Cursor":
        return self

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._idx >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self._idx]
        self._idx += 1
        return row


class _Collection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def find(self, *args: Any, **kwargs: Any) -> _Cursor:
        return _Cursor(self.rows)


class _Db:
    def __init__(self) -> None:
        self.rows = [
            {"fired_at": datetime.now(), "updated_at": datetime.now(), "outcomes": {"24h": "event_occurred"}, "summary": "12床 张三患者 脓毒症补液建议后24h恶化 13800138000"},
            {"fired_at": datetime.now(), "updated_at": datetime.now(), "adopted": False, "harm": "moderate", "summary": "8床 李四患者 升压建议未采纳"},
            {"fired_at": datetime.now(), "updated_at": datetime.now(), "outcomes": {"24h": "event_occurred"}, "summary": "9床 王五患者 AKI 进展"},
            {"fired_at": datetime.now(), "updated_at": datetime.now(), "outcomes": {"24h": "event_occurred"}, "summary": "10床 赵六患者 呼吸衰竭"},
        ]

    def col(self, name: str) -> _Collection:
        return _Collection(self.rows if name == "alert_outcomes" else [])


@pytest.mark.asyncio
async def test_failure_library_deidentifies_and_limits_top3() -> None:
    lib = AgentFailureLibrary(db=_Db())
    cases = await lib.get_relevant_failures({"problem_list": ["脓毒症", "AKI"], "recent_alerts_24h": []})

    assert len(cases) == 3
    assert all(len(item["lesson"]) < 200 for item in cases)
    blob = " ".join(item["lesson"] for item in cases)
    assert "张三" not in blob
    assert "13800138000" not in blob
    assert "B##床" in blob or "P###" in blob
