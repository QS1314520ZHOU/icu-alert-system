"""Streaming ASR session — FunASR 2pass WebSocket connection manager.

Manages a single FunASR WebSocket connection in 2pass mode per voice-rounding
session.  Responsibilities:
- Open WS to FunASR, send mode=2pass config frame
- Pass-through PCM chunks from browser at real-time pace (no artificial sleep)
- Receive and dispatch 2pass-online (partial) and 2pass-offline (final_segment) messages
- stop_marker race protection: only the response matching the unique wav_name
  sent in the stop frame completes stop_final_future
- No per-message receive timeout during recording — only stop_final_future has a timeout
- Ping/pong liveness detection via websockets protocol ping
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from app.services.asr_client import (
    ASREmptyTranscriptionError,
    ASRRuntimeUnavailableError,
    DEFAULT_TIMEOUT_SECONDS,
)

logger = logging.getLogger("icu-alert")

# ── FunASR 2pass constants ────────────────────────────────────────────────
CHUNK_SIZE = [5, 10, 5]          # [stride_ms/60, encoder_look_back, decoder_look_back]
CHUNK_INTERVAL = 10              # stride 公式分母
STRIDE_BYTES = int(60 * CHUNK_SIZE[1] / CHUNK_INTERVAL / 1000 * 16000 * 2)  # 1920
PING_INTERVAL_SEC = 30
PONG_TIMEOUT_SEC = 10


# ── Callback types ─────────────────────────────────────────────────────────
OnPartial = Callable[[str, Any, Any], Awaitable[None]]
"""Called with (text: str, start_ms: int|None, end_ms: int|None)."""

OnFinalSegment = Callable[[str, list[dict], Any, Any], Awaitable[None]]
"""Called with (text, segments, start_ms, end_ms)."""

OnError = Callable[[str], Awaitable[None]]
"""Called with (message: str)."""


# ── StreamingASRSession ────────────────────────────────────────────────────

class StreamingASRSession:
    """Manages one FunASR 2pass WebSocket connection for a streaming session."""

    def __init__(
        self,
        base_url: str,
        *,
        hotwords: list[str] | None = None,
        language: str = "zh",
    ) -> None:
        ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        if not ws_url.startswith("ws"):
            ws_url = f"ws://{ws_url}"
        self._ws_url = ws_url
        self._hotwords = hotwords or []
        self._language = language or "zh"
        self._session_id = uuid.uuid4().hex[:12]

        # Connection state
        self._ws: ClientConnection | None = None
        self._ws_ctx = None            # async context manager handle
        self._closed = False
        self._recv_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None

        # Stop / finalisation state
        self._stop_sent = False
        self._stop_marker: str | None = None
        self._stop_final_future: asyncio.Future | None = None

        # Callbacks — set by owner before open()
        self.on_partial: OnPartial | None = None
        self.on_final_segment: OnFinalSegment | None = None
        self.on_error: OnError | None = None

        # Stats
        self.total_pcm_bytes_sent = 0

    # ── Public API ──────────────────────────────────────────────────────

    async def open(self) -> None:
        """Connect to FunASR, send the 2pass config frame, start background tasks."""
        # websockets 14.x: connect() returns a ClientConnection (async context manager),
        # not a coroutine.  Use manual __aenter__ to enter the context.
        self._ws_ctx = websockets.connect(self._ws_url, ping_interval=None)
        self._ws = await self._ws_ctx.__aenter__()

        config = {
            "mode": "2pass",
            "chunk_size": CHUNK_SIZE,
            "chunk_interval": CHUNK_INTERVAL,
            "wav_name": self._session_id,
            "is_speaking": True,
            "wav_format": "pcm",
            "audio_fs": 16000,
            "hotwords": "\n".join(self._hotwords) if self._hotwords else "",
            "itn": True,
            "language": self._language,
            "encoder_chunk_look_back": 4,
            "decoder_chunk_look_back": 0,
        }
        await self._ws.send(json.dumps(config))

        self._recv_task = asyncio.create_task(self._recv_loop())
        self._ping_task = asyncio.create_task(self._ping_loop())

    async def send_pcm(self, chunk: bytes) -> None:
        """Forward a PCM chunk to FunASR immediately — no artificial sleep."""
        if self._closed or self._ws is None:
            return
        await self._ws.send(chunk)
        self.total_pcm_bytes_sent += len(chunk)

    async def send_stop(self) -> None:
        """Send the stop frame with a unique wav_name marker.

        Creates stop_final_future — call wait_final() to await the matching
        offline response.
        """
        self._stop_sent = True
        self._stop_marker = f"{self._session_id}-stop-{uuid.uuid4().hex[:8]}"
        self._stop_final_future = asyncio.get_event_loop().create_future()
        await self._ws.send(json.dumps({
            "wav_name": self._stop_marker,
            "is_speaking": False,
        }))

    async def wait_final(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Block until the stop_marker offline response arrives."""
        if self._stop_final_future is None:
            raise ASRRuntimeUnavailableError("send_stop() 未被调用")
        await asyncio.wait_for(self._stop_final_future, timeout=timeout)

    async def close(self) -> None:
        """Clean shutdown — cancel tasks, close FunASR WS."""
        self._closed = True
        for task in (self._ping_task, self._recv_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._ws_ctx is not None:
            try:
                await self._ws_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._ws = None
            self._ws_ctx = None

    # ── Background loops ────────────────────────────────────────────────

    async def _recv_loop(self) -> None:
        """Receive messages from FunASR — no per-message timeout.

        Dispatches 2pass-online → on_partial, 2pass-offline → on_final_segment.
        stop_final_future is completed only when the response's wav_name matches
        the stop_marker (or, as fallback, the first is_final offline after stop
        when FunASR doesn't echo wav_name).
        """
        try:
            while not self._closed:
                try:
                    raw = await self._ws.recv()  # no timeout — wait forever
                except (ConnectionClosed, StopAsyncIteration):
                    if not self._stop_sent:
                        await self._dispatch_error("FunASR 连接意外关闭")
                    break

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                mode = str(data.get("mode") or "")
                text = str(data.get("text") or "").strip()
                is_final = bool(data.get("is_final"))
                wav_name = str(data.get("wav_name") or "")

                if mode == "2pass-online":
                    # Partial / interim result — relay immediately
                    if text and self.on_partial:
                        start_ms = _normalize_timestamp(data.get("start"), "start")
                        end_ms = _normalize_timestamp(data.get("end"), "end")
                        await self.on_partial(text, start_ms, end_ms)

                elif mode == "2pass-offline":
                    # All non-empty offline messages are final segments
                    segs = _normalize_segments_ws(data)
                    start_ms = _normalize_timestamp(data.get("start"), "start")
                    end_ms = _normalize_timestamp(data.get("end"), "end")
                    if text and self.on_final_segment:
                        await self.on_final_segment(text, segs, start_ms, end_ms)

                    # ── Stop marker matching ──────────────────────────
                    if (self._stop_sent
                            and self._stop_final_future
                            and not self._stop_final_future.done()
                            and is_final is True):
                        if wav_name and wav_name == self._stop_marker:
                            # Exact match — reliable completion
                            self._stop_final_future.set_result(True)
                            break
                        elif not wav_name:
                            # FunASR doesn't echo wav_name — fallback to first
                            # is_final offline after stop
                            logger.warning(
                                "FunASR 未回传 wav_name，使用第一条 stop 后 "
                                "is_final 作为结束（可能不准确）"
                            )
                            self._stop_final_future.set_result(True)
                            break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("_recv_loop 异常")
            await self._dispatch_error("ASR 接收异常")

    async def _ping_loop(self) -> None:
        """Send protocol ping every PING_INTERVAL_SEC.  Timeout = connection dead."""
        while not self._closed:
            await asyncio.sleep(PING_INTERVAL_SEC)
            if self._closed or self._ws is None:
                break
            try:
                pong_waiter = await self._ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=PONG_TIMEOUT_SEC)
            except asyncio.CancelledError:
                break
            except (asyncio.TimeoutError, ConnectionClosed):
                await self._dispatch_error("FunASR 连接无响应 (ping 超时)")
                break
            except Exception:
                logger.exception("ping 异常")
                break

    async def _dispatch_error(self, message: str) -> None:
        """Safely dispatch an error to the owner callback."""
        logger.warning("StreamingASRSession error: %s", message)
        if self.on_error:
            try:
                await self.on_error(message)
            except Exception:
                logger.exception("on_error 回调异常")


