from __future__ import annotations

from datetime import datetime

import pytest

from app.services.patient_narrative_service import PatientNarrativeService


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

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
    def __init__(self, rows=None):
        self.rows = rows or []
        self.upserts = []

    def find(self, *args, **kwargs):
        return _Cursor(self.rows)

    async def find_one(self, query=None, *args, **kwargs):
        query = query or {}
        for row in self.rows:
            if all(row.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return row
        return None

    async def update_one(self, query, update, upsert=False):
        self.upserts.append((query, update, upsert))
        record = {**query, **(update.get("$set") or {})}
        self.rows = [row for row in self.rows if not all(row.get(k) == v for k, v in query.items())]
        self.rows.append(record)


class _DB:
    def __init__(self):
        self.collections = {
            "patient_narratives": _Collection([]),
            "patient": _Collection([]),
            "paramData": _Collection([{"_id": "v1", "code": "param_SpO2", "value": 96, "time": datetime.now()}]),
            "labResult": _Collection([{"_id": "l1", "itemName": "乳酸", "value": 2.1, "authTime": datetime.now()}]),
            "drugExe": _Collection([{"_id": "d1", "drugName": "去甲肾上腺素", "executeTime": datetime.now()}]),
            "alert_records": _Collection([{"_id": "a1", "name": "低血压", "severity": "high", "created_at": datetime.now()}]),
            "nursing_score": _Collection([]),
            "workflow_events": _Collection([]),
            "score": _Collection([]),
        }

    def col(self, name):
        return self.collections.setdefault(name, _Collection([]))


@pytest.mark.asyncio
async def test_patient_narrative_generates_fixed_sections_without_llm(monkeypatch) -> None:
    async def _trajectory(self, patient_id):
        return self._bullet("轨迹预测未就绪：测试。", [], {"available": False})

    monkeypatch.setattr(PatientNarrativeService, "_trajectory_bullet", _trajectory)
    cfg = type("Cfg", (), {"yaml_cfg": {"patient_narrative": {"enabled": True, "max_context_chars": 2000}}})()
    service = PatientNarrativeService(db=_DB(), config=cfg, alert_engine=None)

    record = await service.generate_daily("p1", {"_id": "p1", "name": "P001", "hisBed": "B01", "clinicalDiagnosis": "感染性休克"}, refresh=True)

    assert record["json"]["generator_version"] == "patient-narrative-rules-v1"
    assert [section["section_type"] for section in record["json"]["sections"]] == ["overview", "respiratory", "hemodynamic", "neuro", "renal", "infection", "events", "trajectory"]
    assert "markdown" in record and "llm_context_text" in record
    first_bullet = record["json"]["sections"][0]["bullet_points"][0]
    assert first_bullet["value_snapshot"]
    assert "provenance" in record


@pytest.mark.asyncio
async def test_patient_narrative_disabled_by_default_degrades() -> None:
    cfg = type("Cfg", (), {"yaml_cfg": {}})()
    service = PatientNarrativeService(db=_DB(), config=cfg, alert_engine=None)
    record = await service.generate_daily("p1", {"_id": "p1"}, refresh=True)
    assert record["available"] is False
