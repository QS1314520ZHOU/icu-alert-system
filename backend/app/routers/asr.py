"""ASR transcription endpoints for ICU voice ward-round entry."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.runtime import ConfigDep, DbDep
from app.services.asr_client import ASRRuntimeUnavailableError, transcribe as transcribe_audio
from app.services.audit_service import normalize_actor, write_audit_log
from app.services.voice_rounding import VoiceRoundingService
from app.services.ward_round_generator import WardRoundGenerator

logger = logging.getLogger("icu-alert")

API_TZ = ZoneInfo("Asia/Shanghai")
COLLECTION_DRAFTS = "clinical_document_drafts"

router = APIRouter(prefix="/api/asr", tags=["asr"])

# TODO: move ICU hotwords to runtime/config yaml after deployment wordlist is finalized.
ICU_MEDICAL_HOTWORDS = [
    "ICU",
    "RASS",
    "CAM-ICU",
    "GCS",
    "SOFA",
    "APACHE",
    "CPOT",
    "PEEP",
    "FiO2",
    "SpO2",
    "PaO2",
    "PaCO2",
    "CRRT",
    "俯卧位",
    "气管插管",
    "机械通气",
    "去甲肾上腺素",
    "乳酸",
    "降钙素原",
    "脓毒症",
    "镇痛",
    "镇静",
]


def _actor(request: Request, actor: str | None = None) -> str:
    return normalize_actor(
        actor,
        request.headers.get("x-user-id"),
        request.headers.get("x-actor-id"),
        request.headers.get("x-operator-id"),
    )


def _audit_source_data(raw_text: str) -> dict[str, Any]:
    # Reuse WardRoundGenerator._audit_numbers without changing its signature.
    # The raw ASR text is the only trusted number source in this upload path.
    return {"respiratory": {"asr_transcript": raw_text}}


async def _persist_draft(
    db,
    *,
    patient_id: str | None,
    raw_text: str,
    corrected_text: str,
    asr_result: dict[str, Any],
    correction: dict[str, Any],
    audit: dict[str, Any],
    needs_review: bool,
    actor: str,
) -> str:
    now = datetime.now(API_TZ)
    draft_id = str(uuid.uuid4())
    content = {
        "content_type": "voice_ward_round",
        "source": "asr",
        "raw_transcription": raw_text,
        "corrected_text": corrected_text,
        "asr": {
            "segments": asr_result.get("segments") or [],
            "duration": float(asr_result.get("duration") or 0),
        },
        "correction": correction,
        "number_audit": audit,
        "needs_review": needs_review,
    }
    draft_doc = {
        "_id": draft_id,
        "patient_id": str(patient_id or ""),
        "doc_type": "voice_ward_round",
        "status": "draft",
        "ai_original": content,
        "current_content": content,
        "citations": [],
        "hallucination_warnings": audit.get("hallucinated_numbers") or [],
        "context_snapshot": {"patient_id": str(patient_id or ""), "source": "voice_ward_round"},
        "model_used": "sensevoice",
        "prompt_version": "voice_ward_round_asr_v1",
        "usage": None,
        "created_at": now,
        "updated_at": now,
        "finalized_by": None,
        "finalized_at": None,
        "created_by": actor,
    }
    await db.col(COLLECTION_DRAFTS).insert_one(draft_doc)
    return draft_id


@router.post("/transcribe")
async def transcribe(
    request: Request,
    db: DbDep,
    config: ConfigDep,
    audio: UploadFile = File(...),
    patient_id: str | None = Form(None),
    actor: str | None = Form(None),
    language: str = Form("zh"),
) -> dict[str, Any]:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频文件为空")

    resolved_actor = _actor(request, actor)
    filename = audio.filename or "rounding_audio.wav"

    try:
        asr_result = await transcribe_audio(
            audio_bytes,
            filename=filename,
            hotwords=ICU_MEDICAL_HOTWORDS,
            language=language or "zh",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ASRRuntimeUnavailableError as exc:
        logger.warning("ASR unavailable patient_id=%s filename=%s: %s", patient_id, filename, exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("ASR transcribe failed patient_id=%s filename=%s", patient_id, filename)
        raise HTTPException(status_code=502, detail=f"ASR转写失败: {exc}")

    raw_text = str(asr_result.get("text") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=422, detail="ASR未返回有效文本")

    correction = await VoiceRoundingService(db, config)._llm_correct(raw_text, str(patient_id or ""))
    corrected_text = str(correction.get("text") or raw_text).strip() or raw_text

    round_time = datetime.now(API_TZ).strftime("%Y-%m-%d %H:%M")
    generator = WardRoundGenerator(db=db, config=config, alert_engine=None)
    audit = generator._audit_numbers(corrected_text, _audit_source_data(raw_text), round_time)

    needs_review = bool(correction.get("needs_human_review"))
    if audit.get("status") == "blocked":
        corrected_text = raw_text
        needs_review = True

    draft_id = await _persist_draft(
        db,
        patient_id=patient_id,
        raw_text=raw_text,
        corrected_text=corrected_text,
        asr_result=asr_result,
        correction=correction,
        audit=audit,
        needs_review=needs_review,
        actor=resolved_actor,
    )
    await write_audit_log(
        db,
        action="asr_transcribe_voice_ward_round",
        module="asr",
        actor=resolved_actor,
        target_type="clinical_document_draft",
        target_id=draft_id,
        detail={
            "patient_id": str(patient_id or ""),
            "filename": filename,
            "duration": asr_result.get("duration"),
            "needs_review": needs_review,
            "audit_status": audit.get("status"),
        },
    )

    return {
        "draft_id": draft_id,
        "raw_transcription": raw_text,
        "corrected_text": corrected_text,
        "audit": audit,
        "needs_review": needs_review,
        "asr": {
            "segments": asr_result.get("segments") or [],
            "duration": asr_result.get("duration") or 0,
        },
    }
