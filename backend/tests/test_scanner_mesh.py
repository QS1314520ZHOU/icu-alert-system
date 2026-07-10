from __future__ import annotations

from datetime import timedelta

import pytest

from app.alert_engine.scanner_mesh import DerivedFact, ScannerMesh


def _cfg(enabled: bool = True):
    return type("Cfg", (), {"yaml_cfg": {"scanner_mesh": {"enabled": enabled, "fact_ttl_seconds": 60, "max_facts_per_patient": 3}}})()


@pytest.mark.asyncio
async def test_scanner_mesh_publish_and_query_in_memory() -> None:
    mesh = ScannerMesh(config=_cfg(True))
    fact = await mesh.publish("p1", "vital_trend", {"trend_direction": "up"}, "unit", confidence=0.8)

    assert isinstance(fact, DerivedFact)
    rows = await mesh.query_derived_facts("p1", ["vital_trend"], timedelta(minutes=5))
    assert len(rows) == 1
    assert rows[0].value["trend_direction"] == "up"
    assert mesh.telemetry()["scanner_mesh_facts_published_total"] == 1


@pytest.mark.asyncio
async def test_scanner_mesh_disabled_is_noop() -> None:
    mesh = ScannerMesh(config=_cfg(False))
    assert await mesh.publish("p1", "vital_trend", {"x": 1}, "unit") is None
    assert await mesh.query("p1") == []


@pytest.mark.asyncio
async def test_scanner_mesh_ttl_and_patient_cap() -> None:
    mesh = ScannerMesh(config=_cfg(True))
    await mesh.publish("p1", "a", {"n": 1}, "unit", ttl_seconds=1)
    await mesh.publish("p1", "b", {"n": 2}, "unit")
    await mesh.publish("p1", "c", {"n": 3}, "unit")
    await mesh.publish("p1", "d", {"n": 4}, "unit")

    rows = await mesh.query("p1")
    assert len(rows) == 3
    assert rows[0]["fact_type"] == "d"
