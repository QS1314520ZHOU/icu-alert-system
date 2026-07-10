"""Tests for subphenotype × treatment_class × outcome stratified analysis."""

import asyncio
import unittest
from datetime import datetime, timedelta

from bson import ObjectId

from app.alert_engine.subphenotype_stratified_outcome import (
    SubphenotypeStratifiedOutcomeMixin,
    classify_order_drug,
    classify_action_taken,
    classify_alert_treatment,
    DRUG_TO_TREATMENT_CLASS,
    _LIMITATIONS,
    _FORBIDDEN_PHRASES,
)


# ---------------------------------------------------------------------------
# Test helpers (same pattern as test_alert_actionability.py)
# ---------------------------------------------------------------------------


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key, direction):
        reverse = direction == -1
        self._docs.sort(key=lambda item: item.get(key) if isinstance(item, dict) else item, reverse=reverse)
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

    async def find_one(self, query, sort=None, projection=None):
        docs = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            docs.sort(key=lambda item: item.get(key), reverse=direction == -1)
        return dict(docs[0]) if docs else None

    async def insert_one(self, doc):
        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = ObjectId()
        self.docs.append(doc_copy)

        class _Result:
            inserted_id = doc_copy["_id"]

        return _Result()

    async def insert_many(self, docs):
        ids = []
        for doc in docs:
            doc_copy = dict(doc)
            if "_id" not in doc_copy:
                doc_copy["_id"] = ObjectId()
            self.docs.append(doc_copy)
            ids.append(doc_copy["_id"])

        class _Result:
            inserted_ids = ids

        return _Result()

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._match(doc, query)]

        class _Result:
            deleted_count = before - len(self.docs)

        return _Result()

    async def update_one(self, selector, update):
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return

    async def count_documents(self, query):
        return len([doc for doc in self.docs if self._match(doc, query)])

    @staticmethod
    def _resolve(doc, dotted_key):
        """Resolve a dotted key path like 'action_taken.matched' against a nested dict."""
        parts = dotted_key.split(".")
        current = doc
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    @staticmethod
    def _exists(doc, dotted_key):
        """Check if a dotted key path exists in a nested dict."""
        parts = dotted_key.split(".")
        current = doc
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        return True

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
            current = _Collection._resolve(doc, key)
            if isinstance(value, dict):
                if "$gte" in value and not (current is not None and current >= value["$gte"]):
                    return False
                if "$lte" in value and not (current is not None and current <= value["$lte"]):
                    return False
                if "$ne" in value and current == value["$ne"]:
                    return False
                if "$exists" in value:
                    exists = _Collection._exists(doc, key)
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


class _FakeEngine(SubphenotypeStratifiedOutcomeMixin):
    def __init__(self, db, cfg=None):
        self.db = db
        self._cfg_data = cfg or {
            "alert_engine": {
                "subphenotype_stratified": {
                    "enabled": True,
                    "min_sample": 5,  # Lower for test convenience
                    "gap_low": -0.2,
                    "gap_high": 0.2,
                    "persist_neutral": False,
                    "outcome_window": "2h",
                    "lookback_days": 90,
                }
            }
        }

    def _cfg(self, *path, default=None):
        cursor = self._cfg_data
        for key in path:
            if not isinstance(cursor, dict):
                return default
            cursor = cursor.get(key)
        return cursor if cursor is not None else default


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestClassifyOrderDrug(unittest.TestCase):
    """Test drug name → treatment_class mapping."""

    def test_exact_match(self):
        self.assertEqual(classify_order_drug("去甲肾上腺素"), "vasopressor")
        self.assertEqual(classify_order_drug("美罗培南"), "antimicrobial")
        self.assertEqual(classify_order_drug("甲泼尼龙"), "steroid")
        self.assertEqual(classify_order_drug("呋塞米"), "diuretic")
        self.assertEqual(classify_order_drug("右美托咪定"), "sedation")

    def test_substring_match(self):
        # "头孢曲松" contains "头孢"
        self.assertEqual(classify_order_drug("头孢曲松"), "antimicrobial")
        # "哌拉西林他唑巴坦" contains "哌拉西林"
        self.assertEqual(classify_order_drug("哌拉西林他唑巴坦"), "antimicrobial")

    def test_unknown_drug(self):
        self.assertEqual(classify_order_drug("未知药物XYZ"), "other")
        self.assertEqual(classify_order_drug(""), "other")
        self.assertEqual(classify_order_drug(None), "other")

    def test_fluid_classified_as_other(self):
        self.assertEqual(classify_order_drug("乳酸林格"), "other")
        self.assertEqual(classify_order_drug("氯化钠"), "other")


