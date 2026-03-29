from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

import pandas as pd
from bson import ObjectId

from app import runtime
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")
API_TZ = ZoneInfo("Asia/Shanghai")
EXPORT_DIR = Path("backend/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

DATA_DICT_TEMPLATES: dict[str, list[dict]] = {
    "vitals": [
        {"字段名": "time", "中文名": "记录时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T08:00:00+08:00"},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "bedNo", "中文名": "床位号", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "ICU-01"},
        {"字段名": "fVal", "中文名": "数值", "数据类型": "float", "单位": "视指标而定", "取值范围/说明": "", "示例值": "120.5"},
        {"字段名": "itemName", "中文名": "指标名称", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "心率"},
    ],
    "labs": [
        {"字段名": "authTime", "中文名": "审核时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T10:00:00+08:00"},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "itemName", "中文名": "检验项目", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "白细胞计数"},
        {"字段名": "result", "中文名": "结果值", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "12.3"},
        {"字段名": "unit", "中文名": "单位", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "×10⁹/L"},
    ],
    "alerts": [
        {"字段名": "createdAt", "中文名": "预警时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T09:00:00+08:00"},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "alertType", "中文名": "预警类型", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "sepsis"},
        {"字段名": "severity", "中文名": "严重程度", "数据类型": "string", "单位": "", "取值范围/说明": "low/medium/high/critical", "示例值": "high"},
        {"字段名": "message", "中文名": "预警内容", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "疑似脓毒症"},
    ],
    "scores": [
        {"字段名": "time", "中文名": "评分时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T08:00:00+08:00"},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "scoreType", "中文名": "评分类型", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "SOFA"},
        {"字段名": "score", "中文名": "评分值", "数据类型": "float", "单位": "分", "取值范围/说明": "", "示例值": "8"},
    ],
    "ai_logs": [
        {"字段名": "createdAt", "中文名": "记录时间", "数据类型": "datetime", "单位": "", "取值范围/说明": "ISO8601", "示例值": "2025-01-01T09:30:00+08:00"},
        {"字段名": "hisPid", "中文名": "住院号(脱敏)", "数据类型": "string", "单位": "", "取值范围/说明": "SHA256哈希", "示例值": "a3f1..."},
        {"字段名": "model", "中文名": "模型名称", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "gpt-4o"},
        {"字段名": "input_summary", "中文名": "输入摘要", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "患者生命体征异常"},
        {"字段名": "output_summary", "中文名": "输出摘要", "数据类型": "string", "单位": "", "取值范围/说明": "", "示例值": "建议立即评估"},
    ],
}

SOURCE_CONFIG: dict[str, list[dict[str, Any]]] = {
    # 先走历史结构（captureData），没有命中时回退到 bedside。
    "vitals": [
        {
            "db": "smartcare",
            "collection": "captureData",
            "time_fields": ["time", "recordTime", "createdAt"],
            "id_fields": ["hisPid", "pid"],
            "dept_fields": ["department", "dept", "hisDept"],
        },
        {
            "db": "smartcare",
            "collection": "bedside",
            "time_fields": ["time", "recordTime"],
            "id_fields": ["pid"],
            "dept_fields": [],
        },
    ],
    "labs": [
        {
            "db": "datacenter",
            "collection": "VI_ICU_EXAM_ITEM",
            "time_fields": ["authTime", "collectTime", "reportTime", "time"],
            "id_fields": ["hisPid"],
            "dept_fields": ["department", "dept", "hisDept"],
        }
    ],
    "alerts": [
        {
            "db": "smartcare",
            "collection": "alert_records",
            "time_fields": ["created_at", "createdAt", "time"],
            "id_fields": ["patient_id", "hisPid", "pid"],
            "dept_fields": ["dept", "hisDept", "department"],
        }
    ],
    "scores": [
        {
            "db": "smartcare",
            "collection": "score_records",
            "time_fields": ["calc_time", "created_at", "time"],
            "id_fields": ["patient_id", "hisPid", "pid"],
            "dept_fields": ["dept", "hisDept", "department"],
        }
    ],
    "ai_logs": [
        {
            "db": "smartcare",
            "collection": "ai_monitor_logs",
            "time_fields": ["created_at", "createdAt", "time"],
            "id_fields": ["patient_id", "meta.patient_id", "hisPid", "meta.hisPid", "pid", "meta.pid"],
            "dept_fields": ["dept", "meta.dept", "department", "meta.department"],
        }
    ],
}


