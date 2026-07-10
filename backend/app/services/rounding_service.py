from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bson import ObjectId

from app import runtime
from app.services.ai_prompt_templates import (
    ROUNDING_FOCUS_PROMPT_VERSION,
    build_rounding_focus_prompts,
    extract_json_object,
)
from app.services.audit_service import source_hash, write_ai_generation_log, write_audit_log
from app.services.llm_runtime import call_llm_chat
from app.utils.patient_helpers import calculate_age, patient_his_pid, research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

logger = logging.getLogger("icu-alert")

EXPORT_DIR = Path("backend/exports/rounding")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_LABELS = {
    "neuro": "神经系统",
    "respiratory": "呼吸系统",
    "circulation": "循环系统",
    "renal": "肾脏/液体平衡",
    "infection": "感染/抗感染",
    "nutrition": "营养/代谢",
    "coagulation": "凝血/血液",
    "others": "其他重要事件",
}

SEVERITY_RANK = {"low": 1, "info": 1, "warning": 2, "medium": 2, "high": 3, "critical": 4}
EVENT_TYPE_LABELS = {
    "alert": "预警",
    "lab": "检验",
    "medication": "用药",
    "nursing_event": "护理/处置",
}


def _patient_name(patient: dict[str, Any]) -> str:
    name = str(patient.get("name") or patient.get("hisName") or "").strip()
    if not name:
        return "未命名患者"
    return name


def _diagnosis(patient: dict[str, Any]) -> str:
    return str(
        patient.get("clinicalDiagnosis")
        or patient.get("admissionDiagnosis")
        or patient.get("hisDiagnose")
        or "暂无诊断"
    )


def _risk_from_alerts(alerts: list[dict[str, Any]]) -> str:
    max_rank = 0
    for alert in alerts:
        max_rank = max(max_rank, SEVERITY_RANK.get(str(alert.get("severity") or "").lower(), 0))
    if max_rank >= 4:
        return "critical"
    if max_rank == 3:
        return "high"
    if max_rank == 2:
        return "medium"
    return "low"