class TestClassifyActionTaken(unittest.TestCase):
    """Test orders list → dominant treatment_class."""

    def test_single_order(self):
        orders = [{"drug_name": "去甲肾上腺素"}]
        self.assertEqual(classify_action_taken(orders), "vasopressor")

    def test_multiple_orders_same_class(self):
        orders = [
            {"drug_name": "去甲肾上腺素"},
            {"drug_name": "肾上腺素"},
        ]
        self.assertEqual(classify_action_taken(orders), "vasopressor")

    def test_mixed_orders_majority_wins(self):
        orders = [
            {"drug_name": "去甲肾上腺素"},
            {"drug_name": "肾上腺素"},
            {"drug_name": "美罗培南"},
        ]
        self.assertEqual(classify_action_taken(orders), "vasopressor")

    def test_empty_orders(self):
        self.assertEqual(classify_action_taken([]), "other")

    def test_order_name_fallback(self):
        orders = [{"order_name": "万古霉素注射液"}]
        self.assertEqual(classify_action_taken(orders), "antimicrobial")


class TestClassifyAlertTreatment(unittest.TestCase):
    """Test alert metadata → treatment_class inference."""

    def test_shock_category(self):
        alert = {"category": "shock", "parameter": "map", "name": "低血压"}
        self.assertEqual(classify_alert_treatment(alert), "vasopressor")

    def test_sepsis_category(self):
        alert = {"category": "sepsis", "name": "脓毒症预警"}
        self.assertEqual(classify_alert_treatment(alert), "antimicrobial")

    def test_ards_category(self):
        alert = {"category": "ards", "parameter": "spo2"}
        self.assertEqual(classify_alert_treatment(alert), "steroid")

    def test_aki_category(self):
        alert = {"category": "aki", "parameter": "cr"}
        self.assertEqual(classify_alert_treatment(alert), "diuretic")

    def test_sedation_category(self):
        alert = {"category": "delir", "name": "谵妄评估"}
        self.assertEqual(classify_alert_treatment(alert), "sedation")

    def test_no_match(self):
        alert = {"category": "unknown", "name": "xyz"}
        self.assertEqual(classify_alert_treatment(alert), "other")


