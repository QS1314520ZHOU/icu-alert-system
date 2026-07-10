"""
音频预处理器：将浏览器上传的 WebM/Opus 等格式统一转换为 16kHz 单声道 WAV/PCM。

职责单一：只做格式转换和基础校验，不涉及 ASR 调用或业务逻辑。
所有 FFmpeg 调用使用 asyncio.create_subprocess_exec，禁止 shell=True。
"""
from __future__ import annotations

import asyncio
import logging
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("icu-alert")

# 默认限制
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_DURATION_SECONDS = 300  # 5 分钟
DEFAULT_FFMPEG_TIMEOUT_SECONDS = 60

# 目标格式
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # 16-bit


@dataclass(frozen=True)
class AudioPreprocessResult:
    """音频预处理结果。"""
    pcm_bytes: bytes       # raw PCM (signed 16-bit LE, mono, 16kHz)
    wav_bytes: bytes       # WAV 容器（含 44 字节头）
    duration_seconds: float
    sample_rate: int       # 目标采样率
    channels: int          # 目标声道数
    sample_width: int      # 目标采样宽度（字节）
    source_format: str     # 源格式标识，如 "webm/opus", "ogg/opus", "wav"


class AudioPreprocessError(Exception):
    """音频预处理异常基类。"""

    def __init__(self, message: str, *, status_code: int = 400):
        self.status_code = status_code
        super().__init__(message)


class AudioEmptyError(AudioPreprocessError):
    """音频文件为空。"""
    def __init__(self) -> None:
        super().__init__("音频文件为空", status_code=400)


class AudioTooLargeError(AudioPreprocessError):
    """音频文件超过最大字节数。"""
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(
            f"音频文件过大（{size / 1024 / 1024:.1f}MB），最大允许 {limit / 1024 / 1024:.0f}MB",
            status_code=413,
        )


class AudioTooLongError(AudioPreprocessError):
    """音频时长超过限制。"""
    def __init__(self, duration: float, limit: float) -> None:
        super().__init__(
            f"音频时长过长（{duration:.0f}秒），最大允许 {limit:.0f}秒",
            status_code=413,
        )


class AudioInvalidError(AudioPreprocessError):
    """音频数据无效（无法解码）。"""
    def __init__(self, detail: str = "") -> None:
        msg = "无法解码音频数据，请确认录音格式正确"
        if detail:
            msg = f"{msg}（{detail}）"
        super().__init__(msg, status_code=422)


class FFmpegUnavailableError(AudioPreprocessError):
    """FFmpeg 不可用。"""
    def __init__(self) -> None:
        super().__init__(
            "音频处理服务不可用（FFmpeg 未安装），请联系系统管理员",
            status_code=503,
        )


class FFmpegTimeoutError(AudioPreprocessError):
    """FFmpeg 执行超时。"""
    def __init__(self, timeout: float) -> None:
        super().__init__(
            f"音频处理超时（超过 {timeout:.0f} 秒），请缩短录音后重试",
            status_code=504,
        )


def _detect_source_format(data: bytes, filename: str, content_type: str) -> str:
    """根据文件头和元信息推断源格式。"""
    # WebM magic: 0x1A45DFA3
    if data[:4] == b"\x1a\x45\xdf\xa3":
        if "opus" in content_type.lower():
            return "webm/opus"
        return "webm"
    # OGG magic: OggS
    if data[:4] == b"OggS":
        if "opus" in content_type.lower():
            return "ogg/opus"
        return "ogg"
    # RIFF/WAV magic
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    # FLAC magic
    if data[:4] == b"fLaC":
        return "flac"
    # MP3 magic
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return "mp3"
    # Fallback to filename extension
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in ("webm", "ogg", "opus", "wav", "flac", "mp3", "m4a", "aac"):
        return ext
    return "unknown"


def _build_wav_header(pcm_size: int, sample_rate: int, channels: int, sample_width: int) -> bytes:
    """构建标准 44 字节 WAV 文件头。"""
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = pcm_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,       # ChunkSize
        b"WAVE",
        b"fmt ",
        16,                    # SubChunk1Size (PCM)
        1,                     # AudioFormat (PCM=1)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,      # BitsPerSample
        b"data",
        data_size,
    )
    return header


async def _check_ffmpeg_available() -> None:
    """检查 FFmpeg 是否可用。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0:
            raise FFmpegUnavailableError()
    except FileNotFoundError:
        raise FFmpegUnavailableError()


async def _probe_duration(input_path: str, timeout: float) -> float:
    """
    使用 ffprobe 获取音频时长。
    基于实际解码结果，不使用字节长度估算。
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            input_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="ignore").strip()
        if output:
            return float(output)
    except asyncio.TimeoutError:
        logger.warning("ffprobe 超时，尝试从转换结果推断时长")
    except (ValueError, FileNotFoundError) as exc:
        logger.warning("ffprobe 执行失败: %s", exc)
    return 0.0


async def _convert_to_pcm(
    input_path: str,
    output_path: str,
    timeout: float,
) -> None:
    """
    使用 FFmpeg 将输入音频转换为 raw PCM (16kHz, mono, s16le)。
    同时输出到 WAV 容器。
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",                # 覆盖输出文件
        "-i", input_path,    # 输入
        "-ac", str(TARGET_CHANNELS),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        "-f", "s16le",       # raw PCM 输出（通过 pipe 或文件）
        output_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="ignore")[-200:]
        raise AudioInvalidError(f"FFmpeg 转换失败: {err_msg}")


async def _convert_to_wav(
    input_path: str,
    output_path: str,
    timeout: float,
) -> None:
    """使用 FFmpeg 将输入音频转换为 WAV (16kHz, mono, s16le)。"""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", str(TARGET_CHANNELS),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        "-f", "wav",
        output_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="ignore")[-200:]
        raise AudioInvalidError(f"FFmpeg WAV 转换失败: {err_msg}")


def _is_silent(pcm_bytes: bytes, threshold: int = 100) -> bool:
    """检测 PCM 数据是否几乎静音。"""
    if len(pcm_bytes) < 2:
        return True
    # 采样检查：每 100 个样本检查一次
    step = 200  # 2 bytes per sample * 100
    samples_checked = 0
    non_silent = 0
    for i in range(0, len(pcm_bytes) - 1, step):
        sample = struct.unpack_from("<h", pcm_bytes, i)[0]
        samples_checked += 1
        if abs(sample) > threshold:
            non_silent += 1
    if samples_checked == 0:
        return True
    # 如果超过 99% 的采样都是静音，认为是空音频
    return (non_silent / samples_checked) < 0.01


async def preprocess_audio(
    audio_bytes: bytes,
    *,
    filename: str = "audio.webm",
    content_type: str = "",
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
    ffmpeg_timeout: float = DEFAULT_FFMPEG_TIMEOUT_SECONDS,
) -> AudioPreprocessResult:
    """
    预处理浏览器上传的音频，统一转换为 16kHz 单声道 PCM/WAV。

    流程：
    1. 校验输入大小
    2. 检测源格式
    3. 检查 FFmpeg 可用性
    4. 写入临时文件
    5. ffprobe 获取真实时长
    6. 校验时长限制
    7. FFmpeg 转换为 PCM + WAV
    8. 检测静音
    9. 返回结构化结果

    参数：
        audio_bytes: 原始音频字节
        filename: 原始文件名（用于格式推断）
        content_type: MIME 类型（用于格式推断）
        max_upload_bytes: 最大上传字节数
        max_duration_seconds: 最大音频时长（秒）
        ffmpeg_timeout: FFmpeg 执行超时（秒）

    返回：
        AudioPreprocessResult 包含 pcm_bytes, wav_bytes, duration 等

    异常：
        AudioEmptyError: 音频为空
        AudioTooLargeError: 文件过大
        AudioTooLongError: 时长过长
        AudioInvalidError: 无法解码
        FFmpegUnavailableError: FFmpeg 未安装
        FFmpegTimeoutError: 处理超时
    """
    # 1. 基础校验
    if not audio_bytes:
        raise AudioEmptyError()

    if len(audio_bytes) > max_upload_bytes:
        raise AudioTooLargeError(len(audio_bytes), max_upload_bytes)

    # 2. 检测源格式
    source_format = _detect_source_format(audio_bytes, filename, content_type or "")
    logger.info(
        "音频预处理: filename=%s, format=%s, size=%d bytes",
        filename, source_format, len(audio_bytes),
    )

    # 3. 检查 FFmpeg
    await _check_ffmpeg_available()

    # 4-9. 临时文件处理
    tmp_dir = tempfile.mkdtemp(prefix="icu_audio_")
    input_path = os.path.join(tmp_dir, "input")
    pcm_path = os.path.join(tmp_dir, "output.pcm")
    wav_path = os.path.join(tmp_dir, "output.wav")

    try:
        # 写入输入文件
        with open(input_path, "wb") as f:
            f.write(audio_bytes)

        # 5. 获取真实时长
        duration = await _probe_duration(input_path, timeout=ffmpeg_timeout)
        if duration <= 0:
            # ffprobe 失败时，尝试转换后从文件大小推算
            logger.warning("ffprobe 未能获取时长，将在转换后推算")

        # 6. 时长校验
        if duration > 0 and duration > max_duration_seconds:
            raise AudioTooLongError(duration, max_duration_seconds)

        # 7. 转换为 PCM
        try:
            await _convert_to_pcm(input_path, pcm_path, timeout=ffmpeg_timeout)
        except asyncio.TimeoutError:
            raise FFmpegTimeoutError(ffmpeg_timeout)

        # 读取 PCM
        with open(pcm_path, "rb") as f:
            pcm_bytes = f.read()

        if not pcm_bytes:
            raise AudioInvalidError("转换后 PCM 数据为空")

        # 如果 ffprobe 失败，从 PCM 大小推算时长
        if duration <= 0:
            duration = len(pcm_bytes) / (TARGET_SAMPLE_RATE * TARGET_CHANNELS * TARGET_SAMPLE_WIDTH)
            # 再次校验
            if duration > max_duration_seconds:
                raise AudioTooLongError(duration, max_duration_seconds)

        # 8. 静音检测
        if _is_silent(pcm_bytes):
            raise AudioInvalidError("音频几乎全部静音，请确认麦克风正常工作")

        # 构建 WAV
        wav_header = _build_wav_header(
            len(pcm_bytes), TARGET_SAMPLE_RATE, TARGET_CHANNELS, TARGET_SAMPLE_WIDTH
        )
        wav_bytes = wav_header + pcm_bytes

        logger.info(
            "音频预处理完成: duration=%.1fs, pcm=%d bytes, wav=%d bytes, source=%s",
            duration, len(pcm_bytes), len(wav_bytes), source_format,
        )

        return AudioPreprocessResult(
            pcm_bytes=pcm_bytes,
            wav_bytes=wav_bytes,
            duration_seconds=round(duration, 2),
            sample_rate=TARGET_SAMPLE_RATE,
            channels=TARGET_CHANNELS,
            sample_width=TARGET_SAMPLE_WIDTH,
            source_format=source_format,
        )

    except AudioPreprocessError:
        raise
    except asyncio.TimeoutError:
        raise FFmpegTimeoutError(ffmpeg_timeout)
    except Exception as exc:
        raise AudioInvalidError(str(exc))
    finally:
        # 清理临时文件
        for p in (input_path, pcm_path, wav_path):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


async def check_audio_preprocessor_available() -> dict[str, Any]:
    """
    健康检查：返回音频预处理器可用状态。
    供 /health 端点使用。
    """
    try:
        await _check_ffmpeg_available()
        return {"available": True, "ffmpeg": True}
    except FFmpegUnavailableError:
        return {"available": False, "ffmpeg": False, "reason": "FFmpeg 未安装"}
