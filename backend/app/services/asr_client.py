"""ASR client for local FunASR OpenAI-compatible transcription service."""
from __future__ import annotations

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


def _asr_base_url() -> str:
    cfg = get_config()
    return str(getattr(cfg.settings, "ASR_BASE_URL", "") or "").rstrip("/")


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


async def transcribe(
    audio_bytes: bytes,
    *,
    filename: str,
    hotwords: list[str],
    language: str = "zh",
) -> dict[str, Any]:
    """Transcribe audio through local FunASR's OpenAI-compatible API."""
    if not audio_bytes:
        raise ValueError("audio_bytes is empty")

    base_url = _asr_base_url()
    if not base_url:
        raise ASRRuntimeUnavailableError("ASR_BASE_URL is not configured")

    url = f"{base_url}/v1/audio/transcriptions"
    safe_filename = filename or "rounding_audio.wav"
    files = {
        "file": (safe_filename, audio_bytes, "application/octet-stream"),
    }
    data = {
        "model": DEFAULT_ASR_MODEL,
        "response_format": "verbose_json",
        "language": language or "zh",
        "hotwords": json.dumps(hotwords or [], ensure_ascii=False),
    }
    timeout = httpx.Timeout(DEFAULT_TIMEOUT_SECONDS, read=DEFAULT_TIMEOUT_SECONDS)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, data=data, files=files)
            if resp.status_code >= 400:
                logger.error("ASR API error: status=%d url=%s body=%s", resp.status_code, url, resp.text[:500])
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
        raise ASRRuntimeUnavailableError(f"ASR runtime unavailable: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise ASRRuntimeUnavailableError(f"ASR runtime returned HTTP {status}") from exc
    except ValueError as exc:
        raise ASRRuntimeUnavailableError("ASR runtime returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ASRRuntimeUnavailableError("ASR runtime returned unexpected payload")

    text = str(payload.get("text") or "").strip()
    segments = _normalize_segments(payload)
    duration = _duration_from(payload, segments)
    return {
        "text": text,
        "segments": segments,
        "duration": duration,
    }


class ASRClient:
    """Backward-compatible wrapper used by the existing voice rounding service."""

    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg or {}
        self.mode = str(self.cfg.get("mode") or "funasr_openai")
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
