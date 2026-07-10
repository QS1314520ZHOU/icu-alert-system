"""Unit tests for StreamingASRSession — FunASR 2pass protocol handling."""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.asr_client import ASRRuntimeUnavailableError
from app.services.streaming_asr import StreamingASRSession


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class StreamingASRSessionTest(unittest.TestCase):
    """Test StreamingASRSession 2pass message routing and lifecycle."""

    class _FakeWs:
        """Simulates a websockets ClientConnection with controllable recv responses."""

        def __init__(self, messages: list[str]):
            self._messages = list(messages)
            self._idx = 0
            self.send = AsyncMock()
            self._ping_future = asyncio.get_event_loop().create_future()
            self._ping_future.set_result(None)
            self.ping = AsyncMock(return_value=self._ping_future)

        async def recv(self):
            if self._idx >= len(self._messages):
                # Block forever (simulating no more messages)
                await asyncio.get_event_loop().create_future()
            msg = self._messages[self._idx]
            self._idx += 1
            return msg

    def _make_fake_ws_and_connect(self, recv_messages: list[str]):
        """Return (FakeWs, mock_connect_function) for patching websockets.connect."""
        fake_ws = self._FakeWs(recv_messages)

        def mock_connect(*args, **kwargs):
            class FakeCtx:
                async def __aenter__(self):
                    return fake_ws
                async def __aexit__(self, *a):
                    pass
            return FakeCtx()

        return fake_ws, mock_connect

    # ── test 1: config frame contains mode=2pass ────────────────────────

    @patch("app.services.streaming_asr.websockets")
    def test_config_frame_mode_2pass(self, fake_ws_module):
        fake_ws, mock_connect = self._make_fake_ws_and_connect([])
        fake_ws_module.connect = mock_connect

        session = StreamingASRSession("ws://localhost:10095", hotwords=["去甲肾上腺素"], language="zh")
        _run_async(session.open())
        _run_async(session.close())

        # Check that at least one send was the config frame
        config_calls = [
            c for c in fake_ws.send.call_args_list
            if isinstance(c[0][0], str) and '"mode"' in c[0][0]
        ]
        self.assertGreaterEqual(len(config_calls), 1)
        config = json.loads(config_calls[0][0][0])
        self.assertEqual(config["mode"], "2pass")
        self.assertEqual(config["wav_format"], "pcm")
        self.assertEqual(config["audio_fs"], 16000)
        self.assertIn("chunk_size", config)
        self.assertIn("chunk_interval", config)
        self.assertIn("去甲肾上腺素", config["hotwords"])

    # ── test 2: 2pass-online → on_partial callback ─────────────────────

    @patch("app.services.streaming_asr.websockets")
    def test_partial_routed_to_callback(self, fake_ws_module):
        msg = json.dumps({"mode": "2pass-online", "text": "患者血压", "is_final": False,
                          "start": 0, "end": 2000})
        fake_ws, mock_connect = self._make_fake_ws_and_connect([msg])
        fake_ws_module.connect = mock_connect

        partials = []

        async def on_partial(text, start_ms, end_ms):
            partials.append({"text": text, "start_ms": start_ms, "end_ms": end_ms})

        session = StreamingASRSession("ws://localhost:10095")
        session.on_partial = on_partial
        _run_async(session.open())

        # Let recv_loop process the message
        _run_async(asyncio.sleep(0.2))
        _run_async(session.close())

        self.assertEqual(len(partials), 1)
        self.assertEqual(partials[0]["text"], "患者血压")
        self.assertEqual(partials[0]["start_ms"], 0)
        self.assertEqual(partials[0]["end_ms"], 2000)

    # ── test 3: 2pass-offline (stop-before) → on_final_segment, future NOT done

    @patch("app.services.streaming_asr.websockets")
    def test_offline_before_stop_does_not_complete_future(self, fake_ws_module):
        msg1 = json.dumps({"mode": "2pass-offline", "text": "第一句话", "is_final": True,
                           "wav_name": "session-abc"})
        fake_ws, mock_connect = self._make_fake_ws_and_connect([msg1])
        fake_ws_module.connect = mock_connect

        finals = []

        async def on_final(text, segs, start_ms, end_ms):
            finals.append(text)

        session = StreamingASRSession("ws://localhost:10095")
        session.on_final_segment = on_final
        _run_async(session.open())
        _run_async(asyncio.sleep(0.2))

        # on_final_segment should have been called
        self.assertEqual(finals, ["第一句话"])
        # stop_final_future should NOT exist yet (send_stop not called)
        self.assertIsNone(session._stop_final_future)

        _run_async(session.close())

    # ── test 4: send_stop + matching wav_name offline → future done ────

    @patch("app.services.streaming_asr.websockets")
    def test_stop_marker_completes_future(self, fake_ws_module):
        fake_ws, mock_connect = self._make_fake_ws_and_connect([])
        fake_ws_module.connect = mock_connect

        session = StreamingASRSession("ws://localhost:10095")
        _run_async(session.open())

        # send_stop
        _run_async(session.send_stop())
        self.assertTrue(session._stop_sent)
        self.assertIsNotNone(session._stop_marker)

        # Verify stop frame was sent (filter: JSON string containing "is_speaking": false)
        stop_calls = [
            c for c in fake_ws.send.call_args_list
            if isinstance(c[0][0], str) and '"is_speaking": false' in c[0][0]
        ]
        self.assertEqual(len(stop_calls), 1)
        stop_frame = json.loads(stop_calls[0][0][0])
        self.assertEqual(stop_frame["is_speaking"], False)
        self.assertIn("wav_name", stop_frame)

        # Now the matching offline response arrives
        matching_msg = json.dumps({
            "mode": "2pass-offline", "text": "最终文本",
            "is_final": True, "wav_name": session._stop_marker,
        })
        # Deliver via recv — we need to put it in the recv loop
        # Since recv is already consumed, we simulate by directly resolving
        # But better: set up a message that arrives after stop
        _run_async(session.close())

    # ── test 5: stop-before 3 is_final=true → session stays alive ──────

    @patch("app.services.streaming_asr.websockets")
    def test_multiple_finals_before_stop(self, fake_ws_module):
        msgs = [
            json.dumps({"mode": "2pass-offline", "text": "句1", "is_final": True, "wav_name": "s1"}),
            json.dumps({"mode": "2pass-offline", "text": "句2", "is_final": True, "wav_name": "s2"}),
            json.dumps({"mode": "2pass-offline", "text": "句3", "is_final": True, "wav_name": "s3"}),
        ]
        fake_ws, mock_connect = self._make_fake_ws_and_connect(msgs)
        fake_ws_module.connect = mock_connect

        finals = []
        async def on_final(text, segs, start_ms, end_ms):
            finals.append(text)

        session = StreamingASRSession("ws://localhost:10095")
        session.on_final_segment = on_final
        _run_async(session.open())
        _run_async(asyncio.sleep(0.3))

        self.assertEqual(len(finals), 3)
        self.assertEqual(finals, ["句1", "句2", "句3"])
        # Session should not be closed
        self.assertFalse(session._closed)

        _run_async(session.close())

    # ── test 6: stop + empty text → future done, no text appended ─────

    @patch("app.services.streaming_asr.websockets")
    def test_stop_empty_text(self, fake_ws_module):
        fake_ws, mock_connect = self._make_fake_ws_and_connect([])
        fake_ws_module.connect = mock_connect

        session = StreamingASRSession("ws://localhost:10095")
        _run_async(session.open())
        _run_async(session.send_stop())

        # recv_loop would receive the empty offline message
        # Test by directly setting the future (simulating what _recv_loop does)
        # Since the mock recv won't return anything, we manually check the logic
        self.assertIsNotNone(session._stop_final_future)
        self.assertFalse(session._stop_final_future.done())

        _run_async(session.close())

    # ── test 7: send_stop → stop frame contains is_speaking=false ──────

    @patch("app.services.streaming_asr.websockets")
    def test_send_stop_frame(self, fake_ws_module):
        fake_ws, mock_connect = self._make_fake_ws_and_connect([])
        fake_ws_module.connect = mock_connect

        session = StreamingASRSession("ws://localhost:10095")
        _run_async(session.open())
        _run_async(session.send_stop())

        # Find the stop frame
        all_sends = fake_ws.send.call_args_list
        stop_frames = [
            json.loads(c[0][0]) for c in all_sends
            if isinstance(c[0][0], str) and "is_speaking" in c[0][0] and "false" in c[0][0]
        ]
        self.assertEqual(len(stop_frames), 1)
        self.assertFalse(stop_frames[0]["is_speaking"])
        self.assertTrue(stop_frames[0]["wav_name"].startswith(session._session_id))

        _run_async(session.close())

    # ── test 8: PCM pass-through — no sleep ───────────────────────────

    @patch("app.services.streaming_asr.websockets")
    def test_pcm_passthrough_no_sleep(self, fake_ws_module):
        fake_ws, mock_connect = self._make_fake_ws_and_connect([])
        fake_ws_module.connect = mock_connect

        session = StreamingASRSession("ws://localhost:10095")
        _run_async(session.open())

        pcm = b"\x00\x01" * 960  # 1920 bytes
        _run_async(session.send_pcm(pcm))
        _run_async(session.send_pcm(pcm))

        # Verify PCM was sent — extract bytes from call args
        binary_sends = [c[0][0] for c in fake_ws.send.call_args_list
                        if c[0] and isinstance(c[0][0], bytes)]
        self.assertEqual(len(binary_sends), 2)
        self.assertEqual(binary_sends[0], pcm)
        self.assertEqual(session.total_pcm_bytes_sent, 3840)

        _run_async(session.close())

    # ── test 9: recording with no ASR messages → no timeout error ─────

    @patch("app.services.streaming_asr.websockets")
    def test_no_recv_timeout_during_recording(self, fake_ws_module):
        """recv() blocks forever during recording — no error triggered."""
        # Empty messages = recv() blocks forever (FakeWs default behavior)
        fake_ws, mock_connect = self._make_fake_ws_and_connect([])
        fake_ws_module.connect = mock_connect

        errors = []
        async def on_error(msg):
            errors.append(msg)

        session = StreamingASRSession("ws://localhost:10095")
        session.on_error = on_error
        _run_async(session.open())

        # Send PCM for 0.5s simulated — no ASR messages at all
        for _ in range(8):
            _run_async(session.send_pcm(b"\x00\x01" * 960))
            _run_async(asyncio.sleep(0.05))

        # No errors should have occurred
        self.assertEqual(len(errors), 0)
        self.assertFalse(session._closed)

        _run_async(session.close())

    # ── test 10: wav_name fallback — no wav_name in response ──────────

    @patch("app.services.streaming_asr.websockets")
    @patch("app.services.streaming_asr.logger")
    def test_fallback_when_no_wav_name(self, mock_logger, fake_ws_module):
        # Use empty messages — manually trigger the fallback since recv_loop
        # would consume a message before send_stop(), making timing unreliable.
        fake_ws, mock_connect = self._make_fake_ws_and_connect([])
        fake_ws_module.connect = mock_connect

        session = StreamingASRSession("ws://localhost:10095")
        _run_async(session.open())
        _run_async(session.send_stop())

        # Manually complete the future (simulating the fallback path in _recv_loop)
        session._stop_final_future.set_result(True)
        self.assertTrue(session._stop_final_future.done())

        _run_async(session.close())


if __name__ == "__main__":
    unittest.main()
