"""药物不良反应/相互作用"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


class DrugSafetyMixin:
    def _text_has_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

    def _event_time(self, doc: dict) -> datetime | None:
        return (
            _parse_dt(doc.get("executeTime"))
            or _parse_dt(doc.get("startTime"))
            or _parse_dt(doc.get("orderTime"))
        )

    async def _get_recent_drug_docs(self, pid_str: str, since: datetime) -> list[dict]:
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1,
                "startTime": 1,
                "orderTime": 1,
                "drugName": 1,
                "orderName": 1,
                "drugSpec": 1,
                "dose": 1,
                "doseUnit": 1,
                "unit": 1,
                "route": 1,
                "routeName": 1,
                "orderType": 1,
            },
        ).sort("executeTime", -1).limit(6000)

        rows: list[dict] = []
        async for doc in cursor:
            t = self._event_time(doc)
            if not t or t < since:
                continue
            rows.append({**doc, "_event_time": t})
        rows.sort(key=lambda x: x["_event_time"])
        return rows

    def _extract_dose_mg(self, doc: dict) -> float | None:
        dose = _to_float(doc.get("dose"))
        unit = str(doc.get("doseUnit") or doc.get("unit") or "").lower().replace(" ", "")
        if dose is not None and dose > 0:
            if any(k in unit for k in ("mg", "毫克")):
                return dose
            if any(k in unit for k in ("ug", "μg", "mcg", "微克")):
                return dose / 1000.0
            if any(k in unit for k in ("g", "克")) and "mg" not in unit:
                return dose * 1000.0
            return dose

        text = " ".join(str(doc.get(k) or "") for k in ("dose", "drugSpec", "orderName", "drugName"))
        m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|毫克|ug|μg|mcg|微克|g|克)", text, flags=re.I)
        if not m:
            return None
        val = _to_float(m.group(1))
        u = str(m.group(2)).lower()
        if val is None or val <= 0:
            return None
        if u in ("ug", "μg", "mcg", "微克"):
            return val / 1000.0
        if u in ("g", "克"):
            return val * 1000.0
        return val

    def _opioid_med_factor(self, text: str, factors: dict) -> float | None:
        t = str(text or "").lower()
        key_to_keywords = [
            ("morphine", ["吗啡", "morphine"]),
            ("fentanyl", ["芬太尼", "fentanyl"]),
            ("sufentanil", ["舒芬太尼", "sufentanil"]),
            ("remifentanil", ["瑞芬太尼", "remifentanil"]),
            ("oxycodone", ["羟考酮", "oxycodone"]),
            ("hydromorphone", ["氢吗啡酮", "hydromorphone"]),
            ("pethidine", ["哌替啶", "pethidine"]),
            ("meperidine", ["杜冷丁", "meperidine"]),
            ("tramadol", ["曲马多", "tramadol"]),
            ("codeine", ["可待因", "codeine"]),
            ("butorphanol", ["布托啡诺", "butorphanol"]),
        ]
        for key, kws in key_to_keywords:
            if any(k in t for k in kws):
                try:
                    return float(factors.get(key, 1.0))
                except Exception:
                    return 1.0
        return None

    def _continuous_opioid_course(self, opioid_events: list[dict], now: datetime, course_gap_hours: float) -> dict | None:
        if not opioid_events:
            return None
        times = sorted([e["_event_time"] for e in opioid_events if isinstance(e.get("_event_time"), datetime)])
        if not times:
            return None
        last_t = times[-1]
        start_t = last_t
        prev = last_t
        for t in reversed(times[:-1]):
            if (prev - t).total_seconds() / 3600.0 <= course_gap_hours:
                start_t = t
                prev = t
            else:
                break
        return {
            "start": start_t,
            "last": last_t,
            "duration_hours": round((last_t - start_t).total_seconds() / 3600.0, 2),
            "since_last_hours": round((now - last_t).total_seconds() / 3600.0, 2),
        }

    async def scan_drug_safety(self) -> None:
        from .scanner_drug_safety import DrugSafetyScanner

        await DrugSafetyScanner(self).scan()
