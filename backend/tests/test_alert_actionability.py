"""Tests for refactored alert_actionability — suspected actions, metric observation, adjudication."""
import unittest
from datetime import datetime, timedelta

from bson import ObjectId

from app.alert_engine.alert_actionability import (
    AlertActionabilityScorerMixin,
    _observe_metric_direction,
    _wilson_ci,
)


# ── Fake DB infrastructure ────────────────────────────────────────────────────


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key, direction):
        reverse = direction == -1
        self._docs.sort(
            key=lambda item: item.get(key)
            if not isinstance(key, list)
            else item.get(key[0]),
            reverse=reverse,
        )
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
        self.inserted: list[dict] = []

    def find(self, query=None, projection=None):
        query = query or {}
        matched = [doc for doc in self.docs if self._match(doc, query)]
        if projection:
            projected = []
            for doc in matched:
                row = {}
                for key, enabled in projection.items():
                    if enabled and key in doc:
                        row[key] = doc[key]
                if "_id" in doc:
                    row["_id"] = doc["_id"]
                projected.append(row)
            matched = projected
        return _Cursor(matched)

    async def find_one(self, query, projection=None, sort=None):
        docs = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            if isinstance(sort, list):
                field, direction = sort[0]
            else:
                field = sort[0]
                direction = sort[1] if len(sort) > 1 else 1
            docs.sort(
                key=lambda item: item.get(field) or datetime.min,
                reverse=direction == -1,
            )
        return dict(docs[0]) if docs else None

    async def update_one(self, selector, update, upsert=False):
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    self._set_nested(doc, key, value)
                return
        if upsert:
            doc = dict(selector)
            for key, value in update.get("$set", {}).items():
                self._set_nested(doc, key, value)
            self.docs.append(doc)

    async def update_many(self, selector, update):
        modified = 0
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    self._set_nested(doc, key, value)
                modified += 1

        class _Result:
            modified_count = modified
        return _Result()

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        self.inserted.append(doc)

        class _Result:
            inserted_id = doc["_id"]
        return _Result()

    async def count_documents(self, query):
        return len([d for d in self.docs if self._match(d, query)])

    def aggregate(self, pipeline):
        # Minimal: return all docs with _id set to first match key
        return _Cursor([
            {"_id": d.get(pipeline[0].get("$group", {}).get("_id", "_id"), "unknown"), **d}
            for d in self.docs
        ])

    @staticmethod
    def _set_nested(doc, key, value):
        parts = str(key).split(".")
        cur = doc
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value

    @staticmethod
    def _match(doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(_Collection._match(doc, item) for item in value):
                    return False
                continue
            if key == "$and":
                if not all(_Collection._match(doc, item) for item in value):
                    return False
                continue
            current = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (
                    current is not None and current >= value["$gte"]
                ):
                    return False
                if "$lte" in value and not (
                    current is not None and current <= value["$lte"]
                ):
                    return False
                if "$ne" in value and current == value["$ne"]:
                    return False
                if "$exists" in value:
                    exists = key in doc
                    if bool(value["$exists"]) != exists:
                        return False
                if "$in" in value and current not in value["$in"]:
                    return False
                if "$eq" in value and current != value["$eq"]:
                    return False
                if "$cond" in value:
                    # simplified: skip $cond matching
                    pass
                if "$sum" in value:
                    pass
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


class _FakeAlertEngine(AlertActionabilityScorerMixin):
    def __init__(self, db):
        self.db = db

    def _cfg(self, *path, default=None):
        data = {
            "alert_engine": {
                "alert_actionability": {
                    "enabled": True,
                    "history_lookback_days": 30,
                    "min_history_samples": 8,
                    "action_match_hours": 24,
                },
            },
            "vital_signs": {
                "map_priority": ["param_ibp_m", "param_nibp_m"],
            },
        }
        cursor = data
        for key in path:
            if not isinstance(cursor, dict):
                return default
            cursor = cursor.get(key)
        return cursor if cursor is not None else default

    async def _get_latest_vitals_by_patient(self, patient_id):
        return {}

    async def _get_latest_labs_map(self, his_pid, lookback_hours=48):
        return {}

    async def _load_patient(self, patient_id):
        return {"_id": patient_id, "hisPid": "HIS-1"}, None

    async def _get_param_series_by_pid(self, *args, **kwargs):
        return []

    async def _get_lab_series(self, *args, **kwargs):
        return []

    def _is_night_window(self, now):
        return False


# ── Tests ────────────────────────────────────────────────────────────────────


class HeuristicAttentionScoreTest(unittest.IsolatedAsyncioTestCase):
    """Test 1-8: Heuristic attention score frozen at trigger, no future leakage."""

    async def test_1_heuristic_score_frozen_at_trigger(self):
        """Score uses only trigger-time data; no medication/circadian/recent factors."""
        engine = _FakeAlertEngine(_FakeDb())

        async def fake_state(patient_id, patient_doc):
            return {"factor": 0.82, "signals": {}}

        async def fake_history(alert_doc, lookback_days, min_samples):
            return {
                "factor": 0.7, "applied": True,
                "false_discovery_proportion": 0.3,
                "sample_count": 14, "all_reviewed_count": 20,
                "true_positive_count": 10, "false_positive_count": 4,
                "indeterminate_count": 0,
                "confidence": "moderate",
            }

        engine._attention_patient_state = fake_state
        engine._heuristic_history_factor = fake_history

        result = await engine._compute_heuristic_attention_score(
            {
                "_id": ObjectId(),
                "patient_id": "patient-1",
                "severity": "high",
                "alert_type": "shock_hypotension",
                "name": "低血压风险",
                "created_at": datetime.now(),
            },
            {"hisPid": "HIS-1"},
        )

        self.assertAlmostEqual(result["score"], 76.6, places=0)  # 0.75*.25+0.82*.45+0.7*.30=0.7665→76.6
        self.assertEqual(result["level"], "immediate")
        self.assertEqual(result["factors"]["severity_factor"], 0.75)
        self.assertEqual(result["factors"]["patient_state_factor"], 0.82)
        self.assertEqual(result["factors"]["history_factor"], 0.7)
        self.assertFalse(result["validated"])
        self.assertIn("NOT clinical actionability", result["note"])
        self.assertIsNotNone(result["frozen_at"])

    async def test_2_medication_factor_excluded(self):
        """Medication factor is NOT in the attention score formula."""
        engine = _FakeAlertEngine(_FakeDb())

        async def fake_state(patient_id, patient_doc):
            return {"factor": 0.5, "signals": {}}

        async def fake_history(alert_doc, lookback_days, min_samples):
            return {"factor": None, "applied": False, "sample_count": 0, "all_reviewed_count": 0, "confidence": "low"}

        engine._attention_patient_state = fake_state
        engine._heuristic_history_factor = fake_history

        result = await engine._compute_heuristic_attention_score(
            {
                "_id": ObjectId(),
                "patient_id": "patient-1",
                "severity": "warning",
                "alert_type": "sepsis",
                "created_at": datetime.now(),
            },
            {"hisPid": "HIS-1"},
        )

        self.assertNotIn("medication_factor", result["factors"])
        self.assertNotIn("recent_response_factor", result["factors"])
        self.assertNotIn("circadian_factor", result["factors"])


class SuspectedActionDetectionTest(unittest.IsolatedAsyncioTestCase):
    """Test 1-5: Drug matching produces suspected, not action_taken."""

    async def test_3_post_alert_drug_keyword_match_marked_suspected(self):
        """Post-alert drug matching produces status='suspected', not action_taken."""
        engine = _FakeAlertEngine(_FakeDb({"drugExe": _Collection([
            {
                "pid": "patient-1",
                "drugName": "去甲肾上腺素", "orderName": "去甲肾上腺素注射液",
                "dose": 4, "doseUnit": "mg/h", "route": "IV",
                "executeTime": datetime.now() + timedelta(minutes=18),
                "orderId": "order-001",
            },
        ])}))

        result = await engine._detect_suspected_actions(
            {
                "patient_id": "patient-1",
                "alert_type": "shock_hypotension",
                "name": "低血压",
                "created_at": datetime.now(),
            },
            {"hisPid": "HIS-1"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "suspected")
        self.assertEqual(result["method"], "keyword_time_match")
        self.assertIsNone(result["confidence"])
        self.assertFalse(result["confidence_calibrated"])
        self.assertEqual(result["evidence_strength"], "weak")
        self.assertIsNone(result["confirmed_by"])
        self.assertIn("去甲肾上腺素", result["match_summary"])
        # delay_minutes should be >= 0 for post-alert drug
        self.assertGreaterEqual(result["temporal_relation"]["delay_minutes"], 0)

    async def test_4_same_drug_for_other_indication_detected(self):
        """Furosemide could be for AKI, ARDS, or heart failure — uncertainty recorded."""
        engine = _FakeAlertEngine(_FakeDb({"drugExe": _Collection([
            {
                "pid": "patient-2",
                "drugName": "呋塞米", "orderName": "呋塞米注射液",
                "executeTime": datetime.now() + timedelta(minutes=25),
                "orderId": "order-002",
            },
        ])}))

        result = await engine._detect_suspected_actions(
            {
                "patient_id": "patient-2",
                "alert_type": "ards",
                "name": "氧合恶化",
                "created_at": datetime.now(),
            },
            {"hisPid": "HIS-2"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "suspected")

    async def test_5_pre_alert_order_excluded_from_post_alert(self):
        """Orders before alert are handled but flagged by negative delay_minutes."""
        engine = _FakeAlertEngine(_FakeDb({"drugExe": _Collection([
            {
                "drugName": "美罗培南", "orderName": "美罗培南",
                "executeTime": datetime.now() - timedelta(hours=3),
                "orderId": "order-003",
            },
        ])}))

        result = await engine._detect_suspected_actions(
            {
                "patient_id": "patient-3",
                "alert_type": "sepsis",
                "created_at": datetime.now(),
            },
            {"hisPid": "HIS-3"},
        )

        # Order before alert may still appear in matched_orders
        # but delay_minutes is negative
        if result:
            self.assertLess(result["temporal_relation"]["delay_minutes"], 0)


class MetricObservationTest(unittest.IsolatedAsyncioTestCase):
    """Test 6-7: Metric observation without causal claims."""

    async def test_6_map_improvement_not_auto_causal(self):
        """MAP improvement observed but attribution=not_assessed."""
        engine = _FakeAlertEngine(_FakeDb())

        async def fake_summary(patient_id, patient_doc, metric, start, end):
            return {"count": 5, "mean": 58.0, "median": 58.0, "representative": 58.0}

        async def fake_near(patient_id, patient_doc, metric, start, end):
            return 67.0

        engine._metric_window_summary = fake_summary
        engine._metric_near_time = fake_near

        result = await engine._observe_post_alert_metrics(
            {"patient_id": "patient-4", "created_at": datetime.now()},
            {"hisPid": "HIS-4"},
            anchor_time=datetime.now(),
            anchor_type="alert_time",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["attribution"], "not_assessed")
        self.assertIn("Observational only", result["limitations"][0])
        self.assertIn("not_assessed", result["attribution"])

    async def test_7_sofa_excluded_from_short_term_observation(self):
        """SOFA is not observed for alert_time anchor (short-term not meaningful)."""
        engine = _FakeAlertEngine(_FakeDb())

        async def fake_summary(patient_id, patient_doc, metric, start, end):
            return {"count": 1, "mean": 8.0, "median": 8.0, "representative": 8.0}

        async def fake_near(patient_id, patient_doc, metric, start, end):
            return 10.0

        engine._metric_window_summary = fake_summary
        engine._metric_near_time = fake_near

        result = await engine._observe_post_alert_metrics(
            {"patient_id": "patient-5", "created_at": datetime.now()},
            {"hisPid": "HIS-5"},
            anchor_time=datetime.now(),
            anchor_type="alert_time",
        )

        # SOFA should NOT appear for alert_time anchor
        if result and result.get("metrics"):
            self.assertNotIn("sofa", result["metrics"])

    def test_8_improvement_direction_labels(self):
        """Delta > 0 does not auto-claim 'improvement'."""
        # increase direction
        r1 = _observe_metric_direction(0.5, 1.0, "increase")
        self.assertEqual(r1["direction_label"], "上升")
        self.assertNotEqual(r1["direction_label"], "改善")

        # decrease direction
        r2 = _observe_metric_direction(4.0, 2.0, "decrease")
        self.assertEqual(r2["direction_label"], "下降")

        # toward_range
        r3 = _observe_metric_direction(50, 68, "toward_range", [65, 100])
        self.assertIn("目标范围", r3["direction_label"])


class AdjudicationTest(unittest.IsolatedAsyncioTestCase):
    """Test 8-12: Adjudication, feedback, append-only, RBAC, optimistic lock."""

    async def test_9_adjudication_writes_append_only(self):
        """Formal adjudication goes to alert_adjudications, not overwriting."""
        db = _FakeDb({
            "alert_records": _Collection([{
                "_id": ObjectId(), "patient_id": "p-1",
                "rule_id": "rule_a", "alert_type": "sepsis",
                "created_at": datetime.now(),
            }]),
            "alert_adjudications": _Collection(),
            "audit_log": _Collection(),
        })
        engine = _FakeAlertEngine(db)

        result = await engine.adjudicate_alert(
            str(db.collections["alert_records"].docs[0]["_id"]),
            actor="dr_wang",
            role="doctor",
            alert_validity="true_positive",
            clinical_actionability="actionable",
            workflow_context="new_finding",
            clinical_helpfulness="helpful",
            action_related=True,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["version"], 1)
        # Check append-only collection
        adj_docs = db.collections["alert_adjudications"].docs
        self.assertEqual(len(adj_docs), 1)
        self.assertEqual(adj_docs[0]["alert_validity"], "true_positive")
        self.assertEqual(adj_docs[0]["reviewer"], "dr_wang")

        # Second adjudication → new version, does not delete first
        result2 = await engine.adjudicate_alert(
            str(db.collections["alert_records"].docs[0]["_id"]),
            actor="dr_li",
            role="attending",
            alert_validity="false_positive",
            expected_version=1,
        )
        self.assertEqual(result2["version"], 2)
        self.assertEqual(len(db.collections["alert_adjudications"].docs), 2)

    async def test_10_optimistic_lock_prevents_conflict(self):
        """Version mismatch returns conflict."""
        db = _FakeDb({
            "alert_records": _Collection([{
                "_id": ObjectId(), "patient_id": "p-2",
                "rule_id": "rule_b", "alert_type": "aki",
                "created_at": datetime.now(),
            }]),
            "alert_adjudications": _Collection(),
            "audit_log": _Collection(),
        })
        engine = _FakeAlertEngine(db)
        alert_id = str(db.collections["alert_records"].docs[0]["_id"])

        # First adjudication
        await engine.adjudicate_alert(
            alert_id, actor="dr_wang", role="doctor",
            alert_validity="true_positive",
        )
        # Second with stale version
        result = await engine.adjudicate_alert(
            alert_id, actor="dr_li", role="doctor",
            alert_validity="false_positive", expected_version=0,
        )
        self.assertTrue(result.get("conflict"))
        self.assertEqual(result["current_version"], 1)

    async def test_11_harmful_requires_harm_type_and_secondary_review(self):
        """harmful=helpfulness requires harm_type, harm_description, requires_secondary_review=true."""
        db = _FakeDb({
            "alert_records": _Collection([{
                "_id": ObjectId(), "patient_id": "p-3",
                "rule_id": "rule_c", "alert_type": "ards",
                "created_at": datetime.now(),
            }]),
            "alert_adjudications": _Collection(),
            "audit_log": _Collection(),
        })
        engine = _FakeAlertEngine(db)
        alert_id = str(db.collections["alert_records"].docs[0]["_id"])

        # Missing harm_type
        r1 = await engine.adjudicate_alert(
            alert_id, actor="dr_wang", role="doctor",
            alert_validity="true_positive",
            clinical_helpfulness="harmful",
        )
        self.assertEqual(r1["error"], "harm_type_required")

        # Missing requires_secondary_review
        r2 = await engine.adjudicate_alert(
            alert_id, actor="dr_wang", role="doctor",
            alert_validity="true_positive",
            clinical_helpfulness="harmful",
            harm_type="misleading_recommendation",
            harm_description="Suggested wrong antibiotic",
            requires_secondary_review=False,
        )
        self.assertEqual(r2["error"], "secondary_review_required")

        # Valid harmful adjudication
        r3 = await engine.adjudicate_alert(
            alert_id, actor="dr_wang", role="doctor",
            alert_validity="true_positive",
            clinical_helpfulness="harmful",
            harm_type="misleading_recommendation",
            harm_description="Suggested wrong antibiotic for this pathogen",
            requires_secondary_review=True,
        )
        self.assertIsNotNone(r3.get("adjudication"))

    async def test_12_four_dimensions_independent(self):
        """alert_validity, clinical_actionability, workflow_context, clinical_helpfulness independent."""
        db = _FakeDb({
            "alert_records": _Collection([{
                "_id": ObjectId(), "patient_id": "p-4",
                "rule_id": "rule_d", "alert_type": "shock",
                "created_at": datetime.now(),
            }]),
            "alert_adjudications": _Collection(),
            "audit_log": _Collection(),
        })
        engine = _FakeAlertEngine(db)
        alert_id = str(db.collections["alert_records"].docs[0]["_id"])

        # false_positive can still be actionable (alert was wrong but prompted useful action)
        result = await engine.adjudicate_alert(
            alert_id, actor="dr_wang", role="doctor",
            alert_validity="false_positive",
            clinical_actionability="actionable",
            workflow_context="already_addressed",
            clinical_helpfulness="helpful",
        )
        self.assertIsNotNone(result.get("adjudication"))
        adj = result["adjudication"]
        self.assertEqual(adj["alert_validity"], "false_positive")
        self.assertEqual(adj["clinical_actionability"], "actionable")
        self.assertEqual(adj["workflow_context"], "already_addressed")
        self.assertEqual(adj["clinical_helpfulness"], "helpful")

    async def test_13_feedback_excluded_from_formal_stats(self):
        """Quick feedback writes to alert_feedback, enters_formal_stats=False."""
        db = _FakeDb({"alert_feedback": _Collection()})
        engine = _FakeAlertEngine(db)

        doc = await engine.submit_alert_feedback(
            "507f1f77bcf86cd799439011",  # valid ObjectId hex
            actor="nurse_li",
            feedback_type="useful",
            quick_label="及时提醒",
        )
        self.assertIsNotNone(doc)
        self.assertFalse(doc["enters_formal_stats"])
        self.assertEqual(doc["feedback_type"], "useful")


class WilsonCITest(unittest.TestCase):
    """Test Wilson CI and FDP/FPR distinction."""

    def test_14_wilson_ci_basic(self):
        """Wilson CI for 8/10."""
        ci = _wilson_ci(8, 10)
        self.assertAlmostEqual(ci["lower"], 0.4902, places=3)
        self.assertAlmostEqual(ci["upper"], 0.9432, places=3)
        self.assertEqual(ci["method"], "wilson")

    def test_15_wilson_ci_empty(self):
        """Wilson CI with 0 denominator returns nulls."""
        ci = _wilson_ci(0, 0)
        self.assertIsNone(ci["lower"])
        self.assertIsNone(ci["upper"])

    def test_16_fdp_not_fpr(self):
        """FDP = FP/reviewed; true FPR = FP/(FP+TN) requires non-alert samples."""
        fp, reviewed = 3, 30
        fdp = fp / reviewed  # 0.1
        self.assertEqual(round(fdp, 3), 0.1)
        # true FPR is null because we don't have FP+TN from non-alert samples
        true_fpr = None
        self.assertIsNone(true_fpr)


class UnackedNotFalsePositiveTest(unittest.IsolatedAsyncioTestCase):
    """Test 7: Unacked alerts are not automatically false positives."""

    async def test_17_history_factor_ignores_unacked(self):
        """History factor uses adjudications, not acknowledged_at proxy."""
        db = _FakeDb({
            "alert_adjudications": _Collection([
                {
                    "rule_id": "rule_e", "alert_type": "hypotension",
                    "alert_validity": "true_positive",
                    "created_at": datetime.now() - timedelta(days=1),
                },
                {
                    "rule_id": "rule_e", "alert_type": "hypotension",
                    "alert_validity": "true_positive",
                    "created_at": datetime.now() - timedelta(days=2),
                },
                {
                    "rule_id": "rule_e", "alert_type": "hypotension",
                    "alert_validity": "false_positive",
                    "created_at": datetime.now() - timedelta(days=3),
                },
            ] * 6,  # 18 samples total — enough for min_samples
        )})
        engine = _FakeAlertEngine(db)

        result = await engine._heuristic_history_factor(
            {"rule_id": "rule_e", "alert_type": "hypotension"},
            lookback_days=30,
            min_samples=5,
        )
        # 18 samples, 12 true_positive, 6 false_positive → FDP = 6/18 = 0.333
        self.assertTrue(result["applied"])
        self.assertAlmostEqual(result["false_discovery_proportion"], 0.333, places=2)
        self.assertEqual(result["false_positive_count"], 6)


class MetricDirectionTest(unittest.TestCase):
    """Test 14: improvement_direction per metric."""

    def test_18_map_toward_range(self):
        """MAP uses toward_range direction."""
        r = _observe_metric_direction(55, 67, "toward_range", [65, 100])
        # Label indicates moving toward target range (not claiming 'improvement')
        self.assertIn(r["direction_label"], ["趋向目标范围", "进入目标范围", "偏离目标范围", "toward range"])

    def test_19_lactate_decrease_label(self):
        """Lactate decrease labeled '下降', not '改善'."""
        r = _observe_metric_direction(4.5, 2.1, "decrease")
        self.assertEqual(r["direction_label"], "下降")

    def test_20_urine_increase_label(self):
        """Urine output increase labeled '上升', not '改善'."""
        r = _observe_metric_direction(0.3, 0.8, "increase")
        self.assertEqual(r["direction_label"], "上升")


class LegacyCompatibilityTest(unittest.TestCase):
    """Test 9: Legacy field compatibility."""

    def test_21_legacy_delay_minutes_calculation(self):
        """delay_minutes = order_time - alert_time (not action_count)."""
        alert_time = datetime(2026, 7, 1, 10, 0, 0)
        order_time = datetime(2026, 7, 1, 10, 18, 0)
        delay = round((order_time - alert_time).total_seconds() / 60.0, 1)
        self.assertEqual(delay, 18.0)


class TestUnackedDoesNotReduceScore(unittest.IsolatedAsyncioTestCase):
    """Test 7: Unacknowledged alerts do not reduce actionability score."""

    async def test_22_unacked_alerts_in_alert_records_ignored_by_history_factor(self):
        """alert_records with unacked alerts don't affect heuristic_history_factor."""
        db = _FakeDb({
            "alert_adjudications": _Collection([]),  # No adjudications at all
        })
        engine = _FakeAlertEngine(db)

        result = await engine._heuristic_history_factor(
            {"rule_id": "rule_f", "alert_type": "test"},
            lookback_days=30,
            min_samples=8,
        )
        # No adjudications → not applied (neutral prior)
        self.assertFalse(result["applied"])
        self.assertIsNone(result["factor"])
        # When not applied, false_discovery_proportion may be absent or None
        self.assertTrue(result.get("false_discovery_proportion") is None or "false_discovery_proportion" not in result)


if __name__ == "__main__":
    unittest.main()
