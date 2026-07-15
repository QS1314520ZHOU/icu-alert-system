"""Handover schemas — Pydantic models for ISBAR structured handover documents."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────

class HandoverStatus(str, Enum):
    NOT_CREATED = "not_created"
    DRAFT = "draft"
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"


class ContentSource(str, Enum):
    AI_GENERATED = "ai_generated"
    HUMAN_CONFIRMED = "human_confirmed"
    HUMAN_MODIFIED = "human_modified"
    SYSTEM_POPULATED = "system_populated"


# ── ISBAR Section Models ─────────────────────────────────────────────

class IdentifySection(BaseModel):
    bed: str = ""
    name: str = ""
    sex: str = ""
    age: str = ""
    admission_no: str = ""
    medical_group: str = ""
    special_tags: list[str] = Field(default_factory=list)


class SituationSection(BaseModel):
    diagnosis: str = ""
    surgery: str = ""
    post_op_day: str = ""
    icu_day: str = ""
    main_problems: str = ""
    life_support_level: str = ""
    life_support_changes: str = ""


class BackgroundSection(BaseModel):
    admission_course: str = ""
    past_history: str = ""
    isolation: str = ""
    allergies: str = ""


class NeuroAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class RespAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class CircAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class TempAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class GiAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class HemeAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class SpecialtyAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class NursingAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class LinesAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class SkinAssessment(BaseModel):
    content: str = ""
    changes: str = ""


class ItemsHandover(BaseModel):
    content: str = ""


class AssessmentSection(BaseModel):
    neuro: NeuroAssessment = Field(default_factory=NeuroAssessment)
    resp: RespAssessment = Field(default_factory=RespAssessment)
    circ: CircAssessment = Field(default_factory=CircAssessment)
    temp: TempAssessment = Field(default_factory=TempAssessment)
    gi: GiAssessment = Field(default_factory=GiAssessment)
    heme: HemeAssessment = Field(default_factory=HemeAssessment)
    specialty: SpecialtyAssessment = Field(default_factory=SpecialtyAssessment)
    nursing: NursingAssessment = Field(default_factory=NursingAssessment)
    lines: LinesAssessment = Field(default_factory=LinesAssessment)
    skin: SkinAssessment = Field(default_factory=SkinAssessment)
    items: ItemsHandover = Field(default_factory=ItemsHandover)


class RecommendationSection(BaseModel):
    critical_first: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    escalation: list[str] = Field(default_factory=list)


class ISbarSections(BaseModel):
    identify: IdentifySection = Field(default_factory=IdentifySection)
    situation: SituationSection = Field(default_factory=SituationSection)
    background: BackgroundSection = Field(default_factory=BackgroundSection)
    assessment: AssessmentSection = Field(default_factory=AssessmentSection)
    recommendation: RecommendationSection = Field(default_factory=RecommendationSection)


# ── Evidence & Metadata ───────────────────────────────────────────────

class EvidenceItem(BaseModel):
    field: str = ""
    source: str = ""
    value: str = ""
    time: str = ""


class VersionSnapshot(BaseModel):
    version: int = 1
    sections: ISbarSections = Field(default_factory=ISbarSections)
    data_snapshot: dict[str, Any] = Field(default_factory=dict)
    ai_first_draft: Optional[dict[str, Any]] = None
    created_by: str = ""
    created_at: str = ""
    change_note: str = ""


class ForcedConfirmation(BaseModel):
    item_id: str = ""
    item_type: str = ""  # critical_value / high_risk_line / vasoactive / isolation / unclosed_alert / escalation
    description: str = ""
    confirmed: bool = False
    confirmed_by: str = ""
    confirmed_at: str = ""


# ── Main Document ─────────────────────────────────────────────────────

class HandoverDocument(BaseModel):
    handover_id: str = ""
    patient_id: str = ""
    handover_type: str = "nurse_bedside"
    shift: dict[str, Any] = Field(default_factory=dict)
    time_window: dict[str, str] = Field(default_factory=dict)
    data_snapshot_at: str = ""
    sections: ISbarSections = Field(default_factory=ISbarSections)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    ai_generated_fields: list[str] = Field(default_factory=list)
    content_sources: dict[str, str] = Field(default_factory=dict)
    status: HandoverStatus = HandoverStatus.NOT_CREATED
    versions: list[VersionSnapshot] = Field(default_factory=list)
    submitted_by: str = ""
    submitted_at: str = ""
    acknowledged_by: str = ""
    acknowledged_at: str = ""
    forced_confirmations: list[ForcedConfirmation] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


# ── Request / Response Models ─────────────────────────────────────────

class GenerateRequest(BaseModel):
    patient_id: str
    handover_type: str = "nurse_bedside"
    shift_code: Optional[str] = None


class UpdateContentRequest(BaseModel):
    sections: dict[str, Any]
    edited_fields: list[str] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    operator: str


class AcknowledgeRequest(BaseModel):
    operator: str
    forced_confirmations: list[dict[str, Any]] = Field(default_factory=list)


class RejectRequest(BaseModel):
    operator: str
    reason: str = ""


# ── Context Model (input to LLM) ──────────────────────────────────────

class HandoverContext(BaseModel):
    patient: dict[str, Any] = Field(default_factory=dict)
    time_window: dict[str, str] = Field(default_factory=dict)
    shift: dict[str, Any] = Field(default_factory=dict)
    data_snapshot_at: str = ""
    situation: dict[str, Any] = Field(default_factory=dict)
    background: dict[str, Any] = Field(default_factory=dict)
    vitals: list[dict[str, Any]] = Field(default_factory=list)
    labs: list[dict[str, Any]] = Field(default_factory=list)
    io: dict[str, Any] = Field(default_factory=dict)
    pumps: list[dict[str, Any]] = Field(default_factory=list)
    airway_vent: dict[str, Any] = Field(default_factory=dict)
    lines: list[dict[str, Any]] = Field(default_factory=list)
    assessments: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    pending_orders: list[dict[str, Any]] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
