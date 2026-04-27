from __future__ import annotations

import re
import sys
import json
from pathlib import Path
from typing import Any

import pytest
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.ai_modules import chat
from app.services.llm_runtime import LLMRuntimeUnavailableError


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)
        self._idx = 0

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
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = [dict(row) for row in docs]

    def find(self, query: dict[str, Any]) -> _Cursor:
        rows = [row for row in self.docs if self._match(row, query)]
        return _Cursor(rows)

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for row in self.docs:
            if self._match(row, query):
                return dict(row)
        return None

    @classmethod
    def _eq(cls, left: Any, right: Any) -> bool:
        return left == right or str(left) == str(right)

    @classmethod
    def _match(cls, row: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, value in query.items():
            if key == "$or":
                if not any(cls._match(row, item) for item in value):
                    return False
                continue
            current = row.get(key)
            if isinstance(value, dict):
                if "$in" in value:
                    if not any(cls._eq(current, item) for item in value.get("$in") or []):
                        return False
                    continue
                if "$regex" in value:
                    pattern = str(value.get("$regex") or "")
                    flags = re.IGNORECASE if "i" in str(value.get("$options") or "").lower() else 0
                    if re.search(pattern, str(current or ""), flags=flags) is None:
                        return False
                    continue
            if not cls._eq(current, value):
                return False
        return True


class _FakeDb:
    def __init__(self, patient_docs: list[dict[str, Any]]) -> None:
        self._patient = _Collection(patient_docs)

    def col(self, name: str) -> _Collection:
        if name != "patient":
            raise AssertionError(f"unexpected collection: {name}")
        return self._patient


@pytest.mark.asyncio
async def test_resolve_patient_from_message_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    p1 = ObjectId()
    p2 = ObjectId()
    db = _FakeDb(
        [
            {"_id": p1, "name": "张三", "hisPid": "H1001", "status": "admitted"},
            {"_id": p2, "name": "李四", "hisPid": "H2002", "status": "admitted"},
        ]
    )
    monkeypatch.setattr(chat.runtime, "db", db, raising=False)

    patient, resolved_id, source, note = await chat._resolve_patient_from_payload(
        None,
        "请评估住院号 H1001 患者当前感染风险。",
    )

    assert patient is not None
    assert resolved_id == str(p1)
    assert source == "message_mention"
    assert "匹配患者" in note


@pytest.mark.asyncio
async def test_resolve_patient_message_name_overrides_invalid_payload_id(monkeypatch: pytest.MonkeyPatch) -> None:
    target_id = ObjectId()
    db = _FakeDb([{"_id": target_id, "name": "王小明", "hisPid": "HX009", "status": "admitted"}])
    monkeypatch.setattr(chat.runtime, "db", db, raising=False)

    patient, resolved_id, source, _ = await chat._resolve_patient_from_payload(
        "not-a-valid-objectid",
        "患者 王小明 现在乳酸升高，怎么处理？",
    )

    assert patient is not None
    assert resolved_id == str(target_id)
    assert source == "message_mention"


@pytest.mark.asyncio
async def test_ai_chat_consult_degrades_when_circuit_breaker_open(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build_patient_context(patient_id: str | None, message: str):
        del patient_id, message
        return "", "", None, "none", ""

    async def _fake_call_api_llm(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        raise LLMRuntimeUnavailableError("LLM runtime circuit breaker open, retry after 164.0s")

    monkeypatch.setattr(chat, "_build_patient_context", _fake_build_patient_context)
    monkeypatch.setattr(chat, "call_api_llm", _fake_call_api_llm)

    payload = chat.ChatConsultPayload(message="请给出处理建议", history=[], patient_id=None)
    res = await chat.ai_chat_consult(payload)

    body = json.loads(res.body.decode("utf-8")) if hasattr(res, "body") else {}
    assert hasattr(res, "status_code")
    assert res.status_code == 200
    assert body.get("code") == 0
    assert body.get("degraded") is True
    assert body.get("retry_after_seconds") == 164.0


def test_strip_markdown_for_display_removes_think_blocks() -> None:
    raw = "<think>这里是内部推理</think>\n**结论**：建议先复查乳酸并评估灌注。"
    assert chat._strip_markdown_for_display(raw) == "结论：建议先复查乳酸并评估灌注。"


def test_extract_llm_stream_delta_skips_reasoning_blocks() -> None:
    payload = {
        "choices": [
            {
                "delta": {
                    "content": [
                        {"type": "reasoning_content", "text": "先思考"},
                        {"type": "output_text", "text": "最终答案"},
                    ]
                }
            }
        ]
    }
    assert chat._extract_llm_stream_delta(payload) == "最终答案"


def test_finalize_ai_consult_answer_enforces_fixed_sections() -> None:
    text = "感染可能性高，需要先复查乳酸并评估灌注。"
    result = chat._finalize_ai_consult_answer(text)
    assert "初步判断：" in result
    assert "风险点：" in result
    assert "建议检查：" in result
    assert "下一步处理：" in result
    assert "1、" in result


def test_normalize_ai_consult_section_content_adds_numbering() -> None:
    assert chat._normalize_ai_consult_section_content("感染风险高；循环不稳定；需动态复评") == (
        "1、感染风险高\n2、循环不稳定\n3、需动态复评"
    )


def test_resolve_ai_consult_limits_supports_patient_or_complex_case() -> None:
    normal = chat._resolve_ai_consult_limits(message="请给我一个初步建议", history=[], patient_context="")
    patient_bound = chat._resolve_ai_consult_limits(message="请结合该患者情况分析", history=[], patient_context="患者标签: 1床")
    complex_case = chat._resolve_ai_consult_limits(
        message="患者乳酸持续升高且去甲肾上腺素加量，帮我做鉴别诊断和下一步处理",
        history=[],
        patient_context="",
    )

    assert normal[0] == 3200
    assert patient_bound[0] >= 4096
    assert complex_case[0] >= 4096


@pytest.mark.asyncio
async def test_ai_chat_consult_strips_think_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build_patient_context(patient_id: str | None, message: str):
        del patient_id, message
        return "", "", None, "none", ""

    async def _fake_call_api_llm(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return "<think>内部分析</think>\n1. 初步判断：感染可能性高。"

    monkeypatch.setattr(chat, "_build_patient_context", _fake_build_patient_context)
    monkeypatch.setattr(chat, "call_api_llm", _fake_call_api_llm)

    payload = chat.ChatConsultPayload(message="请给出处理建议", history=[], patient_id=None)
    res = await chat.ai_chat_consult(payload)

    assert res.get("code") == 0
    assert "<think>" not in str(res.get("answer") or "")
    assert "内部分析" not in str(res.get("answer") or "")
    assert "初步判断" in str(res.get("answer") or "")
    assert "风险点" in str(res.get("answer") or "")
    assert res.get("answer_max_tokens") == 3200
