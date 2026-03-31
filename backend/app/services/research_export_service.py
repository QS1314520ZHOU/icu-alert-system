from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from bson import ObjectId

from app import runtime
from app.utils.patient_helpers import research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

logger = logging.getLogger("icu-alert")
API_TZ = ZoneInfo("Asia/Shanghai")
EXPORT_DIR = Path("backend/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

DATA_TYPE_LABELS: dict[str, str] = {
    "patients": "患者主表",
    "outcomes": "结局表",
    "vitals": "生命体征",
    "labs": "检验结果",
    "alerts": "预警记录",
    "scores": "评分数据",
    "ai_logs": "人工智能日志",
}

DATA_DICT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "patients": [
        {"字段名": "patient_id", "中文名": "患者ID", "数据类型": "string", "单位": "", "取值范围/说明": "patient._id 脱敏或原值", "示例值": "66f0..."},
        {"字段名": "hisPid", "中文名": "住院号", "数据类型": "string", "单位": "", "取值范围/说明": "脱敏后哈希", "示例值": "a3f1..."},
        {"字段名": "name", "中文名": "姓名", "数据类型": "string", "单位": "", "取值范围/说明": "脱敏关闭时保留", "示例值": "张三"},
        {"字段名": "age", "中文名": "年龄", "数据类型": "number", "单位": "岁", "取值范围/说明": "", "示例值": 68},
        {"字段名": "sex", "中文名": "性别", "数据类型": "string", "单位": "", "取值范围/说明": "M/F", "示例值": "M"},
        {"字段名": "dept", "中文名": "科室", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "ICU"},
        {"字段名": "deptCode", "中文名": "科室编码", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "1101"},
        {"字段名": "status", "中文名": "患者状态", "数据类型": "string", "单位": "", "取值范围/说明": "admitted/discharged", "示例值": "discharged"},
        {"字段名": "primary_diagnosis", "中文名": "主要诊断", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "脓毒症"},
        {"字段名": "admission_time", "中文名": "入科时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T08:00:00+08:00"},
        {"字段名": "discharge_time", "中文名": "出科时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-05T10:00:00+08:00"},
        {"字段名": "sofa_admission", "中文名": "入科SOFA", "数据类型": "number", "单位": "分", "取值范围/说明": "", "示例值": 8},
        {"字段名": "apache2", "中文名": "APACHE II", "数据类型": "number", "单位": "分", "取值范围/说明": "", "示例值": 18},
    ],
    "outcomes": [
        {"字段名": "patient_id", "中文名": "患者ID", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "66f0..."},
        {"字段名": "hisPid", "中文名": "住院号", "数据类型": "string", "单位": "", "取值范围/说明": "脱敏后哈希", "示例值": "a3f1..."},
        {"字段名": "outcome", "中文名": "结局", "数据类型": "string", "单位": "", "取值范围/说明": "alive/dead", "示例值": "alive"},
        {"字段名": "icu_mortality", "中文名": "ICU死亡", "数据类型": "integer", "单位": "", "取值范围/说明": "0/1", "示例值": 0},
        {"字段名": "hospital_mortality", "中文名": "院内死亡", "数据类型": "integer", "单位": "", "取值范围/说明": "0/1", "示例值": 0},
        {"字段名": "mortality_28d", "中文名": "28天死亡", "数据类型": "integer", "单位": "", "取值范围/说明": "0/1", "示例值": 0},
        {"字段名": "los_icu_days", "中文名": "ICU住院天数", "数据类型": "number", "单位": "天", "取值范围/说明": "", "示例值": 5.2},
        {"字段名": "discharge_time", "中文名": "出科时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-05T10:00:00+08:00"},
    ],
    "vitals": [
        {"字段名": "patient_id", "中文名": "患者ID", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "66f0..."},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "time", "中文名": "记录时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T08:00:00+08:00"},
        {"字段名": "item_name", "中文名": "指标名称", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "心率"},
        {"字段名": "code", "中文名": "指标编码", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "param_HR"},
        {"字段名": "value_numeric", "中文名": "数值型结果", "数据类型": "float", "单位": "视指标而定", "取值范围/说明": "", "示例值": 120.5},
        {"字段名": "value_text", "中文名": "文本型结果", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": ""},
        {"字段名": "dept", "中文名": "科室", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "ICU"},
    ],
    "labs": [
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "auth_time", "中文名": "审核时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T10:00:00+08:00"},
        {"字段名": "item_name", "中文名": "检验项目", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "白细胞计数"},
        {"字段名": "result", "中文名": "结果值", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "12.3"},
        {"字段名": "unit", "中文名": "单位", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "×10⁹/L"},
        {"字段名": "dept", "中文名": "科室", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "ICU"},
    ],
    "alerts": [
        {"字段名": "patient_id", "中文名": "患者ID", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "66f0..."},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "created_at", "中文名": "预警时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T09:00:00+08:00"},
        {"字段名": "alert_type", "中文名": "预警类型", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "sepsis"},
        {"字段名": "severity", "中文名": "严重程度", "数据类型": "string", "单位": "", "取值范围/说明": "low/medium/high/critical", "示例值": "high"},
        {"字段名": "message", "中文名": "预警内容", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "疑似脓毒症"},
        {"字段名": "dept", "中文名": "科室", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "ICU"},
    ],
    "scores": [
        {"字段名": "patient_id", "中文名": "患者ID", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "66f0..."},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "time", "中文名": "评分时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T08:00:00+08:00"},
        {"字段名": "score_type", "中文名": "评分类型", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "SOFA"},
        {"字段名": "score", "中文名": "评分值", "数据类型": "float", "单位": "分", "取值范围/说明": "", "示例值": 8},
        {"字段名": "dept", "中文名": "科室", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "ICU"},
    ],
    "ai_logs": [
        {"字段名": "patient_id", "中文名": "患者ID", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "66f0..."},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "created_at", "中文名": "记录时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T09:30:00+08:00"},
        {"字段名": "model", "中文名": "模型名称", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "gpt-4o"},
        {"字段名": "module", "中文名": "模块", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "reasoning"},
        {"字段名": "input_summary", "中文名": "输入摘要", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "患者生命体征异常"},
        {"字段名": "output_summary", "中文名": "输出摘要", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "建议立即评估"},
    ],
}

