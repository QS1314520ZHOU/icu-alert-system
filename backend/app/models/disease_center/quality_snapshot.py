"""质量快照模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QualitySnapshot(BaseModel):
    """质量快照。"""
    id: str = ""
    resource_type: str = ""  # disease, terminology, phenotype_rule, etc.
    resource_id: str = ""
    resource_version: str = ""
    completeness: float = 0.0  # 0.0 - 1.0
    terminology_consistency: float = 0.0
    coding_quality: float = 0.0
    source_coverage: float = 0.0
    test_pass_rate: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    specificity: float = 0.0
    sensitivity: float = 0.0
    validation_sample_size: int = 0
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    calculation_version: str = ""
