"""审核任务模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class ReviewStatus(StrEnum):
    """审核状态。"""
    PENDING = "pending"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ReviewTask(BaseModel):
    """审核任务。"""
    id: str = ""
    resource_type: str = ""  # disease, terminology, phenotype_rule, etc.
    resource_id: str = ""
    resource_version: str = ""
    status: ReviewStatus = ReviewStatus.PENDING
    submitter_id: str = ""
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    reviewer_id: str = ""
    reviewed_at: Optional[datetime] = None
    review_comment: str = ""
    change_request: str = ""
    approval_level: int = 1
    snapshot_before: dict = Field(default_factory=dict)
    snapshot_after: dict = Field(default_factory=dict)
    diff: str = ""
    impact_analysis: dict = Field(default_factory=dict)
    test_summary: dict = Field(default_factory=dict)
    ai_check_summary: dict = Field(default_factory=dict)
    signature: str = ""
    revision: int = 1
