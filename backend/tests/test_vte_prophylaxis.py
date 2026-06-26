from datetime import datetime, timedelta
import unittest

from app.alert_engine.vte_prophylaxis import VteProphylaxisMixin


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
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
    yaml_cfg = {"alert_engine": {"vte_prophylaxis": {}}}


class _Vte(VteProphylaxisMixin):
    def __init__(self, rows):
        self.db = _Db(rows)
        self.config = _Cfg()

    def _get_cfg_list(self, path, default):
        return default

    async def _get_latest_assessment(self, pid, name):
        return None


class VteProphylaxisTest(unittest.IsolatedAsyncioTestCase):
    async def test_passive_activity_does_not_clear_immobility(self):
        now = datetime.now()
        rows = [
            {"time": now - timedelta(hours=36), "remark": "绝对卧床"},
            {"time": now - timedelta(hours=1), "remark": "翻身 被动活动"},
        ]
        mixin = _Vte(rows)
        hours = await mixin._immobility_hours({"icuAdmissionTime": now - timedelta(hours=48)}, "p1", now)
        self.assertGreater(hours, 0)


if __name__ == "__main__":
    unittest.main()
