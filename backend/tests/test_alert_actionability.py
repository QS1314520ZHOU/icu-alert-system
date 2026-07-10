import unittest
from datetime import datetime, timedelta

from bson import ObjectId

from app.alert_engine.alert_actionability import AlertActionabilityScorerMixin


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key, direction):
        reverse = direction == -1
        self._docs.sort(key=lambda item: item.get(key), reverse=reverse)
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

    async def find_one(self, query, sort=None):
        docs = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            docs.sort(key=lambda item: item.get(key), reverse=direction == -1)
        return dict(docs[0]) if docs else None

    async def update_one(self, selector, update):
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return

    async def update_many(self, selector, update):
        modified = 0
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                modified += 1

        class _Result:
            modified_count = modified

        return _Result()

    @staticmethod
    def _match(doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(_Collection._match(doc, item) for item in value):
                    return False
                continue
            current = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (current >= value["$gte"]):
                    return False
                if "$lte" in value and not (current <= value["$lte"]):
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
                    "recent_response_window_minutes": 60,
                }
            }
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

    def _is_night_window(self, now):
        return False


class AlertActionabilityTest(unittest.IsolatedAsyncioTestCase):
    async def test_compute_alert_actionability_keeps_weighted_score_stable(self):
        engine = _FakeAlertEngine(_FakeDb())

        async def fake_state(patient_id, patient_doc):
            return {"factor": 0.82, "signals": {}}

        async def fake_history(alert_doc, lookback_days, min_samples):
            return {"factor": 0.7, "false_positive_rate": 0.3, "samples": 20, "evaluated_samples": 14}

        async def fake_match(alert_doc, patient_doc, hours=24):
            return {
                "matched": True,
                "matched_keywords": ["去甲肾上腺素"],
                "action_time": datetime.now() + timedelta(minutes=18),
                "action_count": 2,
                "orders": [{"drug_name": "去甲肾上腺素"}],
                "summary": "去甲肾上腺素",
            }

        async def fake_recent_same_type(patient_id, alert_doc, minutes):
            return [{"acknowledged_at": datetime.now() - timedelta(minutes=10)}]

        engine._actionability_patient_state = fake_state
        engine._actionability_history_factor = fake_history
        engine._match_action_taken = fake_match
        engine._actionability_recent_same_type_alerts = fake_recent_same_type

        result = await engine._compute_alert_actionability(
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

        self.assertEqual(result["score"], 76.2)
        self.assertEqual(result["level"], "immediate")
        self.assertEqual(result["factors"]["severity_factor"], 0.75)
        self.assertEqual(result["factors"]["patient_state_factor"], 0.82)
        self.assertEqual(result["factors"]["history_factor"], 0.7)
        self.assertEqual(result["factors"]["medication_factor"], 0.92)
        self.assertEqual(result["factors"]["recent_response_factor"], 0.35)
        self.assertEqual(result["factors"]["circadian_factor"], 1.0)
        self.assertEqual(result["recent_same_type_response_count"], 1)

    async def test_refresh_alert_lifecycle_backfills_action_and_outcome_then_persists(self):
        oid = ObjectId()
        source_doc = {
            "_id": oid,
            "patient_id": "patient-1",
            "created_at": datetime.now() - timedelta(hours=2),
            "action_taken": None,
            "outcome_delta": None,
        }
        alert_records = _Collection([source_doc])
        engine = _FakeAlertEngine(_FakeDb({"alert_records": alert_records}))

        async def fake_match(alert_doc, patient_doc, hours=24):
            return {
                "matched": True,
                "action_time": datetime.now() - timedelta(minutes=20),
                "action_count": 1,
                "orders": [{"drug_name": "美罗培南"}],
                "summary": "美罗培南",
            }

        async def fake_outcome(alert_doc, patient_doc, action_taken):
            return {
                "action_time": action_taken["action_time"],
                "windows": {
                    "30m": {
                        "map": {
                            "baseline": 58.0,
                            "followup": 67.0,
                            "delta": 9.0,
                            "direction": "up",
                            "improved": True,
                        }
                    }
                },
                "improved_any": True,
            }

        engine._match_action_taken = fake_match
        engine._build_outcome_delta = fake_outcome

        refreshed = await engine.refresh_alert_lifecycle(dict(source_doc), persist=True)

        self.assertIsNotNone(refreshed["action_taken"])
        self.assertTrue(refreshed["action_taken"]["matched"])
        self.assertIsNotNone(refreshed["outcome_delta"])
        self.assertTrue(refreshed["outcome_delta"]["improved_any"])
        self.assertIsInstance(refreshed["lifecycle_updated_at"], datetime)

        stored = alert_records.docs[0]
        self.assertEqual(stored["action_taken"]["summary"], "美罗培南")
        self.assertTrue(stored["outcome_delta"]["improved_any"])
        self.assertIsInstance(stored["lifecycle_updated_at"], datetime)


if __name__ == "__main__":
    unittest.main()
