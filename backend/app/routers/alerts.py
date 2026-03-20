from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.utils.alerting import window_to_hours
from app.utils.serialization import serialize_doc

router = APIRouter()


def resolve_actor_identity(payload: dict | None, request: Request) -> str:
    body = payload if isinstance(payload, dict) else {}
    candidates = [
        body.get("actor"),
        request.headers.get("x-user-id"),
        request.headers.get("x-actor-id"),
        request.headers.get("x-operator-id"),
        request.headers.get("x-forwarded-user"),
        request.headers.get("x-user-name"),
        request.headers.get("remote-user"),
    ]
    for item in candidates:
        value = runtime.alert_engine._normalize_lifecycle_actor(str(item or "").strip())
        if value:
            return value
    return ""


@router.get("/api/alerts/recent")
async def recent_alerts(
    limit: int = Query(50, ge=1, le=200),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
    role: Optional[str] = Query(None, description="角色过滤: nurse/doctor/pharmacist"),
):
    col = runtime.db.col("alert_records")
    query: dict = {"is_active": True}
    if dept:
        query["dept"] = dept
    elif dept_code:
        patient_ids = []
        cursor_p = runtime.db.col("patient").find({"deptCode": dept_code}, {"_id": 1})
        async for patient in cursor_p:
            patient_ids.append(str(patient.get("_id")))
        if patient_ids:
            query = {
                "is_active": True,
                "$or": [
                    {"deptCode": dept_code},
                    {"patient_id": {"$in": patient_ids}},
                ],
            }
        else:
            query["deptCode"] = dept_code
    if role:
        query.setdefault("$and", []).append(
            {
                "$or": [
                    {"route_targets": str(role).lower()},
                    {"extra.route_targets": str(role).lower()},
                ]
            }
        )

    cursor = col.find(query).sort([("actionability_score", -1), ("created_at", -1)]).limit(limit)
    records = [serialize_doc(doc) async for doc in cursor]
    return {"code": 0, "records": records}


@router.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request, payload: dict = Body(default={})):
    doc = await runtime.alert_engine.acknowledge_alert(
        alert_id,
        actor=resolve_actor_identity(payload, request),
        note=str((payload or {}).get("note") or "").strip(),
    )
    if not doc:
        return {"code": 404, "message": "告警不存在"}
    return {"code": 0, "record": serialize_doc(doc)}


@router.get("/api/alerts/lifecycle/analytics")
async def alert_lifecycle_analytics(
    window: str = Query("24h"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    hours = window_to_hours(window, default=24)
    analytics = await runtime.alert_engine.alert_lifecycle_analytics(hours=hours, dept=dept, dept_code=dept_code)
    return {"code": 0, **serialize_doc(analytics)}


@router.get("/api/alerts/stats")
async def alert_stats(window: str = Query("24h")):
    hours = window_to_hours(window, default=24)
    since = datetime.utcnow() - timedelta(hours=hours)

    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "hour": {"$dateToString": {"format": "%Y-%m-%d %H:00", "date": "$created_at"}},
                    "severity": "$severity",
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.hour": 1}},
    ]

    results = {}
    cursor = await runtime.db.col("alert_records").aggregate(pipeline)
    async for doc in cursor:
        hour = doc["_id"]["hour"]
        severity = doc["_id"]["severity"]
        if hour not in results:
            results[hour] = {"time": hour, "warning": 0, "high": 0, "critical": 0}
        if severity in results[hour]:
            results[hour][severity] = doc["count"]

    return {"code": 0, "series": sorted(results.values(), key=lambda item: item["time"])}
