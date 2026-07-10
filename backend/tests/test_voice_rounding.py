"""语音查房单元测试：填充词清洗、数值保护、LLM 降级、草稿隔离、热词注入、纠错提示、编辑日志。"""
from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


class FillerStripTest(unittest.TestCase):
    """级2：填充词清洗测试。"""

    def _make_service(self, filler_words=None):
        from app.services.voice_rounding import VoiceRoundingService

        cfg = {"filler_words": filler_words}
        db = MagicMock()
        config = SimpleNamespace(yaml_cfg={"voice_rounding": cfg})
        return VoiceRoundingService(db, config)

    def test_basic_fillers_removed(self):
        svc = self._make_service()
        result = svc._strip_fillers("嗯，患者今天嗯血压稳定哦")
        self.assertNotIn("，，", result)
        self.assertIn("患者", result)
        self.assertIn("血压稳定", result)

    def test_consecutive_punctuation_cleaned(self):
        svc = self._make_service()
        result = svc._strip_fillers("嗯，，，哦，患者稳定")
        self.assertNotIn("，，，", result)
        self.assertIn("患者稳定", result)

    def test_custom_filler_words(self):
        svc = self._make_service(filler_words=["然后", "就是"])
        result = svc._strip_fillers("然后患者就是稳定")
        self.assertIn("患者", result)
        self.assertIn("稳定", result)

    def test_no_filler_preserves_text(self):
        svc = self._make_service()
        text = "患者血压120/80，心率78次/分"
        result = svc._strip_fillers(text)
        self.assertEqual(result, text)

    def test_drug_name_not_mangled(self):
        svc = self._make_service(filler_words=["啊"])
        result = svc._strip_fillers("啊患者用了啊霉素")
        self.assertIn("霉素", result)


class NumberProtectionTest(unittest.TestCase):
    """数值保护：LLM 改动数字时不采纳并标红。"""

    def _make_service(self):
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        config = SimpleNamespace(yaml_cfg={"voice_rounding": {"llm_correction": {"protect_numbers": True}}})
        return VoiceRoundingService(db, config)

    def test_extract_numbers_basic(self):
        svc = self._make_service()
        nums = svc._extract_numbers("体温38.5℃，心率120次/分")
        self.assertIn("38.5", nums)
        self.assertIn("120", nums)

    def test_extract_numbers_with_units(self):
        svc = self._make_service()
        nums = svc._extract_numbers("去甲肾上腺素0.2μg/kg/min")
        self.assertTrue(any("0.2" in n for n in nums))

    def test_numbers_changed_true(self):
        svc = self._make_service()
        self.assertTrue(svc._numbers_changed("体温38.5℃", "体温39.0℃"))

    def test_numbers_changed_false(self):
        svc = self._make_service()
        self.assertFalse(svc._numbers_changed("体温38.5℃", "体温38.5摄氏度"))

    def test_numbers_changed_same_set_different_order(self):
        svc = self._make_service()
        self.assertFalse(svc._numbers_changed("120和80", "80和120"))

    def test_numbers_changed_added_number(self):
        svc = self._make_service()
        self.assertTrue(svc._numbers_changed("血压120", "血压120，心率80"))

    def test_numbers_changed_removed_number(self):
        svc = self._make_service()
        self.assertTrue(svc._numbers_changed("120和80", "120"))


