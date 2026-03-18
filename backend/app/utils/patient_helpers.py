from __future__ import annotations

from datetime import datetime


def calculate_age(birthday) -> str:
    """从出生日期计算年龄字符串"""
    if not birthday:
        return ""
    try:
        if isinstance(birthday, str):
            birthday = datetime.fromisoformat(birthday.replace("Z", "+00:00"))

        now = datetime.now()
        diff = now - birthday
        days = diff.days

        if days < 0:
            return "0天"
        if days < 30:
            return f"{days}天"
        if days < 365:
            return f"{days // 30}月"

        years = now.year - birthday.year
        if (now.month, now.day) < (birthday.month, birthday.day):
            years -= 1
        return f"{years}岁"
    except Exception:
        return ""


def active_patient_query() -> dict:
    return {
        "$or": [
            {"status": {"$nin": ["discharged", "invalid", "invaild"]}},
            {"status": {"$exists": False}},
        ]
    }


def patient_his_pid_candidates(patient: dict | None) -> list[str]:
    if not patient:
        return []
    keys = ["hisPid", "hisPID", "hisPatientId", "patientId", "patientID", "mrn", "hisMrn", "pid"]
    values: list[str] = []
    for key in keys:
        raw = patient.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text and text not in values:
            values.append(text)
    return values


def patient_his_pid(patient: dict | None) -> str:
    values = patient_his_pid_candidates(patient)
    return values[0] if values else ""


def normalize_bed(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.upper().replace("床", "")
    if text.startswith("BED"):
        text = text[3:]
    text = text.strip()
    import re

    match = re.search(r"\d+", text)
    if match:
        try:
            return str(int(match.group(0)))
        except Exception:
            return match.group(0)
    return text


def bed_match(a, b) -> bool:
    aa = normalize_bed(a)
    bb = normalize_bed(b)
    return bool(aa and bb and aa == bb)


def infer_clinical_tags(doc: dict) -> list:
    """根据诊断、护理级别等信息推断临床标签"""
    tags = []
    diag = (str(doc.get("clinicalDiagnosis", "")) + str(doc.get("admissionDiagnosis", ""))).lower()
    nursing = str(doc.get("nursingLevel", "")).lower()

    vent_kw = ["呼吸机", "机械通气", "气管插管", "气管切开", "ventilator", "mv"]
    if any(key in diag for key in vent_kw):
        tags.append({"tag": "ventilator", "label": "呼吸机", "icon": "🫁", "color": "#3b82f6"})

    crrt_kw = ["crrt", "血滤", "血液净化", "透析"]
    if any(key in diag for key in crrt_kw):
        tags.append({"tag": "crrt", "label": "CRRT", "icon": "🩸", "color": "#8b5cf6"})

    if "压疮" in diag or "压力性损伤" in diag:
        tags.append({"tag": "pressure_ulcer", "label": "压疮", "icon": "⚠️", "color": "#ef4444"})

    infect_kw = ["脓毒", "感染", "sepsis", "肺炎", "pneumonia"]
    if any(key in diag for key in infect_kw):
        tags.append({"tag": "infection", "label": "感染", "icon": "🦠", "color": "#f59e0b"})

    bleed_kw = ["出血", "hemorrhage", "bleeding"]
    if any(key in diag for key in bleed_kw):
        tags.append({"tag": "bleeding", "label": "出血", "icon": "🩹", "color": "#dc2626"})

    cons_kw = ["昏迷", "意识障碍", "脑出血", "脑梗", "coma"]
    if any(key in diag for key in cons_kw):
        tags.append({"tag": "consciousness", "label": "意识障碍", "icon": "🧠", "color": "#a855f7"})

    if "特级" in nursing or "特护" in nursing:
        tags.append({"tag": "special_care", "label": "特护", "icon": "⭐", "color": "#eab308"})

    mods_kw = ["mods", "多器官", "多脏器"]
    if any(key in diag for key in mods_kw):
        tags.append({"tag": "mods", "label": "MODS", "icon": "💔", "color": "#b91c1c"})

    return tags
