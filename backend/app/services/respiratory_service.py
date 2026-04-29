from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from app import runtime
from app.services.audit_service import write_audit_log
from app.utils.patient_helpers import calculate_age, patient_his_pid, research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

logger = logging.getLogger("icu-alert")

VENT_CODES = [
    "param_TiWei",
    "param_HuXiMoShi",
    "param_vent_mode",
    "param_FiO2",
    "param_fio2",
    "param_vent_peep",
    "param_vent_measure_peep",
    "param_vent_vt",
    "param_vent_vti",
    "param_vent_set_vt",
    "param_vent_set_PeakFlow",
    "param_vent_plat_pressure",
    "param_vent_pip",
    "param_vent_resp",
    "param_HuXiPinLv",
    "param_qiDaoZuLi",
    "param_vent_P0.1",
    "param_vent_C_STAT",
    "param_vent_pause_C_STAT",
    "param_jingTaiShunYingXing",
]


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fio2_fraction(value: Any) -> float | None:
    val = _num(value)
    if val is None or val <= 0:
        return None
    return round(val / 100.0, 3) if val > 1 else round(val, 3)


def _patient_name(patient: dict[str, Any]) -> str:
    name = str(patient.get("name") or patient.get("hisName") or "").strip()
    if not name:
        return "未命名患者"
    return name


def _vent_param(params: dict[str, Any], *codes: str) -> Any:
    for code in codes:
        if params.get(code) not in (None, ""):
            return params.get(code)
    return None


