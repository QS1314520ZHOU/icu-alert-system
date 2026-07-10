from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class StandardizedObservation:
    concept: str
    value: Any
    unit: str
    timestamp: datetime | None
    source: str
    match_method: str = "none"
    raw_code: str = ""
    raw_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ClinicalDataAdapter(Protocol):
    data_source: str

    async def get_vitals_series(self, patient: dict[str, Any], concept: str, start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        ...

    async def get_labs(self, patient: dict[str, Any], concepts: list[str], start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        ...

    async def get_drug_exposure(self, patient: dict[str, Any], start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        ...

    async def get_devices(self, patient: dict[str, Any], concepts: list[str], start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        ...
