"""血糖管理预警"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if not value:
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


class GlycemicControlMixin:
    def _glu_to_mmol_l(self, value: Any, unit: Any = None) -> float | None:
        v = _to_float(value)
        if v is None:
            return None
        u = str(unit or "").lower().replace(" ", "")
        # 常见换算: mg/dL / 18 = mmol/L
        if "mg/dl" in u:
            return round(v / 18.0, 3)
        if "mmol/l" in u or "mmol" in u:
            return round(v, 3)
        # 无单位时，按临床经验值做兜底判断
        if v > 35:
            return round(v / 18.0, 3)
        return round(v, 3)

    async def _get_bedside_glucose_points(self, pid_str: str, since: datetime, codes: list[str]) -> list[dict]:
        if not pid_str or not codes:
            return []
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "code": {"$in": codes}, "time": {"$gte": since}},
            {"time": 1, "code": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1, "unit": 1},
        ).sort("time", 1).limit(1500)

        points: list[dict] = []
        async for doc in cursor:
            t = _parse_dt(doc.get("time"))
            if not t:
                continue
            raw = doc.get("fVal")
            if raw is None:
                raw = doc.get("intVal")
            if raw is None:
                raw = doc.get("value")
            if raw is None:
                raw = doc.get("strVal")
            val = self._glu_to_mmol_l(raw, doc.get("unit"))
            if val is None:
                continue
            points.append(
                {
                    "time": t,
                    "value": val,
                    "source": "bedside",
                    "unit": "mmol/L",
                    "raw_code": doc.get("code"),
                }
            )
        return points

    async def _get_lab_glucose_points(self, his_pid: str, since: datetime) -> list[dict]:
        if not his_pid:
            return []
        series = await self._get_lab_series(his_pid, "glu", since, limit=800)
        points = []
        for item in series:
            t = item.get("time")
            if not isinstance(t, datetime):
                continue
            val = self._glu_to_mmol_l(item.get("value"), item.get("unit"))
            if val is None:
                continue
            points.append(
                {
                    "time": t,
                    "value": val,
                    "source": "lab",
                    "unit": "mmol/L",
                    "raw_unit": item.get("unit"),
                }
            )
        return points

    async def _get_drug_records(self, pid_str: str, since: datetime) -> list[dict]:
        if not pid_str:
            return []
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1, "startTime": 1, "orderTime": 1,
                "drugName": 1, "orderName": 1, "route": 1, "routeName": 1, "orderType": 1, "exeMethod": 1,
            },
        ).sort("executeTime", -1).limit(600)

        docs: list[dict] = []
        async for doc in cursor:
            t = _parse_dt(doc.get("executeTime")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            if not t or t < since:
                continue
            docs.append({**doc, "_event_time": t})
        return docs

    def _is_insulin_doc(self, doc: dict, insulin_keywords: list[str]) -> bool:
        text = " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName")).lower()
        return any(k.lower() in text for k in insulin_keywords)

    def _is_pump_doc(self, doc: dict, pump_keywords: list[str]) -> bool:
        text = " ".join(str(doc.get(k) or "") for k in ("route", "routeName", "orderType", "exeMethod")).lower()
        return any(k.lower() in text for k in pump_keywords)

    def _calc_cv_percent(self, values: list[float]) -> float | None:
        nums = [float(v) for v in values if v is not None]
        if len(nums) < 2:
            return None
        mean = sum(nums) / len(nums)
        if mean <= 0:
            return None
        var = sum((x - mean) ** 2 for x in nums) / max(1, (len(nums) - 1))
        sd = math.sqrt(var)
        return round(sd / mean * 100.0, 2)

    async def scan_glycemic_control(self) -> None:
        from .scanner_glycemic_control import GlycemicControlScanner

        await GlycemicControlScanner(self).scan()