DATASET_COLUMN_ORDER: dict[str, list[str]] = {
    "patients": [
        "patient_id",
        "hisPid",
        "name",
        "age",
        "sex",
        "dept",
        "deptCode",
        "status",
        "primary_diagnosis",
        "admission_time",
        "discharge_time",
        "sofa_admission",
        "apache2",
    ],
    "outcomes": [
        "patient_id",
        "hisPid",
        "outcome",
        "icu_mortality",
        "hospital_mortality",
        "mortality_28d",
        "los_icu_days",
        "discharge_time",
    ],
    "vitals": [
        "patient_id",
        "hisPid",
        "time",
        "item_name",
        "code",
        "value_numeric",
        "value_text",
        "dept",
    ],
    "labs": [
        "hisPid",
        "auth_time",
        "item_name",
        "result",
        "unit",
        "dept",
    ],
    "alerts": [
        "patient_id",
        "hisPid",
        "created_at",
        "alert_type",
        "severity",
        "message",
        "dept",
    ],
    "scores": [
        "patient_id",
        "hisPid",
        "time",
        "score_type",
        "score",
        "dept",
    ],
    "ai_logs": [
        "patient_id",
        "hisPid",
        "created_at",
        "model",
        "module",
        "input_summary",
        "output_summary",
    ],
}

FILE_BASENAME_MAP: dict[str, str] = {
    "patients": "patients_baseline",
    "outcomes": "patient_outcomes",
    "vitals": "vital_signs_long",
    "labs": "laboratory_results",
    "alerts": "alert_events",
    "scores": "clinical_scores",
    "ai_logs": "ai_activity_logs",
}

SOURCE_CONFIG: dict[str, list[dict[str, Any]]] = {
    "vitals": [
        {"db": "smartcare", "collection": "captureData", "time_fields": ["time", "recordTime", "createdAt"], "id_fields": ["hisPid", "pid"], "dept_fields": ["department", "dept", "hisDept"]},
        {"db": "smartcare", "collection": "bedside", "time_fields": ["time", "recordTime"], "id_fields": ["pid"], "dept_fields": []},
    ],
    "labs": [
        {"db": "datacenter", "collection": "VI_ICU_EXAM_ITEM", "time_fields": ["authTime", "collectTime", "reportTime", "time"], "id_fields": ["hisPid"], "dept_fields": ["department", "dept", "hisDept"]},
    ],
    "alerts": [
        {"db": "smartcare", "collection": "alert_records", "time_fields": ["created_at", "createdAt", "time"], "id_fields": ["patient_id", "hisPid", "pid"], "dept_fields": ["dept", "hisDept", "department"]},
    ],
    "scores": [
        {"db": "smartcare", "collection": "score", "time_fields": ["calc_time", "created_at", "time"], "id_fields": ["patient_id", "hisPid", "pid"], "dept_fields": ["dept", "hisDept", "department"]},
    ],
    "ai_logs": [
        {"db": "smartcare", "collection": "ai_monitor_logs", "time_fields": ["created_at", "createdAt", "time"], "id_fields": ["patient_id", "meta.patient_id", "hisPid", "meta.hisPid", "pid", "meta.pid"], "dept_fields": ["dept", "meta.dept", "department", "meta.department"]},
    ],
}


