"""术语模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class TerminologyStatus(StrEnum):
    """术语状态。"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class Terminology(BaseModel):
    """术语。"""
    id: str = ""
    standard_name: str
    english_name: str = ""
    abbreviation: str = ""
    synonyms: list[str] = Field(default_factory=list)
    category: str = ""
    icd10_codes: list[str] = Field(default_factory=list)
    icd11_codes: list[str] = Field(default_factory=list)
    local_codes: list[str] = Field(default_factory=list)
    snomed_code: str = ""
    unit: str = ""
    description: str = ""
    related_disease_ids: list[str] = Field(default_factory=list)
    status: TerminologyStatus = TerminologyStatus.ACTIVE
    version: str = "v1.0.0"
    source: str = ""
    source_version: str = ""
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_by: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: str = ""
    published_by: str = ""
    published_at: Optional[datetime] = None
    revision: int = 1
    content_hash: str = ""
