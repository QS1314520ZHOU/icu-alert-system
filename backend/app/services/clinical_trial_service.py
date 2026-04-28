from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any

from app import runtime
from app.services.ai_prompt_templates import CLINICAL_TRIAL_PARSE_PROMPT_VERSION, build_clinical_trial_parse_prompts, extract_json_object
from app.services.audit_service import write_ai_generation_log, write_audit_log
from app.services.llm_runtime import call_llm_chat
from app.utils.patient_helpers import calculate_age, research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

logger = logging.getLogger("icu-alert")

CANDIDATE_STATUSES = {
    "pending",
    "notified",
    "doctor_confirmed_suitable",
    "doctor_confirmed_not_suitable",
    "research_team_contacted",
    "enrolled",
    "not_enrolled",
}


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _field_value(patient: dict[str, Any], field: str) -> Any:
    key = str(field or "").strip()
    aliases = {
        "age": ["age", "hisAge"],
        "diagnosis": ["clinicalDiagnosis", "admissionDiagnosis", "hisDiagnose", "diagnosis"],
        "sex": ["sex", "gender", "hisSex"],
        "department": ["hisDept", "dept"],
        "icu_hours": ["icuAdmissionTime", "admissionTime"],
        "bed_no": ["hisBed", "bed"],
        "rass": ["rass", "latest_rass"],
        "sofa": ["sofa", "latest_sofa"],
        "apache": ["apache", "apacheII", "latest_apache"],
        "fio2": ["fio2", "latest_fio2"],
        "peep": ["peep", "latest_peep"],
        "spo2": ["spo2", "latest_spo2"],
        "pf_ratio": ["pf_ratio", "latest_pf_ratio"],
    }
    for candidate in aliases.get(key, [key]):
        if patient.get(candidate) not in (None, ""):
            return patient.get(candidate)
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


def _op_match(actual: Any, operator: str, expected: Any) -> tuple[bool, str]:
    op = str(operator or "eq").lower()
    a_num = _num(actual)
    e_num = _num(expected)
    if op in {"gte", ">="}:
        return (a_num is not None and e_num is not None and a_num >= e_num, f"{actual} >= {expected}")
    if op in {"gt", ">"}:
        return (a_num is not None and e_num is not None and a_num > e_num, f"{actual} > {expected}")
    if op in {"lte", "<="}:
        return (a_num is not None and e_num is not None and a_num <= e_num, f"{actual} <= {expected}")
    if op in {"lt", "<"}:
        return (a_num is not None and e_num is not None and a_num < e_num, f"{actual} < {expected}")
    if op in {"between", "range"} and isinstance(expected, (list, tuple)) and len(expected) >= 2:
        low, high = _num(expected[0]), _num(expected[1])
        return (a_num is not None and low is not None and high is not None and low <= a_num <= high, f"{actual} between {expected[0]} and {expected[1]}")
    if op in {"contains", "include"}:
        return (str(expected).lower() in str(actual or "").lower(), f"{actual} contains {expected}")
    if op in {"regex"}:
        try:
            return (bool(re.search(str(expected), str(actual or ""), re.I)), f"{actual} regex {expected}")
        except Exception:
            return (False, f"invalid regex {expected}")
    if op in {"in"}:
        values = expected if isinstance(expected, list) else [expected]
        return (str(actual) in {str(v) for v in values}, f"{actual} in {values}")
    return (str(actual or "").strip().lower() == str(expected or "").strip().lower(), f"{actual} == {expected}")


