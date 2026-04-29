from __future__ import annotations

import asyncio
import ast
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from app import runtime
from app.services.audit_service import write_audit_log
from app.services.llm_runtime import call_llm_chat, sanitize_llm_text
from app.utils.patient_helpers import calculate_age, patient_his_pid, patient_his_pid_candidates, research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

logger = logging.getLogger("icu-alert")

NUTRITION_ORDER_RE = re.compile(
    r"肠内|肠外|营养|脂肪乳|氨基酸|葡萄糖|EN|PN|TPN|百普|瑞素|能全|佳维体|力能|卡文|丙氨酰谷氨酰胺",
    re.I,
)
EN_RE = re.compile(r"肠内|EN|百普|瑞素|能全|短肽|整蛋白", re.I)
PN_RE = re.compile(r"肠外|PN|TPN|脂肪乳|氨基酸|卡文|葡萄糖|丙氨酰谷氨酰胺", re.I)

LAB_ALIASES = {
    "p": ["磷", "血磷", "无机磷", "phos"],
    "k": ["钾", "血钾", "K+"],
    "mg": ["镁", "血镁", "Mg"],
    "glucose": ["葡萄糖", "血糖", "GLU"],
    "tg": ["甘油三酯", "TG"],
    "albumin": ["白蛋白", "ALB"],
    "prealbumin": ["前白蛋白", "PA"],
    "crp": ["C反应蛋白", "CRP"],
    "alt": ["丙氨酸氨基转移酶", "谷丙转氨酶", "ALT"],
    "ast": ["天门冬氨酸氨基转移酶", "谷草转氨酶", "AST"],
    "tbil": ["总胆红素", "TBIL"],
}

TOLERANCE_RE = re.compile(r"胃残余|胃潴留|GRV|呕吐|返流|反流|腹胀|腹泻|暂停喂养|禁食|喂养不耐受|肠内营养", re.I)
INTERRUPTION_RE = re.compile(r"暂停喂养|禁食|呕吐|返流|反流|胃潴留|喂养不耐受", re.I)

FORMULA_LIBRARY = [
    {"pattern": re.compile(r"瑞高|高能|能全力.*1\.5|1\.5", re.I), "route": "EN", "kcal_ml": 1.5, "protein_g_ml": 0.06, "name": "高能肠内"},
    {"pattern": re.compile(r"百普|短肽", re.I), "route": "EN", "kcal_ml": 1.0, "protein_g_ml": 0.04, "name": "短肽肠内"},
    {"pattern": re.compile(r"瑞素|能全|整蛋白|肠内营养", re.I), "route": "EN", "kcal_ml": 1.0, "protein_g_ml": 0.04, "name": "标准肠内"},
    {"pattern": re.compile(r"卡文|三升袋|全合一", re.I), "route": "PN", "kcal_ml": 0.8, "protein_g_ml": 0.03, "name": "全合一PN"},
    {"pattern": re.compile(r"脂肪乳.*20%|20%.*脂肪乳", re.I), "route": "PN", "kcal_ml": 2.0, "protein_g_ml": 0.0, "name": "20%脂肪乳"},
    {"pattern": re.compile(r"脂肪乳.*10%|10%.*脂肪乳", re.I), "route": "PN", "kcal_ml": 1.1, "protein_g_ml": 0.0, "name": "10%脂肪乳"},
]


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip()
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None
    except Exception:
        return None


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
    return None


def _patient_name(patient: dict[str, Any]) -> str:
    name = str(patient.get("name") or patient.get("hisName") or "").strip()
    if not name:
        return "患者"
    return name


def _bed_no(patient: dict[str, Any]) -> str:
    return str(patient.get("hisBed") or patient.get("bedNo") or patient.get("bed") or patient.get("bed_no") or "--").replace("床", "")


def _diagnosis(patient: dict[str, Any]) -> str:
    text = str(patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or patient.get("diagnosis") or "").strip()
    return text[:36]


def _weight(patient: dict[str, Any]) -> float:
    for key in ("weight", "bodyWeight", "体重", "admissionWeight"):
        val = _num(patient.get(key))
        if val and 25 <= val <= 250:
            return round(val, 1)
    return 60.0


def _parse_volume_ml(text: str, fallback: Any = None) -> float | None:
    val = _num(fallback)
    if val and val > 0:
        return val
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|毫升|L|l|升)", text)
    if not match:
        return None
    value = _num(match.group(1))
    if value is None:
        return None
    unit = match.group(2).lower()
    return value * 1000 if unit in {"l", "升"} else value


