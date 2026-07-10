"""ASR client for local FunASR — supports HTTP API and WebSocket protocol."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

from app.config import get_config

logger = logging.getLogger("icu-alert")

DEFAULT_ASR_MODEL = "sensevoice"
DEFAULT_TIMEOUT_SECONDS = 60.0


class ASRRuntimeUnavailableError(RuntimeError):
    """ASR 服务不可用（连接失败、超时、返回错误等）。"""
    pass


class ASREmptyTranscriptionError(RuntimeError):
    """ASR 返回空文本（is_final=true 但 text 为空）。"""
    pass


@dataclass(frozen=True)
class ASRInput:
    """
    ASR 输入：明确区分不同音频格式。

    - wav_bytes: 标准 WAV 容器（含 44 字节头），HTTP 模式使用
    - pcm_bytes: raw PCM (signed 16-bit LE, mono, 16kHz)，WS 模式使用
    - source_format: 源格式标识（仅用于日志）
    """
    wav_bytes: bytes = b""
    pcm_bytes: bytes = b""
    source_format: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.wav_bytes and not self.pcm_bytes


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
    normalized: list[dict[str, Any]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        # 统一字段名：start_time/end_time → start_ms/end_ms
        seg: dict[str, Any] = {}
        for key in ("text", "speaker"):
            if key in item:
                seg[key] = item[key]
        # 时间戳归一化为毫秒
        for src, dst in (("start", "start_ms"), ("start_time", "start_ms"),
                         ("end", "end_ms"), ("end_time", "end_ms")):
            if src in item:
                try:
                    val = float(item[src])
                    # FunASR 返回秒，转毫秒
                    seg[dst] = int(val * 1000) if val < 10000 else int(val)
                except (TypeError, ValueError):
                    pass
        # confidence
        if "confidence" in item:
            try:
                seg["confidence"] = float(item["confidence"])
            except (TypeError, ValueError):
                pass
        # speaker_id 保留 null（本阶段不做说话人推断）
        seg.setdefault("speaker_id", None)
        normalized.append(seg)
    return normalized


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
        for key in ("end_ms", "end", "end_time"):
            try:
                value = float(item.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                # 如果是毫秒，转回秒
                ends.append(value / 1000 if value > 10000 else value)
    return max(ends) if ends else 0.0


# ================================================================
# HTTP mode (OpenAI-compatible /v1/audio/transcriptions)
# ================================================================

async def _transcribe_http(
    base_url: str,
    wav_bytes: bytes,
    *,
    hotwords: list[str],
    language: str,
) -> dict[str, Any]:
    """
    HTTP 模式：发送标准 16kHz 单声道 WAV 到 FunASR OpenAI 兼容端点。
    wav_bytes 必须是含 44 字节头的标准 WAV。
    """
    url = f"{base_url}/v1/audio/transcriptions"
    files = {"file": ("rounding.wav", wav_bytes, "audio/wav")}
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
    pcm_bytes: bytes,
    *,
    hotwords: list[str],
    language: str,
) -> dict[str, Any]:
    """
    FunASR native WebSocket protocol (offline mode)。
    必须发送 raw PCM (signed 16-bit LE, mono, 16kHz)。
    不得发送 WAV 文件头或 WebM 字节。

    协议要点（参考 FunASR 官方 Python 客户端）：
    1. 首帧：JSON 配置（mode, wav_format, audio_fs, chunk_size, hotwords 等）
    2. 音频帧：按 chunk_size 分块发送 PCM 二进制帧
    3. 结束帧：{"is_speaking": false}
    4. 接收：只在 is_final==true 时结束，不因 mode=="offline" 提前退出
    """
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    if not ws_url.startswith("ws"):
        ws_url = f"ws://{ws_url}"

    # FunASR chunk_size: [stride_ms/60, encoder_look_back, decoder_look_back]
    # chunk_interval: 分片发送参数，影响 stride 和 sleep 计算（非简单毫秒值）
    # 参考 FunASR 官方 funasr_wss_client.py 的 send_stride 逻辑
    chunk_size = [5, 10, 5]
    chunk_interval = 10  # 用于 stride 公式的分母，非直接毫秒值

    # stride = 60 × chunk_size[1] / chunk_interval / 1000 × sample_rate × 2
    #        = 60 × 10 / 10 / 1000 × 16000 × 2 = 1920 bytes (60ms audio)
    stride = int(60 * chunk_size[1] / chunk_interval / 1000 * 16000 * 2)

    # offline 模式：sleep 仅 0.001s（极短 yield，不模拟实时节奏）
    # 2pass/online 模式：sleep = 60 × chunk_size[1] / chunk_interval / 1000 = 0.06s
    sleep_duration = 0.001  # offline mode
    ws_recv_timeout = DEFAULT_TIMEOUT_SECONDS

    result_text = ""
    result_segments: list[dict[str, Any]] = []
    got_final = False

    async with websockets.connect(ws_url, ping_interval=None) as ws:
        # 1) Config frame — FunASR 离线模式协议完整配置
        config = {
            "mode": "offline",
            "chunk_size": chunk_size,
            "chunk_interval": chunk_interval,
            "wav_name": "rounding",
            "is_speaking": True,
            "wav_format": "pcm",
            "audio_fs": 16000,
            "hotwords": "\n".join(hotwords) if hotwords else "",
            "itn": True,
            "language": language or "zh",
            "encoder_chunk_look_back": 4,
            "decoder_chunk_look_back": 0,
        }
        await ws.send(json.dumps(config))

        # 2) Audio data — 按 stride 分块发送 PCM
        #    参考 FunASR 官方 funasr_wss_client.py 的 send_stride 逻辑
        #    offline 模式：sleep 仅 0.001s，不做实时节奏模拟
        audio_len = len(pcm_bytes)
        for beg in range(0, audio_len, stride):
            end = min(beg + stride, audio_len)
            chunk = pcm_bytes[beg:end]
            if chunk:
                await ws.send(chunk)
                await asyncio.sleep(sleep_duration)

        # 3) End frame — 通知服务端音频发送完毕
        await ws.send(json.dumps({"is_speaking": False}))

        # 4) Collect results — 只在 is_final==true 时结束
        #    离线模式下 FunASR 可能先发空文本中间帧，再发最终结果
        #    使用 asyncio.wait_for 给每条消息增加接收超时
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=ws_recv_timeout)
                except asyncio.TimeoutError:
                    raise ASRRuntimeUnavailableError(
                        f"ASR WebSocket 接收超时 ({ws_recv_timeout}s)，服务端未返回识别结果"
                    )
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                # 禁止因 mode=="offline" 结束接收，只看 is_final
                text_chunk = str(data.get("text") or "")
                # Collect segment info if available
                if "sentence_info" in data:
                    for seg in data["sentence_info"]:
                        if isinstance(seg, dict):
                            result_segments.append(seg)
                if data.get("is_final"):
                    # is_final==true：离线识别最终结果，结束接收循环
                    result_text += text_chunk
                    got_final = True
                    break
                # 非 final 消息：忽略 text 为空的中间帧，只累积有内容的
                if text_chunk:
                    result_text += text_chunk
        except asyncio.TimeoutError:
            raise ASRRuntimeUnavailableError(
                f"ASR WebSocket 接收超时 ({ws_recv_timeout}s)，服务端未返回识别结果"
            )

    if not got_final:
        raise ASRRuntimeUnavailableError(
            "ASR WebSocket 连接关闭但未收到 is_final=true，服务端可能异常"
        )

    return {"text": result_text.strip(), "segments": result_segments, "duration": 0.0}


# ================================================================
# Public API
# ================================================================

async def transcribe(
    wav_bytes: bytes = b"",
    pcm_bytes: bytes = b"",
    *,
    filename: str = "rounding.wav",
    hotwords: list[str] | None = None,
    language: str = "zh",
    source_format: str = "",
) -> dict[str, Any]:
    """
    通过本地 FunASR 转写音频（自动选择 HTTP 或 WS 模式）。

    参数：
        wav_bytes: 标准 WAV 字节（HTTP 模式使用）
        pcm_bytes: raw PCM 字节（WS 模式使用）
        filename: 文件名（仅 HTTP 模式使用）
        hotwords: 热词列表
        language: 语言代码
        source_format: 源格式标识（仅日志）

    返回：
        {"text": str, "segments": list, "duration": float}
    """
    if not wav_bytes and not pcm_bytes:
        raise ValueError("wav_bytes 和 pcm_bytes 不能同时为空")

    base_url, mode = _asr_config()
    if not base_url:
        raise ASRRuntimeUnavailableError("ASR_BASE_URL 未配置")

    hotwords = hotwords or []

    try:
        if mode == "ws":
            if not pcm_bytes:
                raise ASRRuntimeUnavailableError("WebSocket 模式需要 pcm_bytes，但未提供")
            logger.info("ASR WS mode: %s, pcm=%d bytes, source=%s", base_url, len(pcm_bytes), source_format)
            payload = await _transcribe_ws(base_url, pcm_bytes, hotwords=hotwords, language=language)
        else:
            if not wav_bytes:
                raise ASRRuntimeUnavailableError("HTTP 模式需要 wav_bytes，但未提供")
            logger.info("ASR HTTP mode: %s, wav=%d bytes, source=%s", base_url, len(wav_bytes), source_format)
            payload = await _transcribe_http(base_url, wav_bytes, hotwords=hotwords, language=language)
    except ASRRuntimeUnavailableError:
        raise
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
        raise ASRRuntimeUnavailableError(f"ASR 服务连接失败: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise ASRRuntimeUnavailableError(f"ASR 服务返回错误 HTTP {status}") from exc
    except Exception as exc:
        raise ASRRuntimeUnavailableError(f"ASR 服务异常: {exc}") from exc

    if not isinstance(payload, dict):
        raise ASRRuntimeUnavailableError("ASR 服务返回了意外的响应格式")

    text = str(payload.get("text") or "").strip()
    segments = _normalize_segments(payload)
    duration = _duration_from(payload, segments)

    if not text:
        logger.warning("ASR 返回空文本, source=%s", source_format)
        raise ASREmptyTranscriptionError("ASR 未返回有效文本（识别结果为空）")

    return {"text": text, "segments": segments, "duration": duration}


class ASRClient:
    """
    向后兼容的 ASR 客户端包装器。
    供 VoiceRoundingService 使用。
    """

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
            logger.warning("热词文件读取失败: %s", path)
            return []

    async def transcribe(
        self,
        wav_bytes: bytes = b"",
        pcm_bytes: bytes = b"",
        *,
        sample_rate: int = 16000,
        source_format: str = "",
    ) -> str:
        """
        转写音频，返回文本。

        参数：
            wav_bytes: 标准 WAV 字节（HTTP 模式使用）
            pcm_bytes: raw PCM 字节（WS 模式使用）
            sample_rate: 采样率（仅用于日志和文件名）
            source_format: 源格式标识（仅日志）

        注意：
            旧调用方式 `transcribe(audio_bytes)` 仍然兼容，
            但建议使用 preprocess_audio() 后传入 wav_bytes/pcm_bytes。
        """
        if self.mode == "mock":
            logger.info("ASR mock mode: returning test text, wav=%d pcm=%d", len(wav_bytes), len(pcm_bytes))
            return "患者今天血压稳定，体温38.5度，心率120次每分，使用去甲肾上腺素0.2微克每公斤每分钟"

        # 向后兼容：如果只传了旧的 audio_bytes 参数（通过位置参数）
        # 本版本中 wav_bytes/pcm_bytes 都是 keyword-only，
        # 如果旧代码传了位置参数，它会落在 wav_bytes 上
        result = await transcribe(
            wav_bytes=wav_bytes,
            pcm_bytes=pcm_bytes,
            filename=f"rounding_{sample_rate}.wav",
            hotwords=self.hotwords,
            language=str(self.cfg.get("language") or "zh"),
            source_format=source_format,
        )
        return str(result.get("text") or "")
