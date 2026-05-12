from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body

from app import runtime
from app.services.treatment_policy_service import get_treatment_policy_service
from app.utils.serialization import serialize_doc

router = APIRouter()


@router.get("/api/treatment/recommend/{patient_id}")
async def treatment_recommend(patient_id: str):
    service = get_treatment_policy_service(db=runtime.db, config=runtime.config, alert_engine=runtime.alert_engine)
    result = await service.recommend_action(patient_id)
    return serialize_doc(result)


@router.post("/api/treatment/feedback")
async def treatment_feedback(payload: dict[str, Any] = Body(default={})):
    now = datetime.now()
    record = {
        "patient_id": str(payload.get("patient_id") or ""),
        "recommendation_id": str(payload.get("recommendation_id") or ""),
        "adopted": bool(payload.get("adopted")) if payload.get("adopted") is not None else None,
        "reason": str(payload.get("reason") or "")[:500],
        "actor": str(payload.get("actor") or "")[:120],
        "created_at": now,
        "updated_at": now,
    }
    inserted = await runtime.db.col("treatment_policy_feedback").insert_one(record)
    return {"code": 0, "id": str(inserted.inserted_id), "record": serialize_doc(record)}
