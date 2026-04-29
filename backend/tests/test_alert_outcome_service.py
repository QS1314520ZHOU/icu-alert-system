import unittest
from datetime import datetime, timedelta

from app.services.alert_outcome_service import AlertOutcomeService


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self.idx = 0

    def sort(self, key, direction=None):
        if isinstance(key, list):
            field, direction = key[0]
        else:
            field = key
        self.docs.sort(key=lambda item: item.get(field) or datetime.min, reverse=direction == -1)
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
            field, direction = sort[0]
            rows.sort(key=lambda item: item.get(field) or datetime.min, reverse=direction == -1)
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
    async def test_record_acknowledgement_maps_ui_feedback_to_outcome_disposition(self):
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
            alert,
            actor="doctor-a",
            disposition="false_positive",
            reason_code="not_clinically_relevant",
        )

        self.assertEqual(result["disposition"], "overridden")
        self.assertEqual(result["override_reason"]["code"], "not_clinically_relevant")
        self.assertGreaterEqual(result["time_to_acknowledge_minutes"], 0)

    async def test_scanner_health_flags_low_ppv_high_override_for_review(self):
        fired_at = datetime.now() - timedelta(days=1)
        docs = []
        for idx in range(12):
            docs.append(
                {
                    "alert_id": f"a-{idx}",
                    "patient_id": f"p-{idx}",
                    "scanner_name": "noisy_scanner",
                    "fired_at": fired_at + timedelta(minutes=idx),
                    "disposition": "overridden" if idx < 11 else "accepted",
                    "time_to_acknowledge_minutes": 4 + idx,
                    "outcomes": {"24h": "unknown"},
                    "override_reason": {"code": "duplicate_or_noise"},
                }
            )
        db = _Db({"alert_outcomes": _Collection(docs)})
        service = AlertOutcomeService(db)

        result = await service.scanner_health(days=7)
        row = result["rows"][0]

        self.assertEqual(row["scanner_name"], "noisy_scanner")
        self.assertEqual(row["drift_status"], "red")
        self.assertTrue(row["review_suggestion"])
        self.assertEqual(len(row["recent_overrides"]), 5)


if __name__ == "__main__":
    unittest.main()