def _hash_pid(pid: str) -> str:
    return hashlib.sha256(pid.encode()).hexdigest()[:16]


def _desensitize(doc: dict[str, Any]) -> dict[str, Any]:
    doc = dict(doc)
    doc.pop("_id", None)
    for id_key in ("hisPid", "hisPID", "patient_id", "pid", "patientId"):
        if id_key in doc and doc.get(id_key) not in (None, ""):
            doc[id_key] = _hash_pid(str(doc[id_key]))
    for field in ("patientName", "name", "idCard", "phone", "mobile", "address", "contact", "contactPhone"):
        doc.pop(field, None)
    return doc


def _parse_window_endpoint(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=API_TZ)
    return dt.astimezone(timezone.utc)


def _dedupe(values: list[Any]) -> list[Any]:
    seen: set[tuple[str, str]] = set()
    out: list[Any] = []
    for item in values:
        if item in (None, ""):
            continue
        key = (type(item).__name__, str(item))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _normalize_department_scope(department: str | None, dept_code: str | None) -> tuple[str, str]:
    dept_name = str(department or "").strip()
    dept_code_text = str(dept_code or "").strip()
    if dept_name and not dept_code_text and dept_name.isdigit():
        dept_code_text = dept_name
        dept_name = ""
    if dept_name and dept_code_text and (dept_name == dept_code_text or dept_name.isdigit()):
        dept_name = ""
    return dept_name, dept_code_text


async def _resolve_cohort_scope(params: dict[str, Any]) -> tuple[list[str] | None, str | None, str | None, str, dict[str, Any] | None]:
    patient_ids = params.get("patient_ids") or None
    cohort_id = str(params.get("cohort_id") or "").strip()
    department = params.get("department")
    dept_code = params.get("dept_code")
    patient_scope = str(params.get("patient_scope") or "all").strip() or "all"
    cohort_doc: dict[str, Any] | None = None
    if cohort_id:
        query: dict[str, Any] = {"cohort_id": cohort_id}
        oid = safe_oid(cohort_id)
        if oid is not None:
            query = {"$or": [{"_id": oid}, {"cohort_id": cohort_id}]}
        cohort_doc = await runtime.db.col("research_cohorts").find_one(query)
        if cohort_doc:
            cohort_ids = cohort_doc.get("patient_ids")
            if isinstance(cohort_ids, list) and cohort_ids:
                patient_ids = [str(item).strip() for item in cohort_ids if str(item or "").strip()]
            department = department or cohort_doc.get("department")
            dept_code = dept_code or cohort_doc.get("dept_code")
            patient_scope = str(cohort_doc.get("patient_scope") or patient_scope).strip() or patient_scope
    return patient_ids, department, dept_code, patient_scope, cohort_doc


