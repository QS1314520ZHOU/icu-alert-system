"""表型规则模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class PhenotypeRuleStatus(StrEnum):
    """表型规则状态。"""
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class PhenotypeRule(BaseModel):
    """表型规则。"""
    id: str = ""
    name: str
    disease_id: str
    description: str = ""
    version: str = "v1.0.0"
    status: PhenotypeRuleStatus = PhenotypeRuleStatus.DRAFT
    dsl: dict = Field(default_factory=dict)  # JSON DSL expression
    compiled_expression: str = ""
    compiled_hash: str = ""
    input_schema: dict = Field(default_factory=dict)
    missing_policy: str = ""
    time_window: str = ""
    test_summary: dict = Field(default_factory=dict)
    quality_summary: dict = Field(default_factory=dict)
    created_by: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: str = ""
    published_by: str = ""
    published_at: Optional[datetime] = None
    revision: int = 1
