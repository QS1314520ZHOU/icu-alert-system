"""
Schemas for ICU rounding workbench clinical documents.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class VitalStat(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    trend: str = "未提供"


class VitalEvent(BaseModel):
    time_hm: str
    type: str
    value: str


class Vitals(BaseModel):
    hr: VitalStat
    map: VitalStat
    spo2: VitalStat
    temp: VitalStat
    rr: VitalStat
    events: list[VitalEvent] = Field(default_factory=list)


class LabDelta(BaseModel):
    id: int
    name: str
    prev: float
    curr: float
    unit: str = ""
    flag: str = ""


class DrugEvent(BaseModel):
    id: int
    time_hm: str
    action: str
    name: str
    dose_after: Optional[str] = None


class VentChange(BaseModel):
    id: int
    time_hm: str
    detail: str


class Ventilator(BaseModel):
    mode: str
    fio2: float
    peep: float
    vt: int
    pplat: float
    pf_ratio: Optional[float] = None
    changes: list[VentChange] = Field(default_factory=list)


class NeuroAssessment(BaseModel):
    rass: Optional[float] = None
    cam_icu: Optional[str] = None
    observed_at: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)


class AlertItem(BaseModel):
    id: int
    type: str
    severity: str
    count: int
    active: bool


class Scores(BaseModel):
    gcs: int
    sofa: int
    apache: int


class FluidBalance(BaseModel):
    intake_24h_ml: Optional[float] = None
    output_24h_ml: Optional[float] = None
    urine_24h_ml: Optional[float] = None
    net_24h_ml: Optional[float] = None
    evidence_refs: list[str] = Field(default_factory=list)


class TubeDevice(BaseModel):
    name: str
    category: str
    site: str = ""
    dwell_days: Optional[int] = None
    start_time: Optional[str] = None
    latest_record_time: Optional[str] = None
    latest_status: str = ""


class LineDevices(BaseModel):
    active_tubes: list[TubeDevice] = Field(default_factory=list)
    drainage_24h_ml: Optional[float] = None
    drainage_codes: list[str] = Field(default_factory=list)


class InfectionLabItem(BaseModel):
    name: str
    value: str
    unit: str = ""
    observed_at: Optional[str] = None
    flag: str = ""


class InfectionEvidence(BaseModel):
    inflammatory_markers: list[InfectionLabItem] = Field(default_factory=list)
    culture_results: list[InfectionLabItem] = Field(default_factory=list)


class Basics(BaseModel):
    name: str
    bed: str
    age: int
    sex: str
    day: int
    diagnosis: str


class ProgressNoteContext(BaseModel):
    patient_id: str
    window_start: str
    window_end: str
    basics: Basics
    v: Vitals
    labs: list[LabDelta] = Field(default_factory=list)
    drugs: list[DrugEvent] = Field(default_factory=list)
    vent: Optional[Ventilator] = None
    neuro: Optional[NeuroAssessment] = None
    alerts: list[AlertItem] = Field(default_factory=list)
    scores: Optional[Scores] = None
    fluid_balance: Optional[FluidBalance] = None
    line_devices: Optional[LineDevices] = None
    infection_evidence: Optional[InfectionEvidence] = None


StatementKind = Literal["fact", "inference", "recommendation"]
Priority = Literal["critical", "high", "medium", "low"]
ReviewStatus = Literal["unreviewed", "reviewed", "edited"]


class ClinicalStatement(BaseModel):
    id: str
    kind: StatementKind
    text: str
    confidence: Optional[Literal["low", "medium", "high"]] = None
    evidence_refs: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    review_required: bool = False


class PatientBanner(BaseModel):
    bed_no: str
    age: str
    sex: str
    icu_day: str
    primary_diagnosis: str
    current_diagnosis: Optional[str] = None
    allergy_status: str = "未提供"
    isolation_status: str = "未提供"
    code_status: str = "未提供"


class OrganSupportItem(BaseModel):
    key: Literal["vent", "pressor", "crrt", "sedation", "lines", "infection"]
    label: str
    status: Literal["active", "inactive", "unknown"] = "unknown"
    summary: str
    missing_data: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    id: str
    occurred_at: str
    category: Literal["vital", "lab", "medication", "procedure", "vent", "alert", "note"]
    title: str
    description: str
    severity: Optional[Priority] = None
    evidence_refs: list[str] = Field(default_factory=list)


class SystemAPCard(BaseModel):
    id: str
    system: Literal[
        "neuro",
        "resp",
        "cv",
        "renal_fluid",
        "gi_nutrition",
        "id",
        "heme",
        "endo",
        "lines_devices",
        "goals",
    ]
    title: str
    priority: Priority = "medium"
    status: list[ClinicalStatement] = Field(default_factory=list)
    trend: list[ClinicalStatement] = Field(default_factory=list)
    assessment: list[ClinicalStatement] = Field(default_factory=list)
    plan_items: list[ClinicalStatement] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = "unreviewed"


class DailyGoal(BaseModel):
    id: str
    category: Literal[
        "map",
        "oxygenation",
        "rass",
        "fluid_balance",
        "antibiotics",
        "nutrition",
        "lines",
        "rehab",
        "family_communication",
        "night_plan",
    ]
    label: str
    target: str
    status: Literal["open", "done", "not_applicable"] = "open"
    evidence_refs: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class RiskTaskAction(BaseModel):
    label: str
    action_type: Literal["add_to_plan", "create_order_draft_placeholder", "snooze", "dismiss"]


class RiskTask(BaseModel):
    id: str
    priority: Priority
    category: str
    title: str
    why_triggered: list[ClinicalStatement] = Field(default_factory=list)
    confirm_items: list[str] = Field(default_factory=list)
    suggested_actions: list[RiskTaskAction] = Field(default_factory=list)
    status: Literal["open", "done", "dismissed", "snoozed"] = "open"


class NotePreview(BaseModel):
    style: Literal["APSO", "SOAP", "DAILY_PROGRESS"] = "APSO"
    generated_text: str
    final_text_override: Optional[str] = None
    is_overridden: bool = False
    generated_from_hash: str


class StaleDataItem(BaseModel):
    name: str
    last_observed_at: str
    age_hours: float


class QualityChecks(BaseModel):
    critical_missing_data: list[str] = Field(default_factory=list)
    stale_data: list[StaleDataItem] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContextWindow(BaseModel):
    start: str
    end: str


class RoundingWorkbenchDraft(BaseModel):
    schema_version: Literal["icu_rounding_workbench.v1"] = "icu_rounding_workbench.v1"
    content_type: Literal["rounding_workbench"] = "rounding_workbench"
    generated_at: str
    context_window: ContextWindow
    patient_banner: PatientBanner
    organ_support: list[OrganSupportItem] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    system_ap: list[SystemAPCard] = Field(default_factory=list)
    daily_goals: list[DailyGoal] = Field(default_factory=list)
    risk_tasks: list[RiskTask] = Field(default_factory=list)
    note_preview: NotePreview
    quality_checks: QualityChecks = Field(default_factory=QualityChecks)
    raw_ai_tags: list[str] = Field(default_factory=list)


# Backward-compatible alias for existing imports/tests while the module name
# still says "progress note".
DraftOutput = RoundingWorkbenchDraft
