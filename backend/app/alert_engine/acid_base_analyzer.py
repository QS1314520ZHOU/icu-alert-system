"""血气酸碱自动分析工具。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _parse_num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _norm_unit(unit: Any) -> str:
    return str(unit or "").strip().lower().replace("μ", "u")


def _lab_time(doc: dict) -> datetime | None:
    value = (
        doc.get("authTime")
        or doc.get("collectTime")
        or doc.get("requestTime")
        or doc.get("reportTime")
        or doc.get("resultTime")
        or doc.get("time")
    )
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _item_name(doc: dict) -> str:
    return str(
        doc.get("itemCnName")
        or doc.get("itemName")
        or doc.get("item")
        or doc.get("itemCode")
        or ""
    ).strip()


def _item_code(doc: dict) -> str:
    return str(doc.get("itemCode") or doc.get("code") or "").strip()


def _doc_text(doc: dict) -> str:
    return " ".join(
        str(v).strip()
        for v in [
            doc.get("examName"),
            doc.get("requestName"),
            doc.get("orderName"),
            _item_name(doc),
            _item_code(doc),
        ]
        if v
    ).lower()


def _convert_field_value(field: str, value: float, unit: str) -> float:
    u = _norm_unit(unit)
    if field == "albumin":
        if "g/dl" in u:
            return value
        if "g/l" in u:
            return value / 10.0
    if field in {"paco2"} and "kpa" in u:
        return value * 7.50062
    if field in {"po4"}:
        if "mg/dl" in u:
            return value / 3.1
    if field == "mg":
        if "mg/dl" in u:
            return value / 2.43
    return value


FIELD_KEYWORDS: dict[str, list[str]] = {
    "ph": ["ph", "酸碱度"],
    "paco2": ["paco2", "pco2", "二氧化碳分压", "二氧化碳"],
    "pao2": ["pao2", "po2", "氧分压"],
    "hco3": ["hco3", "碳酸氢根", "碳酸氢盐", "标准碳酸氢根", "实际碳酸氢根", "sbc", "abc"],
    "na": ["na+", "na", "钠", "sodium"],
    "k": ["k+", "k", "钾", "potassium"],
    "cl": ["cl-", "cl", "氯", "chloride"],
    "albumin": ["albumin", "alb", "白蛋白"],
    "lactate": ["lactate", "lac", "乳酸"],
    "mg": ["mg", "镁", "magnesium"],
    "po4": ["po4", "phos", "phosphate", "磷", "无机磷", "血磷"],
    "ica": ["ica", "离子钙", "ionized calcium"],
    "ca": ["ca", "总钙", "calcium", "钙"],
}


BLOOD_GAS_HINT_KEYWORDS = [
    "血气",
    "a-ado2",
    "p/f ratio",
    "fio2",
    "pao2",
    "po2",
    "pco2",
    "hco3act",
    "hco3std",
    "be(",
    "so2",
    "cohb",
    "methb",
    "o2hb",
]

NON_BLOOD_HINT_KEYWORDS = [
    "爱威",
    "优利特",
    "微白蛋白",
    "尿常规",
    "尿沉渣",
    "fa280",
    "粪便",
]

SUPPORTIVE_FALLBACK_FIELDS = ("na", "k", "cl", "albumin", "lactate", "mg", "po4", "ica", "ca")

BGA_TEMP_FIELD_ALIASES: dict[str, list[str]] = {
    "ph": ["param_bg_pH", "param_bg_pH_T", "ph", "bgaph", "abgph", "phvalue"],
    "paco2": ["param_bg_pco2", "param_bg_pco2_T", "paco2", "pco2", "bgapco2", "abgpco2"],
    "pao2": ["param_bg_po2", "param_bg_po2_T", "pao2", "po2", "bgapo2", "abgpo2"],
    "hco3": ["param_bg_HCO3-", "param_bg_HCO3-c", "param_bg_HCO3std", "hco3", "hco3act", "hco3std", "actualhco3", "stdhco3", "abchco3", "sbchco3"],
    "na": ["param_bg_Na+", "na", "sodium", "na+"],
    "k": ["param_bg_K+", "k", "potassium", "k+"],
    "cl": ["param_bg_Cl-", "cl", "chloride", "cl-"],
    "albumin": ["param_ana_ALB", "albumin", "alb"],
    "lactate": ["param_bg_Lac", "lactate", "lac"],
    "mg": ["param_bg_Mg++", "mg", "magnesium"],
    "po4": ["param_bg_PO4---", "po4", "phosphate", "phos"],
    "ica": ["param_bg_Ca+", "param_bg_Ca+74", "ica", "ionizedcalcium", "ionizedca", "freeca"],
    "ca": ["param_bg_Ca+", "param_bg_Ca+74", "ca", "calcium", "totalca", "totalcalcium"],
}

BGA_TEMP_FIELD_LABELS: dict[str, str] = {
    "ph": "pH",
    "paco2": "PaCO2",
    "pao2": "PaO2",
    "hco3": "HCO3-",
    "na": "Na+",
    "k": "K+",
    "cl": "Cl-",
    "albumin": "白蛋白",
    "lactate": "乳酸",
    "mg": "镁",
    "po4": "无机磷",
    "ica": "离子钙",
    "ca": "总钙",
}

BGA_TEMP_DEFAULT_UNITS: dict[str, str] = {
    "ph": "",
    "paco2": "mmHg",
    "pao2": "mmHg",
    "hco3": "mmol/L",
    "na": "mmol/L",
    "k": "mmol/L",
    "cl": "mmol/L",
    "albumin": "g/dL",
    "lactate": "mmol/L",
    "mg": "mmol/L",
    "po4": "mmol/L",
    "ica": "mmol/L",
    "ca": "mmol/L",
}


def _is_non_blood_context(doc: dict) -> bool:
    text = _doc_text(doc)
    item_name = _item_name(doc).lower()
    item_code = _item_code(doc).lower()

    if item_code.startswith("ny"):
        return True
    if any(keyword in text for keyword in NON_BLOOD_HINT_KEYWORDS):
        return True
    if any(keyword in item_name for keyword in ["尿胆", "尿糖", "尿胆原", "微白蛋白", "尿白蛋白"]):
        return True
    return False


def _value_is_plausible(field: str, value: float) -> bool:
    ranges = {
        "ph": (6.8, 7.8),
        "paco2": (10.0, 120.0),
        "pao2": (20.0, 500.0),
        "hco3": (3.0, 60.0),
        "na": (100.0, 180.0),
        "k": (1.0, 10.0),
        "cl": (60.0, 140.0),
        "albumin": (0.5, 6.5),
        "lactate": (0.1, 30.0),
        "mg": (0.2, 10.0),
        "po4": (0.2, 20.0),
        "ica": (0.2, 3.0),
        "ca": (0.5, 5.0),
    }
    lo_hi = ranges.get(field)
    if not lo_hi:
        return True
    lo, hi = lo_hi
    return lo <= value <= hi


def _match_field(doc: dict) -> str | None:
    normalized = " ".join(filter(None, [_item_name(doc), _item_code(doc)])).strip().lower()
    if not normalized or _is_non_blood_context(doc):
        return None
    for field, keywords in FIELD_KEYWORDS.items():
        for kw in keywords:
            kw_l = kw.lower()
            if kw_l in normalized:
                if field == "k" and "肌酐" in normalized:
                    continue
                if field == "mg" and ("image" in normalized or "mg/dl" in normalized):
                    continue
                if field == "albumin" and any(x in normalized for x in ["微白蛋白", "尿白蛋白", "microalbumin", " ma "]):
                    continue
                return field
    return None


def _field_row(field: str, value: float | None, unit: str = "", abnormal: bool = False) -> dict[str, Any]:
    return {"field": field, "value": value, "unit": unit, "abnormal": abnormal}


def _normalize_bga_temp_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _flatten_bga_temp_doc(doc: dict[str, Any], depth: int = 0, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if not isinstance(doc, dict) or depth > 2:
        return flat
    for key, value in doc.items():
        merged_key = f"{prefix}{key}"
        norm_key = _normalize_bga_temp_key(merged_key)
        if isinstance(value, dict):
            flat.update(_flatten_bga_temp_doc(value, depth + 1, f"{merged_key}_"))
            continue
        if norm_key and norm_key not in flat:
            flat[norm_key] = value
    return flat


def bga_temp_time(doc: dict[str, Any]) -> datetime | None:
    value = (
        doc.get("sampleTime")
        or doc.get("sample_time")
        or doc.get("recordTime")
        or doc.get("reportTime")
        or doc.get("authTime")
        or doc.get("collectTime")
        or doc.get("createTime")
        or doc.get("createdTime")
        or doc.get("updatedTime")
        or doc.get("updateTime")
        or doc.get("time")
    )
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def extract_bga_temp_items(doc: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    sample_time = bga_temp_time(doc)
    exam_name = str(doc.get("examName") or doc.get("panelName") or doc.get("sourceName") or "SmartCare 血气(bGATemp)").strip() or "SmartCare 血气(bGATemp)"
    items: list[dict[str, Any]] = []
    bedsides = doc.get("bedsides") if isinstance(doc.get("bedsides"), list) else []
    if bedsides:
        latest_by_code: dict[str, dict[str, Any]] = {}
        for row in bedsides:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            latest_by_code[code] = row
        for field, aliases in BGA_TEMP_FIELD_ALIASES.items():
            matched = None
            matched_code = ""
            for alias in aliases:
                for candidate in latest_by_code.keys():
                    if _normalize_bga_temp_key(candidate) == _normalize_bga_temp_key(alias):
                        matched = latest_by_code[candidate]
                        matched_code = candidate
                        break
                if matched is not None:
                    break
            raw_value = None if matched is None else matched.get("fVal", matched.get("value", matched.get("strVal")))
            num = _parse_num(raw_value)
            if num is None:
                continue
            unit = str(matched.get("unit") or matched.get("resultUnit") or BGA_TEMP_DEFAULT_UNITS.get(field, "")) if matched else BGA_TEMP_DEFAULT_UNITS.get(field, "")
            items.append(
                {
                    "itemName": matched.get("name") if matched else BGA_TEMP_FIELD_LABELS.get(field, field),
                    "itemCnName": matched.get("name") if matched else BGA_TEMP_FIELD_LABELS.get(field, field),
                    "itemCode": matched_code or field,
                    "result": raw_value,
                    "unit": unit,
                    "resultUnit": unit,
                    "authTime": matched.get("time") if matched and matched.get("time") else sample_time,
                    "time": matched.get("time") if matched and matched.get("time") else sample_time,
                    "examName": exam_name,
                    "sourceTable": "bGATemp",
                }
            )
        if items:
            return items

    flat = _flatten_bga_temp_doc(doc)
    for field, aliases in BGA_TEMP_FIELD_ALIASES.items():
        raw_value = None
        alias_key = ""
        for alias in aliases:
            lookup = _normalize_bga_temp_key(alias)
            if lookup in flat:
                raw_value = flat.get(lookup)
                alias_key = lookup
                break
        num = _parse_num(raw_value)
        if num is None:
            continue
        unit = ""
        if alias_key:
            for suffix in ("unit", "resultunit", "valueunit"):
                maybe_unit = flat.get(f"{alias_key}{suffix}")
                if maybe_unit:
                    unit = str(maybe_unit)
                    break
        unit = unit or BGA_TEMP_DEFAULT_UNITS.get(field, "")
        items.append(
            {
                "itemName": BGA_TEMP_FIELD_LABELS.get(field, field),
                "itemCnName": BGA_TEMP_FIELD_LABELS.get(field, field),
                "itemCode": field,
                "result": raw_value,
                "unit": unit,
                "resultUnit": unit,
                "authTime": sample_time,
                "time": sample_time,
                "examName": exam_name,
                "sourceTable": "bGATemp",
            }
        )
    return items


def extract_acid_base_snapshot(items: list[dict], fallback_latest: dict[str, dict] | None = None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"fields": {}, "time": None}
    fallback_latest = fallback_latest or {}
    latest_by_field: dict[str, tuple[datetime | None, float, str, str]] = {}

    for doc in items:
        name = _item_name(doc)
        field = _match_field(doc)
        if not field:
            continue
        raw = doc.get("result") or doc.get("resultValue") or doc.get("value")
        num = _parse_num(raw)
        if num is None:
            continue
        unit = str(doc.get("unit") or doc.get("resultUnit") or "")
        converted = _convert_field_value(field, num, unit)
        if not _value_is_plausible(field, converted):
            continue
        t = _lab_time(doc)
        prev = latest_by_field.get(field)
        if prev is None or (t or datetime.min) >= (prev[0] or datetime.min):
            latest_by_field[field] = (t, converted, unit, name)

    for field, info in latest_by_field.items():
        t, value, unit, name = info
        snapshot["fields"][field] = {"value": value, "unit": unit, "source_name": name, "time": t}
        if t and (snapshot["time"] is None or t > snapshot["time"]):
            snapshot["time"] = t

    # albumin 等可从非血气同次之外的最近检验补齐
    for field in ("na", "k", "cl", "albumin", "lactate", "mg", "po4", "ica", "ca"):
        if field in snapshot["fields"]:
            continue
        fallback = fallback_latest.get(field)
        if not fallback:
            continue
        snapshot["fields"][field] = {
            "value": fallback.get("value"),
            "unit": fallback.get("unit", ""),
            "source_name": fallback.get("raw_name", field),
            "fallback": True,
            "time": fallback.get("time"),
        }
        f_time = fallback.get("time")
        if snapshot["time"] is None and isinstance(f_time, datetime):
            snapshot["time"] = f_time

    return snapshot


def is_blood_gas_snapshot(
    snapshot: dict[str, Any],
    items: list[dict] | None = None,
    exam_name: str | None = None,
) -> bool:
    fields = snapshot.get("fields") or {}
    if not fields:
        return False

    joined = " ".join(
        [str(exam_name or "").lower(), *[_doc_text(doc) for doc in (items or [])]]
    )
    if joined and any(keyword in joined for keyword in NON_BLOOD_HINT_KEYWORDS):
        if not any(keyword in joined for keyword in BLOOD_GAS_HINT_KEYWORDS):
            return False

    ph = _parse_num(fields.get("ph", {}).get("value"))
    has_ph = ph is not None and 6.8 <= ph <= 7.8
    has_paco2 = _parse_num(fields.get("paco2", {}).get("value")) is not None
    has_pao2 = _parse_num(fields.get("pao2", {}).get("value")) is not None
    has_hco3 = _parse_num(fields.get("hco3", {}).get("value")) is not None
    has_gas_hint = any(keyword in joined for keyword in BLOOD_GAS_HINT_KEYWORDS)

    if has_gas_hint and (has_ph or has_paco2 or has_pao2 or has_hco3):
        return True
    if has_ph and (has_paco2 or has_pao2 or has_hco3):
        return True
    if has_paco2 and has_pao2:
        return True
    return False


def _dominant_primary(ph: float | None, paco2: float | None, hco3: float | None) -> str:
    if ph is None:
        return "undetermined"
    acidemia = ph < 7.35
    alkalemia = ph > 7.45
    if acidemia:
        if paco2 is not None and paco2 > 45 and (hco3 is None or hco3 >= 22):
            return "resp_acidosis"
        if hco3 is not None and hco3 < 22 and (paco2 is None or paco2 <= 45):
            return "met_acidosis"
        resp_score = max(0.0, ((paco2 or 40.0) - 40.0) / 5.0)
        met_score = max(0.0, (24.0 - (hco3 or 24.0)) / 2.0)
        return "resp_acidosis" if resp_score > met_score else "met_acidosis"
    if alkalemia:
        if paco2 is not None and paco2 < 35 and (hco3 is None or hco3 <= 26):
            return "resp_alkalosis"
        if hco3 is not None and hco3 > 26 and (paco2 is None or paco2 >= 35):
            return "met_alkalosis"
        resp_score = max(0.0, (40.0 - (paco2 or 40.0)) / 5.0)
        met_score = max(0.0, ((hco3 or 24.0) - 24.0) / 2.0)
        return "resp_alkalosis" if resp_score > met_score else "met_alkalosis"
    if hco3 is not None and hco3 < 22:
        return "met_acidosis"
    if hco3 is not None and hco3 > 26:
        return "met_alkalosis"
    if paco2 is not None and paco2 > 45:
        return "resp_acidosis"
    if paco2 is not None and paco2 < 35:
        return "resp_alkalosis"
    return "undetermined"


def _respiratory_compensation(paco2: float | None, hco3: float | None) -> dict[str, Any] | None:
    if paco2 is None or hco3 is None:
        return None

    if paco2 > 45:
        delta = (paco2 - 40.0) / 10.0
        acute_expected = 24.0 + delta * 1.0
        chronic_expected = 24.0 + delta * 3.5
        acute_gap = abs(hco3 - acute_expected)
        chronic_gap = abs(hco3 - chronic_expected)
        chronicity = "急性" if acute_gap <= chronic_gap else "慢性"
        expected = acute_expected if chronicity == "急性" else chronic_expected
        if hco3 < acute_expected - 2:
            mixed = "合并代谢性酸中毒"
        elif hco3 > chronic_expected + 2:
            mixed = "合并代谢性碱中毒"
        else:
            mixed = ""
        return {
            "type": "呼吸性酸中毒",
            "chronicity": chronicity,
            "expected_hco3": round(expected, 1),
            "acute_expected_hco3": round(acute_expected, 1),
            "chronic_expected_hco3": round(chronic_expected, 1),
            "mixed": mixed,
        }

    if paco2 < 35:
        delta = (40.0 - paco2) / 10.0
        acute_expected = 24.0 - delta * 2.0
        chronic_expected = 24.0 - delta * 4.0
        acute_gap = abs(hco3 - acute_expected)
        chronic_gap = abs(hco3 - chronic_expected)
        chronicity = "急性" if acute_gap <= chronic_gap else "慢性"
        expected = acute_expected if chronicity == "急性" else chronic_expected
        if hco3 > acute_expected + 2:
            mixed = "合并代谢性碱中毒"
        elif hco3 < chronic_expected - 2:
            mixed = "合并代谢性酸中毒"
        else:
            mixed = ""
        return {
            "type": "呼吸性碱中毒",
            "chronicity": chronicity,
            "expected_hco3": round(expected, 1),
            "acute_expected_hco3": round(acute_expected, 1),
            "chronic_expected_hco3": round(chronic_expected, 1),
            "mixed": mixed,
        }
    return None


def _field_mmol_value(field_info: dict[str, Any] | None, *, default_factor: float | None = None) -> float | None:
    if not field_info:
        return None
    value = _parse_num(field_info.get("value"))
    if value is None:
        return None
    unit = _norm_unit(field_info.get("unit"))
    if not unit:
        return value if default_factor is None else value / default_factor
    if "mg/dl" in unit:
        return value if default_factor is None else value / default_factor
    return value


def interpret_acid_base(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    fields = snapshot.get("fields") or {}
    ph = _parse_num(fields.get("ph", {}).get("value"))
    paco2 = _parse_num(fields.get("paco2", {}).get("value"))
    hco3 = _parse_num(fields.get("hco3", {}).get("value"))
    na = _parse_num(fields.get("na", {}).get("value"))
    k = _parse_num(fields.get("k", {}).get("value"))
    cl = _parse_num(fields.get("cl", {}).get("value"))
    albumin_g_dl = _parse_num(fields.get("albumin", {}).get("value"))
    lactate = _parse_num(fields.get("lactate", {}).get("value"))
    mg_mmol = _field_mmol_value(fields.get("mg"), default_factor=2.43)
    ica = _field_mmol_value(fields.get("ica"))
    ca = _field_mmol_value(fields.get("ca"))

    if ph is None and hco3 is None and paco2 is None:
        return None

    dominant_primary = _dominant_primary(ph, paco2, hco3)
    acidemia = ph is not None and ph < 7.35
    alkalemia = ph is not None and ph > 7.45
    ag = None
    corrected_ag = None
    delta_ratio = None
    lactate_corrected_ag = None
    sid = None
    stewart_summary = ""
    compensation = "未知"
    primary = "未定"
    secondary = ""
    tertiary = ""
    respiratory_analysis = None

    if na is not None and k is not None and cl is not None and hco3 is not None:
        ag = round(na + k - cl - hco3, 1)
        albumin_use = albumin_g_dl if albumin_g_dl is not None else 4.0
        corrected_ag = round(ag + 2.5 * (4.0 - albumin_use), 1)
        if lactate is not None:
            lactate_corrected_ag = round(corrected_ag - lactate, 1)
        delta_hco3 = 24.0 - hco3
        if corrected_ag is not None and delta_hco3 > 0:
            delta_ratio = round((corrected_ag - 12.0) / delta_hco3, 2)

    sid_terms = [x for x in [na, k, ca or ica, mg_mmol] if x is not None]
    if sid_terms and cl is not None:
        sid = round(sum(sid_terms) - cl - (lactate or 0.0), 1)
        if sid < 38:
            stewart_summary = "SID降低，支持强离子差相关代谢性酸中毒"
        elif sid > 42:
            stewart_summary = "SID升高，支持强离子差相关代谢性碱中毒"
        else:
            stewart_summary = "SID大致正常"

    # 主要紊乱
    if acidemia:
        if dominant_primary == "resp_acidosis":
            primary = "呼吸性酸中毒"
        elif hco3 is not None and hco3 < 22:
            if corrected_ag is not None and corrected_ag > 12:
                primary = "代谢性酸中毒(AG增高)"
            else:
                primary = "代谢性酸中毒(AG正常)"
        else:
            primary = "酸血症(待定型)"
    elif alkalemia:
        if dominant_primary == "resp_alkalosis":
            primary = "呼吸性碱中毒"
        elif hco3 is not None and hco3 > 26:
            primary = "代谢性碱中毒"
        else:
            primary = "碱血症(待定型)"
    else:
        if dominant_primary == "resp_acidosis":
            primary = "呼吸性酸中毒(已代偿/混合)"
        elif dominant_primary == "resp_alkalosis":
            primary = "呼吸性碱中毒(已代偿/混合)"
        elif hco3 is not None and hco3 < 22:
            if corrected_ag is not None and corrected_ag > 12:
                primary = "代谢性酸中毒(已代偿/混合)"
            else:
                primary = "代谢性酸中毒(AG正常)"
        elif hco3 is not None and hco3 > 26:
            primary = "代谢性碱中毒(已代偿/混合)"

    # Winter 公式
    if hco3 is not None and paco2 is not None and "代谢性酸中毒" in primary:
        expected = 1.5 * hco3 + 8
        low = expected - 2
        high = expected + 2
        if low <= paco2 <= high:
            compensation = "适当"
        else:
            compensation = "不适当"
            if paco2 > high:
                secondary = f"呼吸性酸中毒(代偿不足，PaCO₂ {round(paco2,1)} > 预计{round(high,1)})"
            elif paco2 < low:
                secondary = f"呼吸性碱中毒(代偿不足，PaCO₂ {round(paco2,1)} < 预计{round(low,1)})"
    elif "代谢性碱中毒" in primary and paco2 is not None and hco3 is not None:
        expected = 0.7 * (hco3 - 24) + 40
        if abs(paco2 - expected) <= 5:
            compensation = "适当"
        else:
            compensation = "不适当"
            secondary = "合并呼吸性紊乱"
    elif "呼吸性" in primary and paco2 is not None and hco3 is not None:
        respiratory_analysis = _respiratory_compensation(paco2, hco3)
        if respiratory_analysis:
            primary = f"{respiratory_analysis['type']}({respiratory_analysis['chronicity']})"
            compensation = f"{respiratory_analysis['chronicity']}代偿"
            if respiratory_analysis.get("mixed"):
                secondary = respiratory_analysis["mixed"]

    if delta_ratio is not None:
        if delta_ratio > 2:
            tertiary = f"合并代谢性碱中毒(Delta ratio {delta_ratio})"
        elif delta_ratio < 1:
            tertiary = f"合并非AG代谢性酸中毒(Delta ratio {delta_ratio})"

    lactate_context = ""
    if lactate is not None and lactate > 2 and corrected_ag is not None:
        if lactate_corrected_ag is not None and lactate_corrected_ag > 4:
            lactate_context = "乳酸升高，但仍存在其他未测有机酸负荷"
        else:
            lactate_context = "乳酸性酸中毒为主"

    abnormalities = [
        _field_row("ph", ph, abnormal=ph is not None and (ph < 7.35 or ph > 7.45)),
        _field_row("paco2", paco2, "mmHg", abnormal=paco2 is not None and (paco2 < 35 or paco2 > 45)),
        _field_row("hco3", hco3, "mmol/L", abnormal=hco3 is not None and (hco3 < 22 or hco3 > 26)),
        _field_row("na", na, "mmol/L", abnormal=na is not None and (na < 135 or na > 145)),
        _field_row("k", k, "mmol/L", abnormal=k is not None and (k < 3.5 or k > 5.5)),
        _field_row("cl", cl, "mmol/L", abnormal=cl is not None and (cl < 98 or cl > 107)),
        _field_row("albumin", albumin_g_dl, "g/dL", abnormal=albumin_g_dl is not None and albumin_g_dl < 3.5),
        _field_row("lactate", lactate, "mmol/L", abnormal=lactate is not None and lactate > 2),
    ]

    return {
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "AG": ag,
        "corrected_AG": corrected_ag,
        "delta_ratio": delta_ratio,
        "lactate_corrected_AG": lactate_corrected_ag,
        "lactate_context": lactate_context,
        "SID": sid,
        "stewart_summary": stewart_summary,
        "compensation": compensation,
        "respiratory_compensation": respiratory_analysis,
        "snapshot_time": snapshot.get("time"),
        "abnormal_components": abnormalities,
        "inputs": {
            "ph": ph,
            "PaCO2": paco2,
            "HCO3": hco3,
            "Na": na,
            "K": k,
            "Cl": cl,
            "Albumin_g_dL": albumin_g_dl,
            "Lactate": lactate,
            "Mg_mmol_L": mg_mmol,
            "iCa_mmol_L": ica,
            "Ca_mmol_L": ca,
        },
    }