def _time_value(doc: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if doc.get(key) is not None:
            return doc.get(key)
    return None


async def _patient_or_none(patient_id: str) -> dict[str, Any] | None:
    oid = safe_oid(patient_id)
    query: dict[str, Any] = {"_id": oid} if oid is not None else {"_id": patient_id}
    return await runtime.db.col("patient").find_one(query)


def _append_department_scope(query: dict[str, Any], *, department: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    dept_name = str(department or "").strip()
    dept_code_text = str(dept_code or "").strip()
    if dept_name and not dept_code_text and dept_name.isdigit():
        dept_code_text = dept_name
        dept_name = ""
    if dept_name and dept_code_text and (dept_name == dept_code_text or dept_name.isdigit()):
        dept_name = ""
    clauses = [query]
    if dept_code_text:
        clauses.append({"deptCode": dept_code_text})
    if dept_name:
        clauses.append({"$or": [{"hisDept": dept_name}, {"dept": dept_name}]})
    return {"$and": clauses} if len(clauses) > 1 else query


async def list_rounding_patients(limit: int = 200, department: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    query = research_patient_scope_query("in_dept")
    query = _append_department_scope(query, department=department, dept_code=dept_code)
    cursor = runtime.db.col("patient").find(query).sort("hisBed", 1).limit(limit)
    rows: list[dict[str, Any]] = []
    async for patient in cursor:
        pid = str(patient.get("_id"))
        alerts = [
            doc async for doc in runtime.db.col("alert_records")
            .find({"patient_id": {"$in": [pid, patient.get("_id")]}}, {"severity": 1, "created_at": 1})
            .sort("created_at", -1)
            .limit(20)
        ]
        rows.append(
            {
                "patient_id": pid,
                "bed_no": patient.get("hisBed") or patient.get("bed") or "",
                "name": _patient_name(patient),
                "age": patient.get("age") or calculate_age(patient.get("birthday")) or patient.get("hisAge") or "",
                "diagnosis": _diagnosis(patient),
                "risk_level": _risk_from_alerts(alerts),
                "latest_alert_at": alerts[0].get("created_at") if alerts else None,
                "department": patient.get("hisDept") or patient.get("dept") or "",
                "dept_code": patient.get("deptCode") or "",
                "data_source": "patient+alert_records",
            }
        )
    return {
        "patients": serialize_doc(rows),
        "generated_at": serialize_doc(datetime.now()),
        "scope": {
            "patient_scope": "in_dept",
            "department": str(department or "").strip() or None,
            "dept_code": str(dept_code or "").strip() or None,
            "patient_count": len(rows),
        },
    }


async def _collect_alerts(pid: str, since: datetime) -> list[dict[str, Any]]:
    cursor = runtime.db.col("alert_records").find(
        {"patient_id": {"$in": [pid, safe_oid(pid)]}, "created_at": {"$gte": since}},
        {"name": 1, "alert_type": 1, "category": 1, "severity": 1, "message": 1, "value": 1, "extra": 1, "created_at": 1},
    ).sort("created_at", -1).limit(80)
    return [serialize_doc(doc) async for doc in cursor]


async def _collect_labs(patient: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    his_pid = patient_his_pid(patient)
    if not his_pid:
        return []
    cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(
        {"hisPid": his_pid, "$or": [{"authTime": {"$gte": since}}, {"reportTime": {"$gte": since}}, {"time": {"$gte": since}}]},
        {"itemName": 1, "itemCnName": 1, "result": 1, "resultValue": 1, "value": 1, "unit": 1, "authTime": 1, "reportTime": 1, "time": 1, "resultFlag": 1},
    ).sort("authTime", -1).limit(300)
    rows = []
    async for doc in cursor:
        rows.append(
            serialize_doc(
                {
                    "name": doc.get("itemCnName") or doc.get("itemName"),
                    "value": doc.get("result") or doc.get("resultValue") or doc.get("value"),
                    "unit": doc.get("unit") or "",
                    "flag": doc.get("resultFlag") or "",
                    "time": _time_value(doc, "authTime", "reportTime", "time"),
                }
            )
        )
    return rows


async def _collect_drugs(patient: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    his_pid = patient_his_pid(patient)
    if not his_pid:
        return []
    rows: list[dict[str, Any]] = []
    for col_name in ("drugExe",):
        cursor = runtime.db.col(col_name).find(
            {"pid": str(patient.get("_id")), "$or": [{"executeTime": {"$gte": since}}, {"startTime": {"$gte": since}}, {"orderTime": {"$gte": since}}]},
            {"drugName": 1, "orderName": 1, "dose": 1, "doseUnit": 1, "route": 1, "frequency": 1, "executeTime": 1, "startTime": 1, "orderTime": 1, "status": 1},
        ).sort("executeTime", -1).limit(80)
        async for doc in cursor:
            rows.append(serialize_doc({"name": doc.get("drugName") or doc.get("orderName"), "dose": doc.get("dose"), "route": doc.get("route"), "frequency": doc.get("frequency"), "time": _time_value(doc, "executeTime", "startTime", "orderTime"), "status": doc.get("status")}))
    if rows:
        return rows[:80]
    cursor = runtime.db.dc_col("VI_ICU_ZYYZ").find(
        {"pid": his_pid, "orderTime": {"$gte": since}},
        {"orderName": 1, "spec": 1, "exeMethod": 1, "freq": 1, "orderTime": 1, "orderType": 1},
    ).sort("orderTime", -1).limit(80)
    async for doc in cursor:
        rows.append(serialize_doc({"name": doc.get("orderName"), "dose": doc.get("spec"), "route": doc.get("exeMethod"), "frequency": doc.get("freq"), "time": doc.get("orderTime"), "status": doc.get("orderType")}))
    return rows


async def _collect_bedside_events(pid: str, since: datetime) -> list[dict[str, Any]]:
    keywords = ["护理", "吸痰", "翻身", "俯卧", "管路", "气囊", "入量", "出量", "营养", "感染", "医嘱", "处置"]
    cursor = runtime.db.col("bedside").find(
        {"pid": pid, "time": {"$gte": since}},
        {"time": 1, "code": 1, "strVal": 1, "value": 1, "fVal": 1, "intVal": 1},
    ).sort("time", -1).limit(800)
    rows = []
    async for doc in cursor:
        text = " ".join(str(doc.get(k) or "") for k in ("code", "strVal", "value")).strip()
        if any(k.lower() in text.lower() for k in keywords):
            rows.append(serialize_doc({"time": doc.get("time"), "code": doc.get("code"), "text": text[:240], "source": "bedside"}))
    return rows[:80]


async def _collect_vitals(pid: str, since: datetime) -> list[dict[str, Any]]:
    codes = {
        "param_HR": "HR",
        "param_resp": "RR",
        "param_spo2": "SpO2",
        "param_T": "T",
        "param_ibp_m": "MAP",
        "param_nibp_m": "MAP",
    }
    rows = []
    for code, label in codes.items():
        try:
            points = await runtime.alert_engine._get_param_series_by_pid(pid, code, since, limit=600)
        except Exception:
            points = []
        values = [p.get("value") for p in points if isinstance(p.get("value"), (int, float))]
        if not values:
            continue
        rows.append({"label": label, "code": code, "first": values[0], "latest": values[-1], "min": min(values), "max": max(values), "points": len(values)})
    return serialize_doc(rows)


def _system_bucket(event: dict[str, Any]) -> str:
    text = json.dumps(event, ensure_ascii=False).lower()
    if any(k in text for k in ["gcs", "rass", "谵妄", "意识", "神经", "脑"]):
        return "neuro"
    if any(k in text for k in ["vent", "fio2", "peep", "spo2", "呼吸", "气道", "吸痰", "肺", "sbt"]):
        return "respiratory"
    if any(k in text for k in ["map", "血压", "去甲", "休克", "循环", "心率"]):
        return "circulation"
    if any(k in text for k in ["尿", "出量", "入量", "液体", "crrt", "肌酐", "肾"]):
        return "renal"
    if any(k in text for k in ["感染", "抗菌", "抗生素", "培养", "pct", "wbc", "脓毒"]):
        return "infection"
    if any(k in text for k in ["营养", "白蛋白", "血糖", "代谢", "肠内"]):
        return "nutrition"
    if any(k in text for k in ["凝血", "血小板", "出血", "plt", "inr", "aptt"]):
        return "coagulation"
    return "others"


def _event_rank(row: dict[str, Any]) -> int:
    severity = str(row.get("severity") or (row.get("evidence") or {}).get("severity") or "").lower()
    rank = SEVERITY_RANK.get(severity, 0)
    event_type = str(row.get("type") or "").lower()
    if event_type == "alert":
        rank += 2
    if event_type in {"lab", "medication"}:
        rank += 1
    return rank


def _short_evidence(row: dict[str, Any]) -> str:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    title = str(row.get("title") or evidence.get("name") or evidence.get("itemName") or evidence.get("code") or "事件").strip()
    value = evidence.get("value") or evidence.get("result") or evidence.get("dose") or evidence.get("message") or ""
    unit = evidence.get("unit") or evidence.get("doseUnit") or ""
    time_text = row.get("time") or evidence.get("created_at") or evidence.get("time") or ""
    detail = f"{title}"
    if value not in ("", None):
        detail += f"：{value}{unit}"
    if time_text:
        detail += f"（{time_text}）"
    return detail[:220]


def _build_system_assessments(systems: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    assessments: list[dict[str, Any]] = []
    for key, label in SYSTEM_LABELS.items():
        rows = sorted(systems.get(key) or [], key=_event_rank, reverse=True)
        if not rows:
            assessments.append(
                {
                    "system": key,
                    "label": label,
                    "status": "stable",
                    "headline": f"{label}暂无突出新增事件",
                    "evidence": [],
                    "action_hint": "查房时结合床旁体征和病程记录常规复核。",
                }
            )
            continue
        max_rank = max(_event_rank(row) for row in rows)
        status = "critical" if max_rank >= 6 else "high" if max_rank >= 4 or len(rows) >= 8 else "watch"
        top = rows[:3]
        first = top[0]
        assessments.append(
            {
                "system": key,
                "label": label,
                "status": status,
                "headline": f"{label}过去窗口内有 {len(rows)} 条相关记录，重点关注：{first.get('title') or EVENT_TYPE_LABELS.get(str(first.get('type')), '事件')}",
                "evidence": [_short_evidence(row) for row in top],
                "action_hint": "建议查房时核对趋势、治疗反应和是否需要补充床旁评估；仅作决策支持提示。",
            }
        )
    return assessments


def _build_overnight_digest(
    *,
    hours: int,
    alerts: list[dict[str, Any]],
    labs: list[dict[str, Any]],
    drugs: list[dict[str, Any]],
    vitals: list[dict[str, Any]],
    bedside: list[dict[str, Any]],
    data_gaps: list[str],
) -> dict[str, Any]:
    high_alerts = [row for row in alerts if SEVERITY_RANK.get(str(row.get("severity") or "").lower(), 0) >= 3]
    abnormal_labs = [row for row in labs if str(row.get("flag") or "").strip()]
    vital_text = []
    for row in vitals[:6]:
        vital_text.append(
            f"{row.get('label')} {row.get('first')} -> {row.get('latest')}，范围 {row.get('min')} - {row.get('max')}"
        )
    summary_lines = [
        f"过去 {hours} 小时共捕获 {len(alerts)} 条预警、{len(labs)} 条检验、{len(drugs)} 条用药/医嘱记录、{len(bedside)} 条护理/处置记录。",
    ]
    if high_alerts:
        summary_lines.append(f"其中高危及以上预警 {len(high_alerts)} 条，建议晨会优先复核。")
    if abnormal_labs:
        summary_lines.append(f"检验异常/带标记项目 {len(abnormal_labs)} 条，需结合趋势判断临床意义。")
    if not high_alerts and not abnormal_labs:
        summary_lines.append("未见明显高危预警或带标记检验，但仍需结合床旁病情和数据完整性确认。")
    return {
        "headline": " ".join(summary_lines),
        "alerts": [str(row.get("name") or row.get("message") or row.get("alert_type") or "预警事件")[:180] for row in alerts[:6]],
        "vitals": vital_text,
        "labs": [f"{row.get('name')} {row.get('value') or ''}{row.get('unit') or ''} {row.get('flag') or ''}".strip() for row in labs[:8]],
        "medications": [f"{row.get('name')} {row.get('dose') or ''} {row.get('route') or ''} {row.get('frequency') or ''}".strip() for row in drugs[:8]],
        "nursing": [str(row.get("text") or row.get("code") or "护理/处置记录")[:180] for row in bedside[:8]],
        "data_gaps": data_gaps,
    }


def _build_clinical_priorities(
    systems: dict[str, list[dict[str, Any]]],
    vitals: list[dict[str, Any]],
    data_gaps: list[str],
) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = []
    ranked_systems = sorted(
        [(key, rows) for key, rows in systems.items() if rows],
        key=lambda item: (max(_event_rank(row) for row in item[1]), len(item[1])),
        reverse=True,
    )
    for key, rows in ranked_systems[:5]:
        top = sorted(rows, key=_event_rank, reverse=True)[:3]
        max_rank = max(_event_rank(row) for row in top)
        priorities.append(
            {
                "title": f"{SYSTEM_LABELS.get(key, key)}重点问题",
                "risk_level": "high" if max_rank >= 4 else "medium",
                "why_it_matters": f"该系统过去窗口内聚合 {len(rows)} 条事件，可能影响今日治疗策略和交班重点。",
                "evidence": [_short_evidence(row) for row in top],
                "rounding_questions": [
                    "当前趋势是否仍在进展，还是已经对治疗有反应？",
                    "是否存在需要床旁立即确认的缺失数据或矛盾数据？",
                    "今日目标是否需要在医嘱、护理或治疗计划中同步更新？",
                ],
            }
        )
    if vitals and len(priorities) < 5:
        priorities.append(
            {
                "title": "生命体征趋势复核",
                "risk_level": "medium",
                "why_it_matters": "连续监护趋势比单点数值更适合查房前快速判断过夜变化。",
                "evidence": [f"{row.get('label')} 最新 {row.get('latest')}，范围 {row.get('min')} - {row.get('max')}" for row in vitals[:4]],
                "rounding_questions": ["是否存在夜间波动峰值？", "波动是否与用药、操作或呼吸机调整相关？"],
            }
        )
    if data_gaps:
        priorities.append(
            {
                "title": "数据完整性补核",
                "risk_level": "low",
                "why_it_matters": "查房报告存在数据缺口时，系统结论需降低确信度。",
                "evidence": data_gaps[:5],
                "rounding_questions": ["监护、LIS、医嘱、护理记录是否已完成同步？", "是否需要人工补录关键事件？"],
            }
        )
    return priorities[:6]


def _build_checklist(summary: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = list((summary.get("data_quality") or {}).get("data_gaps") or [])
    rows = [
        {"label": "核对高危预警是否已处理", "status": "todo" if summary.get("key_events") else "ok", "source": "alert_records"},
        {"label": "复核生命体征夜间趋势和峰谷值", "status": "todo" if summary.get("trend_highlights") else "missing", "source": "bedside/device trend"},
        {"label": "确认新开/停用/调整医嘱", "status": "todo" if summary.get("medication_changes") else "missing", "source": "drugExe/VI_ICU_ZYYZ"},
        {"label": "确认护理操作、管路和出入量记录", "status": "todo" if summary.get("nursing_events") else "missing", "source": "bedside"},
    ]
    for gap in gaps[:4]:
        rows.append({"label": gap, "status": "missing", "source": "data_quality"})
    return rows


def _build_rounding_completion(summary: dict[str, Any]) -> dict[str, Any]:
    checklist = summary.get("rounding_checklist") or []
    tasks: list[dict[str, Any]] = []
    for item in checklist:
        status = str(item.get("status") or "")
        if status in {"todo", "missing"}:
            tasks.append(
                {
                    "title": item.get("label") or "查房复核",
                    "source": item.get("source") or "",
                    "priority": "high" if status == "todo" else "medium",
                    "action": "查房确认",
                }
            )
    for priority in summary.get("clinical_priorities") or []:
        tasks.append(
            {
                "title": priority.get("title") or "优先问题",
                "source": "clinical_priority",
                "priority": priority.get("risk_level") or "medium",
                "action": "同步今日计划",
            }
        )
    evidence_blocks = [
        bool(summary.get("key_events")),
        bool(summary.get("trend_highlights")),
        bool(summary.get("medication_changes")),
        bool(summary.get("nursing_events")),
        bool(summary.get("clinical_priorities")),
    ]
    complete = sum(1 for item in evidence_blocks if item)
    data_gaps = (summary.get("data_quality") or {}).get("data_gaps") or []
    data_quality = max(0, round((1 - len(data_gaps) / 4) * 100))
    percent = round((complete / len(evidence_blocks)) * 70 + data_quality * 0.3)
    return {
        "percent": max(0, min(100, percent)),
        "status": "ready" if percent >= 90 else "open",
        "label": f"{len(tasks)} 个查房动作",
        "data_quality": {"percent": data_quality, "gaps": data_gaps[:5]},
        "tasks": tasks[:8],
        "chips": [
            {"label": "预警", "value": len(summary.get("key_events") or [])},
            {"label": "趋势", "value": len(summary.get("trend_highlights") or [])},
            {"label": "医嘱", "value": len(summary.get("medication_changes") or [])},
            {"label": "护理", "value": len(summary.get("nursing_events") or [])},
        ],
    }


async def build_rounding_summary(patient_id: str, hours: int = 24) -> dict[str, Any]:
    hours = min(max(int(hours or 24), 8), 48)
    patient = await _patient_or_none(patient_id)
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    pid = str(patient.get("_id"))
    since = datetime.now() - timedelta(hours=hours)
    alerts = await _collect_alerts(pid, since)
    labs = await _collect_labs(patient, since)
    drugs = await _collect_drugs(patient, since)
    vitals = await _collect_vitals(pid, since)
    bedside = await _collect_bedside_events(pid, since)

    systems: dict[str, list[dict[str, Any]]] = {key: [] for key in SYSTEM_LABELS}
    for row in alerts:
        systems[_system_bucket(row)].append({"type": "alert", "title": row.get("name") or row.get("alert_type"), "severity": row.get("severity"), "time": row.get("created_at"), "evidence": row})
    for row in labs[:60]:
        systems[_system_bucket(row)].append({"type": "lab", "title": row.get("name"), "time": row.get("time"), "evidence": row})
    for row in drugs[:40]:
        systems[_system_bucket(row)].append({"type": "medication", "title": row.get("name"), "time": row.get("time"), "evidence": row})
    for row in bedside[:50]:
        systems[_system_bucket(row)].append({"type": "nursing_event", "title": row.get("code") or "护理/处置记录", "time": row.get("time"), "evidence": row})

    data_gaps = []
    if not labs:
        data_gaps.append("过去时间窗内未检索到 LIS 检验明细")
    if not drugs:
        data_gaps.append("过去时间窗内未检索到用药/医嘱调整")
    if not vitals:
        data_gaps.append("过去时间窗内未检索到床旁生命体征趋势")
    if not bedside:
        data_gaps.append("过去时间窗内护理/处置文本记录不足")

    overnight_digest = _build_overnight_digest(
        hours=hours,
        alerts=alerts,
        labs=labs,
        drugs=drugs,
        vitals=vitals,
        bedside=bedside,
        data_gaps=data_gaps,
    )
    system_assessments = _build_system_assessments(systems)
    clinical_priorities = _build_clinical_priorities(systems, vitals, data_gaps)
    summary = {
        "patient_id": pid,
        "bed_no": patient.get("hisBed") or patient.get("bed") or "",
        "name": _patient_name(patient),
        "age": patient.get("age") or calculate_age(patient.get("birthday")) or patient.get("hisAge") or "",
        "diagnosis": _diagnosis(patient),
        "time_range_hours": hours,
        "generated_at": datetime.now(),
        "risk_level": _risk_from_alerts(alerts),
        "systems": systems,
        "overnight_digest": overnight_digest,
        "system_assessments": system_assessments,
        "clinical_priorities": clinical_priorities,
        "key_events": alerts[:20],
        "trend_highlights": vitals,
        "medication_changes": drugs[:40],
        "nursing_events": bedside[:40],
        "ai_focus_points": [],
        "data_quality": {
            "source": "real_data_with_compatibility_fallback",
            "is_mock": False,
            "data_gaps": data_gaps,
            "source_collections": ["patient", "alert_records", "score", "bedside", "deviceCap", "VI_ICU_EXAM_ITEM", "VI_ICU_ZYYZ"],
        },
    }
    summary["rounding_checklist"] = _build_checklist(summary)
    summary["completion"] = _build_rounding_completion(summary)
    return {"code": 0, "summary": serialize_doc(summary)}


def _fallback_focus_points(summary: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = summary.get("key_events") if isinstance(summary, dict) else []
    points = []
    for alert in (alerts or [])[:3]:
        points.append(
            {
                "title": str(alert.get("name") or alert.get("alert_type") or "预警事件需复核"),
                "risk_level": "high" if str(alert.get("severity")) in {"high", "critical"} else "medium",
                "evidence": [str(alert.get("message") or alert.get("name") or alert.get("alert_type") or "存在预警记录")],
                "suggested_attention": "结合床旁状态、检验趋势和治疗反应复核风险。",
                "uncertainty": "当前为规则兜底生成，未调用大模型。",
            }
        )
    if not points:
        points.append(
            {
                "title": "数据完整性需确认",
                "risk_level": "low",
                "evidence": list((summary.get("data_quality") or {}).get("data_gaps") or ["未发现突出预警事件"]),
                "suggested_attention": "查房前确认监护、检验、用药和护理记录是否同步完整。",
                "uncertainty": "证据不足，仅提示补充核对。",
            }
        )
    return points[:5]


async def generate_ai_focus_points(patient_id: str, hours: int = 24, actor: str = "anonymous") -> dict[str, Any]:
    base = await build_rounding_summary(patient_id, hours)
    if base.get("code") != 0:
        return base
    summary = base["summary"]
    system_prompt, user_prompt = build_rounding_focus_prompts(summary)
    cfg = runtime.config
    result: dict[str, Any]
    model = str(getattr(cfg, "llm_fast_model", "") or getattr(cfg.settings, "LLM_MODEL", "") or "unknown")
    try:
        llm = await call_llm_chat(
            cfg=cfg,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=0.1,
            max_tokens=1200,
            timeout_seconds=45,
        )
        model = str(llm.get("model") or model)
        parsed = extract_json_object(str(llm.get("text") or ""))
        focus_points = parsed.get("focus_points") if isinstance(parsed.get("focus_points"), list) else []
        result = {
            "focus_points": focus_points[:5] or _fallback_focus_points(summary),
            "disclaimer": parsed.get("disclaimer") or "仅供临床决策支持，不替代医生判断",
            "degraded": False,
            "model": model,
            "prompt_version": ROUNDING_FOCUS_PROMPT_VERSION,
            "generated_at": datetime.now(),
        }
        await write_ai_generation_log(
            runtime.db,
            module="rounding",
            action="ai_focus_points",
            model=model,
            prompt_version=ROUNDING_FOCUS_PROMPT_VERSION,
            source_data_summary=summary,
            result=result,
            actor=actor,
            patient_id=patient_id,
            success=True,
        )
    except Exception as exc:
        logger.warning("rounding ai focus fallback patient_id=%s error=%s", patient_id, exc)
        result = {
            "focus_points": _fallback_focus_points(summary),
            "disclaimer": "仅供临床决策支持，不替代医生判断",
            "degraded": True,
            "error": str(exc),
            "model": model,
            "prompt_version": ROUNDING_FOCUS_PROMPT_VERSION,
            "generated_at": datetime.now(),
        }
        await write_ai_generation_log(
            runtime.db,
            module="rounding",
            action="ai_focus_points",
            model=model,
            prompt_version=ROUNDING_FOCUS_PROMPT_VERSION,
            source_data_summary=summary,
            result=result,
            actor=actor,
            patient_id=patient_id,
            success=False,
            metadata={"error": str(exc)},
        )
    return {"code": 0, "insights": serialize_doc(result)}


def _summary_to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# ICU 智能查房报告 / Rounding Sheet",
        "",
        f"- 患者：{summary.get('name')}（{summary.get('bed_no')}床）",
        f"- 诊断：{summary.get('diagnosis')}",
        f"- 时间范围：过去 {summary.get('time_range_hours')} 小时",
        f"- 当前风险：{summary.get('risk_level')}",
        f"- 生成时间：{summary.get('generated_at')}",
        "",
        "> 仅供临床决策支持，不替代医生判断。",
        "",
        "## 关键趋势",
    ]
    digest = summary.get("overnight_digest") or {}
    if digest.get("headline"):
        lines.extend(["", "## 过夜摘要", str(digest.get("headline"))])
    priorities = summary.get("clinical_priorities") or []
    if priorities:
        lines.extend(["", "## 今日优先关注问题"])
        for item in priorities:
            lines.append(f"- {item.get('title')}（{item.get('risk_level')}）：{item.get('why_it_matters')}")
            for evidence in item.get("evidence") or []:
                lines.append(f"  - 证据：{evidence}")
    for item in summary.get("trend_highlights") or []:
        lines.append(f"- {item.get('label')}: {item.get('first')} -> {item.get('latest')}，范围 {item.get('min')} - {item.get('max')}")
    lines.append("")
    lines.append("## 器官系统")
    systems = summary.get("systems") or {}
    for key, label in SYSTEM_LABELS.items():
        lines.append(f"### {label}")
        rows = systems.get(key) or []
        if not rows:
            lines.append("- 暂无重点事件")
            continue
        for row in rows[:20]:
            lines.append(f"- [{row.get('type')}] {row.get('title') or '事件'} - {row.get('time') or '时间未知'}")
    lines.append("")
    lines.append("## AI 关注点")
    for point in summary.get("ai_focus_points") or []:
        lines.append(f"- {point.get('title')}（{point.get('risk_level')}）：{point.get('suggested_attention')}")
    return "\n".join(lines).strip() + "\n"


async def export_rounding_report(payload: dict[str, Any], actor: str = "anonymous") -> dict[str, Any]:
    patient_ids = [str(x).strip() for x in payload.get("patient_ids") or [] if str(x).strip()]
    hours = int(payload.get("hours") or 24)
    fmt = str(payload.get("format") or "markdown").lower()
    if not patient_ids:
        return {"code": 400, "message": "patient_ids 不能为空"}
    summaries = []
    for pid in patient_ids[:100]:
        item = await build_rounding_summary(pid, hours)
        if item.get("code") == 0:
            summaries.append(item["summary"])
    if not summaries:
        return {"code": 404, "message": "未生成任何查房报告"}
    task_id = str(uuid.uuid4())
    suffix = "html" if fmt == "html" else "md"
    file_path = EXPORT_DIR / f"rounding_{task_id}.{suffix}"
    content = "\n\n---\n\n".join(_summary_to_markdown(summary) for summary in summaries)
    if fmt == "html":
        body = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>\n")
        content = f"<!doctype html><html><head><meta charset='utf-8'><title>Rounding Sheet</title></head><body>{body}</body></html>"
    file_path.write_text(content, encoding="utf-8")
    doc = {
        "task_id": task_id,
        "status": "completed",
        "format": fmt,
        "file_path": str(file_path),
        "patient_count": len(summaries),
        "hours": hours,
        "created_by": actor,
        "created_at": datetime.now(),
        "source_data_hash": source_hash(json.dumps(summaries, ensure_ascii=False, default=str)),
    }
    await runtime.db.col("rounding_export_tasks").insert_one(doc)
    await write_audit_log(runtime.db, action="export_rounding_report", module="rounding", actor=actor, target_type="rounding_export", target_id=task_id, detail={"patient_count": len(summaries), "format": fmt})
    return {"code": 0, "task": serialize_doc({k: v for k, v in doc.items() if k != "file_path"})}


async def list_rounding_versions(patient_id: str, limit: int = 20) -> dict[str, Any]:
    cursor = runtime.db.col("rounding_report_versions").find(
        {"patient_id": str(patient_id)}
    ).sort([("version_no", -1), ("created_at", -1)]).limit(max(1, min(int(limit or 20), 100)))
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"versions": rows}


async def save_rounding_version(patient_id: str, payload: dict[str, Any], actor: str = "anonymous") -> dict[str, Any]:
    now = datetime.now()
    latest = await runtime.db.col("rounding_report_versions").find_one(
        {"patient_id": str(patient_id)},
        sort=[("version_no", -1)],
    )
    version_no = int((latest or {}).get("version_no") or 0) + 1
    content = str(payload.get("content") or "").strip()
    if not content:
        return {"code": 400, "message": "content 不能为空"}
    doc = {
        "version_id": str(uuid.uuid4()),
        "patient_id": str(patient_id),
        "version_no": version_no,
        "status": str(payload.get("status") or "draft").strip() or "draft",
        "source": str(payload.get("source") or "doctor_edit").strip() or "doctor_edit",
        "content": content,
        "content_hash": source_hash(content),
        "summary_snapshot": payload.get("summary_snapshot") or {},
        "created_by": actor,
        "updated_by": actor,
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("rounding_report_versions").insert_one(doc)
    await write_audit_log(
        runtime.db,
        action="save_rounding_version",
        module="rounding",
        actor=actor,
        target_type="rounding_report_version",
        target_id=doc["version_id"],
        detail={"patient_id": patient_id, "version_no": version_no, "status": doc["status"]},
    )
    return {"code": 0, "version": serialize_doc(doc)}


async def confirm_rounding_version(patient_id: str, version_id: str, payload: dict[str, Any], actor: str = "anonymous") -> dict[str, Any]:
    now = datetime.now()
    doc = await runtime.db.col("rounding_report_versions").find_one(
        {"patient_id": str(patient_id), "version_id": str(version_id)}
    )
    if not doc:
        return {"code": 404, "message": "版本不存在"}
    update = {
        "status": str(payload.get("status") or "confirmed").strip() or "confirmed",
        "confirmed_by": actor,
        "confirmed_at": now,
        "confirm_note": str(payload.get("note") or "").strip(),
        "updated_by": actor,
        "updated_at": now,
    }
    await runtime.db.col("rounding_report_versions").update_one(
        {"_id": doc["_id"]},
        {"$set": update},
    )
    updated = await runtime.db.col("rounding_report_versions").find_one({"_id": doc["_id"]})
    await write_audit_log(
        runtime.db,
        action="confirm_rounding_version",
        module="rounding",
        actor=actor,
        target_type="rounding_report_version",
        target_id=str(version_id),
        detail={"patient_id": patient_id, "status": update["status"]},
    )
    return {"code": 0, "version": serialize_doc(updated)}