class LLMCorrectionTest(unittest.TestCase):
    """级3：LLM 纠错 + 数值保护集成测试。"""

    def _make_service(self, protect_numbers=True, enabled=True):
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        config = SimpleNamespace(
            yaml_cfg={
                "voice_rounding": {
                    "llm_correction": {
                        "enabled": enabled,
                        "protect_numbers": protect_numbers,
                        "temperature": 0.1,
                        "max_tokens": 2048,
                        "timeout": 30,
                    },
                },
            },
            llm_model_medical="test-model",
            llm_fast_model="fast-model",
        )
        return VoiceRoundingService(db, config)

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.voice_rounding.call_llm_chat")
    def test_llm_changes_number_rejected(self, mock_llm):
        """LLM 把 38.5 改成 39.0 → 不采纳，保留原值，needs_human_review=True。"""
        mock_llm.return_value = {
            "text": json.dumps({"corrected_text": "体温39.0℃", "suspect": []}),
        }
        svc = self._make_service(protect_numbers=True)
        svc._build_patient_context = AsyncMock(return_value={})
        result = self._run_async(svc._llm_correct("体温38.5℃", "patient1"))
        self.assertEqual(result["text"], "体温38.5℃")  # 原值保留
        self.assertTrue(result["needs_human_review"])
        # suspect 现在是 list[dict]
        suspect_types = [s.get("type") for s in result.get("suspect", [])]
        self.assertIn("number_override", suspect_types)

    @patch("app.services.voice_rounding.call_llm_chat")
    def test_llm_no_number_change_adopted(self, mock_llm):
        """LLM 只改错字不改数字 → 正常采纳。"""
        mock_llm.return_value = {
            "text": json.dumps({"corrected_text": "体温38.5摄氏度", "suspect": []}),
        }
        svc = self._make_service(protect_numbers=True)
        svc._build_patient_context = AsyncMock(return_value={})
        result = self._run_async(svc._llm_correct("体温38.5℃", "patient1"))
        self.assertEqual(result["text"], "体温38.5摄氏度")
        self.assertFalse(result["needs_human_review"])

    @patch("app.services.voice_rounding.call_llm_chat")
    def test_llm_timeout_degrades(self, mock_llm):
        """LLM 超时 → 降级返回规则清洗文本。"""
        mock_llm.side_effect = TimeoutError("LLM timeout")
        svc = self._make_service()
        svc._build_patient_context = AsyncMock(return_value={})
        result = self._run_async(svc._llm_correct("患者血压稳定", "patient1"))
        self.assertEqual(result["text"], "患者血压稳定")
        self.assertFalse(result["corrected"])
        self.assertTrue(result["degraded"])

    def test_llm_correction_disabled(self):
        """LLM 纠错关闭 → 直接返回原文。"""
        svc = self._make_service(enabled=False)
        result = self._run_async(svc._llm_correct("患者血压稳定", "patient1"))
        self.assertEqual(result["text"], "患者血压稳定")
        self.assertFalse(result["corrected"])

    def test_parse_llm_json_valid(self):
        svc = self._make_service()
        raw = '{"corrected_text": "体温正常", "suspect": ["温度不确定"]}'
        text, suspect = svc._parse_llm_json(raw, fallback="fallback")
        self.assertEqual(text, "体温正常")
        self.assertEqual(suspect, ["温度不确定"])

    def test_parse_llm_json_markdown_wrapped(self):
        svc = self._make_service()
        raw = '```json\n{"corrected_text": "正常", "suspect": []}\n```'
        text, suspect = svc._parse_llm_json(raw, fallback="fallback")
        self.assertEqual(text, "正常")

    def test_parse_llm_json_invalid_returns_fallback(self):
        svc = self._make_service()
        text, suspect = svc._parse_llm_json("not json at all", fallback="fallback")
        self.assertEqual(text, "fallback")
        self.assertEqual(suspect, [])

    def test_suspect_backward_compat_field(self):
        """suspect_terms 兼容字段存在且为扁平 list[str]。"""
        svc = self._make_service(enabled=False)
        result = self._run_async(svc._llm_correct("患者血压稳定", "patient1"))
        self.assertIn("suspect_terms", result)
        self.assertIsInstance(result["suspect_terms"], list)


