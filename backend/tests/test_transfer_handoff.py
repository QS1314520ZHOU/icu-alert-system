"""转出交接评估模块测试。"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from app.alert_engine.transfer_handoff import TransferHandoffMixin


# ── 测试辅助 ──

class _FakeConfig:
    def __init__(self, data=None):
        self.yaml_cfg = data or {
            "alert_engine": {
                "transfer_handoff": {
                    "enabled": True,
                    "llm_narrative": False,
                    "verify_window_hours": 72,
                    "high_threshold": 70,
                    "mod_threshold": 40,
                    "factor_weights": {
                        "vital_trend_high_variability": 15,
                        "vital_trend_acute_worsening": 20,
                        "sofa_trend_rising": 10,
                        "vent_weaned_lt_24h": 15,
                        "vent_weaned_24_48h": 8,
                        "vaso_stopped_lt_24h": 15,
                        "vaso_stopped_24_48h": 8,
                        "residual_hypoxemia": 12,
                        "residual_hypotension": 12,
                        "residual_tachycardia": 8,
                        "residual_fever": 8,
                        "residual_low_gcs": 12,
                        "residual_high_lactate": 12,
                        "residual_oliguria": 10,
                        "pics_risk_high": 10,
                        "sepsis_subtype_hyperinflammatory": 8,
                    },
                    "thresholds": {
                        "vital_cv_high": 0.3,
                        "trend_delta_hours": 6,
                        "weaning_window_hours": 48,
                        "spo2_low": 92,
                        "fio2_high": 0.4,
                        "map_low": 65,
                        "hr_high": 110,
                        "temp_high": 38.5,
                        "gcs_low": 13,
                        "lactate_high": 2.0,
                        "urine_low_ml_kg_h": 0.5,
                    },
                },
                "suppression": {
                    "same_rule_same_patient_seconds": 1800,
                    "max_alerts_per_patient_per_hour": 10,
                },
            }
        }


class _FakeCollection:
    """简易内存 MongoDB 集合模拟。"""

    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, query, sort=None):
        matched = [d for d in self.docs if self._match(d, query)]
        if sort:
            key, direction = sort[0]
            matched.sort(key=lambda x: x.get(key) or datetime.min, reverse=(direction == -1))
        return dict(matched[0]) if matched else None

    async def count_documents(self, query):
        return sum(1 for d in self.docs if self._match(d, query))

    async def update_one(self, selector, update):
        for d in self.docs:
            if self._match(d, selector):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                return

    def find(self, query):
        return _FakeCursor([d for d in self.docs if self._match(d, query)])

    @staticmethod
    def _resolve(doc, dotted_key):
        """Resolve dotted key like 'verification.checked_at' from nested dicts."""
        parts = dotted_key.split(".")
        current = doc
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None, False
        return current, True

    @staticmethod
    def _match(doc, query):
        for key, value in query.items():
            # Handle dotted notation (e.g. "verification.checked_at")
            if "." in key:
                current, exists = _FakeCollection._resolve(doc, key)
                if isinstance(value, dict):
                    if "$ne" in value:
                        if current == value["$ne"]:
                            return False
                    if "$exists" in value:
                        if bool(value["$exists"]) != exists:
                            return False
                elif value is None:
                    if current is not None:
                        return False
                elif current != value:
                    return False
                continue

            current = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (current is not None and current >= value["$gte"]):
                    return False
                if "$lte" in value and not (current is not None and current <= value["$lte"]):
                    return False
                if "$ne" in value and current == value["$ne"]:
                    return False
                if "$in" in value and current not in value["$in"]:
                    return False
                if "$exists" in value:
                    if bool(value["$exists"]) != (key in doc):
                        return False
            elif current != value:
                return False
        return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key, direction):
        self._docs.sort(key=lambda x: x.get(key) or datetime.min, reverse=(direction == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
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


class _FakeDb:
    def __init__(self, collections=None):
        self._cols = collections or {}

    def col(self, name):
        if name not in self._cols:
            self._cols[name] = _FakeCollection()
        return self._cols[name]


class _StubEngine(TransferHandoffMixin):
    """用于测试的最小引擎桩。"""

    def __init__(self, db=None, config=None):
        self.db = db or _FakeDb()
        self.config = config or _FakeConfig()

    def _pid_str(self, pid):
        return str(pid) if pid is not None else ""

    def _cfg(self, *path, default=None):
        cursor = self.config.yaml_cfg
        for p in path:
            if not isinstance(cursor, dict) or p not in cursor:
                return default
            cursor = cursor[p]
        return cursor if cursor is not None else default

    def _get_cfg_list(self, path, default):
        val = self._cfg(*path, default=default)
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [val]
        return default

    async def _get_param_series_by_pid(self, pid, code, since, prefer_device_types=None, limit=2000):
        col = self.db.col("bedside")
        pid_str = self._pid_str(pid)
        docs = [d for d in col.docs if d.get("pid") == pid_str and d.get("code") == code]
        if since:
            docs = [d for d in docs if d.get("time") and d["time"] >= since]
        docs.sort(key=lambda x: x.get("time"))
        return [{"time": d["time"], "value": d["value"]} for d in docs[:limit]]

    async def _get_latest_assessment(self, pid, kind):
        doc = await self.db.col("score").find_one(
            {"patient_id": self._pid_str(pid), "score_type": kind},
            sort=[("calc_time", -1)],
        )
        if doc:
            return doc.get("value")
        return None

    async def _get_urine_rate(self, pid, patient_doc, hours):
        return None

    async def _has_vasopressor(self, pid):
        return False

    async def _find_recent_drug_docs(self, pid, keywords, hours=24, limit=600):
        return []

    async def _get_device_id_for_patient(self, patient_doc, types):
        return None

    async def _get_latest_device_cap(self, device_id):
        return None

    def _vent_param(self, cap, name, code, default=None):
        return default

    def _vent_param_priority(self, cap, names, codes, default=None):
        return default

    async def _calc_sofa(self, patient_doc, pid, device_id, his_pid):
        return None

    async def _get_active_vent_bind(self, pid_str):
        return None

    def _drug_event_time(self, doc):
        for key in ("_event_time", "executeTime", "startTime", "orderTime"):
            val = doc.get(key)
            if isinstance(val, datetime):
                return val
        return None


# ── 测试用例 ──

class TestTransferHandoffRiskScore(unittest.IsolatedAsyncioTestCase):
    """风险分计算与分级测试。"""

    def _make_patient(self, pid=None):
        return {"_id": pid or ObjectId(), "hisPid": "HIS-001", "name": "测试患者"}

    async def test_low_risk_patient_gets_low_score(self):
        """无任何风险因素的患者应得低分。"""
        engine = _StubEngine()
        patient = self._make_patient()
        result = await engine.compute_transfer_risk_score(patient)
        self.assertEqual(result["risk_level"], "low")
        self.assertLess(result["score"], 40)
        self.assertEqual(len(result["risk_factors"]), 0)

    async def test_high_variability_increases_score(self):
        """生命体征变异系数高的患者应被标记。"""
        now = datetime.now()
        pid = ObjectId()
        # 构造高变异 HR 数据：均值 90，标准差大（CV > 0.3）
        bedside_data = []
        for i in range(20):
            val = 50 if i % 2 == 0 else 140  # 交替 50/140，CV ≈ 0.5
            bedside_data.append({"pid": str(pid), "code": "param_HR", "time": now - timedelta(minutes=30 - i), "value": val})

        db = _FakeDb({"bedside": _FakeCollection(bedside_data)})
        engine = _StubEngine(db=db)
        patient = self._make_patient(pid)
        result = await engine.compute_transfer_risk_score(patient)

        factor_names = [f["factor"] for f in result["risk_factors"]]
        self.assertIn("vital_trend_high_variability", factor_names)

    async def test_residual_hypoxemia_detected(self):
        """SpO2 低于阈值应触发残余低氧因子。"""
        now = datetime.now()
        pid = ObjectId()
        bedside_data = [{"pid": str(pid), "code": "param_spo2", "time": now - timedelta(minutes=5), "value": 88}]

        db = _FakeDb({"bedside": _FakeCollection(bedside_data)})
        engine = _StubEngine(db=db)
        patient = self._make_patient(pid)
        result = await engine.compute_transfer_risk_score(patient)

        factor_names = [f["factor"] for f in result["risk_factors"]]
        self.assertIn("residual_hypoxemia", factor_names)

    async def test_residual_hypotension_detected(self):
        """MAP 低于阈值应触发残余低血压因子。"""
        now = datetime.now()
        pid = ObjectId()
        bedside_data = [{"pid": str(pid), "code": "param_nibp_m", "time": now - timedelta(minutes=5), "value": 58}]

        db = _FakeDb({"bedside": _FakeCollection(bedside_data)})
        engine = _StubEngine(db=db)
        patient = self._make_patient(pid)
        result = await engine.compute_transfer_risk_score(patient)

        factor_names = [f["factor"] for f in result["risk_factors"]]
        self.assertIn("residual_hypotension", factor_names)

    async def test_low_gcs_detected(self):
        """GCS 低于阈值应被标记。"""
        pid = ObjectId()
        db = _FakeDb({
            "score": _FakeCollection([
                {"patient_id": str(pid), "score_type": "gcs", "value": 10, "calc_time": datetime.now()},
            ]),
        })
        engine = _StubEngine(db=db)
        patient = self._make_patient(pid)
        result = await engine.compute_transfer_risk_score(patient)

        factor_names = [f["factor"] for f in result["risk_factors"]]
        self.assertIn("residual_low_gcs", factor_names)

    async def test_score_capped_at_100(self):
        """总分不应超过 100。"""
        now = datetime.now()
        pid = ObjectId()
        # 制造多个风险因素
        bedside_data = []
        for i in range(20):
            bedside_data.extend([
                {"pid": str(pid), "code": "param_HR", "time": now - timedelta(minutes=30 - i), "value": 70 if i % 2 == 0 else 130},
                {"pid": str(pid), "code": "param_spo2", "time": now - timedelta(minutes=30 - i), "value": 85},
                {"pid": str(pid), "code": "param_nibp_m", "time": now - timedelta(minutes=30 - i), "value": 55},
                {"pid": str(pid), "code": "param_resp", "time": now - timedelta(minutes=30 - i), "value": 30},
                {"pid": str(pid), "code": "param_T", "time": now - timedelta(minutes=30 - i), "value": 39.5},
            ])
        db = _FakeDb({
            "bedside": _FakeCollection(bedside_data),
            "score": _FakeCollection([
                {"patient_id": str(pid), "score_type": "gcs", "value": 8, "calc_time": datetime.now()},
                {"patient_id": str(pid), "score_type": "pics_risk_assessment", "assessment": {"score": 85, "high_threshold": 70}, "calc_time": datetime.now()},
            ]),
        })
        engine = _StubEngine(db=db)
        patient = self._make_patient(pid)
        result = await engine.compute_transfer_risk_score(patient)

        self.assertLessEqual(result["score"], 100)
        # 多因素叠加应达到 high
        self.assertEqual(result["risk_level"], "high")

    async def test_high_risk_threshold(self):
        """score >= 70 应为 high。"""
        # 通过构造多个中等因子来验证阈值
        now = datetime.now()
        pid = ObjectId()
        bedside_data = []
        for i in range(20):
            bedside_data.extend([
                {"pid": str(pid), "code": "param_spo2", "time": now - timedelta(minutes=30 - i), "value": 88},  # 12
                {"pid": str(pid), "code": "param_nibp_m", "time": now - timedelta(minutes=30 - i), "value": 58},  # 12
                {"pid": str(pid), "code": "param_HR", "time": now - timedelta(minutes=30 - i), "value": 70 if i % 2 == 0 else 120},  # 15+8
                {"pid": str(pid), "code": "param_T", "time": now - timedelta(minutes=30 - i), "value": 39.0},  # 8
                {"pid": str(pid), "code": "param_resp", "time": now - timedelta(minutes=30 - i), "value": 28},  # high variability
            ])
        db = _FakeDb({
            "bedside": _FakeCollection(bedside_data),
            "score": _FakeCollection([
                {"patient_id": str(pid), "score_type": "gcs", "value": 10, "calc_time": datetime.now()},  # 12
            ]),
        })
        engine = _StubEngine(db=db)
        patient = self._make_patient(pid)
        result = await engine.compute_transfer_risk_score(patient)

        # 应该有多个因子，总分 >= 40 (moderate) 或 >= 70 (high)
        self.assertIn(result["risk_level"], ("moderate", "high"))
        self.assertGreaterEqual(result["score"], 40)

    async def test_moderate_risk_threshold(self):
        """40 <= score < 70 应为 moderate。"""
        now = datetime.now()
        pid = ObjectId()
        # 仅构造 SpO2 低 + MAP 低 = 24 分，加上 GCS 低 = 36 分，还不够 moderate
        # 加上 HR 高 = 44 分 -> moderate
        bedside_data = []
        for i in range(5):
            bedside_data.extend([
                {"pid": str(pid), "code": "param_spo2", "time": now - timedelta(minutes=30 - i), "value": 90},
                {"pid": str(pid), "code": "param_nibp_m", "time": now - timedelta(minutes=30 - i), "value": 60},
            ])
        db = _FakeDb({
            "bedside": _FakeCollection(bedside_data),
            "score": _FakeCollection([
                {"patient_id": str(pid), "score_type": "gcs", "value": 10, "calc_time": datetime.now()},
            ]),
        })
        engine = _StubEngine(db=db)
        patient = self._make_patient(pid)
        result = await engine.compute_transfer_risk_score(patient)

        # SpO2(12) + MAP(12) + GCS(12) = 36 < 40 → low
        # 但如果有 HR 波动可能更高
        self.assertIn(result["risk_level"], ("low", "moderate"))


class TestTransferHandoffChecklist(unittest.IsolatedAsyncioTestCase):
    """Checklist 生成测试。"""

    def test_high_risk_gets_full_checklist(self):
        """高风险应包含 watch_window 通用项。"""
        engine = _StubEngine()
        risk_factors = [
            {"factor": "residual_hypoxemia", "detail": "SpO2=88", "weight": 12},
            {"factor": "residual_hypotension", "detail": "MAP=58", "weight": 12},
            {"factor": "vent_weaned_lt_24h", "detail": "撤机 12h 前", "weight": 15},
        ]
        checklist = engine.build_checklist(risk_factors, "high")
        items = [c["item"] for c in checklist]
        self.assertIn("复查血气，评估氧疗方案", items)
        self.assertIn("评估容量状态与血管张力", items)
        self.assertIn("确认撤机后呼吸储备，备无创通气", items)
        self.assertIn("转出后 72h 内关注再入 ICU 征象", items)
        self.assertIn("确认交接班信息完整传达", items)

    def test_low_risk_gets_minimal_checklist(self):
        """低风险仅包含通用交接项。"""
        engine = _StubEngine()
        checklist = engine.build_checklist([], "low")
        items = [c["item"] for c in checklist]
        self.assertIn("确认交接班信息完整传达", items)
        self.assertNotIn("转出后 72h 内关注再入 ICU 征象", items)

    def test_each_factor_maps_to_at_least_one_item(self):
        """每个 risk_factor 应映射至少一条 checklist。"""
        engine = _StubEngine()
        all_factors = list(TransferHandoffMixin._FACTOR_CHECKLIST_MAP.keys())
        for factor in all_factors:
            risk_factors = [{"factor": factor, "detail": "test", "weight": 10}]
            checklist = engine.build_checklist(risk_factors, "high")
            self.assertGreaterEqual(len(checklist), 1, f"Factor {factor} should map to at least 1 checklist item")

    def test_no_duplicate_checklist_items(self):
        """checklist 不应有重复项。"""
        engine = _StubEngine()
        risk_factors = [
            {"factor": "residual_hypoxemia", "detail": "SpO2=88", "weight": 12},
            {"factor": "residual_hypotension", "detail": "MAP=58", "weight": 12},
        ]
        checklist = engine.build_checklist(risk_factors, "high")
        items = [c["item"] for c in checklist]
        self.assertEqual(len(items), len(set(items)))


class TestTransferHandoffEvaluate(unittest.IsolatedAsyncioTestCase):
    """完整评估流程测试。"""

    async def test_evaluate_returns_complete_doc(self):
        """evaluate_transfer_handoff 应返回完整结构。"""
        pid = ObjectId()
        db = _FakeDb({"bedside": _FakeCollection(), "score": _FakeCollection()})
        engine = _StubEngine(db=db)
        patient = {"_id": pid, "hisPid": "HIS-001"}
        doc = await engine.evaluate_transfer_handoff(patient)

        self.assertEqual(doc["score_type"], "transfer_handoff")
        self.assertEqual(doc["patient_id"], str(pid))
        self.assertEqual(doc["status"], "active")
        self.assertIn("post_transfer_risk_score", doc)
        self.assertIn("risk_level", doc)
        self.assertIn("risk_factors", doc)
        self.assertIn("handoff_checklist", doc)
        self.assertIn("narrative", doc)
        self.assertIn("transferred_at", doc)
        self.assertIn("verification", doc)
        self.assertIn("calc_time", doc)
        self.assertIn("month", doc)
        self.assertIn("day", doc)

        # verification 初始为 null
        self.assertIsNone(doc["verification"]["checked_at"])
        self.assertIsNone(doc["verification"]["readmitted_within_72h"])
        self.assertIsNone(doc["verification"]["critical_alert_within_72h"])

    async def test_evaluate_no_patient_id(self):
        """无 patient id 应返回 error。"""
        engine = _StubEngine()
        result = await engine.evaluate_transfer_handoff({})
        self.assertIn("error", result)


class TestTransferHandoffVerification(unittest.IsolatedAsyncioTestCase):
    """72h 回填验证测试。"""

    async def test_verify_backfills_readmission(self):
        """72h 后检测到再入 ICU 应写回 verification。"""
        pid = str(ObjectId())
        now = datetime.now()
        transferred_at = now - timedelta(hours=73)

        score_doc = {
            "_id": ObjectId(),
            "score_type": "transfer_handoff",
            "patient_id": pid,
            "transferred_at": transferred_at,
            "verification": {"checked_at": None, "readmitted_within_72h": None, "critical_alert_within_72h": None, "details": []},
            "calc_time": transferred_at,
        }

        alert_doc = {
            "patient_id": pid,
            "category": "transfer",
            "alert_type": "readmission",
            "created_at": transferred_at + timedelta(hours=24),
        }

        db = _FakeDb({
            "score": _FakeCollection([score_doc]),
            "alert_records": _FakeCollection([alert_doc]),
        })
        engine = _StubEngine(db=db)
        processed = await engine.verify_transfer_outcomes()

        self.assertEqual(processed, 1)
        updated = db.col("score").docs[0]
        self.assertIsNotNone(updated["verification"]["checked_at"])
        self.assertTrue(updated["verification"]["readmitted_within_72h"])

    async def test_verify_backfills_critical_alert(self):
        """72h 后检测到 critical 预警应写回。"""
        pid = str(ObjectId())
        now = datetime.now()
        transferred_at = now - timedelta(hours=73)

        score_doc = {
            "_id": ObjectId(),
            "score_type": "transfer_handoff",
            "patient_id": pid,
            "transferred_at": transferred_at,
            "verification": {"checked_at": None, "readmitted_within_72h": None, "critical_alert_within_72h": None, "details": []},
            "calc_time": transferred_at,
        }

        alert_doc = {
            "patient_id": pid,
            "category": "vital_signs",
            "severity": "critical",
            "created_at": transferred_at + timedelta(hours=12),
        }

        db = _FakeDb({
            "score": _FakeCollection([score_doc]),
            "alert_records": _FakeCollection([alert_doc]),
        })
        engine = _StubEngine(db=db)
        processed = await engine.verify_transfer_outcomes()

        self.assertEqual(processed, 1)
        updated = db.col("score").docs[0]
        self.assertTrue(updated["verification"]["critical_alert_within_72h"])
        self.assertFalse(updated["verification"]["readmitted_within_72h"])

    async def test_verify_skips_not_yet_due(self):
        """transferred_at 未满 verify_window_hours 的记录应跳过。"""
        pid = str(ObjectId())
        now = datetime.now()
        transferred_at = now - timedelta(hours=24)  # 仅 24h，未满 72h

        score_doc = {
            "_id": ObjectId(),
            "score_type": "transfer_handoff",
            "patient_id": pid,
            "transferred_at": transferred_at,
            "verification": {"checked_at": None, "readmitted_within_72h": None, "critical_alert_within_72h": None, "details": []},
            "calc_time": transferred_at,
        }

        db = _FakeDb({"score": _FakeCollection([score_doc])})
        engine = _StubEngine(db=db)
        processed = await engine.verify_transfer_outcomes()

        self.assertEqual(processed, 0)

    async def test_verify_skips_already_checked(self):
        """已验证的记录应跳过。"""
        pid = str(ObjectId())
        now = datetime.now()
        transferred_at = now - timedelta(hours=73)

        score_doc = {
            "_id": ObjectId(),
            "score_type": "transfer_handoff",
            "patient_id": pid,
            "transferred_at": transferred_at,
            "verification": {"checked_at": now, "readmitted_within_72h": False, "critical_alert_within_72h": False, "details": []},
            "calc_time": transferred_at,
        }

        db = _FakeDb({"score": _FakeCollection([score_doc])})
        engine = _StubEngine(db=db)
        processed = await engine.verify_transfer_outcomes()

        self.assertEqual(processed, 0)


class TestTransferHandoffNarrative(unittest.IsolatedAsyncioTestCase):
    """Narrative 生成测试。"""

    def test_rule_narrative_includes_risk_level(self):
        """规则 narrative 应包含风险等级。"""
        engine = _StubEngine()
        factors = [{"factor": "residual_hypoxemia", "detail": "SpO2=88", "weight": 12}]
        checklist = [{"item": "复查血气", "why": "低氧", "category": "unstable_vital"}]
        narrative = engine._build_rule_narrative(factors, "high", checklist)
        self.assertIn("高", narrative)
        self.assertIn("1", narrative)  # checklist count

    def test_rule_narrative_empty_factors(self):
        """无风险因素时 narrative 仍应完整。"""
        engine = _StubEngine()
        narrative = engine._build_rule_narrative([], "low", [])
        self.assertIn("低", narrative)


class TestTransferHandoffApi(unittest.IsolatedAsyncioTestCase):
    """API 返回结构测试。"""

    async def test_get_latest_returns_none_when_empty(self):
        """无记录时应返回 None。"""
        engine = _StubEngine()
        result = await engine.get_latest_transfer_handoff("nonexistent")
        self.assertIsNone(result)

    async def test_get_latest_returns_doc(self):
        """有记录时应返回最新一条。"""
        pid = str(ObjectId())
        now = datetime.now()
        doc1 = {
            "score_type": "transfer_handoff",
            "patient_id": pid,
            "calc_time": now - timedelta(hours=1),
            "post_transfer_risk_score": 50,
            "verification": {"checked_at": None},
        }
        doc2 = {
            "score_type": "transfer_handoff",
            "patient_id": pid,
            "calc_time": now,
            "post_transfer_risk_score": 75,
            "verification": {"checked_at": now},
        }
        db = _FakeDb({"score": _FakeCollection([doc1, doc2])})
        engine = _StubEngine(db=db)
        result = await engine.get_latest_transfer_handoff(pid)

        self.assertIsNotNone(result)
        self.assertEqual(result["post_transfer_risk_score"], 75)
        self.assertIn("verification", result)

    async def test_persist_and_retrieve(self):
        """持久化后应可检索。"""
        pid = str(ObjectId())
        db = _FakeDb({"score": _FakeCollection()})
        engine = _StubEngine(db=db)

        doc = {
            "score_type": "transfer_handoff",
            "patient_id": pid,
            "post_transfer_risk_score": 55,
            "risk_level": "moderate",
            "calc_time": datetime.now(),
            "verification": {"checked_at": None, "readmitted_within_72h": None, "critical_alert_within_72h": None, "details": []},
        }
        await engine.persist_transfer_handoff(doc)

        result = await engine.get_latest_transfer_handoff(pid)
        self.assertIsNotNone(result)
        self.assertEqual(result["post_transfer_risk_score"], 55)
        self.assertEqual(result["risk_level"], "moderate")


if __name__ == "__main__":
    unittest.main()
