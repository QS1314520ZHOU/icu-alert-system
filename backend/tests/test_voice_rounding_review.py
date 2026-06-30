"""语音查房错例 review 服务测试：安全写回、药名拦截、回滚、审计。"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import yaml

# 合法的 24 位 hex ObjectId
VALID_OID = "665a1b2c3d4e5f6a7b8c9d0e"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_db():
    """创建一个支持 async 的 db mock，所有集合操作都返回 AsyncMock。"""
    db = MagicMock()
    col_mock = MagicMock()
    col_mock.find_one = AsyncMock(return_value=None)
    col_mock.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=MagicMock(__aiter__=lambda s: s, __anext__=AsyncMock(side_effect=StopAsyncIteration)))))))
    col_mock.update_one = AsyncMock()
    col_mock.insert_one = AsyncMock()
    db.col = MagicMock(return_value=col_mock)
    db._col_mock = col_mock
    db._find_one_result = None

    # 让 find_one 返回 _find_one_result
    async def _find_one(*args, **kwargs):
        return db._find_one_result
    col_mock.find_one = AsyncMock(side_effect=_find_one)

    return db


class DecideCandidateDrugBlockTest(unittest.TestCase):
    """药名候选拒绝写回（医疗安全红线）。"""

    def test_drug_confusable_accept_rejected(self):
        from app.services.voice_rounding_review import decide_candidate

        db = _mock_db()
        db._find_one_result = {
            "_id": VALID_OID, "status": "pending", "is_drug_confusable": True,
            "before_variants": ["多巴酚丁胺"], "after": "多巴胺",
        }

        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        result = _run(decide_candidate(db, config, VALID_OID, action="accept", reviewer="admin"))
        self.assertEqual(result["code"], 403)
        self.assertIn("药名", result["message"])


class SafeWriteHintsTest(unittest.TestCase):
    """安全写回 hints yaml 测试。"""

    def test_normal_accept_writes_yaml_and_creates_backup(self):
        from app.services.voice_rounding_review import decide_candidate

        with tempfile.TemporaryDirectory() as tmp:
            hints_path = Path(tmp) / "hints.yaml"
            original = {
                "accent_errors": [{"wrong": ["旧错字"], "right": "旧正确"}],
                "dialect_phrases": [], "drug_confusables": [],
            }
            hints_path.write_text(yaml.dump(original, allow_unicode=True), encoding="utf-8")

            db = _mock_db()
            candidate = {
                "_id": VALID_OID, "status": "pending", "is_drug_confusable": False,
                "before_variants": ["会部", "灰部"], "after": "肺部",
                "suggested_category": "accent_errors",
            }
            db._find_one_result = candidate

            config = SimpleNamespace(yaml_cfg={
                "voice_rounding": {"correction_hints_path": str(hints_path)},
            })
            result = _run(decide_candidate(db, config, VALID_OID, action="accept", reviewer="doctor1"))
            self.assertEqual(result["code"], 0)

            updated = yaml.safe_load(hints_path.read_text(encoding="utf-8"))
            self.assertEqual(len(updated["accent_errors"]), 2)
            self.assertEqual(updated["accent_errors"][-1]["right"], "肺部")

            backups = list(Path(tmp).glob("hints.yaml.bak.*"))
            self.assertEqual(len(backups), 1)

    def test_dedup_on_accept(self):
        """已存在的对照 → 标 accepted 但不重复写入。"""
        from app.services.voice_rounding_review import decide_candidate

        with tempfile.TemporaryDirectory() as tmp:
            hints_path = Path(tmp) / "hints.yaml"
            original = {
                "accent_errors": [{"wrong": ["会部", "灰部"], "right": "肺部"}],
                "dialect_phrases": [], "drug_confusables": [],
            }
            hints_path.write_text(yaml.dump(original, allow_unicode=True), encoding="utf-8")

            db = _mock_db()
            db._find_one_result = {
                "_id": VALID_OID, "status": "pending", "is_drug_confusable": False,
                "before_variants": ["会部", "灰部"], "after": "肺部",
                "suggested_category": "accent_errors",
            }

            config = SimpleNamespace(yaml_cfg={
                "voice_rounding": {"correction_hints_path": str(hints_path)},
            })
            result = _run(decide_candidate(db, config, VALID_OID, action="accept", reviewer="doctor1"))
            self.assertEqual(result["code"], 0)
            # dedup: 标 accepted 但不重复写入
            self.assertIn("已存在", result["message"])

            after = yaml.safe_load(hints_path.read_text(encoding="utf-8"))
            self.assertEqual(len(after["accent_errors"]), 1)

    def test_yaml_corruption_rollback(self):
        """写后解析失败 → 回滚到备份。"""
        from app.services.voice_rounding_review import _safe_write_hints_yaml

        with tempfile.TemporaryDirectory() as tmp:
            hints_path = Path(tmp) / "hints.yaml"
            original = {"accent_errors": [], "dialect_phrases": []}
            hints_path.write_text(yaml.dump(original, allow_unicode=True), encoding="utf-8")

            # 模拟写入后文件损坏：在 yaml.dump 写完后，手动写垃圾到文件
            # 通过 patch yaml.safe_load 在重新读取时抛异常
            import app.services.voice_rounding_review as mod
            original_safe_load = mod.yaml.safe_load
            call_count = [0]

            def failing_safe_load(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] > 1:
                    # 第二次调用（写后校验）→ 模拟解析失败
                    raise ValueError("模拟 yaml 损坏")
                return original_safe_load(*args, **kwargs)

            db = MagicMock()
            with patch.object(mod.yaml, "safe_load", side_effect=failing_safe_load):
                result = _run(_safe_write_hints_yaml(
                    hints_path=str(hints_path),
                    category="accent_errors",
                    new_entry={"wrong": ["测试"], "right": "正确"},
                    db=db, reviewer="admin", candidate_id="id1",
                ))

            self.assertFalse(result["success"])
            # 原文件应保持不变（回滚）
            after = yaml.safe_load(hints_path.read_text(encoding="utf-8"))
            self.assertEqual(after, original)


class RejectCandidateTest(unittest.TestCase):
    def test_reject_updates_status(self):
        from app.services.voice_rounding_review import decide_candidate

        db = _mock_db()
        db._find_one_result = {
            "_id": VALID_OID, "status": "pending",
            "before_variants": ["A"], "after": "B",
        }

        config = SimpleNamespace(yaml_cfg={"voice_rounding": {}})
        result = _run(decide_candidate(db, config, VALID_OID, action="reject", reviewer="admin"))
        self.assertEqual(result["code"], 0)
        self.assertIn("驳回", result["message"])


class ListCandidatesTest(unittest.TestCase):
    def test_list_returns_drug_first(self):
        from app.services.voice_rounding_review import list_candidates

        db = MagicMock()
        docs = [
            {"_id": "1", "is_drug_confusable": False, "systematic_score": 0.8, "status": "pending"},
            {"_id": "2", "is_drug_confusable": True, "systematic_score": 0.5, "status": "pending"},
        ]

        class MockCursor:
            def sort(self, *a, **kw): return self
            def limit(self, *a, **kw): return self
            def __aiter__(self): return self._aiter()
            async def _aiter(self):
                # 模拟排序：drug 置顶
                yield docs[1]
                yield docs[0]

        db.col.return_value.find = MagicMock(return_value=MockCursor())
        result = _run(list_candidates(db, status="pending"))
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0]["is_drug_confusable"])


class ReloadHintsTest(unittest.TestCase):
    def test_reload_updates_hints(self):
        from app.services.voice_rounding import VoiceRoundingService

        with tempfile.TemporaryDirectory() as tmp:
            hints_path = Path(tmp) / "hints.yaml"
            v1 = {"accent_errors": [{"wrong": ["A"], "right": "B"}], "dialect_phrases": [], "drug_confusables": []}
            hints_path.write_text(yaml.dump(v1, allow_unicode=True), encoding="utf-8")

            db = MagicMock()
            config = SimpleNamespace(yaml_cfg={
                "voice_rounding": {"correction_hints_path": str(hints_path)},
            })
            svc = VoiceRoundingService(db, config)
            self.assertEqual(len(svc.correction_hints["accent_errors"]), 1)

            v2 = {"accent_errors": [{"wrong": ["A"], "right": "B"}, {"wrong": ["C"], "right": "D"}], "dialect_phrases": [], "drug_confusables": []}
            hints_path.write_text(yaml.dump(v2, allow_unicode=True), encoding="utf-8")

            ok = _run(svc.reload_correction_hints())
            self.assertTrue(ok)
            self.assertEqual(len(svc.correction_hints["accent_errors"]), 2)

    def test_reload_missing_file_returns_true(self):
        """文件不存在时降级为空表，返回 True。"""
        from app.services.voice_rounding import VoiceRoundingService

        db = MagicMock()
        config = SimpleNamespace(yaml_cfg={
            "voice_rounding": {"correction_hints_path": "/nonexistent/path.yaml"},
        })
        svc = VoiceRoundingService(db, config)
        ok = _run(svc.reload_correction_hints())
        self.assertTrue(ok)
        self.assertEqual(svc.correction_hints.get("accent_errors") or [], [])


if __name__ == "__main__":
    unittest.main()