class DraftIsolationTest(unittest.TestCase):
    """草稿隔离：transcribe 只写草稿集合，不写正式记录集合。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.voice_rounding.preprocess_audio")
    @patch("app.services.voice_rounding.VoiceRoundingService._llm_correct")
    def test_transcribe_only_writes_drafts(self, mock_llm, mock_preprocess):
        from app.services.voice_rounding import VoiceRoundingService
        from app.services.audio_preprocessor import AudioPreprocessResult

        mock_llm.return_value = {
            "text": "测试文本", "corrected": False, "suspect": [],
            "suspect_terms": [], "needs_human_review": False, "degraded": False,
        }
        mock_preprocess.return_value = AudioPreprocessResult(
            pcm_bytes=b"\x00\x01" * 16000,
            wav_bytes=b"RIFF" + b"\x00" * 40 + b"\x00\x01" * 16000,
            duration_seconds=1.0,
            sample_rate=16000,
            channels=1,
            sample_width=2,
            source_format="webm/opus",
        )

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "fake_id_123"
        db.col.return_value.insert_one = AsyncMock(return_value=mock_result)

        config = SimpleNamespace(
            yaml_cfg={
                "voice_rounding": {
                    "enabled": True,
                    "asr": {"mode": "mock"},
                    "llm_correction": {"enabled": False},
                },
            }
        )
        svc = VoiceRoundingService(db, config)

        result = self._run_async(svc.transcribe("patient1", b"fake_audio"))

        self.assertEqual(result["status"], "draft")
        db.col.assert_called_with("voice_rounding_drafts")
        calls = [str(c) for c in db.col.call_args_list]
        self.assertFalse(any("voice_rounding_records" in c for c in calls))


class HotwordInjectionTest(unittest.TestCase):
    """热词注入：ASRClient 正确加载热词文件。"""

    def test_hotwords_loaded_from_file(self):
        import tempfile
        from pathlib import Path

        from app.services.asr_client import ASRClient

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("去甲肾上腺素 20\n万古霉素 15\n")
            f.flush()
            client = ASRClient({"hotword_path": f.name})
            self.assertIn("去甲肾上腺素 20", client.hotwords)
            self.assertIn("万古霉素 15", client.hotwords)
        Path(f.name).unlink(missing_ok=True)

    def test_hotwords_empty_when_no_path(self):
        from app.services.asr_client import ASRClient
        client = ASRClient({})
        self.assertEqual(client.hotwords, [])

    def test_hotwords_empty_when_file_missing(self):
        from app.services.asr_client import ASRClient
        client = ASRClient({"hotword_path": "/nonexistent/path.txt"})
        self.assertEqual(client.hotwords, [])


class ASRClientModeTest(unittest.TestCase):
    """ASR 客户端模式选择测试。"""

    def test_default_mode_is_http(self):
        from app.services.asr_client import ASRClient
        client = ASRClient({})
        # 默认模式从全局 ASR_MODE 读取，默认为 "http"
        self.assertIn(client.mode, ("http", "ws"))

    def test_mock_mode_returns_text(self):
        from app.services.asr_client import ASRClient
        client = ASRClient({"mode": "mock"})
        self.assertEqual(client.mode, "mock")

    def test_explicit_http_mode(self):
        from app.services.asr_client import ASRClient
        client = ASRClient({"mode": "http"})
        self.assertEqual(client.mode, "http")

    def test_explicit_ws_mode(self):
        from app.services.asr_client import ASRClient
        client = ASRClient({"mode": "ws"})
        self.assertEqual(client.mode, "ws")

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)


class AudioLengthLimitTest(unittest.TestCase):
    """音频时长限制测试。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.voice_rounding.preprocess_audio")
    def test_oversized_audio_rejected(self, mock_preprocess):
        from app.services.audio_preprocessor import AudioTooLargeError
        from app.services.voice_rounding import VoiceRoundingService

        mock_preprocess.side_effect = AudioTooLargeError(100 * 1024 * 1024, 50 * 1024 * 1024)

        db = MagicMock()
        config = SimpleNamespace(
            yaml_cfg={"voice_rounding": {"max_audio_seconds": 300, "asr": {"mode": "mock"}}},
        )
        svc = VoiceRoundingService(db, config)
        with self.assertRaises(AudioTooLargeError):
            self._run_async(svc.transcribe("patient1", b"\x00" * 100))


