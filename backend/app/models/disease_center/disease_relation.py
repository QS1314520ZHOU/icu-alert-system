"""病种关系模型。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RelationType(StrEnum):
    """关系类型。"""
    HAS_SYMPTOM = "has_symptom"
    HAS_SIGN = "has_sign"
    HAS_LAB_FINDING = "has_lab_finding"
    HAS_IMAGING_FINDING = "has_imaging_finding"
    HAS_STAGE = "has_stage"
    HAS_COMPLICATION = "has_complication"
    DIFFERENTIAL_FROM = "differential_from"
    TREATED_BY = "treated_by"
    CONTRAINDICATED_WITH = "contraindicated_with"
    ASSESSED_BY = "assessed_by"
    DETECTED_BY = "detected_by"
    SUPPORTED_BY = "supported_by"
    RELATED_TO = "related_to"


class DiseaseRelation(BaseModel):
    """病种关系。"""
    id: str = ""
    source_type: str = ""
    source_id: str = ""
    relation_type: RelationType
    target_type: str = ""
    target_id: str = ""
    direction: str = "forward"  # forward, backward, bidirectional
    description: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    version: str = "v1.0.0"
    status: str = "active"
