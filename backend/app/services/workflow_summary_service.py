from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.utils.patient_helpers import admitted_patient_query, calculate_age, infer_clinical_tags
from app.utils.serialization import serialize_doc


SEVERITY_RANK = {"info": 1, "warning": 2, "high": 3, "critical": 4}


def _now() -> datetime:
    return datetime.now()


def _safe_dt(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _patient_name(patient: dict[str, Any]) -> str:
    return _text(patient.get("name") or patient.get("hisName")) or "未知患者"


def _patient_bed(patient: dict[str, Any]) -> str:
    return _text(patient.get("hisBed") or patient.get("bed") or patient.get("bedNo"))


def _alert_key(alert: dict[str, Any]) -> str:
    return _text(alert.get("rule_id") or alert.get("alert_type") or alert.get("name") or "unknown")


def _alert_title(alert: dict[str, Any]) -> str:
    return _text(alert.get("name") or alert.get("alert_type") or alert.get("rule_id")) or "预警"


def _is_unhandled(alert: dict[str, Any]) -> bool:
    if alert.get("acknowledged_at"):
        return False
    disposition = _text(alert.get("ack_disposition")).lower()
    return disposition not in {"resolved", "accepted", "false_positive", "override", "overridden", "ignored"}


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _alert_suggestion(alert: dict[str, Any]) -> list[str]:
    haystack = " ".join(
        _text(alert.get(key))
        for key in ("name", "alert_type", "rule_id", "parameter", "category", "condition")
    )
    extra = alert.get("extra") if isinstance(alert.get("extra"), dict) else {}
    if isinstance(extra.get("recommendations"), list):
        rows = [_text(item) for item in extra.get("recommendations") if _text(item)]
        if rows:
            return rows[:4]
    if _contains_any(haystack, ["lactate", "乳酸", "shock", "sepsis", "脓毒", "休克"]):
        return ["复查乳酸和血气", "评估灌注状态与容量反应性", "复核感染灶和抗感染方案"]
    if _contains_any(haystack, ["spo2", "氧合", "fio2", "peep", "ards", "呼吸"]):
        return ["复核呼吸机参数", "评估肺保护通气与氧合趋势", "必要时完善血气"]
    if _contains_any(haystack, ["尿", "cr", "creatinine", "aki", "肾"]):
        return ["复核尿量和肌酐趋势", "评估液体平衡", "排查肾毒性药物"]
    if _contains_any(haystack, ["glucose", "血糖"]):
        return ["复测血糖", "核对胰岛素和营养输入", "评估低/高血糖风险"]
    return ["查看触发依据", "结合床旁情况确认是否处理", "必要时设置复评任务"]


def _alert_evidence(alert: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    value = alert.get("value")
    parameter = _text(alert.get("parameter") or alert.get("condition"))
    if value is not None and value != "":
        rows.append(f"{parameter or '指标'} {value}")
    extra = alert.get("extra") if isinstance(alert.get("extra"), dict) else {}
    for key in ("evidence", "evidences", "reasons", "reasoning"):
        value = extra.get(key)
        if isinstance(value, list):
            rows.extend(_text(item) for item in value if _text(item))
        elif _text(value):
            rows.append(_text(value))
    snapshot = extra.get("context_snapshot") if isinstance(extra.get("context_snapshot"), dict) else {}
    labs = snapshot.get("labs") if isinstance(snapshot.get("labs"), dict) else {}
    vitals = snapshot.get("vitals") if isinstance(snapshot.get("vitals"), dict) else {}
    for key, label in [("lactate", "乳酸"), ("map", "MAP"), ("spo2", "SpO2"), ("hr", "HR")]:
        item = labs.get(key) or vitals.get(key)
        if isinstance(item, dict) and item.get("value") is not None:
            rows.append(f"{label} {item.get('value')}{item.get('unit') or ''}")
    return rows[:5]


async def build_patient_priority(db: Any, *, dept: str | None = None, dept_code: str | None = None, limit: int = 120) -> list[dict[str, Any]]:
    query: dict[str, Any] = admitted_patient_query()
    if dept:
        query = {"$and": [query, {"$or": [{"hisDept": dept}, {"dept": dept}]}]}
    elif dept_code:
        query = {"$and": [query, {"deptCode": dept_code}]}

    patients = [doc async for doc in db.col("patient").find(query).limit(limit)]
    if not patients:
        return []
    patient_ids = [str(row.get("_id")) for row in patients if row.get("_id")]
    since24 = _now() - timedelta(hours=24)
    since6 = _now() - timedelta(hours=6)
    alerts_by_patient: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cursor = db.col("alert_records").find(
        {"patient_id": {"$in": patient_ids}, "created_at": {"$gte": since24}},
        {
            "patient_id": 1,
            "rule_id": 1,
            "alert_type": 1,
            "name": 1,
            "severity": 1,
            "created_at": 1,
            "acknowledged_at": 1,
            "ack_actor": 1,
            "ack_disposition": 1,
            "lifecycle_updated_at": 1,
            "extra": 1,
            "parameter": 1,
            "value": 1,
        },
    ).sort("created_at", -1)
    async for alert in cursor:
        alerts_by_patient[str(alert.get("patient_id") or "")].append(alert)

    rows: list[dict[str, Any]] = []
    for patient in patients:
        pid = str(patient.get("_id"))
        alerts = alerts_by_patient.get(pid, [])
        unhandled = [alert for alert in alerts if _is_unhandled(alert)]
        severe_count = sum(1 for alert in unhandled if _text(alert.get("severity")).lower() in {"critical", "high"})
        warning_count = sum(1 for alert in unhandled if _text(alert.get("severity")).lower() == "warning")
        new_alerts = [alert for alert in alerts if (_safe_dt(alert.get("created_at")) or datetime.min) >= since6]
        haystack = " ".join(
            [
                _text(patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis")),
                " ".join(_text(alert.get("name") or alert.get("alert_type") or alert.get("rule_id")) for alert in alerts[:12]),
            ]
        )
        tags = infer_clinical_tags(patient)
        tag_text = " ".join(_text(tag.get("tag") or tag.get("label")) for tag in tags if isinstance(tag, dict))
        mechanically_ventilated = _contains_any(haystack + tag_text, ["机械通气", "vent", "fio2", "peep", "插管"])
        infection_risk = _contains_any(haystack + tag_text, ["感染", "脓毒", "sepsis", "lactate", "乳酸"])
        weaning_candidate = _contains_any(haystack + tag_text, ["sbt", "脱机", "撤机", "weaning"])
        nutrition_risk = _contains_any(haystack + tag_text, ["nutrition", "营养"])
        data_completeness = {
            "vitals": 0.35 if any("无监护" in _alert_title(a) for a in alerts) else (0.95 if alerts else 0.7),
            "labs": 0.8 if alerts else 0.55,
            "drugs": 0.7,
            "nursing": 0.4 if not _contains_any(tag_text, ["rass", "cam"]) else 0.75,
        }
        missing_severity = sum(1 for value in data_completeness.values() if float(value) < 0.6)
        trend_up = bool(new_alerts and len(new_alerts) >= max(1, len(alerts) // 3))
        score = (
            severe_count * 30
            + warning_count * 15
            + (20 if trend_up else 0)
            + (10 if mechanically_ventilated else 0)
            + (15 if infection_risk else 0)
            + missing_severity * 5
            + len(new_alerts) * 20
        )
        reasons: list[str] = []
        if severe_count:
            reasons.append(f"{severe_count}条严重未处理预警")
        if warning_count:
            reasons.append(f"{warning_count}条中级未处理预警")
        if new_alerts:
            reasons.append(f"近6小时新发{len(new_alerts)}条")
        if trend_up:
            reasons.append("风险上升")
        if mechanically_ventilated:
            reasons.append("机械通气")
        if infection_risk:
            reasons.append("感染/脓毒症风险")
        if weaning_candidate:
            reasons.append("脱机候选")
        if nutrition_risk:
            reasons.append("营养风险")
        if missing_severity:
            reasons.append("数据缺失")
        latest_handled = next((alert for alert in alerts if alert.get("acknowledged_at")), None)
        rows.append(
            {
                "patient_id": pid,
                "bed": _patient_bed(patient),
                "name": _patient_name(patient),
                "age": patient.get("age") or calculate_age(patient.get("birthday")),
                "dept": patient.get("hisDept") or patient.get("dept"),
                "priority_score": min(int(score), 100),
                "risk_level": "critical" if score >= 80 else "warning" if score >= 45 else "info" if score else "unknown",
                "risk_reasons": reasons[:6] or ["暂无高优先级原因"],
                "unhandled_alerts": len(unhandled),
                "new_alerts_6h": len(new_alerts),
                "risk_trend": "up" if trend_up else "flat",
                "mechanical_ventilation": mechanically_ventilated,
                "infection_risk": infection_risk,
                "weaning_candidate": weaning_candidate,
                "nutrition_risk": nutrition_risk,
                "data_missing": missing_severity > 0,
                "data_completeness": data_completeness,
                "alert_status_counts": {
                    "unhandled": len(unhandled),
                    "acknowledged": sum(1 for alert in alerts if alert.get("acknowledged_at")),
                    "processing": sum(1 for alert in alerts if _text(alert.get("ack_disposition")).lower() in {"watching", "later", "escalate"}),
                    "closed": sum(1 for alert in alerts if _text(alert.get("ack_disposition")).lower() in {"resolved", "accepted", "false_positive", "ignored"}),
                },
                "latest_handler": latest_handled.get("ack_actor") if latest_handled else "",
                "latest_handled_at": latest_handled.get("acknowledged_at") if latest_handled else None,
                "latest_alert_title": _alert_title(alerts[0]) if alerts else "",
            }
        )
    rows.sort(key=lambda item: (-int(item.get("priority_score") or 0), _text(item.get("bed"))))
    return serialize_doc(rows)


async def build_clinical_summary(db: Any, patient_id: str, *, hours: int = 24) -> dict[str, Any] | None:
    try:
        oid = ObjectId(str(patient_id))
    except Exception:
        return None
    patient = await db.col("patient").find_one({"_id": oid})
    if not patient:
        return None
    pid = str(oid)
    since = _now() - timedelta(hours=max(1, min(int(hours or 24), 72)))
    alerts = [
        doc
        async for doc in db.col("alert_records")
        .find({"patient_id": {"$in": [pid, oid]}, "created_at": {"$gte": since}})
        .sort("created_at", -1)
        .limit(80)
    ]
    unhandled = [alert for alert in alerts if _is_unhandled(alert)]
    severe_count = sum(1 for alert in alerts if _text(alert.get("severity")).lower() in {"critical", "high"})
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alert in unhandled or alerts:
        grouped[_alert_key(alert)].append(alert)
    top_problems = []
    for idx, group in enumerate(sorted(grouped.values(), key=lambda rows: max(SEVERITY_RANK.get(_text(row.get("severity")).lower(), 1) for row in rows), reverse=True)[:3], start=1):
        latest = group[0]
        evidence = _alert_evidence(latest)
        top_problems.append(
            {
                "rank": idx,
                "problem": _alert_title(latest),
                "evidence": evidence or ["触发依据不足，请查看原始预警详情"],
                "risk": _text(latest.get("severity")).lower() or "warning",
                "suggestions": _alert_suggestion(latest),
                "status": "待处理" if _is_unhandled(latest) else "已确认",
                "review_time": latest.get("review_due_at") or latest.get("recheck_due_at"),
                "alert_id": str(latest.get("_id") or ""),
            }
        )
    if not top_problems:
        top_problems = [
            {
                "rank": 1,
                "problem": "暂无未处理高危问题",
                "evidence": ["近窗口内未检出需要立即闭环的预警"],
                "risk": "unknown",
                "suggestions": ["继续常规监护", "确认关键数据是否完整"],
                "status": "观察",
                "review_time": None,
            }
        ]
    worsening_indicators = []
    for alert in alerts[:12]:
        title = _alert_title(alert)
        if _contains_any(title, ["升高", "下降", "恶化", "低", "高", "worsen", "trend"]):
            worsening_indicators.append(
                {
                    "name": _text(alert.get("parameter") or title),
                    "direction": "up" if _contains_any(title, ["升高", "高", "up"]) else "down" if _contains_any(title, ["下降", "低", "down"]) else "change",
                    "from": None,
                    "to": alert.get("value"),
                    "unit": "",
                    "time": alert.get("created_at"),
                    "source": "alert_records",
                }
            )
    pending_tasks = []
    for alert in unhandled[:6]:
        pending_tasks.append(
            {
                "title": f"处理{_alert_title(alert)}",
                "action": "确认处置并设置复评",
                "due_at": alert.get("review_due_at") or alert.get("created_at"),
                "source": "alert",
                "alert_id": str(alert.get("_id") or ""),
            }
        )
    handled = [alert for alert in alerts if alert.get("acknowledged_at")]
    summary_lines = [
        f"新发预警：{len(alerts)} 条，其中严重 {severe_count} 条",
        f"主要问题：{'、'.join(item['problem'] for item in top_problems[:3])}",
        f"已处理事项：{len(handled)} 条预警已确认",
        f"待处理事项：{len(unhandled)} 条预警需要闭环",
    ]
    return serialize_doc(
        {
            "patient": {
                "patient_id": pid,
                "bed": _patient_bed(patient),
                "name": _patient_name(patient),
                "diagnosis": patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis"),
            },
            "hours": hours,
            "summary": "\n".join(summary_lines),
            "top_problems": top_problems,
            "worsening_indicators": worsening_indicators[:8],
            "pending_tasks": pending_tasks,
            "unhandled_alerts": [serialize_doc(alert) for alert in unhandled[:10]],
            "safety_notice": "以上为系统辅助摘要，不能替代责任医生诊疗决策；高风险处置需床旁确认。",
        }
    )