class TestStratifiedSignalComputation(unittest.TestCase):
    """Test that stratified differences are identified correctly."""

    def _make_engine(self, alerts, patients, cfg=None):
        db = _FakeDb({
            "alert_records": _Collection(alerts),
            "patient": _Collection(patients),
        })
        return _FakeEngine(db, cfg)

    def test_underperforming_signal_detected(self):
        """When a subphenotype has significantly lower improved rate, produce underperforming."""
        now = datetime.now()
        pid_alpha = str(ObjectId())
        pid_beta = str(ObjectId())

        # Alpha patients: 2/10 improved with vasopressor (20%)
        alerts = []
        for i in range(10):
            alerts.append({
                "patient_id": pid_alpha if i < 10 else pid_beta,
                "action_taken": {
                    "matched": True,
                    "orders": [{"drug_name": "去甲肾上腺素"}],
                },
                "outcome_delta": {
                    "windows": {
                        "2h": {"map": {"improved": i < 2}},  # 2/10 improved
                    },
                    "improved_any": i < 2,
                },
                "created_at": now - timedelta(days=1),
            })

        # Beta patients: 8/10 improved with vasopressor (80%)
        for i in range(10):
            alerts.append({
                "patient_id": pid_beta,
                "action_taken": {
                    "matched": True,
                    "orders": [{"drug_name": "去甲肾上腺素"}],
                },
                "outcome_delta": {
                    "windows": {
                        "2h": {"map": {"improved": i < 8}},  # 8/10 improved
                    },
                    "improved_any": i < 8,
                },
                "created_at": now - timedelta(days=1),
            })

        patients = [
            {"_id": ObjectId(pid_alpha), "current_profile": {"sepsis_subphenotype": {"phenotype": "alpha_hyperinflammatory"}}},
            {"_id": ObjectId(pid_beta), "current_profile": {"sepsis_subphenotype": {"phenotype": "beta_immunosuppressed"}}},
        ]

        cfg = {
            "alert_engine": {
                "subphenotype_stratified": {
                    "enabled": True,
                    "min_sample": 5,
                    "gap_low": -0.2,
                    "gap_high": 0.2,
                    "persist_neutral": False,
                    "outcome_window": "2h",
                    "lookback_days": 90,
                }
            }
        }
        engine = self._make_engine(alerts, patients, cfg)

        signals = asyncio.run(engine.compute_stratified_signals(now=now))

        # Alpha should be underperforming (20% vs cohort ~50%)
        alpha_signals = [s for s in signals if s["subphenotype"] == "alpha_hyperinflammatory"]
        self.assertTrue(len(alpha_signals) > 0, "Should produce signal for alpha")
        self.assertEqual(alpha_signals[0]["signal"], "underperforming")
        self.assertTrue(alpha_signals[0]["rate_gap"] < 0)
        self.assertEqual(alpha_signals[0]["treatment_class"], "vasopressor")

    def test_sample_size_insufficient(self):
        """When sample size < min_sample, no signal is produced."""
        now = datetime.now()
        pid = str(ObjectId())
        alerts = []
        # Only 3 alerts — below min_sample of 5
        for i in range(3):
            alerts.append({
                "patient_id": pid,
                "action_taken": {
                    "matched": True,
                    "orders": [{"drug_name": "去甲肾上腺素"}],
                },
                "outcome_delta": {
                    "windows": {"2h": {"map": {"improved": False}}},
                    "improved_any": False,
                },
                "created_at": now - timedelta(days=1),
            })

        patients = [
            {"_id": ObjectId(pid), "current_profile": {"sepsis_subphenotype": {"phenotype": "alpha_hyperinflammatory"}}},
        ]

        engine = self._make_engine(alerts, patients)
        signals = asyncio.run(engine.compute_stratified_signals(now=now))
        self.assertEqual(len(signals), 0, "Should not produce signal when sample is too small")

    def test_neutral_not_persisted(self):
        """When persist_neutral=False, neutral signals are filtered out."""
        now = datetime.now()
        pid = str(ObjectId())
        alerts = []
        # 10 alerts, 5 improved — 50% rate, cohort also 50% → neutral
        for i in range(10):
            alerts.append({
                "patient_id": pid,
                "action_taken": {
                    "matched": True,
                    "orders": [{"drug_name": "去甲肾上腺素"}],
                },
                "outcome_delta": {
                    "windows": {"2h": {"map": {"improved": i < 5}}},
                    "improved_any": i < 5,
                },
                "created_at": now - timedelta(days=1),
            })

        patients = [
            {"_id": ObjectId(pid), "current_profile": {"sepsis_subphenotype": {"phenotype": "alpha_hyperinflammatory"}}},
        ]

        cfg = {
            "alert_engine": {
                "subphenotype_stratified": {
                    "enabled": True,
                    "min_sample": 5,
                    "gap_low": -0.2,
                    "gap_high": 0.2,
                    "persist_neutral": False,
                    "outcome_window": "2h",
                    "lookback_days": 90,
                }
            }
        }
        engine = self._make_engine(alerts, patients, cfg)
        signals = asyncio.run(engine.compute_stratified_signals(now=now))
        # With only one subphenotype and one treatment, cohort_rate == improved_rate → gap=0 → neutral
        self.assertEqual(len(signals), 0, "Neutral signals should not be persisted when persist_neutral=False")