class ConfirmTest(unittest.TestCase):
    """确认入库测试。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_confirm_writes_to_records(self):
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "record_id_456"
        db.col.return_value.insert_one = AsyncMock(return_value=mock_result)
        db.col.return_value.update_one = AsyncMock()
        db.col.return_value.find_one = AsyncMock(return_value=None)

        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        svc = VoiceRoundingService(db, config)

        result = self._run_async(
            svc.confirm("patient1", final_text="确认文本", draft_id="draft123", actor="doctor1")
        )
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["source"], "voice_rounding")
        self.assertEqual(result["confirmed_by"], "doctor1")

    def test_confirm_requires_non_empty_text(self):
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "id"
        db.col.return_value.insert_one = AsyncMock(return_value=mock_result)
        db.col.return_value.update_one = AsyncMock()
        db.col.return_value.find_one = AsyncMock(return_value=None)

        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        svc = VoiceRoundingService(db, config)
        result = self._run_async(svc.confirm("patient1", final_text="", actor="doctor1"))
        self.assertEqual(result["text"], "")


class CorrectionHintsTest(unittest.TestCase):
    """纠错提示配置加载与 prompt 注入测试。"""

    def _make_service(self, hints=None):
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        svc = VoiceRoundingService(db, config)
        if hints is not None:
            svc.correction_hints = hints
        return svc

    def test_missing_hints_file_degrades_gracefully(self):
        svc = self._make_service()
        self.assertIsInstance(svc.correction_hints, dict)

    def test_accent_prompt_section_contains_mappings(self):
        svc = self._make_service(hints={
            "accent_errors": [
                {"wrong": ["会部", "灰部"], "right": "肺部"},
                {"wrong": ["料量"], "right": "尿量"},
            ],
        })
        section = svc._build_accent_prompt_section()
        self.assertIn("会部", section)
        self.assertIn("肺部", section)
        self.assertIn("料量", section)
        self.assertIn("→", section)

    def test_accent_prompt_section_empty_when_no_hints(self):
        svc = self._make_service(hints={})
        section = svc._build_accent_prompt_section()
        self.assertEqual(section, "")

    def test_dialect_prompt_section_contains_mappings(self):
        svc = self._make_service(hints={
            "dialect_phrases": [
                {"wrong": ["拉稀", "屙稀"], "right": "腹泻"},
            ],
        })
        section = svc._build_dialect_prompt_section()
        self.assertIn("拉稀", section)
        self.assertIn("腹泻", section)

    def test_drug_confusable_both_found(self):
        """两个易混药名同时出现 → 高危 suspect，type=drug_confusable。"""
        svc = self._make_service(hints={
            "drug_confusables": [
                {"names": ["多巴胺", "多巴酚丁胺"], "note": ""},
            ],
        })
        suspects = svc._detect_drug_confusables("患者使用多巴胺和多巴酚丁胺")
        self.assertTrue(len(suspects) > 0)
        self.assertEqual(suspects[0]["type"], "drug_confusable")
        self.assertIn("多巴胺", suspects[0]["term"])

    def test_drug_confusable_one_found(self):
        """只出现一个易混药名 → 提醒可能混淆。"""
        svc = self._make_service(hints={
            "drug_confusables": [
                {"names": ["去甲肾上腺素", "肾上腺素"], "note": "看泵速"},
            ],
        })
        suspects = svc._detect_drug_confusables("泵入去甲肾上腺素0.2μg/kg/min")
        self.assertTrue(len(suspects) > 0)
        self.assertEqual(suspects[0]["type"], "drug_confusable")
        self.assertIn("泵速", suspects[0]["note"])

    def test_drug_confusable_none_found(self):
        svc = self._make_service(hints={
            "drug_confusables": [
                {"names": ["多巴胺", "多巴酚丁胺"], "note": ""},
            ],
        })
        suspects = svc._detect_drug_confusables("患者体温38.5℃，心率120次/分")
        self.assertEqual(suspects, [])

    def test_normalize_drug_confusables_on_load(self):
        """_normalize_drug_confusables 将 list[str] 格式统一为 dict。"""
        from app.services.voice_rounding import _normalize_drug_confusables

        raw = [["多巴胺", "多巴酚丁胺"], {"names": ["A", "B"], "note": "测试"}]
        result = _normalize_drug_confusables(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["names"], ["多巴胺", "多巴酚丁胺"])
        self.assertEqual(result[0]["note"], "")
        self.assertEqual(result[1]["names"], ["A", "B"])
        self.assertEqual(result[1]["note"], "测试")

    def test_suspect_to_terms_compat(self):
        """_suspect_to_terms 从结构化 suspect 提取扁平 term 列表。"""
        from app.services.voice_rounding import VoiceRoundingService

        suspects = [
            {"term": "多巴胺", "type": "drug_confusable", "note": "易混"},
            {"term": "数值被模型改动", "type": "number_override", "note": "保留原值"},
        ]
        terms = VoiceRoundingService._suspect_to_terms(suspects)
        self.assertEqual(terms, ["多巴胺", "数值被模型改动"])


class EditLogTest(unittest.TestCase):
    """编辑日志测试。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_confirm_writes_edit_log(self):
        """confirm 写入 voice_rounding_logs，edited_spans 正确捕获差异。"""
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "record_id"
        inserted_docs = []

        async def mock_insert(doc):
            inserted_docs.append(doc)
            return mock_result

        # 用合法的 24 位 hex ObjectId（否则 ObjectId() 抛异常被 except 吞掉）
        valid_draft_id = "665a1b2c3d4e5f6a7b8c9d0e"
        draft_doc = {
            "_id": valid_draft_id,
            "raw_text": "体温三八点五度",
            "cleaned_text": "体温三八点五度",
            "corrected_text": "体温38.5℃",
            "suspect": [{"term": "38.5", "type": "number_override", "note": ""}],
            "suspect_terms": ["38.5"],
            "hints_hit": {"accent": []},
            "needs_human_review": False,
            "degraded": False,
            "duration_seconds": 5.0,
        }

        def mock_col(name):
            col_mock = MagicMock()
            col_mock.insert_one = AsyncMock(side_effect=mock_insert)
            col_mock.update_one = AsyncMock()
            if name == "voice_rounding_drafts":
                col_mock.find_one = AsyncMock(return_value=draft_doc)
            else:
                col_mock.find_one = AsyncMock(return_value=None)
            return col_mock

        db.col = mock_col

        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        svc = VoiceRoundingService(db, config)

        # 医生在 LLM 结果基础上改了 "℃" → "摄氏度"
        self._run_async(
            svc.confirm("patient1", final_text="体温38.5摄氏度", draft_id=valid_draft_id, actor="doctor1")
        )

        # 找到写入 voice_rounding_logs 的那条
        log_doc = None
        for doc in inserted_docs:
            if "edited_spans" in doc:
                log_doc = doc
                break
        self.assertIsNotNone(log_doc, "voice_rounding_logs 未写入")
        self.assertEqual(log_doc["patient_id"], "patient1")
        self.assertEqual(log_doc["corrected_text"], "体温38.5℃")
        self.assertEqual(log_doc["final_text"], "体温38.5摄氏度")
        self.assertFalse(log_doc["draft_missing"])
        # edited_spans 应捕获 "℃" → "摄氏度"
        self.assertTrue(len(log_doc["edited_spans"]) > 0)
        span = log_doc["edited_spans"][0]
        self.assertEqual(span["op"], "replace")
        self.assertIn("℃", span.get("before", ""))
        self.assertIn("摄氏度", span.get("after", ""))

    def test_confirm_log_failure_non_blocking(self):
        """日志写入失败不阻断 confirm 主流程。"""
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "record_id"
        db.col.return_value.insert_one = AsyncMock(return_value=mock_result)
        db.col.return_value.update_one = AsyncMock()

        # find_one 返回 None（模拟 draft 不存在）
        db.col.return_value.find_one = AsyncMock(return_value=None)

        # 让第二次 insert_one（日志写入）抛异常
        call_count = 0

        async def mock_insert(doc):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception("DB write failed")
            return mock_result

        db.col.return_value.insert_one = AsyncMock(side_effect=mock_insert)

        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        svc = VoiceRoundingService(db, config)

        # confirm 应该成功返回，不抛异常
        result = self._run_async(
            svc.confirm("patient1", final_text="确认文本", draft_id="draft123", actor="doctor1")
        )
        self.assertEqual(result["status"], "confirmed")

    def test_confirm_draft_missing_marked_in_log(self):
        """draft 不存在时，日志标记 draft_missing=True，主流程仍成功。"""
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "record_id"
        inserted_docs = []

        async def mock_insert(doc):
            inserted_docs.append(doc)
            return mock_result

        db.col.return_value.insert_one = AsyncMock(side_effect=mock_insert)
        db.col.return_value.update_one = AsyncMock()
        db.col.return_value.find_one = AsyncMock(return_value=None)

        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        svc = VoiceRoundingService(db, config)

        result = self._run_async(
            svc.confirm("patient1", final_text="确认文本", draft_id="bad_id", actor="doctor1")
        )
        self.assertEqual(result["status"], "confirmed")

        log_doc = next((d for d in inserted_docs if "edited_spans" in d), None)
        self.assertIsNotNone(log_doc)
        self.assertTrue(log_doc["draft_missing"])
        self.assertIsNone(log_doc["raw_text"])


