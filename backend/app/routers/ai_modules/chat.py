from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from pydantic import BaseModel, Field

from app import runtime
from app.config import get_config
from app.services.audit_service import normalize_actor, write_ai_generation_log
from app.services.llm_runtime import LLMRuntimeUnavailableError
from app.utils.api_llm import call_api_llm
from app.utils.patient_helpers import bed_match, normalize_bed, patient_his_pid_candidates

router = APIRouter()
logger = logging.getLogger("icu-alert")
_AI_CONSULT_LLM_TIMEOUT_SECONDS = 90
_AI_CONSULT_TOTAL_TIMEOUT_SECONDS = 120
_AI_CONSULT_MAX_TOKENS = 3200
_AI_CONSULT_COMPLEX_LLM_TIMEOUT_SECONDS = 120
_AI_CONSULT_COMPLEX_TOTAL_TIMEOUT_SECONDS = 150
_AI_CONSULT_COMPLEX_MAX_TOKENS = 4096
_AI_CONSULT_PREVIEW_TIMEOUT_SECONDS = 6
_AI_CONSULT_PREVIEW_MAX_TOKENS = 180
_AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS = 1.8
_AI_CONSULT_CONTEXT_MAX_CHARS = 4200
_AI_CONSULT_HISTORY_TURNS = 8
_AI_CONSULT_HISTORY_ITEM_MAX_CHARS = 320
_AI_CONSULT_SECTION_ORDER = ("初步判断", "关键证据", "风险点", "不确定性", "建议检查", "下一步处理建议", "安全提示")
_AI_CONSULT_COMPLEX_KEYWORDS = (
    "鉴别诊断",
    "诊断思路",
    "病因分析",
    "复杂病例",
    "多器官",
    "休克",
    "脓毒",
    "感染性休克",
    "乳酸",
    "升压药",
    "去甲肾上腺素",
    "机械通气",
    "呼吸衰竭",
    "CRRT",
    "ECMO",
    "床旁超声",
    "血流动力学",
    "酸中毒",
    "ARDS",
    "神经评估",
    "凝血",
    "出血",
)

_AI_CONSULT_INTENT_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("检查建议", "建议检查", ("检查", "化验", "检验", "影像", "ct", "cta", "mri", "b超", "超声", "血气", "乳酸", "培养", "复查")),
    ("下一步处理", "下一步处理", ("处理", "治疗", "怎么做", "怎么办", "处置", "干预", "用药", "补液", "升压", "呼吸机", "调整", "6小时", "下一步")),
    ("风险识别", "风险点", ("风险", "警惕", "并发症", "恶化", "最危险", "高危", "危重", "预警")),
    ("诊断判断", "初步判断", ("诊断", "判断", "考虑", "病因", "鉴别", "原因", "为什么", "初步判断", "诊断思路")),
    ("病情总结", "初步判断", ("总结", "概括", "梳理", "汇总", "总体", "病情")),
]

_PATIENT_IDENTIFIER_FIELDS = (
    "hisPid",
    "hisPID",
    "hisPatientId",
    "patientId",
    "patientID",
    "mrn",
    "hisMrn",
    "pid",
    "inHosNo",
    "admissionNo",
    "hospitalNo",
    "zyh",
)

_OBS_CODE_LABELS: list[tuple[str, str]] = [
    ("param_HR", "HR"),
    ("param_resp", "RR"),
    ("param_spo2", "SpO2"),
    ("param_nibp_s", "NIBP收缩压"),
    ("param_nibp_d", "NIBP舒张压"),
    ("param_nibp_m", "NIBP-MAP"),
    ("param_ibp_s", "IBP收缩压"),
    ("param_ibp_d", "IBP舒张压"),
    ("param_ibp_m", "IBP-MAP"),
    ("param_T", "体温"),
    ("param_cvp", "CVP"),
    ("param_ETCO2", "EtCO2"),
    ("param_score_gcs_obs", "GCS"),
    ("param_score_rass_obs", "RASS"),
    ("param_tengTong_score", "疼痛评分"),
    ("param_delirium_score", "谵妄评分"),
    ("param_score_braden", "Braden"),
]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=4000)


class ChatConsultPayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list)
    patient_id: str | None = Field(default=None, max_length=64)
    patient_ids: list[str] = Field(default_factory=list, max_length=8)
    mode: Literal["clinical", "free"] = "clinical"
    pending_clarifications: list[str] = Field(default_factory=list, max_length=3)


