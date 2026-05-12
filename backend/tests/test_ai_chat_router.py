from __future__ import annotations

import re
import sys
import json
from pathlib import Path
from typing import Any

import pytest
from bson import ObjectId
from starlette.requests import Request

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


def _fake_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/ai/chat-consult", "headers": []})


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

    patients, resolved_ids, source, note = await chat._resolve_patient_from_payload(
        None,
        None,
        "请评估住院号 H1001 患者当前感染风险。",
    )

    patient = patients[0] if patients else None
    assert patient is not None
    assert resolved_ids == [str(p1)]
    assert source == "message_mention"
    assert "匹配" in note


@pytest.mark.asyncio
async def test_resolve_patient_message_name_overrides_invalid_payload_id(monkeypatch: pytest.MonkeyPatch) -> None:
    target_id = ObjectId()
    db = _FakeDb([{"_id": target_id, "name": "王小明", "hisPid": "HX009", "status": "admitted"}])
    monkeypatch.setattr(chat.runtime, "db", db, raising=False)

    patients, resolved_ids, source, _ = await chat._resolve_patient_from_payload(
        "not-a-valid-objectid",
        None,
        "患者 王小明 现在乳酸升高，怎么处理？",
    )

    patient = patients[0] if patients else None
    assert patient is not None
    assert resolved_ids == [str(target_id)]
    assert source == "message_mention"


@pytest.mark.asyncio
async def test_ai_chat_consult_degrades_when_circuit_breaker_open(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build_patient_context(patient_id: str | None, patient_ids: list[str] | None, message: str):
        del patient_id, patient_ids, message
        return "", "", None, [], "none", ""

    async def _fake_call_api_llm(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        raise LLMRuntimeUnavailableError("LLM runtime circuit breaker open, retry after 164.0s")

    async def _fake_write_ai_consult_log(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(chat, "_build_patient_context", _fake_build_patient_context)
    monkeypatch.setattr(chat, "call_api_llm", _fake_call_api_llm)
    monkeypatch.setattr(chat, "_write_ai_consult_log", _fake_write_ai_consult_log)

    payload = chat.ChatConsultPayload(message="请给出处理建议", history=[], patient_id=None)
    res = await chat.ai_chat_consult(payload, _fake_request())

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


def test_finalize_ai_consult_answer_replaces_placeholder_sections() -> None:
    text = "初步判断：\n-\n\n风险点：\n暂无\n\n建议检查：\nN/A\n\n下一步处理：\n1、-"
    result = chat._finalize_ai_consult_answer(text)

    assert "初步判断：\n1、-" not in result
    assert "风险点：\n1、暂无" not in result
    assert "建议检查：\n1、N/A" not in result
    assert "下一步处理：\n1、-" not in result
    assert "当前回答未形成有效初步判断" in result
    assert "请补充关键化验" in result


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
    async def _fake_build_patient_context(patient_id: str | None, patient_ids: list[str] | None, message: str):
        del patient_id, patient_ids, message
        return "", "", None, [], "none", ""

    async def _fake_call_api_llm(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return "<think>内部分析</think>\n1. 初步判断：感染可能性高。"

    async def _fake_write_ai_consult_log(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(chat, "_build_patient_context", _fake_build_patient_context)
    monkeypatch.setattr(chat, "call_api_llm", _fake_call_api_llm)
    monkeypatch.setattr(chat, "_write_ai_consult_log", _fake_write_ai_consult_log)

    payload = chat.ChatConsultPayload(message="请给出处理建议", history=[], patient_id=None)
    res = await chat.ai_chat_consult(payload, _fake_request())

    assert res.get("code") == 0
    assert "<think>" not in str(res.get("answer") or "")
    assert "内部分析" not in str(res.get("answer") or "")
    assert "初步判断" in str(res.get("answer") or "")
    assert "风险点" in str(res.get("answer") or "")
    assert res.get("answer_max_tokens") == 3200


@pytest.mark.asyncio
async def test_ai_chat_consult_returns_clarification_before_final_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build_patient_context(patient_id: str | None, patient_ids: list[str] | None, message: str):
        del patient_id, patient_ids, message
        return "患者标签: 1床\n主要诊断: 脓毒症", "1床 · 张三 · 脓毒症", "p1", ["p1"], "payload", ""

    async def _fake_propose_information_gaps(patient_context: str):
        assert "患者标签" in patient_context
        return [{"rank": 1, "question": "最近 2 小时乳酸和 MAP 趋势如何？", "reason": "会改变复苏策略", "information_gain": 0.9}]

    async def _fake_call_api_llm(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        raise AssertionError("final LLM should not be called before clarification is answered")

    async def _fake_write_ai_consult_log(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(chat, "_build_patient_context", _fake_build_patient_context)
    monkeypatch.setattr(chat, "propose_information_gaps", _fake_propose_information_gaps)
    monkeypatch.setattr(chat, "call_api_llm", _fake_call_api_llm)
    monkeypatch.setattr(chat, "_write_ai_consult_log", _fake_write_ai_consult_log)

    payload = chat.ChatConsultPayload(message="请给出下一步处理建议", history=[], patient_id="p1")
    res = await chat.ai_chat_consult(payload, _fake_request())

    assert res.get("code") == 0
    assert res.get("message_type") == "clarification"
    assert res.get("pending_clarifications") == ["最近 2 小时乳酸和 MAP 趋势如何？"]
    assert "为了避免建议偏差" in str(res.get("answer") or "")


@pytest.mark.asyncio
async def test_ai_chat_consult_continues_after_clarification_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_build_patient_context(patient_id: str | None, patient_ids: list[str] | None, message: str):
        del patient_id, patient_ids, message
        return "患者标签: 1床\n主要诊断: 脓毒症", "1床 · 张三 · 脓毒症", "p1", ["p1"], "payload", ""

    async def _fake_propose_information_gaps(patient_context: str):
        del patient_context
        raise AssertionError("information gaps should not run when pending clarification was answered")

    async def _fake_call_api_llm(*args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return "初步判断：\n感染性休克风险高\n\n下一步处理：\n复查乳酸并评估灌注"

    async def _fake_write_ai_consult_log(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(chat, "_build_patient_context", _fake_build_patient_context)
    monkeypatch.setattr(chat, "propose_information_gaps", _fake_propose_information_gaps)
    monkeypatch.setattr(chat, "call_api_llm", _fake_call_api_llm)
    monkeypatch.setattr(chat, "_write_ai_consult_log", _fake_write_ai_consult_log)

    payload = chat.ChatConsultPayload(
        message="乳酸从 2.1 升到 3.5，MAP 需要去甲肾维持。",
        history=[chat.ChatTurn(role="assistant", content="为了避免建议偏差，我需要先确认：最近 2 小时乳酸和 MAP 趋势如何？")],
        patient_id="p1",
        pending_clarifications=["最近 2 小时乳酸和 MAP 趋势如何？"],
    )
    res = await chat.ai_chat_consult(payload, _fake_request())

    assert res.get("code") == 0
    assert res.get("message_type") != "clarification"
    assert "下一步处理：" in str(res.get("answer") or "")