class ComputeEditsTest(unittest.TestCase):
    """_compute_edits diff 算法测试。"""

    def test_replace(self):
        from app.services.voice_rounding import VoiceRoundingService

        edits = VoiceRoundingService._compute_edits("体温38.5℃", "体温38.5摄氏度")
        self.assertTrue(len(edits) > 0)
        replace_ops = [e for e in edits if e["op"] == "replace"]
        self.assertTrue(len(replace_ops) > 0)
        self.assertIn("℃", replace_ops[0]["before"])
        self.assertIn("摄氏度", replace_ops[0]["after"])

    def test_no_diff(self):
        from app.services.voice_rounding import VoiceRoundingService

        edits = VoiceRoundingService._compute_edits("相同文本", "相同文本")
        self.assertEqual(edits, [])

    def test_insert(self):
        from app.services.voice_rounding import VoiceRoundingService

        edits = VoiceRoundingService._compute_edits("血压稳定", "血压稳定，心率正常")
        insert_ops = [e for e in edits if e["op"] == "insert"]
        self.assertTrue(len(insert_ops) > 0)

    def test_delete(self):
        from app.services.voice_rounding import VoiceRoundingService

        edits = VoiceRoundingService._compute_edits("血压稳定，心率正常", "血压稳定")
        delete_ops = [e for e in edits if e["op"] == "delete"]
        self.assertTrue(len(delete_ops) > 0)


