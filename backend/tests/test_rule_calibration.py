"""
规则级自校准控制器单元测试
覆盖：高误报降级、夜间静默、effectiveness 持续差 flag_review、
样本不足 keep、critical 不被静默、未 approved 不生效。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from app.alert_engine.rule_calibration import (
    RuleCalibrationMixin,
    SEVERITY_DOWNSTEP,
    _VALID_DISPOSITIONS,
)


# ── Mock 基础设施 ─────────────────────────────────────────────────────────


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key, direction=1):
        reverse = direction == -1
        self._docs.sort(key=lambda item: item.get(key) if isinstance(item, dict) else "", reverse=reverse)
        return self

    def limit(self, count):
        self._docs = self._docs[:count]
        return self

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._idx]
        self._idx += 1
        return item


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query=None, projection=None):
        query = query or {}
        matched = [doc for doc in self.docs if self._match(doc, query)]
        return _Cursor(matched)

    async def find_one(self, query, sort=None):
        docs = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            docs.sort(key=lambda item: item.get(key) or "", reverse=direction == -1)
        return dict(docs[0]) if docs else None

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)

        class _Result:
            inserted_id = doc["_id"]

        return _Result()

    async def update_one(self, selector, update):
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return

    @staticmethod
    def _match(doc, query):
        for key, value in query.items():
            current = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (current is not None and current >= value["$gte"]):
                    return False
                if "$lte" in value and not (current is not None and current <= value["$lte"]):
                    return False
                if "$ne" in value and current == value["$ne"]:
                    return False
                if "$exists" in value:
                    exists = key in doc
                    if bool(value["$exists"]) != exists:
                        return False
                if "$in" in value and current not in value["$in"]:
                    return False
            elif current != value:
                return False
        return True


class _FakeDb:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def col(self, name):
        if name not in self.collections:
            self.collections[name] = _Collection()
        return self.collections[name]


class _FakeConfig:
    def __init__(self, cfg=None):
        self.yaml_cfg = cfg or {}


class _FakeEngine(RuleCalibrationMixin):
    """最小化 AlertEngine 模拟，只包含 calibration 所需方法。"""

    def __init__(self, db, config=None):
        self.db = db
        self.config = config or _FakeConfig()

    def _cfg(self, *path, default=None):
        cfg = self.config.yaml_cfg
        for p in path:
            if not isinstance(cfg, dict) or p not in cfg:
                return default
            cfg = cfg[p]
        return cfg


# ── 辅助函数 ──────────────────────────────────────────────────────────────


def _make_alert_doc(
    rule_id="RULE_001",
    severity="high",
    ack_disposition=None,
    outcome_delta=None,
    source_time=None,
    alert_type="vital_signs",
) -> dict:
    doc = {
        "rule_id": rule_id,
        "severity": severity,
        "alert_type": alert_type,
        "patient_id": "P001",
        "created_at": datetime.now(),
    }
    if ack_disposition:
        doc["ack_disposition"] = ack_disposition
    if outcome_delta:
        doc["outcome_delta"] = outcome_delta
    if source_time:
        doc["source_time"] = source_time
    return doc


def _make_calibration_doc(
    rule_id="RULE_001",
    status="approved",
    suggestion="suggest_downgrade",
    suggested_severity=None,
    suggested_silence_minutes=None,
) -> dict:
    return {
        "_id": ObjectId(),
        "score_type": "rule_calibration",
        "rule_id": rule_id,
        "status": status,
        "suggestion": suggestion,
        "suggested_severity": suggested_severity,
        "suggested_silence_minutes": suggested_silence_minutes,
        "created_at": datetime.now(),
    }


def _outcome_delta(window="2h", improved=False) -> dict:
    return {
        "windows": {
            window: {
                "map": {"improved": improved, "baseline": 70, "followup": 75, "delta": 5, "direction": "up"},
            }
        },
        "improved_any": improved,
    }


# ── 测试 ─────────────────────────────────────────────────────────────────


class TestRuleCalibrationMixin(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.db = _FakeDb()

    # 1. approved 降级生效
    async def test_downgrade_applied(self):
        cal_doc = _make_calibration_doc(
            suggestion="suggest_downgrade",
            suggested_severity="warning",
        )
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)
        alert_doc = _make_alert_doc(severity="high")

        result = await engine._apply_rule_calibration(alert_doc)

        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "warning")
        self.assertTrue(result["extra"]["calibration"]["applied"])
        self.assertEqual(result["extra"]["calibration"]["original_severity"], "high")

    # 2. 未 approved 不生效
    async def test_unapproved_no_effect(self):
        cal_doc = _make_calibration_doc(
            status="pending_review",
            suggestion="suggest_downgrade",
        )
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)
        alert_doc = _make_alert_doc(severity="high")

        result = await engine._apply_rule_calibration(alert_doc)

        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "high")
        self.assertNotIn("calibration", result.get("extra", {}))

    # 3. critical 不被静默
    async def test_critical_not_silenced(self):
        cal_doc = _make_calibration_doc(
            suggestion="suggest_silence_window",
            suggested_silence_minutes=360,
        )
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)

        # mock _in_silence_window 返回 True（夜间）
        engine._in_silence_window = lambda cal: True

        alert_doc = _make_alert_doc(severity="critical")
        result = await engine._apply_rule_calibration(alert_doc)

        # critical 永不静默
        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "critical")

    # 4. 非 critical 在静默窗口内被静默
    async def test_non_critical_silenced_in_window(self):
        cal_doc = _make_calibration_doc(
            suggestion="suggest_silence_window",
            suggested_silence_minutes=360,
        )
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)
        engine._in_silence_window = lambda cal: True

        alert_doc = _make_alert_doc(severity="high")
        result = await engine._apply_rule_calibration(alert_doc)

        self.assertIsNone(result)

    # 5. keep 建议不改变任何东西
    async def test_keep_no_change(self):
        cal_doc = _make_calibration_doc(suggestion="keep")
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)
        alert_doc = _make_alert_doc(severity="high")

        result = await engine._apply_rule_calibration(alert_doc)

        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "high")

    # 6. severity 降级链正确
    async def test_severity_downstep_chain(self):
        self.assertEqual(SEVERITY_DOWNSTEP["critical"], "high")
        self.assertEqual(SEVERITY_DOWNSTEP["high"], "warning")
        self.assertEqual(SEVERITY_DOWNSTEP["warning"], "info")
        self.assertEqual(SEVERITY_DOWNSTEP["info"], "info")

    # 7. 缓存命中
    async def test_cache_hit(self):
        cal_doc = _make_calibration_doc()
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)

        # 第一次查询
        result1 = await engine.get_approved_rule_calibration("RULE_001")
        self.assertIsNotNone(result1)

        # 清空数据库
        self.db.collections["score"] = _Collection([])

        # 缓存内仍能取到
        result2 = await engine.get_approved_rule_calibration("RULE_001")
        self.assertIsNotNone(result2)

    # 8. 缓存失效
    async def test_cache_invalidation(self):
        cal_doc = _make_calibration_doc()
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)

        await engine.get_approved_rule_calibration("RULE_001")
        engine.invalidate_calibration_cache("RULE_001")

        # 清空数据库
        self.db.collections["score"] = _Collection([])

        # 失效后查不到
        result = await engine.get_approved_rule_calibration("RULE_001")
        self.assertIsNone(result)


class TestRuleCalibrationScanner(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.db = _FakeDb()

    # 9. 样本不足 → keep
    async def test_small_sample_keep(self):
        from app.alert_engine.scanner_rule_calibration import RuleCalibrationScanner

        # 只有 5 条记录
        now = datetime.now()
        alerts = [
            _make_alert_doc(ack_disposition="resolved", source_time=now - timedelta(hours=i))
            for i in range(5)
        ]
        self.db.collections["alert_records"] = _Collection(alerts)
        engine = _FakeEngine(self.db)
        scanner = RuleCalibrationScanner(engine)

        stats = {
            "total": 5,
            "fp_rate": 0.8,
            "eff_2h": 0.0,
            "action_rate": 0.9,
            "night_ratio": 0.1,
            "ppv_proxy": 0.2,
            "alert_type": "test",
        }
        cfg = scanner._cfg()
        suggestion, sev, sil, reason = scanner._decide(stats, cfg)

        self.assertEqual(suggestion, "keep")
        self.assertIn("样本不足", reason)

    # 10. 高误报低效果 → 降级
    async def test_high_fp_low_eff_downgrade(self):
        from app.alert_engine.scanner_rule_calibration import RuleCalibrationScanner

        engine = _FakeEngine(self.db)
        scanner = RuleCalibrationScanner(engine)

        stats = {
            "total": 50,
            "fp_rate": 0.7,
            "eff_2h": 0.1,
            "action_rate": 0.3,
            "night_ratio": 0.1,
            "ppv_proxy": 0.3,
            "alert_type": "test",
        }
        cfg = scanner._cfg()
        suggestion, sev, sil, reason = scanner._decide(stats, cfg)

        self.assertEqual(suggestion, "suggest_downgrade")

    # 11. 高误报 + 夜间高频 → 静默
    async def test_high_fp_night_silence(self):
        from app.alert_engine.scanner_rule_calibration import RuleCalibrationScanner

        engine = _FakeEngine(self.db)
        scanner = RuleCalibrationScanner(engine)

        stats = {
            "total": 50,
            "fp_rate": 0.7,
            "eff_2h": 0.3,  # effectiveness 不算太差
            "action_rate": 0.3,
            "night_ratio": 0.6,
            "ppv_proxy": 0.3,
            "alert_type": "test",
        }
        cfg = scanner._cfg()
        suggestion, sev, sil, reason = scanner._decide(stats, cfg)

        self.assertEqual(suggestion, "suggest_silence_window")
        self.assertEqual(sil, 360)

    # 12. 有效但效果差 → flag_review
    async def test_action_but_no_effect_flag_review(self):
        from app.alert_engine.scanner_rule_calibration import RuleCalibrationScanner

        engine = _FakeEngine(self.db)
        scanner = RuleCalibrationScanner(engine)

        stats = {
            "total": 50,
            "fp_rate": 0.2,
            "eff_2h": 0.05,
            "action_rate": 0.6,
            "night_ratio": 0.1,
            "ppv_proxy": 0.8,
            "alert_type": "test",
        }
        cfg = scanner._cfg()
        suggestion, sev, sil, reason = scanner._decide(stats, cfg)

        self.assertEqual(suggestion, "flag_review")
        self.assertIn("人工复核", reason)

    # 13. 正常指标 → keep
    async def test_normal_keep(self):
        from app.alert_engine.scanner_rule_calibration import RuleCalibrationScanner

        engine = _FakeEngine(self.db)
        scanner = RuleCalibrationScanner(engine)

        stats = {
            "total": 100,
            "fp_rate": 0.1,
            "eff_2h": 0.5,
            "action_rate": 0.6,
            "night_ratio": 0.1,
            "ppv_proxy": 0.8,
            "alert_type": "test",
        }
        cfg = scanner._cfg()
        suggestion, sev, sil, reason = scanner._decide(stats, cfg)

        self.assertEqual(suggestion, "keep")
        self.assertIn("正常", reason)


class TestCalibrationIntegration(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.db = _FakeDb()

    # 14. 完整拦截链：calibration 在 intelligence 之前生效
    async def test_intercept_calls_calibration(self):
        cal_doc = _make_calibration_doc(
            suggestion="suggest_downgrade",
            suggested_severity="warning",
        )
        self.db.collections["score"] = _Collection([cal_doc])
        engine = _FakeEngine(self.db)
        alert_doc = _make_alert_doc(severity="high")

        result = await engine._alert_intelligence_intercept(alert_doc, None)

        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "warning")

    # 15. 无 rule_id 时不崩溃
    async def test_no_rule_id_no_crash(self):
        engine = _FakeEngine(self.db)
        alert_doc = {"severity": "high", "patient_id": "P001"}

        result = await engine._apply_rule_calibration(alert_doc)

        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "high")


if __name__ == "__main__":
    unittest.main()
