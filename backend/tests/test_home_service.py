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


class _NurseRecordCollection:
    def __init__(self, rows):
        self.rows = list(rows)

    def find(self, *_args, **_kwargs):
        return _AsyncCursor(self.rows)


class _ReminderCollection:
    def __init__(self, rows):
        self.rows = list(rows)

    def find(self, query, projection=None):
        filtered = list(self.rows)
        if "is_active" in query:
            filtered = [r for r in filtered if r.get("is_active") == query["is_active"]]
        if "patient_id" in query and isinstance(query["patient_id"], dict):
            pids = query["patient_id"].get("$in", [])
            filtered = [r for r in filtered if r.get("patient_id") in pids]
        if "score_type" in query and isinstance(query["score_type"], dict):
            types = query["score_type"].get("$in", [])
            filtered = [r for r in filtered if r.get("score_type") in types]
        return _AsyncCursor(filtered)


class _Config:
    def __init__(self, yaml_cfg=None):
        self.yaml_cfg = yaml_cfg or {}


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


class _DbWithReminders:
    def __init__(self, reminders=None, nurse_records=None):
        self.collections = {
            "patient": _PatientCollection([
                {"_id": "p1", "name": "张三", "bed": "1", "hisPid": "H1", "status": "admitted", "deptCode": "3439"},
                {"_id": "p2", "name": "李四", "bed": "2", "hisPid": "H2", "status": "admitted", "deptCode": "3439"},
            ]),
            "nurseRecords": _NurseRecordCollection(nurse_records or []),
            "nurse_reminders": _ReminderCollection(reminders or []),
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


@pytest.mark.asyncio
async def test_nurse_timeline_populates_from_reminders():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    shift = ShiftInfo(code="AP", name="AP班", start_time="08:00", end_time="20:00", start=now - timedelta(hours=1), end=now + timedelta(hours=11))

    reminders = [
        {
            "_id": "r1", "patient_id": "p1", "score_type": "cam_icu", "is_active": True,
            "due_at": now - timedelta(minutes=30), "last_score_time": now - timedelta(hours=9),
            "severity": "critical", "name": "CAM-ICU评估超时", "code": "param_delirium_score",
        },
        {
            "_id": "r2", "patient_id": "p1", "score_type": "braden", "is_active": False,
            "due_at": now - timedelta(hours=2), "last_score_time": now - timedelta(hours=2),
            "resolved_at": now - timedelta(hours=1),
            "severity": "warning", "name": "BRADEN压疮风险评估超时", "code": "param_score_braden",
        },
    ]
    nurse_records = [
        {"pid": "p1", "recordTime": now - timedelta(minutes=30), "userName": "nurse1", "userId": "nurse1", "content": "护理记录"},
        {"pid": "p2", "recordTime": now - timedelta(minutes=20), "userName": "nurse1", "userId": "nurse1", "content": "护理记录"},
    ]
    config = _Config(yaml_cfg={
        "nurse_reminders": {
            "cam_icu": {"code": "param_delirium_score", "interval_hours": 8, "name": "CAM-ICU评估超时"},
            "braden": {"code": "param_score_braden", "interval_hours": 24, "name": "BRADEN压疮风险评估超时"},
        },
    })

    service = RoleHomeService(db=_DbWithReminders(reminders=reminders, nurse_records=nurse_records), config=config)
    result = await service.nurse_timeline("nurse1", shift)

    tasks = result.get("tasks", [])
    assert len(tasks) >= 2

    cam_task = next((t for t in tasks if "cam_icu" in t.get("source", "")), None)
    assert cam_task is not None
    assert cam_task["status"] == "overdue"
    assert cam_task["title"] == "CAM-ICU评估超时"
    assert cam_task["patient_id"] == "p1"

    braden_task = next((t for t in tasks if "braden" in t.get("source", "")), None)
    assert braden_task is not None
    assert braden_task["status"] in ("future", "done")


@pytest.mark.asyncio
async def test_nurse_timeline_empty_reminders():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    shift = ShiftInfo(code="AP", name="AP班", start_time="08:00", end_time="20:00", start=now - timedelta(hours=1), end=now + timedelta(hours=11))
    nurse_records = [
        {"pid": "p1", "recordTime": now - timedelta(minutes=30), "userName": "nurse1", "userId": "nurse1", "content": "护理记录"},
    ]
    config = _Config(yaml_cfg={"nurse_reminders": {"cam_icu": {"code": "param_delirium_score", "interval_hours": 8}}})

    service = RoleHomeService(db=_DbWithReminders(reminders=[], nurse_records=nurse_records), config=config)
    result = await service.nurse_timeline("nurse1", shift)

    assert not any("nurse_reminders:" in t.get("source", "") for t in result.get("tasks", []))


@pytest.mark.asyncio
async def test_nurse_timeline_no_config():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    shift = ShiftInfo(code="AP", name="AP班", start_time="08:00", end_time="20:00", start=now - timedelta(hours=1), end=now + timedelta(hours=11))
    nurse_records = [
        {"pid": "p1", "recordTime": now - timedelta(minutes=30), "userName": "nurse1", "userId": "nurse1", "content": "护理记录"},
    ]

    service = RoleHomeService(db=_DbWithReminders(reminders=[], nurse_records=nurse_records), config=None)
    result = await service.nurse_timeline("nurse1", shift)

    assert not any("nurse_reminders:" in t.get("source", "") for t in result.get("tasks", []))