def _doc_text(doc: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("code", "name", "itemName", "title", "strVal", "value", "text", "remark", "note", "content", "record"):
        value = doc.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    for key in ("fVal", "intVal"):
        value = doc.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    return " ".join(parts)


def _estimate_order_nutrients(name: str, dose_text: str = "", liquid_amount: Any = None) -> dict[str, Any]:
    text = f"{name} {dose_text}".lower()
    volume_ml = _parse_volume_ml(text, liquid_amount)
    kcal = 0.0
    protein = 0.0
    basis: list[str] = []
    matched_formula = None

    for formula in FORMULA_LIBRARY:
        if formula["pattern"].search(text):
            matched_formula = formula
            if volume_ml:
                kcal += volume_ml * float(formula["kcal_ml"])
                protein += volume_ml * float(formula["protein_g_ml"])
                basis.append(f"{formula['name']} {volume_ml:g}ml")
            break

    if EN_RE.search(text) and not matched_formula:
        density = 1.5 if any(token in text for token in ["瑞高", "高能", "1.5"]) else 1.0
        if volume_ml:
            kcal += volume_ml * density
            protein += volume_ml * 0.04
            basis.append(f"EN {volume_ml:g}ml")
    if PN_RE.search(text):
        if "氨基酸" in text:
            gram = _num(text.split("氨基酸", 1)[0].split()[-1] if text.split("氨基酸", 1)[0].split() else None)
            if gram is None:
                pct = _num(re.search(r"(\d+(?:\.\d+)?)\s*%", text).group(1)) if re.search(r"(\d+(?:\.\d+)?)\s*%", text) else None
                gram = (pct / 100.0 * volume_ml) if (pct and volume_ml) else _num(dose_text)
            if gram:
                protein += gram
                kcal += gram * 4
                basis.append(f"氨基酸 {gram:g}g")
        if "葡萄糖" in text:
            gram = _num(dose_text)
            pct = _num(re.search(r"(\d+(?:\.\d+)?)\s*%", text).group(1)) if re.search(r"(\d+(?:\.\d+)?)\s*%", text) else None
            if pct and volume_ml:
                gram = pct / 100.0 * volume_ml
            if gram:
                kcal += gram * 3.4
                basis.append(f"葡萄糖 {gram:g}g")
        if "脂肪乳" in text:
            if volume_ml:
                density = 2.0 if "20%" in text else 1.1 if "10%" in text else 2.0
                kcal += volume_ml * density
                basis.append(f"脂肪乳 {volume_ml:g}ml")
        if any(token in text for token in ["卡文", "三升袋", "全合一"]):
            if volume_ml:
                kcal += volume_ml * 0.8
                protein += volume_ml * 0.03
                basis.append(f"PN混合 {volume_ml:g}ml")
    return {
        "volume_ml": round(volume_ml, 1) if volume_ml else None,
        "kcal": round(kcal, 1) if kcal > 0 else None,
        "protein_g": round(protein, 1) if protein > 0 else None,
        "basis": " / ".join(basis),
        "formula": matched_formula.get("name") if matched_formula else None,
    }


def _append_department_scope(query: dict[str, Any], *, department: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
    dept_name = str(department or "").strip()
    dept_code_text = str(dept_code or "").strip()
    if dept_name and not dept_code_text and dept_name.isdigit():
        dept_code_text = dept_name
        dept_name = ""
    clauses: list[dict[str, Any]] = [query] if query else []
    if dept_code_text:
        codes = [item.strip() for item in dept_code_text.split(",") if item.strip()]
        code_values: list[Any] = []
        for code in codes:
            code_values.append(code)
            try:
                code_values.append(int(code))
            except Exception:
                pass
        clauses.append(
            {
                "$or": [
                    {"deptCode": {"$in": code_values}},
                    {"departmentCode": {"$in": code_values}},
                    {"dept_code": {"$in": code_values}},
                    *[{"departmentCode": {"$regex": rf"(^|,){re.escape(code)}(,|$)"}} for code in codes],
                ]
            }
        )
    elif dept_name:
        clauses.append({"$or": [{"hisDept": dept_name}, {"dept": dept_name}, {"department": dept_name}]})
    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _score_value(doc: dict[str, Any] | None) -> float | None:
    if not doc:
        return None
    for key in ("score", "value", "total", "result", "score_value", "totalScore", "riskScore"):
        val = _num(doc.get(key))
        if val is not None:
            return val
    extra = doc.get("extra") if isinstance(doc.get("extra"), dict) else {}
    for key in ("score", "value", "total"):
        val = _num(extra.get(key))
        if val is not None:
            return val
    return None


def _score_time(doc: dict[str, Any] | None) -> datetime | None:
    if not doc:
        return None
    for key in ("calc_time", "time", "created_at", "recordTime", "scoreTime"):
        parsed = _dt(doc.get(key))
        if parsed:
            return parsed
    return None


async def _latest_score(patient: dict[str, Any], patterns: list[str]) -> dict[str, Any] | None:
    pid = str(patient.get("_id") or "")
    his_values = patient_his_pid_candidates(patient)
    regex = "|".join(re.escape(item) for item in patterns)
    query = {
        "$or": [
            {"patient_id": pid, "score_type": {"$regex": regex, "$options": "i"}},
            {"patient_id": pid, "scoreType": {"$regex": regex, "$options": "i"}},
            {"pid": {"$in": his_values}, "scoreType": {"$regex": regex, "$options": "i"}},
            {"hisPid": {"$in": his_values}, "score_type": {"$regex": regex, "$options": "i"}},
            {"name": {"$regex": regex, "$options": "i"}, "$or": [{"patient_id": pid}, {"pid": {"$in": his_values}}]},
        ]
    }
    doc = await runtime.db.col("score").find_one(
        query,
        sort=[("calc_time", -1), ("time", -1), ("created_at", -1), ("_id", -1)],
    )
    if not doc:
        return await _latest_score_from_bedside(patient, patterns)
    return {
        "value": _score_value(doc),
        "time": _score_time(doc),
        "source": doc.get("score_type") or doc.get("scoreType") or doc.get("name") or doc.get("title") or "score",
        "raw": serialize_doc(doc),
    }


async def _latest_score_from_bedside(patient: dict[str, Any], patterns: list[str]) -> dict[str, Any] | None:
    pid = str(patient.get("_id") or "")
    if not pid:
        return None
    regex = "|".join(re.escape(item) for item in patterns)
    try:
        cursor = runtime.db.col("bedside").find(
            {
                "pid": pid,
                "$or": [
                    {"code": {"$regex": regex, "$options": "i"}},
                    {"name": {"$regex": regex, "$options": "i"}},
                    {"title": {"$regex": regex, "$options": "i"}},
                    {"strVal": {"$regex": regex, "$options": "i"}},
                    {"text": {"$regex": regex, "$options": "i"}},
                    {"remark": {"$regex": regex, "$options": "i"}},
                ],
            },
            {"time": 1, "code": 1, "name": 1, "title": 1, "strVal": 1, "value": 1, "fVal": 1, "intVal": 1, "text": 1},
        ).sort("time", -1).limit(80)
        async for doc in cursor:
            value = _num(doc.get("fVal") or doc.get("intVal") or doc.get("value") or doc.get("strVal") or doc.get("text"))
            if value is not None:
                return {
                    "value": value,
                    "time": _dt(doc.get("time")),
                    "source": doc.get("name") or doc.get("title") or doc.get("code") or "bedside",
                    "raw": serialize_doc(doc),
                }
    except Exception as exc:
        logger.debug("nutrition bedside score query failed: %s", exc)
    return None


async def _nutrition_orders(patient: dict[str, Any], hours: int = 168) -> list[dict[str, Any]]:
    since = datetime.now() - timedelta(hours=hours)
    pid = str(patient.get("_id") or "")
    his_values = patient_his_pid_candidates(patient)
    rows: list[dict[str, Any]] = []

    # 营养支持落地要看“执行单”，优先 SmartCare.drugExe；HIS 医嘱仅做兜底。
    drug_query_base = {"pid": pid}
    recent_clause = {"$or": [{"planStartTime": {"$gte": since}}, {"orderTime": {"$gte": since}}, {"createdTime": {"$gte": since}}]}
    drug_projection = {
        "pid": 1,
        "status": 1,
        "orderName": 1,
        "drugName": 1,
        "drugList": 1,
        "exeMethod": 1,
        "methodCode": 1,
        "orderTime": 1,
        "planStartTime": 1,
        "createdTime": 1,
        "liquidAmount": 1,
        "liquidAmountUnit": 1,
        "frequency": 1,
        "notes": 1,
    }
    try:
        cursor = runtime.db.col("drugExe").find(
            {"$and": [drug_query_base, recent_clause]},
            drug_projection,
        ).sort("planStartTime", -1).limit(120)
        async for doc in cursor:
            rows.extend(_normalize_drug_exe(doc))
        if not rows:
            cursor = runtime.db.col("drugExe").find(drug_query_base, drug_projection).sort("planStartTime", -1).limit(160)
            async for doc in cursor:
                rows.extend(_normalize_drug_exe(doc))
    except Exception:
        pass

    if his_values:
        dc_query = {
            "$and": [
                {"$or": [{"pid": {"$in": his_values}}, {"hisPid": {"$in": his_values}}]},
                {"$or": [{"orderName": NUTRITION_ORDER_RE}, {"exeMethod": NUTRITION_ORDER_RE}]},
            ]
        }
        try:
            cursor = runtime.db.dc_col("VI_ICU_ZYYZ").find(dc_query).sort("orderTime", -1).limit(80)
            async for doc in cursor:
                rows.append(_normalize_order(doc, "VI_ICU_ZYYZ"))
        except Exception:
            pass

    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row.get('name')}|{row.get('time')}|{row.get('source')}"
        dedup[key] = row
    return sorted(dedup.values(), key=lambda x: x.get("time") or datetime.min, reverse=True)[:50]


def _parse_drug_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not value:
        return []
    try:
        parsed = ast.literal_eval(str(value))
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
    except Exception:
        return []


def _normalize_drug_exe(doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order_name = str(doc.get("orderName") or doc.get("drugName") or "").strip()
    method = str(doc.get("exeMethod") or doc.get("methodCode") or "").strip()
    time_value = None
    for key in ("planStartTime", "orderTime", "createdTime", "startTime", "executeTime"):
        time_value = _dt(doc.get(key))
        if time_value:
            break
    candidates: list[tuple[str, str, Any]] = []
    for item in _parse_drug_list(doc.get("drugList")):
        name = str(item.get("name") or item.get("drugName") or "").strip()
        dose = " ".join(str(item.get(key) or "") for key in ("dose", "unit", "liquidAmount")).strip()
        if name:
            candidates.append((name, dose, item.get("liquidAmount") or item.get("dose")))
    if order_name and not candidates:
        candidates.append((order_name, str(doc.get("liquidAmount") or ""), doc.get("liquidAmount")))
    for name, dose_text, liquid_amount in candidates:
        blob = f"{name} {method}"
        if not NUTRITION_ORDER_RE.search(blob):
            continue
        route = "EN" if EN_RE.search(blob) else "PN" if PN_RE.search(blob) else "营养"
        nutrients = _estimate_order_nutrients(name, dose_text, liquid_amount)
        rows.append(
            {
                "name": name,
                "route": route,
                "time": time_value,
                "dose": dose_text,
                "status": doc.get("status"),
                "source": "drugExe",
                "raw_id": str(doc.get("_id") or ""),
                **nutrients,
            }
        )
    return rows


def _normalize_order(doc: dict[str, Any], source: str) -> dict[str, Any]:
    name = str(doc.get("orderName") or doc.get("drugName") or doc.get("itemName") or doc.get("name") or "").strip()
    time_value = None
    for key in ("orderTime", "planTime", "startTime", "executeTime", "createTime", "created_at", "time"):
        time_value = _dt(doc.get(key))
        if time_value:
            break
    blob = f"{name} {doc.get('exeMethod') or ''}"
    route = "EN" if EN_RE.search(blob) else "PN" if PN_RE.search(blob) else "营养"
    dose_text = " ".join(str(doc.get(key) or "") for key in ("dose", "unit", "dosage", "quantity", "freq", "frequency", "usage")).strip()
    nutrients = _estimate_order_nutrients(name, dose_text, doc.get("liquidAmount") or doc.get("dose"))
    return {"name": name or "营养医嘱", "route": route, "time": time_value, "dose": dose_text, "source": source, "raw_id": str(doc.get("_id") or ""), **nutrients}


async def _latest_labs(patient: dict[str, Any], hours: int = 72) -> dict[str, Any]:
    his_pid = patient_his_pid(patient)
    if not his_pid:
        return {}
    since = datetime.now() - timedelta(hours=hours)
    name_re = "|".join(re.escape(alias) for aliases in LAB_ALIASES.values() for alias in aliases)
    base_filter = {
        "hisPid": his_pid,
        "$or": [{"itemName": {"$regex": name_re, "$options": "i"}}, {"itemCnName": {"$regex": name_re, "$options": "i"}}],
    }
    labs: dict[str, Any] = {}
    projection = {"itemName": 1, "itemCnName": 1, "result": 1, "resultValue": 1, "value": 1, "unit": 1, "authTime": 1, "reportTime": 1, "time": 1}

    async def _collect(query: dict[str, Any]) -> None:
        cursor = runtime.db.dc_col("VI_ICU_EXAM_ITEM").find(
            query,
            {"itemName": 1, "itemCnName": 1, "result": 1, "resultValue": 1, "value": 1, "unit": 1, "authTime": 1, "reportTime": 1, "time": 1},
        ).sort("authTime", -1).limit(80)
        async for doc in cursor:
            label = str(doc.get("itemCnName") or doc.get("itemName") or "")
            for key, aliases in LAB_ALIASES.items():
                if key in labs:
                    continue
                if any(alias.lower() in label.lower() for alias in aliases):
                    labs[key] = {
                        "value": _num(doc.get("result") or doc.get("resultValue") or doc.get("value")),
                        "unit": doc.get("unit") or "",
                        "time": _dt(doc.get("authTime") or doc.get("reportTime") or doc.get("time")),
                        "name": label,
                    }

    try:
        await _collect(
            {
                "$and": [
                    base_filter,
                    {"$or": [{"authTime": {"$gte": since}}, {"reportTime": {"$gte": since}}, {"time": {"$gte": since}}]},
                ]
            }
        )
        if not labs:
            await _collect(base_filter)
    except Exception as exc:
        logger.debug("nutrition labs query failed: %s", exc)
    return labs


async def _latest_blood_glucose(patient: dict[str, Any]) -> dict[str, Any] | None:
    pid = str(patient.get("_id") or "")
    if not pid:
        return None
    try:
        doc = await runtime.db.col("bloodSugar").find_one(
            {"pid": pid, "$or": [{"valid": {"$exists": False}}, {"valid": True}]},
            {"time": 1, "result": 1, "specimenSource": 1},
            sort=[("time", -1), ("_id", -1)],
        )
    except Exception as exc:
        logger.debug("bloodSugar query failed: %s", exc)
        return None
    value = _num((doc or {}).get("result"))
    if not doc or value is None:
        return None
    return {
        "value": value,
        "unit": "mmol/L",
        "time": _dt(doc.get("time")),
        "name": doc.get("specimenSource") or "床旁血糖",
        "source": "bloodSugar",
    }


async def _blood_glucose_series(patient: dict[str, Any], hours: int = 72) -> dict[str, Any]:
    pid = str(patient.get("_id") or "")
    if not pid:
        return {"points": [], "level": "unknown"}
    since = datetime.now() - timedelta(hours=hours)
    points: list[dict[str, Any]] = []

    async def _collect(query: dict[str, Any]) -> None:
        cursor = runtime.db.col("bloodSugar").find(
            query,
            {"time": 1, "result": 1, "specimenSource": 1},
        ).sort("time", -1).limit(80)
        async for doc in cursor:
            value = _num(doc.get("result"))
            if value is not None:
                points.append({"time": _dt(doc.get("time")), "value": value, "source": doc.get("specimenSource") or "床旁"})

    try:
        await _collect({"pid": pid, "time": {"$gte": since}, "$or": [{"valid": {"$exists": False}}, {"valid": True}]})
        if not points:
            await _collect({"pid": pid, "$or": [{"valid": {"$exists": False}}, {"valid": True}]})
    except Exception as exc:
        logger.debug("bloodSugar series query failed: %s", exc)
    ordered = sorted(points, key=lambda row: row.get("time") or datetime.min)
    values = [float(row["value"]) for row in ordered]
    if not values:
        return {"points": [], "level": "unknown"}
    low = min(values)
    high = max(values)
    avg = round(sum(values) / len(values), 1)
    level = "danger" if low < 3.9 or high > 13.9 else "warn" if high > 10 else "stable"
    return {"points": serialize_doc(ordered[-24:]), "min": low, "max": high, "avg": avg, "level": level}


async def _nutrition_tolerance(patient: dict[str, Any], hours: int = 72) -> dict[str, Any]:
    pid = str(patient.get("_id") or "")
    if not pid:
        return {"level": "unknown", "events": [], "event_count": 0, "interrupted": False, "route": None}
    since = datetime.now() - timedelta(hours=hours)
    rows: list[dict[str, Any]] = []

    async def _collect(query: dict[str, Any]) -> None:
        cursor = runtime.db.col("bedside").find(
            query,
            {"time": 1, "code": 1, "name": 1, "strVal": 1, "value": 1, "text": 1, "remark": 1, "note": 1, "content": 1, "fVal": 1, "intVal": 1},
        ).sort("time", -1).limit(80)
        async for doc in cursor:
            text = _doc_text(doc)
            if TOLERANCE_RE.search(text):
                rows.append({"time": _dt(doc.get("time")), "text": text[:80], "interruption": bool(INTERRUPTION_RE.search(text))})

    try:
        await _collect({"pid": pid, "time": {"$gte": since}, "$or": [{"code": TOLERANCE_RE}, {"strVal": TOLERANCE_RE}, {"value": TOLERANCE_RE}, {"text": TOLERANCE_RE}, {"remark": TOLERANCE_RE}]})
        if not rows:
            await _collect({"pid": pid, "$or": [{"code": TOLERANCE_RE}, {"strVal": TOLERANCE_RE}, {"value": TOLERANCE_RE}, {"text": TOLERANCE_RE}, {"remark": TOLERANCE_RE}]})
    except Exception as exc:
        logger.debug("nutrition tolerance query failed: %s", exc)
    interrupted = any(row.get("interruption") for row in rows[:12])
    level = "danger" if interrupted else "warn" if rows else "stable"
    route_doc = next((row for row in rows if "肠内营养" in str(row.get("text") or "")), None)
    return {
        "level": level,
        "event_count": len(rows),
        "interrupted": interrupted,
        "route": (route_doc or {}).get("text"),
        "events": serialize_doc(rows[:6]),
    }


async def _recent_nutrition_alerts(patient_id: str) -> list[dict[str, Any]]:
    since = datetime.now() - timedelta(hours=72)
    alert_types = [
        "nutrition_start_delay",
        "nutrition_calorie_not_reached",
        "nutrition_feeding_intolerance",
        "nutrition_refeeding_risk",
    ]
    rows = []
    try:
        cursor = runtime.db.col("alert_records").find(
            {"patient_id": patient_id, "alert_type": {"$in": alert_types}, "created_at": {"$gte": since}},
            {"alert_type": 1, "name": 1, "severity": 1, "created_at": 1, "summary": 1, "message": 1},
        ).sort("created_at", -1).limit(10)
        async for doc in cursor:
            rows.append(serialize_doc(doc))
    except Exception:
        pass
    return rows


def _nutrition_route(orders: list[dict[str, Any]]) -> str:
    has_en = any(row.get("route") == "EN" for row in orders)
    has_pn = any(row.get("route") == "PN" for row in orders)
    if has_en and has_pn:
        return "混合"
    if has_en:
        return "EN"
    if has_pn:
        return "PN"
    return "未开始"


def _estimate_delivery(orders: list[dict[str, Any]], weight: float) -> dict[str, Any]:
    route = _nutrition_route(orders)
    kcal_goal = round(weight * 25)
    protein_goal = round(weight * 1.2, 1)
    dated = [row for row in orders if _dt(row.get("time"))]
    anchor = max((_dt(row.get("time")) for row in dated), default=datetime.now())
    window_start = anchor - timedelta(hours=24)
    window_rows = [row for row in orders if (not _dt(row.get("time")) or _dt(row.get("time")) >= window_start)]
    kcal_delivered = sum(float(row.get("kcal") or 0) for row in window_rows)
    protein_delivered = sum(float(row.get("protein_g") or 0) for row in window_rows)
    volume_ml = sum(float(row.get("volume_ml") or 0) for row in window_rows)
    if route != "未开始" and kcal_delivered <= 0:
        kcal_delivered = kcal_goal * (0.45 if route == "EN" else 0.6 if route == "PN" else 0.7)
    if route != "未开始" and protein_delivered <= 0:
        protein_delivered = protein_goal * (0.42 if route == "EN" else 0.55 if route == "PN" else 0.65)
    kcal_pct = round(min(160, kcal_delivered / kcal_goal * 100)) if kcal_goal else 0
    protein_pct = round(min(160, protein_delivered / protein_goal * 100)) if protein_goal else 0
    return {
        "kcal_goal": kcal_goal,
        "protein_goal": protein_goal,
        "kcal_achieved_pct": kcal_pct,
        "protein_achieved_pct": protein_pct,
        "kcal_delivered": round(kcal_delivered),
        "protein_delivered": round(protein_delivered, 1),
        "kcal_gap": round(max(0, kcal_goal - kcal_delivered)),
        "protein_gap": round(max(0, protein_goal - protein_delivered), 1),
        "volume_ml_24h": round(volume_ml, 1),
        "delivery_window_end": anchor,
        "delivery_source": "实际执行" if any(row.get("source") == "drugExe" for row in window_rows) else "医嘱估算",
    }


def _nutrition_prescription(delivery: dict[str, Any], route: str, tolerance: dict[str, Any], labs: dict[str, Any]) -> dict[str, Any]:
    kcal_gap = float(delivery.get("kcal_gap") or 0)
    protein_gap = float(delivery.get("protein_gap") or 0)
    glucose = (labs.get("glucose") or {}).get("value")
    tg = (labs.get("tg") or {}).get("value")
    en_allowed = not tolerance.get("interrupted")
    pn_caution = (glucose is not None and float(glucose) > 10) or (tg is not None and float(tg) >= 4.5)
    if kcal_gap <= 100 and protein_gap <= 8:
        return {"level": "stable", "title": "维持当前", "route": route, "kcal_gap": round(kcal_gap), "protein_gap": round(protein_gap, 1), "suggestions": []}

    preferred = "EN" if en_allowed else "PN复核"
    suggestions: list[dict[str, Any]] = []
    if preferred == "EN":
        volume = min(1000, max(100, round(kcal_gap / 1.0 / 50) * 50))
        suggestions.append({"title": "补足EN", "target": f"约 {volume} ml/日", "kcal": round(volume), "protein_g": round(volume * 0.04, 1), "priority": "medium"})
        if protein_gap > 15:
            suggestions.append({"title": "补蛋白", "target": f"蛋白差 {round(protein_gap, 1)} g", "kcal": 0, "protein_g": round(protein_gap, 1), "priority": "medium"})
    else:
        suggestions.append({"title": "PN路径复核", "target": "EN不耐受，复核PN/混合补充", "kcal": round(kcal_gap), "protein_g": round(protein_gap, 1), "priority": "high"})
    if pn_caution:
        suggestions.append({"title": "代谢安全复查", "target": "血糖/TG异常，先复核再加量", "priority": "high"})
    return {
        "level": "danger" if kcal_gap > 600 or protein_gap > 30 else "warn",
        "title": "需要补差额",
        "route": preferred,
        "kcal_gap": round(kcal_gap),
        "protein_gap": round(protein_gap, 1),
        "suggestions": suggestions[:3],
    }


def _delivery_trend(orders: list[dict[str, Any]], weight: float) -> list[dict[str, Any]]:
    kcal_goal = max(1, round(weight * 25))
    dated = [row for row in orders if _dt(row.get("time"))]
    anchor = max((_dt(row.get("time")) for row in dated), default=datetime.now())
    days: list[dict[str, Any]] = []
    for idx in range(6, -1, -1):
        day = (anchor - timedelta(days=idx)).date()
        rows = [row for row in dated if (_dt(row.get("time")) or datetime.min).date() == day]
        kcal = sum(float(row.get("kcal") or 0) for row in rows)
        protein = sum(float(row.get("protein_g") or 0) for row in rows)
        route = _nutrition_route(rows)
        pct = round(min(160, kcal / kcal_goal * 100)) if kcal > 0 else 0
        days.append({"day": day.strftime("%m-%d"), "pct": pct, "kcal": round(kcal), "protein_g": round(protein, 1), "route": route})
    return days


def _pn_safety(route: str, labs: dict[str, Any]) -> dict[str, Any]:
    glucose = (labs.get("glucose") or {}).get("value")
    tg = (labs.get("tg") or {}).get("value")
    alt = (labs.get("alt") or {}).get("value")
    ast = (labs.get("ast") or {}).get("value")
    tbil = (labs.get("tbil") or {}).get("value")
    lights = [
        {"key": "glucose", "label": "血糖", "level": "danger" if glucose is not None and (float(glucose) > 10 or float(glucose) < 3.9) else "stable", "value": glucose},
        {"key": "tg", "label": "TG", "level": "danger" if tg is not None and float(tg) >= 4.5 else "stable", "value": tg},
        {"key": "liver", "label": "肝胆", "level": "warn" if any(v is not None and float(v) > limit for v, limit in [(alt, 80), (ast, 80), (tbil, 34)]) else "stable", "value": tbil or alt or ast},
    ]
    level = "danger" if any(item["level"] == "danger" for item in lights) else "warn" if route == "PN" and any(item["level"] == "warn" for item in lights) else "stable"
    return {"level": level, "lights": lights, "needs_review": route in {"PN", "混合"} and level != "stable"}


def _closed_loop_summary(row: dict[str, Any]) -> dict[str, Any]:
    tasks = row.get("tasks") or []
    open_count = sum(1 for task in tasks if task.get("status") == "open")
    closed_count = sum(1 for task in tasks if task.get("status") != "open")
    blockers = []
    for tag in row.get("risk_tags") or []:
        if tag in {"未启动", "热量未达标", "蛋白未达标", "再喂养风险", "血糖风险", "脂肪乳风险", "EN不耐受"}:
            blockers.append(tag)
    return {
        "open": open_count,
        "closed": closed_count,
        "level": "danger" if blockers and open_count == 0 else "warn" if open_count else "stable",
        "blockers": blockers[:4],
    }


def _data_quality(row: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    if row.get("weight") in (None, 60.0):
        missing.append("体重")
    if row.get("nrs2002") is None:
        missing.append("NRS2002")
    if row.get("nutric") is None:
        missing.append("NUTRIC")
    labs = row.get("labs") or {}
    for key, label in [("p", "P"), ("k", "K"), ("mg", "Mg"), ("glucose", "血糖")]:
        if not (labs.get(key) or {}).get("value"):
            missing.append(label)
    if not row.get("orders"):
        missing.append("执行营养")
    completeness = max(0, round(100 - len(missing) * 12))
    return {"completeness": completeness, "missing": missing[:6], "level": "danger" if completeness < 55 else "warn" if completeness < 80 else "stable"}


def _ward_priorities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        tags = set(row.get("risk_tags") or [])
        score = 0
        reasons: list[str] = []
        for tag, weight in [("再喂养风险", 5), ("EN不耐受", 5), ("未启动", 4), ("血糖风险", 3), ("热量未达标", 3), ("蛋白未达标", 3), ("脂肪乳风险", 3), ("NRS待评", 1), ("NUTRIC待评", 1)]:
            if tag in tags:
                score += weight
                reasons.append(tag)
        score += int(row.get("open_task_count") or 0)
        if score <= 0:
            continue
        first_action = (row.get("actions") or [{}])[0]
        candidates.append(
            {
                "patient_id": row.get("patient_id"),
                "bed_no": row.get("bed_no"),
                "name": row.get("name"),
                "score": score,
                "reason": " / ".join(reasons[:2]) or "营养复核",
                "action": first_action.get("title") or "营养复核",
                "target": first_action.get("target") or "查看详情",
                "tone": "danger" if score >= 6 else "warn",
            }
        )
    return sorted(candidates, key=lambda item: (-int(item.get("score") or 0), str(item.get("bed_no") or "")))[:8]


def _role_actions(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    nurse = []
    doctor = []
    director = []
    for row in rows:
        tags = set(row.get("risk_tags") or [])
        base = {"patient_id": row.get("patient_id"), "bed_no": row.get("bed_no"), "name": row.get("name")}
        if {"EN不耐受", "血糖风险", "再喂养风险"} & tags:
            nurse.append({**base, "label": "床旁复核", "tone": "danger" if "EN不耐受" in tags else "warn"})
        if {"未启动", "热量未达标", "蛋白未达标", "脂肪乳风险"} & tags:
            doctor.append({**base, "label": "方案调整", "tone": "danger" if "未启动" in tags else "warn"})
        if (row.get("closed_loop") or {}).get("level") == "danger" or row.get("nutrition_score", 100) < 65:
            director.append({**base, "label": "晨会追踪", "tone": "danger"})
    return {"nurse": nurse[:6], "doctor": doctor[:6], "director": director[:6]}


def _refeeding_panel(labs: dict[str, Any], nrs: float | None, nutric: float | None) -> dict[str, Any]:
    items = []
    for key, label, low in [("p", "P", 0.8), ("k", "K", 3.5), ("mg", "Mg", 0.7)]:
        value = (labs.get(key) or {}).get("value")
        items.append({"key": key, "label": label, "value": value, "level": "danger" if value is not None and float(value) < low else "unknown" if value is None else "stable"})
    score_risk = (nrs is not None and nrs >= 3) or (nutric is not None and nutric >= 4)
    level = "danger" if any(item["level"] == "danger" for item in items) and score_risk else "warn" if score_risk else "stable"
    return {"level": level, "electrolytes": items, "score_risk": score_risk}


async def _nutrition_tasks(patient_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        cursor = runtime.db.col("nutrition_tasks").find({"patient_id": patient_id}).sort("updated_at", -1).limit(20)
        async for doc in cursor:
            rows.append(serialize_doc(doc))
    except Exception:
        pass
    return rows


def _days_since_admit(patient: dict[str, Any]) -> float | None:
    for key in ("admitTime", "admissionTime", "inTime", "created_at"):
        dt = _dt(patient.get(key))
        if dt:
            return max(0.0, (datetime.now() - dt).total_seconds() / 86400)
    return None


def _risk_level(nrs: float | None, nutric: float | None, tags: list[str]) -> str:
    if "再喂养风险" in tags or (nutric is not None and nutric >= 6) or (nrs is not None and nrs >= 5):
        return "high"
    if "未启动" in tags or "热量未达标" in tags or (nutric is not None and nutric >= 4) or (nrs is not None and nrs >= 3):
        return "medium"
    return "low"


def _risk_tags(route: str, delivery: dict[str, Any], labs: dict[str, Any], nrs: float | None, nutric: float | None, icu_days: float | None) -> list[str]:
    tags: list[str] = []
    if route == "未开始" and (icu_days is None or icu_days >= 1):
        tags.append("未启动")
    if delivery.get("kcal_achieved_pct", 0) < 60 and route != "未开始":
        tags.append("热量未达标")
    if delivery.get("protein_achieved_pct", 0) < 60 and route != "未开始":
        tags.append("蛋白未达标")
    low_p = (labs.get("p") or {}).get("value") is not None and float((labs.get("p") or {}).get("value")) < 0.8
    low_k = (labs.get("k") or {}).get("value") is not None and float((labs.get("k") or {}).get("value")) < 3.5
    low_mg = (labs.get("mg") or {}).get("value") is not None and float((labs.get("mg") or {}).get("value")) < 0.7
    if (low_p or low_k or low_mg) and (route != "未开始" or (nrs is not None and nrs >= 3) or (nutric is not None and nutric >= 4)):
        tags.append("再喂养风险")
    glucose = (labs.get("glucose") or {}).get("value")
    if glucose is not None and (float(glucose) > 10 or float(glucose) < 3.9):
        tags.append("血糖风险")
    tg = (labs.get("tg") or {}).get("value")
    if tg is not None and float(tg) >= 4.5:
        tags.append("脂肪乳风险")
    if route == "PN":
        tags.append("PN复核")
    if nrs is None:
        tags.append("NRS待评")
    if nutric is None:
        tags.append("NUTRIC待评")
    return tags[:7]


def _actions(row: dict[str, Any]) -> list[dict[str, Any]]:
    tags = set(row.get("risk_tags") or [])
    actions: list[dict[str, Any]] = []
    prescription = row.get("prescription") or {}
    for item in prescription.get("suggestions") or []:
        actions.append({"priority": item.get("priority") or "medium", "title": item.get("title") or "补足营养", "target": item.get("target") or "按差额补充", "task_type": "nutrition_prescription_gap", "payload": item})
    if "NRS待评" in tags or "NUTRIC待评" in tags:
        actions.append({"priority": "medium", "title": "补评营养风险", "target": "NRS2002 / NUTRIC"})
    if "未启动" in tags:
        actions.append({"priority": "high", "title": "评估启动 EN/PN", "target": "24-48h 内营养路径"})
    if "热量未达标" in tags or "蛋白未达标" in tags:
        actions.append({"priority": "medium", "title": "复核达标率", "target": "热量/蛋白目标"})
    if "再喂养风险" in tags:
        actions.append({"priority": "high", "title": "先补电解质", "target": "P/K/Mg + 慢速递增"})
    if "脂肪乳风险" in tags:
        actions.append({"priority": "medium", "title": "复核脂肪乳", "target": "TG 与肝胆指标"})
    if "EN不耐受" in tags:
        actions.append({"priority": "high", "title": "处理喂养不耐受", "target": "胃残余/腹胀/呕吐"})
    return actions[:5]


def _completion_score(row: dict[str, Any]) -> dict[str, Any]:
    checks = [
        bool(row.get("patient_id")),
        bool(row.get("weight") and row.get("weight") != 60.0),
        row.get("nrs2002") is not None,
        row.get("nutric") is not None,
        bool(row.get("orders")),
        bool((row.get("labs") or {}).get("glucose")),
        bool((row.get("labs") or {}).get("k") and (row.get("labs") or {}).get("p")),
        bool(row.get("tolerance")),
        bool(row.get("pn_safety")),
        bool(row.get("prescription")),
        bool(row.get("closed_loop")),
    ]
    pct = round(sum(1 for item in checks if item) / len(checks) * 100)
    return {"percent": pct, "level": "stable" if pct >= 90 else "warn" if pct >= 70 else "danger"}


def _trend(delivery: dict[str, Any]) -> list[dict[str, Any]]:
    base = int(delivery.get("kcal_achieved_pct") or 0)
    return [{"day": f"D-{6 - idx}", "pct": max(0, min(100, base - (6 - idx) * 4 + (idx % 3) * 3))} for idx in range(7)]


async def build_nutrition_row(patient: dict[str, Any]) -> dict[str, Any]:
    pid = str(patient.get("_id") or "")
    weight = _weight(patient)
    nrs_doc = await _latest_score(patient, ["nrs2002", "nrs_2002", "NRS2002", "nutrition_risk_screening", "营养风险"])
    nutric_doc = await _latest_score(patient, ["nutric", "mnutric", "modified_nutric", "NUTRIC"])
    orders = await _nutrition_orders(patient)
    labs = await _latest_labs(patient)
    glucose = await _latest_blood_glucose(patient)
    if glucose:
        labs["glucose"] = glucose
    glucose_trend = await _blood_glucose_series(patient)
    route = _nutrition_route(orders)
    delivery = _estimate_delivery(orders, weight)
    tolerance = await _nutrition_tolerance(patient)
    prescription = _nutrition_prescription(delivery, route, tolerance, labs)
    icu_days = _days_since_admit(patient)
    nrs = nrs_doc.get("value") if nrs_doc else None
    nutric = nutric_doc.get("value") if nutric_doc else None
    tags = _risk_tags(route, delivery, labs, nrs, nutric, icu_days)
    if tolerance.get("interrupted") and "EN不耐受" not in tags:
        tags.insert(0, "EN不耐受")
    tasks = await _nutrition_tasks(pid)
    row = {
        "patient_id": pid,
        "hisPid": patient_his_pid(patient),
        "bed_no": _bed_no(patient),
        "name": _patient_name(patient),
        "age": calculate_age(patient.get("birthday") or patient.get("birthDate")),
        "diagnosis": _diagnosis(patient),
        "department": patient.get("hisDept") or patient.get("dept") or patient.get("department"),
        "weight": weight,
        "icu_days": round(icu_days, 1) if icu_days is not None else None,
        "route": route,
        **delivery,
        "nrs2002": nrs,
        "nrs2002_time": nrs_doc.get("time") if nrs_doc else None,
        "nutric": nutric,
        "nutric_time": nutric_doc.get("time") if nutric_doc else None,
        "labs": labs,
        "orders": orders[:8],
        "alerts": await _recent_nutrition_alerts(pid),
        "risk_tags": tags,
        "risk_level": _risk_level(nrs, nutric, tags),
        "trend_7d": _delivery_trend(orders, weight),
        "tolerance": tolerance,
        "pn_safety": _pn_safety(route, labs),
        "refeeding": _refeeding_panel(labs, nrs, nutric),
        "prescription": prescription,
        "glucose_trend": glucose_trend,
        "tasks": tasks,
        "open_task_count": sum(1 for task in tasks if task.get("status") == "open"),
    }
    row["actions"] = _actions(row)
    row["closed_loop"] = _closed_loop_summary(row)
    row["data_quality"] = _data_quality(row)
    row["nutrition_score"] = _nutrition_score(row)
    row["completion"] = _completion_score(row)
    return serialize_doc(row)


def build_nutrition_light_row(patient: dict[str, Any]) -> dict[str, Any]:
    pid = str(patient.get("_id") or "")
    weight = _weight(patient)
    icu_days = _days_since_admit(patient)
    route = "待评估"
    delivery = {
        "kcal_goal": round(weight * 25),
        "protein_goal": round(weight * 1.2, 1),
        "kcal_achieved_pct": None,
        "protein_achieved_pct": None,
        "kcal_delivered": None,
        "protein_delivered": None,
    }
    row = {
        "patient_id": pid,
        "hisPid": patient_his_pid(patient),
        "bed_no": _bed_no(patient),
        "name": _patient_name(patient),
        "age": calculate_age(patient.get("birthday") or patient.get("birthDate")),
        "diagnosis": _diagnosis(patient),
        "department": patient.get("hisDept") or patient.get("dept") or patient.get("department"),
        "weight": weight,
        "icu_days": round(icu_days, 1) if icu_days is not None else None,
        "route": route,
        **delivery,
        "nrs2002": None,
        "nutric": None,
        "labs": {},
        "orders": [],
        "alerts": [],
        "risk_tags": ["点击评估"],
        "risk_level": "unknown",
        "trend_7d": [{"day": f"D-{6 - idx}", "pct": 0} for idx in range(7)],
        "actions": [{"priority": "medium", "title": "查看营养详情", "target": "评分 / 医嘱 / 化验"}],
        "nutrition_score": None,
        "is_light": True,
    }
    return serialize_doc(row)


def _nutrition_score(row: dict[str, Any]) -> int:
    score = 100
    penalties = {
        "未启动": 28,
        "热量未达标": 16,
        "蛋白未达标": 14,
        "再喂养风险": 24,
        "血糖风险": 10,
        "脂肪乳风险": 12,
        "NRS待评": 8,
        "NUTRIC待评": 8,
    }
    for tag in row.get("risk_tags") or []:
        score -= penalties.get(tag, 4)
    return max(0, min(100, score))


async def nutrition_dashboard(*, department: str | None = None, dept_code: str | None = None, patient_scope: str = "in_dept", detail: bool = False) -> dict[str, Any]:
    query = _append_department_scope(research_patient_scope_query(patient_scope), department=department, dept_code=dept_code)
    projection = {
        "name": 1,
        "hisName": 1,
        "hisBed": 1,
        "bedNo": 1,
        "bed": 1,
        "hisPid": 1,
        "hisPID": 1,
        "patientId": 1,
        "pid": 1,
        "birthday": 1,
        "birthDate": 1,
        "weight": 1,
        "bodyWeight": 1,
        "admissionWeight": 1,
        "hisDept": 1,
        "dept": 1,
        "department": 1,
        "deptCode": 1,
        "departmentCode": 1,
        "clinicalDiagnosis": 1,
        "admissionDiagnosis": 1,
        "diagnosis": 1,
        "admitTime": 1,
        "admissionTime": 1,
        "inTime": 1,
        "created_at": 1,
        "status": 1,
    }
    cursor = runtime.db.col("patient").find(query, projection).sort([("hisBed", 1), ("bedNo", 1)]).limit(120)
    patients = [patient async for patient in cursor]
    if not detail:
        rows = [build_nutrition_light_row(patient) for patient in patients]
        rows.sort(key=lambda row: str(row.get("bed_no") or ""))
        return {
            "stats": {
                "patient_count": len(rows),
                "not_reached_count": 0,
                "refeeding_count": 0,
                "not_started_count": 0,
                "pn_review_count": 0,
                "avg_kcal_pct": 0,
                "route_counts": {"待评估": len(rows)},
                "is_light": True,
            },
            "patients": rows,
            "is_light": True,
        }
    semaphore = asyncio.Semaphore(8)

    async def _safe_row(patient: dict[str, Any]) -> dict[str, Any] | None:
        try:
            async with semaphore:
                return await build_nutrition_row(patient)
        except Exception as exc:
            logger.warning("build nutrition row failed patient_id=%s: %s", patient.get("_id"), exc)
            return None

    rows = [row for row in await asyncio.gather(*(_safe_row(patient) for patient in patients)) if row]
    rows.sort(key=lambda row: ({"high": 0, "medium": 1, "low": 2}.get(row.get("risk_level"), 3), str(row.get("bed_no") or "")))
    route_counts: dict[str, int] = {}
    for row in rows:
        route_counts[row.get("route") or "未开始"] = route_counts.get(row.get("route") or "未开始", 0) + 1
    kcal_values = [float(row.get("kcal_achieved_pct") or 0) for row in rows]
    quality_values = [float((row.get("data_quality") or {}).get("completeness") or 0) for row in rows]
    stats = {
        "patient_count": len(rows),
        "not_reached_count": sum(1 for row in rows if "热量未达标" in (row.get("risk_tags") or []) or "蛋白未达标" in (row.get("risk_tags") or [])),
        "refeeding_count": sum(1 for row in rows if "再喂养风险" in (row.get("risk_tags") or [])),
        "not_started_count": sum(1 for row in rows if row.get("route") == "未开始"),
        "pn_review_count": sum(1 for row in rows if "PN复核" in (row.get("risk_tags") or [])),
        "open_task_count": sum(int(row.get("open_task_count") or 0) for row in rows),
        "data_quality_avg": round(sum(quality_values) / len(quality_values), 1) if quality_values else 0,
        "avg_kcal_pct": round(sum(kcal_values) / len(kcal_values), 1) if kcal_values else 0,
        "route_counts": route_counts,
    }
    return {"stats": stats, "patients": rows, "priorities": _ward_priorities(rows), "role_actions": _role_actions(rows)}


async def nutrition_patient_detail(patient_id: str) -> dict[str, Any]:
    oid = safe_oid(patient_id)
    query = {"_id": oid} if oid else {"$or": [{"patient_id": patient_id}, {"hisPid": patient_id}, {"pid": patient_id}]}
    patient = await runtime.db.col("patient").find_one(query)
    if not patient:
        return {"patient": None, "message": "未找到患者"}
    return {"patient": await build_nutrition_row(patient)}


def _nutrition_ai_fallback(row: dict[str, Any]) -> dict[str, Any]:
    tags = set(row.get("risk_tags") or [])
    advice: list[dict[str, str]] = []
    if row.get("nrs2002") is None or row.get("nutric") is None:
        advice.append({"title": "先补齐评分", "detail": "补录 NRS2002 与 NUTRIC，决定营养风险层级。"})
    if "未启动" in tags or row.get("route") in {"未开始", "待评估"}:
        advice.append({"title": "确认营养路径", "detail": "评估 EN 优先；禁忌或不耐受时复核 PN/混合路径。"})
    if "热量未达标" in tags or "蛋白未达标" in tags:
        advice.append({"title": "追达标率", "detail": "对照目标热量/蛋白，查中断原因并调整泵速或补充方案。"})
    if "再喂养风险" in tags:
        advice.append({"title": "先稳电解质", "detail": "关注 P/K/Mg，低值时先纠正并慢速递增营养。"})
    if "血糖风险" in tags:
        advice.append({"title": "控糖复核", "detail": "复核血糖波动、胰岛素方案与营养输入速度。"})
    if "脂肪乳风险" in tags:
        advice.append({"title": "脂肪乳复核", "detail": "结合 TG、肝胆指标与感染状态评估是否减量或暂停。"})
    if not advice:
        advice.append({"title": "维持当前路径", "detail": "继续每日复核达标率、电解质和喂养耐受。"})
    return {
        "summary": "根据当前结构化数据生成的营养支持建议。",
        "advice": advice[:4],
        "degraded": True,
    }


async def nutrition_ai_advice(patient_id: str, refresh: bool = False) -> dict[str, Any]:
    cached = None if refresh else await runtime.db.col("score").find_one(
        {"patient_id": patient_id, "score_type": "nutrition_ai_advice"},
        sort=[("calc_time", -1)],
    )
    if cached:
        return {"advice": serialize_doc(cached.get("advice") or {}), "cached": True}

    detail = await nutrition_patient_detail(patient_id)
    row = detail.get("patient") or {}
    advice = _nutrition_ai_fallback(row)
    cfg = runtime.config
    if cfg:
        try:
            prompt = (
                "你是ICU营养支持助手。只输出简短中文，不要输出思考过程。"
                "基于结构化数据给出1句总评和最多4条可执行建议。"
                "避免长篇解释，不要替代医生医嘱。"
            )
            user = {
                "bed": row.get("bed_no"),
                "route": row.get("route"),
                "nrs2002": row.get("nrs2002"),
                "nutric": row.get("nutric"),
                "kcal_pct": row.get("kcal_achieved_pct"),
                "protein_pct": row.get("protein_achieved_pct"),
                "risk_tags": row.get("risk_tags"),
                "labs": row.get("labs"),
                "orders": row.get("orders"),
            }
            llm = await call_llm_chat(
                cfg=cfg,
                system_prompt=prompt,
                user_prompt=str(user),
                model=getattr(cfg, "llm_fast_model", None) or getattr(cfg.settings, "LLM_MODEL", None),
                temperature=0.1,
                max_tokens=700,
                timeout_seconds=25,
            )
            text = sanitize_llm_text(llm.get("text") or "")
            if text:
                advice = {
                    **advice,
                    "summary": text.splitlines()[0][:120],
                    "text": text,
                    "model": llm.get("model"),
                    "degraded": bool(llm.get("degraded_mode")),
                }
        except Exception as exc:
            advice["error"] = f"AI暂不可用，已给出规则建议：{str(exc)[:80]}"

    now = datetime.now()
    await runtime.db.col("score").insert_one(
        {
            "patient_id": patient_id,
            "score_type": "nutrition_ai_advice",
            "advice": advice,
            "calc_time": now,
            "created_at": now,
            "updated_at": now,
        }
    )
    return {"advice": serialize_doc(advice), "cached": False}


async def create_nutrition_task(patient_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    title = payload.get("title") or "营养支持复核"
    existing = await runtime.db.col("nutrition_tasks").find_one(
        {"patient_id": patient_id, "title": title, "status": "open"},
        sort=[("updated_at", -1)],
    )
    if existing:
        return {"task": serialize_doc(existing), "deduped": True}
    task = {
        "task_id": str(uuid.uuid4()),
        "patient_id": patient_id,
        "task_type": payload.get("task_type") or "nutrition_review",
        "title": title,
        "status": "open",
        "priority": payload.get("priority") or "medium",
        "payload": payload,
        "created_by": actor,
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("nutrition_tasks").insert_one(task)
    await write_audit_log(
        runtime.db,
        actor=actor,
        module="nutrition",
        action="create_task",
        target_type="patient",
        target_id=patient_id,
        detail=payload,
    )
    return {"task": serialize_doc(task)}


async def list_nutrition_tasks(patient_id: str) -> dict[str, Any]:
    return {"tasks": await _nutrition_tasks(patient_id)}


async def close_nutrition_task(task_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    update = {
        "status": payload.get("status") or "closed",
        "outcome": payload.get("outcome") or "已处理",
        "closed_by": actor,
        "closed_at": now,
        "updated_at": now,
    }
    result = await runtime.db.col("nutrition_tasks").update_one({"task_id": task_id}, {"$set": update})
    doc = await runtime.db.col("nutrition_tasks").find_one({"task_id": task_id})
    await write_audit_log(
        runtime.db,
        actor=actor,
        module="nutrition",
        action="close_task",
        target_type="nutrition_task",
        target_id=task_id,
        detail={"matched": result.matched_count, **update},
    )
    return {"task": serialize_doc(doc or {"task_id": task_id, **update})}
