from __future__ import annotations

import asyncio
from typing import Any

from app.services.runtime_config_service import RuntimeConfigService


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = list(rows)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, count: int):
        self.rows = self.rows[:count]
        return self

    def __aiter__(self):
        self.idx = 0
        return self

    async def __anext__(self):
        if self.idx >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self.idx]
        self.idx += 1
        return row


class _Col:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any]):
        rows = [row for row in self.rows if all(row.get(k) == v for k, v in query.items())]
        return _Cursor(rows)

    async def find_one(self, query: dict[str, Any], *args, **kwargs):
        sort = kwargs.get("sort")
        rows = [row for row in self.rows if all(row.get(k) == v for k, v in query.items())]
        if sort:
            key, direction = sort[0]
            rows = sorted(rows, key=lambda item: item.get(key) or 0, reverse=direction < 0)
        return rows[0] if rows else None

    async def insert_one(self, record: dict[str, Any]):
        self.rows.append(dict(record))
        return type("Result", (), {"inserted_id": "id1"})()

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False):
        row = await self.find_one(query)
        if row is None and upsert:
            row = dict(query)
            row.update(update.get("$setOnInsert") or {})
            self.rows.append(row)
        if row is not None:
            row.update(update.get("$set") or {})
        return type("Result", (), {})()


class _Db:
    def __init__(self) -> None:
        self.cols: dict[str, _Col] = {}

    def col(self, name: str):
        self.cols.setdefault(name, _Col())
        return self.cols[name]


def test_runtime_trajectory_config_filters_alert_codes_to_default_codes() -> None:
    service = RuntimeConfigService(db=None)
    value = service.normalize_trajectory_forecast(
        {
            "default_codes": ["HR", "MAP"],
            "alert_codes": ["MAP", "SpO2"],
            "thresholds": [
                {"code": "MAP", "operator": "<", "threshold": 65, "probability": 0.7, "severity": "high", "horizon_hours": 4},
                {"code": "SpO2", "operator": "<", "threshold": 90, "probability": 0.7, "severity": "high", "horizon_hours": 4},
            ],
        }
    )

    assert value["default_codes"] == ["HR", "MAP"]
    assert value["alert_codes"] == ["MAP"]
    assert [row["code"] for row in value["thresholds"]] == ["MAP"]


def test_runtime_trajectory_config_clamps_probability_and_horizon() -> None:
    service = RuntimeConfigService(db=None)
    value = service.normalize_trajectory_forecast(
        {
            "default_codes": ["MAP"],
            "alert_codes": ["MAP"],
            "horizon_hours": 99,
            "thresholds": [{"code": "MAP", "operator": "bad", "threshold": 65, "probability": 5, "severity": "high", "horizon_hours": 99}],
        }
    )

    assert value["horizon_hours"] == 12
    assert value["thresholds"][0]["operator"] == "<"
    assert value["thresholds"][0]["probability"] == 0.99
    assert value["thresholds"][0]["horizon_hours"] == 12


def test_runtime_config_versions_and_rollback() -> None:
    async def run() -> None:
        db = _Db()
        service = RuntimeConfigService(db)
        await service.update_modules([{"key": "ai", "name": "AI", "enabled": True}], actor="admin")
        await service.update_modules([{"key": "ai", "name": "AI", "enabled": False}], actor="admin")

        history = sorted(await service.history("modules"), key=lambda row: row["version"], reverse=True)
        assert [row["version"] for row in history] == [2, 1]

        result = await service.rollback("modules", 1, actor="admin", role="admin")
        assert result["value"][0]["enabled"] is True
        assert len(db.col("runtime_config_versions").rows) == 3

    asyncio.run(run())


def test_runtime_config_export_snapshot_contains_core_sections() -> None:
    async def run() -> None:
        db = _Db()
        service = RuntimeConfigService(db)
        snapshot = await service.export_snapshot()

        assert "runtime_configs" in snapshot
        assert "modules" in snapshot["runtime_configs"]
        assert "ai" in snapshot["runtime_configs"]
        assert "trajectory_forecast" in snapshot["runtime_configs"]
        assert "alert_rules" in snapshot
        assert "field_mappings" in snapshot

    asyncio.run(run())
