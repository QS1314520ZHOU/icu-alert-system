from __future__ import annotations

import logging
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body

from app import runtime
from app.config import get_config
from app.services.document_generator import ClinicalDocumentGenerator
from app.utils.serialization import serialize_doc

router = APIRouter()
logger = logging.getLogger("icu-alert")


def _safe_text_list(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows


def _normalize_mdt_decisions(payload: dict | None) -> list[dict]:
    rows = (payload or {}).get("decisions") if isinstance((payload or {}).get("decisions"), list) else []
    normalized = []
    for idx, item in enumerate(rows[:20], start=1):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or item.get("title") or "").strip()
        if not action:
            continue
        normalized.append(
            {
                "id": str(item.get("id") or f"decision-{idx}"),
                "action": action,
                "owner": str(item.get("owner") or "").strip() or "值班医生",
                "deadline": str(item.get("deadline") or "").strip() or "6h",
                "monitoring": str(item.get("monitoring") or "").strip() or "按系统指标复评",
                "review_time": str(item.get("review_time") or "").strip() or "6h",
                "status": str(item.get("status") or "pending").strip() or "pending",
                "note": str(item.get("note") or "").strip(),
            }
        )
    return normalized


def _build_order_drafts(*, patient: dict, assessment: dict | None, decisions: list[dict]) -> list[dict]:
    patient_name = str(patient.get("name") or patient.get("hisName") or "当前患者").strip()
    meta_actions = []
    if isinstance(assessment, dict):
        result = assessment.get("result") if isinstance(assessment.get("result"), dict) else assessment
        meta = result.get("meta_agent") if isinstance(result.get("meta_agent"), dict) else {}
        meta_actions = _safe_text_list(meta.get("final_actions"), limit=10)
    base_actions = [row.get("action") for row in decisions if str(row.get("action") or "").strip()]
    actions = list(dict.fromkeys([*base_actions, *meta_actions]))[:8]
    drafts = []
    for idx, action in enumerate(actions, start=1):
        drafts.append({"id": f"order-{idx}", "category": "医嘱建议", "order_text": f"{patient_name}：{action}", "priority": "high" if idx <= 2 else "medium", "status": "draft", "source": "mdt_workspace"})
    if not drafts:
        drafts.append({"id": "order-1", "category": "医嘱建议", "order_text": f"{patient_name}：等待 MDT 决议后生成待审核医嘱草稿。", "priority": "medium", "status": "draft", "source": "mdt_workspace"})
    return drafts


@router.post("/api/ai/documents/{patient_id}")
async def ai_generate_document(patient_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    doc_type = str((payload or {}).get("doc_type") or "").strip()
    if not doc_type:
        return {"code": 400, "message": "doc_type不能为空"}
    time_range = (payload or {}).get("time_range") if isinstance((payload or {}).get("time_range"), dict) else None

    generator = ClinicalDocumentGenerator(
        db=runtime.db,
        config=get_config(),
        alert_engine=runtime.alert_engine,
        rag_service=runtime.ai_rag_service,
        ai_monitor=runtime.ai_monitor,
        ai_handoff_service=runtime.ai_handoff_service,
    )
    try:
        record = await generator.generate(str(pid), doc_type, time_range=time_range)
        return {"code": 0, "document": serialize_doc(record) if record else None}
    except ValueError as exc:
        return {"code": 400, "message": str(exc)}
    except Exception as exc:
        logger.error("AI document generation error: %s", exc)
        return {"code": 0, "document": None, "error": f"文书生成异常: {str(exc)[:120]}"}


@router.get("/api/ai/mdt-workspace/{patient_id}")
async def ai_mdt_workspace(patient_id: str):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1, "name": 1, "hisName": 1, "hisBed": 1, "bed": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    workspace = await runtime.db.col("score_records").find_one({"patient_id": str(pid), "score_type": "mdt_workspace_record"}, sort=[("updated_at", -1), ("calc_time", -1)])
    documents_cursor = runtime.db.col("score_records").find({"patient_id": str(pid), "score_type": "clinical_document", "doc_type": {"$in": ["mdt_summary", "daily_progress", "consultation_request"]}}).sort("updated_at", -1).limit(20)
    documents = [serialize_doc(doc) async for doc in documents_cursor]
    assessment = await runtime.db.col("score_records").find_one({"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"}, sort=[("calc_time", -1)])
    decisions = workspace.get("decisions") if isinstance(workspace, dict) and isinstance(workspace.get("decisions"), list) else []
    order_drafts = workspace.get("order_drafts") if isinstance(workspace, dict) and isinstance(workspace.get("order_drafts"), list) else []
    if not order_drafts:
        order_drafts = _build_order_drafts(patient=patient, assessment=assessment, decisions=decisions)
    return {"code": 0, "workspace": serialize_doc(workspace) if workspace else None, "documents": documents, "order_drafts": serialize_doc(order_drafts)}


@router.post("/api/ai/mdt-workspace/{patient_id}")
async def ai_save_mdt_workspace(patient_id: str, payload: dict = Body(default={})):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        return {"code": 400, "message": "无效患者ID"}
    patient = await runtime.db.col("patient").find_one({"_id": pid})
    if not patient:
        return {"code": 404, "message": "患者不存在"}

    assessment = await runtime.db.col("score_records").find_one({"patient_id": str(pid), "score_type": "multi_agent_mdt_assessment"}, sort=[("calc_time", -1)])
    decisions = _normalize_mdt_decisions(payload)
    consult_record = str((payload or {}).get("consult_record") or "").strip()
    progress_record = str((payload or {}).get("progress_record") or "").strip()
    order_drafts = (payload or {}).get("order_drafts") if isinstance((payload or {}).get("order_drafts"), list) else None
    normalized_orders = []
    for idx, item in enumerate(order_drafts or [], start=1):
        if not isinstance(item, dict):
            continue
        order_text = str(item.get("order_text") or item.get("text") or "").strip()
        if not order_text:
            continue
        normalized_orders.append({"id": str(item.get("id") or f"order-{idx}"), "category": str(item.get("category") or "医嘱建议").strip(), "order_text": order_text, "priority": str(item.get("priority") or "medium").strip(), "status": str(item.get("status") or "draft").strip(), "source": str(item.get("source") or "mdt_workspace").strip()})
    if not normalized_orders:
        normalized_orders = _build_order_drafts(patient=patient, assessment=assessment, decisions=decisions)

    now = datetime.now()
    record = {
        "patient_id": str(pid),
        "patient_name": patient.get("name") or patient.get("hisName") or "",
        "bed": patient.get("hisBed") or patient.get("bed") or "",
        "score_type": "mdt_workspace_record",
        "summary": decisions[0].get("action") if decisions else "MDT 工作站结构化记录",
        "decisions": decisions,
        "consult_record": consult_record,
        "progress_record": progress_record,
        "order_drafts": normalized_orders,
        "meta_actions": _safe_text_list((((assessment or {}).get("result") or {}).get("meta_agent") or {}).get("final_actions"), limit=12),
        "updated_at": now,
        "calc_time": now,
    }
    existing = await runtime.db.col("score_records").find_one({"patient_id": str(pid), "score_type": "mdt_workspace_record"}, sort=[("updated_at", -1), ("calc_time", -1)])
    if existing:
        await runtime.db.col("score_records").update_one({"_id": existing["_id"]}, {"$set": record})
        record["_id"] = existing["_id"]
    else:
        insert_res = await runtime.db.col("score_records").insert_one(record)
        record["_id"] = insert_res.inserted_id
    return {"code": 0, "workspace": serialize_doc(record)}