async def _build_scope(patient_ids: list[str] | None, department: str | None, dept_code: str | None, patient_scope: str) -> dict[str, Any]:
    his_pids: list[str] = []
    patient_ids_mixed: list[Any] = []
    resolved_patient_ids: list[str] = []

    dept_name, dept_code_text = _normalize_department_scope(department, dept_code)
    raw_patient_ids = [str(item).strip() for item in (patient_ids or []) if str(item or "").strip()]

    if raw_patient_ids:
        oid_values = [oid for oid in (safe_oid(token) for token in raw_patient_ids) if oid is not None]
        query_terms: list[dict[str, Any]] = []
        if oid_values:
            query_terms.append({"_id": {"$in": oid_values}})
        query_terms.append({"_id": {"$in": raw_patient_ids}})
        query_terms.append({"hisPid": {"$in": raw_patient_ids}})
        query_terms.append({"hisPID": {"$in": raw_patient_ids}})
        query = {"$or": query_terms}
    else:
        base_query = research_patient_scope_query(patient_scope)
        clauses: list[dict[str, Any]] = [base_query] if base_query else []
        if dept_name:
            clauses.append({"$or": [{"hisDept": dept_name}, {"dept": dept_name}]})
        if dept_code_text:
            clauses.append({"deptCode": dept_code_text})
        query = {} if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}

    cursor = runtime.db.col("patient").find(query, {"_id": 1, "hisPid": 1, "hisPID": 1, "hisDept": 1, "dept": 1, "deptCode": 1, "status": 1})
    preview_patients: list[dict[str, Any]] = []
    async for row in cursor:
        pid = str(row.get("_id") or "").strip()
        if pid:
            patient_ids_mixed.extend([pid, row.get("_id")])
            resolved_patient_ids.append(pid)
        for key in ("hisPid", "hisPID"):
            value = str(row.get(key) or "").strip()
            if value:
                his_pids.append(value)
        if len(preview_patients) < 5:
            preview_patients.append({
                "patient_id": pid,
                "hisPid": str(row.get("hisPid") or row.get("hisPID") or "").strip(),
                "department": str(row.get("hisDept") or row.get("dept") or "").strip() or None,
                "dept_code": str(row.get("deptCode") or "").strip() or None,
                "status": str(row.get("status") or "").strip() or None,
            })

    return {
        "his_pids": _dedupe(his_pids),
        "patient_ids": _dedupe(patient_ids_mixed),
        "resolved_patient_ids": _dedupe(resolved_patient_ids),
        "patient_count": len(_dedupe(resolved_patient_ids)),
        "department": dept_name or None,
        "dept_code": dept_code_text or None,
        "patient_scope": patient_scope,
        "preview_patients": preview_patients,
    }


def _window_string_variants(start_utc: datetime, end_utc: datetime) -> list[tuple[str, str]]:
    local_start = start_utc.astimezone(API_TZ)
    local_end = end_utc.astimezone(API_TZ)
    return [
        (local_start.isoformat(timespec="seconds"), local_end.isoformat(timespec="seconds")),
        (start_utc.isoformat(timespec="seconds"), end_utc.isoformat(timespec="seconds")),
        (start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")),
    ]


def _build_time_clause(time_fields: list[str], start_utc: datetime, end_utc: datetime) -> dict[str, Any]:
    variants = _window_string_variants(start_utc, end_utc)
    clauses: list[dict[str, Any]] = []
    for field in time_fields:
        clauses.append({field: {"$gte": start_utc, "$lte": end_utc}})
        for start_str, end_str in variants:
            clauses.append({field: {"$gte": start_str, "$lte": end_str}})
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def _build_scope_clause(source: dict[str, Any], scope: dict[str, Any], strict_scope: bool) -> dict[str, Any] | None:
    clauses: list[dict[str, Any]] = []
    id_fields = [str(field) for field in source.get("id_fields") or [] if str(field).strip()]
    candidate_values = _dedupe([*scope.get("his_pids", []), *scope.get("patient_ids", [])])
    if id_fields and candidate_values:
        for field in id_fields:
            clauses.append({field: {"$in": candidate_values}})

    dept_fields = [str(field) for field in source.get("dept_fields") or [] if str(field).strip()]
    department = scope.get("department")
    if department and dept_fields:
        for field in dept_fields:
            clauses.append({field: department})

    if not clauses:
        if strict_scope:
            return {"_id": {"$exists": False}}
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


async def _fetch_from_source(source: dict[str, Any], scope: dict[str, Any], time_range: dict[str, Any], strict_scope: bool, limit: int | None = None) -> list[dict[str, Any]]:
    start_utc = _parse_window_endpoint(time_range["start"])
    end_utc = _parse_window_endpoint(time_range["end"])
    if end_utc < start_utc:
        start_utc, end_utc = end_utc, start_utc

    clauses: list[dict[str, Any]] = []
    time_clause = _build_time_clause([str(field) for field in source.get("time_fields") or [] if str(field).strip()], start_utc, end_utc)
    if time_clause:
        clauses.append(time_clause)
    scope_clause = _build_scope_clause(source, scope, strict_scope)
    if scope_clause:
        clauses.append(scope_clause)
    query = {} if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}

    db_type = str(source.get("db") or "smartcare")
    col_name = str(source.get("collection") or "").strip()
    col = runtime.db.col(col_name) if db_type == "smartcare" else runtime.db.dc_col(col_name)
    cursor = col.find(query)
    if limit:
        cursor = cursor.limit(limit)
    docs = [serialize_doc(doc) async for doc in cursor]
    return docs


