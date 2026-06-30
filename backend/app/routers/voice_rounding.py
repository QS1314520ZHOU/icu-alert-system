"""语音查房接口。第一版：离线上传转写 + 确认入库。流式 WS 预留。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from app.runtime import ConfigDep, DbDep
from app.services.voice_rounding import VoiceRoundingService
from app.utils.websocket_auth import is_ws_authorized

logger = logging.getLogger("icu-alert")

router = APIRouter(prefix="/api/voice-rounding", tags=["voice-rounding"])


def _service(db: DbDep, config: ConfigDep) -> VoiceRoundingService:
    return VoiceRoundingService(db, config)


@router.post("/{patient_id}/transcribe")
async def transcribe(
    patient_id: str,
    db: DbDep,
    config: ConfigDep,
    audio: UploadFile = File(...),
):
    """
    上传音频，返回 draft 转写结果。
    音频格式：浏览器 MediaRecorder 默认 webm/opus，需在 service 层转码为 PCM 后喂 ASR。
    """
    svc = _service(db, config)
    if not bool(svc.cfg.get("enabled", True)):
        raise HTTPException(403, "语音查房未启用")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "音频文件为空")

    try:
        draft = await svc.transcribe(patient_id, audio_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("语音转写失败")
        raise HTTPException(500, "语音转写服务异常")
    return draft


@router.post("/{patient_id}/confirm")
async def confirm(
    patient_id: str,
    db: DbDep,
    config: ConfigDep,
    final_text: str = Form(...),
    draft_id: str = Form(""),
    actor: str = Form(""),
):
    """医生确认后入库为正式查房记录。"""
    if not final_text.strip():
        raise HTTPException(400, "确认文本不能为空")

    svc = _service(db, config)
    return await svc.confirm(
        patient_id,
        final_text=final_text,
        draft_id=draft_id,
        actor=actor,
    )


# ---------- WebSocket 占位（第二版流式预留） ----------

@router.websocket("/ws/voice-rounding")
async def ws_voice_rounding(ws: WebSocket):
    """
    第二版流式 ASR 预留端点。
    本版仅接受连接并返回占位消息，后续版本将支持：
    - 实时音频流上传
    - 流式 ASR 中间结果推送
    - 实时填充词过滤
    """
    if not is_ws_authorized(ws):
        await ws.close(code=4001, reason="Unauthorized")
        return
    await ws.accept()
    try:
        await ws.send_json({
            "type": "info",
            "message": "语音查房流式模式将在第二版支持，当前请使用离线上传接口",
        })
        while True:
            data = await ws.receive_text()
            await ws.send_json({
                "type": "error",
                "message": "流式模式尚未实现，请使用 POST /api/voice-rounding/{patient_id}/transcribe",
            })
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("voice-rounding WS 异常断开")
