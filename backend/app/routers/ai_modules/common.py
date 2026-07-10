from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from typing import Any

from app import runtime
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).strip())
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _parse_when(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue
    return None


def _iso(value: object) -> str | None:
    if isinstance(value, datetime):
        return serialize_doc(value)
    if value is None:
        return None
    return str(value)


def _serialize_nullable(value):
    if value is None:
        return None
    if isinstance(value, list):
        return [_serialize_nullable(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_nullable(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_nullable(item) for key, item in value.items()}
    return serialize_doc(value)


def _hours_from_window(window: str) -> int:
    return 72 if str(window or "").strip().lower() == "72h" else 24


def _round_number(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _bucket_time(value: datetime, *, bucket_hours: int) -> datetime:
    hour = (value.hour // max(bucket_hours, 1)) * max(bucket_hours, 1)
    return value.replace(minute=0, second=0, microsecond=0, hour=hour)


def _merge_time_series(
    series_map: dict[str, list[dict]],
    *,
    bucket_hours: int = 2,
    max_points: int = 18,
) -> list[dict]:
    buckets: dict[datetime, dict] = {}
    for field, rows in series_map.items():
        for row in rows:
            point_time = _parse_when(row.get("time"))
            value = _safe_float(row.get("value"))
            if point_time is None or value is None:
                continue
            bucket = _bucket_time(point_time, bucket_hours=bucket_hours)
            current = buckets.setdefault(bucket, {"time": bucket})
            current[field] = value
    merged = [buckets[key] for key in sorted(buckets)]
    if len(merged) > max_points:
        step = max(1, math.ceil(len(merged) / max_points))
        merged = merged[::step][-max_points:]
    for row in merged:
        row["time"] = _iso(row.get("time"))
    return merged


async def _device_cap_series(device_id: str | None, code: str, since: datetime) -> list[dict]:
    if not device_id or not code:
        return []
    cursor = runtime.db.col("deviceCap").find(
        {"deviceID": device_id, "code": code, "time": {"$gte": since}},
        {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
    ).sort("time", 1).limit(4000)
    rows: list[dict] = []
    async for doc in cursor:
        point_time = _parse_when(doc.get("time"))
        value = doc.get("fVal")
        if value is None:
            value = doc.get("intVal")
        if value is None:
            value = doc.get("strVal")
        if point_time is None or value in (None, ""):
            continue
        rows.append({"time": point_time, "value": value})
    return rows


async def _lab_series_by_keywords(patient_ids: list[str], keywords: list[str], since: datetime, *, limit: int = 4000) -> list[dict]:
    if not patient_ids or not keywords:
        return []
    his_pid_query = {"hisPid": patient_ids[0]} if len(patient_ids) == 1 else {"hisPid": {"$in": patient_ids}}
    cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(his_pid_query).sort("authTime", -1).limit(limit)
    rows: list[dict] = []
    keyword_list = [str(item).lower() for item in keywords if str(item).strip()]
    async for doc in cursor:
        name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
        if not name:
            continue
        if keyword_list and not any(keyword in name.lower() for keyword in keyword_list):
            continue
        point_time = (
            _parse_when(doc.get("authTime"))
            or _parse_when(doc.get("collectTime"))
            or _parse_when(doc.get("reportTime"))
            or _parse_when(doc.get("time"))
        )
        if point_time is None or point_time < since:
            continue
        value = _safe_float(doc.get("result") or doc.get("resultValue") or doc.get("value"))
        if value is None:
            continue
        rows.append({"time": point_time, "value": value, "unit": str(doc.get("unit") or doc.get("resultUnit") or "").strip(), "name": name})
    rows.sort(key=lambda item: item["time"])
    return rows


def _latest_metric(rows: list[dict], *, digits: int = 1) -> dict | None:
    if not rows:
        return None
    latest = rows[-1]
    return {
        "time": _iso(latest.get("time")),
        "value": _round_number(_safe_float(latest.get("value")), digits),
        "unit": latest.get("unit"),
        "name": latest.get("name"),
    }


def _build_metric_cards(trend_points: list[dict], specs: list[tuple[str, str, str]]) -> list[dict]:
    cards: list[dict] = []
    for key, label, unit in specs:
        latest_value = None
        for row in reversed(trend_points):
            value = _safe_float(row.get(key))
            if value is not None:
                latest_value = value
                break
        cards.append({"key": key, "label": label, "value": _round_number(latest_value, 1), "unit": unit})
    return cards


async def _persist_ai_score_record(patient: dict, payload: dict[str, Any], *, score_type: str) -> dict[str, Any]:
    now = datetime.now()
    record = {
        "patient_id": str(patient.get("_id") or ""),
        "patient_name": patient.get("name") or patient.get("hisName") or "",
        "bed": patient.get("hisBed") or patient.get("bed") or "",
        "dept": patient.get("dept") or patient.get("hisDept") or "",
        "score_type": score_type,
        "calc_time": now,
        "updated_at": now,
        "month": now.strftime("%Y-%m"),
        "day": now.strftime("%Y-%m-%d"),
        **payload,
    }
    insert_res = await runtime.db.col("score").insert_one(record)
    record["_id"] = insert_res.inserted_id
    return record


def _safe_text_list(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows
