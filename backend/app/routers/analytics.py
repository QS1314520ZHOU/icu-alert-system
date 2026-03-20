from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Query

from app import runtime
from app.utils.alerting import (
    bucket_dt_format,
    derive_sepsis_bundle_status,
    normalize_month_param,
    sepsis_bundle_patient_ids_by_dept_code,
    severity_projection,
    window_to_hours,
)
from app.utils.analytics_ai import summarize_sepsis_bundle_analytics
from app.utils.patient_helpers import active_patient_query
from app.utils.serialization import serialize_doc

router = APIRouter()


def _month_bounds(month_norm: str) -> tuple[datetime, datetime]:
    month_start = datetime.strptime(f"{month_norm}-01", "%Y-%m-%d")
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return month_start, next_month


def _bundle_tracker_sort_time(doc: dict) -> datetime:
    for key in ("updated_at", "calc_time", "resolved_at", "created_at", "bundle_started_at"):
        value = doc.get(key)
        if isinstance(value, datetime):
            return value
    return datetime.min


def _bundle_episode_key(doc: dict) -> str:
    patient_id = str(doc.get("patient_id") or "").strip()
    started = doc.get("bundle_started_at")
    if isinstance(started, datetime):
        return f"{patient_id}|{started.isoformat()}"
    return str(doc.get("_id") or f"{patient_id}|unknown")


