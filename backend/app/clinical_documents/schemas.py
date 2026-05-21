"""
Clinical Documents — Pydantic schemas for progress note context & output.
"""
from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Literal


class VitalStat(BaseModel):
    min: float
    max: float
    trend: Literal["上升", "下降", "平稳", "波动"]


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
    events: list[VitalEvent] = []


class LabDelta(BaseModel):
    id: int
    name: str
    prev: float
    curr: float
    unit: str
    flag: str  # ↑↑/↑/→/↓/↓↓


class DrugEvent(BaseModel):
    id: int
    time_hm: str
    action: Literal["新增", "停用", "升级量", "降级量"]
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
    pf_ratio: float
    changes: list[VentChange] = []


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
    labs: list[LabDelta]
    drugs: list[DrugEvent]
    vent: Optional[Ventilator] = None
    alerts: list[AlertItem] = []
    scores: Optional[Scores] = None


class DraftOutput(BaseModel):
    subjective: str
    objective: dict
    assessment: dict
    plan: list[str]
    overall_trend: Literal["好转", "平稳", "恶化"]
    key_concerns: list[str]
