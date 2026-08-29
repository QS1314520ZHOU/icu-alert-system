"""离线包模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class PackageStatus(StrEnum):
    """离线包状态。"""
    DRAFT = "draft"
    VALIDATING = "validating"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ROLLBACK = "rollback"


class OfflinePackage(BaseModel):
    """离线包。"""
    id: str = ""
    name: str
    package_type: str = ""  # icd, terminology, guidelines, model, embedding, vector
    version: str = "v1.0.0"
    manifest_version: str = ""
    file_path: str = ""
    file_size: int = 0
    sha256: str = ""
    signature: str = ""
    signature_algorithm: str = ""
    signer: str = ""
    source: str = ""
    source_version: str = ""
    status: PackageStatus = PackageStatus.DRAFT
    validation_result: dict = Field(default_factory=dict)
    diff_summary: str = ""
    impact_summary: str = ""
    uploaded_by: str = ""
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: str = ""
    published_by: str = ""
    published_at: Optional[datetime] = None
    previous_package_id: str = ""
    rollback_from: str = ""
    rollback_to: str = ""