@router.get("/api/bundle/overview")
async def bundle_overview(
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    query: dict = active_patient_query()
    if dept:
        query = {"$and": [query, {"$or": [{"hisDept": dept}, {"dept": dept}]}]}
    elif dept_code:
        query = {"$and": [query, {"deptCode": dept_code}]}

    counts = {"green": 0, "yellow": 0, "red": 0}
    patient_count = 0
    cursor = runtime.db.col("patient").find(query)
    async for patient in cursor:
        patient_count += 1
        status = await runtime.alert_engine.get_liberation_bundle_status(patient)
        for state in (status.get("lights") or {}).values():
            if state in counts:
                counts[state] += 1
    return {"code": 0, "patient_count": patient_count, "counts": counts}


@router.get("/api/device-risk/heatmap")
async def device_risk_heatmap(
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    query: dict = active_patient_query()
    if dept:
        query = {"$and": [query, {"$or": [{"hisDept": dept}, {"dept": dept}]}]}
    elif dept_code:
        query = {"$and": [query, {"deptCode": dept_code}]}

    rows = []
    cursor = runtime.db.col("patient").find(
        query,
        {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "hisPid": 1, "clinicalDiagnosis": 1},
    )
    async for patient in cursor:
        summary = await runtime.alert_engine._device_management_summary(patient)
        for device in summary.get("devices", []):
            rows.append(
                {
                    "patient_id": str(patient["_id"]),
                    "bed": patient.get("hisBed") or "--",
                    "patient_name": patient.get("name") or "",
                    "device_type": device.get("type"),
                    "line_days": device.get("line_days"),
                    "risk": device.get("risk"),
                    "risk_score": {"low": 1, "medium": 2, "high": 3}.get(device.get("risk"), 0),
                }
            )
    return {"code": 0, "rows": rows}


@router.get("/api/analytics/nursing-workload")
async def analytics_nursing_workload(
    window: Optional[str] = Query("24h", description="时间窗口 24h/7d/14d/30d"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    hours = window_to_hours(window, default=24)
    analytics = await runtime.alert_engine.get_nursing_workload_analytics(
        dept=dept,
        dept_code=dept_code,
        hours=max(8, min(hours, 24 * 30)),
    )
    return {"code": 0, **serialize_doc(analytics)}


@router.get("/api/analytics/scenario-coverage")
async def analytics_scenario_coverage(
    window: Optional[str] = Query("7d", description="时间窗口 24h/7d/14d/30d"),
    top_n: int = Query(12, ge=5, le=40, description="热力图展示 TopN 场景"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    yaml_cfg = runtime.config.yaml_cfg if getattr(runtime, "config", None) is not None else {}
    scenario_cfg = yaml_cfg.get("extended_scenarios", {}) if isinstance(yaml_cfg, dict) else {}
    catalog_rows: list[dict] = []
    scenario_title = getattr(runtime.alert_engine, "_scenario_title", None)
    for group, scenarios in (scenario_cfg.items() if isinstance(scenario_cfg, dict) else []):
        if not isinstance(scenarios, list):
            continue
        for scenario in scenarios:
            name = str(scenario or "").strip()
            if not name:
                continue
            title = scenario_title(name) if callable(scenario_title) else name.replace("_", " ").title()
            catalog_rows.append({"group": str(group or "other"), "scenario": name, "title": title})

    since = datetime.now() - timedelta(hours=window_to_hours(window))
    query: dict = {"category": "extended_scenarios", "created_at": {"$gte": since}}
    if dept:
        query["dept"] = dept
    elif dept_code:
        query["deptCode"] = dept_code

    docs = [doc async for doc in runtime.db.col("alert_records").find(query, {"alert_type": 1, "name": 1, "severity": 1, "patient_id": 1, "dept": 1, "deptCode": 1, "created_at": 1, "extra": 1})]
    alert_count_by_scenario: dict[str, int] = {}
    patient_count_by_scenario: dict[str, set[str]] = {}
    severity_count_by_scenario: dict[str, dict[str, int]] = {}
    catalog_map = {row["scenario"]: row for row in catalog_rows}

    for doc in docs:
        scenario = str(doc.get("alert_type") or doc.get("extra", {}).get("scenario") or "").strip()
        if not scenario:
            continue
        alert_count_by_scenario[scenario] = int(alert_count_by_scenario.get(scenario) or 0) + 1
        patient_id = str(doc.get("patient_id") or "").strip()
        if patient_id:
            patient_count_by_scenario.setdefault(scenario, set()).add(patient_id)
        sev = str(doc.get("severity") or "warning").strip().lower() or "warning"
        severity_count_by_scenario.setdefault(scenario, {})
        severity_count_by_scenario[scenario][sev] = int(severity_count_by_scenario[scenario].get(sev) or 0) + 1

    group_summary: dict[str, dict] = {}
    for row in catalog_rows:
        group = row["group"]
        entry = group_summary.setdefault(
            group,
            {
                "group": group,
                "catalog_count": 0,
                "triggered_count": 0,
                "alert_count": 0,
                "active_titles": [],
            },
        )
        entry["catalog_count"] += 1
        scenario = row["scenario"]
        if scenario in alert_count_by_scenario:
            entry["triggered_count"] += 1
            entry["alert_count"] += int(alert_count_by_scenario.get(scenario) or 0)
            entry["active_titles"].append(row["title"])

    group_rows = []
    for entry in group_summary.values():
        catalog_count = int(entry.get("catalog_count") or 0)
        triggered_count = int(entry.get("triggered_count") or 0)
        group_rows.append(
            {
                **entry,
                "coverage_ratio": round((triggered_count / catalog_count), 4) if catalog_count else 0,
                "active_titles": entry.get("active_titles", [])[:6],
            }
        )
    group_rows.sort(key=lambda item: (-int(item.get("triggered_count") or 0), item.get("group") or ""))

    top_scenarios = sorted(alert_count_by_scenario.items(), key=lambda item: item[1], reverse=True)[:top_n]
    x_labels = []
    scenario_index: dict[str, int] = {}
    for idx, (scenario, _) in enumerate(top_scenarios):
        row = catalog_map.get(scenario) or {"title": scenario.replace("_", " ").title(), "group": "other"}
        x_labels.append(row["title"])
        scenario_index[scenario] = idx

    y_labels = [row["group"] for row in group_rows]
    group_index = {label: idx for idx, label in enumerate(y_labels)}
    heatmap_data: list[list[int]] = []
    for scenario, count in top_scenarios:
        row = catalog_map.get(scenario)
        if not row:
            continue
        xi = scenario_index.get(scenario)
        yi = group_index.get(row["group"])
        if xi is None or yi is None:
            continue
        heatmap_data.append([xi, yi, count])

    scenario_rows = []
    for scenario, count in top_scenarios:
        row = catalog_map.get(scenario) or {"group": "other", "title": scenario.replace("_", " ").title()}
        severity = severity_count_by_scenario.get(scenario) or {}
        scenario_rows.append(
            {
                "scenario": scenario,
                "title": row["title"],
                "group": row["group"],
                "alert_count": count,
                "patient_count": len(patient_count_by_scenario.get(scenario) or set()),
                "critical": int(severity.get("critical") or 0),
                "high": int(severity.get("high") or 0),
                "warning": int(severity.get("warning") or 0),
            }
        )

    total_catalog = len(catalog_rows)
    triggered_catalog = len([scenario for scenario in catalog_map if scenario in alert_count_by_scenario])
    return {
        "code": 0,
        "summary": {
            "window": window,
            "total_catalog_scenarios": total_catalog,
            "triggered_catalog_scenarios": triggered_catalog,
            "coverage_ratio": round((triggered_catalog / total_catalog), 4) if total_catalog else 0,
            "total_alerts": len(docs),
            "scenario_groups": len(group_rows),
        },
        "group_rows": group_rows,
        "heatmap": {"x_labels": x_labels, "y_labels": y_labels, "data": heatmap_data},
        "top_scenarios": scenario_rows,
    }


@router.get("/api/analytics/sepsis-bundle/compliance")
async def analytics_sepsis_bundle_compliance(
    month: Optional[str] = Query(None, description="月份 YYYY-MM"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    month_norm = normalize_month_param(month)
    month_start, next_month = _month_bounds(month_norm)
    query: dict = {
        "score_type": {"$in": ["sepsis_bundle_tracker", "sepsis_antibiotic_bundle"]},
        "bundle_type": {"$in": ["sepsis_hour1_bundle", "sepsis_1h_antibiotic"]},
        "bundle_started_at": {"$gte": month_start, "$lt": next_month},
    }
    if dept:
        query["dept"] = dept
    elif dept_code:
        patient_ids = await sepsis_bundle_patient_ids_by_dept_code(dept_code)
        if patient_ids:
            query["patient_id"] = {"$in": patient_ids}
        else:
            return {
                "code": 0,
                "summary": {
                    "month": month_norm,
                    "total_cases": 0,
                    "compliant_1h_cases": 0,
                    "compliance_rate": 0,
                    "overdue_1h_cases": 0,
                    "overdue_3h_cases": 0,
                    "met_late_cases": 0,
                    "pending_active_cases": 0,
                },
            }

    raw_docs = [doc async for doc in runtime.db.col("score_records").find(query)]
    latest_by_episode: dict[str, dict] = {}
    for doc in raw_docs:
        key = _bundle_episode_key(doc)
        current = latest_by_episode.get(key)
        if current is None or _bundle_tracker_sort_time(doc) >= _bundle_tracker_sort_time(current):
            latest_by_episode[key] = doc
    docs = list(latest_by_episode.values())

    statuses = [derive_sepsis_bundle_status(doc, now=datetime.now()) for doc in docs]
    status_pairs = list(zip(docs, statuses))

    total_cases = len(status_pairs)
    compliant_1h_cases = sum(1 for _doc, status in status_pairs if str(status.get("status") or "") == "met")
    overdue_1h_cases = sum(1 for _doc, status in status_pairs if str(status.get("status") or "") == "overdue_1h")
    overdue_3h_cases = sum(1 for _doc, status in status_pairs if str(status.get("status") or "") == "overdue_3h")
    met_late_cases = sum(1 for _doc, status in status_pairs if str(status.get("status") or "") == "met_late")
    pending_active_cases = sum(1 for _doc, status in status_pairs if str(status.get("status") or "") == "pending")

    daily_map: dict[str, dict[str, int]] = {}
    dept_compare_map: dict[str, dict] = {}
    element_summary: dict[str, dict[str, int]] = {}
    recent_cases: list[dict] = []

    for doc, status in status_pairs:
        started = doc.get("bundle_started_at") if isinstance(doc.get("bundle_started_at"), datetime) else None
        day_key = started.strftime("%Y-%m-%d") if started else month_start.strftime("%Y-%m-%d")
        daily_row = daily_map.setdefault(
            day_key,
            {"date": day_key, "total_cases": 0, "compliant_1h_cases": 0, "overdue_1h_cases": 0, "overdue_3h_cases": 0, "met_late_cases": 0, "pending_cases": 0},
        )
        daily_row["total_cases"] += 1
        normalized_status = str(status.get("status") or "")
        if normalized_status == "met":
            daily_row["compliant_1h_cases"] += 1
        elif normalized_status == "overdue_1h":
            daily_row["overdue_1h_cases"] += 1
        elif normalized_status == "overdue_3h":
            daily_row["overdue_3h_cases"] += 1
        elif normalized_status == "met_late":
            daily_row["met_late_cases"] += 1
        elif normalized_status == "pending":
            daily_row["pending_cases"] += 1

        dept_name = str(doc.get("dept") or "未知科室")
        dept_row = dept_compare_map.setdefault(
            dept_name,
            {
                "dept": dept_name,
                "total_cases": 0,
                "compliant_1h_cases": 0,
                "overdue_1h_cases": 0,
                "overdue_3h_cases": 0,
                "met_late_cases": 0,
                "pending_cases": 0,
            },
        )
        dept_row["total_cases"] += 1
        if normalized_status == "met":
            dept_row["compliant_1h_cases"] += 1
        elif normalized_status == "overdue_1h":
            dept_row["overdue_1h_cases"] += 1
        elif normalized_status == "overdue_3h":
            dept_row["overdue_3h_cases"] += 1
        elif normalized_status == "met_late":
            dept_row["met_late_cases"] += 1
        elif normalized_status == "pending":
            dept_row["pending_cases"] += 1

        bundle_elements = doc.get("bundle_elements") if isinstance(doc.get("bundle_elements"), dict) else {}
        for name, item in bundle_elements.items():
            row = element_summary.setdefault(
                str(name),
                {"element": str(name), "required_cases": 0, "completed_cases": 0},
            )
            if item is None:
                continue
            if isinstance(item, dict) and item.get("required") is False:
                continue
            row["required_cases"] += 1
            if isinstance(item, dict) and bool(item.get("completed")):
                row["completed_cases"] += 1

        recent_cases.append(
            {
                "patient_id": str(doc.get("patient_id") or ""),
                "patient_name": doc.get("patient_name") or "",
                "bed": doc.get("bed") or "",
                "dept": doc.get("dept") or "",
                "bundle_started_at": started,
                "status": normalized_status,
                "label": status.get("label"),
                "light": status.get("light"),
                "elapsed_minutes": status.get("elapsed_minutes"),
                "completion_ratio": ((doc.get("bundle_summary") or {}) if isinstance(doc.get("bundle_summary"), dict) else {}).get("completion_ratio"),
                "pending_items": ((doc.get("bundle_summary") or {}) if isinstance(doc.get("bundle_summary"), dict) else {}).get("pending_items") or [],
                "source_rules": status.get("source_rules") or [],
            }
        )

    daily_trend: list[dict] = []
    cursor_day = month_start
    while cursor_day < next_month:
        day_key = cursor_day.strftime("%Y-%m-%d")
        daily_trend.append(daily_map.get(day_key) or {"date": day_key, "total_cases": 0, "compliant_1h_cases": 0, "overdue_1h_cases": 0, "overdue_3h_cases": 0, "met_late_cases": 0, "pending_cases": 0})
        cursor_day += timedelta(days=1)

    dept_compare = []
    for row in dept_compare_map.values():
        total = int(row.get("total_cases") or 0)
        compliant = int(row.get("compliant_1h_cases") or 0)
        dept_compare.append(
            {
                **row,
                "compliance_rate": round((compliant / total), 4) if total else 0,
            }
        )
    dept_compare.sort(key=lambda item: (item.get("compliance_rate") or 0, -(item.get("overdue_3h_cases") or 0), -(item.get("total_cases") or 0)), reverse=True)

    element_rows = []
    for row in element_summary.values():
        required_cases = int(row.get("required_cases") or 0)
        completed_cases = int(row.get("completed_cases") or 0)
        element_rows.append(
            {
                **row,
                "completion_rate": round((completed_cases / required_cases), 4) if required_cases else 0,
            }
        )
    element_rows.sort(key=lambda item: (item.get("completion_rate") or 0, item.get("required_cases") or 0))

    recent_cases.sort(key=lambda item: item.get("bundle_started_at") or datetime.min, reverse=True)

    analytics_payload = {
        "month": month_norm,
        "total_cases": total_cases,
        "compliant_1h_cases": compliant_1h_cases,
        "compliance_rate": round((compliant_1h_cases / total_cases), 4) if total_cases else 0,
        "overdue_1h_cases": overdue_1h_cases,
        "overdue_3h_cases": overdue_3h_cases,
        "met_late_cases": met_late_cases,
        "pending_active_cases": pending_active_cases,
        "daily_trend": daily_trend,
        "dept_compare": dept_compare,
        "element_compliance": element_rows,
        "recent_cases": recent_cases[:20],
    }
    ai_insight = await summarize_sepsis_bundle_analytics({"summary": analytics_payload})

    return {
        "code": 0,
        "summary": analytics_payload,
        "ai_insight": ai_insight,
    }


@router.get("/api/analytics/weaning-summary")
async def analytics_weaning_summary(
    month: Optional[str] = Query(None, description="月份 YYYY-MM"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    month_norm = normalize_month_param(month)
    patient_filter_ids: list[str] | None = None
    if dept:
        patient_filter_ids = []
        cursor = runtime.db.col("patient").find({"$or": [{"dept": dept}, {"hisDept": dept}]}, {"_id": 1})
        async for patient in cursor:
            if patient.get("_id") is not None:
                patient_filter_ids.append(str(patient["_id"]))
    elif dept_code:
        patient_filter_ids = await sepsis_bundle_patient_ids_by_dept_code(dept_code)
        if not patient_filter_ids:
            return {
                "code": 0,
                "summary": {
                    "month": month_norm,
                    "weaning_assessed_patients": 0,
                    "high_risk_patients": 0,
                    "high_risk_ratio": 0,
                    "extubated_patients": 0,
                    "reintubation_risk_patients": 0,
                    "reintubation_risk_ratio": 0,
                    "critical_post_extubation_patients": 0,
                    "daily_trend": [],
                    "dept_compare": [],
                },
            }

    weaning_query: dict = {"score_type": "weaning_assessment", "month": month_norm}
    if patient_filter_ids is not None:
        weaning_query["patient_id"] = {"$in": patient_filter_ids}
    docs = [doc async for doc in runtime.db.col("score_records").find(weaning_query).sort("calc_time", -1)]
    latest_by_patient: dict[str, dict] = {}
    for doc in docs:
        patient_id = str(doc.get("patient_id") or "").strip()
        if patient_id and patient_id not in latest_by_patient:
            latest_by_patient[patient_id] = doc
    weaning_assessed_patients = len(latest_by_patient)
    high_risk_patients = sum(1 for doc in latest_by_patient.values() if str(doc.get("risk_level") or "").lower() in {"high", "critical"})

    month_start = datetime.strptime(f"{month_norm}-01", "%Y-%m-%d")
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    extub_query: dict = {"unBindTime": {"$gte": month_start, "$lt": next_month}}
    if patient_filter_ids is not None:
        extub_query["pid"] = {"$in": patient_filter_ids}

    extubated_patient_ids: set[str] = set()
    extub_cursor = runtime.db.col("deviceBind").find(extub_query, {"pid": 1, "type": 1, "unBindTime": 1})
    async for doc in extub_cursor:
        dtype = str(doc.get("type") or "").lower()
        if any(key in dtype for key in ["vent", "ventilator", "呼吸"]):
            patient_id = str(doc.get("pid") or "").strip()
            if patient_id:
                extubated_patient_ids.add(patient_id)
    extubated_patients = len(extubated_patient_ids)

    risk_query: dict = {"alert_type": "post_extubation_failure_risk", "created_at": {"$gte": month_start, "$lt": next_month}}
    if patient_filter_ids is not None:
        risk_query["patient_id"] = {"$in": patient_filter_ids}
    elif dept:
        risk_query["dept"] = dept
    risk_docs = [doc async for doc in runtime.db.col("alert_records").find(risk_query).sort("created_at", -1)]
    latest_risk_by_patient: dict[str, dict] = {}
    for doc in risk_docs:
        patient_id = str(doc.get("patient_id") or "").strip()
        if patient_id and patient_id not in latest_risk_by_patient:
            latest_risk_by_patient[patient_id] = doc
    reintubation_risk_patients = len(latest_risk_by_patient)
    critical_post_extubation_patients = sum(1 for doc in latest_risk_by_patient.values() if str(doc.get("severity") or "").lower() == "critical")

    all_patient_ids = set(latest_by_patient.keys()) | set(latest_risk_by_patient.keys()) | set(extubated_patient_ids)
    patient_meta: dict[str, dict] = {}
    if all_patient_ids:
        async for patient in runtime.db.col("patient").find(
            {"_id": {"$in": [ObjectId(pid) for pid in all_patient_ids if ObjectId.is_valid(pid)]}},
            {"_id": 1, "dept": 1, "hisDept": 1, "deptCode": 1},
        ):
            patient_meta[str(patient.get("_id"))] = {
                "dept": patient.get("dept") or patient.get("hisDept") or "未知科室",
                "dept_code": patient.get("deptCode") or "",
            }

    daily_assessed: dict[str, set[str]] = {}
    daily_high_risk: dict[str, set[str]] = {}
    for doc in docs:
        calc_time = doc.get("calc_time") if isinstance(doc.get("calc_time"), datetime) else None
        patient_id = str(doc.get("patient_id") or "").strip()
        if not calc_time or not patient_id:
            continue
        day_key = calc_time.strftime("%Y-%m-%d")
        daily_assessed.setdefault(day_key, set()).add(patient_id)
        if str(doc.get("risk_level") or "").lower() in {"high", "critical"}:
            daily_high_risk.setdefault(day_key, set()).add(patient_id)

    daily_extubated: dict[str, set[str]] = {}
    extub_cursor = runtime.db.col("deviceBind").find(extub_query, {"pid": 1, "type": 1, "unBindTime": 1})
    async for doc in extub_cursor:
        dtype = str(doc.get("type") or "").lower()
        unbind = doc.get("unBindTime") if isinstance(doc.get("unBindTime"), datetime) else None
        patient_id = str(doc.get("pid") or "").strip()
        if not unbind or not patient_id or not any(key in dtype for key in ["vent", "ventilator", "呼吸"]):
            continue
        daily_extubated.setdefault(unbind.strftime("%Y-%m-%d"), set()).add(patient_id)

    daily_reintub_risk: dict[str, set[str]] = {}
    for doc in risk_docs:
        created_at = doc.get("created_at") if isinstance(doc.get("created_at"), datetime) else None
        patient_id = str(doc.get("patient_id") or "").strip()
        if not created_at or not patient_id:
            continue
        daily_reintub_risk.setdefault(created_at.strftime("%Y-%m-%d"), set()).add(patient_id)

    daily_trend: list[dict] = []
    cursor_day = month_start
    while cursor_day < next_month:
        day_key = cursor_day.strftime("%Y-%m-%d")
        daily_trend.append(
            {
                "date": day_key,
                "assessed": len(daily_assessed.get(day_key, set())),
                "high_risk": len(daily_high_risk.get(day_key, set())),
                "extubated": len(daily_extubated.get(day_key, set())),
                "reintubation_risk": len(daily_reintub_risk.get(day_key, set())),
            }
        )
        cursor_day += timedelta(days=1)

    dept_compare_map: dict[str, dict] = {}
    for patient_id, doc in latest_by_patient.items():
        dept_name = (patient_meta.get(patient_id) or {}).get("dept") or "未知科室"
        row = dept_compare_map.setdefault(
            dept_name,
            {
                "dept": dept_name,
                "weaning_assessed_patients": 0,
                "high_risk_patients": 0,
                "extubated_patients": 0,
                "reintubation_risk_patients": 0,
                "critical_post_extubation_patients": 0,
            },
        )
        row["weaning_assessed_patients"] += 1
        if str(doc.get("risk_level") or "").lower() in {"high", "critical"}:
            row["high_risk_patients"] += 1

    for patient_id in extubated_patient_ids:
        dept_name = (patient_meta.get(patient_id) or {}).get("dept") or "未知科室"
        row = dept_compare_map.setdefault(
            dept_name,
            {
                "dept": dept_name,
                "weaning_assessed_patients": 0,
                "high_risk_patients": 0,
                "extubated_patients": 0,
                "reintubation_risk_patients": 0,
                "critical_post_extubation_patients": 0,
            },
        )
        row["extubated_patients"] += 1

    for patient_id, doc in latest_risk_by_patient.items():
        dept_name = (patient_meta.get(patient_id) or {}).get("dept") or "未知科室"
        row = dept_compare_map.setdefault(
            dept_name,
            {
                "dept": dept_name,
                "weaning_assessed_patients": 0,
                "high_risk_patients": 0,
                "extubated_patients": 0,
                "reintubation_risk_patients": 0,
                "critical_post_extubation_patients": 0,
            },
        )
        row["reintubation_risk_patients"] += 1
        if str(doc.get("severity") or "").lower() == "critical":
            row["critical_post_extubation_patients"] += 1

    dept_compare = []
    for row in dept_compare_map.values():
        assessed = int(row.get("weaning_assessed_patients") or 0)
        extubated = int(row.get("extubated_patients") or 0)
        high_risk = int(row.get("high_risk_patients") or 0)
        reintub_risk = int(row.get("reintubation_risk_patients") or 0)
        dept_compare.append(
            {
                **row,
                "high_risk_ratio": round(high_risk / assessed, 4) if assessed else 0,
                "reintubation_risk_ratio": round(reintub_risk / extubated, 4) if extubated else 0,
            }
        )
    dept_compare.sort(
        key=lambda item: (
            item.get("reintubation_risk_ratio") or 0,
            item.get("high_risk_ratio") or 0,
            item.get("weaning_assessed_patients") or 0,
        ),
        reverse=True,
    )

    return {
        "code": 0,
        "summary": {
            "month": month_norm,
            "weaning_assessed_patients": weaning_assessed_patients,
            "high_risk_patients": high_risk_patients,
            "high_risk_ratio": round((high_risk_patients / weaning_assessed_patients), 4) if weaning_assessed_patients else 0,
            "extubated_patients": extubated_patients,
            "reintubation_risk_patients": reintubation_risk_patients,
            "reintubation_risk_ratio": round((reintubation_risk_patients / extubated_patients), 4) if extubated_patients else 0,
            "critical_post_extubation_patients": critical_post_extubation_patients,
            "daily_trend": daily_trend,
            "dept_compare": dept_compare,
        },
    }


@router.get("/api/alerts/analytics/frequency")
async def alerts_analytics_frequency(
    window: str = Query("7d", description="时间窗口: 24h/7d/30d 或 12h/14d"),
    bucket: str = Query("hour", description="聚合粒度: hour/day"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    hours = window_to_hours(window, default=168)
    bucket_norm, fmt = bucket_dt_format(bucket)
    since = datetime.utcnow() - timedelta(hours=hours)

    query: dict = {"created_at": {"$gte": since}}
    if dept:
        query["dept"] = dept
    if dept_code:
        query["deptCode"] = dept_code

    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": {
                    "time": {"$dateToString": {"format": fmt, "date": "$created_at"}},
                    "severity": "$severity",
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.time": 1}},
    ]

    timeline: dict[str, dict] = {}
    cursor = await runtime.db.col("alert_records").aggregate(pipeline)
    async for doc in cursor:
        time_key = str(doc.get("_id", {}).get("time") or "")
        if not time_key:
            continue
        severity = str(doc.get("_id", {}).get("severity") or "")
        count = int(doc.get("count", 0) or 0)
        if time_key not in timeline:
            timeline[time_key] = {"time": time_key, "total": 0, "warning": 0, "high": 0, "critical": 0}
        timeline[time_key]["total"] += count
        if severity in ("warning", "high", "critical"):
            timeline[time_key][severity] += count

    return {"code": 0, "window": window, "bucket": bucket_norm, "series": sorted(timeline.values(), key=lambda item: item["time"])}


@router.get("/api/alerts/analytics/heatmap")
async def alerts_analytics_heatmap(
    window: str = Query("7d", description="时间窗口"),
    top_n: int = Query(12, ge=3, le=30, description="规则类型数量"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    hours = window_to_hours(window, default=168)
    since = datetime.utcnow() - timedelta(hours=hours)
    match_query: dict = {"created_at": {"$gte": since}}
    if dept:
        match_query["dept"] = dept
    if dept_code:
        match_query["deptCode"] = dept_code

    rule_expr = {"$ifNull": ["$alert_type", {"$ifNull": ["$category", {"$ifNull": ["$rule_id", "unknown"]}]}]}

    pipeline_top = [
        {"$match": match_query},
        {"$group": {"_id": rule_expr, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]
    top_rules: list[str] = []
    cursor_top = await runtime.db.col("alert_records").aggregate(pipeline_top)
    async for doc in cursor_top:
        top_rules.append(str(doc.get("_id") or "unknown"))

    if not top_rules:
        return {"code": 0, "window": window, "x_labels": [f"{hour:02d}" for hour in range(24)], "y_labels": [], "data": []}

    pipeline = [
        {"$match": match_query},
        {"$project": {"rule_type": rule_expr, "hour": {"$hour": "$created_at"}}},
        {"$match": {"rule_type": {"$in": top_rules}}},
        {"$group": {"_id": {"rule_type": "$rule_type", "hour": "$hour"}, "count": {"$sum": 1}}},
    ]

    heatmap_data: list[list[int]] = []
    y_index = {rule: idx for idx, rule in enumerate(top_rules)}
    cursor = await runtime.db.col("alert_records").aggregate(pipeline)
    async for doc in cursor:
        key = doc.get("_id", {})
        rule = str(key.get("rule_type") or "unknown")
        hour = int(key.get("hour", 0) or 0)
        count = int(doc.get("count", 0) or 0)
        if rule in y_index and 0 <= hour <= 23:
            heatmap_data.append([hour, y_index[rule], count])

    return {
        "code": 0,
        "window": window,
        "x_labels": [f"{hour:02d}" for hour in range(24)],
        "y_labels": top_rules,
        "data": heatmap_data,
    }


@router.get("/api/alerts/analytics/rankings")
async def alerts_analytics_rankings(
    window: str = Query("7d", description="时间窗口"),
    top_n: int = Query(10, ge=3, le=30, description="排名数量"),
    dept: Optional[str] = Query(None, description="科室名称"),
    dept_code: Optional[str] = Query(None, description="科室代码"),
):
    hours = window_to_hours(window, default=168)
    since = datetime.utcnow() - timedelta(hours=hours)
    match_query: dict = {"created_at": {"$gte": since}}
    if dept:
        match_query["dept"] = dept
    if dept_code:
        match_query["deptCode"] = dept_code

    dept_pipeline = [
        {"$match": match_query},
        {"$group": {"_id": {"$ifNull": ["$dept", "未知科室"]}, "count": {"$sum": 1}, **severity_projection()}},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]
    dept_rankings: list[dict] = []
    dept_cursor = await runtime.db.col("alert_records").aggregate(dept_pipeline)
    async for doc in dept_cursor:
        dept_rankings.append(
            {
                "dept": str(doc.get("_id") or "未知科室"),
                "count": int(doc.get("count", 0) or 0),
                "warning": int(doc.get("warning", 0) or 0),
                "high": int(doc.get("high", 0) or 0),
                "critical": int(doc.get("critical", 0) or 0),
            }
        )

    bed_pipeline = [
        {"$match": match_query},
        {"$project": {"dept": {"$ifNull": ["$dept", "未知科室"]}, "bed": {"$ifNull": ["$bed", "未标注床位"]}, "severity": "$severity"}},
        {"$group": {"_id": {"dept": "$dept", "bed": "$bed"}, "count": {"$sum": 1}, **severity_projection()}},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]
    bed_rankings: list[dict] = []
    bed_cursor = await runtime.db.col("alert_records").aggregate(bed_pipeline)
    async for doc in bed_cursor:
        key = doc.get("_id", {})
        bed_rankings.append(
            {
                "dept": str(key.get("dept") or "未知科室"),
                "bed": str(key.get("bed") or "未标注床位"),
                "count": int(doc.get("count", 0) or 0),
                "warning": int(doc.get("warning", 0) or 0),
                "high": int(doc.get("high", 0) or 0),
                "critical": int(doc.get("critical", 0) or 0),
            }
        )

    return {"code": 0, "window": window, "dept_rankings": dept_rankings, "bed_rankings": bed_rankings}
