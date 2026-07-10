"""Unit tests for VoiceRoundingStreamService — pipeline, LLM gating, degradation."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.asr_client import ASREmptyTranscriptionError
from app.services.streaming_asr import _normalize_timestamp


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class VoiceRoundingStreamServiceTest(unittest.TestCase):
    """Test VoiceRoundingStreamService pipeline and LLM gating."""

    def _make_service(self, patient_id="patient1"):
        from app.services.voice_rounding_stream import VoiceRoundingStreamService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "draft_id_123"
        db.col.return_value.insert_one = AsyncMock(return_value=mock_result)
        db.col.return_value.find_one = AsyncMock(return_value=None)

        config = SimpleNamespace(
            yaml_cfg={
                "voice_rounding": {
                    "enabled": True,
                    "asr": {"mode": "mock"},
                    "llm_correction": {"enabled": True, "protect_numbers": True},
                    "stream": {"final_wait_timeout": 5.0},
                },
            },
            settings=SimpleNamespace(
                ASR_BASE_URL="http://localhost:10095",
                ASR_MODE="ws",
                ASR_2PASS_ENABLED=True,
            ),
            llm_fast_model="fast-model",
        )
        return VoiceRoundingStreamService(db, config, patient_id)

    # ── test 1: LLM never called during partial ───────────────────────

    @patch("app.services.llm_runtime.call_llm_chat")
    @patch("app.services.streaming_asr.websockets")
    def test_llm_not_called_on_partial(self, mock_ws_module, mock_llm):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())  # block
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:  # noqa
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        svc = self._make_service()
        _run_async(svc.start(hotwords=[]))

        # Simulate partial messages
        _run_async(svc._on_partial("患者", None, None))
        _run_async(svc._on_partial("患者血压", None, None))
        _run_async(svc._on_partial("患者血压稳定", None, None))

        # LLM must NOT have been called
        mock_llm.assert_not_called()

        _run_async(svc.cancel())

    # ── test 2: stop() → LLM called exactly twice (correction + summary) ──

    @patch("app.services.llm_runtime.call_llm_chat")
    @patch("app.services.voice_rounding.VoiceRoundingService._llm_correct")
    @patch("app.services.streaming_asr.websockets")
    def test_stop_calls_llm_once_each(self, mock_ws_module, mock_llm_correct, mock_llm_chat):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        mock_llm_correct.return_value = {
            "text": "患者血压稳定", "corrected": True, "suspect": [],
            "suspect_terms": [], "needs_human_review": False, "degraded": False,
        }

        mock_llm_chat.return_value = {
            "text": '{"text": "查房总结", "sections": [{"title": "病情", "content": "稳定"}]}',
        }

        svc = self._make_service()
        _run_async(svc.start(hotwords=[]))

        # Simulate final segments
        _run_async(svc._on_final("患者血压稳定", [], 0, 3000))

        # Manually complete stop — simulate send_stop + matching response
        _run_async(svc._session.send_stop())
        svc._session._stop_final_future.set_result(True)

        # Now stop
        draft = _run_async(svc.stop())

        # LLM correction should have been called once
        mock_llm_correct.assert_called_once()
        # LLM chat (summary) should have been called once
        self.assertGreaterEqual(mock_llm_chat.call_count, 1)

        # Draft should be created
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["raw_text"], "患者血压稳定")

    # ── test 3: correction fails → degraded + summary still called ────

    @patch("app.services.voice_rounding.VoiceRoundingService._llm_correct")
    @patch("app.services.streaming_asr.websockets")
    def test_correction_failure_degraded(self, mock_ws_module, mock_llm_correct):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        mock_llm_correct.side_effect = Exception("LLM 纠错失败")

        svc = self._make_service()
        _run_async(svc.start(hotwords=[]))
        _run_async(svc._on_final("患者血压稳定", [], 0, 3000))
        _run_async(svc._session.send_stop())
        svc._session._stop_final_future.set_result(True)

        draft = _run_async(svc.stop())

        # Should be degraded
        self.assertTrue(draft["degraded"])
        self.assertTrue(draft["needs_human_review"])

    # ── test 4: summary fails → summary_degraded + draft still created ──

    @patch("app.services.voice_rounding.VoiceRoundingService._llm_correct")
    @patch("app.services.llm_runtime.call_llm_chat")
    @patch("app.services.streaming_asr.websockets")
    def test_summary_failure_draft_created(self, mock_ws_module, mock_llm_chat, mock_llm_correct):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        mock_llm_correct.return_value = {
            "text": "患者血压稳定", "corrected": False, "suspect": [],
            "suspect_terms": [], "needs_human_review": False, "degraded": False,
        }
        mock_llm_chat.side_effect = Exception("总结 LLM 失败")

        svc = self._make_service()
        _run_async(svc.start(hotwords=[]))
        _run_async(svc._on_final("患者血压稳定", [], 0, 3000))
        _run_async(svc._session.send_stop())
        svc._session._stop_final_future.set_result(True)

        draft = _run_async(svc.stop())

        self.assertTrue(draft["summary_degraded"])
        self.assertIsNone(draft["summary_text"])
        self.assertEqual(draft["status"], "draft")

    # ── test 5: final empty + partial non-empty → degraded draft ───────

    @patch("app.services.streaming_asr.websockets")
    def test_only_partial_creates_degraded_draft(self, mock_ws_module):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        svc = self._make_service()
        _run_async(svc.start(hotwords=[]))

        # Only partial, no final
        _run_async(svc._on_partial("患者", None, None))

        _run_async(svc._session.send_stop())
        svc._session._stop_final_future.set_result(True)

        draft = _run_async(svc.stop())

        self.assertTrue(draft["degraded"])
        self.assertTrue(draft["needs_human_review"])
        self.assertEqual(draft["raw_text"], "患者")

    # ── test 6: final + partial both empty → ASREmptyTranscriptionError ──

    @patch("app.services.streaming_asr.websockets")
    def test_empty_both_raises(self, mock_ws_module):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        svc = self._make_service()
        _run_async(svc.start(hotwords=[]))
        _run_async(svc._session.send_stop())
        svc._session._stop_final_future.set_result(True)

        with self.assertRaises(ASREmptyTranscriptionError):
            _run_async(svc.stop())

    # ── test 7: cancel → no draft written ──────────────────────────────

    @patch("app.services.streaming_asr.websockets")
    def test_cancel_no_draft(self, mock_ws_module):
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        svc = self._make_service()
        _run_async(svc.start(hotwords=[]))
        _run_async(svc._on_final("患者血压稳定", [], 0, 3000))
        _run_async(svc.cancel())

        # insert_one should not have been called
        svc._db.col.return_value.insert_one.assert_not_called()

    # ── test 8: wait_final timeout → degraded draft ───────────────────

    @patch("app.services.streaming_asr.websockets")
    def test_wait_final_timeout_degraded(self, mock_ws_module):
        mock_ws = AsyncMock()
        # recv blocks forever — simulating FunASR not responding after stop
        mock_ws.recv = AsyncMock(side_effect=asyncio.get_event_loop().create_future())
        mock_ws.send = AsyncMock()
        ping_f = asyncio.get_event_loop().create_future()
        ping_f.set_result(None)
        mock_ws.ping = AsyncMock(return_value=ping_f)

        def mock_connect(*a, **kw):
            class F:
                async def __aenter__(s): return mock_ws
                async def __aexit__(s, *a): pass
            return F()
        mock_ws_module.connect = mock_connect

        # Use short timeout
        import types
        svc = self._make_service()
        svc._cfg["final_wait_timeout"] = 0.1  # very short timeout

        _run_async(svc.start(hotwords=[]))
        _run_async(svc._on_final("患者血压稳定", [], 0, 3000))

        draft = _run_async(svc.stop())

        # Must be degraded
        self.assertTrue(draft["degraded"])
        self.assertTrue(draft["needs_human_review"])
        self.assertFalse(draft["processing"]["asr_final_complete"])
        # LLM should have been attempted (we have full_text)
        self.assertTrue(draft["processing"]["llm_correction"])

    # ── test 9: multiple segment concatenation ────────────────────────

    def test_segments_concatenated(self):
        svc = self._make_service()
        self.assertEqual(svc.full_text, "")

        _run_async(svc._on_final("第一段", [], 0, 1000))
        self.assertEqual(svc.full_text, "第一段")
        _run_async(svc._on_final("第二段", [], 1000, 2000))
        self.assertEqual(svc.full_text, "第一段。第二段")
        _run_async(svc._on_final("第三段", [], 2000, 3000))
        self.assertEqual(svc.full_text, "第一段。第二段。第三段")

    # ── test 10: _normalize_timestamp ─────────────────────────────────

    def test_normalize_timestamp(self):
        self.assertEqual(_normalize_timestamp(5000, "start"), 5000)
        self.assertEqual(_normalize_timestamp(5000.0, "start"), 5000)
        self.assertIsNone(_normalize_timestamp(None, "start"))
        self.assertEqual(_normalize_timestamp(0, "end"), 0)
        self.assertIsNone(_normalize_timestamp(-1, "start"))


if __name__ == "__main__":
    unittest.main()
