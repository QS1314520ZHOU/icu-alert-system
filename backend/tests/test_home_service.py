from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.home_service import RoleHomeService
from app.services.shift_service import ShiftInfo


class _AsyncCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.index = 0

    def limit(self, _limit):
        return self

    def sort(self, *_args, **_kwargs):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self.index]
        self.index += 1
        return row


class _PatientCollection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *_args, **_kwargs):
        return _AsyncCursor(self.rows)


class _BrokenCollection:
    def find(self, *_args, **_kwargs):
        raise RuntimeError("nurse record query unavailable")


class _Db:
    def __init__(self):
        self.collections = {
            "patient": _PatientCollection(
                [
                    {"_id": "p1", "name": "张三", "bed": "1", "hisPid": "H1", "status": "admitted", "deptCode": "3439"},
                    {"_id": "p2", "name": "李四", "bed": "2", "hisPid": "H2", "status": "admitted", "deptCode": "3439"},
                ]
            ),
            "nurseRecords": _BrokenCollection(),
            "alert_records": _PatientCollection([]),
        }

    def col(self, name):
        return self.collections[name]


@pytest.mark.asyncio
async def test_head_nurse_view_keeps_beds_when_extended_metrics_fail():
    service = RoleHomeService(db=_Db())
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    shift = ShiftInfo(code="AP", name="AP班", start_time="08:00", end_time="20:00", start=now - timedelta(hours=1), end=now + timedelta(hours=11))

    result = await service._head_nurse_view(shift, dept_code="3439")

    assert [row["bed"] for row in result["beds"]] == ["1", "2"]
    assert result["workload_heatmap"] == []
    assert result["events"] == []
    assert result["quality"] == {"falls": 0, "pressure_ulcers": 0, "line_displacement": 0, "medication_errors": 0}
