from __future__ import annotations

import re
from datetime import datetime

from app import runtime


def window_to_hours(window: str, default: int = 168) -> int:
    value = str(window or "").strip().lower()
    if not value:
        return default
    fixed = {
        "6h": 6,
        "12h": 12,
        "24h": 24,
        "48h": 48,
        "72h": 72,
        "7d": 168,
        "14d": 336,
        "30d": 720,
    }
    if value in fixed:
        return fixed[value]
    match = re.match(r"^(\d+)\s*([hd])$", value)
    if not match:
        return default
    num = int(match.group(1))
    unit = match.group(2)
    if unit == "h":
        return max(1, min(num, 24 * 90))
    return max(24, min(num * 24, 24 * 180))


def bucket_dt_format(bucket: str) -> tuple[str, str]:
    value = str(bucket or "").strip().lower()
    if value == "day":
        return "day", "%Y-%m-%d"
    return "hour", "%Y-%m-%d %H:00"


def severity_projection() -> dict:
    return {
        "warning": {"$sum": {"$cond": [{"$eq": ["$severity", "warning"]}, 1, 0]}},
        "high": {"$sum": {"$cond": [{"$eq": ["$severity", "high"]}, 1, 0]}},
        "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "critical"]}, 1, 0]}},
    }


def normalize_month_param(month: str | None) -> str:
    value = str(month or "").strip()
    if re.match(r"^\d{4}-\d{2}$", value):
        return value
    return datetime.now().strftime("%Y-%m")


async def sepsis_bundle_patient_ids_by_dept_code(dept_code: str | None) -> list[str]:
    code = str(dept_code or "").strip()
    if not code:
        return []
    patient_ids: list[str] = []
    cursor = runtime.db.col("patient").find({"deptCode": code}, {"_id": 1})
    async for patient in cursor:
        patient_id = patient.get("_id")
        if patient_id is not None:
            patient_ids.append(str(patient_id))
    return patient_ids


def derive_sepsis_bundle_status(tracker: dict | None, now: datetime | None = None) -> dict:
    now_dt = now or datetime.now()
    if not tracker:
        return {
            "active": False,
            "status": "none",
            "bundle_started_at": None,
            "deadline_1h": None,
            "deadline_3h": None,
            "first_antibiotic_time": None,
            "first_antibiotic_name": None,
            "remaining_seconds_to_1h": None,
            "remaining_seconds_to_3h": None,
            "elapsed_minutes": None,
            "compliant_1h": None,
            "source_rules": [],
            "label": "未进入计时",
            "light": "gray",
        }

    started = tracker.get("bundle_started_at")
    deadline_1h = tracker.get("deadline_1h")
    deadline_3h = tracker.get("deadline_3h")
    raw_status = str(tracker.get("status") or "").strip().lower() or "pending"
    effective_status = raw_status

    if raw_status == "pending":
        if isinstance(deadline_3h, datetime) and now_dt >= deadline_3h:
            effective_status = "overdue_3h"
        elif isinstance(deadline_1h, datetime) and now_dt >= deadline_1h:
            effective_status = "overdue_1h"

    remaining_1h = int((deadline_1h - now_dt).total_seconds()) if isinstance(deadline_1h, datetime) else None
    remaining_3h = int((deadline_3h - now_dt).total_seconds()) if isinstance(deadline_3h, datetime) else None
    elapsed_minutes = round((now_dt - started).total_seconds() / 60.0, 1) if isinstance(started, datetime) else None

    light = "gray"
    label = "未进入计时"
    if effective_status == "met":
        light, label = "green", "1h已达标"
    elif effective_status == "met_late":
        light, label = "orange", "已补执行(超1h)"
    elif effective_status == "overdue_3h":
        light, label = "red", "3h仍未执行"
    elif effective_status == "overdue_1h":
        light, label = "red", "1h已超时"
    elif effective_status == "pending":
        if remaining_1h is not None and remaining_1h <= 30 * 60:
            light, label = "yellow", "1h窗口临近"
        else:
            light, label = "blue", "1h内待完成"

    return {
        "active": bool(tracker.get("is_active")) and effective_status == "pending",
        "status": effective_status,
        "raw_status": raw_status,
        "bundle_started_at": started,
        "deadline_1h": deadline_1h,
        "deadline_3h": deadline_3h,
        "first_antibiotic_time": tracker.get("first_antibiotic_time"),
        "first_antibiotic_name": tracker.get("first_antibiotic_name"),
        "remaining_seconds_to_1h": remaining_1h,
        "remaining_seconds_to_3h": remaining_3h,
        "elapsed_minutes": elapsed_minutes,
        "compliant_1h": tracker.get("compliant_1h"),
        "source_rules": tracker.get("source_rules") or [],
        "label": label,
        "light": light,
    }


def normalize_weaning_status(doc: dict | None) -> dict:
    if not doc:
        return {
            "has_assessment": False,
            "risk_score": None,
            "risk_level": "unknown",
            "recommendation": "暂无撤机评估",
            "severity": "warning",
            "factors": [],
            "gate_failures": [],
            "pf_ratio": None,
            "fio2": None,
            "peep": None,
            "rsbi": None,
            "rr": None,
            "vte_ml": None,
            "map": None,
            "rass": None,
            "gcs": None,
            "fluid_overload_pct": None,
            "ventilation_days": None,
            "updated_at": None,
        }
    return {
        "has_assessment": True,
        "risk_score": doc.get("risk_score") if doc.get("risk_score") is not None else doc.get("score"),
        "risk_level": doc.get("risk_level") or "low",
        "recommendation": doc.get("recommendation") or "-",
        "severity": doc.get("severity") or ("high" if str(doc.get("risk_level") or "").lower() in {"high", "critical"} else "warning"),
        "factors": doc.get("factors") or [],
        "gate_failures": doc.get("gate_failures") or [],
        "pf_ratio": doc.get("pf_ratio"),
        "fio2": doc.get("fio2"),
        "peep": doc.get("peep"),
        "rsbi": doc.get("rsbi"),
        "rr": doc.get("rr"),
        "vte_ml": doc.get("vte_ml"),
        "map": doc.get("map"),
        "rass": doc.get("rass"),
        "gcs": doc.get("gcs"),
        "fluid_overload_pct": doc.get("fluid_overload_pct"),
        "ventilation_days": doc.get("ventilation_days"),
        "updated_at": doc.get("calc_time") or doc.get("updated_at") or doc.get("created_at"),
    }


def normalize_sbt_status(doc: dict | None) -> dict:
    if not doc:
        return {
            "has_record": False,
            "result": "none",
            "passed": None,
            "label": "暂无SBT记录",
            "trial_time": None,
            "source": None,
            "duration_minutes": None,
            "rr": None,
            "vte_ml": None,
            "rsbi": None,
            "fio2": None,
            "peep": None,
            "raw_text": None,
        }
    result = str(doc.get("result") or "").lower() or "documented"
    label_map = {
        "passed": "SBT通过",
        "failed": "SBT失败",
        "documented": "已记录SBT",
    }
    return {
        "has_record": True,
        "result": result,
        "passed": doc.get("passed"),
        "label": label_map.get(result, "已记录SBT"),
        "trial_time": doc.get("trial_time") or doc.get("calc_time"),
        "source": doc.get("source"),
        "duration_minutes": doc.get("duration_minutes"),
        "rr": doc.get("rr"),
        "vte_ml": doc.get("vte_ml"),
        "rsbi": doc.get("rsbi"),
        "fio2": doc.get("fio2"),
        "peep": doc.get("peep"),
        "raw_text": doc.get("raw_text"),
    }
