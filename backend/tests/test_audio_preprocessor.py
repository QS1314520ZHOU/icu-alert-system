"""音频预处理器单元测试。"""
from __future__ import annotations

import asyncio
import struct
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class DetectSourceFormatTest(unittest.TestCase):
    """源格式检测测试。"""

    def test_webm_magic_detected(self):
        from app.services.audio_preprocessor import _detect_source_format

        # WebM magic bytes
        data = b"\x1a\x45\xdf\xa3" + b"\x00" * 100
        result = _detect_source_format(data, "test.webm", "audio/webm")
        self.assertEqual(result, "webm")

    def test_webm_opus_detected(self):
        from app.services.audio_preprocessor import _detect_source_format

        data = b"\x1a\x45\xdf\xa3" + b"\x00" * 100
        result = _detect_source_format(data, "test.webm", "audio/webm;codecs=opus")
        self.assertEqual(result, "webm/opus")

    def test_ogg_magic_detected(self):
        from app.services.audio_preprocessor import _detect_source_format

        data = b"OggS" + b"\x00" * 100
        result = _detect_source_format(data, "test.ogg", "audio/ogg")
        self.assertEqual(result, "ogg")

    def test_wav_magic_detected(self):
        from app.services.audio_preprocessor import _detect_source_format

        data = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 100
        result = _detect_source_format(data, "test.wav", "audio/wav")
        self.assertEqual(result, "wav")

    def test_unknown_falls_back_to_extension(self):
        from app.services.audio_preprocessor import _detect_source_format

        data = b"\x00" * 100
        result = _detect_source_format(data, "test.mp3", "")
        self.assertEqual(result, "mp3")

    def test_unknown_no_extension(self):
        from app.services.audio_preprocessor import _detect_source_format

        data = b"\x00" * 100
        result = _detect_source_format(data, "test", "")
        self.assertEqual(result, "unknown")


class BuildWavHeaderTest(unittest.TestCase):
    """WAV 头构建测试。"""

    def test_header_length(self):
        from app.services.audio_preprocessor import _build_wav_header

        header = _build_wav_header(32000, 16000, 1, 2)
        self.assertEqual(len(header), 44)

    def test_header_riff_magic(self):
        from app.services.audio_preprocessor import _build_wav_header

        header = _build_wav_header(32000, 16000, 1, 2)
        self.assertEqual(header[:4], b"RIFF")
        self.assertEqual(header[8:12], b"WAVE")
        self.assertEqual(header[12:16], b"fmt ")
        self.assertEqual(header[36:40], b"data")

    def test_header_sample_rate(self):
        from app.services.audio_preprocessor import _build_wav_header

        header = _build_wav_header(32000, 16000, 1, 2)
        # Sample rate at offset 24 (little-endian uint32)
        sr = struct.unpack_from("<I", header, 24)[0]
        self.assertEqual(sr, 16000)


class IsSilentTest(unittest.TestCase):
    """静音检测测试。"""

    def test_silent_pcm(self):
        from app.services.audio_preprocessor import _is_silent

        # 全零 PCM
        pcm = b"\x00\x00" * 1000
        self.assertTrue(_is_silent(pcm))

    def test_non_silent_pcm(self):
        from app.services.audio_preprocessor import _is_silent

        # 包含非零样本
        samples = [1000, -1000, 500, -500] * 250
        pcm = b"".join(struct.pack("<h", s) for s in samples)
        self.assertFalse(_is_silent(pcm))

    def test_empty_pcm_is_silent(self):
        from app.services.audio_preprocessor import _is_silent

        self.assertTrue(_is_silent(b""))

    def test_very_short_pcm(self):
        from app.services.audio_preprocessor import _is_silent

        self.assertTrue(_is_silent(b"\x00\x00"))


class InputValidationTest(unittest.TestCase):
    """输入校验测试。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_empty_audio_raises_empty_error(self):
        from app.services.audio_preprocessor import AudioEmptyError, preprocess_audio

        with self.assertRaises(AudioEmptyError):
            self._run_async(preprocess_audio(b""))

    def test_oversized_audio_raises_too_large(self):
        from app.services.audio_preprocessor import AudioTooLargeError, preprocess_audio

        # 创建超过限制的数据
        max_bytes = 1024
        data = b"\x00" * (max_bytes + 1)
        with self.assertRaises(AudioTooLargeError):
            self._run_async(preprocess_audio(data, max_upload_bytes=max_bytes))

    def test_too_large_error_status_code(self):
        from app.services.audio_preprocessor import AudioTooLargeError

        err = AudioTooLargeError(100, 50)
        self.assertEqual(err.status_code, 413)

    def test_empty_error_status_code(self):
        from app.services.audio_preprocessor import AudioEmptyError

        err = AudioEmptyError()
        self.assertEqual(err.status_code, 400)

    def test_invalid_error_status_code(self):
        from app.services.audio_preprocessor import AudioInvalidError

        err = AudioInvalidError()
        self.assertEqual(err.status_code, 422)

    def test_ffmpeg_unavailable_status_code(self):
        from app.services.audio_preprocessor import FFmpegUnavailableError

        err = FFmpegUnavailableError()
        self.assertEqual(err.status_code, 503)

    def test_ffmpeg_timeout_status_code(self):
        from app.services.audio_preprocessor import FFmpegTimeoutError

        err = FFmpegTimeoutError(60)
        self.assertEqual(err.status_code, 504)


class FFmpegCheckTest(unittest.TestCase):
    """FFmpeg 可用性检查测试。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.audio_preprocessor.asyncio.create_subprocess_exec")
    def test_ffmpeg_not_found_raises(self, mock_exec):
        from app.services.audio_preprocessor import FFmpegUnavailableError, _check_ffmpeg_available

        mock_exec.side_effect = FileNotFoundError("ffmpeg not found")
        with self.assertRaises(FFmpegUnavailableError):
            self._run_async(_check_ffmpeg_available())

    @patch("app.services.audio_preprocessor.asyncio.create_subprocess_exec")
    def test_ffmpeg_nonzero_exit_raises(self, mock_exec):
        from app.services.audio_preprocessor import FFmpegUnavailableError, _check_ffmpeg_available

        mock_proc = MagicMock()
        mock_proc.wait = AsyncMock(return_value=1)
        mock_exec.return_value = mock_proc
        with self.assertRaises(FFmpegUnavailableError):
            self._run_async(_check_ffmpeg_available())


