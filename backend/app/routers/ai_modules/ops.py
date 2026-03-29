from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import APIRouter, Body, Query

from app import runtime
from app.config import get_config
from app.utils.api_llm import call_api_llm
from app.utils.patient_data import fetch_dc_exam_items_by_his_pid
from app.utils.patient_helpers import patient_his_pid_candidates
from app.utils.serialization import safe_oid, serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")
API_TZ = ZoneInfo("Asia/Shanghai")


async def _safe_ai_handoff_dependency(coro, *, timeout_seconds: float, fallback):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except Exception as exc:
        logger.warning("AI handoff dependency degraded: %s", exc)
        return fallback


@router.get("/api/patients/{patient_id}/handoff-summary")
async def patient_handoff_summary(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    try:
        cfg = get_config()
        similar_case_review = await _safe_ai_handoff_dependency(
            runtime.alert_engine.get_similar_case_outcomes(patient, limit=5),
            timeout_seconds=8.0,
            fallback=None,
        ) if hasattr(runtime.alert_engine, "get_similar_case_outcomes") else None
        nursing_context = await _safe_ai_handoff_dependency(
            runtime.alert_engine._collect_nursing_context(patient, str(pid), hours=12),
            timeout_seconds=5.0,
            fallback=None,
        ) if hasattr(runtime.alert_engine, "_collect_nursing_context") else None
        result = await runtime.ai_handoff_service.generate(
            patient_id=str(pid),
            patient_doc=patient,
            similar_case_review=similar_case_review,
            nursing_context=nursing_context,
            llm_call=lambda system_prompt, user_prompt, model=None: call_api_llm(
                system_prompt,
                user_prompt,
                model,
                max_tokens=1200,
                timeout_seconds=35,
            ),
            model=cfg.llm_fast_model or None,
        )
        return {
            "code": 0,
            "summary": serialize_doc(result.get("summary") or {}),
            "context_snapshot": serialize_doc(result.get("context_snapshot") or {}),
        }
    except Exception as exc:
        logger.exception("AI handoff summary error")
        return {"code": 500, "summary": {}, "error": f"AI服务异常: {str(exc)[:120]}"}


@router.post("/api/ai/feedback")
async def ai_feedback(payload: dict = Body(...)):
    prediction_id = str(payload.get("prediction_id") or "").strip()
    outcome = str(payload.get("outcome") or "").strip().lower()
    module = str(payload.get("module") or "ai_risk").strip() or "ai_risk"
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}

    if not prediction_id:
        return {"code": 400, "message": "prediction_id不能为空"}
    if outcome not in {"confirmed", "dismissed", "inaccurate"}:
        return {"code": 400, "message": "outcome必须为 confirmed/dismissed/inaccurate"}

    try:
        await runtime.ai_monitor.log_prediction_feedback(
            module=module,
            prediction_id=prediction_id,
            outcome=outcome,
            detail=detail,
        )
    except Exception as exc:
        logger.error("AI feedback log error: %s", exc)

    oid = safe_oid(prediction_id)
    if oid is not None:
        try:
            await runtime.db.col("alert_records").update_one(
                {"_id": oid},
                {"$set": {"ai_feedback.outcome": outcome, "ai_feedback.detail": detail, "ai_feedback.updated_at": datetime.now(API_TZ)}},
            )
        except Exception as exc:
            logger.error("AI feedback alert update error: %s", exc)

    return {"code": 0, "prediction_id": prediction_id, "outcome": outcome}


@router.get("/api/ai/feedback/summary")
async def ai_feedback_summary(days: int = Query(default=7, ge=1, le=90), limit: int = Query(default=50, ge=1, le=200)):
    since = datetime.now(API_TZ) - timedelta(days=days)
    cursor = runtime.db.col("ai_prediction_feedback").find({"created_at": {"$gte": since}}).sort("created_at", -1).limit(500)
    docs = [doc async for doc in cursor]

    by_outcome = {"confirmed": 0, "dismissed": 0, "inaccurate": 0}
    by_module: dict[str, int] = {}
    for doc in docs:
        outcome = str(doc.get("outcome") or "").strip().lower()
        module = str(doc.get("module") or "unknown").strip() or "unknown"
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        by_module[module] = int(by_module.get(module, 0) or 0) + 1

    recent_docs = docs[:limit]
    alert_ids: list[ObjectId] = []
    alert_map: dict[str, dict] = {}
    for doc in recent_docs:
        oid = safe_oid(doc.get("prediction_id"))
        if oid is not None:
            alert_ids.append(oid)

    if alert_ids:
        alert_cursor = runtime.db.col("alert_records").find({"_id": {"$in": alert_ids}})
        async for alert_doc in alert_cursor:
            alert_map[str(alert_doc.get("_id"))] = alert_doc

    recent_rows = []
    for doc in recent_docs:
        prediction_id = str(doc.get("prediction_id") or "").strip()
        alert_doc = alert_map.get(prediction_id) or {}
        recent_rows.append(
            serialize_doc(
                {
                    "prediction_id": prediction_id,
                    "module": str(doc.get("module") or "ai_risk"),
                    "outcome": str(doc.get("outcome") or ""),
                    "detail": doc.get("detail") or {},
                    "created_at": doc.get("created_at"),
                    "alert_name": alert_doc.get("name") or alert_doc.get("rule_id") or "",
                    "patient_id": alert_doc.get("patient_id") or "",
                    "patient_name": alert_doc.get("patient_name") or alert_doc.get("name") or "",
                    "bed": alert_doc.get("bed") or alert_doc.get("patient_bed") or alert_doc.get("hisBed") or "",
                    "severity": alert_doc.get("severity") or "",
                }
            )
        )

    total = len(docs)
    confirmed = int(by_outcome.get("confirmed") or 0)
    inaccurate = int(by_outcome.get("inaccurate") or 0)
    summary = {
        "total": total,
        "by_outcome": by_outcome,
        "by_module": by_module,
        "confirmed_ratio": round((confirmed / total), 3) if total else 0,
        "inaccurate_ratio": round((inaccurate / total), 3) if total else 0,
    }
    return {"code": 0, "days": days, "summary": summary, "recent": recent_rows}