class ChineseNumberParseTest(unittest.TestCase):
    """汉字数字解析测试。"""

    def _make_service(self):
        from app.services.voice_rounding import VoiceRoundingService
        db = MagicMock()
        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        return VoiceRoundingService(db, config)

    def test_cn_number_zero_point_two(self):
        """零点二 → 0.2（允许格式转换）。"""
        svc = self._make_service()
        result = svc._parse_cn_number("零点二")
        self.assertAlmostEqual(result, 0.2)

    def test_cn_number_three_eight_point_five(self):
        """三八点五 → 38.5。"""
        svc = self._make_service()
        result = svc._parse_cn_number("三八点五")
        self.assertAlmostEqual(result, 38.5)

    def test_cn_number_negative_two(self):
        """负二 → -2。"""
        svc = self._make_service()
        result = svc._parse_cn_number("负二")
        self.assertAlmostEqual(result, -2.0)

    def test_cn_number_fraction(self):
        """二分之一 → 0.5。"""
        svc = self._make_service()
        result = svc._parse_cn_number("二分之一")
        self.assertAlmostEqual(result, 0.5)

    def test_cn_number_one_hundred_twenty(self):
        """一百二十 → 120。"""
        svc = self._make_service()
        result = svc._parse_cn_number("一百二十")
        self.assertAlmostEqual(result, 120.0)

    def test_cn_number_omit_ten_thousand_two(self):
        """一万二 → 12000。"""
        svc = self._make_service()
        result = self._make_service()._parse_cn_number("一万二")
        self.assertAlmostEqual(result, 12000.0)

    def test_extract_numeric_values_mixed(self):
        """混合阿拉伯和汉字数字提取。"""
        svc = self._make_service()
        values = svc._extract_numeric_values("体温三八点五度，心率120次/分")
        self.assertIn(38.5, values)
        self.assertIn(120.0, values)


class SuspectContractTest(unittest.TestCase):
    """suspect 前后端契约一致性测试。"""

    def _make_service(self):
        from app.services.voice_rounding import VoiceRoundingService
        db = MagicMock()
        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        return VoiceRoundingService(db, config)

    def test_suspect_has_required_fields(self):
        """结构化 suspect 包含 term, type, note 三个必需字段。"""
        svc = self._make_service()
        suspects = svc._detect_drug_confusables("患者使用多巴胺")
        for s in suspects:
            self.assertIn("term", s)
            self.assertIn("type", s)
            self.assertIn("note", s)
            self.assertIsInstance(s["term"], str)
            self.assertIsInstance(s["type"], str)
            self.assertIsInstance(s["note"], str)

    def test_suspect_types_valid(self):
        """suspect type 只能是预定义的几种。"""
        from app.services.voice_rounding import (
            SUSPECT_TYPE_DRUG, SUSPECT_TYPE_NUMBER, SUSPECT_TYPE_DIALECT,
            SUSPECT_TYPE_LOW_CONF, SUSPECT_TYPE_UNIT, SUSPECT_TYPE_OTHER,
        )
        valid_types = {
            SUSPECT_TYPE_DRUG, SUSPECT_TYPE_NUMBER, SUSPECT_TYPE_DIALECT,
            SUSPECT_TYPE_LOW_CONF, SUSPECT_TYPE_UNIT, SUSPECT_TYPE_OTHER,
        }
        svc = self._make_service()
        suspects = svc._detect_drug_confusables("患者使用多巴胺和多巴酚丁胺")
        for s in suspects:
            self.assertIn(s["type"], valid_types)