class PreprocessIntegrationTest(unittest.TestCase):
    """集成测试：完整预处理流程（mock FFmpeg）。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.audio_preprocessor._convert_to_pcm")
    @patch("app.services.audio_preprocessor._probe_duration", return_value=2.0)
    @patch("app.services.audio_preprocessor._check_ffmpeg_available")
    def test_valid_webm_converted(self, mock_check, mock_probe, mock_pcm):
        from app.services.audio_preprocessor import preprocess_audio

        # 模拟 PCM 输出：16kHz, mono, 16-bit, 2秒 = 64000 bytes
        pcm_data = struct.pack("<h", 1000) * 32000

        async def fake_pcm(input_path, output_path, timeout):
            with open(output_path, "wb") as f:
                f.write(pcm_data)

        mock_pcm.side_effect = fake_pcm

        # WebM magic + padding
        webm_data = b"\x1a\x45\xdf\xa3" + b"\x00" * 100

        result = self._run_async(preprocess_audio(webm_data, filename="test.webm"))
        self.assertEqual(result.sample_rate, 16000)
        self.assertEqual(result.channels, 1)
        self.assertEqual(result.sample_width, 2)
        self.assertEqual(result.source_format, "webm")
        self.assertEqual(result.duration_seconds, 2.0)
        self.assertTrue(len(result.pcm_bytes) > 0)
        self.assertTrue(len(result.wav_bytes) > len(result.pcm_bytes))
        # WAV 应以 RIFF 头开始
        self.assertTrue(result.wav_bytes.startswith(b"RIFF"))

    @patch("app.services.audio_preprocessor._convert_to_pcm")
    @patch("app.services.audio_preprocessor._probe_duration", return_value=2.0)
    @patch("app.services.audio_preprocessor._check_ffmpeg_available")
    def test_silent_audio_rejected(self, mock_check, mock_probe, mock_pcm):
        from app.services.audio_preprocessor import AudioInvalidError, preprocess_audio

        # 全静音 PCM
        silent_pcm = b"\x00\x00" * 32000

        async def fake_pcm(input_path, output_path, timeout):
            with open(output_path, "wb") as f:
                f.write(silent_pcm)

        mock_pcm.side_effect = fake_pcm

        webm_data = b"\x1a\x45\xdf\xa3" + b"\x00" * 100
        with self.assertRaises(AudioInvalidError):
            self._run_async(preprocess_audio(webm_data, filename="test.webm"))

    @patch("app.services.audio_preprocessor._convert_to_pcm")
    @patch("app.services.audio_preprocessor._probe_duration", return_value=400.0)
    @patch("app.services.audio_preprocessor._check_ffmpeg_available")
    def test_too_long_audio_rejected(self, mock_check, mock_probe, mock_pcm):
        from app.services.audio_preprocessor import AudioTooLongError, preprocess_audio

        webm_data = b"\x1a\x45\xdf\xa3" + b"\x00" * 100
        with self.assertRaises(AudioTooLongError):
            self._run_async(
                preprocess_audio(webm_data, filename="test.webm", max_duration_seconds=300)
            )


class CheckAvailableTest(unittest.TestCase):
    """健康检查测试。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.audio_preprocessor._check_ffmpeg_available")
    def test_available(self, mock_check):
        from app.services.audio_preprocessor import check_audio_preprocessor_available

        mock_check.return_value = None  # 不抛异常 = 可用
        result = self._run_async(check_audio_preprocessor_available())
        self.assertTrue(result["available"])
        self.assertTrue(result["ffmpeg"])

    @patch("app.services.audio_preprocessor._check_ffmpeg_available")
    def test_unavailable(self, mock_check):
        from app.services.audio_preprocessor import (
            FFmpegUnavailableError,
            check_audio_preprocessor_available,
        )

        mock_check.side_effect = FFmpegUnavailableError()
        result = self._run_async(check_audio_preprocessor_available())
        self.assertFalse(result["available"])
        self.assertFalse(result["ffmpeg"])


if __name__ == "__main__":
    unittest.main()
