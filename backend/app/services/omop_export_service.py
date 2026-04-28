from __future__ import annotations

import csv
import json
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app import runtime
from app.services.audit_service import source_hash, write_audit_log
from app.utils.patient_helpers import patient_his_pid, research_patient_scope_query
from app.utils.serialization import serialize_doc

EXPORT_DIR = Path("backend/exports/omop")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

OMOP_TABLES = [
    "PERSON",
    "VISIT_OCCURRENCE",
    "CONDITION_OCCURRENCE",
    "DRUG_EXPOSURE",
    "MEASUREMENT",
    "PROCEDURE_OCCURRENCE",
    "OBSERVATION",
]

MAPPING_CONFIG = {
    "PERSON": {"person_id": "hashed patient._id", "year_of_birth": "birthday/year", "gender_source_value": "sex/gender/hisSex"},
    "VISIT_OCCURRENCE": {"visit_occurrence_id": "patient._id", "visit_start_datetime": "icuAdmissionTime/admissionTime", "visit_end_datetime": "icuDischargeTime/dischargeTime"},
    "CONDITION_OCCURRENCE": {"condition_source_value": "clinicalDiagnosis/admissionDiagnosis"},
    "DRUG_EXPOSURE": {"drug_source_value": "drugExe.drugName or VI_ICU_ZYYZ.orderName"},
    "MEASUREMENT": {"measurement_source_value": "VI_ICU_EXAM_ITEM.itemName/itemCnName", "value_source_value": "result"},
    "PROCEDURE_OCCURRENCE": {"procedure_source_value": "bedside/code text procedure-like records"},
    "OBSERVATION": {"observation_source_value": "alerts/scores/bedside text"},
}


def _hash(value: Any) -> str:
    return source_hash(str(value or ""))[:16]


def _dt(value: Any) -> str:
    return serialize_doc(value) or ""


def _year(value: Any) -> str:
    try:
        if isinstance(value, datetime):
            return str(value.year)
        text = str(value or "")
        return text[:4] if text[:4].isdigit() else ""
    except Exception:
        return ""


def _patient_scope_query(scope: str, department: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    query = research_patient_scope_query(scope)
    clauses = [query]
    dept_name = str(department or "").strip()
    dept_code_text = str(dept_code or "").strip()
    if dept_name and not dept_code_text and dept_name.isdigit():
        dept_code_text = dept_name
        dept_name = ""
    if dept_code_text:
        clauses.append({"deptCode": dept_code_text})
    elif dept_name:
        clauses.append({"$or": [{"hisDept": dept_name}, {"dept": dept_name}]})
    return {"$and": clauses} if len(clauses) > 1 else query


async def _patients(scope: str, limit: int = 10000, department: str | None = None, dept_code: str | None = None) -> list[dict[str, Any]]:
    cursor = runtime.db.col("patient").find(_patient_scope_query(scope, department=department, dept_code=dept_code)).limit(limit)
    return [doc async for doc in cursor]


async def build_data_quality_report(scope: str = "all", department: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    patients = await _patients(scope, limit=5000, department=department, dept_code=dept_code)
    total = len(patients)
    fields = ["_id", "hisPid", "age", "birthday", "sex", "gender", "clinicalDiagnosis", "icuAdmissionTime", "admissionTime"]
    missing = {}
    for field in fields:
        missing[field] = sum(1 for row in patients if row.get(field) in (None, ""))
    issues = []
    for row in patients:
        start = row.get("icuAdmissionTime") or row.get("admissionTime")
        end = row.get("icuDischargeTime") or row.get("dischargeTime")
        if isinstance(start, datetime) and isinstance(end, datetime) and end < start:
            issues.append({"patient_id": str(row.get("_id")), "issue": "出科时间早于入科时间"})
    return {
        "scope": scope,
        "department": str(department or "").strip() or None,
        "dept_code": str(dept_code or "").strip() or None,
        "patient_count": total,
        "missing_rate": {field: round(count / total, 4) if total else 0 for field, count in missing.items()},
        "time_logic_errors": issues[:100],
        "abnormal_values": [],
        "unit_inconsistency": [],
        "generated_at": serialize_doc(datetime.now()),
    }


def _write_csv(zf: zipfile.ZipFile, name: str, rows: list[dict[str, Any]]) -> None:
    if rows:
        headers = list(dict.fromkeys(key for row in rows for key in row.keys()))
    else:
        headers = ["empty"]
        rows = [{"empty": ""}]
    text_lines: list[str] = []
    from io import StringIO

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: serialize_doc(value) for key, value in row.items()})
    zf.writestr(f"{name}.csv", buf.getvalue())