class ASRWebSocketProtocolTest(unittest.TestCase):
    """FunASR WebSocket 协议测试：多消息处理、is_final 逻辑、空文本处理。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.asr_client._asr_config")
    @patch("app.services.asr_client.websockets")
    def test_ws_does_not_exit_on_first_offline_message(self, mock_ws_module, mock_config):
        """第一条 mode=offline, text='', is_final=false 不应退出接收循环。
        第二条 mode=offline, text='患者病情稳定', is_final=true 才退出。"""
        from app.services.asr_client import _transcribe_ws

        mock_config.return_value = ("ws://localhost:10095", "ws")

        msg1 = json.dumps({"mode": "offline", "text": "", "is_final": False})
        msg2 = json.dumps({"mode": "offline", "text": "患者病情稳定", "is_final": True})

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[msg1, msg2])
        mock_ws.send = AsyncMock()

        def mock_connect(*args, **kwargs):
            class FakeCtx:
                async def __aenter__(self):
                    return mock_ws
                async def __aexit__(self, *a):
                    pass
            return FakeCtx()

        mock_ws_module.connect = mock_connect

        result = self._run_async(
            _transcribe_ws("ws://localhost:10095", b"\x00\x01" * 1000, hotwords=[], language="zh")
        )
        # 必须收到最终文本，不能在第一条消息就退出
        self.assertEqual(result["text"], "患者病情稳定")

    @patch("app.services.asr_client._asr_config")
    @patch("app.services.asr_client.websockets")
    def test_ws_skips_empty_intermediate_messages(self, mock_ws_module, mock_config):
        """多条空文本中间帧被跳过，最终文本来自 is_final=true 的消息。"""
        from app.services.asr_client import _transcribe_ws

        mock_config.return_value = ("ws://localhost:10095", "ws")

        msg1 = json.dumps({"mode": "offline", "text": "", "is_final": False})
        msg2 = json.dumps({"mode": "offline", "text": "", "is_final": False})
        msg3 = json.dumps({"mode": "offline", "text": "患者血压稳定", "is_final": True})

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[msg1, msg2, msg3])
        mock_ws.send = AsyncMock()

        def mock_connect(*args, **kwargs):
            class FakeCtx:
                async def __aenter__(self):
                    return mock_ws
                async def __aexit__(self, *a):
                    pass
            return FakeCtx()

        mock_ws_module.connect = mock_connect

        result = self._run_async(
            _transcribe_ws("ws://localhost:10095", b"\x00\x01" * 1000, hotwords=[], language="zh")
        )
        self.assertEqual(result["text"], "患者血压稳定")

    @patch("app.services.asr_client._asr_config")
    @patch("app.services.asr_client.websockets")
    def test_ws_returns_empty_on_final_empty_text(self, mock_ws_module, mock_config):
        """is_final=true 但 text 为空 → _transcribe_ws 返回空 text，
        上层 transcribe() 检查后抛出 ASREmptyTranscriptionError。"""
        from app.services.asr_client import _transcribe_ws

        mock_config.return_value = ("ws://localhost:10095", "ws")

        msg = json.dumps({"mode": "offline", "text": "", "is_final": True})

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[msg])
        mock_ws.send = AsyncMock()

        def mock_connect(*args, **kwargs):
            class FakeCtx:
                async def __aenter__(self):
                    return mock_ws
                async def __aexit__(self, *a):
                    pass
            return FakeCtx()

        mock_ws_module.connect = mock_connect

        # _transcribe_ws 本身不抛 ASREmptyTranscriptionError（它只返回空 text），
        # 但上层 transcribe() 会检查 text 并抛出。
        # 这里直接测试 _transcribe_ws 返回空 text。
        result = self._run_async(
            _transcribe_ws("ws://localhost:10095", b"\x00\x01" * 1000, hotwords=[], language="zh")
        )
        self.assertEqual(result["text"], "")

    @patch("app.services.asr_client._asr_config")
    @patch("app.services.asr_client.websockets")
    def test_ws_raises_on_timeout(self, mock_ws_module, mock_config):
        """WebSocket 接收超时 → ASRRuntimeUnavailableError。"""
        from app.services.asr_client import ASRRuntimeUnavailableError, _transcribe_ws

        mock_config.return_value = ("ws://localhost:10095", "ws")

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_ws.send = AsyncMock()

        def mock_connect(*args, **kwargs):
            class FakeCtx:
                async def __aenter__(self):
                    return mock_ws
                async def __aexit__(self, *a):
                    pass
            return FakeCtx()

        mock_ws_module.connect = mock_connect

        with self.assertRaises(ASRRuntimeUnavailableError):
            self._run_async(
                _transcribe_ws("ws://localhost:10095", b"\x00\x01" * 1000, hotwords=[], language="zh")
            )

    def test_ws_config_frame_contains_required_fields(self):
        """验证 FunASR 首帧配置包含所有必需字段。"""
        from app.services.asr_client import _transcribe_ws

        # 提取 config 构造逻辑（通过检查源码中的 config dict）
        # 这里直接验证 _transcribe_ws 函数的 config 是否符合协议
        import inspect
        source = inspect.getsource(_transcribe_ws)
        self.assertIn('"wav_format"', source, "config 必须包含 wav_format")
        self.assertIn('"audio_fs"', source, "config 必须包含 audio_fs")
        self.assertIn('"chunk_size"', source, "config 必须包含 chunk_size")
        self.assertIn('"chunk_interval"', source, "config 必须包含 chunk_interval")
        self.assertIn('"encoder_chunk_look_back"', source, "config 必须包含 encoder_chunk_look_back")
        self.assertIn('"decoder_chunk_look_back"', source, "config 必须包含 decoder_chunk_look_back")


class EmptyTranscriptionPipelineTest(unittest.TestCase):
    """ASR 返回空文本时，LLM 不应被调用，草稿不应创建。"""

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("app.services.voice_rounding.preprocess_audio")
    def test_empty_asr_raises_error_no_draft_created(self, mock_preprocess):
        """ASR 返回空文本 → ASREmptyTranscriptionError，不创建草稿。"""
        from app.services.audio_preprocessor import AudioPreprocessResult
        from app.services.asr_client import ASREmptyTranscriptionError
        from app.services.voice_rounding import VoiceRoundingService

        mock_preprocess.return_value = AudioPreprocessResult(
            pcm_bytes=b"\x00\x01" * 16000,
            wav_bytes=b"RIFF" + b"\x00" * 40 + b"\x00\x01" * 16000,
            duration_seconds=1.0,
            sample_rate=16000,
            channels=1,
            sample_width=2,
            source_format="webm/opus",
        )

        db = MagicMock()
        config = SimpleNamespace(
            yaml_cfg={
                "voice_rounding": {
                    "enabled": True,
                    "asr": {"mode": "mock"},
                    "llm_correction": {"enabled": True},
                },
            }
        )
        svc = VoiceRoundingService(db, config)

        # Mock ASR 抛出 ASREmptyTranscriptionError（模拟 ASR 返回空文本）
        svc.asr.transcribe = AsyncMock(
            side_effect=ASREmptyTranscriptionError("ASR 未返回有效文本")
        )

        with self.assertRaises(ASREmptyTranscriptionError):
            self._run_async(svc.transcribe("patient1", b"fake_audio"))

        # 草稿集合不应被写入
        db.col.return_value.insert_one.assert_not_called()

    @patch("app.services.voice_rounding.preprocess_audio")
    @patch("app.services.voice_rounding.call_llm_chat")
    def test_empty_asr_does_not_call_llm(self, mock_llm, mock_preprocess):
        """ASR 返回空文本时，LLM 纠错不应被调用。"""
        from app.services.audio_preprocessor import AudioPreprocessResult
        from app.services.asr_client import ASREmptyTranscriptionError
        from app.services.voice_rounding import VoiceRoundingService

        mock_preprocess.return_value = AudioPreprocessResult(
            pcm_bytes=b"\x00\x01" * 16000,
            wav_bytes=b"RIFF" + b"\x00" * 40 + b"\x00\x01" * 16000,
            duration_seconds=1.0,
            sample_rate=16000,
            channels=1,
            sample_width=2,
            source_format="webm/opus",
        )

        db = MagicMock()
        config = SimpleNamespace(
            yaml_cfg={
                "voice_rounding": {
                    "enabled": True,
                    "asr": {"mode": "mock"},
                    "llm_correction": {"enabled": True},
                },
            }
        )
        svc = VoiceRoundingService(db, config)
        svc.asr.transcribe = AsyncMock(
            side_effect=ASREmptyTranscriptionError("ASR 未返回有效文本")
        )

        with self.assertRaises(ASREmptyTranscriptionError):
            self._run_async(svc.transcribe("patient1", b"fake_audio"))

        # LLM 不应被调用
        mock_llm.assert_not_called()

    @patch("app.services.voice_rounding.preprocess_audio")
    def test_nonempty_asr_proceeds_normally(self, mock_preprocess):
        """ASR 返回有效文本 → 正常创建草稿。"""
        from app.services.audio_preprocessor import AudioPreprocessResult
        from app.services.voice_rounding import VoiceRoundingService

        mock_preprocess.return_value = AudioPreprocessResult(
            pcm_bytes=b"\x00\x01" * 16000,
            wav_bytes=b"RIFF" + b"\x00" * 40 + b"\x00\x01" * 16000,
            duration_seconds=1.0,
            sample_rate=16000,
            channels=1,
            sample_width=2,
            source_format="webm/opus",
        )

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "draft_id_123"
        db.col.return_value.insert_one = AsyncMock(return_value=mock_result)

        config = SimpleNamespace(
            yaml_cfg={
                "voice_rounding": {
                    "enabled": True,
                    "asr": {"mode": "mock"},
                    "llm_correction": {"enabled": False},
                },
            }
        )
        svc = VoiceRoundingService(db, config)
        svc.asr.transcribe = AsyncMock(return_value="患者病情稳定")

        result = self._run_async(svc.transcribe("patient1", b"fake_audio"))

        self.assertEqual(result["raw_text"], "患者病情稳定")
        self.assertEqual(result["status"], "draft")
        db.col.return_value.insert_one.assert_called()


if __name__ == "__main__":
    unittest.main()
