from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from app.utils.clinical import _cap_value
from app.utils.labs import _match_lab_test
from app.utils.parse import _parse_dt as _shared_parse_dt


def parse_dt(value: Any) -> datetime | None:
    return _shared_parse_dt(value)


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def normalize_unit(unit: Any) -> str:
    return (
        str(unit or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("μ", "u")
        .replace("µ", "u")
        .replace("渭", "u")
    )


def convert_unit(value: Any, from_unit: Any, to_unit: str, analyte: str) -> tuple[float | None, str]:
    """Strict unit conversion. Unknown source units never get guessed."""
    v = to_float(value)
    if v is None:
        return None, "invalid"
    src = normalize_unit(from_unit)
    dst = normalize_unit(to_unit)
    key = str(analyte or "").strip().lower()
    if not src:
        return None, "unknown"
    if key in {"glucose", "glu"} and dst in {"mmol/l", "mmol"}:
        if "mg/dl" in src:
            return round(v / 18.0, 3), "known"
        if "mmol" in src:
            return round(v, 3), "known"
        return None, "unknown"
    if key in {"creatinine", "cr"} and dst in {"umol/l", "umol"}:
        if "mg/dl" in src:
            return round(v * 88.4, 3), "known"
        if "umol" in src or "μmol" in src or "µmol" in src:
            return round(v, 3), "known"
        return None, "unknown"
    if dst and src == dst:
        return round(v, 3), "known"
    return None, "unknown"


def _text(doc: dict, keys: tuple[str, ...]) -> str:
    return " ".join(str(doc.get(k) or "") for k in keys).strip()


class EntityResolver:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cfg = getattr(self.config, "yaml_cfg", None) or {}
        for part in path:
            if not isinstance(cfg, dict) or part not in cfg:
                return default
            cfg = cfg[part]
        return cfg

    @staticmethod
    def _code(doc: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            value = str(doc.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _match_keyword(text: str, keywords: list[str]) -> bool:
        haystack = str(text or "").lower()
        return any(str(k).strip().lower() in haystack for k in keywords if str(k).strip())

    def resolve_drug(self, doc: dict) -> dict[str, Any]:
        name = _text(doc, ("drugName", "orderName", "name", "drugSpec", "route", "routeName"))
        code = self._code(doc, ("drugCode", "configDrug.drugCode", "orderCode", "drug_code", "hisDrugCode"))
        code_map = self._cfg("alert_engine", "entity_resolver", "drug_codes", default={}) or {}
        if code and isinstance(code_map, dict) and code in code_map:
            meta = dict(code_map.get(code) or {})
            return {"name": name, "code": code, "atc_class": meta.get("atc_class"), "is_antibiotic": bool(meta.get("is_antibiotic")), "spectrum": meta.get("spectrum"), "match_method": "code"}
        abx_kw = self._cfg("alert_engine", "antibiotic_stewardship", "antibiotic_keywords", default=[]) or []
        is_abx = self._match_keyword(name, list(abx_kw))
        return {"name": name, "code": code or None, "atc_class": None, "is_antibiotic": is_abx, "spectrum": None, "match_method": "keyword" if is_abx else "none"}

    def resolve_lab_item(self, doc: dict) -> dict[str, Any]:
        name = _text(doc, ("itemCnName", "itemName", "item", "name", "testName"))
        code = self._code(doc, ("itemCode", "code", "loinc", "LOINC"))
        code_map = self._cfg("alert_engine", "entity_resolver", "lab_item_codes", default={}) or {}
        if code and isinstance(code_map, dict) and code in code_map:
            meta = dict(code_map.get(code) or {})
            return {"name": name, "code": code, "loinc": meta.get("loinc"), "test_key": meta.get("test_key"), "match_method": "code"}
        test_key = _match_lab_test(name or code)
        return {"name": name or code, "code": code or None, "loinc": None, "test_key": test_key, "match_method": "keyword" if test_key else "none"}


async def urine_ml_h(db: Any, config: Any, pid_str: str, now: datetime, hours: int = 6) -> float | None:
    since = now - timedelta(hours=max(int(hours or 1), 1))
    cfg = getattr(config, "yaml_cfg", None) or {}
    configured_codes = (((cfg.get("alert_engine") or {}).get("data_mapping") or {}).get("urine_output") or {}).get("codes") or []
    codes = list(dict.fromkeys([
        *[str(x) for x in configured_codes if str(x).strip()],
        "param_niaoLiang",
        "param_niaoLiang_pure",
        "param_udd_urine_cur",
        "param_udd_urine_1h",
        "param_udd_urine_total",
        "param_udd_urine_24h",
        "param_out_hour",
        "param_out_hour_sum",
        "param_out_day",
    ]))
    if not pid_str or not codes:
        return None
    cursor = db.col("bedside").find(
        {"pid": pid_str, "time": {"$gte": since}, "code": {"$in": codes}},
        {"time": 1, "code": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
    ).sort("time", 1)
    rows = [row async for row in cursor]
    total = 0.0
    points = 0
    cum_total: list[float] = []
    cum_24h: list[float] = []
    out_vals: list[float] = []
    for row in rows:
        code = str(row.get("code") or "")
        val = None
        for key in ("fVal", "intVal", "strVal", "value"):
            val = to_float(row.get(key))
            if val is not None:
                break
        if val is None:
            val = _cap_value(row)
        if val is None or val < 0:
            continue
        if code in {"param_niaoLiang", "param_niaoLiang_pure", "param_udd_urine_cur", "param_udd_urine_1h"}:
            total += val
            points += 1
        elif code == "param_udd_urine_total":
            cum_total.append(val)
        elif code == "param_udd_urine_24h":
            cum_24h.append(val)
        else:
            out_vals.append(val)
    if points > 0:
        return round(total / max(hours, 1), 2)
    if len(cum_total) >= 2:
        return round(max(cum_total[-1] - cum_total[0], 0.0) / max(hours, 1), 2)
    if cum_24h:
        return round(max(cum_24h[-1], 0.0) / 24.0, 2)
    if len(out_vals) >= 2:
        return round(max(out_vals[-1] - out_vals[0], 0.0) / max(hours, 1), 2)
    return None
