from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from pydantic import BaseModel, Field

from app import runtime
from app.config import get_config
from app.services.llm_runtime import LLMRuntimeUnavailableError
from app.utils.api_llm import call_api_llm
from app.utils.patient_helpers import patient_his_pid_candidates

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
_AI_CONSULT_SECTION_ORDER = ("初步判断", "风险点", "建议检查", "下一步处理")
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
        r"(?<!^)(?<!\n)\s*(?=(?:[一二三四1-4]\s*[、.)：:]\s*)?(初步判断|风险点|建议检查|下一步处理)\s*[:：])",
        "\n",
        normalized,
        flags=re.IGNORECASE,
    )
    pattern = re.compile(
        r"(?mi)^\s*(?:[一二三四1-4]\s*[、.)：:]\s*)?(初步判断|风险点|建议检查|下一步处理)\s*[:：]?\s*"
    )
    matches = list(pattern.finditer(normalized))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        title = str(match.group(1) or "").strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        content = normalized[start:end].strip(" \n\t:：")
        if content:
            sections[title] = content
    return sections


def _normalize_ai_consult_section_content(content: str) -> str:
    text = str(content or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    rows = [row.strip() for row in text.split("\n") if row.strip()]
    if len(rows) > 1:
        normalized_rows: list[str] = []
        for idx, row in enumerate(rows, start=1):
            if re.match(r"^\s*(?:\d+[、.)：:]|[一二三四五六七八九十]+[、.)：:])", row):
                normalized_rows.append(row)
            else:
                normalized_rows.append(f"{idx}、{row}")
        return "\n".join(normalized_rows)

    single = rows[0] if rows else text
    if re.match(r"^\s*(?:\d+[、.)：:]|[一二三四五六七八九十]+[、.)：:])", single):
        return single

    parts = [item.strip(" \t。；;") for item in re.split(r"[；;]+", single) if item.strip(" \t。；;")]
    if len(parts) <= 1:
        return f"1、{single}"
    return "\n".join(f"{idx}、{part}" for idx, part in enumerate(parts, start=1))


def _finalize_ai_consult_answer(raw: str | None) -> str:
    text = _strip_markdown_for_display(raw)
    if not text:
        text = "暂时没有生成有效回答，请稍后重试。"

    parsed = _extract_ai_consult_sections(text)
    if not parsed:
        parsed = {
            "初步判断": text,
            "风险点": "1、当前原始回答未明确分段，请重点结合生命体征、器官灌注、意识状态和近期治疗反应综合判断。",
            "建议检查": "1、建议补充最关键的生命体征趋势、化验变化、血气/乳酸及床旁评估信息。",
            "下一步处理": "1、请优先处理当前最紧急问题，并结合补充信息动态调整方案。仅供临床参考，需结合床旁评估。",
        }
    else:
        if "初步判断" not in parsed:
            parsed["初步判断"] = text
        if "风险点" not in parsed:
            parsed["风险点"] = "1、原回答未单列风险点，请结合潜在休克、低氧、出血、感染进展等高危问题重点排查。"
        if "建议检查" not in parsed:
            parsed["建议检查"] = "1、请补充关键化验、影像、生命体征趋势和床旁评估。"
        if "下一步处理" not in parsed:
            parsed["下一步处理"] = "1、请按床旁紧急程度优先处理，并根据新增检查结果及时调整。仅供临床参考，需结合床旁评估。"

    blocks: list[str] = []
    for title in _AI_CONSULT_SECTION_ORDER:
        content = str(parsed.get(title) or "").strip()
        if not content:
            continue
        blocks.append(f"{title}：\n{_normalize_ai_consult_section_content(content)}")
    return "\n\n".join(blocks).strip()


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


def _build_ai_consult_degraded_response(
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
) -> JSONResponse:
    degraded_answer = _build_ai_consult_degraded_answer(retry_after_seconds)
    return JSONResponse(
        status_code=200,
        content={
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
        },
    )


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


def _extract_patient_mentions(message: str) -> tuple[list[str], list[str]]:
    text = _safe_text(message)
    if not text:
        return [], []

    identifiers: list[str] = []
    names: list[str] = []

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
    return identifiers[:6], names[:4]


def _is_likely_active_status(status: str) -> bool:
    token = _safe_text(status).lower()
    if not token:
        return True
    if token in {"admitted", "在科", "住院", "icu", "icu在科", "in_dept", "active"}:
        return True
    if token in {"discharged", "出科", "出院", "离科", "转出", "dead", "death", "deceased", "invalid", "invaild", "out_dept"}:
        return False
    return True


def _rank_patient_match(patient: dict[str, Any], *, identifiers: list[str], names: list[str]) -> int:
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
    if _safe_text(patient.get("hisBed") or patient.get("bed")):
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


async def _resolve_patient_from_payload(
    patient_id: str | None,
    message: str,
) -> tuple[dict[str, Any] | None, str | None, str, str]:
    identifiers, names = _extract_patient_mentions(message)
    match_note = ""
    if identifiers or names:
        candidates: list[dict[str, Any]] = []
        if identifiers:
            candidates.extend(await _find_patients_by_identifiers(identifiers))
        if not candidates and names:
            candidates.extend(await _find_patients_by_names(names))
        if candidates:
            ranked = sorted(
                candidates,
                key=lambda row: _rank_patient_match(row, identifiers=identifiers, names=names),
                reverse=True,
            )
            chosen = ranked[0]
            return chosen, _safe_text(chosen.get("_id")), "message_mention", "已按提及的姓名/住院号匹配患者。"
        mention_tokens = []
        if names:
            mention_tokens.append("姓名: " + "、".join(names))
        if identifiers:
            mention_tokens.append("住院号/患者号: " + "、".join(identifiers))
        match_note = "检测到患者线索（" + "；".join(mention_tokens) + "），但未在 patient 表中检索到匹配患者。"

    token = _safe_text(patient_id)
    if token:
        patient = await _load_patient_by_id(token)
        if patient:
            return patient, token, "selected_patient_id", match_note
        if not (identifiers or names):
            raise ValueError("无效患者ID")
    return None, None, "none", match_note


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
    message: str,
) -> tuple[str, str, str | None, str, str]:
    patient, resolved_patient_id, match_source, match_note = await _resolve_patient_from_payload(patient_id, message)
    if not patient or not resolved_patient_id:
        return "", "", None, match_source, match_note

    lines = [
        f"患者标签: {_patient_label(patient)}",
        f"患者ID: {resolved_patient_id}",
        f"性别: {patient.get('gender') or patient.get('sex') or '未知'}",
        f"年龄: {patient.get('age') or patient.get('hisAge') or '未知'}",
        f"住院号: {patient.get('hisPid') or patient.get('hisPID') or patient.get('patientId') or patient.get('mrn') or '未知'}",
        f"科室: {patient.get('dept') or patient.get('deptName') or patient.get('hisDept') or patient.get('ward') or '未知'}",
        f"护理级别: {patient.get('nursingLevel') or '未知'}",
        f"主要诊断: {patient.get('clinicalDiagnosis') or patient.get('admissionDiagnosis') or '暂无诊断'}",
    ]

    if match_note:
        lines.append(f"患者匹配说明: {match_note}")

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
        lines.append("观察项(近24h/最新): " + _clip_text(obs, 1000))
    if io_text:
        lines.append("出入量总结: " + _clip_text(io_text, 800))
    if drug_text:
        lines.append("用药执行(近24h): " + _clip_text(drug_text, 1200))
    if order_text:
        lines.append("医嘱摘要: " + _clip_text(order_text, 1200))
    nursing_record_text, nursing_plan_text = nursing_tuple
    if nursing_record_text:
        lines.append("护理记录(近24h): " + _clip_text(nursing_record_text, 1000))
    if nursing_plan_text:
        lines.append(nursing_plan_text)
    lab_text, exam_text = lab_exam_tuple
    if lab_text:
        lines.append("检验摘要(近72h): " + _clip_text(lab_text, 1200))
    if exam_text:
        lines.append("检查摘要(近72h): " + _clip_text(exam_text, 800))
    if alert_text:
        lines.append("最近预警: " + _clip_text(alert_text, 800))

    context = "\n".join(lines)
    return _clip_text(context, _AI_CONSULT_CONTEXT_MAX_CHARS), _patient_label(patient), resolved_patient_id, match_source, match_note


