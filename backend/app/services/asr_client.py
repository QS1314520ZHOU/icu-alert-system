"""ASR client for local FunASR — supports HTTP API and WebSocket protocol."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.config import get_config

logger = logging.getLogger("icu-alert")

DEFAULT_ASR_MODEL = "sensevoice"
DEFAULT_TIMEOUT_SECONDS = 60.0


class ASRRuntimeUnavailableError(RuntimeError):
    pass


def _asr_config() -> tuple[str, str]:
    """Return (base_url, mode) from settings."""
    cfg = get_config()
    url = str(getattr(cfg.settings, "ASR_BASE_URL", "") or "").rstrip("/")
    mode = str(getattr(cfg.settings, "ASR_MODE", "") or "http").strip().lower()
    return url, mode


def _normalize_segments(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_segments = data.get("segments")
    if raw_segments is None:
        raw_segments = data.get("sentence_info")
    if not isinstance(raw_segments, list):
        return []
    return [item for item in raw_segments if isinstance(item, dict)]


def _duration_from(data: dict[str, Any], segments: list[dict[str, Any]]) -> float:
    for key in ("duration", "audio_duration"):
        try:
            value = float(data.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    ends: list[float] = []
    for item in segments:
        for key in ("end", "end_time"):
            try:
                value = float(item.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                ends.append(value)
    return max(ends) if ends else 0.0


# ================================================================
# HTTP mode (OpenAI-compatible /v1/audio/transcriptions)
# ================================================================

async def _transcribe_http(
    base_url: str,
    audio_bytes: bytes,
    *,
    filename: str,
    hotwords: list[str],
    language: str,
) -> dict[str, Any]:
    url = f"{base_url}/v1/audio/transcriptions"
    safe_filename = filename or "rounding_audio.wav"
    files = {"file": (safe_filename, audio_bytes, "application/octet-stream")}
    data = {
        "model": DEFAULT_ASR_MODEL,
        "response_format": "verbose_json",
        "language": language or "zh",
        "hotwords": json.dumps(hotwords or [], ensure_ascii=False),
    }
    timeout = httpx.Timeout(DEFAULT_TIMEOUT_SECONDS, read=DEFAULT_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, data=data, files=files)
        if resp.status_code >= 400:
            logger.error("ASR HTTP error: status=%d url=%s body=%s", resp.status_code, url, resp.text[:500])
        resp.raise_for_status()
        return resp.json()


# ================================================================
# WebSocket mode (FunASR native WS protocol)
# ================================================================

async def _transcribe_ws(
    base_url: str,
    audio_bytes: bytes,
    *,
    hotwords: list[str],
    language: str,
) -> dict[str, Any]:
    """
    FunASR native WebSocket protocol (offline mode).
    ws_url example: ws://10.191.132.139:10095
    """
    import websockets  # pip install websockets

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    if not ws_url.startswith("ws"):
        ws_url = f"ws://{ws_url}"

    result_text = ""
    result_segments: list[dict[str, Any]] = []

    async with websockets.connect(ws_url, ping_interval=None) as ws:
        # 1) Config frame
        config = {
            "mode": "offline",
            "chunk_size": [5, 10, 5],
            "wav_name": "rounding",
            "is_speaking": True,
            "hotwords": "\n".join(hotwords) if hotwords else "",
            "itn": True,
            "language": language or "zh",
        }
        await ws.send(json.dumps(config))

        # 2) Audio data
        await ws.send(audio_bytes)

        # 3) End frame
        await ws.send(json.dumps({"is_speaking": False}))

        # 4) Collect results
        async for message in ws:
            try:
                data = json.loads(message)
            except Exception:
                continue
            text_chunk = str(data.get("text") or "")
            result_text += text_chunk
            # Collect segment info if available
            if "sentence_info" in data:
                for seg in data["sentence_info"]:
                    if isinstance(seg, dict):
                        result_segments.append(seg)
            if data.get("is_final") or data.get("mode") == "offline":
                break

    return {"text": result_text.strip(), "segments": result_segments, "duration": 0.0}


# ================================================================
# Public API
# ================================================================

async def transcribe(
    audio_bytes: bytes,
    *,
    filename: str,
    hotwords: list[str],
    language: str = "zh",
) -> dict[str, Any]:
    """Transcribe audio through local FunASR (auto-selects HTTP or WS mode)."""
    if not audio_bytes:
        raise ValueError("audio_bytes is empty")

    base_url, mode = _asr_config()
    if not base_url:
        raise ASRRuntimeUnavailableError("ASR_BASE_URL is not configured")

    try:
        if mode == "ws":
            logger.info("ASR WS mode: %s", base_url)
            payload = await _transcribe_ws(base_url, audio_bytes, hotwords=hotwords, language=language)
        else:
            logger.info("ASR HTTP mode: %s", base_url)
            payload = await _transcribe_http(base_url, audio_bytes, filename=filename, hotwords=hotwords, language=language)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
        raise ASRRuntimeUnavailableError(f"ASR runtime unavailable: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise ASRRuntimeUnavailableError(f"ASR runtime returned HTTP {status}") from exc
    except Exception as exc:
        raise ASRRuntimeUnavailableError(f"ASR runtime error: {exc}") from exc

    if not isinstance(payload, dict):
        raise ASRRuntimeUnavailableError("ASR runtime returned unexpected payload")

    text = str(payload.get("text") or "").strip()
    segments = _normalize_segments(payload)
    duration = _duration_from(payload, segments)
    return {"text": text, "segments": segments, "duration": duration}


class ASRClient:
    """Backward-compatible wrapper used by the existing voice rounding service."""

    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg or {}
        # mode 优先读 voice_rounding.asr.mode，空则 fallback 到全局 ASR_MODE(.env)
        cfg_mode = str(self.cfg.get("mode") or "").strip().lower()
        if cfg_mode in ("http", "ws", "mock"):
            self.mode = cfg_mode
        else:
            _, global_mode = _asr_config()
            self.mode = global_mode  # "http" or "ws"
        self.hotwords = self._load_hotwords(self.cfg.get("hotword_path"))

    def _load_hotwords(self, path: str | None) -> list[str]:
        if not path:
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception:
            logger.warning("hotword file read failed: %s", path)
            return []

    async def transcribe(self, audio_bytes: bytes, *, sample_rate: int = 16000) -> str:
        if self.mode == "mock":
            logger.info("ASR mock mode: returning test text for %d bytes", len(audio_bytes))
            return "患者今天血压稳定，体温38.5度，心率120次每分，使用去甲肾上腺素0.2微克每公斤每分钟"
        result = await transcribe(
            audio_bytes,
            filename=f"rounding_{sample_rate}.wav",
            hotwords=self.hotwords,
            language=str(self.cfg.get("language") or "zh"),
        )
        return str(result.get("text") or "")
