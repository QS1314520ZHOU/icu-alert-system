"""管理质控汇总 v2 — 基于人工复核的统计口径。

变更：
- false_positive_rate → false_discovery_proportion (FDP=FP/reviewed, 非FPR)
- 真正 FPR 需非告警样本 → 返回 null
- PPV → reviewed_sample_ppv 附带 Wilson CI
- 按 rule_id、科室、时间分层统计
- 快速反馈不进入正式统计
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from app.utils.serialization import serialize_doc


def _window_since(days: int) -> datetime:
    return datetime.now() - timedelta(days=max(1, min(int(days or 30), 365)))


def _rule_key(doc: dict[str, Any]) -> str:
    return str(
        doc.get("rule_id") or doc.get("alert_type") or doc.get("name") or "unknown",
    ).strip() or "unknown"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dept_scope_query(
    *, dept: str | None = None, dept_code: str | None = None,
) -> dict[str, Any] | None:
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
        clauses.append({
            "$or": [
                {"dept": dept_text}, {"hisDept": dept_text},
                {"department": dept_text}, {"deptName": dept_text},
            ],
        })
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}


def _with_dept_scope(
    base: dict[str, Any], *, dept: str | None = None, dept_code: str | None = None,
) -> dict[str, Any]:
    scope = _dept_scope_query(dept=dept, dept_code=dept_code)
    if not scope:
        return base
    return {"$and": [base, scope]}


def _wilson_ci(numerator: int, denominator: int, z: float = 1.96) -> dict[str, Any]:
    if denominator <= 0:
        return {"lower": None, "upper": None, "method": "wilson", "z": z}
    p = numerator / denominator
    n = denominator
    z2 = z * z
    denominator_adj = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denominator_adj
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denominator_adj
    return {
        "lower": round(max(0.0, centre - margin), 4),
        "upper": round(min(1.0, centre + margin), 4),
        "method": "wilson",
        "z": z,
    }


async def admin_quality_summary(
    db: Any, *, days: int = 30, dept: str | None = None,
    dept_code: str | None = None,
) -> dict[str, Any]:
    since = _window_since(days)
    scoped = bool(_text(dept) or _text(dept_code))
    min_threshold = 30

    # ── 1. Get adjudication-based stats ──
    adj_match: dict[str, Any] = {"created_at": {"$gte": since}}
    # Department filtering on adjudications (by patient_id lookup)
    if scoped:
        patient_keys = await _patient_keys_for_dept(db, dept=dept, dept_code=dept_code)
        if patient_keys:
            adj_match["patient_id"] = {"$in": list(patient_keys)}
        else:
            adj_match = {"_id": {"$exists": False}}

    adj_cursor = db.col("alert_adjudications").find(
        adj_match,
        {
            "alert_id": 1, "rule_id": 1, "alert_type": 1, "scanner_name": 1,
            "dept": 1, "dept_code": 1,
            "alert_validity": 1, "clinical_actionability": 1,
            "workflow_context": 1, "clinical_helpfulness": 1,
            "action_related": 1, "harm_type": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(20000)
    adj_docs = [doc async for doc in adj_cursor]

    # ── 2. Per-rule adjudication stats ──
    by_rule: dict[str, dict[str, Any]] = {}
    for doc in adj_docs:
        key = _text(doc.get("rule_id") or doc.get("scanner_name") or doc.get("alert_type")) or "unknown"
        rule = by_rule.setdefault(key, {
            "rule": key, "reviewed": 0, "true_positive": 0,
            "false_positive": 0, "indeterminate": 0,
            "actionable": 0, "already_addressed": 0,
            "helpful": 0, "neutral": 0, "harmful": 0,
            "action_related_confirmed": 0,
        })
        rule["reviewed"] += 1
        validity = str(doc.get("alert_validity") or "")
        if validity == "true_positive":
            rule["true_positive"] += 1
        elif validity == "false_positive":
            rule["false_positive"] += 1
        elif validity == "indeterminate":
            rule["indeterminate"] += 1
        if str(doc.get("clinical_actionability") or "") == "actionable":
            rule["actionable"] += 1
        if str(doc.get("workflow_context") or "") == "already_addressed":
            rule["already_addressed"] += 1
        helpfulness = str(doc.get("clinical_helpfulness") or "")
        if helpfulness == "helpful":
            rule["helpful"] += 1
        elif helpfulness == "neutral":
            rule["neutral"] += 1
        elif helpfulness == "harmful":
            rule["harmful"] += 1
        if doc.get("action_related") is True:
            rule["action_related_confirmed"] += 1

    # ── 3. Get alert record counts for review_coverage ──
    record_match: dict[str, Any] = _with_dept_scope(
        {"created_at": {"$gte": since}}, dept=dept, dept_code=dept_code,
    )
    record_cursor = db.col("alert_records").find(
        record_match, {"alert_type": 1, "rule_id": 1, "dept": 1, "deptCode": 1, "acknowledged_at": 1, "created_at": 1},
    ).sort("created_at", -1).limit(20000)
    record_docs = [doc async for doc in record_cursor]

    fired_by_rule: dict[str, int] = {}
    for doc in record_docs:
        key = _rule_key(doc)
        fired_by_rule[key] = fired_by_rule.get(key, 0) + 1

    # ── 4. Build rule rows ──
    all_rules = sorted(set(list(by_rule.keys()) + list(fired_by_rule.keys())))
    rule_rows = []
    for rule_name in all_rules:
        adj = by_rule.get(rule_name, {})
        fired = fired_by_rule.get(rule_name, 0)
        reviewed = int(adj.get("reviewed") or 0)
        tp = int(adj.get("true_positive") or 0)
        fp = int(adj.get("false_positive") or 0)
        indet = int(adj.get("indeterminate") or 0)
        determinate = tp + fp

        fdp = round(fp / determinate, 3) if determinate > 0 else None
        ppv = round(tp / determinate, 3) if determinate > 0 else None
        ci = _wilson_ci(tp, determinate) if determinate > 0 else {"lower": None, "upper": None}
        review_coverage = round(reviewed / fired, 3) if fired > 0 else 0.0
        indet_prop = round(indet / reviewed, 3) if reviewed > 0 else None

        rule_rows.append({
            "rule": rule_name,
            "fired_count": fired,
            "formally_reviewed_count": reviewed,
            "determinate_reviewed": determinate,
            "review_coverage": review_coverage,
            "true_positive": tp,
            "false_positive": fp,
            "indeterminate": indet,
            "indeterminate_proportion": indet_prop,
            "false_discovery_proportion": fdp,
            "fdp_note": f"FDP={fp}/{determinate}=FP/(TP+FP) — indeterminate excluded. Not FPR. True FPR requires non-alert samples.",
            "true_fpr": None,
            "true_fpr_reason": "No non-alert control group available",
            "reviewed_sample_ppv": ppv,
            "ppv_note": f"PPV={tp}/{determinate}=TP/(TP+FP) — indeterminate excluded",
            "ppv_ci_lower": ci.get("lower"),
            "ppv_ci_upper": ci.get("upper"),
            "actionable_count": int(adj.get("actionable") or 0),
            "already_addressed_count": int(adj.get("already_addressed") or 0),
            "helpful_count": int(adj.get("helpful") or 0),
            "neutral_count": int(adj.get("neutral") or 0),
            "harmful_count": int(adj.get("harmful") or 0),
            "action_related_confirmed": int(adj.get("action_related_confirmed") or 0),
            "insufficient_review_samples": reviewed < min_threshold,
            "min_review_threshold": min_threshold,
            "sampling_method": "convenience",
            "representativeness": "unknown",
        })
    rule_rows.sort(
        key=lambda item: (
            -(int(item.get("reviewed_count") or 0)),
            -(int(item.get("fired_count") or 0)),
            item.get("rule") or "",
        ),
    )

    # ── 5. Per-department stats ──
    by_dept: dict[str, dict[str, Any]] = {}
    response_minutes: list[float] = []
    for doc in record_docs:
        dept_name = str(doc.get("dept") or doc.get("deptCode") or "未标注科室")
        dept_row = by_dept.setdefault(dept_name, {
            "dept": dept_name, "total": 0, "acknowledged": 0,
            "response_minutes": [], "reviewed": 0,
        })
        dept_row["total"] += 1
        if doc.get("acknowledged_at"):
            dept_row["acknowledged"] += 1
        created_at = doc.get("created_at")
        ack_at = doc.get("acknowledged_at")
        if isinstance(created_at, datetime) and isinstance(ack_at, datetime):
            minutes = max((ack_at - created_at).total_seconds() / 60.0, 0.0)
            dept_row["response_minutes"].append(minutes)
            response_minutes.append(minutes)

    # Also count adjudications by dept
    for doc in adj_docs:
        dept_name = str(doc.get("dept") or doc.get("dept_code") or "未标注科室")
        dept_row = by_dept.setdefault(dept_name, {
            "dept": dept_name, "total": 0, "acknowledged": 0,
            "response_minutes": [], "reviewed": 0,
        })
        dept_row["reviewed"] += 1

    dept_rows = []
    for row in by_dept.values():
        total = max(int(row["total"]), 1)
        mins = sorted(float(x) for x in row.pop("response_minutes", []) if x is not None)
        row["ack_rate"] = round(row["acknowledged"] / total, 3)
        row["review_coverage"] = round(row["reviewed"] / total, 3) if total > 0 else 0.0
        row["median_response_minutes"] = round(mins[len(mins) // 2], 1) if mins else None
        dept_rows.append(row)
    dept_rows.sort(
        key=lambda item: (
            item["median_response_minutes"] is None,
            item["median_response_minutes"] or 999999,
        ),
    )

    # ── 6. Module usage ──
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
                        ],
                    },
                ],
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
        row = module_map.setdefault(module, {
            "module": module, "events": 0, "actors": set(),
            "last_used_at": None,
        })
        row["events"] += 1
        if doc.get("actor"):
            row["actors"].add(str(doc.get("actor")))
        if (
            row["last_used_at"] is None
            or (
                isinstance(doc.get("created_at"), datetime)
                and doc.get("created_at") > row["last_used_at"]
            )
        ):
            row["last_used_at"] = doc.get("created_at")
    module_rows = []
    for row in module_map.values():
        row["actor_count"] = len(row.pop("actors"))
        module_rows.append(row)
    module_rows.sort(key=lambda item: item["events"], reverse=True)

    # ── 7. Feedback exclusion count ──
    feedback_count = await db.col("alert_feedback").count_documents(
        {"created_at": {"$gte": since}},
    )

    median_response = None
    if response_minutes:
        sorted_minutes = sorted(response_minutes)
        median_response = round(sorted_minutes[len(sorted_minutes) // 2], 1)

    return serialize_doc({
        "days": days,
        "generated_at": datetime.now(),
        "summary": {
            "alerts": len(record_docs),
            "rules": len(rule_rows),
            "departments": len(dept_rows),
            "median_response_minutes": median_response,
            "modules_used": len(module_rows),
            "total_adjudications": len(adj_docs),
            "total_feedback_excluded_from_stats": feedback_count,
            "terminology": (
                "FDP=FP/reviewed (not FPR). "
                "PPV=TP/reviewed (reviewed sample only). "
                "True FPR requires non-alert samples → null. "
                "Feedback records excluded from formal statistics."
            ),
        },
        "rule_rows": rule_rows[:50],
        "department_response_rows": dept_rows[:50],
        "module_usage_rows": module_rows[:50],
    })


async def _patient_keys_for_dept(
    db: Any, *, dept: str | None = None, dept_code: str | None = None,
) -> set[str]:
    scope = _dept_scope_query(dept=dept, dept_code=dept_code)
    if not scope:
        return set()
    cursor = db.col("patient").find(
        scope, {"_id": 1, "patientId": 1, "pid": 1, "hisPid": 1, "hisPID": 1},
    )
    keys: set[str] = set()
    async for patient in cursor:
        for field in ("_id", "patientId", "pid", "hisPid", "hisPID"):
            value = _text(patient.get(field))
            if value:
                keys.add(value)
    return keys
