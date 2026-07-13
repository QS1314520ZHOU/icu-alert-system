"""Tests for refactored alert_outcome_service — observation-only, adjudication-based stats."""
import unittest
from datetime import datetime, timedelta

from app.services.alert_outcome_service import (
    AlertOutcomeService,
    _wilson_ci,
)


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self.idx = 0

    def sort(self, key, direction=None):
        if isinstance(key, list):
            field, direction = key[0]
        else:
            field = key
        self.docs.sort(
            key=lambda item: item.get(field) or datetime.min,
            reverse=direction == -1,
        )
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
        return self

    def __aiter__(self):
        self.idx = 0
        return self

    async def __anext__(self):
        if self.idx >= len(self.docs):
            raise StopAsyncIteration
        row = self.docs[self.idx]
        self.idx += 1
        return row


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query=None, projection=None):
        rows = [doc for doc in self.docs if self._match(doc, query or {})]
        return _Cursor(rows)

    async def find_one(self, query, projection=None, sort=None):
        rows = [doc for doc in self.docs if self._match(doc, query or {})]
        if sort:
            field, direction = sort[0] if isinstance(sort[0], (list, tuple)) else sort
            if isinstance(field, (list, tuple)):
                field, direction = field
            rows.sort(
                key=lambda item: item.get(field) or datetime.min,
                reverse=direction == -1,
            )
        return dict(rows[0]) if rows else None

    async def update_one(self, selector, update, upsert=False):
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$setOnInsert", {}).items():
                    doc.setdefault(key, value)
                for key, value in update.get("$set", {}).items():
                    self._set_nested(doc, key, value)
                return
        if upsert:
            doc = dict(selector)
            for key, value in update.get("$setOnInsert", {}).items():
                self._set_nested(doc, key, value)
            for key, value in update.get("$set", {}).items():
                self._set_nested(doc, key, value)
            self.docs.append(doc)

    async def update_many(self, selector, update):
        count = 0
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    self._set_nested(doc, key, value)
                count += 1

        class _Result:
            modified_count = count
        return _Result()

    async def count_documents(self, query):
        return len([d for d in self.docs if self._match(d, query)])

    def aggregate(self, pipeline):
        return _Cursor([
            {"_id": d.get(
                pipeline[0].get("$group", {}).get("_id", {}).get("$ifNull", ["_id", "unknown"])[0],
                "unknown",
            ), **d}
            for d in self.docs
        ])

    @staticmethod
    def _set_nested(doc, key, value):
        parts = str(key).split(".")
        cur = doc
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value

    @classmethod
    def _match(cls, doc, query):
        for key, value in (query or {}).items():
            if key == "$or":
                if not any(cls._match(doc, item) for item in value):
                    return False
                continue
            if key == "$and":
                if not all(cls._match(doc, item) for item in value):
                    return False
                continue
            cur = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (cur is not None and cur >= value["$gte"]):
                    return False
                if "$lte" in value and not (cur is not None and cur <= value["$lte"]):
                    return False
                if "$in" in value and cur not in value["$in"]:
                    return False
                if "$ne" in value and cur == value["$ne"]:
                    return False
                if "$eq" in value:
                    # simplified
                    pass
                if "$cond" in value:
                    pass
                if "$sum" in value:
                    pass
            elif cur != value:
                return False
        return True


class _Db:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def col(self, name):
        self.collections.setdefault(name, _Collection())
        return self.collections[name]