class RuleEvaluator:
    def evaluate_rules(self, patient: dict[str, Any], rules: list[dict[str, Any]], *, exclusion: bool = False) -> dict[str, Any]:
        matched = []
        unmet = []
        missing = []
        for rule in rules or []:
            field = str(rule.get("field") or "").strip()
            actual = _field_value(patient, field)
            if actual in (None, ""):
                missing.append({"rule": rule, "reason": f"{field} 缺失"})
                continue
            ok, evidence = _op_match(actual, str(rule.get("operator") or "eq"), rule.get("value"))
            row = {"rule": rule, "actual": actual, "evidence": evidence}
            if ok:
                matched.append(row)
            else:
                unmet.append(row)
        if exclusion:
            passed = len(matched) == 0
        else:
            # Inclusion screening is intentionally permissive for research recruitment:
            # matched objective evidence can create a "needs confirmation" candidate even
            # when age/scores/labs are missing, as long as no rule is clearly unmet.
            passed = len(unmet) == 0 and (len(matched) > 0 or not rules)
        total = max(1, len(rules or []))
        confidence = round((len(matched) + (0 if missing else 0.2)) / total, 2) if not exclusion else round(1 - len(matched) / total, 2)
        return {"passed": passed, "matched": matched, "unmet": unmet, "missing": missing, "confidence": max(0.0, min(1.0, confidence))}

    def explain_match(self, patient: dict[str, Any], trial: dict[str, Any]) -> dict[str, Any]:
        inclusion = self.evaluate_rules(patient, trial.get("inclusion_rules") or [], exclusion=False)
        exclusion = self.evaluate_rules(patient, trial.get("exclusion_rules") or [], exclusion=True)
        possible = bool(inclusion["passed"] and exclusion["passed"])
        return {
            "possible_match": possible,
            "matched_inclusion": inclusion["matched"],
            "unmet_inclusion": inclusion["unmet"],
            "missing_data": [*inclusion["missing"], *exclusion["missing"]],
            "triggered_exclusion": exclusion["matched"],
            "untriggered_exclusion": exclusion["unmet"],
            "confidence": round((inclusion["confidence"] + exclusion["confidence"]) / 2, 2),
            "human_review_required": True,
            "safety_notice": "系统仅提示可能符合，必须由主管医生和研究团队人工确认，不自动入组。",
            "message": f"该患者可能符合【{trial.get('trial_name') or trial.get('name')}】入组标准，请确认是否通知研究团队。" if possible else "当前证据不足或触发排除/未满足入组条件。",
        }


def _mask_name(name: Any) -> str:
    text = str(name or "").strip()
    if not text:
        return "脱敏患者"
    return f"{text[0]}*{text[-1]}" if len(text) > 1 else f"{text}*"


def candidate_status_flow(current: str) -> list[dict[str, Any]]:
    steps = [
        ("pending", "待确认"),
        ("notified", "已通知主管医生"),
        ("doctor_confirmed_suitable", "医生确认适合"),
        ("research_team_contacted", "已联系研究团队"),
        ("enrolled", "已入组"),
    ]
    current_idx = next((idx for idx, (key, _) in enumerate(steps) if key == current), 0)
    return [{"status": key, "label": label, "done": idx <= current_idx} for idx, (key, label) in enumerate(steps)]


async def list_trials() -> dict[str, Any]:
    cursor = runtime.db.col("clinical_trials").find({}).sort("updated_at", -1).limit(300)
    return {"trials": [serialize_doc(doc) async for doc in cursor]}


async def get_trial(trial_id: str) -> dict[str, Any]:
    query: dict[str, Any] = {"trial_id": trial_id}
    oid = safe_oid(trial_id)
    if oid:
        query = {"$or": [{"trial_id": trial_id}, {"_id": oid}]}
    doc = await runtime.db.col("clinical_trials").find_one(query)
    return {"trial": serialize_doc(doc)}