def _build_ai_consult_prompts(
    *,
    message: str,
    history: list[ChatTurn],
    match_note: str,
    patient_context: str,
) -> tuple[str, str]:
    intent = _detect_ai_consult_intent(message)
    system_prompt = (
        "你是 ICU AI 问诊助手，面向临床医生/护士提供中文辅助问答。"
        "请基于用户问题、历史对话以及患者上下文，输出简洁、专业、可执行的回答。"
        "若问题中提及具体患者姓名/住院号，优先使用已检索到的 patient 表匹配患者，不要混淆同名患者。"
        "必须严格按以下固定结构输出，并且四个标题都要出现："
        "初步判断："
        "风险点："
        "建议检查："
        "下一步处理："
        "其中每一部分都要有具体内容，不能省略标题，不能合并标题。"
        "不要编造不存在的生命体征、化验或影像结果；若信息不足必须明确说明。"
        "若存在潜在急危重情况，先提示立即线下评估/抢救。"
        "严禁输出 <think>、</think>、思维链、推理过程、内部分析草稿。"
        "只输出纯文本，不要使用任何 markdown 语法（如 #、*、-、```、[链接]()）。"
        "不要输出 markdown 表格，不要长篇空泛免责声明，结尾可简短提示“仅供临床参考，需结合床旁评估”。"
        f"本轮问题意图判定为：{intent['primary']}，重点展开栏目：{intent['focus_section']}。"
        f"{intent['focus_instruction']}"
    )
    user_prompt = (
        f"【本轮问题意图】\n意图={intent['primary']}；重点栏目={intent['focus_section']}；关键词={intent['matched_keywords']}\n\n"
        f"【患者匹配信息】\n{match_note or '无额外匹配提示'}\n\n"
        f"【患者上下文】\n{patient_context or '未选择具体患者，本轮按通用 ICU 问答处理。'}\n\n"
        f"【历史对话】\n{_format_history(history)}\n\n"
        f"【本轮问题】\n{_clip_text(message, 2000)}\n\n"
        f"请直接回答本轮问题，并优先把重点写在“{intent['focus_section']}”。"
    )
    return system_prompt, user_prompt