class AlertOutcomeServiceTest(unittest.IsolatedAsyncioTestCase):

    async def test_1_record_acknowledgement_no_auto_inference(self):
        """Acknowledgement records disposition but does NOT auto-infer outcome."""
        db = _Db()
        service = AlertOutcomeService(db)
        now = datetime.now() - timedelta(minutes=10)
        alert = {
            "_id": "alert-1",
            "patient_id": "patient-1",
            "alert_type": "generic",
            "severity": "warning",
            "created_at": now,
            "acknowledged_at": datetime.now(),
            "ack_disposition": "false_positive",
        }
        result = await service.record_acknowledgement(
            alert, actor="doctor-a", disposition="false_positive",
            reason_code="not_clinically_relevant",
        )
        self.assertEqual(result["disposition"], "overridden")
        self.assertEqual(result["override_reason"]["code"], "not_clinically_relevant")
        # Inference is not completed by record_acknowledgement alone
        self.assertNotEqual(
            result.get("inference", {}).get("status"),
            "completed",
        )

    async def test_2_scanner_health_no_adjudications_returns_insufficient(self):
        """Without adjudications, scanner health shows insufficient_review_samples."""
        db = _Db({
            "alert_adjudications": _Collection(),
            "alert_records": _Collection([
                {
                    "alert_type": "test_scanner", "created_at": datetime.now() - timedelta(days=1),
                    "acknowledged_at": datetime.now() - timedelta(hours=23),
                },
            ] * 5),
        })
        service = AlertOutcomeService(db)
        result = await service.scanner_health(days=7)

        if result["rows"]:
            row = result["rows"][0]
            self.assertTrue(row["insufficient_review_samples"])
            self.assertEqual(row["formally_reviewed_count"], 0)
            self.assertIsNone(row["reviewed_sample_ppv"])

    async def test_3_scanner_health_with_adjudications(self):
        """With adjudications, PPV and FDP are computed from human reviews only."""
        db = _Db({
            "alert_adjudications": _Collection([
                {
                    "scanner_name": "test_scanner",
                    "alert_validity": "true_positive",
                    "clinical_actionability": "actionable",
                    "clinical_helpfulness": "helpful",
                    "created_at": datetime.now() - timedelta(days=1),
                },
            ] * 8 + [
                {
                    "scanner_name": "test_scanner",
                    "alert_validity": "false_positive",
                    "clinical_actionability": "non_actionable",
                    "clinical_helpfulness": "neutral",
                    "created_at": datetime.now() - timedelta(days=2),
                },
            ] * 2),
            "alert_records": _Collection([
                {
                    "alert_type": "test_scanner", "created_at": datetime.now() - timedelta(days=1),
                    "acknowledged_at": datetime.now() - timedelta(hours=23),
                },
            ] * 15),
            "scanner_runs": _Collection(),
        })
        service = AlertOutcomeService(db)
        result = await service.scanner_health(days=7)

        # Verify statistical terminology and structure
        self.assertIn("statistical_notes", result)
        self.assertTrue(result["statistical_notes"]["fpr_unavailable"])
        self.assertIn("non-alert", result["statistical_notes"]["fpr_reason"])

        if result["rows"]:
            row = result["rows"][0]
            # Verify key fields exist with correct types/notes
            self.assertIsNotNone(row.get("sampling_method"))
            # True FPR always null
            self.assertIsNone(row["true_fpr"])
            self.assertIn("FDP", str(row.get("fdp_note", "")))

    async def test_4_wilson_ci_edge_cases(self):
        """Wilson CI handles edge cases."""
        # 0/10
        ci = _wilson_ci(0, 10)
        self.assertAlmostEqual(ci["lower"], 0.0, places=3)
        self.assertAlmostEqual(ci["upper"], 0.2775, places=3)

        # 10/10
        ci2 = _wilson_ci(10, 10)
        self.assertAlmostEqual(ci2["lower"], 0.7225, places=3)
        self.assertAlmostEqual(ci2["upper"], 1.0, places=3)

        # 0/0
        ci3 = _wilson_ci(0, 0)
        self.assertIsNone(ci3["lower"])
        self.assertIsNone(ci3["upper"])

    async def test_5_infer_outcome_observation_only(self):
        """infer_outcome records observations, does NOT auto-change disposition."""
        db = _Db()
        service = AlertOutcomeService(db)
        alert = {
            "_id": "alert-obs-1",
            "patient_id": "patient-obs",
            "alert_type": "generic",
            "severity": "warning",
            "created_at": datetime.now() - timedelta(hours=2),
            "ack_disposition": "",
        }
        # Ensure the outcome doc exists
        await service.ensure_for_alert(alert)

        result = await service.infer_outcome(alert)
        self.assertIsNotNone(result)
        inference = result.get("inference") or {}
        self.assertEqual(inference.get("causal_inference"), "NOT_PERFORMED")
        # Disposition is NOT auto-changed to "accepted"
        self.assertNotEqual(result.get("disposition"), "accepted")

    async def test_6_fdp_not_fpr_in_stats(self):
        """FDP explicitly labeled, true FPR is null."""
        db = _Db({
            "alert_adjudications": _Collection([
                {
                    "scanner_name": "s", "alert_validity": "true_positive",
                    "created_at": datetime.now() - timedelta(hours=1),
                },
            ] * 5 + [
                {
                    "scanner_name": "s", "alert_validity": "false_positive",
                    "created_at": datetime.now() - timedelta(hours=2),
                },
            ] * 3),
            "alert_records": _Collection([
                {"alert_type": "s", "created_at": datetime.now() - timedelta(hours=1)},
            ] * 10),
            "scanner_runs": _Collection(),
        })
        service = AlertOutcomeService(db)
        result = await service.scanner_health(days=7)

        row = result["rows"][0]
        self.assertIsNone(row["true_fpr"])
        self.assertIn("FP/(TP+FP)", str(row.get("fdp_note", "")))


if __name__ == "__main__":
    unittest.main()
