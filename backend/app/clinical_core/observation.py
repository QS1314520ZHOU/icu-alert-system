"""观察值：生命体征、检验、设备参数、评分、护理评估。

从 critical-care-alert-platform/src/ccalert/domain/observation.py 迁移。
导入路径已调整为 app.clinical_core.enums。
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .enums import DataQuality, ObservationCategory


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: ObservationCategory
    code: str
    display_name: str
    value_number: float | None = None
    value_text: str | None = None
    unit: str = ""
    observed_at: datetime
    source_system: str = ""
    source_record_id: str = ""
    data_quality: DataQuality = DataQuality.VALID

    @model_validator(mode="after")
    def _value_present(self) -> Self:
        if self.value_number is None and not self.value_text:
            raise ValueError("至少需要 value_number 或 value_text")
        return self

    @field_validator("observed_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("observed_at 必须为 timezone-aware datetime")
        return v
