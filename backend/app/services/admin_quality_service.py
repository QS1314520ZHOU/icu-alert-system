from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.utils.serialization import serialize_doc


def _window_since(days: int) -> datetime:
    return datetime.now() - timedelta(days=max(1, min(int(days or 30), 365)))


def _rule_key(doc: dict[str, Any]) -> str:
    return str(doc.get("rule_id") or doc.get("alert_type") or doc.get("name") or "unknown").strip() or "unknown"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dept_scope_query(*, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any] | None:
    dept_text = _text(dept)
    dept_code_text = _text(dept_code)
    if dept_text and not dept_code_text and dept_text.isdigit():
        dept_code_text = dept_text
        dept_text = ""
    clauses: list[dict[str, Any]] = []
    if dept_code_text:
        codes = [item.strip() for item in dept_code_text.split(",") if item.strip()]
        if codes:
            clauses.append({"deptCode": {"$in": codes}})
    if dept_text:
        clauses.append({"$or": [{"dept": dept_text}, {"hisDept": dept_text}, {"department": dept_text}, {"deptName": dept_text}]})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}


async def _patient_keys_for_dept(db: Any, *, dept: str | None = None, dept_code: str | None = None) -> set[str]:
    scope = _dept_scope_query(dept=dept, dept_code=dept_code)
    if not scope:
        return set()
    cursor = db.col("patient").find(scope, {"_id": 1, "patientId": 1, "pid": 1, "hisPid": 1, "hisPID": 1})
    keys: set[str] = set()
    async for patient in cursor:
        for field in ("_id", "patientId", "pid", "hisPid", "hisPID"):
            value = _text(patient.get(field))
            if value:
                keys.add(value)
    return keys


def _with_dept_scope(base: dict[str, Any], *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    scope = _dept_scope_query(dept=dept, dept_code=dept_code)
    if not scope:
        return base
    return {"$and": [base, scope]}


async def admin_quality_summary(db: Any, *, days: int = 30, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    since = _window_since(days)
    scoped = bool(_text(dept) or _text(dept_code))
    cursor = db.col("alert_records").find(
        _with_dept_scope({"created_at": {"$gte": since}}, dept=dept, dept_code=dept_code),
        {
            "rule_id": 1,
            "alert_type": 1,
            "name": 1,
            "dept": 1,
            "deptCode": 1,
            "created_at": 1,
            "viewed_at": 1,
            "acknowledged_at": 1,
            "ack_disposition": 1,
            "disposition": 1,
            "review_result": 1,
            "severity": 1,
        },
    ).sort("created_at", -1).limit(20000)
    docs = [doc async for doc in cursor]

    by_rule: dict[str, dict[str, Any]] = {}
    by_dept: dict[str, dict[str, Any]] = {}
    response_minutes: list[float] = []
    for doc in docs:
        key = _rule_key(doc)
        rule = by_rule.setdefault(key, {"rule": key, "total": 0, "false_positive": 0, "duplicate": 0, "data_error": 0, "reviewed": 0})
        rule["total"] += 1
        disposition = str(doc.get("ack_disposition") or ((doc.get("disposition") or {}).get("action") if isinstance(doc.get("disposition"), dict) else "") or "").lower()
        if disposition in {"false_positive", "override", "overridden"}:
            rule["false_positive"] += 1
        if disposition == "duplicate":
            rule["duplicate"] += 1
        if disposition == "data_error":
            rule["data_error"] += 1
        if doc.get("review_result"):
            rule["reviewed"] += 1

        dept = str(doc.get("dept") or doc.get("deptCode") or "未标注科室")
        dept_row = by_dept.setdefault(dept, {"dept": dept, "total": 0, "acknowledged": 0, "response_minutes": []})
        dept_row["total"] += 1
        if doc.get("acknowledged_at"):
            dept_row["acknowledged"] += 1
        created_at = doc.get("created_at")
        ack_at = doc.get("acknowledged_at")
        if isinstance(created_at, datetime) and isinstance(ack_at, datetime):
            minutes = max((ack_at - created_at).total_seconds() / 60.0, 0.0)
            dept_row["response_minutes"].append(minutes)
            response_minutes.append(minutes)

    rule_rows = []
    for row in by_rule.values():
        total = max(int(row["total"]), 1)
        row["false_positive_rate"] = round(row["false_positive"] / total, 3)
        row["duplicate_rate"] = round(row["duplicate"] / total, 3)
        row["data_error_rate"] = round(row["data_error"] / total, 3)
        row["review_rate"] = round(row["reviewed"] / total, 3)
        rule_rows.append(row)
    rule_rows.sort(key=lambda item: (item["false_positive_rate"] + item["duplicate_rate"] + item["data_error_rate"], item["total"]), reverse=True)

    dept_rows = []
    for row in by_dept.values():
        total = max(int(row["total"]), 1)
        mins = sorted(float(x) for x in row.pop("response_minutes", []) if x is not None)
        row["ack_rate"] = round(row["acknowledged"] / total, 3)
        row["median_response_minutes"] = round(mins[len(mins) // 2], 1) if mins else None
        dept_rows.append(row)
    dept_rows.sort(key=lambda item: (item["median_response_minutes"] is None, item["median_response_minutes"] or 999999))

    patient_keys = await _patient_keys_for_dept(db, dept=dept, dept_code=dept_code) if scoped else set()
    module_query: dict[str, Any] = {"created_at": {"$gte": since}}
    if scoped:
        if patient_keys:
            module_query = {
                "$and": [
                    module_query,
                    {
                        "$or": [
                            {"target_id": {"$in": list(patient_keys)}},
                            {"detail.patient_id": {"$in": list(patient_keys)}},
                            {"detail.patient_ids": {"$in": list(patient_keys)}},
                        ]
                    },
                ]
            }
        else:
            module_query = {"_id": {"$exists": False}}
    module_cursor = db.col("audit_logs").find(
        module_query,
        {"module": 1, "action": 1, "created_at": 1, "actor": 1, "target_id": 1, "detail": 1},
    ).sort("created_at", -1).limit(20000)
    module_map: dict[str, dict[str, Any]] = {}
    async for doc in module_cursor:
        module = str(doc.get("module") or "unknown")
        row = module_map.setdefault(module, {"module": module, "events": 0, "actors": set(), "last_used_at": None})
        row["events"] += 1
        if doc.get("actor"):
            row["actors"].add(str(doc.get("actor")))
        if row["last_used_at"] is None or (isinstance(doc.get("created_at"), datetime) and doc.get("created_at") > row["last_used_at"]):
            row["last_used_at"] = doc.get("created_at")
    module_rows = []
    for row in module_map.values():
        row["actor_count"] = len(row.pop("actors"))
        module_rows.append(row)
    module_rows.sort(key=lambda item: item["events"], reverse=True)

    median_response = None
    if response_minutes:
        sorted_minutes = sorted(response_minutes)
        median_response = round(sorted_minutes[len(sorted_minutes) // 2], 1)

    return serialize_doc(
        {
            "days": days,
            "generated_at": datetime.now(),
            "summary": {
                "alerts": len(docs),
                "rules": len(rule_rows),
                "departments": len(dept_rows),
                "median_response_minutes": median_response,
                "modules_used": len(module_rows),
            },
            "rule_false_positive_rows": rule_rows[:50],
            "department_response_rows": dept_rows[:50],
            "module_usage_rows": module_rows[:50],
        }
    )