def _clip_text(value: str | None, limit: int = 1200) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _strip_markdown_for_display(value: str | None) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    text = re.sub(r"<think\b[^>]*>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<think\b[^>]*>[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?think\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;think\b[^&]*&gt;[\s\S]*?&lt;/think&gt;", "", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;think\b[^&]*&gt;[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;/?think\b[^&]*&gt;", "", text, flags=re.IGNORECASE)

    full_fence = re.fullmatch(r"\s*```(?:[\w+-]+)?\s*([\s\S]*?)\s*```\s*", text, flags=re.IGNORECASE)
    if full_fence:
        text = str(full_fence.group(1) or "").strip()

    text = re.sub(
        r"```(?:[\w+-]+)?\s*([\s\S]*?)```",
        lambda match: str(match.group(1) or "").strip(),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(\d+)\.\s+", r"\1、", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+)__", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_ai_consult_sections(text: str) -> dict[str, str]:
    normalized = str(text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return {}
    normalized = re.sub(
        r"(?<!^)(?<!\n)\s*(?=(?:[一二三四1-7]\s*[、.)：:]\s*)?(初步判断|关键证据|风险点|不确定性|建议检查|下一步处理建议|下一步处理|安全提示)\s*[:：])",
        "\n",
        normalized,
        flags=re.IGNORECASE,
    )
    pattern = re.compile(
        r"(?mi)^\s*(?:[一二三四五六七1-7]\s*[、.)：:]\s*)?(初步判断|关键证据|风险点|不确定性|建议检查|下一步处理建议|下一步处理|安全提示)\s*[:：]?\s*"
    )
    matches = list(pattern.finditer(normalized))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        title = str(match.group(1) or "").strip()
        if title == "下一步处理":
            title = "下一步处理建议"
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        content = normalized[start:end].strip(" \n\t:：")
        if content:
            sections[title] = content
    return sections


def _normalize_ai_consult_section_content(content: str) -> str:
    text = str(content or "").replace("\r\n", "\n").strip()
    if not text or _is_placeholder_ai_consult_section_text(text):
        return ""

    rows = [
        row.strip()
        for row in text.split("\n")
        if row.strip() and not _is_placeholder_ai_consult_section_text(row)
    ]
    if not rows:
        return ""
    if len(rows) > 1:
        normalized_rows: list[str] = []
        for idx, row in enumerate(rows, start=1):
            if re.match(r"^\s*(?:\d+[、.)：:]|[一二三四五六七八九十]+[、.)：:])", row):
                normalized_rows.append(row)
            else:
                normalized_rows.append(f"{idx}、{row}")
        return "\n".join(normalized_rows)

    single = rows[0] if rows else text
    if _is_placeholder_ai_consult_section_text(single):
        return ""
    if re.match(r"^\s*(?:\d+[、.)：:]|[一二三四五六七八九十]+[、.)：:])", single):
        return single

    parts = [
        item.strip(" \t。；;")
        for item in re.split(r"[；;]+", single)
        if item.strip(" \t。；;") and not _is_placeholder_ai_consult_section_text(item)
    ]
    if len(parts) <= 1:
        return f"1、{single}"
    return "\n".join(f"{idx}、{part}" for idx, part in enumerate(parts, start=1))


def _is_placeholder_ai_consult_section_text(value: str | None) -> bool:
    text = _strip_markdown_for_display(value).strip()
    if not text:
        return True

    normalized = text.lower()
    normalized = re.sub(r"^\s*(?:\d+|[一二三四五六七八九十]+)\s*[、.)：:]\s*", "", normalized)
    normalized = re.sub(r"[\s\-_—–。；;，,：:、.]+", "", normalized)
    return normalized in {"", "无", "暂无", "未提供", "na", "n/a", "null", "none"}


def _format_rag_citation(item: dict[str, Any], idx: int) -> str:
    source = _safe_text(item.get("source") or item.get("title") or item.get("doc_id") or f"指南{idx}")
    rec = _safe_text(item.get("recommendation") or item.get("section_title"))
    grade = _safe_text(item.get("recommendation_grade"))
    label = source
    if grade:
        label += f" {grade}"
    if rec:
        label += f"：{_clip_text(rec, 80)}"
    return label


def _format_rag_evidence_block(rag_hits: list[dict[str, Any]]) -> str:
    if not rag_hits:
        return "无指南检索命中"
    lines = []
    for idx, item in enumerate(rag_hits[:6], start=1):
        citation = _format_rag_citation(item, idx)
        content = _clip_text(_safe_text(item.get("content")), 260)
        chunk_id = _safe_text(item.get("chunk_id"))
        lines.append(f"[R{idx}] {citation}；chunk={chunk_id}；内容摘录：{content}")
    return "\n".join(lines)


def _append_rag_citations(answer: str, rag_hits: list[dict[str, Any]]) -> str:
    text = _strip_markdown_for_display(answer)
    if not rag_hits:
        return text
    existing = text.lower()
    citations: list[str] = []
    for idx, item in enumerate(rag_hits[:4], start=1):
        citation = _format_rag_citation(item, idx)
        source = _safe_text(item.get("source") or item.get("title") or item.get("doc_id"))
        if source and source.lower() in existing:
            continue
        citations.append(f"{idx}、根据 {citation}")
    if not citations:
        return text
    return f"{text}\n\n引用来源：\n" + "\n".join(citations)


def _finalize_ai_consult_answer(raw: str | None, rag_hits: list[dict[str, Any]] | None = None) -> str:
    text = _strip_markdown_for_display(raw)
    if not text:
        text = "暂时没有生成有效回答，请稍后重试。"

    fallback_sections = {
        "初步判断": "1、当前回答未形成有效初步判断，请结合已加载患者上下文、生命体征、主要诊断、近期预警和检验结果重新评估；若信息不足，应明确补充关键数据后再判断。",
        "关键证据": "1、当前可引用证据不足，请核对生命体征、检验、用药、护理评估和预警触发依据。",
        "风险点": "1、原回答未单列风险点，请结合潜在休克、低氧、出血、感染进展等高危问题重点排查。",
        "不确定性": "1、系统无法替代床旁查体；缺失数据、采样时间和患者基础状态需由临床人员确认。",
        "建议检查": "1、请补充关键化验、影像、生命体征趋势和床旁评估。",
        "下一步处理建议": "1、请按床旁紧急程度优先处理，并根据新增检查结果及时调整。",
        "安全提示": "1、以上内容仅作为临床辅助，不替代医生判断。高风险处置需由责任医生确认。",
    }
    parsed = _extract_ai_consult_sections(text)
    if not parsed:
        initial_text = "" if _is_placeholder_ai_consult_section_text(text) else text
        parsed = {
            "初步判断": initial_text or fallback_sections["初步判断"],
            "关键证据": fallback_sections["关键证据"],
            "风险点": "1、当前原始回答未明确分段，请重点结合生命体征、器官灌注、意识状态和近期治疗反应综合判断。",
            "不确定性": fallback_sections["不确定性"],
            "建议检查": "1、建议补充最关键的生命体征趋势、化验变化、血气/乳酸及床旁评估信息。",
            "下一步处理建议": "1、请优先处理当前最紧急问题，并结合补充信息动态调整方案。",
            "安全提示": fallback_sections["安全提示"],
        }
    else:
        for title, fallback in fallback_sections.items():
            content = str(parsed.get(title) or "").strip()
            if not content or _is_placeholder_ai_consult_section_text(content):
                parsed[title] = fallback

    blocks: list[str] = []
    for title in _AI_CONSULT_SECTION_ORDER:
        content = str(parsed.get(title) or "").strip()
        normalized_content = _normalize_ai_consult_section_content(content)
        if not normalized_content:
            continue
        display_title = "下一步处理" if title == "下一步处理建议" else title
        blocks.append(f"{display_title}：\n{normalized_content}")
    return _append_rag_citations("\n\n".join(blocks).strip(), rag_hits or [])


def _ai_consult_structured_fields(answer: str, rag_hits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sections = _extract_ai_consult_sections(answer)
    def _lines(title: str) -> list[str]:
        return [
            line.strip()
            for line in str(sections.get(title) or "").splitlines()
            if line.strip()
        ]

    evidence = []
    for idx, line in enumerate(_lines("关键证据")[:8], start=1):
        evidence.append({"type": "clinical_context", "name": f"证据{idx}", "value": line, "unit": "", "time": None, "source": "AI回答结构化"})
    for item in (rag_hits or [])[:6]:
        evidence.append(
            {
                "type": "knowledge",
                "name": str(item.get("recommendation") or item.get("source") or "指南证据"),
                "value": str(item.get("content") or "")[:240],
                "unit": "",
                "time": None,
                "source": str(item.get("source") or item.get("doc_id") or "RAG"),
                "chunk_id": item.get("chunk_id"),
            }
        )
    safety = _lines("安全提示") or ["以上内容仅作为临床辅助，不替代医生判断。高风险处置需由责任医生确认。"]
    return {
        "evidence": evidence,
        "uncertainties": _lines("不确定性"),
        "safety_warnings": safety,
    }


def _resolve_ai_consult_limits(
    *,
    message: str,
    history: list[ChatTurn],
    patient_context: str,
) -> tuple[int, int, int]:
    text = _safe_text(message)
    history_turns = len(history or [])
    normalized_text = text.lower()
    complex_hit = any(keyword.lower() in normalized_text for keyword in _AI_CONSULT_COMPLEX_KEYWORDS)
    is_complex = bool(
        patient_context
        or history_turns >= 6
        or len(text) >= 220
        or text.count("\n") >= 4
        or complex_hit
    )
    if is_complex:
        return (
            _AI_CONSULT_COMPLEX_MAX_TOKENS,
            _AI_CONSULT_COMPLEX_LLM_TIMEOUT_SECONDS,
            _AI_CONSULT_COMPLEX_TOTAL_TIMEOUT_SECONDS,
        )
    return (
        _AI_CONSULT_MAX_TOKENS,
        _AI_CONSULT_LLM_TIMEOUT_SECONDS,
        _AI_CONSULT_TOTAL_TIMEOUT_SECONDS,
    )


def _parse_retry_after_seconds(error_text: str) -> float | None:
    token = str(error_text or "").strip()
    if not token:
        return None
    match = re.search(r"retry\s+after\s+(\d+(?:\.\d+)?)s", token, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        value = float(match.group(1))
        return value if value >= 0 else None
    except Exception:
        return None


def _looks_like_clarification_answer(message: str, pending_clarifications: list[str] | None) -> bool:
    pending = [str(item or "").strip() for item in (pending_clarifications or []) if str(item or "").strip()]
    if not pending:
        return False
    text = _safe_text(message)
    if not text:
        return False
    normalized_text = _normalize_clarification_text(text)
    if not normalized_text:
        return False
    for question in pending:
        normalized_question = _normalize_clarification_text(question)
        if not normalized_question:
            continue
        overlap = len(set(normalized_text) & set(normalized_question)) / max(1, min(len(set(normalized_text)), len(set(normalized_question))))
        if overlap >= 0.3:
            return True
        for keyword in _clarification_keywords(question):
            if keyword in normalized_text:
                return True
        if SequenceMatcher(None, normalized_text, normalized_question).ratio() >= 0.3:
            return True
    return False


def _normalize_clarification_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "").lower())


def _clarification_keywords(question: str) -> list[str]:
    stopwords = {"是否", "有没有", "请问", "目前", "当前", "需要", "确认", "这个", "病人", "患者", "哪些", "什么", "如何", "多少"}
    tokens = re.findall(r"[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]{2,}", str(question or "").lower())
    keywords: list[str] = []
    for token in tokens:
        if token in stopwords:
            continue
        if len(token) > 12:
            keywords.extend([token[i : i + 4] for i in range(0, len(token), 4) if len(token[i : i + 4]) >= 2])
        else:
            keywords.append(token)
    return keywords[:10]


def _parse_information_gaps(raw: str) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except Exception:
        return []
    gaps = data.get("gaps") if isinstance(data, dict) else None
    if not isinstance(gaps, list):
        return []
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(gaps[:3], start=1):
        if not isinstance(item, dict):
            continue
        question = _strip_markdown_for_display(str(item.get("question") or item.get("item") or "")).strip()
        if not question:
            continue
        if not question.endswith(("？", "?")):
            question = question.rstrip("。；;，,") + "？"
        rows.append(
            {
                "rank": int(item.get("rank") or idx),
                "question": question,
                "reason": _clip_text(str(item.get("reason") or "该信息可能显著改变建议。"), 220),
                "information_gain": max(0.0, min(1.0, float(item.get("information_gain") or (1.0 - (idx - 1) * 0.2)))),
            }
        )
    return rows


async def propose_information_gaps(patient_context) -> list[dict[str, Any]]:
    context = _clip_text(str(patient_context or ""), 3600)
    if not context or context == "未选择具体患者，本轮按通用 ICU 问答处理。":
        return []
    cfg = get_config()
    system_prompt = (
        "你是 ICU AI Consult 的 AMIE 式主动追问模块。"
        "请评估哪些缺失信息会显著改变临床建议，按信息增益排序。"
        "只返回 JSON，不要输出解释文本。"
        "若现有信息足够直接给建议，返回 {\"gaps\":[]}。"
        "最多返回 3 个问题，问题必须适合医生快速回答。"
        "JSON schema: {\"gaps\":[{\"rank\":1,\"question\":\"\",\"reason\":\"\",\"information_gain\":0.0}]}"
    )
    user_prompt = f"【患者与对话上下文】\n{context}\n\n请找出给最终建议前最值得主动追问的信息缺口。"
    try:
        raw = await asyncio.wait_for(
            call_api_llm(
                system_prompt,
                user_prompt,
                cfg.llm_fast_model or cfg.llm_model_medical or None,
                max_tokens=600,
                timeout_seconds=min(20, _AI_CONSULT_LLM_TIMEOUT_SECONDS),
            ),
            timeout=25,
        )
        return _parse_information_gaps(str(raw or ""))
    except Exception as exc:
        logger.warning("AI consult information gap proposal skipped: %s", exc)
        return []


async def _write_ai_consult_log(
    *,
    request: Request | None,
    payload: ChatConsultPayload,
    answer: Any,
    success: bool,
    model: str = "",
    patient_ids: list[str] | None = None,
    patient_label: str = "",
    match_source: str = "",
    match_note: str = "",
    rag_hits: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    actor = normalize_actor(
        request.headers.get("X-User-Id") if request is not None else "",
        request.headers.get("x-operator-id") if request is not None else "",
        request.headers.get("X-Operator-Id") if request is not None else "",
    )
    ids = [str(item).strip() for item in (patient_ids or []) if str(item).strip()]
    try:
        await write_ai_generation_log(
            runtime.db,
            module="ai_consult",
            action="chat_consult",
            model=model,
            prompt_version="ai_consult_v2_multi_patient_rag_audit",
            actor=actor,
            patient_id=ids[0] if ids else None,
            success=success,
            source_data_summary={
                "message": _clip_text(payload.message, 1200),
                "history_turns": len(payload.history or []),
                "patient_ids": ids,
                "patient_label": patient_label,
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "rag_sources": [
                    {
                        "chunk_id": item.get("chunk_id"),
                        "source": item.get("source"),
                        "recommendation": item.get("recommendation"),
                        "recommendation_grade": item.get("recommendation_grade"),
                        "score": item.get("score"),
                    }
                    for item in (rag_hits or [])[:8]
                ],
            },
            result=answer,
            metadata={
                "patient_ids": ids,
                "rag_chunk_ids": [item.get("chunk_id") for item in (rag_hits or [])[:8] if item.get("chunk_id")],
                **(metadata or {}),
            },
        )
    except Exception as exc:
        logger.warning("AI consult audit log write failed: %s", exc)


def _build_ai_consult_degraded_payload(
    *,
    message: str,
    patient_context_used: bool,
    patient_label: str,
    resolved_patient_id: str | None,
    patient_match_source: str | None,
    patient_match_note: str,
    intent_primary: str | None = None,
    intent_focus_section: str | None = None,
    retry_after_seconds: float | None = None,
) -> dict[str, Any]:
    degraded_answer = _build_ai_consult_degraded_answer(retry_after_seconds)
    return {
        "code": 0,
        "message": message,
        "answer": degraded_answer,
        "degraded": True,
        "retry_after_seconds": retry_after_seconds,
        "patient_context_used": patient_context_used,
        "patient_label": patient_label,
        "resolved_patient_id": resolved_patient_id,
        "patient_match_source": patient_match_source,
        "patient_match_note": patient_match_note,
        "intent_primary": intent_primary,
        "intent_focus_section": intent_focus_section,
        **_ai_consult_structured_fields(degraded_answer, []),
    }


def _build_ai_consult_degraded_response(**kwargs: Any) -> JSONResponse:
    return JSONResponse(status_code=200, content=_build_ai_consult_degraded_payload(**kwargs))


def _build_ai_consult_degraded_answer(retry_after_seconds: float | None = None) -> str:
    retry_hint = ""
    if retry_after_seconds is not None:
        retry_hint = f"，建议约 {max(1, int(round(retry_after_seconds)))} 秒后重试"
    return (
        f"当前 AI 服务处于短时保护模式{retry_hint}。"
        "如病情紧急，请先按床旁评估与既有流程处理。"
        "仅供临床参考，需结合床旁评估。"
    )


def _patient_label(patient: dict) -> str:
    bed = str(patient.get("hisBed") or patient.get("bed") or "—").strip()
    name = str(patient.get("name") or patient.get("hisName") or "未知患者").strip()
    diagnosis = str(patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "暂无诊断").strip()
    return f"{bed}床 · {name} · {diagnosis}"


def _patient_bed(patient: dict[str, Any]) -> str:
    return _safe_text(
        patient.get("hisBed")
        or patient.get("bed")
        or patient.get("bedNo")
        or patient.get("bed_no")
        or patient.get("bedNumber")
        or patient.get("bedName")
        or patient.get("curBed")
    )


def _format_history(history: list[ChatTurn]) -> str:
    rows: list[str] = []
    for item in history[-_AI_CONSULT_HISTORY_TURNS:]:
        content = _clip_text(item.content, _AI_CONSULT_HISTORY_ITEM_MAX_CHARS)
        if not content:
            continue
        speaker = "用户" if item.role == "user" else "助手"
        rows.append(f"{speaker}: {content}")
    return "\n".join(rows) if rows else "无历史对话"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_compare_text(value: str | None) -> str:
    text = _strip_markdown_for_display(value)
    if not text:
        return ""
    text = re.sub(
        r"(?mi)^\s*(?:[一二三四1-4]\s*[、.)：:]\s*)?(初步判断|风险点|建议检查|下一步处理)\s*[:：]?\s*",
        "",
        text,
    )
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。；：:、,.!?！？（）()\[\]【】“”\"'`~\-_/\\|]+", "", text)
    return text[:4000]


def _text_similarity(a: str | None, b: str | None) -> float:
    left = _normalize_compare_text(a)
    right = _normalize_compare_text(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _latest_history_content(history: list[ChatTurn], role: Literal["user", "assistant"]) -> str:
    for item in reversed(history or []):
        if item.role != role:
            continue
        content = _safe_text(item.content)
        if content:
            return content
    return ""


def _should_retry_ai_consult_answer(
    *,
    message: str,
    history: list[ChatTurn],
    answer_text: str,
) -> bool:
    current_question = _safe_text(message)
    previous_question = _latest_history_content(history, "user")
    previous_answer = _latest_history_content(history, "assistant")
    if not current_question or not previous_answer or not answer_text:
        return False
    if len(_normalize_compare_text(answer_text)) < 90:
        return False
    question_similarity = _text_similarity(current_question, previous_question)
    answer_similarity = _text_similarity(answer_text, previous_answer)
    return question_similarity < 0.72 and answer_similarity >= 0.84


def _detect_ai_consult_intent(message: str) -> dict[str, str]:
    text = _safe_text(message).lower()
    primary = "综合评估"
    focus_section = "初步判断 / 风险点 / 建议检查 / 下一步处理"
    matched_keywords: list[str] = []

    for intent_name, section_name, keywords in _AI_CONSULT_INTENT_RULES:
        hits = [keyword for keyword in keywords if keyword.lower() in text]
        if hits:
            primary = intent_name
            focus_section = section_name
            matched_keywords = hits[:4]
            break

    focus_instruction_map = {
        "建议检查": "本轮如果在问进一步检查，请把“建议检查”写得最具体，明确检查项目、目的和优先级，其他部分相对精简。",
        "下一步处理": "本轮如果在问处置/治疗，请把“下一步处理”写成最优先、最可执行的动作清单，其他部分相对精简。",
        "风险点": "本轮如果在问风险，请把“风险点”写成最核心的 3-5 条，并说明为什么危险，其他部分相对精简。",
        "初步判断": "本轮如果在问诊断/判断，请把“初步判断”写得最完整，说明当前最可能方向与依据，其他部分相对精简。",
    }
    preview_focus_map = {
        "建议检查": "首句优先回答最关键还缺什么检查。",
        "下一步处理": "首句优先回答现在最先该做什么处理。",
        "风险点": "首句优先回答当前最危险的风险是什么。",
        "初步判断": "首句优先回答当前最可能的初步判断是什么。",
    }
    return {
        "primary": primary,
        "focus_section": focus_section,
        "matched_keywords": "、".join(matched_keywords) if matched_keywords else "未命中显式关键词",
        "focus_instruction": focus_instruction_map.get(
            focus_section,
            "请根据本轮问题重心作答，不要平均分配篇幅，不要机械重复患者概况。",
        ),
        "preview_instruction": preview_focus_map.get(
            focus_section,
            "首句优先回答本轮问题最核心的临床结论。",
        ),
    }


def _format_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%m-%d %H:%M")
    return _safe_text(value)


def _to_num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", _safe_text(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _extract_patient_mentions(message: str) -> tuple[list[str], list[str], list[str]]:
    text = _safe_text(message)
    if not text:
        return [], []

    identifiers: list[str] = []
    names: list[str] = []
    beds: list[str] = []

    for match in re.finditer(r"(?<!\d)(\d{1,3})\s*(?:床|床位)", text):
        token = _safe_text(match.group(1)).lstrip("0") or "0"
        if token and token not in beds:
            beds.append(token)

    id_patterns = [
        r"(?:住院号|病案号|病历号|患者号|病人号|mrn|hispid|patient[\s_-]*id|患者id)\s*[:：#]?\s*([A-Za-z0-9_-]{3,64})",
    ]
    for pattern in id_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            token = _safe_text(match.group(1))
            if token and token not in identifiers:
                identifiers.append(token)

    name_patterns = [
        r"(?:患者|病人|姓名|叫做|叫|名为)\s*[:：]?\s*([A-Za-z\u4e00-\u9fa5·]{2,20})",
    ]
    stop_words = {"患者", "病人", "医生", "护士", "目前", "今天", "昨天", "今天的", "这个", "那个", "该患者"}
    for pattern in name_patterns:
        for match in re.finditer(pattern, text):
            token = _safe_text(match.group(1)).strip("，,。；;:：")
            if not token or token in stop_words:
                continue
            if token not in names:
                names.append(token)
    return identifiers[:6], names[:4], beds[:8]


def _is_likely_active_status(status: str) -> bool:
    token = _safe_text(status).lower()
    if not token:
        return True
    if token in {"admitted", "在科", "住院", "icu", "icu在科", "in_dept", "active"}:
        return True
    if token in {"discharged", "出科", "出院", "离科", "转出", "dead", "death", "deceased", "invalid", "invaild", "out_dept"}:
        return False
    return True


def _rank_patient_match(patient: dict[str, Any], *, identifiers: list[str], names: list[str], beds: list[str] | None = None) -> int:
    score = 0
    if _is_likely_active_status(_safe_text(patient.get("status"))):
        score += 200
    for field in _PATIENT_IDENTIFIER_FIELDS:
        value = _safe_text(patient.get(field))
        if value and value in identifiers:
            score += 120
    for field in ("name", "hisName"):
        value = _safe_text(patient.get(field))
        if value and value in names:
            score += 80
    bed = normalize_bed(_patient_bed(patient)) or _safe_text(patient.get("hisBed") or patient.get("bed")).lstrip("0")
    if beds and bed in {normalize_bed(item) or item for item in beds}:
        score += 100
    if _patient_bed(patient):
        score += 10
    if _safe_text(patient.get("dept") or patient.get("hisDept")):
        score += 5
    return score


async def _load_patient_by_id(patient_id: str) -> dict[str, Any] | None:
    token = _safe_text(patient_id)
    if not token:
        return None
    try:
        oid = ObjectId(token)
    except Exception:
        return None
    return await runtime.db.col("patient").find_one({"_id": oid})


async def _find_patients_by_identifiers(identifiers: list[str]) -> list[dict[str, Any]]:
    tokens = [item for item in identifiers if _safe_text(item)]
    if not tokens:
        return []
    clauses: list[dict[str, Any]] = []
    for field in _PATIENT_IDENTIFIER_FIELDS:
        clauses.append({field: {"$in": tokens}})
    for token in tokens:
        if ObjectId.is_valid(token):
            clauses.append({"_id": ObjectId(token)})
    cursor = runtime.db.col("patient").find({"$or": clauses}).limit(30)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    async for item in cursor:
        key = _safe_text(item.get("_id"))
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return rows


async def _find_patients_by_names(names: list[str]) -> list[dict[str, Any]]:
    tokens = [item for item in names if _safe_text(item)]
    if not tokens:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in tokens[:4]:
        pattern = re.escape(name)
        query = {
            "$or": [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"hisName": {"$regex": pattern, "$options": "i"}},
            ]
        }
        cursor = runtime.db.col("patient").find(query).limit(20)
        async for item in cursor:
            key = _safe_text(item.get("_id"))
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append(item)
    return rows


async def _find_patients_by_beds(beds: list[str]) -> list[dict[str, Any]]:
    tokens = [item for item in beds if _safe_text(item)]
    if not tokens:
        return []
    normalized_tokens = [normalize_bed(token) or token for token in tokens]
    variants: list[str] = []
    for token in tokens:
        raw = _safe_text(token)
        normalized = normalize_bed(raw) or raw
        for candidate in {raw, normalized, raw.zfill(2), raw.zfill(3), f"{raw}床", f"{raw.zfill(2)}床", f"{normalized}床", f"BED{raw}", f"BED{raw.zfill(2)}"}:
            if candidate and candidate not in variants:
                variants.append(candidate)
    regex_terms = []
    for token in normalized_tokens:
        escaped = re.escape(token)
        regex_terms.append({"hisBed": {"$regex": rf"(^|[^0-9])0*{escaped}([^0-9]|$|床)", "$options": "i"}})
        regex_terms.append({"bed": {"$regex": rf"(^|[^0-9])0*{escaped}([^0-9]|$|床)", "$options": "i"}})
        regex_terms.append({"bedNo": {"$regex": rf"(^|[^0-9])0*{escaped}([^0-9]|$|床)", "$options": "i"}})
        regex_terms.append({"bed_no": {"$regex": rf"(^|[^0-9])0*{escaped}([^0-9]|$|床)", "$options": "i"}})
    query = {
        "$or": [
            {"hisBed": {"$in": variants}},
            {"bed": {"$in": variants}},
            {"bedNo": {"$in": variants}},
            {"bed_no": {"$in": variants}},
            *regex_terms,
        ]
    }
    cursor = runtime.db.col("patient").find(query).limit(80)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    async for item in cursor:
        patient_bed = _patient_bed(item)
        if normalized_tokens and not any(bed_match(patient_bed, token) for token in normalized_tokens):
            continue
        key = _safe_text(item.get("_id"))
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return rows


async def _resolve_patient_from_payload(
    patient_id: str | None,
    patient_ids: list[str] | None,
    message: str,
) -> tuple[list[dict[str, Any]], list[str], str, str]:
    explicit_ids = []
    for item in [patient_id, *(patient_ids or [])]:
        token = _safe_text(item)
        if token and token not in explicit_ids:
            explicit_ids.append(token)

    selected_patients: list[dict[str, Any]] = []
    seen_selected: set[str] = set()
    for token in explicit_ids[:8]:
        patient = await _load_patient_by_id(token)
        if not patient:
            continue
        key = _safe_text(patient.get("_id"))
        if key and key not in seen_selected:
            seen_selected.add(key)
            selected_patients.append(patient)

    identifiers, names, beds = _extract_patient_mentions(message)
    match_note = ""
    if identifiers or names or beds:
        candidates: list[dict[str, Any]] = []
        if identifiers:
            candidates.extend(await _find_patients_by_identifiers(identifiers))
        if names:
            candidates.extend(await _find_patients_by_names(names))
        if beds:
            candidates.extend(await _find_patients_by_beds(beds))
        if candidates:
            deduped: dict[str, dict[str, Any]] = {}
            for row in candidates:
                key = _safe_text(row.get("_id"))
                if key and key not in deduped:
                    deduped[key] = row
            ranked = sorted(
                deduped.values(),
                key=lambda row: _rank_patient_match(row, identifiers=identifiers, names=names, beds=beds),
                reverse=True,
            )
            for chosen in ranked[:8]:
                key = _safe_text(chosen.get("_id"))
                if key and key not in seen_selected:
                    seen_selected.add(key)
                    selected_patients.append(chosen)
            matched_beds = {normalize_bed(_patient_bed(row)) for row in selected_patients if normalize_bed(_patient_bed(row))}
            requested_beds = {normalize_bed(item) or item for item in beds}
            missing_beds = sorted(requested_beds - matched_beds, key=lambda item: int(item) if str(item).isdigit() else str(item))
            note = "已按提及的床号/姓名/住院号匹配患者。"
            if missing_beds:
                note += " 未匹配到床号：" + "、".join(f"{bed}床" for bed in missing_beds) + "。"
            return selected_patients, [_safe_text(row.get("_id")) for row in selected_patients if _safe_text(row.get("_id"))], "message_mention", note
        mention_tokens = []
        if beds:
            mention_tokens.append("床号: " + "、".join(f"{bed}床" for bed in beds))
        if names:
            mention_tokens.append("姓名: " + "、".join(names))
        if identifiers:
            mention_tokens.append("住院号/患者号: " + "、".join(identifiers))
        match_note = "检测到患者线索（" + "；".join(mention_tokens) + "），但未在 patient 表中检索到匹配患者。"

    if explicit_ids and not selected_patients and not (identifiers or names or beds):
        raise ValueError("无效患者ID")
    return selected_patients, [_safe_text(row.get("_id")) for row in selected_patients if _safe_text(row.get("_id"))], "selected_patient_id" if selected_patients else "none", match_note


async def _collect_alert_summary(pid_str: str) -> str:
    if not pid_str:
        return ""
    pid_oid = ObjectId(pid_str) if ObjectId.is_valid(pid_str) else None
    pid_values = [pid_str]
    if pid_oid is not None:
        pid_values.append(pid_oid)
    alert_rows: list[str] = []
    cursor = runtime.db.col("alert_records").find({"patient_id": {"$in": pid_values}}).sort("created_at", -1).limit(6)
    async for row in cursor:
        name = _clip_text(str(row.get("name") or row.get("rule_id") or "预警"), 60)
        severity = _safe_text(row.get("severity") or "warning")
        status = _safe_text(row.get("status") or row.get("disposition") or "active")
        created_at = _format_dt(row.get("created_at"))
        alert_rows.append(f"{name}（{severity}/{status}，{created_at}）")
    return "；".join(alert_rows)


async def _collect_observation_summary(pid_str: str) -> str:
    if not pid_str:
        return ""
    labels = dict(_OBS_CODE_LABELS)
    parts: list[str] = []
    try:
        engine = getattr(runtime, "alert_engine", None)
        snapshot: dict[str, Any] | None = None
        if engine is not None and hasattr(engine, "_get_latest_param_snapshot_by_pid"):
            snapshot = await engine._get_latest_param_snapshot_by_pid(
                pid_str,
                codes=[row[0] for row in _OBS_CODE_LABELS],
                lookback_minutes=720,
            )
        params = snapshot.get("params") if isinstance(snapshot, dict) else {}
        if isinstance(params, dict) and params:
            for code, label in _OBS_CODE_LABELS:
                if code not in params:
                    continue
                raw = params.get(code)
                value = _to_num(raw)
                text = str(round(value, 2)) if value is not None else _safe_text(raw)
                if text:
                    parts.append(f"{label}={text}")
            if parts:
                return "；".join(parts[:14])
    except Exception:
        pass

    try:
        cursor = runtime.db.col("bedside").find(
            {"pid": pid_str, "code": {"$in": [row[0] for row in _OBS_CODE_LABELS]}, "time": {"$gte": datetime.now() - timedelta(hours=24)}},
            {"code": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1, "time": 1},
        ).sort("time", -1).limit(300)
        latest_by_code: dict[str, str] = {}
        async for row in cursor:
            code = _safe_text(row.get("code"))
            if not code or code in latest_by_code:
                continue
            value = None
            for key in ("fVal", "intVal", "value", "strVal"):
                cell = row.get(key)
                if cell is None or _safe_text(cell) == "":
                    continue
                num = _to_num(cell)
                value = str(round(num, 2)) if num is not None else _safe_text(cell)
                break
            if not value:
                continue
            latest_by_code[code] = value
        for code, label in _OBS_CODE_LABELS:
            if code in latest_by_code:
                parts.append(f"{label}={latest_by_code[code]}")
    except Exception:
        return ""
    return "；".join(parts[:14])


async def _collect_io_summary(pid_str: str) -> str:
    engine = getattr(runtime, "alert_engine", None)
    if engine is None or not hasattr(engine, "_collect_intake_events") or not hasattr(engine, "_collect_output_events") or not hasattr(engine, "_sum_window"):
        return ""
    now = datetime.now()
    since = now - timedelta(hours=24)
    try:
        intake_events = await engine._collect_intake_events(pid_str, since)
        output_events = await engine._collect_output_events(pid_str, since)
        intake_24h = float(engine._sum_window(intake_events, 24, now))
        output_24h = float(engine._sum_window(output_events, 24, now))
        net_24h = round(intake_24h - output_24h, 1)
        intake_6h = float(engine._sum_window(intake_events, 6, now))
        output_6h = float(engine._sum_window(output_events, 6, now))
        urine_24h = float(engine._sum_window(output_events, 24, now, category="urine"))
        drainage_24h = float(engine._sum_window(output_events, 24, now, category="drainage"))
        return (
            f"24h 入量{round(intake_24h, 1)}mL，出量{round(output_24h, 1)}mL，净平衡{net_24h}mL；"
            f"6h 入量{round(intake_6h, 1)}mL，出量{round(output_6h, 1)}mL；"
            f"24h尿量{round(urine_24h, 1)}mL，引流{round(drainage_24h, 1)}mL。"
        )
    except Exception:
        return ""


def _format_drug_row(row: dict[str, Any]) -> str:
    name = _safe_text(row.get("drugName") or row.get("orderName") or row.get("drugSpec"))
    if not name:
        return ""
    dose = _safe_text(row.get("dose") or row.get("dosage") or row.get("drugSpec"))
    dose_unit = _safe_text(row.get("doseUnit") or row.get("unit"))
    route = _safe_text(row.get("routeName") or row.get("route") or row.get("exeMethod"))
    freq = _safe_text(row.get("frequency"))
    when = _format_dt(row.get("_event_time") or row.get("executeTime") or row.get("exeTime") or row.get("startTime") or row.get("orderTime"))
    details = []
    if dose:
        details.append(f"{dose}{dose_unit}")
    if route:
        details.append(route)
    if freq:
        details.append(freq)
    suffix = "，".join(details)
    return f"{name}{('（' + suffix + '）') if suffix else ''}@{when}" if when else f"{name}{('（' + suffix + '）') if suffix else ''}"


async def _collect_drug_summary(pid_str: str) -> str:
    rows: list[dict[str, Any]] = []
    engine = getattr(runtime, "alert_engine", None)
    try:
        if engine is not None and hasattr(engine, "_get_recent_drug_docs_window"):
            rows = await engine._get_recent_drug_docs_window(pid_str, hours=24, limit=180)
    except Exception:
        rows = []

    if not rows:
        try:
            cursor = runtime.db.col("drugExe").find(
                {"pid": pid_str},
                {
                    "drugName": 1,
                    "orderName": 1,
                    "drugSpec": 1,
                    "dose": 1,
                    "doseUnit": 1,
                    "route": 1,
                    "routeName": 1,
                    "frequency": 1,
                    "executeTime": 1,
                    "startTime": 1,
                    "orderTime": 1,
                },
            ).sort("executeTime", -1).limit(120)
            async for row in cursor:
                rows.append(row)
        except Exception:
            rows = []

    if not rows:
        return ""
    formatted: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = _format_drug_row(row)
        if not text:
            continue
        key = text.split("@", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        formatted.append(text)
        if len(formatted) >= 10:
            break
    return "；".join(formatted)


async def _collect_order_summary(patient_doc: dict[str, Any]) -> str:
    patient_ids = patient_his_pid_candidates(patient_doc)
    if not patient_ids:
        return ""
    his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
    rows: list[str] = []
    try:
        cursor = runtime.db.dc_col("VI_ICU_ZYYZ").find(
            his_pid_query,
            {"orderName": 1, "spec": 1, "freq": 1, "exeMethod": 1, "status": 1, "orderType": 1, "orderTime": 1},
        ).sort("orderTime", -1).limit(80)
        async for row in cursor:
            name = _safe_text(row.get("orderName"))
            if not name:
                continue
            spec = _safe_text(row.get("spec"))
            freq = _safe_text(row.get("freq"))
            route = _safe_text(row.get("exeMethod"))
            status = _safe_text(row.get("status"))
            order_type = _safe_text(row.get("orderType"))
            when = _format_dt(row.get("orderTime"))
            parts = [item for item in [spec, route, freq, status, order_type] if item]
            details = "，".join(parts[:4])
            text = f"{name}{('（' + details + '）') if details else ''}@{when}" if when else f"{name}{('（' + details + '）') if details else ''}"
            rows.append(text)
            if len(rows) >= 10:
                break
    except Exception:
        return ""
    return "；".join(rows)


async def _collect_nursing_summary(patient_doc: dict[str, Any], pid_str: str) -> tuple[str, str]:
    engine = getattr(runtime, "alert_engine", None)
    if engine is None or not hasattr(engine, "_collect_nursing_context"):
        return "", ""
    try:
        ctx = await engine._collect_nursing_context(patient_doc, pid_str, hours=24)
    except Exception:
        return "", ""
    if not isinstance(ctx, dict):
        return "", ""
    records = ctx.get("records") if isinstance(ctx.get("records"), list) else []
    plans = ctx.get("plans") if isinstance(ctx.get("plans"), dict) else {}
    top_records = []
    for row in records[:4]:
        if not isinstance(row, dict):
            continue
        text = _safe_text(row.get("text"))
        if not text:
            continue
        when = _format_dt(row.get("time"))
        top_records.append(f"{text}@{when}" if when else text)
    plan_line = (
        f"护理计划: 计划{int(plans.get('planned_count') or 0)}条，已执行{int(plans.get('executed_count') or 0)}条，"
        f"待执行{int(plans.get('pending_count') or 0)}条，延迟{int(plans.get('delayed_count') or 0)}条。"
    )
    return "；".join(top_records), plan_line


def _format_lab_item(item: dict[str, Any], key: str) -> str:
    name = _safe_text(item.get("raw_name") or key)
    value = item.get("value")
    unit = _safe_text(item.get("unit"))
    flag = _safe_text(item.get("raw_flag"))
    when = _format_dt(item.get("time"))
    value_text = str(value)
    if isinstance(value, float):
        value_text = str(round(value, 3))
    text = f"{name}={value_text}{unit}"
    if flag:
        text += f"({flag})"
    if when:
        text += f"@{when}"
    return text


async def _await_with_timeout(coro: Any, timeout_seconds: float, fallback: Any):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except Exception:
        return fallback


async def _collect_lab_exam_summary(patient_doc: dict[str, Any]) -> tuple[str, str]:
    patient_ids = patient_his_pid_candidates(patient_doc)
    if not patient_ids:
        return "", ""
    his_pid = patient_ids[0]
    lab_rows: list[str] = []
    exam_rows: list[str] = []

    engine = getattr(runtime, "alert_engine", None)
    if engine is not None and hasattr(engine, "_get_latest_labs_map"):
        try:
            labs_map = await engine._get_latest_labs_map(his_pid, lookback_hours=72)
            if isinstance(labs_map, dict):
                ordered = sorted(
                    [(key, value) for key, value in labs_map.items() if isinstance(value, dict) and value.get("value") is not None],
                    key=lambda row: row[1].get("time") or datetime.min,
                    reverse=True,
                )
                for key, item in ordered[:12]:
                    lab_rows.append(_format_lab_item(item, key))
        except Exception:
            lab_rows = []

    his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
    try:
        exam_docs: list[dict[str, Any]] = []
        for col_name in ("VI_ICU_EXAM", "VI_ICU_EXAM_admitted"):
            cursor = runtime.db.dc_col(col_name).find(
                his_pid_query,
                {"code": 1, "examName": 1, "requestName": 1, "orderName": 1, "authTime": 1, "reportTime": 1},
            ).sort("authTime", -1).limit(20)
            async for row in cursor:
                exam_docs.append(row)
        exam_docs = sorted(exam_docs, key=lambda row: row.get("authTime") or row.get("reportTime") or datetime.min, reverse=True)
        seen_names: set[str] = set()
        for row in exam_docs:
            name = _safe_text(row.get("examName") or row.get("requestName") or row.get("orderName") or row.get("code"))
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            when = _format_dt(row.get("authTime") or row.get("reportTime"))
            exam_rows.append(f"{name}@{when}" if when else name)
            if len(exam_rows) >= 8:
                break
    except Exception:
        exam_rows = []

    return "；".join(lab_rows[:12]), "；".join(exam_rows[:8])


async def _build_patient_context(
    patient_id: str | None,
    patient_ids: list[str] | None,
    message: str,
) -> tuple[str, str, str | None, list[str], str, str]:
    patients, resolved_patient_ids, match_source, match_note = await _resolve_patient_from_payload(patient_id, patient_ids, message)
    if not patients or not resolved_patient_ids:
        return "", "", None, [], match_source, match_note

    async def build_one(patient: dict[str, Any], resolved_patient_id: str, index: int) -> str:
        lines = [
            f"【患者{index}】",
            f"患者标签: {_patient_label(patient)}",
            f"患者ID: {resolved_patient_id}",
            f"性别: {patient.get('gender') or patient.get('sex') or '未知'}",
            f"年龄: {patient.get('age') or patient.get('hisAge') or '未知'}",
            f"住院号: {patient.get('hisPid') or patient.get('hisPID') or patient.get('patientId') or patient.get('mrn') or '未知'}",
            f"科室: {patient.get('dept') or patient.get('deptName') or patient.get('hisDept') or patient.get('ward') or '未知'}",
            f"护理级别: {patient.get('nursingLevel') or '未知'}",
            f"主要诊断: {patient.get('clinicalDiagnosis') or patient.get('admissionDiagnosis') or '暂无诊断'}",
        ]

        obs, io_text, drug_text, order_text, nursing_tuple, lab_exam_tuple, alert_text = await asyncio.gather(
            _await_with_timeout(_collect_observation_summary(resolved_patient_id), _AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS, ""),
            _await_with_timeout(_collect_io_summary(resolved_patient_id), _AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS, ""),
            _await_with_timeout(_collect_drug_summary(resolved_patient_id), _AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS, ""),
            _await_with_timeout(_collect_order_summary(patient), _AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS, ""),
            _await_with_timeout(_collect_nursing_summary(patient, resolved_patient_id), _AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS, ("", "")),
            _await_with_timeout(_collect_lab_exam_summary(patient), _AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS, ("", "")),
            _await_with_timeout(_collect_alert_summary(resolved_patient_id), _AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS, ""),
        )

        if obs:
            lines.append("观察项(近24h/最新): " + _clip_text(obs, 800))
        if io_text:
            lines.append("出入量总结: " + _clip_text(io_text, 600))
        if drug_text:
            lines.append("用药执行(近24h): " + _clip_text(drug_text, 900))
        if order_text:
            lines.append("医嘱摘要: " + _clip_text(order_text, 900))
        nursing_record_text, nursing_plan_text = nursing_tuple
        if nursing_record_text:
            lines.append("护理记录(近24h): " + _clip_text(nursing_record_text, 800))
        if nursing_plan_text:
            lines.append(nursing_plan_text)
        lab_text, exam_text = lab_exam_tuple
        if lab_text:
            lines.append("检验摘要(近72h): " + _clip_text(lab_text, 900))
        if exam_text:
            lines.append("检查摘要(近72h): " + _clip_text(exam_text, 600))
        if alert_text:
            lines.append("最近预警: " + _clip_text(alert_text, 600))
        return "\n".join(lines)

    blocks = await asyncio.gather(*[build_one(patient, resolved_patient_ids[idx], idx + 1) for idx, patient in enumerate(patients[:6])])
    lines = [
        f"多患者上下文: 共加载 {len(blocks)} 位患者。若问题涉及比较，请逐床说明差异、优先级和依据。",
        *blocks,
    ]
    if match_note:
        lines.insert(1, f"患者匹配说明: {match_note}")
    context = "\n\n".join(lines)
    labels = "；".join(_patient_label(patient) for patient in patients[:6])
    return _clip_text(context, _AI_CONSULT_CONTEXT_MAX_CHARS * max(1, min(len(blocks), 2))), labels, resolved_patient_ids[0] if resolved_patient_ids else None, resolved_patient_ids, match_source, match_note


def _legacy_single_patient_context_lines(patient: dict[str, Any], resolved_patient_id: str) -> list[str]:
    return [
        f"患者标签: {_patient_label(patient)}",
        f"患者ID: {resolved_patient_id}",
        f"性别: {patient.get('gender') or patient.get('sex') or '未知'}",
        f"年龄: {patient.get('age') or patient.get('hisAge') or '未知'}",
        f"住院号: {patient.get('hisPid') or patient.get('hisPID') or patient.get('patientId') or patient.get('mrn') or '未知'}",
        f"科室: {patient.get('dept') or patient.get('deptName') or patient.get('hisDept') or patient.get('ward') or '未知'}",
        f"护理级别: {patient.get('nursingLevel') or '未知'}",
        f"主要诊断: {patient.get('clinicalDiagnosis') or patient.get('admissionDiagnosis') or '暂无诊断'}",
    ]


def _search_ai_consult_rag(message: str, patient_context: str) -> list[dict[str, Any]]:
    rag = getattr(runtime, "ai_rag_service", None)
    if rag is None:
        return []
    try:
        query = _clip_text(f"{message}\n{patient_context}", 2400)
        return rag.search(query, top_k=5)
    except Exception as exc:
        logger.warning("AI consult RAG search skipped: %s", exc)
        return []


def _build_ai_consult_prompts(
    *,
    message: str,
    history: list[ChatTurn],
    match_note: str,
    patient_context: str,
    rag_hits: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    intent = _detect_ai_consult_intent(message)
    system_prompt = (
        "你是 ICU AI 问诊助手，面向临床医生/护士提供中文辅助问答。"
        "请基于用户问题、历史对话以及患者上下文，输出简洁、专业、可执行的回答。"
        "若问题中提及具体患者姓名/住院号，优先使用已检索到的 patient 表匹配患者，不要混淆同名患者。"
        "必须严格按以下固定结构输出，并且七个标题都要出现："
        "初步判断："
        "关键证据："
        "风险点："
        "不确定性："
        "建议检查："
        "下一步处理建议："
        "安全提示："
        "其中每一部分都要有具体内容，不能省略标题，不能合并标题。"
        "禁止用“-”、“无”、“暂无”、“N/A”等占位符作为任一栏目内容；信息不足时必须说明缺什么信息和如何补充。"
        "不要编造不存在的生命体征、化验或影像结果；若信息不足必须明确说明。"
        "如使用指南证据，必须在相关句子中写明来源，例如“根据 SSC 2021 指南 1A 推荐...”。"
        "若存在潜在急危重情况，先提示立即线下评估/抢救。"
        "严禁输出 <think>、</think>、思维链、推理过程、内部分析草稿。"
        "只输出纯文本，不要使用任何 markdown 语法（如 #、*、-、```、[链接]()）。"
        "安全提示必须包含“仅作为临床辅助，不替代医生判断。高风险处置需由责任医生确认”。"
        f"本轮问题意图判定为：{intent['primary']}，重点展开栏目：{intent['focus_section']}。"
        f"{intent['focus_instruction']}"
    )
    user_prompt = (
        f"【本轮问题意图】\n意图={intent['primary']}；重点栏目={intent['focus_section']}；关键词={intent['matched_keywords']}\n\n"
        f"【患者匹配信息】\n{match_note or '无额外匹配提示'}\n\n"
        f"【患者上下文】\n{patient_context or '未选择具体患者，本轮按通用 ICU 问答处理。'}\n\n"
        f"【指南证据/RAG】\n{_format_rag_evidence_block(rag_hits or [])}\n\n"
        f"【历史对话】\n{_format_history(history)}\n\n"
        f"【本轮问题】\n{_clip_text(message, 2000)}\n\n"
        f"请直接回答本轮问题，并优先把重点写在“{intent['focus_section']}”。"
    )
    return system_prompt, user_prompt


def _build_ai_free_chat_prompts(
    *,
    message: str,
    history: list[ChatTurn],
    match_note: str,
    patient_context: str,
    rag_hits: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    system_prompt = (
        "你是一个中文 AI 对话助手，可以和医生/护士进行自然对话。"
        "本模式是自由对话模式：不要强制使用“初步判断/风险点/建议检查/下一步处理”等固定标题，"
        "也不要为了满足模板而拆分栏目。"
        "请优先按用户当前问题的语气和要求回答；可以简短、可以展开，也可以用自然段或普通列表。"
        "如果用户询问临床问题，仍需保持专业、谨慎，不编造不存在的患者信息；高风险医疗处置要提醒由责任医生确认。"
        "严禁输出 <think>、</think>、思维链、推理过程、内部分析草稿。"
    )
    user_prompt = (
        f"【患者匹配信息】\n{match_note or '无额外匹配提示'}\n\n"
        f"【患者上下文】\n{patient_context or '未选择具体患者；如果问题不需要患者信息，可按通用对话处理。'}\n\n"
        f"【可参考证据/RAG】\n{_format_rag_evidence_block(rag_hits or [])}\n\n"
        f"【历史对话】\n{_format_history(history)}\n\n"
        f"【用户当前问题】\n{_clip_text(message, 2000)}\n\n"
        "请按自由对话方式直接回答，不要套用固定问诊模板。"
    )
    return system_prompt, user_prompt


def _build_ai_consult_preview_prompts(
    *,
    message: str,
    history: list[ChatTurn],
    match_note: str,
    patient_context: str,
    rag_hits: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    intent = _detect_ai_consult_intent(message)
    system_prompt = (
        "你是 ICU AI 问诊助手。"
        "请先给出“首屏预览”回答：仅 1-2 句中文，聚焦初步判断与第一优先风险，必须可执行。"
        "严禁输出 <think>、</think>、思维链或内部推理。"
        "不要使用 markdown，不要列表，不要展开细节，不要超过 90 字。"
        "若信息不足，明确指出最关键缺失信息。"
        f"{intent['preview_instruction']}"
    )
    user_prompt = (
        f"【本轮问题意图】意图={intent['primary']}；重点栏目={intent['focus_section']}；关键词={intent['matched_keywords']}\n"
        f"【患者匹配信息】{_clip_text(match_note or '无额外匹配提示', 200)}\n"
        f"【患者上下文】{_clip_text(patient_context or '未选择具体患者，本轮按通用 ICU 问答处理。', 900)}\n"
        f"【指南证据/RAG】{_clip_text(_format_rag_evidence_block(rag_hits or []), 500)}\n"
        f"【历史对话】{_clip_text(_format_history(history), 450)}\n"
        f"【本轮问题】{_clip_text(message, 800)}\n"
        "请输出首屏预览。"
    )
    return system_prompt, user_prompt


def _build_ai_consult_retry_prompts(
    *,
    message: str,
    history: list[ChatTurn],
    match_note: str,
    patient_context: str,
    rag_hits: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    intent = _detect_ai_consult_intent(message)
    previous_question = _latest_history_content(history, "user")
    previous_answer = _latest_history_content(history, "assistant")
    system_prompt = (
        "你是 ICU AI 问诊助手。"
        "上一轮回答与当前问题过于相似，需要你重新作答。"
        "这一次必须优先响应【本轮问题】本身，不要只重复患者概况、固定模板或上一轮原话。"
        "若当前问题与上一轮关注点不同，就必须体现新的分析角度。"
        "仍然必须严格按以下固定结构输出，并且七个标题都要出现："
        "初步判断："
        "关键证据："
        "风险点："
        "不确定性："
        "建议检查："
        "下一步处理建议："
        "安全提示："
        "每个部分都要有具体内容。"
        "禁止用“-”、“无”、“暂无”、“N/A”等占位符作为任一栏目内容；信息不足时必须说明缺什么信息和如何补充。"
        "如使用指南证据，必须在相关句子中写明来源，例如“根据 SSC 2021 指南 1A 推荐...”。"
        "严禁输出 <think>、</think>、思维链、内部推理。"
        "只输出纯文本，不要使用 markdown。"
        f"本轮问题意图判定为：{intent['primary']}，重点展开栏目：{intent['focus_section']}。"
        f"{intent['focus_instruction']}"
    )
    user_prompt = (
        f"【本轮问题意图】\n意图={intent['primary']}；重点栏目={intent['focus_section']}；关键词={intent['matched_keywords']}\n\n"
        f"【患者匹配信息】\n{match_note or '无额外匹配提示'}\n\n"
        f"【患者上下文】\n{patient_context or '未选择具体患者，本轮按通用 ICU 问答处理。'}\n\n"
        f"【指南证据/RAG】\n{_format_rag_evidence_block(rag_hits or [])}\n\n"
        f"【上一轮用户问题】\n{_clip_text(previous_question or '无', 1200)}\n\n"
        f"【上一轮助手回答】\n{_clip_text(previous_answer or '无', 1800)}\n\n"
        f"【本轮问题】\n{_clip_text(message, 2000)}\n\n"
        "请重新回答本轮问题；如果本轮在问检查，就把建议检查写具体；如果本轮在问处理，就把下一步处理写具体；"
        "不要复述上一轮相同内容。"
    )
    return system_prompt, user_prompt


def _sse_pack(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_llm_stream_delta(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    delta = first.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    block_type = _safe_text(item.get("type") or item.get("content_type") or item.get("kind")).lower()
                    if "reason" in block_type or "think" in block_type:
                        continue
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            if chunks:
                return "".join(chunks)
    text = first.get("text")
    if isinstance(text, str):
        return text
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


async def _iter_llm_stream(
    *,
    cfg: Any,
    system_prompt: str,
    user_prompt: str,
    model: str | None,
    max_tokens: int,
    timeout_seconds: int,
):
    llm_url = cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": model or cfg.llm_fast_model,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.settings.LLM_API_KEY}",
    }

    timeout = httpx.Timeout(timeout_seconds, read=timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", llm_url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                token = str(line or "").strip()
                if not token or token.startswith(":"):
                    continue
                if not token.lower().startswith("data:"):
                    continue
                data_text = token[5:].strip()
                if not data_text:
                    continue
                if data_text == "[DONE]":
                    break
                try:
                    chunk_payload = json.loads(data_text)
                except Exception:
                    continue
                delta = _extract_llm_stream_delta(chunk_payload if isinstance(chunk_payload, dict) else {})
                if delta:
                    yield delta


@router.post("/api/ai/chat-consult")
async def ai_chat_consult(payload: ChatConsultPayload, request: Request):
    message = str(payload.message or "").strip()
    if not message:
        return {"code": 400, "message": "message不能为空"}
    is_free_mode = payload.mode == "free"
    intent = _detect_ai_consult_intent(message)

    patient_id = str(payload.patient_id or "").strip() or None
    resolved_patient_ids: list[str] = []
    rag_hits: list[dict[str, Any]] = []
    patient_context = ""
    patient_label = ""
    resolved_patient_id: str | None = None
    match_source = "none"
    match_note = ""
    model_name = ""
    try:
        patient_context, patient_label, resolved_patient_id, resolved_patient_ids, match_source, match_note = await _build_patient_context(patient_id, payload.patient_ids, message)
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}

    pending_questions = [str(item or "").strip() for item in (payload.pending_clarifications or []) if str(item or "").strip()]
    clarification_answered = _looks_like_clarification_answer(message, pending_questions)
    rag_hits = _search_ai_consult_rag(message, patient_context)
    if not is_free_mode and patient_context and not clarification_answered:
        gaps = await propose_information_gaps(
            "\n\n".join([
                f"【本轮问题】{message}",
                f"【患者上下文】{patient_context}",
                f"【历史对话】{_format_history(payload.history)}",
            ])
        )
        if gaps:
            questions = [item["question"] for item in gaps[:3] if item.get("question")]
            answer_text = "为了避免建议偏差，我需要先确认：\n" + "\n".join(f"{idx}、{question}" for idx, question in enumerate(questions, start=1))
            response = {
                "code": 0,
                "answer": answer_text,
                "message_type": "clarification",
                "pending_clarifications": questions,
                "information_gaps": gaps,
                "patient_context_used": bool(patient_context),
                "patient_label": patient_label,
                "resolved_patient_id": resolved_patient_id,
                "resolved_patient_ids": resolved_patient_ids,
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "intent_primary": intent["primary"],
                "intent_focus_section": intent["focus_section"],
                "mode": payload.mode,
                "rag_sources": [
                    {"chunk_id": item.get("chunk_id"), "source": item.get("source"), "recommendation": item.get("recommendation"), "recommendation_grade": item.get("recommendation_grade")}
                    for item in rag_hits[:6]
                ],
            }
            await _write_ai_consult_log(request=request, payload=payload, answer=response, success=True, model="", patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"message_type": "clarification"})
            return response

    prompt_builder = _build_ai_free_chat_prompts if is_free_mode else _build_ai_consult_prompts
    system_prompt, user_prompt = prompt_builder(
        message=message,
        history=payload.history,
        match_note=match_note,
        patient_context=patient_context,
        rag_hits=rag_hits,
    )
    max_tokens, llm_timeout_seconds, total_timeout_seconds = _resolve_ai_consult_limits(
        message=message,
        history=payload.history,
        patient_context=patient_context,
    )

    try:
        cfg = get_config()
        model_name = cfg.llm_fast_model or cfg.llm_model_medical or ""
        answer = await asyncio.wait_for(
            call_api_llm(
                system_prompt,
                user_prompt,
                model_name or None,
                max_tokens=max_tokens,
                timeout_seconds=llm_timeout_seconds,
            ),
            timeout=total_timeout_seconds,
        )
        answer_text = _strip_markdown_for_display(str(answer or "").strip()) if is_free_mode else _finalize_ai_consult_answer(str(answer or "").strip(), rag_hits)
        if not is_free_mode and _should_retry_ai_consult_answer(message=message, history=payload.history, answer_text=answer_text):
            retry_system_prompt, retry_user_prompt = _build_ai_consult_retry_prompts(
                message=message,
                history=payload.history,
                match_note=match_note,
                patient_context=patient_context,
                rag_hits=rag_hits,
            )
            retry_answer = await asyncio.wait_for(
                call_api_llm(
                    retry_system_prompt,
                    retry_user_prompt,
                    model_name or None,
                    max_tokens=max_tokens,
                    timeout_seconds=llm_timeout_seconds,
                ),
                timeout=total_timeout_seconds,
            )
            retry_text = _finalize_ai_consult_answer(str(retry_answer or "").strip(), rag_hits)
            if retry_text:
                answer_text = retry_text
        response = {
            "code": 0,
            "answer": answer_text,
            "patient_context_used": bool(patient_context),
            "patient_label": patient_label,
            "resolved_patient_id": resolved_patient_id,
            "resolved_patient_ids": resolved_patient_ids,
            "patient_match_source": match_source,
            "patient_match_note": match_note,
            "answer_max_tokens": max_tokens,
            "intent_primary": intent["primary"],
            "intent_focus_section": intent["focus_section"],
            "mode": payload.mode,
            "rag_sources": [
                {"chunk_id": item.get("chunk_id"), "source": item.get("source"), "recommendation": item.get("recommendation"), "recommendation_grade": item.get("recommendation_grade")}
                for item in rag_hits[:6]
            ],
            **({} if is_free_mode else _ai_consult_structured_fields(answer_text, rag_hits)),
        }
        await _write_ai_consult_log(request=request, payload=payload, answer=response, success=True, model=model_name, patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits)
        return response
    except LLMRuntimeUnavailableError as exc:
        retry_after_seconds = _parse_retry_after_seconds(str(exc))
        logger.warning("AI consult chat degraded due to LLM runtime unavailable: %s", exc)
        response = _build_ai_consult_degraded_payload(
            message="AI服务暂时繁忙，已降级为提示模式",
            retry_after_seconds=retry_after_seconds,
            patient_context_used=bool(patient_context),
            patient_label=patient_label,
            resolved_patient_id=resolved_patient_id,
            patient_match_source=match_source,
            patient_match_note=match_note,
            intent_primary=intent["primary"],
            intent_focus_section=intent["focus_section"],
        )
        response["resolved_patient_ids"] = resolved_patient_ids
        await _write_ai_consult_log(request=request, payload=payload, answer=response, success=True, model=model_name, patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"degraded": True})
        return JSONResponse(status_code=200, content=response)
    except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
        logger.warning("AI consult chat timeout, degraded: %s", exc)
        response = _build_ai_consult_degraded_payload(
            message="AI服务响应超时，已降级为提示模式",
            retry_after_seconds=10,
            patient_context_used=bool(patient_context),
            patient_label=patient_label,
            resolved_patient_id=resolved_patient_id,
            patient_match_source=match_source,
            patient_match_note=match_note,
            intent_primary=intent["primary"],
            intent_focus_section=intent["focus_section"],
        )
        response["resolved_patient_ids"] = resolved_patient_ids
        await _write_ai_consult_log(request=request, payload=payload, answer=response, success=True, model=model_name, patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"degraded": True, "timeout": True})
        return JSONResponse(status_code=200, content=response)
    except Exception as exc:
        logger.exception("AI consult chat error")
        response = {
            "code": 500,
            "message": "AI服务异常",
            "answer": "",
            "error": f"AI服务异常: {str(exc)[:120]}",
            "intent_primary": intent["primary"],
            "intent_focus_section": intent["focus_section"],
        }
        await _write_ai_consult_log(request=request, payload=payload, answer=response, success=False, model=model_name, patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"error": str(exc)[:300]})
        return response


@router.post("/api/ai/chat-consult/stream")
async def ai_chat_consult_stream(payload: ChatConsultPayload, request: Request):
    message = str(payload.message or "").strip()
    if not message:
        return JSONResponse(status_code=400, content={"code": 400, "message": "message不能为空"})
    is_free_mode = payload.mode == "free"
    intent = _detect_ai_consult_intent(message)

    patient_id = str(payload.patient_id or "").strip() or None
    try:
        patient_context, patient_label, resolved_patient_id, resolved_patient_ids, match_source, match_note = await _build_patient_context(patient_id, payload.patient_ids, message)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": 400, "message": str(exc)})

    pending_questions = [str(item or "").strip() for item in (payload.pending_clarifications or []) if str(item or "").strip()]
    clarification_answered = _looks_like_clarification_answer(message, pending_questions)
    rag_hits = _search_ai_consult_rag(message, patient_context)
    if not is_free_mode and patient_context and not clarification_answered:
        gaps = await propose_information_gaps(
            "\n\n".join([
                f"【本轮问题】{message}",
                f"【患者上下文】{patient_context}",
                f"【历史对话】{_format_history(payload.history)}",
            ])
        )
        if gaps:
            questions = [item["question"] for item in gaps[:3] if item.get("question")]
            answer_text = "为了避免建议偏差，我需要先确认：\n" + "\n".join(f"{idx}、{question}" for idx, question in enumerate(questions, start=1))
            async def _clarification_stream():
                response = {
                    "code": 0,
                    "answer": answer_text,
                    "message_type": "clarification",
                    "pending_clarifications": questions,
                    "information_gaps": gaps,
                    "patient_context_used": bool(patient_context),
                    "patient_label": patient_label,
                    "resolved_patient_id": resolved_patient_id,
                    "resolved_patient_ids": resolved_patient_ids,
                    "patient_match_source": match_source,
                    "patient_match_note": match_note,
                    "intent_primary": intent["primary"],
                    "intent_focus_section": intent["focus_section"],
                    "mode": payload.mode,
                    "rag_sources": [
                        {"chunk_id": item.get("chunk_id"), "source": item.get("source"), "recommendation": item.get("recommendation"), "recommendation_grade": item.get("recommendation_grade")}
                        for item in rag_hits[:6]
                    ],
                }
                yield _sse_pack("delta", {"text": answer_text})
                await _write_ai_consult_log(request=request, payload=payload, answer=response, success=True, model="", patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"stream": True, "message_type": "clarification"})
                yield _sse_pack("done", response)

            return StreamingResponse(
                _clarification_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
            )

    prompt_builder = _build_ai_free_chat_prompts if is_free_mode else _build_ai_consult_prompts
    system_prompt, user_prompt = prompt_builder(
        message=message,
        history=payload.history,
        match_note=match_note,
        patient_context=patient_context,
        rag_hits=rag_hits,
    )
    max_tokens, llm_timeout_seconds, total_timeout_seconds = _resolve_ai_consult_limits(
        message=message,
        history=payload.history,
        patient_context=patient_context,
    )
    preview_system_prompt, preview_user_prompt = _build_ai_consult_preview_prompts(
        message=message,
        history=payload.history,
        match_note=match_note,
        patient_context=patient_context,
        rag_hits=rag_hits,
    )

    async def _event_stream():
        cfg = get_config()
        model_name = cfg.llm_fast_model or cfg.llm_model_medical or None
        yield _sse_pack(
            "meta",
            {
                "code": 0,
                "patient_context_used": bool(patient_context),
                "patient_label": patient_label,
                "resolved_patient_id": resolved_patient_id,
                "resolved_patient_ids": resolved_patient_ids,
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "model": model_name or "",
                "answer_max_tokens": max_tokens,
                "intent_primary": intent["primary"],
                "intent_focus_section": intent["focus_section"],
                "mode": payload.mode,
                "rag_sources": [
                    {"chunk_id": item.get("chunk_id"), "source": item.get("source"), "recommendation": item.get("recommendation"), "recommendation_grade": item.get("recommendation_grade")}
                    for item in rag_hits[:6]
                ],
            },
        )

        raw_answer_chunks: list[str] = []
        visible_answer_text = ""
        stream_used = False
        preview_emitted = False
        first_delta_received = False
        preview_task: asyncio.Task | None = None if is_free_mode else asyncio.create_task(
            call_api_llm(
                preview_system_prompt,
                preview_user_prompt,
                model_name,
                max_tokens=_AI_CONSULT_PREVIEW_MAX_TOKENS,
                timeout_seconds=_AI_CONSULT_PREVIEW_TIMEOUT_SECONDS,
            )
        )

        try:
            stream_iter = _iter_llm_stream(
                cfg=cfg,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model_name,
                max_tokens=max_tokens,
                timeout_seconds=total_timeout_seconds,
            )
            next_delta_task: asyncio.Task = asyncio.create_task(anext(stream_iter))

            while True:
                wait_targets = {next_delta_task}
                if preview_task and not preview_emitted and not first_delta_received:
                    wait_targets.add(preview_task)
                done, _ = await asyncio.wait(wait_targets, return_when=asyncio.FIRST_COMPLETED)

                if preview_task and preview_task in done and not preview_emitted and not first_delta_received:
                    preview_text = ""
                    try:
                        preview_text = _strip_markdown_for_display(str(preview_task.result() or "").strip())
                    except Exception:
                        preview_text = ""
                    if preview_text:
                        preview_emitted = True
                        yield _sse_pack("preview", {"text": preview_text})

                if next_delta_task in done:
                    try:
                        delta = next_delta_task.result()
                    except StopAsyncIteration:
                        break
                    stream_used = True
                    first_delta_received = True
                    if preview_task and not preview_task.done():
                        preview_task.cancel()
                    raw_answer_chunks.append(delta)
                    if is_free_mode:
                        # 自由对话不要求固定栏目。这里不要在“半截 Markdown”上做全量
                        # strip + prefix diff：例如模型先吐出 "**标题"、随后补齐 "**" 时，
                        # 清洗后的全文会改写已发送前缀，导致 delta 计算失败，最终只保留
                        # 早期可见文本（表现为回答在列表开头处被截断）。自由对话直接把
                        # 原始增量交给前端累计清洗，最终 done 再基于完整 raw chunks 清洗。
                        visible_answer_text += delta
                        yield _sse_pack("delta", {"text": delta})
                        next_delta_task = asyncio.create_task(anext(stream_iter))
                        continue
                    new_visible_text = _strip_markdown_for_display("".join(raw_answer_chunks).strip())
                    if new_visible_text:
                        if new_visible_text.startswith(visible_answer_text):
                            delta_text = new_visible_text[len(visible_answer_text):]
                        else:
                            delta_text = ""
                        if delta_text or not visible_answer_text:
                            visible_answer_text = new_visible_text
                        if delta_text:
                            yield _sse_pack("delta", {"text": delta_text})
                    next_delta_task = asyncio.create_task(anext(stream_iter))
        except Exception as stream_exc:
            logger.warning("AI consult stream failed, fallback to non-stream: %s", stream_exc)
        finally:
            if preview_task and not preview_task.done():
                preview_task.cancel()

        try:
            if not "".join(raw_answer_chunks).strip():
                fallback_answer = await asyncio.wait_for(
                    call_api_llm(
                        system_prompt,
                        user_prompt,
                        model_name,
                        max_tokens=max_tokens,
                        timeout_seconds=llm_timeout_seconds,
                    ),
                    timeout=total_timeout_seconds,
                )
                fallback_text = str(fallback_answer or "").strip()
                if fallback_text:
                    raw_answer_chunks.append(fallback_text)
                    if is_free_mode:
                        visible_answer_text += fallback_text
                        yield _sse_pack("delta", {"text": fallback_text})
                        fallback_text = ""
                    new_visible_text = _strip_markdown_for_display("".join(raw_answer_chunks).strip())
                    if new_visible_text:
                        if new_visible_text.startswith(visible_answer_text):
                            delta_text = new_visible_text[len(visible_answer_text):]
                        else:
                            delta_text = ""
                        if delta_text or not visible_answer_text:
                            visible_answer_text = new_visible_text
                        if delta_text:
                            yield _sse_pack("delta", {"text": delta_text})
        except LLMRuntimeUnavailableError as exc:
            retry_after_seconds = _parse_retry_after_seconds(str(exc))
            degraded_payload = {
                "code": 0,
                "degraded": True,
                "message": "AI服务暂时繁忙，已降级为提示模式",
                "answer": _build_ai_consult_degraded_answer(retry_after_seconds),
                "retry_after_seconds": retry_after_seconds,
                "patient_context_used": bool(patient_context),
                "patient_label": patient_label,
                "resolved_patient_id": resolved_patient_id,
                "resolved_patient_ids": resolved_patient_ids,
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "stream_used": stream_used,
                "intent_primary": intent["primary"],
                "intent_focus_section": intent["focus_section"],
            }
            await _write_ai_consult_log(request=request, payload=payload, answer=degraded_payload, success=True, model=model_name or "", patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"stream": True, "degraded": True})
            yield _sse_pack("done", degraded_payload)
            return
        except (asyncio.TimeoutError, httpx.TimeoutException):
            timeout_payload = {
                "code": 0,
                "degraded": True,
                "message": "AI服务响应超时，已降级为提示模式",
                "answer": _build_ai_consult_degraded_answer(10),
                "retry_after_seconds": 10,
                "patient_context_used": bool(patient_context),
                "patient_label": patient_label,
                "resolved_patient_id": resolved_patient_id,
                "resolved_patient_ids": resolved_patient_ids,
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "stream_used": stream_used,
                "intent_primary": intent["primary"],
                "intent_focus_section": intent["focus_section"],
            }
            await _write_ai_consult_log(request=request, payload=payload, answer=timeout_payload, success=True, model=model_name or "", patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"stream": True, "degraded": True, "timeout": True})
            yield _sse_pack("done", timeout_payload)
            return
        except Exception as exc:
            logger.exception("AI consult stream fallback failed")
            error_payload = {
                "code": 500,
                "message": "AI服务异常",
                "error": f"AI服务异常: {str(exc)[:120]}",
            }
            await _write_ai_consult_log(request=request, payload=payload, answer=error_payload, success=False, model=model_name or "", patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"stream": True, "error": str(exc)[:300]})
            yield _sse_pack("error", error_payload)
            return

        answer_text = (
            _strip_markdown_for_display("".join(raw_answer_chunks).strip() or visible_answer_text)
            if is_free_mode
            else _finalize_ai_consult_answer(visible_answer_text or "".join(raw_answer_chunks).strip(), rag_hits)
        )
        if not is_free_mode and _should_retry_ai_consult_answer(message=message, history=payload.history, answer_text=answer_text):
            try:
                retry_system_prompt, retry_user_prompt = _build_ai_consult_retry_prompts(
                    message=message,
                    history=payload.history,
                    match_note=match_note,
                    patient_context=patient_context,
                    rag_hits=rag_hits,
                )
                retry_answer = await asyncio.wait_for(
                    call_api_llm(
                        retry_system_prompt,
                        retry_user_prompt,
                        model_name,
                        max_tokens=max_tokens,
                        timeout_seconds=llm_timeout_seconds,
                    ),
                    timeout=total_timeout_seconds,
                )
                retry_text = _finalize_ai_consult_answer(str(retry_answer or "").strip(), rag_hits)
                if retry_text:
                    answer_text = retry_text
            except Exception as retry_exc:
                logger.warning("AI consult stream duplicate-answer retry skipped: %s", retry_exc)
        done_payload = {
                "code": 0,
                "answer": answer_text,
                "patient_context_used": bool(patient_context),
                "patient_label": patient_label,
                "resolved_patient_id": resolved_patient_id,
                "resolved_patient_ids": resolved_patient_ids,
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "stream_used": stream_used,
                "answer_max_tokens": max_tokens,
                "intent_primary": intent["primary"],
                "intent_focus_section": intent["focus_section"],
                "mode": payload.mode,
                "rag_sources": [
                    {"chunk_id": item.get("chunk_id"), "source": item.get("source"), "recommendation": item.get("recommendation"), "recommendation_grade": item.get("recommendation_grade")}
                    for item in rag_hits[:6]
                ],
                **({} if is_free_mode else _ai_consult_structured_fields(answer_text, rag_hits)),
            }
        await _write_ai_consult_log(request=request, payload=payload, answer=done_payload, success=True, model=model_name or "", patient_ids=resolved_patient_ids, patient_label=patient_label, match_source=match_source, match_note=match_note, rag_hits=rag_hits, metadata={"stream": True, "stream_used": stream_used})
        yield _sse_pack("done", done_payload)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