async def create_trial(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    doc = {
        "trial_id": str(uuid.uuid4()),
        "trial_name": payload.get("trial_name") or payload.get("name") or "未命名临床试验",
        "registration_no": payload.get("registration_no") or "",
        "pi": payload.get("pi") or "",
        "department": payload.get("department") or "",
        "study_type": payload.get("study_type") or "",
        "status": payload.get("status") or "准备中",
        "inclusion_rules": payload.get("inclusion_rules") or [],
        "exclusion_rules": payload.get("exclusion_rules") or [],
        "time_window": payload.get("time_window") or "",
        "contact": payload.get("contact") or "",
        "ethics_no": payload.get("ethics_no") or "",
        "remarks": payload.get("remarks") or "",
        "raw_criteria_text": payload.get("raw_criteria_text") or {},
        "ai_parse_result": payload.get("ai_parse_result") or None,
        "confirmed_rules": payload.get("confirmed_rules") or None,
        "created_by": actor,
        "updated_by": actor,
        "created_at": now,
        "updated_at": now,
        "activated_at": None,
    }
    await runtime.db.col("clinical_trials").insert_one(doc)
    return {"trial": serialize_doc(doc)}


async def update_trial(trial_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    update = {key: value for key, value in payload.items() if key not in {"_id", "trial_id", "created_at", "created_by"}}
    update["updated_by"] = actor
    update["updated_at"] = now
    await runtime.db.col("clinical_trials").update_one({"trial_id": trial_id}, {"$set": update})
    return await get_trial(trial_id)


async def delete_trial(trial_id: str) -> dict[str, Any]:
    result = await runtime.db.col("clinical_trials").delete_one({"trial_id": trial_id})
    return {"deleted": int(getattr(result, "deleted_count", 0))}


async def set_trial_active(trial_id: str, active: bool, actor: str) -> dict[str, Any]:
    status = "招募中" if active else "暂停"
    update = {"status": status, "updated_by": actor, "updated_at": datetime.now()}
    if active:
        update["activated_at"] = datetime.now()
    await runtime.db.col("clinical_trials").update_one({"trial_id": trial_id}, {"$set": update})
    await write_audit_log(runtime.db, action="activate_clinical_trial" if active else "deactivate_clinical_trial", module="clinical_trials", actor=actor, target_type="clinical_trial", target_id=trial_id, detail={"status": status})
    return await get_trial(trial_id)


async def parse_criteria(trial_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    inclusion = str(payload.get("inclusion_text") or payload.get("inclusion") or "")
    exclusion = str(payload.get("exclusion_text") or payload.get("exclusion") or "")
    cfg = runtime.config
    model = str(getattr(cfg, "llm_fast_model", "") or getattr(cfg.settings, "LLM_MODEL", "") or "unknown")
    try:
        system_prompt, user_prompt = build_clinical_trial_parse_prompts(inclusion, exclusion)
        llm = await call_llm_chat(cfg=cfg, system_prompt=system_prompt, user_prompt=user_prompt, model=model, temperature=0.0, max_tokens=1800, timeout_seconds=60)
        model = str(llm.get("model") or model)
        parsed = extract_json_object(str(llm.get("text") or ""))
        degraded = False
    except Exception as exc:
        logger.warning("clinical trial criteria parse fallback: %s", exc)
        parsed = {"inclusion_rules": [], "exclusion_rules": [], "need_human_review": True, "warnings": [f"AI解析失败: {exc}"]}
        degraded = True
    doc = {"raw_inclusion_text": inclusion, "raw_exclusion_text": exclusion, "ai_parse_result": parsed, "need_human_review": True, "model": model, "prompt_version": CLINICAL_TRIAL_PARSE_PROMPT_VERSION, "parsed_at": datetime.now(), "parsed_by": actor, "degraded": degraded}
    await runtime.db.col("clinical_trials").update_one({"trial_id": trial_id}, {"$set": doc})
    await write_ai_generation_log(runtime.db, module="clinical_trials", action="parse_criteria", model=model, prompt_version=CLINICAL_TRIAL_PARSE_PROMPT_VERSION, source_data_summary={"inclusion_text": inclusion, "exclusion_text": exclusion}, result=parsed, actor=actor, success=not degraded)
    return {"parse_result": serialize_doc(doc)}


async def screen_patients(*, department: str | None = None, dept_code: str | None = None, patient_scope: str = "in_dept") -> dict[str, Any]:
    evaluator = RuleEvaluator()
    trials = [doc async for doc in runtime.db.col("clinical_trials").find({"status": "招募中"}).limit(100)]
    patient_query = _append_department_scope(
        research_patient_scope_query(patient_scope or "in_dept"),
        department=department,
        dept_code=dept_code,
    )
    patients = [doc async for doc in runtime.db.col("patient").find(patient_query).limit(500)]
    candidates = []
    diagnostics = []
    now = datetime.now()
    for trial in trials:
        trial_diag = {
            "trial_id": trial.get("trial_id"),
            "trial_name": trial.get("trial_name"),
            "matched": 0,
            "unmet": 0,
            "missing_only": 0,
            "excluded": 0,
            "sample_reasons": [],
        }
        for patient in patients:
            explanation = evaluator.explain_match(patient, trial)
            if not explanation["possible_match"]:
                if explanation.get("triggered_exclusion"):
                    trial_diag["excluded"] += 1
                elif explanation.get("unmet_inclusion"):
                    trial_diag["unmet"] += 1
                elif explanation.get("missing_data"):
                    trial_diag["missing_only"] += 1
                if len(trial_diag["sample_reasons"]) < 5:
                    trial_diag["sample_reasons"].append({
                        "bed_no": patient.get("hisBed") or patient.get("bed") or "",
                        "patient_name": _mask_name(patient.get("name") or patient.get("hisName")),
                        "message": explanation.get("message"),
                        "unmet": len(explanation.get("unmet_inclusion") or []),
                        "missing": len(explanation.get("missing_data") or []),
                        "excluded": len(explanation.get("triggered_exclusion") or []),
                    })
                continue
            trial_diag["matched"] += 1
            candidate_id = f"{trial.get('trial_id')}:{patient.get('_id')}"
            existing = await runtime.db.col("clinical_trial_candidates").find_one({"candidate_id": candidate_id})
            doc = {
                "candidate_id": candidate_id,
                "trial_id": trial.get("trial_id"),
                "trial_name": trial.get("trial_name"),
                "patient_id": str(patient.get("_id")),
                "patient_name": _mask_name(patient.get("name") or patient.get("hisName")),
                "bed_no": patient.get("hisBed") or patient.get("bed") or "",
                "department": patient.get("hisDept") or patient.get("dept") or "",
                "dept_code": patient.get("deptCode") or "",
                "status": (existing or {}).get("status") or "pending",
                "match_evidence": explanation,
                "message": explanation["message"],
                "status_flow": candidate_status_flow((existing or {}).get("status") or "pending"),
                "updated_at": now,
            }
            if existing:
                await runtime.db.col("clinical_trial_candidates").update_one({"_id": existing["_id"]}, {"$set": doc})
            else:
                doc["created_at"] = now
                await runtime.db.col("clinical_trial_candidates").insert_one(doc)
            candidates.append(doc)
        diagnostics.append(trial_diag)
    return {
        "scanned_trials": len(trials),
        "scanned_patients": len(patients),
        "scope": {
            "department": str(department or "").strip() or None,
            "dept_code": str(dept_code or "").strip() or None,
            "patient_scope": patient_scope or "in_dept",
        },
        "candidates": serialize_doc(candidates),
        "diagnostics": serialize_doc(diagnostics),
    }


async def list_candidates(*, department: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    dept_name = str(department or "").strip()
    dept_code_text = str(dept_code or "").strip()
    if dept_name and not dept_code_text and dept_name.isdigit():
        dept_code_text = dept_name
        dept_name = ""
    query: dict[str, Any] = {}
    if dept_code_text:
        query["dept_code"] = dept_code_text
    elif dept_name:
        query["department"] = dept_name
    cursor = runtime.db.col("clinical_trial_candidates").find(query).sort("updated_at", -1).limit(300)
    return {"candidates": [serialize_doc(doc) async for doc in cursor]}


async def patient_matches(patient_id: str) -> dict[str, Any]:
    cursor = runtime.db.col("clinical_trial_candidates").find({"patient_id": patient_id}).sort("updated_at", -1).limit(50)
    rows = [serialize_doc(doc) async for doc in cursor]
    return {"matches": rows}


async def update_candidate_status(candidate_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    status = str(payload.get("status") or "").strip()
    if status not in CANDIDATE_STATUSES:
        return {"code": 400, "message": f"不支持的候选状态: {status}"}
    update = {"status": status, "status_reason": payload.get("reason") or "", "status_flow": candidate_status_flow(status), "updated_by": actor, "updated_at": datetime.now()}
    await runtime.db.col("clinical_trial_candidates").update_one({"candidate_id": candidate_id}, {"$set": update})
    await write_audit_log(runtime.db, action="update_trial_candidate_status", module="clinical_trials", actor=actor, target_type="clinical_trial_candidate", target_id=candidate_id, detail=update)
    doc = await runtime.db.col("clinical_trial_candidates").find_one({"candidate_id": candidate_id})
    return {"code": 0, "candidate": serialize_doc(doc)}
