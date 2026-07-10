import unittest
from datetime import datetime
from types import SimpleNamespace

from app.services.ai_monitor import AiMonitor


class _InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key, direction):
        reverse = direction == -1
        self._docs.sort(key=lambda x: x.get(key), reverse=reverse)
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
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _InsertResult(len(self.docs))

    async def update_one(self, selector, update, upsert=False):
        target = None
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in selector.items()):
                target = doc
                break
        if target is None and upsert:
            target = dict(selector)
            self.docs.append(target)
        if target is None:
            return
        for key, value in update.get("$setOnInsert", {}).items():
            target.setdefault(key, value)
        for key, value in update.get("$set", {}).items():
            target[key] = value

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if self._match(doc, query)])

    @staticmethod
    def _match(doc, query):
        for key, value in query.items():
            current = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (current >= value["$gte"]):
                    return False
                if "$lt" in value and not (current < value["$lt"]):
                    return False
            elif current != value:
                return False
        return True


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def col(self, name):
        if name not in self.collections:
            self.collections[name] = _Collection()
        return self.collections[name]


class AiMonitorTest(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_daily_aggregate_tracks_tokens_and_alerts(self):
        cfg = SimpleNamespace(
            yaml_cfg={
                "ai_service": {
                    "monitor": {
                        "enabled": True,
                        "aggregate_interval_seconds": 1,
                        "success_rate_alert_threshold": 0.9,
                        "p95_latency_alert_ms": 1000,
                        "min_samples_for_alert": 1,
                    }
                }
            }
        )
        db = _FakeDb()
        monitor = AiMonitor(db, cfg)

        await monitor.log_llm_call(
            module="ai_risk",
            model="test",
            prompt="a",
            output="b",
            latency_ms=2000,
            success=False,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        await monitor.log_llm_call(
            module="ai_risk",
            model="test",
            prompt="c",
            output="d",
            latency_ms=800,
            success=True,
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        )

        stats = await monitor.refresh_daily_aggregate(module="ai_risk", now=datetime.now())
        self.assertEqual(stats["total_tokens"], 45)
        self.assertEqual(stats["calls"], 2)
        self.assertEqual(stats["success_calls"], 1)

        summary = await monitor.get_daily_summary(date=datetime.now().strftime("%Y-%m-%d"))
        active_codes = {doc.get("alert_code") for doc in summary["active_alerts"]}
        self.assertIn("success_rate_low", active_codes)
        self.assertIn("p95_latency_high", active_codes)


if __name__ == "__main__":
    unittest.main()
