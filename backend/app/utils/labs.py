from __future__ import annotations

import logging
from datetime import datetime

from app.utils.parse import _parse_dt

logger = logging.getLogger("icu-alert")

_LAB_TESTS_ORDERED = [
    ("ph", {"keywords": ["ph", "酸碱度"], "unit": ""}),
    ("pco2", {"keywords": ["paco2", "pco2", "二氧化碳分压"], "unit": "mmHg"}),
    ("hco3", {"keywords": ["hco3", "碳酸氢根", "标准碳酸氢根", "实际碳酸氢根"], "unit": "mmol/L"}),
    ("ica", {"keywords": ["离子钙", "离子鈣", "ionized calcium", "ica", "ica²⁺"], "unit": "mmol/L"}),
    ("ca", {"keywords": ["总钙", "钙", "calcium", "ca"], "unit": "mmol/L"}),
    ("k", {"keywords": ["钾", "potassium", "k+"], "unit": "mmol/L"}),
    ("na", {"keywords": ["钠", "sodium", "na+"], "unit": "mmol/L"}),
    ("cl", {"keywords": ["氯", "chloride", "cl-"], "unit": "mmol/L"}),
    ("lac", {"keywords": ["乳酸", "lactate", "lac"], "unit": "mmol/L"}),
    ("mg", {"keywords": ["镁", "magnesium", "mg"], "unit": "mg/dL"}),
    ("po4", {"keywords": ["磷", "无机磷", "血磷", "phosphate", "phos", "po4"], "unit": "mg/dL"}),
    ("albumin", {"keywords": ["白蛋白", "albumin", "alb"], "unit": "g/L"}),
    ("glu", {"keywords": ["葡萄糖", "血糖", "glucose", "glu"], "unit": "mmol/L"}),
    ("hb", {"keywords": ["血红蛋白", "血紅蛋白", "hemoglobin", "hb"], "unit": "g/L"}),
    ("plt", {"keywords": ["血小板", "platelet", "plt"], "unit": "10^9/L"}),
    ("cr", {"keywords": ["肌酐", "creatinine", "cr"], "unit": "umol/L"}),
    ("egfr", {"keywords": ["egfr", "估算肾小球滤过率", "肾小球滤过率"], "unit": "mL/min/1.73m2"}),
    ("pct", {"keywords": ["降钙素原", "pct", "procalcitonin"], "unit": "ng/mL"}),
    ("inr", {"keywords": ["inr"], "unit": ""}),
    ("pt", {"keywords": ["凝血酶原时间", "pt"], "unit": "s"}),
    ("fib", {"keywords": ["纤维蛋白原", "fibrinogen", "fib"], "unit": "g/L"}),
    ("ddimer", {"keywords": ["d-dimer", "d二聚体", "d-二聚体", "fdp"], "unit": "mg/L"}),
    ("alt", {"keywords": ["谷丙转氨酶", "丙氨酸氨基转移酶", "alanine aminotransferase", "alt"], "unit": "U/L"}),
    ("ast", {"keywords": ["谷草转氨酶", "天门冬氨酸氨基转移酶", "aspartate aminotransferase", "ast"], "unit": "U/L"}),
    ("act", {"keywords": ["act", "活化凝血时间"], "unit": "s"}),
    ("trop", {"keywords": ["肌钙蛋白", "troponin"], "unit": ""}),
    ("bnp", {"keywords": ["bnp", "nt-probnp", "ntprobnp"], "unit": "pg/mL"}),
    ("bil", {"keywords": ["胆红素", "bilirubin", "tbil"], "unit": "umol/L"}),
    ("pao2", {"keywords": ["pao2", "po2", "氧分压"], "unit": "mmHg"}),
]


def _normalize_unit(unit) -> str:
    if unit is None:
        return ""
    return str(unit).strip().lower().replace("μ", "u")


def _convert_lab_value(test_key: str, value: float, unit: str) -> float:
    u = _normalize_unit(unit)

    if test_key == "cr":
        return value * 88.4 if "mg/dl" in u else value
    if test_key == "bil":
        return value * 17.1 if "mg/dl" in u else value
    if test_key == "pao2":
        return value * 7.5 if "kpa" in u else value
    if test_key == "pco2":
        return value * 7.5 if "kpa" in u else value
    if test_key == "albumin":
        return value * 10.0 if "g/dl" in u else value
    if test_key == "po4":
        return value * 3.1 if "mmol/l" in u else value
    if test_key == "mg":
        return value * 2.43 if "mmol/l" in u else value
    if test_key == "ddimer":
        is_ddu = "ddu" in u
        if "g/l" in u:
            converted = value * 1000.0
            return converted * 2 if is_ddu else converted
        if "mg/dl" in u:
            converted = value * 10.0
            return converted * 2 if is_ddu else converted
        if "ug/l" in u or "ng/ml" in u:
            converted = value / 1000.0
            return converted * 2 if is_ddu else converted
        if "ug/ml" in u:
            return value * 2 if is_ddu else value
        if "ng/l" in u:
            converted = value / 1_000_000.0
            return converted * 2 if is_ddu else converted
        if "mg/l" in u or not u:
            return value * 2 if is_ddu else value
        logger.warning(f"D-Dimer 单位无法识别: '{unit}'，按 mg/L FEU 处理")
        return value
    return value


def _match_lab_test(name: str) -> str | None:
    if not name:
        return None
    normalized = str(name).lower()
    for key, meta in _LAB_TESTS_ORDERED:
        for keyword in meta["keywords"]:
            keyword_lower = keyword.lower()
            if keyword_lower in normalized:
                if key == "mg" and not any(token in normalized for token in ["镁", "magnesium", "血镁"]):
                    continue
                if key == "k" and "肌酐" in normalized:
                    continue
                return key
    return None


def _lab_time(doc: dict) -> datetime | None:
    return (
        _parse_dt(doc.get("authTime"))
        or _parse_dt(doc.get("collectTime"))
        or _parse_dt(doc.get("requestTime"))
        or _parse_dt(doc.get("reportTime"))
        or _parse_dt(doc.get("resultTime"))
        or _parse_dt(doc.get("time"))
    )