async def _fetch_raw_data(data_type: str, scope: dict[str, Any], time_range: dict[str, Any], strict_scope: bool, limit: int | None = None) -> list[dict[str, Any]]:
    for source in SOURCE_CONFIG.get(data_type, []):
        docs = await _fetch_from_source(source, scope, time_range, strict_scope, limit=limit)
        if docs:
            return docs
    return []


async def _fetch_patient_rows(scope: dict[str, Any], *, outcomes_only: bool = False) -> list[dict[str, Any]]:
    patient_ids = [pid for pid in scope.get("resolved_patient_ids", []) if pid]
    if not patient_ids:
        return []
    oid_values = [oid for oid in (safe_oid(pid) for pid in patient_ids) if oid is not None]
    query = {"_id": {"$in": oid_values}} if oid_values else {"_id": {"$in": patient_ids}}
    projection = {
        "_id": 1,
        "hisPid": 1,
        "hisPID": 1,
        "name": 1,
        "sex": 1,
        "gender": 1,
        "age": 1,
        "hisDept": 1,
        "dept": 1,
        "deptCode": 1,
        "status": 1,
        "outcome": 1,
        "icu_mortality": 1,
        "hospital_mortality": 1,
        "mortality_28d": 1,
        "mortality28d": 1,
        "los_icu_days": 1,
        "apache2": 1,
        "sofa_admission": 1,
        "admissionTime": 1,
        "icuAdmissionTime": 1,
        "dischargeTime": 1,
        "icuDischargeTime": 1,
        "clinicalDiagnosis": 1,
        "admissionDiagnosis": 1,
        "diagnosis": 1,
    }
    rows = []
    async for doc in runtime.db.col("patient").find(query, projection):
        row = serialize_doc(doc)
        if outcomes_only:
            rows.append({
                "patient_id": str(row.get("_id") or ""),
                "hisPid": row.get("hisPid") or row.get("hisPID"),
                "outcome": row.get("outcome") or row.get("status"),
                "icu_mortality": row.get("icu_mortality"),
                "hospital_mortality": row.get("hospital_mortality"),
                "mortality_28d": row.get("mortality_28d") or row.get("mortality28d"),
                "los_icu_days": row.get("los_icu_days"),
                "discharge_time": row.get("icuDischargeTime") or row.get("dischargeTime"),
            })
        else:
            rows.append({
                "patient_id": str(row.get("_id") or ""),
                "hisPid": row.get("hisPid") or row.get("hisPID"),
                "name": row.get("name"),
                "age": row.get("age"),
                "sex": row.get("sex") or row.get("gender"),
                "dept": row.get("hisDept") or row.get("dept"),
                "deptCode": row.get("deptCode"),
                "status": row.get("status"),
                "primary_diagnosis": row.get("clinicalDiagnosis") or row.get("admissionDiagnosis") or row.get("diagnosis"),
                "admission_time": row.get("icuAdmissionTime") or row.get("admissionTime"),
                "discharge_time": row.get("icuDischargeTime") or row.get("dischargeTime"),
                "sofa_admission": row.get("sofa_admission"),
                "apache2": row.get("apache2"),
            })
    return rows


async def _fetch_data(data_type: str, export_mode: str, scope: dict[str, Any], time_range: dict[str, Any], strict_scope: bool, limit: int | None = None) -> list[dict[str, Any]]:
    if data_type == "patients":
        return await _fetch_patient_rows(scope, outcomes_only=False)
    if data_type == "outcomes":
        return await _fetch_patient_rows(scope, outcomes_only=True)
    return await _fetch_raw_data(data_type, scope, time_range, strict_scope, limit=limit)


