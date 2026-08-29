"""AI 提案模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class AiProposalStatus(StrEnum):
    """AI 提案状态。"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"


class AiProposal(BaseModel):
    """AI 提案。"""
    id: str = ""
    task_type: str = ""  # extract_definition, recommend_stages, check_missing, etc.
    resource_type: str = ""  # disease, terminology, phenotype_rule, etc.
    resource_id: str = ""
    input_snapshot: dict = Field(default_factory=dict)
    output_proposal: dict = Field(default_factory=dict)
    citations: list[dict] = Field(default_factory=list)
    model: str = ""
    model_version: str = ""
    prompt_version: str = ""
    knowledge_version: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    uncertainty_level: str = ""  # low, medium, high
    uncertainties: list[str] = Field(default_factory=list)
    status: AiProposalStatus = AiProposalStatus.PENDING
    accepted_fields: list[str] = Field(default_factory=list)
    rejected_fields: list[str] = Field(default_factory=list)
    modified_fields: list[dict] = Field(default_factory=list)
    reviewer_id: str = ""
    reviewed_at: Optional[datetime] = None