def _build_ai_consult_preview_prompts(
    *,
    message: str,
    history: list[ChatTurn],
    match_note: str,
    patient_context: str,
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
) -> tuple[str, str]:
    intent = _detect_ai_consult_intent(message)
    previous_question = _latest_history_content(history, "user")
    previous_answer = _latest_history_content(history, "assistant")
    system_prompt = (
        "你是 ICU AI 问诊助手。"
        "上一轮回答与当前问题过于相似，需要你重新作答。"
        "这一次必须优先响应【本轮问题】本身，不要只重复患者概况、固定模板或上一轮原话。"
        "若当前问题与上一轮关注点不同，就必须体现新的分析角度。"
        "仍然必须严格按以下固定结构输出，并且四个标题都要出现："
        "初步判断："
        "风险点："
        "建议检查："
        "下一步处理："
        "每个部分都要有具体内容。"
        "严禁输出 <think>、</think>、思维链、内部推理。"
        "只输出纯文本，不要使用 markdown。"
        f"本轮问题意图判定为：{intent['primary']}，重点展开栏目：{intent['focus_section']}。"
        f"{intent['focus_instruction']}"
    )
    user_prompt = (
        f"【本轮问题意图】\n意图={intent['primary']}；重点栏目={intent['focus_section']}；关键词={intent['matched_keywords']}\n\n"
        f"【患者匹配信息】\n{match_note or '无额外匹配提示'}\n\n"
        f"【患者上下文】\n{patient_context or '未选择具体患者，本轮按通用 ICU 问答处理。'}\n\n"
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
async def ai_chat_consult(payload: ChatConsultPayload):
    message = str(payload.message or "").strip()
    if not message:
        return {"code": 400, "message": "message不能为空"}
    intent = _detect_ai_consult_intent(message)

    patient_id = str(payload.patient_id or "").strip() or None
    try:
        patient_context, patient_label, resolved_patient_id, match_source, match_note = await _build_patient_context(patient_id, message)
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}

    system_prompt, user_prompt = _build_ai_consult_prompts(
        message=message,
        history=payload.history,
        match_note=match_note,
        patient_context=patient_context,
    )
    max_tokens, llm_timeout_seconds, total_timeout_seconds = _resolve_ai_consult_limits(
        message=message,
        history=payload.history,
        patient_context=patient_context,
    )

    try:
        cfg = get_config()
        answer = await asyncio.wait_for(
            call_api_llm(
                system_prompt,
                user_prompt,
                cfg.llm_fast_model or cfg.llm_model_medical or None,
                max_tokens=max_tokens,
                timeout_seconds=llm_timeout_seconds,
            ),
            timeout=total_timeout_seconds,
        )
        answer_text = _finalize_ai_consult_answer(str(answer or "").strip())
        if _should_retry_ai_consult_answer(message=message, history=payload.history, answer_text=answer_text):
            retry_system_prompt, retry_user_prompt = _build_ai_consult_retry_prompts(
                message=message,
                history=payload.history,
                match_note=match_note,
                patient_context=patient_context,
            )
            retry_answer = await asyncio.wait_for(
                call_api_llm(
                    retry_system_prompt,
                    retry_user_prompt,
                    cfg.llm_fast_model or cfg.llm_model_medical or None,
                    max_tokens=max_tokens,
                    timeout_seconds=llm_timeout_seconds,
                ),
                timeout=total_timeout_seconds,
            )
            retry_text = _finalize_ai_consult_answer(str(retry_answer or "").strip())
            if retry_text:
                answer_text = retry_text
        return {
            "code": 0,
            "answer": answer_text,
            "patient_context_used": bool(patient_context),
            "patient_label": patient_label,
            "resolved_patient_id": resolved_patient_id,
            "patient_match_source": match_source,
            "patient_match_note": match_note,
            "answer_max_tokens": max_tokens,
            "intent_primary": intent["primary"],
            "intent_focus_section": intent["focus_section"],
        }
    except LLMRuntimeUnavailableError as exc:
        retry_after_seconds = _parse_retry_after_seconds(str(exc))
        logger.warning("AI consult chat degraded due to LLM runtime unavailable: %s", exc)
        return _build_ai_consult_degraded_response(
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
    except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
        logger.warning("AI consult chat timeout, degraded: %s", exc)
        return _build_ai_consult_degraded_response(
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
    except Exception as exc:
        logger.exception("AI consult chat error")
        return {
            "code": 500,
            "message": "AI服务异常",
            "answer": "",
            "error": f"AI服务异常: {str(exc)[:120]}",
            "intent_primary": intent["primary"],
            "intent_focus_section": intent["focus_section"],
        }


@router.post("/api/ai/chat-consult/stream")
async def ai_chat_consult_stream(payload: ChatConsultPayload):
    message = str(payload.message or "").strip()
    if not message:
        return JSONResponse(status_code=400, content={"code": 400, "message": "message不能为空"})
    intent = _detect_ai_consult_intent(message)

    patient_id = str(payload.patient_id or "").strip() or None
    try:
        patient_context, patient_label, resolved_patient_id, match_source, match_note = await _build_patient_context(patient_id, message)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": 400, "message": str(exc)})

    system_prompt, user_prompt = _build_ai_consult_prompts(
        message=message,
        history=payload.history,
        match_note=match_note,
        patient_context=patient_context,
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
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "model": model_name or "",
                "answer_max_tokens": max_tokens,
                "intent_primary": intent["primary"],
                "intent_focus_section": intent["focus_section"],
            },
        )

        raw_answer_chunks: list[str] = []
        visible_answer_text = ""
        stream_used = False
        preview_emitted = False
        first_delta_received = False
        preview_task: asyncio.Task | None = asyncio.create_task(
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
            yield _sse_pack(
                "done",
                {
                    "code": 0,
                    "degraded": True,
                    "message": "AI服务暂时繁忙，已降级为提示模式",
                    "answer": _build_ai_consult_degraded_answer(retry_after_seconds),
                    "retry_after_seconds": retry_after_seconds,
                    "patient_context_used": bool(patient_context),
                    "patient_label": patient_label,
                    "resolved_patient_id": resolved_patient_id,
                    "patient_match_source": match_source,
                    "patient_match_note": match_note,
                    "stream_used": stream_used,
                    "intent_primary": intent["primary"],
                    "intent_focus_section": intent["focus_section"],
                },
            )
            return
        except (asyncio.TimeoutError, httpx.TimeoutException):
            yield _sse_pack(
                "done",
                {
                    "code": 0,
                    "degraded": True,
                    "message": "AI服务响应超时，已降级为提示模式",
                    "answer": _build_ai_consult_degraded_answer(10),
                    "retry_after_seconds": 10,
                    "patient_context_used": bool(patient_context),
                    "patient_label": patient_label,
                    "resolved_patient_id": resolved_patient_id,
                    "patient_match_source": match_source,
                    "patient_match_note": match_note,
                    "stream_used": stream_used,
                    "intent_primary": intent["primary"],
                    "intent_focus_section": intent["focus_section"],
                },
            )
            return
        except Exception as exc:
            logger.exception("AI consult stream fallback failed")
            yield _sse_pack(
                "error",
                {
                    "code": 500,
                    "message": "AI服务异常",
                    "error": f"AI服务异常: {str(exc)[:120]}",
                },
            )
            return

        answer_text = _finalize_ai_consult_answer(visible_answer_text or "".join(raw_answer_chunks).strip())
        if _should_retry_ai_consult_answer(message=message, history=payload.history, answer_text=answer_text):
            try:
                retry_system_prompt, retry_user_prompt = _build_ai_consult_retry_prompts(
                    message=message,
                    history=payload.history,
                    match_note=match_note,
                    patient_context=patient_context,
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
                retry_text = _finalize_ai_consult_answer(str(retry_answer or "").strip())
                if retry_text:
                    answer_text = retry_text
            except Exception as retry_exc:
                logger.warning("AI consult stream duplicate-answer retry skipped: %s", retry_exc)
        yield _sse_pack(
            "done",
            {
                "code": 0,
                "answer": answer_text,
                "patient_context_used": bool(patient_context),
                "patient_label": patient_label,
                "resolved_patient_id": resolved_patient_id,
                "patient_match_source": match_source,
                "patient_match_note": match_note,
                "stream_used": stream_used,
                "answer_max_tokens": max_tokens,
                "intent_primary": intent["primary"],
                "intent_focus_section": intent["focus_section"],
            },
        )

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
