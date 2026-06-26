from datetime import datetime, timedelta
import unittest

from app.alert_engine.clinical_commons import urine_ml_h


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._iter = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *args, **kwargs):
        return _Cursor(self.rows)


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def col(self, name):
        return _Collection(self.rows)


class _Cfg:
    yaml_cfg = {"alert_engine": {"data_mapping": {"urine_output": {"codes": ["param_niaoLiang"]}}}}


class AkiCommonsTest(unittest.IsolatedAsyncioTestCase):
    async def test_urine_ml_h_uses_shared_hourly_output_logic(self):
        now = datetime.now()
        rows = [
            {"pid": "p1", "time": now - timedelta(hours=5), "code": "param_niaoLiang", "fVal": 30},
            {"pid": "p1", "time": now - timedelta(hours=3), "code": "param_niaoLiang", "fVal": 60},
            {"pid": "p1", "time": now - timedelta(hours=1), "code": "param_niaoLiang", "fVal": 30},
        ]
        assert await urine_ml_h(_Db(rows), _Cfg(), "p1", now, hours=6) == 20.0


if __name__ == "__main__":
    unittest.main()