def _append_department_scope(query: dict[str, Any], *, department: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    dept_name = str(department or "").strip()
    dept_code_text = str(dept_code or "").strip()
    if dept_name and not dept_code_text and dept_name.isdigit():
        dept_code_text = dept_name
        dept_name = ""
    if dept_name and dept_code_text and (dept_name == dept_code_text or dept_name.isdigit()):
        dept_name = ""
    clauses: list[dict[str, Any]] = [query] if query else []
    if dept_code_text:
        clauses.append({"deptCode": dept_code_text})
    elif dept_name:
        clauses.append({"$or": [{"hisDept": dept_name}, {"dept": dept_name}]})
    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _patient_matches_department(patient: dict[str, Any], *, department: str | None = None, dept_code: str | None = None) -> bool:
    dept_name = str(department or "").strip()
    dept_code_text = str(dept_code or "").strip()
    if dept_name and not dept_code_text and dept_name.isdigit():
        dept_code_text = dept_name
        dept_name = ""
    if dept_code_text:
        return str(patient.get("deptCode") or "").strip() == dept_code_text
    if dept_name:
        return dept_name in {str(patient.get("hisDept") or "").strip(), str(patient.get("dept") or "").strip()}
    return True


def _patient_matches_scope(patient: dict[str, Any], scope: str | None) -> bool:
    token = str(scope or "in_dept").strip().lower()
    status = str(patient.get("status") or "").strip()
    in_dept_statuses = {"admitted", "在科", "住院", "icu", "icu在科"}
    out_dept_statuses = {"discharged", "出科", "出院", "离科", "转出", "dead", "death", "deceased", "死亡"}
    if token in {"in_dept", "active", "admitted"}:
        return status in in_dept_statuses
    if token in {"out_dept", "discharged"}:
        return status in out_dept_statuses
    return not status or status in in_dept_statuses or status in out_dept_statuses


async def _active_ventilator(
    patient: dict[str, Any],
    bind_hint: dict[str, Any] | None = None,
    cap_hint: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    pid = str(patient.get("_id") or "")
    bind = bind_hint
    try:
        if bind is None:
            bind = await runtime.alert_engine._get_active_vent_bind(pid)
    except Exception:
        bind = bind_hint
    device_id = bind.get("deviceID") if bind else None
    if not device_id:
        try:
            device_id = await runtime.alert_engine._get_device_id_for_patient(patient, ["vent"])
        except Exception:
            device_id = None
    cap = cap_hint
    if device_id:
        try:
            if cap is None:
                cap = await runtime.alert_engine._get_latest_device_cap(device_id, codes=VENT_CODES)
        except Exception:
            cap = cap_hint
    return bind, cap


async def _latest_pao2(patient: dict[str, Any], hours: int = 24) -> float | None:
    his_pid = patient_his_pid(patient)
    if not his_pid:
        return None
    since = datetime.now() - timedelta(hours=hours)
    cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(
        {
            "hisPid": his_pid,
            "$and": [
                {"$or": [{"authTime": {"$gte": since}}, {"reportTime": {"$gte": since}}, {"time": {"$gte": since}}]},
                {"$or": [
                    {"itemName": {"$regex": "pao2|氧分压|动脉氧", "$options": "i"}},
                    {"itemCnName": {"$regex": "pao2|氧分压|动脉氧", "$options": "i"}},
                ]},
            ],
        },
        {"result": 1, "resultValue": 1, "value": 1, "authTime": 1, "reportTime": 1, "time": 1},
    ).sort("authTime", -1).limit(20)
    async for doc in cursor:
        value = _num(doc.get("result") or doc.get("resultValue") or doc.get("value"))
        if value is not None:
            return value
    return None


async def _latest_rass(patient: dict[str, Any]) -> float | None:
    try:
        return await runtime.alert_engine._get_latest_assessment(patient.get("_id"), "rass")
    except Exception:
        return None


async def _latest_spo2_rr(patient: dict[str, Any]) -> tuple[float | None, float | None]:
    try:
        vitals = await runtime.alert_engine._get_latest_vitals_by_patient(patient.get("_id"))
    except Exception:
        vitals = {}
    spo2 = vitals.get("spo2")
    if spo2 is None:
        try:
            cap = await runtime.alert_engine._get_latest_param_snapshot_by_pid(patient.get("_id"), codes=["param_spo2", "param_resp"])
            params = cap.get("params") if cap else {}
            spo2 = params.get("param_spo2")
            rr = params.get("param_resp")
            return _num(spo2), _num(rr)
        except Exception:
            return None, _num(vitals.get("rr"))
    return _num(spo2), _num(vitals.get("rr"))


def _risk_tags(row: dict[str, Any]) -> list[str]:
    tags = []
    if row.get("driving_pressure") is not None and float(row["driving_pressure"]) > 15:
        tags.append("高驱动压")
    if row.get("pf_ratio") is not None and float(row["pf_ratio"]) < 150:
        tags.append("低氧合")
    fio2 = _fio2_fraction(row.get("fio2"))
    if fio2 is not None and fio2 >= 0.6:
        tags.append("高 FiO2")
    if row.get("peep") is not None and float(row["peep"]) >= 10:
        tags.append("高 PEEP")
    if not row.get("latest_cuff_pressure"):
        tags.append("气囊压待测")
    if row.get("difficult_airway"):
        tags.append("困难气道")
    return tags


def _parameter_completeness(row: dict[str, Any]) -> dict[str, Any]:
    required = ["ventilator_mode", "fio2", "peep", "vt", "pplat", "driving_pressure", "spo2", "pf_ratio", "rass"]
    present = [key for key in required if row.get(key) not in (None, "", "未知")]
    missing = [key for key in required if key not in present]
    return {
        "score": round(len(present) / len(required), 2),
        "present": present,
        "missing": missing,
    }


def _safety_score(row: dict[str, Any]) -> int:
    score = 100
    penalties = {
        "高驱动压": 18,
        "低氧合": 20,
        "高 FiO2": 12,
        "高 PEEP": 12,
        "气囊压待测": 8,
        "困难气道": 12,
    }
    for tag in row.get("risk_tags") or []:
        score -= penalties.get(tag, 4)
    completeness = row.get("parameter_completeness") or {}
    score -= int((1 - float(completeness.get("score", 1))) * 12)
    return max(0, min(100, score))


def _worklist_actions(row: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    tags = set(row.get("risk_tags") or [])
    if "高驱动压" in tags:
        actions.append({"priority": "high", "title": "复核肺保护通气", "detail": "驱动压偏高，请结合 Pplat、PEEP、VT 和病因评估。"})
    if "低氧合" in tags or "高 FiO2" in tags:
        actions.append({"priority": "high", "title": "复核氧合策略", "detail": "关注 P/F、俯卧位、PEEP/FiO2 组合和血气复查。"})
    if "气囊压待测" in tags:
        actions.append({"priority": "medium", "title": "测量气囊压", "detail": "建议补录气囊压力、固定深度和湿化状态。"})
    sbt = row.get("sbt_candidate_status") or {}
    if sbt.get("status") == "candidate":
        actions.append({"priority": "medium", "title": "今日 SBT 评估", "detail": "满足默认可评估条件，请床旁确认禁忌证后记录结果。"})
    if row.get("difficult_airway"):
        actions.append({"priority": "high", "title": "确认困难气道预案", "detail": "查阅备选设备和联系人，确保急救流程清晰。"})
    return actions[:5]


def _respiratory_completion(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a small closure dashboard for respiratory therapy."""
    total = len(rows)
    if not total:
        return {
            "percent": 100,
            "status": "ready",
            "label": "暂无机械通气患者",
            "data_quality": {"percent": 100, "missing": []},
            "tasks": [],
            "gaps": [],
        }
    completed = 0
    gaps: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    missing_counter: dict[str, int] = {}
    for row in rows:
        row_done = 0
        if row.get("safety_score") is not None:
            row_done += 1
        if row.get("risk_tags") is not None:
            row_done += 1
        if row.get("sbt_candidate_status"):
            row_done += 1
        if row.get("airway_type") and row.get("airway_type") != "气管插管/气切待确认":
            row_done += 1
        if row.get("latest_cuff_pressure"):
            row_done += 1
        completed += row_done
        for key in (row.get("parameter_completeness") or {}).get("missing") or []:
            missing_counter[key] = missing_counter.get(key, 0) + 1
        for action in row.get("worklist_actions") or []:
            tasks.append(
                {
                    "patient_id": row.get("patient_id"),
                    "bed_no": row.get("bed_no"),
                    "name": row.get("name"),
                    "priority": action.get("priority") or "medium",
                    "title": action.get("title"),
                    "detail": action.get("detail"),
                    "action": "进入患者",
                }
            )
    denominator = total * 5
    percent = round(completed / denominator * 100) if denominator else 100
    for key, count in sorted(missing_counter.items(), key=lambda item: item[1], reverse=True)[:5]:
        gaps.append({"key": key, "label": _respiratory_field_label(key), "count": count})
    return {
        "percent": max(0, min(100, percent)),
        "status": "ready" if percent >= 90 else "open",
        "label": f"{total} 人机械通气，{len(tasks)} 个待办",
        "data_quality": {
            "percent": max(0, min(100, round((1 - sum(missing_counter.values()) / max(1, total * 9)) * 100))),
            "missing": gaps,
        },
        "tasks": tasks[:8],
        "gaps": gaps,
    }


def _respiratory_field_label(key: str) -> str:
    labels = {
        "ventilator_mode": "通气模式",
        "fio2": "FiO2",
        "peep": "PEEP",
        "vt": "潮气量",
        "pplat": "平台压",
        "driving_pressure": "驱动压",
        "spo2": "SpO2",
        "pf_ratio": "P/F",
        "rass": "RASS",
    }
    return labels.get(key, key)


async def build_ventilated_patient_row(
    patient: dict[str, Any],
    bind_hint: dict[str, Any] | None = None,
    cap_hint: dict[str, Any] | None = None,
    *,
    fast: bool = False,
) -> dict[str, Any] | None:
    bind, cap = await _active_ventilator(patient, bind_hint=bind_hint, cap_hint=cap_hint)
    if not bind and not cap:
        return None
    params = (cap or {}).get("params") or {}
    fio2 = _vent_param(params, "param_FiO2", "param_fio2")
    peep = _vent_param(params, "param_vent_measure_peep", "param_vent_peep")
    pplat = _vent_param(params, "param_vent_plat_pressure")
    pip = _vent_param(params, "param_vent_pip")
    vt = _vent_param(params, "param_vent_vt", "param_vent_vti")
    vt_set = _vent_param(params, "param_vent_set_vt")
    rr_vent = _vent_param(params, "param_vent_resp", "param_HuXiPinLv")
    driving_pressure = None
    approximate = False
    if _num(pplat) is not None and _num(peep) is not None:
        driving_pressure = round(float(pplat) - float(peep), 1)
    elif _num(pip) is not None and _num(peep) is not None:
        driving_pressure = round(float(pip) - float(peep), 1)
        approximate = True
    pao2 = None if fast else await _latest_pao2(patient)
    fio2_frac = _fio2_fraction(fio2)
    pf_ratio = round(float(pao2) / fio2_frac, 1) if pao2 is not None and fio2_frac else None
    spo2, rr_vital = (None, None) if fast else await _latest_spo2_rr(patient)
    rass = None if fast else await _latest_rass(patient)
    airway_plan = {"plan": {}} if fast else await get_airway_plan(str(patient.get("_id")))
    latest_airway = {} if fast else await latest_airway_record(str(patient.get("_id")))
    row = {
        "patient_id": str(patient.get("_id")),
        "bed_no": patient.get("hisBed") or patient.get("bed") or "",
        "name": _patient_name(patient),
        "age": patient.get("age") or calculate_age(patient.get("birthday")) or patient.get("hisAge") or "",
        "diagnosis": patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "",
        "position": _vent_param(params, "param_TiWei"),
        "ventilator_mode": _vent_param(params, "param_HuXiMoShi", "param_vent_mode") or "未知",
        "fio2": fio2,
        "peep": peep,
        "vt": vt,
        "vt_set": vt_set,
        "peak_flow": _vent_param(params, "param_vent_set_PeakFlow"),
        "pplat": pplat,
        "pip": pip,
        "airway_resistance": _vent_param(params, "param_qiDaoZuLi"),
        "p01": _vent_param(params, "param_vent_P0.1"),
        "c_stat": _vent_param(params, "param_vent_C_STAT", "param_vent_pause_C_STAT", "param_jingTaiShunYingXing"),
        "static_compliance": _vent_param(params, "param_jingTaiShunYingXing", "param_vent_C_STAT", "param_vent_pause_C_STAT"),
        "driving_pressure": driving_pressure,
        "driving_pressure_approximate": approximate,
        "rr": rr_vent if rr_vent is not None else rr_vital,
        "spo2": spo2,
        "pao2": pao2,
        "pf_ratio": pf_ratio,
        "prone_position": False if fast else await _has_recent_text(str(patient.get("_id")), ["俯卧", "prone"], hours=24),
        "artificial_airway": bool(bind),
        "airway_type": latest_airway.get("airway_type") or ("气管插管/气切待确认" if bind else "无"),
        "rass": rass,
        "latest_cuff_pressure": latest_airway.get("cuff_pressure"),
        "difficult_airway": bool((airway_plan.get("plan") or {}).get("difficult_airway") or (airway_plan.get("plan") or {}).get("risk_level") in {"high", "critical"}),
        "ventilator_time": (cap or {}).get("time"),
        "bind_time": (bind or {}).get("bindTime"),
        "data_source": "deviceCap+deviceBind+score+LIS",
    }
    row["risk_tags"] = _risk_tags(row)
    row["sbt_candidate_status"] = evaluate_sbt_candidate(row, True if fast else await _hemodynamic_stable(patient), rass)
    row["parameter_completeness"] = _parameter_completeness(row)
    row["safety_score"] = _safety_score(row)
    row["worklist_actions"] = _worklist_actions(row)
    return serialize_doc(row)


async def _bulk_latest_vent_caps(device_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [str(item) for item in device_ids if item]
    if not ids:
        return {}
    cursor = runtime.db.col("deviceCap").find(
        {"deviceID": {"$in": ids}, "code": {"$in": VENT_CODES}},
        {"deviceID": 1, "code": 1, "time": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1},
    ).sort("time", -1).limit(max(5000, len(ids) * len(VENT_CODES) * 8))
    snapshots: dict[str, dict[str, Any]] = {}
    expected = len(ids) * len(VENT_CODES)
    seen = 0
    async for doc in cursor:
        device_id = str(doc.get("deviceID") or "")
        code = doc.get("code")
        if not device_id or not code:
            continue
        snap = snapshots.setdefault(device_id, {"params": {}, "time": None})
        if code in snap["params"]:
            continue
        value = doc.get("fVal") if doc.get("fVal") is not None else doc.get("intVal") if doc.get("intVal") is not None else doc.get("strVal") if doc.get("strVal") is not None else doc.get("value")
        if value is None:
            continue
        snap["params"][code] = value
        if doc.get("time") and (snap.get("time") is None or doc.get("time") > snap.get("time")):
            snap["time"] = doc.get("time")
        seen += 1
        if seen >= expected:
            break
    return snapshots


async def _hemodynamic_stable(patient: dict[str, Any]) -> bool:
    try:
        return not await runtime.alert_engine._has_vasopressor(patient.get("_id"))
    except Exception:
        return True


async def _has_recent_text(pid: str, keywords: list[str], hours: int = 24) -> bool:
    try:
        docs = await runtime.alert_engine._get_recent_text_events(pid, keywords, hours=hours, limit=200)
        return bool(docs)
    except Exception:
        return False


def sbt_default_config() -> dict[str, Any]:
    cfg = (runtime.config.yaml_cfg or {}).get("respiratory_dashboard", {}) if runtime.config is not None else {}
    sbt = cfg.get("sbt_criteria") if isinstance(cfg, dict) else None
    if isinstance(sbt, dict):
        return sbt
    return {"fio2_max": 0.5, "peep_max": 8, "pf_ratio_min": 150, "rass_min": -2, "rass_max": 1}


def evaluate_sbt_candidate(row: dict[str, Any], hemodynamic_stable: bool = True, rass: float | None = None) -> dict[str, Any]:
    cfg = sbt_default_config()
    reasons = []
    fio2 = _fio2_fraction(row.get("fio2"))
    peep = _num(row.get("peep"))
    pf_ratio = _num(row.get("pf_ratio"))
    if fio2 is None:
        reasons.append("FiO2 缺失")
    elif fio2 > float(cfg.get("fio2_max", 0.5)):
        reasons.append(f"FiO2 {fio2} 高于阈值")
    if peep is None:
        reasons.append("PEEP 缺失")
    elif peep > float(cfg.get("peep_max", 8)):
        reasons.append(f"PEEP {peep} 高于阈值")
    if pf_ratio is not None and pf_ratio < float(cfg.get("pf_ratio_min", 150)):
        reasons.append(f"P/F {pf_ratio} 偏低")
    if not hemodynamic_stable:
        reasons.append("仍需血管活性药或循环不稳")
    if rass is not None and not (float(cfg.get("rass_min", -2)) <= rass <= float(cfg.get("rass_max", 1))):
        reasons.append(f"RASS {rass} 不在目标范围")
    return {
        "status": "candidate" if not reasons else "not_suitable",
        "reasons": reasons,
        "criteria": cfg,
        "confidence": 0.78 if not reasons else 0.55,
    }


async def list_ventilated_patients(*, department: str | None = None, dept_code: str | None = None, patient_scope: str = "in_dept") -> dict[str, Any]:
    rows = []
    seen: set[str] = set()

    # 呼吸治疗工作台以“当前呼吸机绑定”为主索引，避免全科患者逐个反查设备导致接口超时。
    bind_cursor = runtime.db.col("deviceBind").find(
        {"unBindTime": None, "type": {"$regex": "vent|呼吸", "$options": "i"}},
        {"pid": 1, "deviceID": 1, "type": 1, "bindTime": 1, "unBindTime": 1},
    ).sort("bindTime", -1).limit(200)
    binds = [bind async for bind in bind_cursor]
    cap_by_device = await _bulk_latest_vent_caps([str(bind.get("deviceID") or "") for bind in binds])
    pid_values = [str(bind.get("pid") or "").strip() for bind in binds if str(bind.get("pid") or "").strip()]
    oid_values = [safe_oid(pid) for pid in pid_values if safe_oid(pid) is not None]
    patient_by_pid: dict[str, dict[str, Any]] = {}
    if oid_values:
        patient_cursor = runtime.db.col("patient").find({"_id": {"$in": oid_values}})
        async for patient in patient_cursor:
            patient_by_pid[str(patient.get("_id"))] = patient
    for bind in binds:
        pid = str(bind.get("pid") or "").strip()
        if not pid or pid in seen:
            continue
        patient = patient_by_pid.get(pid)
        if not patient:
            patient = await runtime.db.col("patient").find_one({"_id": safe_oid(pid) or pid})
        if not patient:
            continue
        if not _patient_matches_scope(patient, patient_scope):
            continue
        if not _patient_matches_department(patient, department=department, dept_code=dept_code):
            continue
        cap_hint = cap_by_device.get(str(bind.get("deviceID") or ""))
        row = await build_ventilated_patient_row(patient, bind_hint=bind, cap_hint=cap_hint, fast=True)
        if row:
            row["patient_status"] = patient.get("status")
            rows.append(row)
            seen.add(pid)

    if not rows:
        query = _append_department_scope(research_patient_scope_query(patient_scope or "in_dept"), department=department, dept_code=dept_code)
        cursor = runtime.db.col("patient").find(query).sort("hisBed", 1).limit(300)
        async for patient in cursor:
            row = await build_ventilated_patient_row(patient, fast=True)
            if row:
                rows.append(row)

    rows.sort(key=lambda row: str(row.get("bed_no") or ""))
    for row in rows:
        if row:
            row["data_source"] = f"{row.get('data_source')};primary=deviceBind"
    stats = {
        "ventilated_count": len(rows),
        "sbt_candidate_count": sum(1 for row in rows if (row.get("sbt_candidate_status") or {}).get("status") == "candidate"),
        "high_driving_pressure_count": sum(1 for row in rows if "高驱动压" in (row.get("risk_tags") or [])),
        "low_oxygenation_count": sum(1 for row in rows if "低氧合" in (row.get("risk_tags") or [])),
        "cuff_pressure_due_count": sum(1 for row in rows if "气囊压待测" in (row.get("risk_tags") or [])),
        "difficult_airway_count": sum(1 for row in rows if row.get("difficult_airway")),
        "avg_safety_score": round(sum(int(row.get("safety_score") or 0) for row in rows) / len(rows), 1) if rows else 0,
    }
    completion = _respiratory_completion(rows)
    return {
        "patients": rows,
        "stats": stats,
        "completion": completion,
        "scope": {
            "department": str(department or "").strip() or None,
            "dept_code": str(dept_code or "").strip() or None,
            "patient_scope": patient_scope or "in_dept",
        },
        "generated_at": serialize_doc(datetime.now()),
    }


async def list_sbt_candidates(*, department: str | None = None, dept_code: str | None = None, patient_scope: str = "in_dept") -> dict[str, Any]:
    dashboard = await list_ventilated_patients(department=department, dept_code=dept_code, patient_scope=patient_scope)
    rows = dashboard["patients"]
    completed_cursor = runtime.db.col("score").find({"score_type": "sbt_assessment"}).sort("trial_time", -1).limit(200)
    completed_by_patient: dict[str, dict[str, Any]] = {}
    async for doc in completed_cursor:
        completed_by_patient.setdefault(str(doc.get("patient_id")), serialize_doc(doc))
    todo = []
    not_suitable = []
    completed = []
    failed = []
    for row in rows:
        latest = completed_by_patient.get(str(row.get("patient_id")))
        if latest and latest.get("result") == "passed":
            completed.append({"patient": row, "record": latest})
        elif latest and latest.get("result") == "failed":
            failed.append({"patient": row, "record": latest, "reason": latest.get("raw_text")})
        elif (row.get("sbt_candidate_status") or {}).get("status") == "candidate":
            todo.append(row)
        else:
            not_suitable.append({"patient": row, "reasons": (row.get("sbt_candidate_status") or {}).get("reasons") or []})
    return {"todo": todo, "not_suitable": not_suitable, "completed": completed, "failed": failed, "generated_at": serialize_doc(datetime.now())}


async def update_sbt_status(patient_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    status = str(payload.get("status") or "documented").strip()
    result = "passed" if status in {"completed", "passed"} else "failed" if status in {"failed"} else "documented"
    doc = {
        "patient_id": patient_id,
        "score_type": "sbt_assessment",
        "result": result,
        "passed": result == "passed" if result in {"passed", "failed"} else None,
        "trial_time": payload.get("trial_time") or now,
        "calc_time": now,
        "source": "respiratory_dashboard",
        "raw_text": payload.get("reason") or payload.get("note") or "",
        "duration_minutes": payload.get("duration_minutes"),
        "created_by": actor,
        "updated_by": actor,
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("score").insert_one(doc)
    await write_audit_log(runtime.db, action="update_sbt_status", module="respiratory", actor=actor, target_type="patient", target_id=patient_id, detail={"status": status, "result": result})
    return {"record": serialize_doc(doc)}


async def ventilator_timeline(patient_id: str, hours: int = 72) -> dict[str, Any]:
    hours = min(max(int(hours or 72), 24), 168)
    patient = await runtime.db.col("patient").find_one({"_id": safe_oid(patient_id)})
    if not patient:
        return {"code": 404, "message": "患者不存在"}
    bind, _ = await _active_ventilator(patient)
    device_id = (bind or {}).get("deviceID")
    since = datetime.now() - timedelta(hours=hours)
    rows: list[dict[str, Any]] = []
    if device_id:
        cursor = runtime.db.col("deviceCap").find(
            {"deviceID": device_id, "code": {"$in": VENT_CODES}, "time": {"$gte": since}},
            {"time": 1, "code": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1},
        ).sort("time", 1).limit(5000)
        buckets: dict[str, dict[str, Any]] = {}
        async for doc in cursor:
            t = doc.get("time")
            key = t.replace(minute=(t.minute // 30) * 30, second=0, microsecond=0).isoformat() if isinstance(t, datetime) else str(t)
            bucket = buckets.setdefault(key, {"time": t})
            value = doc.get("fVal") if doc.get("fVal") is not None else doc.get("intVal") if doc.get("intVal") is not None else doc.get("strVal") or doc.get("value")
            bucket[doc.get("code")] = value
        for item in buckets.values():
            peep = _vent_param(item, "param_vent_measure_peep", "param_vent_peep")
            pplat = _vent_param(item, "param_vent_plat_pressure")
            rows.append(
                serialize_doc(
                    {
                        "time": item.get("time"),
                        "position": _vent_param(item, "param_TiWei"),
                        "mode": _vent_param(item, "param_HuXiMoShi", "param_vent_mode"),
                        "fio2": _vent_param(item, "param_FiO2", "param_fio2"),
                        "peep": peep,
                        "vt": _vent_param(item, "param_vent_vt", "param_vent_vti"),
                        "vt_set": _vent_param(item, "param_vent_set_vt"),
                        "peak_flow": _vent_param(item, "param_vent_set_PeakFlow"),
                        "pplat": pplat,
                        "airway_resistance": _vent_param(item, "param_qiDaoZuLi"),
                        "p01": _vent_param(item, "param_vent_P0.1"),
                        "c_stat": _vent_param(item, "param_vent_C_STAT", "param_vent_pause_C_STAT", "param_jingTaiShunYingXing"),
                        "static_compliance": _vent_param(item, "param_jingTaiShunYingXing", "param_vent_C_STAT", "param_vent_pause_C_STAT"),
                        "driving_pressure": round(float(pplat) - float(peep), 1) if _num(pplat) is not None and _num(peep) is not None else None,
                        "rr": _vent_param(item, "param_vent_resp", "param_HuXiPinLv"),
                    }
                )
            )
    return {"code": 0, "timeline": rows, "hours": hours}


async def latest_airway_record(patient_id: str) -> dict[str, Any]:
    doc = await runtime.db.col("airway_records").find_one({"patient_id": patient_id}, sort=[("recorded_at", -1), ("created_at", -1)])
    return serialize_doc(doc) if doc else {}


async def list_airway_records(patient_id: str) -> dict[str, Any]:
    cursor = runtime.db.col("airway_records").find({"patient_id": patient_id}).sort("recorded_at", -1).limit(100)
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"records": rows}


async def create_airway_record(patient_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    doc = {
        "record_id": str(uuid.uuid4()),
        "patient_id": patient_id,
        "recorded_at": payload.get("recorded_at") or now,
        "suction_count": payload.get("suction_count"),
        "sputum_character": payload.get("sputum_character"),
        "cuff_pressure": payload.get("cuff_pressure"),
        "airway_depth": payload.get("airway_depth"),
        "airway_type": payload.get("airway_type"),
        "humidification_status": payload.get("humidification_status"),
        "vap_bundle": payload.get("vap_bundle") or {},
        "note": payload.get("note") or "",
        "created_by": actor,
        "updated_by": actor,
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("airway_records").insert_one(doc)
    return {"record": serialize_doc(doc)}


async def get_airway_plan(patient_id: str) -> dict[str, Any]:
    doc = await runtime.db.col("airway_plans").find_one({"patient_id": patient_id}, sort=[("updated_at", -1)])
    if doc:
        return {"plan": serialize_doc(doc)}
    return {
        "plan": {
            "patient_id": patient_id,
            "risk_level": "unknown",
            "difficult_airway": False,
            "history": [],
            "backup_equipment": ["视频喉镜", "纤支镜", "环甲膜穿刺包"],
            "contacts": ["麻醉科", "耳鼻喉科"],
            "note": "暂无人工维护预案，展示默认流程提醒。",
            "is_default": True,
        }
    }


async def upsert_airway_plan(patient_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    doc = {
        "patient_id": patient_id,
        "risk_level": payload.get("risk_level") or "medium",
        "difficult_airway": bool(payload.get("difficult_airway", True)),
        "history": payload.get("history") or [],
        "backup_equipment": payload.get("backup_equipment") or [],
        "contacts": payload.get("contacts") or [],
        "note": payload.get("note") or "",
        "updated_by": actor,
        "updated_at": now,
    }
    existing = await runtime.db.col("airway_plans").find_one({"patient_id": patient_id})
    if existing:
        await runtime.db.col("airway_plans").update_one({"_id": existing["_id"]}, {"$set": doc})
        doc["created_at"] = existing.get("created_at")
    else:
        doc["created_by"] = actor
        doc["created_at"] = now
        await runtime.db.col("airway_plans").insert_one(doc)
    await write_audit_log(runtime.db, action="edit_airway_plan", module="respiratory", actor=actor, target_type="patient", target_id=patient_id, detail={"risk_level": doc["risk_level"], "difficult_airway": doc["difficult_airway"]})
    return {"plan": serialize_doc(doc)}
