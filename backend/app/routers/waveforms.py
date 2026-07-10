from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Query

from app import runtime
from app.services.waveform_service import WaveformService
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/waveforms", tags=["waveforms"])


def _service() -> WaveformService:
    return WaveformService(db=runtime.db, config=runtime.config, alert_engine=runtime.alert_engine)


@router.get("/patients/{patient_id}/channels")
async def waveform_channels(patient_id: str, hours: int = Query(24, ge=1, le=168)):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        pid = patient_id
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    rows = await _service().list_channels(str(pid), hours=hours)
    return {"code": 0, "rows": serialize_doc(rows)}


@router.get("/patients/{patient_id}/segments")
async def waveform_segments(
    patient_id: str,
    channel: str = Query(..., min_length=1),
    hours: int = Query(6, ge=1, le=72),
    limit: int = Query(2000, ge=50, le=10000),
):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        pid = patient_id
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    rows = await _service().get_series(str(pid), channel=channel, hours=hours, limit=limit)
    return {"code": 0, "channel": channel, "rows": serialize_doc(rows)}


@router.get("/patients/{patient_id}/qc")
async def waveform_quality(
    patient_id: str,
    channel: str = Query(..., min_length=1),
    hours: int = Query(6, ge=1, le=72),
):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        pid = patient_id
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    rows = await _service().get_series(str(pid), channel=channel, hours=hours, limit=4000)
    qc = _service().assess_quality(rows, channel=channel)
    return {"code": 0, "qc": serialize_doc(qc)}


@router.get("/patients/{patient_id}/events")
async def waveform_events(
    patient_id: str,
    channel: str = Query(..., min_length=1),
    hours: int = Query(6, ge=1, le=72),
):
    try:
        pid = ObjectId(patient_id)
    except Exception:
        pid = patient_id
    patient = await runtime.db.col("patient").find_one({"_id": pid}, {"_id": 1})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    rows = await _service().get_series(str(pid), channel=channel, hours=hours, limit=4000)
    events = _service().detect_events(rows, channel=channel)
    return {"code": 0, "events": serialize_doc(events)}