def _to_dataframe(docs: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(docs)


def _write_parquet(df: pd.DataFrame, buf: io.BytesIO) -> None:
    df.to_parquet(buf, index=False, engine="pyarrow")


def _apply_column_order(data_type: str, df: pd.DataFrame, export_mode: str) -> pd.DataFrame:
    if export_mode != "dataset" or df.empty:
        return df
    preferred = DATASET_COLUMN_ORDER.get(data_type, [])
    if not preferred:
        return df
    existing = [col for col in preferred if col in df.columns]
    remaining = [col for col in df.columns if col not in existing]
    return df[existing + remaining]


def _pick_first(doc: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = doc.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_export_docs(data_type: str, docs: list[dict[str, Any]], export_mode: str) -> list[dict[str, Any]]:
    if export_mode != "dataset":
        return docs

    normalized: list[dict[str, Any]] = []
    for doc in docs:
        row = dict(doc)
        if data_type == "vitals":
            normalized.append(
                {
                    "patient_id": _pick_first(row, ["patient_id", "patientId", "pid"]),
                    "hisPid": _pick_first(row, ["hisPid", "hisPID"]),
                    "time": _pick_first(row, ["time", "recordTime", "createdAt"]),
                    "item_name": _pick_first(row, ["itemName", "name", "code"]),
                    "code": _pick_first(row, ["code"]),
                    "value_numeric": _pick_first(row, ["fVal", "intVal", "value"]),
                    "value_text": _pick_first(row, ["strVal"]),
                    "dept": _pick_first(row, ["department", "dept", "hisDept"]),
                }
            )
            continue
        if data_type == "labs":
            normalized.append(
                {
                    "hisPid": _pick_first(row, ["hisPid", "hisPID"]),
                    "auth_time": _pick_first(row, ["authTime", "collectTime", "reportTime", "time"]),
                    "item_name": _pick_first(row, ["itemName", "name"]),
                    "result": _pick_first(row, ["result", "value"]),
                    "unit": _pick_first(row, ["unit"]),
                    "dept": _pick_first(row, ["department", "dept", "hisDept"]),
                }
            )
            continue
        if data_type == "alerts":
            normalized.append(
                {
                    "patient_id": _pick_first(row, ["patient_id", "pid"]),
                    "hisPid": _pick_first(row, ["hisPid", "hisPID"]),
                    "created_at": _pick_first(row, ["created_at", "createdAt", "time"]),
                    "alert_type": _pick_first(row, ["alertType", "alert_type", "type"]),
                    "severity": _pick_first(row, ["severity", "level"]),
                    "message": _pick_first(row, ["message", "content", "summary"]),
                    "dept": _pick_first(row, ["department", "dept", "hisDept"]),
                }
            )
            continue
        if data_type == "scores":
            normalized.append(
                {
                    "patient_id": _pick_first(row, ["patient_id", "patientId", "pid"]),
                    "hisPid": _pick_first(row, ["hisPid", "hisPID"]),
                    "time": _pick_first(row, ["calc_time", "created_at", "time"]),
                    "score_type": _pick_first(row, ["scoreType", "score_type", "type"]),
                    "score": _pick_first(row, ["score", "value", "risk_score"]),
                    "dept": _pick_first(row, ["department", "dept", "hisDept"]),
                }
            )
            continue
        if data_type == "ai_logs":
            normalized.append(
                {
                    "patient_id": _pick_first(row, ["patient_id", "pid"]),
                    "hisPid": _pick_first(row, ["hisPid", "hisPID"]),
                    "created_at": _pick_first(row, ["created_at", "createdAt", "time"]),
                    "model": _pick_first(row, ["model", "model_name"]),
                    "module": _pick_first(row, ["module"]),
                    "input_summary": _pick_first(row, ["input_summary", "prompt_summary", "summary"]),
                    "output_summary": _pick_first(row, ["output_summary", "response_summary", "result_summary"]),
                }
            )
            continue
        normalized.append(row)
    return normalized


def _scope_summary(params: dict[str, Any], scope: dict[str, Any], cohort_doc: dict[str, Any] | None) -> dict[str, Any]:
    start = str((params.get("time_range") or {}).get("start") or "")
    end = str((params.get("time_range") or {}).get("end") or "")
    return {
        "cohort_id": str(params.get("cohort_id") or "").strip() or None,
        "cohort_name": str((cohort_doc or {}).get("name") or "").strip() or None,
        "patient_scope": scope.get("patient_scope") or str(params.get("patient_scope") or "all"),
        "department": scope.get("department") or None,
        "dept_code": scope.get("dept_code") or None,
        "patient_count": int(scope.get("patient_count") or 0),
        "time_range": {"start": start, "end": end},
        "export_mode": str(params.get("export_mode") or "dataset"),
    }


def _warning_messages(scope_summary: dict[str, Any], estimates: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    patient_count = int(scope_summary.get("patient_count") or 0)
    if patient_count == 0:
        warnings.append("当前范围内没有患者，导出结果将为空。")
    elif patient_count < 20:
        warnings.append(f"当前患者数较少（n={patient_count}），部分分析型数据可能非常稀疏。")
    empty_types = [item.get("label") for item in estimates if int(item.get("row_count") or 0) == 0]
    if empty_types:
        warnings.append(f"以下数据类型当前时间窗内没有命中：{'、'.join([str(x) for x in empty_types if x])}。")
    return warnings


def _quality_summary_rows(scope_summary: dict[str, Any], estimates: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {"类别": "范围", "项目": "患者范围", "值": str(scope_summary.get("patient_scope") or "all")},
        {"类别": "范围", "项目": "患者数", "值": int(scope_summary.get("patient_count") or 0)},
        {"类别": "范围", "项目": "科室", "值": str(scope_summary.get("department") or "全部科室")},
        {"类别": "范围", "项目": "导出模式", "值": str(scope_summary.get("export_mode") or "dataset")},
    ]
    for item in estimates:
        rows.append(
            {
                "类别": "数据类型",
                "项目": str(item.get("label") or item.get("data_type") or ""),
                "值": int(item.get("row_count") or 0),
            }
        )
    for idx, warning in enumerate(warnings, start=1):
        rows.append({"类别": "风险提示", "项目": f"warning_{idx}", "值": warning})
    return rows


def _build_readme_text(scope_summary: dict[str, Any], estimates: list[dict[str, Any]], warnings: list[str]) -> str:
    lines = [
        "ICU 科研导出说明",
        "",
        f"导出模式: {scope_summary.get('export_mode') or 'dataset'}",
        f"患者范围: {scope_summary.get('patient_scope') or 'all'}",
        f"患者数: {int(scope_summary.get('patient_count') or 0)}",
        f"科室: {scope_summary.get('department') or '全部科室'}",
        f"队列: {scope_summary.get('cohort_name') or '未指定队列'}",
        f"时间范围: {((scope_summary.get('time_range') or {}).get('start') or '—')} ~ {((scope_summary.get('time_range') or {}).get('end') or '—')}",
        "",
        "文件摘要:",
    ]
    for item in estimates:
        lines.append(f"- {item.get('file_name')}: {item.get('label') or item.get('data_type')} / {int(item.get('row_count') or 0)} 行")
    if warnings:
        lines.extend(["", "风险提示:"])
        lines.extend([f"- {text}" for text in warnings])
    return "\n".join(lines)


async def preview_export(params: dict[str, Any]) -> dict[str, Any]:
    patient_ids, department, dept_code, patient_scope, cohort_doc = await _resolve_cohort_scope(params)
    scope = await _build_scope(patient_ids, department, dept_code, patient_scope)
    data_types = [str(item).strip() for item in (params.get("data_types") or []) if str(item).strip()]
    export_mode = str(params.get("export_mode") or "dataset")
    time_range = params.get("time_range") or {}
    strict_scope = bool(scope.get("patient_ids") or scope.get("his_pids") or scope.get("department") or scope.get("dept_code"))
    estimates: list[dict[str, Any]] = []
    for data_type in data_types:
        docs = await _fetch_data(data_type, export_mode, scope, time_range, strict_scope, limit=3000)
        estimates.append({
            "data_type": data_type,
            "label": DATA_TYPE_LABELS.get(data_type, data_type),
            "row_count": int(len(docs)),
            "is_empty": len(docs) == 0,
        })
    summary = _scope_summary(params, scope, cohort_doc)
    return {
        "scope_summary": summary,
        "data_type_estimates": estimates,
        "warnings": _warning_messages(summary, estimates),
        "preview_patients": scope.get("preview_patients") or [],
    }


async def run_export_task(task_id: str, params: dict[str, Any], created_by: str) -> None:
    col = runtime.db.col("research_export_tasks")
    await col.update_one({"task_id": task_id}, {"$set": {"status": "processing", "progress": 5}})
    try:
        patient_ids, department, dept_code, patient_scope, cohort_doc = await _resolve_cohort_scope(params)
        scope = await _build_scope(patient_ids, department, dept_code, patient_scope)
        data_types = [str(item).strip() for item in (params.get("data_types") or []) if str(item).strip()]
        export_mode = str(params.get("export_mode") or "dataset")
        time_range = params["time_range"]
        fmt = str(params.get("format") or "csv")
        desensitize = bool(params.get("desensitize", True))
        include_data_dict = bool(params.get("include_data_dict", True))
        strict_scope = bool(scope.get("patient_ids") or scope.get("his_pids") or scope.get("department") or scope.get("dept_code"))

        timestamp = datetime.now(API_TZ).strftime("%Y%m%d_%H%M%S")
        zip_name = f"research_export_{timestamp}.zip"
        zip_path = EXPORT_DIR / zip_name
        total = max(1, len(data_types))
        export_summary_rows: list[dict[str, Any]] = []
        summary = _scope_summary(params, scope, cohort_doc)
        warnings = _warning_messages(summary, export_summary_rows)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            meta_buf = io.StringIO()
            pd.DataFrame([summary]).to_csv(meta_buf, index=False, encoding="utf-8-sig")
            zf.writestr("scope_summary.csv", meta_buf.getvalue().encode("utf-8-sig"))

            for i, data_type in enumerate(data_types):
                docs = await _fetch_data(data_type, export_mode, scope, time_range, strict_scope)
                docs = _normalize_export_docs(data_type, docs, export_mode)
                if desensitize:
                    docs = [_desensitize(doc) for doc in docs]
                df = _apply_column_order(data_type, _to_dataframe(docs), export_mode)
                row_count = len(df.index)
                file_stem = DATA_TYPE_LABELS.get(data_type, data_type)
                base_name = FILE_BASENAME_MAP.get(data_type, data_type)
                mode_prefix = "dataset" if export_mode == "dataset" else "raw"
                data_filename = f"{mode_prefix}_{base_name}.parquet" if fmt == "parquet" else f"{mode_prefix}_{base_name}.csv"

                if fmt == "parquet":
                    parquet_df = df if len(df.columns) > 0 else pd.DataFrame({"_empty": []})
                    buf = io.BytesIO()
                    _write_parquet(parquet_df, buf)
                    zf.writestr(data_filename, buf.getvalue())
                else:
                    buf = io.StringIO()
                    df.to_csv(buf, index=False, encoding="utf-8-sig")
                    zf.writestr(data_filename, buf.getvalue().encode("utf-8-sig"))

                export_summary_rows.append({
                    "data_type": data_type,
                    "label": file_stem,
                    "file_name": data_filename,
                    "row_count": int(row_count),
                    "is_empty": bool(row_count == 0),
                })

                if include_data_dict and data_type in DATA_DICT_TEMPLATES:
                    dict_df = pd.DataFrame(DATA_DICT_TEMPLATES[data_type])
                    dict_buf = io.StringIO()
                    dict_df.to_csv(dict_buf, index=False, encoding="utf-8-sig")
                    zf.writestr(f"data_dictionary_{data_type}.csv", dict_buf.getvalue().encode("utf-8-sig"))

                progress = min(95, int((i + 1) / total * 90) + 5)
                await col.update_one({"task_id": task_id}, {"$set": {"progress": progress}})

            warnings = _warning_messages(summary, export_summary_rows)
            summary_df = pd.DataFrame(export_summary_rows)
            summary_buf = io.StringIO()
            summary_df.to_csv(summary_buf, index=False, encoding="utf-8-sig")
            zf.writestr("export_summary.csv", summary_buf.getvalue().encode("utf-8-sig"))
            quality_df = pd.DataFrame(_quality_summary_rows(summary, export_summary_rows, warnings))
            quality_buf = io.StringIO()
            quality_df.to_csv(quality_buf, index=False, encoding="utf-8-sig")
            zf.writestr("export_quality_summary.csv", quality_buf.getvalue().encode("utf-8-sig"))
            if warnings:
                zf.writestr("export_warnings.txt", "\n".join(warnings).encode("utf-8"))
            zf.writestr("README.txt", _build_readme_text(summary, export_summary_rows, warnings).encode("utf-8"))
            manifest = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "scope_summary": summary,
                "result_stats": export_summary_rows,
                "warnings": warnings,
                "created_by": created_by,
            }
            zf.writestr("export_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))

        await col.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "completed",
                "progress": 100,
                "file_path": str(zip_path),
                "completed_at": datetime.now(timezone.utc),
                "result_stats": export_summary_rows,
                "scope_summary": summary,
                "warnings": warnings,
                "preview_patients": scope.get("preview_patients", []),
                "scope_stats": {
                    "his_pid_count": len(scope.get("his_pids", [])),
                    "patient_id_count": len(scope.get("patient_ids", [])),
                },
            }},
        )
    except Exception as exc:
        logger.exception("Export task %s failed: %s", task_id, exc)
        await col.update_one({"task_id": task_id}, {"$set": {"status": "failed", "error": str(exc)}})
