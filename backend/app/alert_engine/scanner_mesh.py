from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class DerivedFact:
    fact_id: str
    fact_type: str
    patient_id: str
    source_scanner: str
    value: dict[str, Any]
    confidence: float
    valid_from: datetime
    valid_until: datetime
    upstream_refs: list[str]


Subscriber = Callable[[DerivedFact], Awaitable[None] | None]


class ScannerMeshMetrics:
    def __init__(self) -> None:
        self.facts_published_total = 0
        self.query_count = 0
        self.query_latency_seconds_total = 0.0
        self.publish_errors_total = 0

    def snapshot(self) -> dict[str, float | int]:
        return {
            "scanner_mesh_facts_published_total": self.facts_published_total,
            "scanner_mesh_query_count": self.query_count,
            "scanner_mesh_query_latency_seconds_total": round(self.query_latency_seconds_total, 6),
            "scanner_mesh_publish_errors_total": self.publish_errors_total,
        }


class ScannerMesh:
    """In-process sidecar event bus for derived scanner facts.

    v1 is publish/query only. It never injects data back into scanners and does not write MongoDB.
    """

    def __init__(self, config=None) -> None:
        self.config = config
        self._facts: dict[str, list[DerivedFact]] = {}
        self._subscribers: list[Subscriber] = []
        self._lock = asyncio.Lock()
        self.metrics = ScannerMeshMetrics()

    def _cfg(self) -> dict[str, Any]:
        try:
            cfg = (self.config.yaml_cfg or {}).get("scanner_mesh", {}) if self.config is not None else {}
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    @property
    def enabled(self) -> bool:
        return self._cfg().get("enabled", False) is True

    @property
    def publish_only(self) -> bool:
        return self._cfg().get("publish_only", False) is True

    @property
    def subscribers_active(self) -> int:
        return len(self._subscribers)

    def _ttl(self, ttl_seconds: int | None = None) -> int:
        if ttl_seconds is not None:
            return max(1, int(ttl_seconds))
        return max(1, int(self._cfg().get("fact_ttl_seconds", 1800) or 1800))

    def _max_facts(self) -> int:
        return max(10, int(self._cfg().get("max_facts_per_patient", 500) or 500))

    def subscribe(self, subscriber: Subscriber) -> None:
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    async def publish_derived_fact(
        self,
        *,
        patient_id: str,
        fact_type: str,
        value: dict[str, Any],
        source_scanner: str,
        confidence: float = 1.0,
        ttl_seconds: int | None = None,
        upstream_refs: list[str] | None = None,
    ) -> DerivedFact | None:
        if not self.enabled:
            return None
        now = datetime.now()
        fact = DerivedFact(
            fact_id=str(uuid.uuid4()),
            fact_type=str(fact_type),
            patient_id=str(patient_id),
            source_scanner=str(source_scanner),
            value=value if isinstance(value, dict) else {"value": value},
            confidence=max(0.0, min(1.0, float(confidence))),
            valid_from=now,
            valid_until=now + timedelta(seconds=self._ttl(ttl_seconds)),
            upstream_refs=[str(item) for item in (upstream_refs or []) if str(item)],
        )
        try:
            async with self._lock:
                rows = [row for row in self._facts.get(fact.patient_id, []) if row.valid_until > now]
                rows.append(fact)
                rows = sorted(rows, key=lambda row: row.valid_from, reverse=True)[: self._max_facts()]
                self._facts[fact.patient_id] = rows
                self.metrics.facts_published_total += 1
            if not self.publish_only:
                for subscriber in list(self._subscribers):
                    result = subscriber(fact)
                    if asyncio.iscoroutine(result):
                        await result
            return fact
        except Exception:
            self.metrics.publish_errors_total += 1
            return None

    async def publish(self, patient_id: str, fact_type: str, value: dict[str, Any], source_scanner: str, confidence: float = 1.0, ttl_seconds: int | None = None, evidence_refs: list[str] | None = None) -> DerivedFact | None:
        return await self.publish_derived_fact(patient_id=patient_id, fact_type=fact_type, value=value, source_scanner=source_scanner, confidence=confidence, ttl_seconds=ttl_seconds, upstream_refs=evidence_refs)

    async def query_derived_facts(self, patient_id: str, fact_types: list[str] | None = None, time_window: timedelta | None = None) -> list[DerivedFact]:
        if not self.enabled:
            return []
        started = time.perf_counter()
        now = datetime.now()
        allowed = {str(item) for item in fact_types or [] if str(item)}
        lower_bound = now - time_window if time_window else None
        async with self._lock:
            rows = [row for row in self._facts.get(str(patient_id), []) if row.valid_until > now]
            if allowed:
                rows = [row for row in rows if row.fact_type in allowed]
            if lower_bound:
                rows = [row for row in rows if row.valid_from >= lower_bound]
        self.metrics.query_count += 1
        self.metrics.query_latency_seconds_total += time.perf_counter() - started
        return sorted(rows, key=lambda row: row.valid_from, reverse=True)

    async def query(self, patient_id: str, fact_types: list[str] | None = None, time_window: timedelta | None = None) -> list[dict[str, Any]]:
        return [asdict(row) for row in await self.query_derived_facts(patient_id, fact_types, time_window)]

    async def get(self, patient_id: str, fact_type: str) -> dict[str, Any] | None:
        rows = await self.query(str(patient_id), [fact_type])
        return rows[0] if rows else None

    async def list_patient_facts(self, patient_id: str) -> list[dict[str, Any]]:
        return await self.query(str(patient_id))

    def telemetry(self) -> dict[str, Any]:
        return {**self.metrics.snapshot(), "scanner_mesh_subscribers_active": self.subscribers_active}


async def _dry_run(patient_id: str) -> None:
    mesh = ScannerMesh(config=type("Cfg", (), {"yaml_cfg": {"scanner_mesh": {"enabled": True}}})())
    await mesh.publish(patient_id, "vital_trend", {"trend_direction": "stable", "slope": 0.0}, "dry_run", 1.0)
    rows = await mesh.query(patient_id)
    for row in rows:
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run ScannerMesh in-memory fact bus")
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("Only --dry-run is supported")
    asyncio.run(_dry_run(args.patient_id))


if __name__ == "__main__":
    main()