def _hash_pid(pid: str) -> str:
    return hashlib.sha256(pid.encode()).hexdigest()[:16]


def _desensitize(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    for id_key in ("hisPid", "hisPID", "patient_id", "pid"):
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


def _is_object_id(value: str) -> bool:
    text = str(value or "").strip()
    return len(text) == 24 and all(ch in "0123456789abcdefABCDEF" for ch in text)


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


async def _build_scope(patient_ids: list[str] | None, department: str | None) -> dict[str, list[Any]]:
    his_pids: list[str] = []
    patient_ids_mixed: list[Any] = []

    raw_patient_ids = patient_ids or []
    oid_candidates: list[ObjectId] = []
    for raw in raw_patient_ids:
        token = str(raw or "").strip()
        if not token:
            continue
        if _is_object_id(token):
            oid = ObjectId(token)
            oid_candidates.append(oid)
            patient_ids_mixed.extend([token, oid])
        else:
            his_pids.append(token)

    if oid_candidates:
        cursor = runtime.db.col("patient").find({"_id": {"$in": oid_candidates}}, {"hisPid": 1, "hisPID": 1})
        async for row in cursor:
            for key in ("hisPid", "hisPID"):
                value = str(row.get(key) or "").strip()
                if value:
                    his_pids.append(value)

    if department:
        query = {"$or": [{"hisDept": department}, {"dept": department}]}
        cursor = runtime.db.col("patient").find(query, {"_id": 1, "hisPid": 1, "hisPID": 1})
        async for row in cursor:
            oid = row.get("_id")
            if oid is not None:
                patient_ids_mixed.extend([str(oid), oid])
            for key in ("hisPid", "hisPID"):
                value = str(row.get(key) or "").strip()
                if value:
                    his_pids.append(value)

    return {
        "his_pids": _dedupe(his_pids),
        "patient_ids": _dedupe(patient_ids_mixed),
    }


def _window_string_variants(start_utc: datetime, end_utc: datetime) -> list[tuple[str, str]]:
    local_start = start_utc.astimezone(API_TZ)
    local_end = end_utc.astimezone(API_TZ)
    return [
        (local_start.isoformat(timespec="seconds"), local_end.isoformat(timespec="seconds")),
        (start_utc.isoformat(timespec="seconds"), end_utc.isoformat(timespec="seconds")),
        (start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")),
    ]


def _build_time_clause(time_fields: list[str], start_utc: datetime, end_utc: datetime) -> dict:
    variants = _window_string_variants(start_utc, end_utc)
    clauses: list[dict] = []
    for field in time_fields:
        clauses.append({field: {"$gte": start_utc, "$lte": end_utc}})
        for start_str, end_str in variants:
            clauses.append({field: {"$gte": start_str, "$lte": end_str}})
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def _build_scope_clause(
    source: dict[str, Any],
    scope: dict[str, list[Any]],
    *,
    department: str | None,
    strict_scope: bool,
) -> dict | None:
    clauses: list[dict] = []

    id_fields = [str(field) for field in source.get("id_fields") or [] if str(field).strip()]
    if id_fields:
        candidate_values = _dedupe([*scope.get("his_pids", []), *scope.get("patient_ids", [])])
        if candidate_values:
            for field in id_fields:
                clauses.append({field: {"$in": candidate_values}})

    dept_fields = [str(field) for field in source.get("dept_fields") or [] if str(field).strip()]
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


async def _fetch_from_source(
    source: dict[str, Any],
    scope: dict[str, list[Any]],
    *,
    department: str | None,
    time_range: dict,
    strict_scope: bool,
) -> list[dict]:
    start_utc = _parse_window_endpoint(time_range["start"])
    end_utc = _parse_window_endpoint(time_range["end"])
    if end_utc < start_utc:
        start_utc, end_utc = end_utc, start_utc

    time_fields = [str(field) for field in source.get("time_fields") or [] if str(field).strip()]
    clauses = []
    time_clause = _build_time_clause(time_fields, start_utc, end_utc)
    if time_clause:
        clauses.append(time_clause)

    scope_clause = _build_scope_clause(source, scope, department=department, strict_scope=strict_scope)
    if scope_clause:
        clauses.append(scope_clause)

    if not clauses:
        query: dict = {}
    elif len(clauses) == 1:
        query = clauses[0]
    else:
        query = {"$and": clauses}

    db_type = str(source.get("db") or "smartcare")
    col_name = str(source.get("collection") or "").strip()
    if not col_name:
        return []
    col = runtime.db.col(col_name) if db_type == "smartcare" else runtime.db.dc_col(col_name)

    docs: list[dict] = []
    async for doc in col.find(query).batch_size(500):
        docs.append(serialize_doc(doc))
    return docs


async def _fetch_data(
    data_type: str,
    scope: dict[str, list[Any]],
    department: str | None,
    time_range: dict,
    *,
    strict_scope: bool,
) -> list[dict]:
    for source in SOURCE_CONFIG.get(data_type, []):
        docs = await _fetch_from_source(
            source,
            scope,
            department=department,
            time_range=time_range,
            strict_scope=strict_scope,
        )
        if docs:
            return docs
    return []


def _to_dataframe(docs: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(docs)


def _write_parquet(df: pd.DataFrame, path: Any) -> None:
    df.to_parquet(path, index=False, engine="pyarrow")


async def run_export_task(task_id: str, params: dict, created_by: str) -> None:
    col = runtime.db.col("research_export_tasks")
    await col.update_one({"task_id": task_id}, {"$set": {"status": "processing", "progress": 0}})

    try:
        data_types: list[str] = params["data_types"]
        patient_ids: list[str] | None = params.get("patient_ids") or None
        department: str | None = params.get("department")
        time_range: dict = params["time_range"]
        fmt: str = params.get("format", "csv")
        desensitize: bool = params.get("desensitize", True)
        include_data_dict: bool = params.get("include_data_dict", True)
        strict_scope = bool(patient_ids or department)
        scope = await _build_scope(patient_ids, department)

        timestamp = datetime.now(API_TZ).strftime("%Y%m%d_%H%M%S")
        zip_name = f"research_export_{timestamp}.zip"
        zip_path = EXPORT_DIR / zip_name

        total = len(data_types)
        export_summary_rows: list[dict[str, Any]] = []
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, data_type in enumerate(data_types):
                docs = await _fetch_data(
                    data_type,
                    scope,
                    department,
                    time_range,
                    strict_scope=strict_scope,
                )
                if desensitize:
                    docs = [_desensitize(d) for d in docs]
                df = _to_dataframe(docs)
                row_count = len(df.index)
                data_filename = f"{data_type}.parquet" if fmt == "parquet" else f"{data_type}.csv"

                if fmt == "parquet":
                    # pyarrow 在 0 列 DataFrame 上会失败，空结果时写入占位列保证文件可读。
                    parquet_df = df if len(df.columns) > 0 else pd.DataFrame({"_empty": []})
                    buf = io.BytesIO()
                    _write_parquet(parquet_df, buf)
                    zf.writestr(data_filename, buf.getvalue())
                else:
                    buf = io.StringIO()
                    df.to_csv(buf, index=False, encoding="utf-8-sig")
                    zf.writestr(data_filename, buf.getvalue().encode("utf-8-sig"))

                export_summary_rows.append(
                    {
                        "data_type": data_type,
                        "file_name": data_filename,
                        "row_count": int(row_count),
                        "is_empty": bool(row_count == 0),
                    }
                )

                if include_data_dict and data_type in DATA_DICT_TEMPLATES:
                    dict_df = pd.DataFrame(DATA_DICT_TEMPLATES[data_type])
                    dict_buf = io.StringIO()
                    dict_df.to_csv(dict_buf, index=False, encoding="utf-8-sig")
                    zf.writestr(f"data_dictionary_{data_type}.csv", dict_buf.getvalue().encode("utf-8-sig"))

                progress = int((i + 1) / total * 100)
                await col.update_one({"task_id": task_id}, {"$set": {"progress": progress}})

            summary_df = pd.DataFrame(export_summary_rows)
            summary_buf = io.StringIO()
            summary_df.to_csv(summary_buf, index=False, encoding="utf-8-sig")
            zf.writestr("export_summary.csv", summary_buf.getvalue().encode("utf-8-sig"))

        await col.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "completed",
                    "progress": 100,
                    "file_path": str(zip_path),
                    "completed_at": datetime.now(timezone.utc),
                    "result_stats": export_summary_rows,
                    "scope_stats": {
                        "his_pid_count": len(scope.get("his_pids", [])),
                        "patient_id_count": len(scope.get("patient_ids", [])),
                    },
                }
            },
        )
    except Exception as e:
        logger.exception(f"Export task {task_id} failed: {e}")
        await col.update_one({"task_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
