from __future__ import annotations

from datetime import datetime
from typing import Any


class EicuClinicalDataAdapter:
    data_source = "eicu"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.unavailable_reason = (
            "eICU-CRD adapter is reserved for offline external validation; "
            "PhysioNet credentialed access, DUA, CITI training, and an isolated PostgreSQL environment are required. "
            "It is not connected to the online production system in this phase."
        )

    async def get_vitals_series(self, patient: dict[str, Any], concept: str, start: datetime, end: datetime | None = None):
        raise NotImplementedError(self.unavailable_reason)

    async def get_labs(self, patient: dict[str, Any], concepts: list[str], start: datetime, end: datetime | None = None):
        raise NotImplementedError(self.unavailable_reason)

    async def get_drug_exposure(self, patient: dict[str, Any], start: datetime, end: datetime | None = None):
        raise NotImplementedError(self.unavailable_reason)

    async def get_devices(self, patient: dict[str, Any], concepts: list[str], start: datetime, end: datetime | None = None):
        raise NotImplementedError(self.unavailable_reason)
