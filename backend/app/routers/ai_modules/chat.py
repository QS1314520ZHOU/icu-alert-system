from __future__ import annotations

import asyncio
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
_AI_CONSULT_LLM_TIMEOUT_SECONDS = 20
_AI_CONSULT_TOTAL_TIMEOUT_SECONDS = 36
_AI_CONSULT_MAX_TOKENS = 900
_AI_CONSULT_PREVIEW_TIMEOUT_SECONDS = 6
_AI_CONSULT_PREVIEW_MAX_TOKENS = 180
_AI_CONSULT_CONTEXT_ITEM_TIMEOUT_SECONDS = 1.8
_AI_CONSULT_CONTEXT_MAX_CHARS = 4200
_AI_CONSULT_HISTORY_TURNS = 8
_AI_CONSULT_HISTORY_ITEM_MAX_CHARS = 320

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
    system_prompt = (
        "你是 ICU AI 问诊助手，面向临床医生/护士提供中文辅助问答。"
        "请基于用户问题、历史对话以及患者上下文，输出简洁、专业、可执行的回答。"
        "若问题中提及具体患者姓名/住院号，优先使用已检索到的 patient 表匹配患者，不要混淆同名患者。"
        "优先给出：1) 初步判断；2) 关键风险；3) 建议补充的信息/检查；4) 下一步处理建议。"
        "不要编造不存在的生命体征、化验或影像结果；若信息不足必须明确说明。"
        "若存在潜在急危重情况，先提示立即线下评估/抢救。"
        "只输出纯文本，不要使用任何 markdown 语法（如 #、*、-、```、[链接]()）。"
        "不要输出 markdown 表格，不要长篇空泛免责声明，结尾可简短提示“仅供临床参考，需结合床旁评估”。"
    )
    user_prompt = (
        f"【患者匹配信息】\n{match_note or '无额外匹配提示'}\n\n"
        f"【患者上下文】\n{patient_context or '未选择具体患者，本轮按通用 ICU 问答处理。'}\n\n"
        f"【历史对话】\n{_format_history(history)}\n\n"
        f"【本轮问题】\n{_clip_text(message, 2000)}\n\n"
        "请直接回答本轮问题。"
    )
    return system_prompt, user_prompt


def _build_ai_consult_preview_prompts(
    *,
    message: str,
    history: list[ChatTurn],
    match_note: str,
    patient_context: str,
) -> tuple[str, str]:
    system_prompt = (
        "你是 ICU AI 问诊助手。"
        "请先给出“首屏预览”回答：仅 1-2 句中文，聚焦初步判断与第一优先风险，必须可执行。"
        "不要使用 markdown，不要列表，不要展开细节，不要超过 90 字。"
        "若信息不足，明确指出最关键缺失信息。"
    )
    user_prompt = (
        f"【患者匹配信息】{_clip_text(match_note or '无额外匹配提示', 200)}\n"
        f"【患者上下文】{_clip_text(patient_context or '未选择具体患者，本轮按通用 ICU 问答处理。', 900)}\n"
        f"【历史对话】{_clip_text(_format_history(history), 450)}\n"
        f"【本轮问题】{_clip_text(message, 800)}\n"
        "请输出首屏预览。"
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
):
    llm_url = cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": model or cfg.llm_fast_model,
        "temperature": 0.1,
        "max_tokens": _AI_CONSULT_MAX_TOKENS,
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

    timeout = httpx.Timeout(_AI_CONSULT_TOTAL_TIMEOUT_SECONDS, read=_AI_CONSULT_TOTAL_TIMEOUT_SECONDS)
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

    try:
        cfg = get_config()
        answer = await asyncio.wait_for(
            call_api_llm(
                system_prompt,
                user_prompt,
                cfg.llm_fast_model or cfg.llm_model_medical or None,
                max_tokens=_AI_CONSULT_MAX_TOKENS,
                timeout_seconds=_AI_CONSULT_LLM_TIMEOUT_SECONDS,
            ),
            timeout=_AI_CONSULT_TOTAL_TIMEOUT_SECONDS,
        )
        answer_text = _strip_markdown_for_display(str(answer or "").strip()) or "暂时没有生成有效回答，请稍后重试。"
        return {
            "code": 0,
            "answer": answer_text,
            "patient_context_used": bool(patient_context),
            "patient_label": patient_label,
            "resolved_patient_id": resolved_patient_id,
            "patient_match_source": match_source,
            "patient_match_note": match_note,
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
        )
    except Exception as exc:
        logger.exception("AI consult chat error")
        return {
            "code": 500,
            "message": "AI服务异常",
            "answer": "",
            "error": f"AI服务异常: {str(exc)[:120]}",
        }


@router.post("/api/ai/chat-consult/stream")
async def ai_chat_consult_stream(payload: ChatConsultPayload):
    message = str(payload.message or "").strip()
    if not message:
        return JSONResponse(status_code=400, content={"code": 400, "message": "message不能为空"})

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
            },
        )

        raw_answer_chunks: list[str] = []
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
                    yield _sse_pack("delta", {"text": delta})
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
                        max_tokens=_AI_CONSULT_MAX_TOKENS,
                        timeout_seconds=_AI_CONSULT_LLM_TIMEOUT_SECONDS,
                    ),
                    timeout=_AI_CONSULT_TOTAL_TIMEOUT_SECONDS,
                )
                fallback_text = str(fallback_answer or "").strip()
                if fallback_text:
                    raw_answer_chunks.append(fallback_text)
                    yield _sse_pack("delta", {"text": fallback_text})
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

        answer_text = _strip_markdown_for_display("".join(raw_answer_chunks).strip()) or "暂时没有生成有效回答，请稍后重试。"
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
