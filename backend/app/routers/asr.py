"""
ASR 转写端点。

注意：本端点保留用于向后兼容，但核心逻辑已收敛到 VoiceRoundingService。
新代码应使用 /api/voice-rounding/{patient_id}/transcribe。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.runtime import ConfigDep, DbDep
from app.services.audio_preprocessor import (
    AudioEmptyError,
    AudioInvalidError,
    AudioPreprocessError,
    AudioTooLargeError,
    AudioTooLongError,
    FFmpegUnavailableError,
    FFmpegTimeoutError,
)
from app.services.asr_client import ASREmptyTranscriptionError, ASRRuntimeUnavailableError
from app.services.audit_service import normalize_actor, write_audit_log
from app.services.voice_rounding import VoiceRoundingService

logger = logging.getLogger("icu-alert")

API_TZ = ZoneInfo("Asia/Shanghai")
COLLECTION_DRAFTS = "clinical_document_drafts"

router = APIRouter(prefix="/api/asr", tags=["asr"])


def _actor(request: Request, actor: str | None = None) -> str:
    return normalize_actor(
        actor,
        request.headers.get("x-user-id"),
        request.headers.get("x-actor-id"),
        request.headers.get("x-operator-id"),
    )


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
    """
    ASR 转写端点（向后兼容）。

    内部委托给 VoiceRoundingService，保持返回格式兼容。
    新代码建议使用 /api/voice-rounding/{patient_id}/transcribe。

    错误码：
    - 400: 音频文件为空或格式无效
    - 413: 文件过大或时长过长
    - 422: ASR 未返回有效文本或音频无法解码
    - 503: ASR 或 FFmpeg 服务不可用
    - 504: 处理超时
    - 500/502: 未知内部错误
    """
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频文件为空")

    resolved_actor = _actor(request, actor)
    filename = audio.filename or "rounding_audio.wav"
    content_type = audio.content_type or ""

    # 使用 VoiceRoundingService 统一处理
    svc = VoiceRoundingService(db, config)

    try:
        draft = await svc.transcribe(
            str(patient_id or ""),
            audio_bytes,
            filename=filename,
            content_type=content_type,
        )
    except AudioEmptyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AudioTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except AudioTooLongError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except AudioInvalidError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FFmpegUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FFmpegTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except AudioPreprocessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except ASREmptyTranscriptionError as exc:
        logger.warning("ASR 返回空文本: patient_id=%s, %s", patient_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except ASRRuntimeUnavailableError as exc:
        logger.warning("ASR 不可用: patient_id=%s, %s", patient_id, exc)
        raise HTTPException(status_code=503, detail=f"语音识别服务不可用: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("ASR 转写失败: patient_id=%s, filename=%s", patient_id, filename)
        raise HTTPException(status_code=502, detail="语音转写服务异常，请稍后重试")

    # 检查 ASR 是否返回有效文本
    raw_text = str(draft.get("raw_text") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=422, detail="ASR 未返回有效文本")

    # 审计日志
    try:
        await write_audit_log(
            db,
            action="asr_transcribe_voice_ward_round",
            module="asr",
            actor=resolved_actor,
            target_type="voice_draft",
            target_id=str(draft.get("_id", "")),
            detail={
                "patient_id": str(patient_id or ""),
                "filename": filename,
                "duration_seconds": draft.get("duration_seconds", 0),
                "needs_human_review": draft.get("needs_human_review", False),
                "degraded": draft.get("degraded", False),
            },
        )
    except Exception:
        logger.debug("审计日志写入失败（不阻断主流程）")

    # 返回兼容格式（同时包含新字段）
    return {
        "draft_id": str(draft.get("_id", "")),
        "patient_id": str(patient_id or ""),
        "status": "draft",
        "raw_text": raw_text,
        "raw_transcription": raw_text,  # 向后兼容
        "cleaned_text": draft.get("cleaned_text", ""),
        "corrected_text": draft.get("corrected_text", ""),
        "duration_seconds": draft.get("duration_seconds", 0),
        "segments": draft.get("segments", []),
        "suspect": draft.get("suspect", []),
        "needs_human_review": draft.get("needs_human_review", False),
        "needs_review": draft.get("needs_human_review", False),  # 向后兼容
        "degraded": draft.get("degraded", False),
        "processing": draft.get("processing", {}),
        "asr": {
            "segments": draft.get("segments", []),
            "duration": draft.get("duration_seconds", 0),
        },
    }
