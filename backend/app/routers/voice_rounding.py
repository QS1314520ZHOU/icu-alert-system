"""语音查房接口。离线上传转写 + 确认入库 + 流式 WS。"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect

from app import runtime
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
from app.services.voice_rounding_stream import VoiceRoundingStreamService
from app.utils.websocket_auth import is_ws_authorized

logger = logging.getLogger("icu-alert")

router = APIRouter(prefix="/api/voice-rounding", tags=["voice-rounding"])


def _service(db: DbDep, config: ConfigDep) -> VoiceRoundingService:
    return VoiceRoundingService(db, config)


def _actor(request: Request, actor: str | None = None) -> str:
    """从请求头或表单字段解析操作人身份。"""
    return normalize_actor(
        actor,
        request.headers.get("x-user-id"),
        request.headers.get("x-actor-id"),
        request.headers.get("x-operator-id"),
    )


@router.post("/{patient_id}/transcribe")
async def transcribe(
    patient_id: str,
    request: Request,
    db: DbDep,
    config: ConfigDep,
    audio: UploadFile = File(...),
):
    """
    上传音频，返回 draft 转写结果。

    音频格式：浏览器 MediaRecorder 产生的 WebM/Opus、OGG/Opus 等。
    服务端会自动转换为 16kHz 单声道 WAV/PCM 后送入 ASR。

    错误码：
    - 400: 音频文件为空或格式无效
    - 403: 语音查房未启用
    - 413: 文件过大或时长过长
    - 422: 无法解码音频
    - 503: ASR 或 FFmpeg 服务不可用
    - 504: 处理超时
    - 500: 未知内部错误
    """
    svc = _service(db, config)
    if not bool(svc.cfg.get("enabled", True)):
        raise HTTPException(403, "语音查房未启用")

    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or ""

    try:
        draft = await svc.transcribe(
            patient_id,
            audio_bytes,
            filename=filename,
            content_type=content_type,
        )
    except AudioEmptyError as exc:
        raise HTTPException(400, str(exc))
    except AudioTooLargeError as exc:
        raise HTTPException(413, str(exc))
    except AudioTooLongError as exc:
        raise HTTPException(413, str(exc))
    except AudioInvalidError as exc:
        raise HTTPException(422, str(exc))
    except FFmpegUnavailableError as exc:
        raise HTTPException(503, str(exc))
    except FFmpegTimeoutError as exc:
        raise HTTPException(504, str(exc))
    except AudioPreprocessError as exc:
        raise HTTPException(exc.status_code, str(exc))
    except ASREmptyTranscriptionError as exc:
        logger.warning("ASR 返回空文本: patient_id=%s, %s", patient_id, exc)
        raise HTTPException(422, str(exc))
    except ASRRuntimeUnavailableError as exc:
        logger.warning("ASR 不可用: patient_id=%s, %s", patient_id, exc)
        raise HTTPException(503, f"语音识别服务不可用: {exc}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        logger.exception("语音转写失败: patient_id=%s", patient_id)
        raise HTTPException(500, "语音转写服务异常，请稍后重试")

    # 审计日志（不阻断主流程）
    try:
        actor = _actor(request)
        await write_audit_log(
            db,
            action="voice_rounding_transcribe",
            module="voice_rounding",
            actor=actor,
            target_type="voice_draft",
            target_id=str(draft.get("_id", "")),
            detail={
                "patient_id": str(patient_id),
                "duration_seconds": draft.get("duration_seconds", 0),
                "needs_human_review": draft.get("needs_human_review", False),
                "degraded": draft.get("degraded", False),
                "suspect_count": len(draft.get("suspect") or []),
            },
        )
    except Exception:
        logger.debug("审计日志写入失败（不阻断主流程）")

    return draft


@router.post("/{patient_id}/confirm")
async def confirm(
    patient_id: str,
    request: Request,
    db: DbDep,
    config: ConfigDep,
    final_text: str = Form(...),
    draft_id: str = Form(""),
    actor: str = Form(""),
):
    """
    医生确认后入库为正式查房记录。

    错误码：
    - 400: 确认文本为空
    - 500: 入库失败
    """
    if not final_text.strip():
        raise HTTPException(400, "确认文本不能为空")

    # 优先从认证上下文解析 actor，表单字段仅作 fallback
    resolved_actor = _actor(request, actor if actor else None)

    svc = _service(db, config)

    # 校验 draft 状态
    if draft_id:
        try:
            from bson import ObjectId
            draft_doc = await db.col("voice_rounding_drafts").find_one(
                {"_id": ObjectId(draft_id)}
            )
            if draft_doc and draft_doc.get("status") != "draft":
                raise HTTPException(400, "该草稿已确认或已废弃，不能重复确认")
        except HTTPException:
            raise
        except Exception:
            pass  # draft_id 格式错误等，不阻断

    result = await svc.confirm(
        patient_id,
        final_text=final_text,
        draft_id=draft_id,
        actor=resolved_actor,
    )

    # 审计日志
    try:
        await write_audit_log(
            db,
            action="voice_rounding_confirm",
            module="voice_rounding",
            actor=resolved_actor,
            target_type="voice_record",
            target_id=str(result.get("_id", "")),
            detail={
                "patient_id": str(patient_id),
                "draft_id": draft_id,
                "text_length": len(final_text),
            },
        )
    except Exception:
        logger.debug("审计日志写入失败（不阻断主流程）")

    return result


# ---------- 流式 2pass WebSocket ----------

# ── PCM frame validation ─────────────────────────────────────────────────
_MAX_SINGLE_FRAME_BYTES = 64 * 1024       # 64 KB
_MAX_TOTAL_AUDIO_BYTES = 16000 * 2 * 600  # ~19.2 MB (10 min)
_START_TIMEOUT_SEC = 5.0
_FINAL_WAIT_TIMEOUT = 30.0


def _validate_pcm_frame(chunk: bytes, total_bytes: int, stopped: bool) -> None:
    if stopped:
        raise ValueError("已 stop，拒绝接收 PCM")
    if len(chunk) == 0:
        raise ValueError("空 PCM 帧")
    if len(chunk) % 2 != 0:
        raise ValueError(f"PCM 帧长度不是 2 的倍数: {len(chunk)}")
    if len(chunk) > _MAX_SINGLE_FRAME_BYTES:
        raise ValueError(f"PCM 帧过大: {len(chunk)} > {_MAX_SINGLE_FRAME_BYTES}")
    if total_bytes + len(chunk) > _MAX_TOTAL_AUDIO_BYTES:
        raise ValueError("累计音频超限")


@router.websocket("/ws/voice-rounding/{patient_id}")
async def ws_voice_rounding_stream(ws: WebSocket, patient_id: str):
    """流式语音查房 WebSocket — FunASR 2pass 实时识别。"""
    # 1) Auth
    if not is_ws_authorized(ws):
        await ws.close(code=4001, reason="Unauthorized")
        return

    if not _is_2pass_enabled():
        await ws.accept()
        await ws.send_json({"type": "error", "code": "asr_2pass_disabled",
                            "message": "流式模式未启用"})
        await ws.close()
        return

    await ws.accept()
    await ws.send_json({"type": "connected", "session_id": ""})

    stream_svc: VoiceRoundingStreamService | None = None
    send_task: asyncio.Task | None = None
    recv_task: asyncio.Task | None = None
    pending_messages: list[dict] = []
    total_audio_bytes = 0
    stopped = False

    try:
        # 2) Wait for start message (with timeout)
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=_START_TIMEOUT_SEC)
            start_msg = json.loads(raw)
        except asyncio.TimeoutError:
            await ws.send_json({"type": "error", "code": "start_timeout",
                                "message": "等待 start 消息超时"})
            return
        except WebSocketDisconnect:
            return

        if start_msg.get("type") != "start":
            await ws.send_json({"type": "error", "code": "bad_message",
                                "message": "首条消息必须是 start"})
            return

        # Validate patient_id
        req_patient = str(start_msg.get("patient_id", ""))
        if req_patient and req_patient != patient_id:
            logger.warning("patient_id mismatch: ws=%s start=%s", patient_id, req_patient)

        # Validate audio params — only 16000 Hz mono s16le is accepted
        req_sr = int(start_msg.get("sample_rate", 0))
        req_ch = int(start_msg.get("channels", 0))
        if req_sr != 0 and req_sr != 16000:
            await ws.send_json({"type": "error", "code": "bad_sample_rate",
                                "message": f"仅支持 16000 Hz，收到 {req_sr}"})
            return
        if req_ch != 0 and req_ch != 1:
            await ws.send_json({"type": "error", "code": "bad_channels",
                                "message": f"仅支持单声道，收到 {req_ch} 声道"})
            return

        # 3) Create streaming service and connect to FunASR
        stream_svc = VoiceRoundingStreamService(
            runtime.db, runtime.config, patient_id
        )
        await stream_svc.start()
        await ws.send_json({"type": "ready", "session_id": stream_svc.session_id,
                            "sample_rate": 16000})

        # 4) Background task: push partial/final/error messages from service → WS
        async def _push_loop():
            while not stopped:
                try:
                    await asyncio.wait_for(stream_svc._partial_updated.wait(), timeout=0.5)
                    await ws.send_json({"type": "partial",
                                        "text": stream_svc.partial_text,
                                        "start_ms": None, "end_ms": None})
                except asyncio.TimeoutError:
                    pass
                try:
                    await asyncio.wait_for(stream_svc._final_updated.wait(), timeout=0.1)
                    segs = stream_svc.final_segments
                    if segs:
                        latest = segs[-1]
                        await ws.send_json({"type": "final_segment",
                                            "text": latest.get("text", ""),
                                            "start_ms": latest.get("start_ms"),
                                            "end_ms": latest.get("end_ms"),
                                            "segments": latest.get("segments", [])})
                except asyncio.TimeoutError:
                    pass
                try:
                    await asyncio.wait_for(stream_svc._error_occurred.wait(), timeout=0.1)
                    msg = stream_svc.error_message
                    await ws.send_json({"type": "error", "code": "asr_error",
                                        "message": msg})
                    return
                except asyncio.TimeoutError:
                    pass

        send_task = asyncio.create_task(_push_loop())

        # 5) Main receive loop — binary PCM + JSON control messages
        while True:
            raw = await ws.receive()

            if "text" in raw:
                # JSON control message
                msg = json.loads(raw["text"])
                msg_type = msg.get("type", "")

                if msg_type == "stop":
                    stopped = True
                    await ws.send_json({"type": "stopped"})
                    break
                elif msg_type == "cancel":
                    await stream_svc.cancel()
                    return
                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                else:
                    logger.debug("unknown WS message type: %s", msg_type)

            elif "bytes" in raw:
                # Binary PCM frame
                chunk = raw["bytes"]
                try:
                    _validate_pcm_frame(chunk, total_audio_bytes, stopped)
                except ValueError as exc:
                    await ws.send_json({"type": "error", "code": "protocol_error",
                                        "message": str(exc)})
                    break
                total_audio_bytes += len(chunk)
                await stream_svc.send_pcm(chunk)

        # 6) Stop → final pipeline → completed
        if stopped and stream_svc is not None:
            try:
                draft = await stream_svc.stop()
                await ws.send_json({"type": "completed", "draft": _serializable_draft(draft)})
            except ASREmptyTranscriptionError:
                await ws.send_json({"type": "error", "code": "empty_transcription",
                                    "message": "未识别到有效语音内容"})
            except ASRRuntimeUnavailableError as exc:
                await ws.send_json({"type": "error", "code": "asr_unavailable",
                                    "message": str(exc)})

    except WebSocketDisconnect:
        logger.debug("voice-rounding WS 客户端断开: patient=%s", patient_id)
        if stream_svc:
            await stream_svc.cancel()
    except Exception:
        logger.exception("voice-rounding WS 异常: patient=%s", patient_id)
        if stream_svc:
            await stream_svc.cancel()
        try:
            await ws.send_json({"type": "error", "code": "internal_error",
                                "message": "服务内部异常"})
        except Exception:
            pass
    finally:
        for task in (send_task, recv_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def _is_2pass_enabled() -> bool:
    """Check whether the 2pass streaming mode is enabled."""
    try:
        if runtime.config is None:
            return False
        enabled = getattr(runtime.config.settings, "ASR_2PASS_ENABLED", False)
        return bool(enabled)
    except Exception:
        return False


def _serializable_draft(draft: dict) -> dict:
    """Ensure draft is JSON-serializable (BSON ObjectId → str, datetime → str)."""
    out: dict = {}
    for k, v in draft.items():
        if k == "_id":
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, bytes):
            out[k] = v.decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


# ---------- Capabilities ----------

@router.get("/capabilities")
async def capabilities():
    """Return voice-rounding capabilities for the frontend to decide UI mode."""
    return {
        "streaming_enabled": _is_2pass_enabled(),
        "offline_enabled": True,
        "max_session_seconds": 600,
        "supported_sample_rates": [16000],
    }
