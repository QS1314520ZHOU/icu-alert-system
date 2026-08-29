"""病种定义模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class DiseaseStatus(StrEnum):
    """病种状态。"""
    DRAFT = "draft"
    VALIDATING = "validating"
    REVIEW_PENDING = "review_pending"
    REVIEWING = "reviewing"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class DiseaseDefinition(BaseModel):
    """病种定义。"""
    id: str = ""
    code: str = ""
    name: str
    english_name: str = ""
    short_name: str = ""
    category_id: str = ""
    parent_id: str = ""
    description: str = ""
    definition: str = ""
    diagnostic_criteria: str = ""
    differential_diagnoses: list[str] = Field(default_factory=list)
    stages: list[dict] = Field(default_factory=list)
    complications: list[str] = Field(default_factory=list)
    recommended_tests: list[str] = Field(default_factory=list)
    treatment_principles: str = ""
    contraindications: str = ""
    followup_requirements: str = ""
    icd10_codes: list[str] = Field(default_factory=list)
    icd11_codes: list[str] = Field(default_factory=list)
    local_codes: list[str] = Field(default_factory=list)
    synonym_ids: list[str] = Field(default_factory=list)
    related_score_ids: list[str] = Field(default_factory=list)
    related_phenotype_rule_ids: list[str] = Field(default_factory=list)
    related_guideline_ids: list[str] = Field(default_factory=list)
    clinical_pathway_id: str = ""
    status: DiseaseStatus = DiseaseStatus.DRAFT
    version: str = "v1.0.0"
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    owner_id: str = ""
    created_by: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: str = ""
    published_by: str = ""
    published_at: Optional[datetime] = None
    revision: int = 1
    content_hash: str = ""