class TestCautionMounting(unittest.TestCase):
    """Test that stratified_caution is only mounted for approved signals."""

    def _make_engine(self, score_docs, patient_doc):
        db = _FakeDb({
            "score": _Collection(score_docs),
        })
        return _FakeEngine(db), patient_doc

    def test_approved_underperforming_mounts_caution(self):
        """Approved underperforming signal should mount caution on matching alert."""
        signal_id = ObjectId()
        signal_doc = {
            "_id": signal_id,
            "score_type": "subphenotype_treatment_signal",
            "status": "approved",
            "subphenotype": "alpha_hyperinflammatory",
            "treatment_class": "vasopressor",
            "signal": "underperforming",
        }

        patient_doc = {
            "current_profile": {
                "sepsis_subphenotype": {"phenotype": "alpha_hyperinflammatory"}
            }
        }

        engine, patient_doc = self._make_engine([signal_doc], patient_doc)

        alert_doc = {
            "category": "shock",
            "parameter": "map",
            "extra": {},
        }

        asyncio.run(engine.mount_stratified_caution(alert_doc, patient_doc))

        caution = alert_doc.get("extra", {}).get("stratified_caution")
        self.assertIsNotNone(caution, "Should mount stratified_caution")
        self.assertEqual(caution["subphenotype"], "alpha_hyperinflammatory")
        self.assertEqual(caution["treatment_class"], "vasopressor")
        self.assertIn("床旁判断", caution["note"])
        self.assertEqual(caution["signal_id"], str(signal_id))

    def test_pending_review_does_not_mount(self):
        """Pending review signals should NOT mount caution."""
        signal_doc = {
            "_id": ObjectId(),
            "score_type": "subphenotype_treatment_signal",
            "status": "pending_review",
            "subphenotype": "alpha_hyperinflammatory",
            "treatment_class": "vasopressor",
            "signal": "underperforming",
        }

        patient_doc = {
            "current_profile": {
                "sepsis_subphenotype": {"phenotype": "alpha_hyperinflammatory"}
            }
        }

        engine, patient_doc = self._make_engine([signal_doc], patient_doc)

        alert_doc = {
            "category": "shock",
            "parameter": "map",
            "extra": {},
        }

        asyncio.run(engine.mount_stratified_caution(alert_doc, patient_doc))

        caution = alert_doc.get("extra", {}).get("stratified_caution")
        self.assertIsNone(caution, "Pending review signal should NOT mount caution")

    def test_rejected_does_not_mount(self):
        """Rejected signals should NOT mount caution."""
        signal_doc = {
            "_id": ObjectId(),
            "score_type": "subphenotype_treatment_signal",
            "status": "rejected",
            "subphenotype": "alpha_hyperinflammatory",
            "treatment_class": "vasopressor",
            "signal": "underperforming",
        }

        patient_doc = {
            "current_profile": {
                "sepsis_subphenotype": {"phenotype": "alpha_hyperinflammatory"}
            }
        }

        engine, patient_doc = self._make_engine([signal_doc], patient_doc)

        alert_doc = {
            "category": "shock",
            "parameter": "map",
            "extra": {},
        }

        asyncio.run(engine.mount_stratified_caution(alert_doc, patient_doc))

        caution = alert_doc.get("extra", {}).get("stratified_caution")
        self.assertIsNone(caution, "Rejected signal should NOT mount caution")

    def test_non_matching_treatment_class_no_caution(self):
        """When alert treatment_class doesn't match signal, no caution mounted."""
        signal_doc = {
            "_id": ObjectId(),
            "score_type": "subphenotype_treatment_signal",
            "status": "approved",
            "subphenotype": "alpha_hyperinflammatory",
            "treatment_class": "vasopressor",
            "signal": "underperforming",
        }

        patient_doc = {
            "current_profile": {
                "sepsis_subphenotype": {"phenotype": "alpha_hyperinflammatory"}
            }
        }

        engine, patient_doc = self._make_engine([signal_doc], patient_doc)

        # AKI alert — diuretic class, doesn't match vasopressor
        alert_doc = {
            "category": "aki",
            "parameter": "cr",
            "extra": {},
        }

        asyncio.run(engine.mount_stratified_caution(alert_doc, patient_doc))

        caution = alert_doc.get("extra", {}).get("stratified_caution")
        self.assertIsNone(caution, "Non-matching treatment_class should NOT mount caution")


class TestReasoningContent(unittest.TestCase):
    """Test that reasoning contains no causal/directive language."""

    def test_no_forbidden_phrases_in_reasoning(self):
        """Reasoning text must not contain causal or directive phrases."""
        from app.alert_engine.subphenotype_stratified_outcome import _REASONING_TEMPLATE, _validate_reasoning

        reasoning = _REASONING_TEMPLATE.format(
            n=30,
            window="2小时",
            rate=40.0,
            cohort_rate=60.0,
            gap=-20.0,
        )
        reasoning = _validate_reasoning(reasoning)

        for phrase in _FORBIDDEN_PHRASES:
            self.assertNotIn(phrase, reasoning, f"Reasoning must not contain '{phrase}'")

    def test_limitations_always_present(self):
        """Every signal doc must have a non-empty limitations field."""
        self.assertTrue(len(_LIMITATIONS) > 0)
        self.assertIn("confounding by indication", _LIMITATIONS)
        self.assertIn("不可作为因果", _LIMITATIONS)

    def test_validate_reasoning_strips_forbidden(self):
        """_validate_reasoning should strip forbidden phrases."""
        from app.alert_engine.subphenotype_stratified_outcome import _validate_reasoning
        text = "该组应使用此方案，导致改善了预后"
        clean = _validate_reasoning(text)
        self.assertNotIn("应使用", clean)
        self.assertNotIn("导致", clean)
        self.assertNotIn("改善了", clean)


class TestDisabledConfig(unittest.TestCase):
    """Test that disabled config prevents signal computation."""

    def test_disabled_returns_empty(self):
        cfg = {
            "alert_engine": {
                "subphenotype_stratified": {
                    "enabled": False,
                }
            }
        }
        db = _FakeDb()
        engine = _FakeEngine(db, cfg)

        signals = asyncio.run(engine.compute_stratified_signals())
        self.assertEqual(signals, [])


if __name__ == "__main__":
    unittest.main()
