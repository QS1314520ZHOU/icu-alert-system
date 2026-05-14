from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Body, Query, Request

from app import runtime
from app.services.audit_service import normalize_actor, write_audit_log
from app.services.clinical_adoption_service import ClinicalAdoptionService
from app.services.rounding_service import build_rounding_summary, save_rounding_version
from app.utils.patient_helpers import admitted_patient_query
from app.utils.serialization import serialize_doc

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

MOBILE_SOURCE = "mobile_h5"


def _service() -> ClinicalAdoptionService:
    return ClinicalAdoptionService(runtime.db, alert_engine=runtime.alert_engine)


def _actor(request: Request, payload: dict[str, Any] | None = None) -> str:
    body = payload if isinstance(payload, dict) else {}
    return normalize_actor(
        body.get("actor"),
        request.headers.get("X-User-Id"),
        request.headers.get("x-operator-id"),
        request.headers.get("x-user-name"),
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _admitted_scope_query(dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    query: dict[str, Any] = admitted_patient_query()
    code = _text(dept_code)
    dept_text = _text(dept)
    clauses: list[dict[str, Any]] = []
    if code:
        code_values: list[Any] = [code]
        if code.isdigit():
            code_values.append(int(code))
        clauses.extend([
            {"deptCode": {"$in": code_values}},
            {"departmentCode": {"$in": code_values}},
            {"dept_code": {"$in": code_values}},
        ])
    if dept_text:
        clauses.extend([
            {"hisDept": dept_text},
            {"dept": dept_text},
            {"deptName": dept_text},
            {"department": dept_text},
            {"departmentName": dept_text},
        ])
    if clauses:
        return {"$and": [query, {"$or": clauses}]}
    return query


async def _resolve_mobile_account(user_name: str | None, dept_code: str | None = None, dept: str | None = None) -> dict[str, Any]:
    code = _text(dept_code)
    dept_text = _text(dept)
    if code or dept_text:
        return {"dept_code": code, "dept": dept_text}
    user = _text(user_name)
    if not user:
        return {}
    account = await runtime.db.col("account").find_one(
        {"$or": [{"userName": user}, {"username": user}, {"account": user}, {"loginName": user}, {"宸ュ彿": user}]},
        {"deptCode": 1, "departmentCode": 1, "dept_code": 1, "dept": 1, "deptName": 1, "departmentName": 1, "department": 1},
    )
    if not account:
        return {}
    return {
        "dept_code": _text(account.get("deptCode") or account.get("departmentCode") or account.get("dept_code")),
        "dept": _text(account.get("dept") or account.get("deptName") or account.get("departmentName") or account.get("department")),
    }


def _oid(value: Any) -> ObjectId | None:
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def _alert_doc(alert_id: str) -> dict[str, Any] | None:
    oid = _oid(alert_id)
    if not oid:
        return None
    return await runtime.db.col("alert_records").find_one({"_id": oid})


async def _patient_doc(patient_id: str | None) -> dict[str, Any] | None:
    oid = _oid(patient_id)
    if oid:
        return await runtime.db.col("patient").find_one({"_id": oid})
    text = _text(patient_id)
    if not text:
        return None
    return await runtime.db.col("patient").find_one({"$or": [{"hisPid": text}, {"patient_id": text}, {"hisBed": text}, {"bed": text}]})


def _patient_label(patient: dict[str, Any] | None, alert: dict[str, Any] | None = None) -> str:
    patient = patient or {}
    alert = alert or {}
    bed = patient.get("hisBed") or patient.get("bed") or alert.get("bed") or "--"
    name = patient.get("name") or patient.get("hisName") or alert.get("patient_name") or "未知患者"
    return f"{bed}床 {name}"


def _patient_display(patient: dict[str, Any] | None) -> dict[str, Any]:
    patient = patient or {}
    return {
        "patient_id": str(patient.get("_id") or patient.get("patient_id") or patient.get("hisPid") or ""),
        "bed": patient.get("hisBed") or patient.get("bed") or patient.get("bed_no") or "",
        "name": patient.get("name") or patient.get("hisName") or "",
        "sex": patient.get("hisSex") or patient.get("sex") or patient.get("gender") or "",
        "age": patient.get("age") or patient.get("hisAge") or "",
        "dept": patient.get("hisDept") or patient.get("dept") or patient.get("deptName") or "",
        "dept_code": patient.get("deptCode") or patient.get("dept_code") or patient.get("departmentCode") or "",
        "diagnosis": patient.get("clinicalDiagnosis")
        or patient.get("admissionDiagnosis")
        or patient.get("diagnosis")
        or patient.get("hisDiagnose")
        or patient.get("hisDiagnosis")
        or patient.get("chiefComplaint")
        or "",
    }


def _simple_alert_label(value: Any) -> str:
    text = _text(value).lower()
    labels = {
        "critical": "危急",
        "high": "高危",
        "warning": "预警",
        "medium": "中危",
        "low": "低危",
        "sepsis": "脓毒症风险",
        "shock": "休克风险",
        "hypoxemia": "低氧血症",
        "respiratory": "呼吸风险",
        "aki": "急性肾损伤",
        "renal": "肾功能异常",
        "lactate": "乳酸异常",
        "infection": "感染风险",
    }
    for key, label in labels.items():
        if key in text:
            return label
    return _text(value) or "临床风险"


async def _latest_patient_alerts(patient_id: str, limit: int = 5) -> list[dict[str, Any]]:
    keys: list[Any] = [patient_id]
    oid = _oid(patient_id)
    if oid:
        keys.append(oid)
    cursor = runtime.db.col("alert_records").find(
        {"patient_id": {"$in": keys}},
        {"name": 1, "alert_type": 1, "rule_id": 1, "category": 1, "severity": 1, "message": 1, "created_at": 1},
    ).sort("created_at", -1).limit(limit)
    return [serialize_doc(doc) async for doc in cursor]


def _severity_priority(severity: Any) -> str:
    value = _text(severity).lower()
    if value in {"critical", "high"}:
        return "high"
    if value in {"warning", "medium", "moderate"}:
        return "medium"
    return "low"


def _alert_type_text(alert: dict[str, Any] | None) -> str:
    alert = alert or {}
    values = [
        alert.get("alert_type"),
        alert.get("rule_id"),
        alert.get("category"),
        alert.get("name"),
        alert.get("parameter"),
    ]
    extra = alert.get("extra") if isinstance(alert.get("extra"), dict) else {}
    values.extend([extra.get("alert_type"), extra.get("rule_id"), extra.get("category")])
    return " ".join(_text(item).lower() for item in values if _text(item))


def _order_stub_items(alert: dict[str, Any]) -> list[dict[str, Any]]:
    text = _alert_type_text(alert)
    if any(key in text for key in ("sepsis", "shock", "lactate", "infection")):
        return [
            {"key": "lactate_recheck", "label": "乳酸复查", "category": "sepsis", "checked": True},
            {"key": "blood_culture_pair", "label": "血培养双套", "category": "sepsis", "checked": True},
            {"key": "empiric_antibiotics", "label": "经验性抗生素", "category": "sepsis", "checked": True},
            {"key": "crystalloid_30ml_kg_eval", "label": "30 mL/kg 晶体液评估", "category": "sepsis", "checked": True},
        ]
    if any(key in text for key in ("respiratory", "hypoxemia", "ards", "ventilator", "spo2", "oxygen")):
        return [
            {"key": "blood_gas_recheck", "label": "复查血气", "category": "respiratory", "checked": True},
            {"key": "oxygen_support_adjust", "label": "调整氧疗/呼吸机参数", "category": "respiratory", "checked": True},
            {"key": "airway_secretion_eval", "label": "评估气道分泌物", "category": "respiratory", "checked": True},
        ]
    if any(key in text for key in ("aki", "renal", "urine", "creatinine", "kidney")):
        return [
            {"key": "creatinine_electrolyte_recheck", "label": "复查肌酐/电解质", "category": "renal", "checked": True},
            {"key": "volume_status_eval", "label": "评估容量状态", "category": "renal", "checked": True},
            {"key": "urine_trend_record", "label": "记录尿量趋势", "category": "renal", "checked": True},
        ]
    return [
        {"key": "bedside_recheck", "label": "床旁复查", "category": "general", "checked": True},
        {"key": "clinical_eval", "label": "评估病情变化", "category": "general", "checked": True},
        {"key": "document_action", "label": "记录处置", "category": "general", "checked": True},
    ]


def _task_type_for_alert(alert: dict[str, Any], suffix: str) -> str:
    text = _alert_type_text(alert)
    if any(key in text for key in ("sepsis", "shock", "infection")):
        return f"sepsis_{suffix}"
    if any(key in text for key in ("respiratory", "hypoxemia", "ards", "ventilator")):
        return f"respiratory_{suffix}"
    if any(key in text for key in ("aki", "renal", "urine")):
        return f"renal_{suffix}"
    return f"general_{suffix}"


def _bundle_templates() -> list[dict[str, Any]]:
    return [
        {
            "bundle_type": "VAP",
            "title": "VAP Bundle",
            "items": [
                {"key": "head_up_30", "label": "床头抬高 30°"},
                {"key": "oral_care", "label": "口腔护理已做"},
                {"key": "sedation_weaning_eval", "label": "镇静唤醒/撤机评估"},
                {"key": "cuff_pressure_check", "label": "气囊压检查"},
            ],
        },
        {
            "bundle_type": "CRBSI",
            "title": "CRBSI Bundle",
            "items": [
                {"key": "catheter_necessity", "label": "导管必要性已评估"},
                {"key": "puncture_site_check", "label": "穿刺点观察"},
                {"key": "dressing_intact", "label": "敷料完整"},
                {"key": "aseptic_maintenance", "label": "无菌维护"},
            ],
        },
        {
            "bundle_type": "Sepsis1h",
            "title": "Sepsis 1h Bundle",
            "items": [
                {"key": "lactate", "label": "乳酸复查/已送检"},
                {"key": "blood_culture", "label": "血培养双套"},
                {"key": "antibiotics", "label": "抗生素评估/执行"},
                {"key": "fluid_vasopressor", "label": "液体复苏/升压药评估"},
            ],
        },
    ]


async def _scoped_patients(dept: str | None, dept_code: str | None, patient_id: str | None) -> list[dict[str, Any]]:
    query: dict[str, Any] = admitted_patient_query()
    if patient_id:
        oid = _oid(patient_id)
        if oid:
            query = {"$and": [query, {"_id": oid}]}
        else:
            query = {"$and": [query, {"$or": [{"hisPid": patient_id}, {"patient_id": patient_id}]}]}
    elif dept_code:
        query = {"$and": [query, {"deptCode": dept_code}]}
    elif dept:
        query = {"$and": [query, {"hisDept": dept}]}
    cursor = runtime.db.col("patient").find(query, {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "deptCode": 1, "hisDept": 1}).sort("hisBed", 1).limit(120)
    return [doc async for doc in cursor]


@router.post("/alerts/{alert_id}/sbar")
async def create_sbar(alert_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    actor = _actor(request, body)
    alert = await _alert_doc(alert_id)
    if not alert:
        return {"code": 404, "message": "告警不存在"}
    patient_id = _text(alert.get("patient_id"))
    patient = await _patient_doc(patient_id)
    handoff = {}
    if patient_id:
        try:
            handoff = await _service().handoff(patient_id, role="doctor", hours=24)
        except Exception:
            handoff = {}
    alert_title = alert.get("name") or alert.get("alert_type") or alert.get("rule_id") or "临床告警"
    summary = _text((handoff or {}).get("summary") or (handoff or {}).get("text") or "")
    sbar_text = "\n".join(
        [
            f"S 情况：{_patient_label(patient, alert)}出现{alert_title}，等级{alert.get('severity') or '关注'}。",
            f"B 背景：{patient.get('clinicalDiagnosis') or patient.get('admissionDiagnosis') or patient.get('diagnosis') or '暂无诊断摘要' if patient else '暂无诊断摘要'}。",
            f"A 评估：{summary or alert.get('explanation_text') or alert.get('message') or '请结合生命体征、化验和用药复核。'}",
            f"R 建议：{_text(body.get('note')) or '请二线/接收团队尽快评估并反馈处置。'}",
        ]
    )
    sbar_id = str(uuid.uuid4())
    doc = {
        "sbar_id": sbar_id,
        "alert_id": str(alert.get("_id")),
        "patient_id": patient_id or None,
        "target_type": _text(body.get("target_type")) or "second_line",
        "target_label": _text(body.get("target_label")),
        "sbar_text": sbar_text,
        "status": "sent",
        "actor": actor,
        "source": _text(body.get("source")) or MOBILE_SOURCE,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    await runtime.db.col("mobile_sbar_handoffs").insert_one(doc)
    task_payload = {
        "patient_id": patient_id,
        "bed": (patient or {}).get("hisBed") or alert.get("bed"),
        "name": (patient or {}).get("name") or alert.get("patient_name"),
        "module": "mobile_handoff",
        "task_type": "sbar_handoff",
        "title": f"SBAR移交：{alert_title}",
        "detail": sbar_text,
        "priority": _severity_priority(alert.get("severity")),
        "source": MOBILE_SOURCE,
        "alert_id": str(alert.get("_id")),
        "sbar_id": sbar_id,
    }
    task = await _service().upsert_clinical_task(task_payload, actor=actor)
    await runtime.alert_engine.disposition_alert(str(alert.get("_id")), action="sbar_handoff", reason=_text(body.get("note")), actor=actor)
    await write_audit_log(runtime.db, action="mobile_sbar_handoff", module="mobile", actor=actor, target_type="alert", target_id=str(alert.get("_id")), detail={"sbar_id": sbar_id})
    return {"code": 0, "sbar_id": sbar_id, "sbar_text": sbar_text, "patient_id": patient_id, "alert_id": str(alert.get("_id")), "status": "sent", "task": serialize_doc(task)}


@router.get("/alerts/{alert_id}/order-stubs/defaults")
async def order_stub_defaults(alert_id: str):
    alert = await _alert_doc(alert_id)
    if not alert:
        return {"code": 404, "message": "告警不存在"}
    return {"code": 0, "items": _order_stub_items(alert)}


@router.post("/alerts/{alert_id}/order-stubs")
async def create_order_stubs(alert_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    actor = _actor(request, body)
    alert = await _alert_doc(alert_id)
    if not alert:
        return {"code": 404, "message": "告警不存在"}
    patient_id = _text(alert.get("patient_id"))
    patient = await _patient_doc(patient_id)
    raw_items = body.get("items") if isinstance(body.get("items"), list) else _order_stub_items(alert)
    items = [item for item in raw_items if isinstance(item, dict) and item.get("checked", True)]
    if not items:
        return {"code": 400, "message": "请至少选择一项医嘱草稿"}
    title = f"医嘱草稿：{alert.get('name') or alert.get('alert_type') or '告警处置'}"
    detail = "；".join(_text(item.get("label")) for item in items if _text(item.get("label")))
    task_payload = {
        "patient_id": patient_id,
        "bed": (patient or {}).get("hisBed") or alert.get("bed"),
        "name": (patient or {}).get("name") or alert.get("patient_name"),
        "module": "order_stub",
        "task_type": _task_type_for_alert(alert, "order_stub"),
        "title": title,
        "detail": detail,
        "priority": _severity_priority(alert.get("severity")),
        "source": MOBILE_SOURCE,
        "alert_id": str(alert.get("_id")),
        "items": items,
        "note": _text(body.get("note")),
        "idempotency_key": _text(body.get("idempotency_key")),
    }
    result = await _service().upsert_clinical_task(task_payload, actor=actor)
    await write_audit_log(runtime.db, action="mobile_order_stub", module="mobile", actor=actor, target_type="alert", target_id=str(alert.get("_id")), detail={"items": items})
    return {"code": 0, **serialize_doc(result)}


@router.get("/bundles")
async def mobile_bundles(
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    patient_id: str | None = Query(None),
):
    patients = await _scoped_patients(dept, dept_code, patient_id)
    patient_ids = [str(item.get("_id")) for item in patients]
    checks = {}
    if patient_ids:
        cursor = runtime.db.col("mobile_bundle_checks").find({"patient_id": {"$in": patient_ids}})
        async for row in cursor:
            checks[(row.get("patient_id"), row.get("bundle_type"), row.get("item_key"))] = row
    bundles = []
    for patient in patients:
        pid = str(patient.get("_id"))
        for template in _bundle_templates():
            items = []
            done = 0
            for item in template["items"]:
                row = checks.get((pid, template["bundle_type"], item["key"])) or {}
                checked = bool(row.get("checked"))
                if checked:
                    done += 1
                items.append({**item, "checked": checked, "updated_at": row.get("updated_at"), "updated_by": row.get("updated_by")})
            bundles.append(
                {
                    "bundle_id": f"{pid}:{template['bundle_type']}",
                    "patient_id": pid,
                    "patient": {"bed": patient.get("hisBed") or patient.get("bed"), "name": patient.get("name") or patient.get("hisName")},
                    "bundle_type": template["bundle_type"],
                    "title": template["title"],
                    "items": serialize_doc(items),
                    "completion_rate": round(done / len(items), 3) if items else 0,
                    "updated_at": max([item.get("updated_at") for item in items if item.get("updated_at")] or [None]),
                }
            )
    return {"code": 0, "bundles": serialize_doc(bundles)}


@router.get("/tasks")
async def mobile_tasks(
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    actor: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(120, ge=1, le=300),
):
    patients = await _scoped_patients(dept, dept_code, None)
    patient_ids = [str(item.get("_id")) for item in patients]
    patient_map = {str(item.get("_id")): item for item in patients}
    task_query: dict[str, Any] = {}
    if patient_ids:
        task_query["patient_id"] = {"$in": patient_ids}
    if status and status != "all":
        task_query["status"] = {"$in": ["closed", "completed", "done"]} if status == "done" else {"$nin": ["closed", "completed", "done", "cancelled"]}
    else:
        task_query["status"] = {"$nin": ["cancelled"]}
    cursor = runtime.db.col("clinical_tasks").find(task_query).sort([("priority", -1), ("due_at", 1), ("updated_at", -1)]).limit(limit)
    rows = []
    async for doc in cursor:
        pid = _text(doc.get("patient_id"))
        patient = patient_map.get(pid) or {}
        rows.append(
            {
                "id": doc.get("task_id") or str(doc.get("_id")),
                "task_id": doc.get("task_id") or str(doc.get("_id")),
                "patient_id": pid,
                "bed": doc.get("bed") or patient.get("hisBed") or patient.get("bed"),
                "patient_name": doc.get("name") or patient.get("name") or patient.get("hisName"),
                "title": doc.get("title") or doc.get("task_type") or "床旁任务",
                "description": doc.get("detail") or doc.get("description") or doc.get("note") or "",
                "module": doc.get("module") or "clinical",
                "task_type": doc.get("task_type") or "",
                "priority": doc.get("priority") or "medium",
                "status": doc.get("status") or "open",
                "due_at": doc.get("due_at"),
                "updated_at": doc.get("updated_at"),
                "source": doc.get("source") or MOBILE_SOURCE,
            }
        )
    reminder_query: dict[str, Any] = {"status": "pending"}
    if actor:
        reminder_query["actor"] = actor
    if patient_ids:
        reminder_query["patient_id"] = {"$in": patient_ids}
    reminders = runtime.db.col("mobile_review_reminders").find(reminder_query).sort("due_at", 1).limit(60)
    async for doc in reminders:
        rows.insert(
            0,
            {
                "id": doc.get("reminder_id"),
                "task_id": doc.get("reminder_id"),
                "patient_id": doc.get("patient_id"),
                "bed": doc.get("bed"),
                "patient_name": doc.get("patient_name"),
                "title": doc.get("title") or "告警复评",
                "description": f"到期复评：{doc.get('due_at') or ''}",
                "module": "mobile_review",
                "task_type": "alert_review_reminder",
                "priority": "high",
                "status": "pending",
                "due_at": doc.get("due_at"),
                "updated_at": doc.get("updated_at"),
                "source": MOBILE_SOURCE,
            },
        )
    return {"code": 0, "tasks": serialize_doc(rows), "count": len(rows)}


async def _mobile_patient_rows(dept: str | None, dept_code: str | None, limit: int = 80) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    query = _admitted_scope_query(dept, dept_code)
    projection = {
        "name": 1,
        "hisName": 1,
        "hisBed": 1,
        "bed": 1,
        "hisPid": 1,
        "patient_id": 1,
        "sex": 1,
        "gender": 1,
        "hisSex": 1,
        "age": 1,
        "birthday": 1,
        "hisDept": 1,
        "dept": 1,
        "deptName": 1,
        "deptCode": 1,
        "clinicalDiagnosis": 1,
        "admissionDiagnosis": 1,
        "diagnosis": 1,
        "hisDiagnose": 1,
        "hisDiagnosis": 1,
        "risk_level": 1,
        "level": 1,
    }
    total = await runtime.db.col("patient").count_documents(query)
    if total == 0 and _text(dept_code) and _text(dept):
        query = _admitted_scope_query(dept, None)
        total = await runtime.db.col("patient").count_documents(query)
    rows: list[dict[str, Any]] = []
    cursor = runtime.db.col("patient").find(query, projection).sort("hisBed", 1).limit(max(1, min(limit, 300)))
    async for doc in cursor:
        row = serialize_doc(doc)
        row["diagnosis"] = row.get("diagnosis") or row.get("clinicalDiagnosis") or row.get("admissionDiagnosis") or row.get("hisDiagnose") or row.get("hisDiagnosis") or ""
        rows.append(row)
    return rows, total, query


async def _attach_latest_alerts(rows: list[dict[str, Any]], alert_limit: int = 600) -> list[dict[str, Any]]:
    patient_ids = [str(row.get("_id") or row.get("patient_id") or "") for row in rows if row.get("_id") or row.get("patient_id")]
    his_pids = [str(row.get("hisPid") or "").strip() for row in rows if row.get("hisPid")]
    beds = [str(row.get("hisBed") or row.get("bed") or "").strip() for row in rows if row.get("hisBed") or row.get("bed")]
    if not (patient_ids or his_pids or beds):
        return rows
    alert_query: dict[str, Any] = {"$or": []}
    if patient_ids:
        alert_query["$or"].extend([
            {"patient_id": {"$in": patient_ids}},
            {"patientId": {"$in": patient_ids}},
            {"extra.patient_id": {"$in": patient_ids}},
            {"payload.patient_id": {"$in": patient_ids}},
        ])
    if his_pids:
        alert_query["$or"].extend([
            {"hisPid": {"$in": his_pids}},
            {"payload.hisPid": {"$in": his_pids}},
            {"extra.hisPid": {"$in": his_pids}},
        ])
    if beds:
        alert_query["$or"].extend([
            {"bed": {"$in": beds}},
            {"hisBed": {"$in": beds}},
            {"bed_no": {"$in": beds}},
            {"payload.bed": {"$in": beds}},
            {"extra.bed": {"$in": beds}},
        ])
    latest: dict[str, dict[str, Any]] = {}
    cursor_alerts = runtime.db.col("alert_records").find(
        alert_query,
        {
            "name": 1,
            "title": 1,
            "alert_name": 1,
            "alert_type": 1,
            "rule_id": 1,
            "category": 1,
            "severity": 1,
            "level": 1,
            "message": 1,
            "summary": 1,
            "patient_id": 1,
            "patientId": 1,
            "hisPid": 1,
            "bed": 1,
            "hisBed": 1,
            "bed_no": 1,
            "payload": 1,
            "extra": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(alert_limit)
    async for alert in cursor_alerts:
        alert_doc = serialize_doc(alert)
        payload = alert_doc.get("payload") if isinstance(alert_doc.get("payload"), dict) else {}
        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
        keys = [
            _text(alert_doc.get("patient_id")),
            _text(alert_doc.get("patientId")),
            _text(alert_doc.get("hisPid")),
            _text(alert_doc.get("bed")),
            _text(alert_doc.get("hisBed")),
            _text(alert_doc.get("bed_no")),
            _text(payload.get("patient_id")),
            _text(payload.get("hisPid")),
            _text(payload.get("bed")),
            _text(extra.get("patient_id")),
            _text(extra.get("hisPid")),
            _text(extra.get("bed")),
        ]
        for key in keys:
            if key and key not in latest:
                latest[key] = alert_doc
    for row in rows:
        keys = [
            _text(row.get("_id")),
            _text(row.get("patient_id")),
            _text(row.get("hisPid")),
            _text(row.get("hisBed") or row.get("bed")),
        ]
        hit = next((latest[key] for key in keys if key in latest), None)
        if hit:
            row["latest_alert"] = hit
            row["alertLevel"] = hit.get("severity") or hit.get("level") or row.get("risk_level") or "warning"
            row["risk_level"] = row["alertLevel"]
    return rows


async def _recent_mobile_alerts(dept: str | None, dept_code: str | None, patient_query: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    patient_ids = [str(doc.get("_id")) async for doc in runtime.db.col("patient").find(patient_query, {"_id": 1}).limit(300)]
    query: dict[str, Any] = {"$or": []}
    if patient_ids:
        query["$or"].append({"patient_id": {"$in": patient_ids}})
    code = _text(dept_code)
    dept_text = _text(dept)
    if code:
        query["$or"].extend([{"deptCode": code}, {"dept_code": code}, {"extra.deptCode": code}, {"extra.dept_code": code}])
    if dept_text:
        query["$or"].extend([{"dept": dept_text}, {"department": dept_text}, {"hisDept": dept_text}, {"extra.dept": dept_text}])
    if not query["$or"]:
        query = {}
    cursor = runtime.db.col("alert_records").find(
        query,
        {"name": 1, "title": 1, "alert_type": 1, "severity": 1, "level": 1, "message": 1, "summary": 1, "patient_id": 1, "bed": 1, "created_at": 1},
    ).sort("created_at", -1).limit(limit)
    return [serialize_doc(doc) async for doc in cursor]


@router.get("/home-lite")
async def mobile_home_lite(
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
    actor: str | None = Query(None),
    userName: str | None = Query(None),
):
    account = await _resolve_mobile_account(actor or userName, dept_code or deptCode, dept)
    resolved_dept_code = _text(dept_code or deptCode or account.get("dept_code"))
    resolved_dept = _text(dept or account.get("dept"))
    rows, total, patient_query = await _mobile_patient_rows(resolved_dept, resolved_dept_code, limit=12)
    rows = await _attach_latest_alerts(rows, alert_limit=160)
    alerts = await _recent_mobile_alerts(resolved_dept, resolved_dept_code, patient_query, limit=8)
    return {
        "code": 0,
        "patient_count": total,
        "patients_preview": serialize_doc(rows),
        "alerts": alerts,
        "alert_count": len(alerts),
        "dept_code": resolved_dept_code,
        "dept": resolved_dept,
        "generated_at": serialize_doc(datetime.now()),
    }


@router.get("/patients")
async def mobile_patients(
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    deptCode: str | None = Query(None),
    patient_scope: str = Query("in_dept"),
):
    rows, total, _ = await _mobile_patient_rows(dept, dept_code or deptCode, limit=80 if patient_scope == "in_dept" else 120)
    rows = await _attach_latest_alerts(rows)
    return {"code": 0, "patients": rows, "count": total, "scope": "admitted"}


@router.get("/patients/resolve")
async def mobile_patient_resolve(q: str = Query(..., min_length=1)):
    text = _text(q)
    query: dict[str, Any]
    oid = _oid(text)
    if oid:
        query = {"_id": oid}
    else:
        query = {
            "$or": [
                {"hisPid": text},
                {"patient_id": text},
                {"hisBed": text},
                {"bed": text},
                {"name": text},
                {"hisName": text},
            ]
        }
    patient = await runtime.db.col("patient").find_one(query)
    if not patient:
        return {"code": 404, "message": "未找到床位或患者", "patient": None}
    return {"code": 0, "patient": serialize_doc(_patient_display(patient))}


@router.get("/patients/{patient_id}/bedcard")
async def mobile_patient_bedcard(patient_id: str):
    patient = await _patient_doc(patient_id)
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    pid = str(patient.get("_id"))
    alerts = await _latest_patient_alerts(pid, limit=5)
    support = {
        "ventilator": any("vent" in _alert_type_text(row) or "respiratory" in _alert_type_text(row) or "spo2" in _alert_type_text(row) for row in alerts),
        "crrt": any("crrt" in _alert_type_text(row) or "renal" in _alert_type_text(row) or "aki" in _alert_type_text(row) for row in alerts),
        "vasopressor": any("shock" in _alert_type_text(row) or "map" in _alert_type_text(row) or "hypotension" in _alert_type_text(row) for row in alerts),
        "sedation": any("delirium" in _alert_type_text(row) or "sedation" in _alert_type_text(row) for row in alerts),
    }
    organs = []
    organ_rules = [
        ("respiratory", "呼吸", ["respiratory", "hypoxemia", "ards", "ventilator", "spo2"]),
        ("circulation", "循环", ["shock", "hypotension", "map", "lactate"]),
        ("renal", "肾脏", ["aki", "renal", "urine", "creatinine"]),
        ("infection", "感染", ["sepsis", "infection", "fever"]),
        ("neuro", "神经", ["delirium", "sedation", "gcs"]),
    ]
    for key, label, tokens in organ_rules:
        hit = next((row for row in alerts if any(token in _alert_type_text(row) for token in tokens)), None)
        organs.append({"key": key, "label": label, "abnormal": bool(hit), "tone": _severity_priority((hit or {}).get("severity")) if hit else "low"})
    return {
        "code": 0,
        "patient": serialize_doc(_patient_display(patient)),
        "support": support,
        "organs": organs,
        "alerts": [
            {
                **row,
                "title_cn": _simple_alert_label(row.get("name") or row.get("alert_type") or row.get("rule_id") or row.get("category")),
                "severity_cn": _simple_alert_label(row.get("severity")),
            }
            for row in alerts
        ],
        "generated_at": serialize_doc(datetime.now()),
    }


@router.post("/patients/{patient_id}/interpret")
async def mobile_patient_interpret(patient_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    actor = _actor(request, body)
    patient = await _patient_doc(patient_id)
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    pid = str(patient.get("_id"))
    summary: dict[str, Any] = {}
    try:
        summary = await build_rounding_summary(pid, hours=int(body.get("hours") or 24))
    except Exception:
        summary = {}
    alerts = await _latest_patient_alerts(pid, limit=3)
    display = _patient_display(patient)
    diagnosis = display.get("diagnosis") or "暂无明确诊断摘要"
    alert_text = "、".join(_simple_alert_label(row.get("name") or row.get("alert_type") or row.get("severity")) for row in alerts) or "暂无活动高危告警"
    vitals = summary.get("vitals") or summary.get("vital_trends") or []
    vital_text = ""
    if isinstance(vitals, list) and vitals:
        vital_text = "，".join(f"{item.get('label')}: {item.get('latest', '--')}" for item in vitals[:3] if isinstance(item, dict))
    lines = [
        f"{display.get('bed') or '--'}床 {display.get('name') or '患者'}，主要问题：{diagnosis}。",
        f"近24小时重点：{alert_text}。",
        f"床旁建议：先复核生命体征、检验异常和活动医嘱；{vital_text or '暂无可用趋势时请以床旁监护为准'}。",
    ]
    await write_audit_log(runtime.db, action="mobile_patient_interpret", module="mobile", actor=actor, target_type="patient", target_id=pid, detail={"source": _text(body.get("source")) or MOBILE_SOURCE})
    return {"code": 0, "summary": lines, "text": "\n".join(lines), "patient_id": pid}


@router.post("/patients/{patient_id}/rounding-note")
async def mobile_rounding_note(patient_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    actor = _actor(request, body)
    patient = await _patient_doc(patient_id)
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    pid = str(patient.get("_id"))
    raw = _text(body.get("text") or body.get("transcript") or body.get("note"))
    if not raw:
        return {"code": 400, "message": "查房记录不能为空"}
    soap = body.get("soap") if isinstance(body.get("soap"), dict) else {}
    if not soap:
        soap = {
            "S": raw,
            "O": _text(body.get("objective")) or "请结合床旁生命体征、检验和用药复核。",
            "A": _text(body.get("assessment")) or "移动端语音查房记录，待医生确认。",
            "P": _text(body.get("plan")) or "完善今日处置计划并闭环。",
        }
    content = "\n".join([f"S: {soap.get('S')}", f"O: {soap.get('O')}", f"A: {soap.get('A')}", f"P: {soap.get('P')}"])
    result = await save_rounding_version(
        pid,
        {
            "content": content,
            "status": _text(body.get("status")) or "draft",
            "source": _text(body.get("source")) or MOBILE_SOURCE,
            "summary_snapshot": {"raw_text": raw, "soap": soap, "device_context": body.get("device_context") or {}},
        },
        actor=actor,
    )
    await write_audit_log(runtime.db, action="mobile_rounding_note", module="mobile", actor=actor, target_type="patient", target_id=pid, detail={"version_id": result.get("version_id")})
    return {"code": 0, "soap": soap, **serialize_doc(result)}


@router.post("/bundles/check")
async def mobile_bundle_check(request: Request, payload: dict = Body(default={})):
    body = payload or {}
    actor = _actor(request, body)
    patient_id = _text(body.get("patient_id"))
    bundle_type = _text(body.get("bundle_type"))
    item_key = _text(body.get("item_key"))
    if not patient_id or not bundle_type or not item_key:
        return {"code": 400, "message": "缺少 bundle 勾选参数"}
    now = datetime.now()
    doc = {
        "patient_id": patient_id,
        "bundle_type": bundle_type,
        "item_key": item_key,
        "item_label": _text(body.get("item_label")),
        "checked": bool(body.get("checked")),
        "updated_by": actor,
        "updated_at": now,
        "source": _text(body.get("source")) or MOBILE_SOURCE,
    }
    await runtime.db.col("mobile_bundle_checks").update_one(
        {"patient_id": patient_id, "bundle_type": bundle_type, "item_key": item_key},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await write_audit_log(runtime.db, action="mobile_bundle_check", module="mobile", actor=actor, target_type="patient", target_id=patient_id, detail=doc)
    return {"code": 0, "check": serialize_doc(doc)}


@router.post("/alerts/{alert_id}/review-reminder")
async def create_review_reminder(alert_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    actor = _actor(request, body)
    alert = await _alert_doc(alert_id)
    if not alert:
        return {"code": 404, "message": "告警不存在"}
    minutes = max(int(body.get("review_after_minutes") or 60), 1)
    now = datetime.now()
    due_at = now + timedelta(minutes=minutes)
    key = _text(body.get("idempotency_key")) or f"{alert_id}:{actor}:{minutes}"
    existing = await runtime.db.col("mobile_review_reminders").find_one({"idempotency_key": key, "status": "pending"})
    if existing:
        return {"code": 0, "reminder": serialize_doc(existing), "deduped": True}
    reminder_id = str(uuid.uuid4())
    doc = {
        "reminder_id": reminder_id,
        "idempotency_key": key,
        "alert_id": str(alert.get("_id")),
        "patient_id": _text(alert.get("patient_id")) or None,
        "bed": alert.get("bed"),
        "patient_name": alert.get("patient_name"),
        "title": alert.get("name") or alert.get("alert_type") or "告警复评",
        "due_at": due_at,
        "actor": actor,
        "status": "pending",
        "source": _text(body.get("source")) or MOBILE_SOURCE,
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("mobile_review_reminders").insert_one(doc)
    task_payload = {
        "patient_id": doc["patient_id"],
        "bed": doc["bed"],
        "name": doc["patient_name"],
        "module": "mobile_review",
        "task_type": "alert_review_reminder",
        "title": f"复评提醒：{doc['title']}",
        "detail": f"{minutes}分钟后复评该告警",
        "priority": _severity_priority(alert.get("severity")),
        "source": MOBILE_SOURCE,
        "alert_id": str(alert.get("_id")),
        "review_reminder_id": reminder_id,
        "due_at": due_at,
        "idempotency_key": key,
    }
    task = await _service().upsert_clinical_task(task_payload, actor=actor)
    await runtime.alert_engine.disposition_alert(str(alert.get("_id")), action="review_later", reason=_text(body.get("note")), actor=actor, review_after_minutes=minutes)
    await write_audit_log(runtime.db, action="mobile_review_reminder", module="mobile", actor=actor, target_type="alert", target_id=str(alert.get("_id")), detail={"reminder_id": reminder_id, "due_at": due_at})
    return {"code": 0, "reminder": serialize_doc(doc), "task": serialize_doc(task), "deduped": False}


@router.get("/review-reminders")
async def review_reminders(
    actor: str | None = Query(None),
    dept: str | None = Query(None),
    dept_code: str | None = Query(None),
    status: str = Query("pending"),
):
    query: dict[str, Any] = {"status": status}
    if actor:
        query["actor"] = actor
    patient_ids = []
    if dept or dept_code:
        patients = await _scoped_patients(dept, dept_code, None)
        patient_ids = [str(item.get("_id")) for item in patients]
        query["patient_id"] = {"$in": patient_ids}
    cursor = runtime.db.col("mobile_review_reminders").find(query).sort("due_at", 1).limit(100)
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"code": 0, "reminders": rows}


@router.post("/review-reminders/{reminder_id}/complete")
async def complete_review_reminder(reminder_id: str, request: Request, payload: dict = Body(default={})):
    body = payload or {}
    actor = _actor(request, body)
    now = datetime.now()
    await runtime.db.col("mobile_review_reminders").update_one(
        {"reminder_id": reminder_id},
        {"$set": {"status": "completed", "completed_by": actor, "completed_at": now, "updated_at": now, "result": _text(body.get("result")) or "reviewed"}},
    )
    doc = await runtime.db.col("mobile_review_reminders").find_one({"reminder_id": reminder_id})
    if not doc:
        return {"code": 404, "message": "复评提醒不存在"}
    alert_id = _text(doc.get("alert_id"))
    if alert_id:
        await runtime.alert_engine.review_alert(alert_id, result=_text(body.get("result")) or "reviewed", evidence=[_text(body.get("note"))] if _text(body.get("note")) else [], actor=actor)
    await write_audit_log(runtime.db, action="mobile_review_complete", module="mobile", actor=actor, target_type="review_reminder", target_id=reminder_id, detail={"alert_id": alert_id})
    return {"code": 0, "reminder": serialize_doc(doc)}
