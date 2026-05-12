from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from app import runtime
from app.services.autonomous_agent import AutonomousInvestigationAgent

router = APIRouter()


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/api/ai/autonomous/investigate")
async def autonomous_investigate(payload: dict[str, Any] = Body(default={})):
    patient_id = str(payload.get("patient_id") or "").strip()
    question = str(payload.get("question") or payload.get("message") or "自主排查当前患者主要风险").strip()

    async def _events():
        if not patient_id:
            yield _sse("error", {"message": "patient_id required"})
            return
        agent = AutonomousInvestigationAgent(db=runtime.db, config=runtime.config, alert_engine=runtime.alert_engine, rag_service=runtime.ai_rag_service)
        async for event, data in agent.investigate(patient_id=patient_id, question=question):
            yield _sse(event, data)

    return StreamingResponse(_events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