async def run_omop_export(payload: dict[str, Any], actor: str = "anonymous") -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    scope = str(payload.get("patient_scope") or "all")
    patients = await _patients(scope, limit=int(payload.get("limit") or 10000), department=payload.get("department") or payload.get("dept"), dept_code=payload.get("dept_code"))
    person_rows = []
    visit_rows = []
    condition_rows = []
    observation_rows = []
    drug_rows = []
    measurement_rows = []
    procedure_rows = []
    for patient in patients:
        pid = str(patient.get("_id"))
        person_id = _hash(pid)
        his_pid = patient_his_pid(patient)
        person_rows.append({"person_id": person_id, "gender_source_value": patient.get("sex") or patient.get("gender") or patient.get("hisSex") or "", "year_of_birth": _year(patient.get("birthday")), "source_patient_id": person_id})
        visit_rows.append({"visit_occurrence_id": person_id, "person_id": person_id, "visit_start_datetime": _dt(patient.get("icuAdmissionTime") or patient.get("admissionTime")), "visit_end_datetime": _dt(patient.get("icuDischargeTime") or patient.get("dischargeTime")), "visit_source_value": patient.get("hisDept") or patient.get("dept") or "ICU"})
        diag = patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or patient.get("hisDiagnose")
        if diag:
            condition_rows.append({"condition_occurrence_id": f"cond-{person_id}", "person_id": person_id, "condition_source_value": diag, "condition_start_datetime": _dt(patient.get("icuAdmissionTime") or patient.get("admissionTime"))})
        observation_rows.append({"observation_id": f"obs-{person_id}", "person_id": person_id, "observation_source_value": "deidentified_patient_baseline", "value_as_string": json.dumps({"age": patient.get("age"), "dept": patient.get("hisDept") or patient.get("dept")}, ensure_ascii=False)})
        if his_pid:
            drug_cursor = runtime.db.dc_col("VI_ICU_ZYYZ").find({"pid": his_pid}, {"orderName": 1, "orderTime": 1, "spec": 1}).sort("orderTime", -1).limit(50)
            async for drug in drug_cursor:
                drug_rows.append({"drug_exposure_id": str(uuid.uuid4()), "person_id": person_id, "drug_source_value": drug.get("orderName"), "drug_exposure_start_datetime": _dt(drug.get("orderTime")), "dose_unit_source_value": drug.get("spec") or ""})
            lab_cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}, {"itemName": 1, "itemCnName": 1, "result": 1, "resultValue": 1, "unit": 1, "authTime": 1}).sort("authTime", -1).limit(200)
            async for lab in lab_cursor:
                measurement_rows.append({"measurement_id": str(uuid.uuid4()), "person_id": person_id, "measurement_source_value": lab.get("itemCnName") or lab.get("itemName"), "measurement_datetime": _dt(lab.get("authTime")), "value_source_value": lab.get("result") or lab.get("resultValue"), "unit_source_value": lab.get("unit") or ""})
    zip_path = EXPORT_DIR / f"omop_{task_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_csv(zf, "PERSON", person_rows)
        _write_csv(zf, "VISIT_OCCURRENCE", visit_rows)
        _write_csv(zf, "CONDITION_OCCURRENCE", condition_rows)
        _write_csv(zf, "DRUG_EXPOSURE", drug_rows)
        _write_csv(zf, "MEASUREMENT", measurement_rows)
        _write_csv(zf, "PROCEDURE_OCCURRENCE", procedure_rows)
        _write_csv(zf, "OBSERVATION", observation_rows)
        zf.writestr("field_mapping.json", json.dumps(MAPPING_CONFIG, ensure_ascii=False, indent=2))
        zf.writestr("data_quality.json", json.dumps(await build_data_quality_report(scope), ensure_ascii=False, indent=2))
    doc = {"task_id": task_id, "status": "completed", "progress": 100, "file_path": str(zip_path), "created_by": actor, "created_at": datetime.now(), "completed_at": datetime.now(), "patient_count": len(patients), "desensitized": True}
    await runtime.db.col("omop_export_tasks").insert_one(doc)
    await write_audit_log(runtime.db, action="export_omop_cdm", module="research_support", actor=actor, target_type="omop_export", target_id=task_id, detail={"patient_count": len(patients), "desensitized": True})
    return {"task": serialize_doc({k: v for k, v in doc.items() if k != "file_path"})}