@router.get("/api/ai/monitor/summary")
async def ai_monitor_summary(date: str | None = Query(default=None)):
    try:
        summary = await runtime.ai_monitor.get_daily_summary(date=date)
        return {
            "code": 0,
            "date": summary.get("date") or date or datetime.now(API_TZ).strftime("%Y-%m-%d"),
            "stats": [serialize_doc(item) for item in summary.get("stats", [])],
            "active_alerts": [serialize_doc(item) for item in summary.get("active_alerts", [])],
        }
    except Exception as exc:
        logger.error("AI monitor summary error: %s", exc)
        return {"code": 0, "date": date or datetime.now(API_TZ).strftime("%Y-%m-%d"), "stats": [], "active_alerts": [], "error": f"监控汇总异常: {str(exc)[:120]}"}


@router.get("/api/ai/rule-recommendations/{patient_id}")
async def ai_rule_recommendations(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    system_prompt = (
        "你是ICU预警规则专家。根据患者诊断和当前状态，推荐个性化监测指标和预警阈值。"
        "必须返回严格 JSON 数组，不要输出 markdown，不要输出解释，不要输出开场白。"
        "每个元素必须包含字段: "
        "parameter(中文参数名), operator(仅允许 >,<,>=,<=), threshold(阈值，字符串或数字), "
        "severity(仅允许 warning/high/critical), reason(中文理由)。"
        "最多返回 6 条，内容务必简洁、可执行。"
    )
    user_prompt = (
        f"患者: {patient.get('name', '未知')}\n"
        f"诊断: {patient.get('clinicalDiagnosis', patient.get('admissionDiagnosis', '未知'))}\n"
        f"护理级别: {patient.get('nursingLevel', '未知')}\n"
        f"请推荐针对性预警规则。"
    )

    normalized_rows: list[dict[str, Any]] = []
    normalized_text = ""

    try:
        text = await call_api_llm(
            system_prompt,
            user_prompt,
            max_tokens=1200,
            timeout_seconds=120,
        )
        normalized_text = text or ""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                for item in parsed[:6]:
                    if not isinstance(item, dict):
                        continue
                    normalized_rows.append(
                        {
                            "parameter": item.get("parameter") or item.get("name") or "",
                            "operator": item.get("operator") or "",
                            "threshold": item.get("threshold"),
                            "severity": item.get("severity") or "warning",
                            "reason": item.get("reason") or item.get("description") or "",
                        }
                    )
        except Exception:
            logger.debug("AI rule recommendations JSON parse fallback", exc_info=True)
        return {"code": 0, "recommendations": normalized_rows, "raw_text": normalized_text}
    except Exception as exc:
        logger.error("AI rule recommendations error: %s", exc)
        return {
            "code": 500,
            "recommendations": normalized_rows,
            "raw_text": normalized_text,
            "error": f"AI服务异常: {str(exc)[:100]}",
        }


@router.get("/api/ai/lab-summary/{patient_id}")
async def ai_lab_summary(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}

    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    exams = []
    patient_ids = patient_his_pid_candidates(patient)
    if patient_ids:
        his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
        cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(300)
        item_docs = [doc async for doc in cursor]
        if not item_docs:
            _, item_docs = await fetch_dc_exam_items_by_his_pid(patient_ids, limit_exams=40, limit_items=300)
        exams = [serialize_doc(doc) for doc in item_docs[:120]]

    if not exams:
        return {"code": 0, "summary": "暂无检验数据，无法生成摘要。"}

    system_prompt = (
        "你是ICU临床检验分析专家。请直接输出中文分析正文，重点关注异常指标、可能的临床意义和后续建议。"
        "不要复述用户要求，不要以“好的”“已收到”“以下是分析”之类的对话式开场。"
        "优先按检验类别分段，内容简洁、专业、可执行。"
    )
    user_prompt = (
        f"患者: {patient.get('name', '未知')}，"
        f"诊断: {patient.get('clinicalDiagnosis', patient.get('admissionDiagnosis', '未知'))}\n"
        f"近期检验数据:\n{json.dumps(exams[:15], ensure_ascii=False, default=str)}"
    )
    try:
        cfg = get_config()
        summary = await call_api_llm(
            system_prompt,
            user_prompt,
            cfg.llm_fast_model or None,
            max_tokens=1400,
            timeout_seconds=180,
        )
        return {"code": 0, "summary": summary}
    except Exception as exc:
        logger.error("AI lab summary error: %s", exc)
        return {"code": 0, "summary": "", "error": f"AI服务异常: {str(exc)[:100]}"}