# ── Shared helpers (keep in sync with asr_client._normalize_segments) ───────

def _normalize_timestamp(value: Any, _field_name: str) -> int | None:
    """Convert a FunASR WebSocket timestamp to milliseconds.

    Per FunASR WS protocol, start / end fields are milliseconds.
    No heuristic conversion — if untrusted, return None.
    """
    if value is None:
        return None
    try:
        ms = int(float(value))
    except (TypeError, ValueError):
        return None
    return ms if ms >= 0 else None


def _normalize_segments_ws(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize FunASR sentence_info segments to a standard shape.

    Unlike asr_client._normalize_segments (used for HTTP mode which returns
    seconds), this function trusts the WS protocol and treats timestamps as
    milliseconds directly.
    """
    raw_segments = data.get("sentence_info") or data.get("segments")
    if not isinstance(raw_segments, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        seg: dict[str, Any] = {}
        if "text" in item:
            seg["text"] = item["text"]
        if "speaker" in item:
            seg["speaker"] = item["speaker"]
        seg.setdefault("speaker_id", None)

        # Timestamps — WS protocol uses milliseconds
        for src, dst in (("start", "start_ms"), ("end", "end_ms")):
            val = item.get(src)
            if val is not None:
                try:
                    seg[dst] = int(float(val))
                except (TypeError, ValueError):
                    pass

        if "confidence" in item:
            try:
                seg["confidence"] = float(item["confidence"])
            except (TypeError, ValueError):
                pass

        normalized.append(seg)
    return normalized
