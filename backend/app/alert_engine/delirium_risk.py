"""谵妄风险评估（PRE-DELIRIC近似）"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


def _to_num(value: Any) -> float | None:
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


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
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


def _severity_rank(severity: str) -> int:
    return {"warning": 1, "high": 2, "critical": 3}.get(str(severity), 0)


class DeliriumRiskMixin:
    def _parse_age_years(self, patient_doc: dict) -> float | None:
        for key in ("age", "hisAge"):
            raw = patient_doc.get(key)
            if raw is None:
                continue
            if isinstance(raw, (int, float)):
                return float(raw)
            s = str(raw).strip()
            if not s:
                continue
            if s.endswith("天"):
                d = _to_num(s)
                return d / 365.0 if d is not None else None
            if s.endswith("月"):
                m = _to_num(s)
                return m / 12.0 if m is not None else None
            num = _to_num(s)
            if num is not None:
                return num
        return None

    def _is_emergency_admission(self, patient_doc: dict) -> bool:
        text = " ".join(
            str(patient_doc.get(k) or "")
            for k in ("admissionType", "admitType", "inType", "admissionSource", "admissionWay", "source")
        ).lower()
        if not text.strip():
            return False
        return any(k in text for k in ("急诊", "emergency", "er", "急救"))

    def _contains_any(self, values: list[str], keywords: list[str]) -> bool:
        if not values or not keywords:
            return False
        return any(any(k in v for k in keywords) for v in values)

    async def _has_mechanical_ventilation(self, patient_doc: dict) -> bool:
        device_id = await self._get_device_id_for_patient(patient_doc, ["vent"])
        if not device_id:
            return False
        cap = await self._get_latest_device_cap(device_id, codes=["param_FiO2", "param_vent_resp", "param_vent_VE"])
        return bool(cap)

    async def _load_delirium_labs(self, his_pid: str, lookback_hours: int = 72) -> dict:
        since = datetime.now() - timedelta(hours=lookback_hours)
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(600)

        result: dict = {
            "bun": None,
            "lactate": None,
            "ph": None,
            "hco3": None,
            "be": None,
        }

        async for doc in cursor:
            t = _lab_time(doc)
            if t and t < since:
                continue

            raw_name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").lower()
            if not raw_name:
                continue

            raw_val = doc.get("result") or doc.get("resultValue") or doc.get("value")
            num = _to_num(raw_val)
            if num is None:
                continue
            unit = str(doc.get("unit") or doc.get("resultUnit") or "").strip()

            if result["bun"] is None and any(k in raw_name for k in ("尿素氮", "bun", "urea nitrogen")):
                result["bun"] = {"value": num, "unit": unit, "time": t, "name": raw_name}
                continue
            if result["lactate"] is None and any(k in raw_name for k in ("乳酸", "lactate", "lac")):
                result["lactate"] = {"value": num, "unit": unit, "time": t, "name": raw_name}
                continue
            if result["ph"] is None and raw_name in ("ph", "血气ph", "动脉血ph"):
                result["ph"] = {"value": num, "unit": unit, "time": t, "name": raw_name}
                continue
            if result["hco3"] is None and any(k in raw_name for k in ("hco3", "碳酸氢根", "actual hco3", "std hco3")):
                result["hco3"] = {"value": num, "unit": unit, "time": t, "name": raw_name}
                continue
            if result["be"] is None and any(k in raw_name for k in ("base excess", "be", "剩余碱")):
                result["be"] = {"value": num, "unit": unit, "time": t, "name": raw_name}
                continue

            if all(result.values()):
                break

        return result

    def _bun_is_high(self, bun: dict | None) -> bool:
        if not bun:
            return False
        v = _to_num(bun.get("value"))
        if v is None:
            return False
        unit = str(bun.get("unit") or "").lower().replace(" ", "")
        if "mg/dl" in unit:
            return v > 28
        if "mg/l" in unit:
            return v > 280
        if "umol/l" in unit or "μmol/l" in unit:
            return v > 10000
        # 默认按 mmol/L 解释（临床常见）
        return v > 10

    def _metabolic_acidosis(self, labs: dict) -> tuple[bool, dict]:
        ph = labs.get("ph")
        hco3 = labs.get("hco3")
        be = labs.get("be")
        lac = labs.get("lactate")

        flags = {
            "ph_low": ph is not None and _to_num(ph.get("value")) is not None and _to_num(ph.get("value")) < 7.35,
            "hco3_low": hco3 is not None and _to_num(hco3.get("value")) is not None and _to_num(hco3.get("value")) < 22,
            "be_low": be is not None and _to_num(be.get("value")) is not None and _to_num(be.get("value")) < -2,
            "lactate_high": lac is not None and _to_num(lac.get("value")) is not None and _to_num(lac.get("value")) >= 2.0,
        }
        return any(flags.values()), flags

    async def _deep_sedation_duration_hours(self, pid, hours: int = 48) -> float:
        series = await self._get_assessment_series(pid, "rass", hours=hours)
        if not series:
            return 0.0
        deep = [p for p in series if p.get("value") is not None and float(p["value"]) < -3]
        if len(deep) < 2:
            return 0.0
        first_t = deep[0].get("time")
        last_t = deep[-1].get("time")
        if not isinstance(first_t, datetime) or not isinstance(last_t, datetime):
            return 0.0
        # 仅当最近6小时仍处于深镇静，视为“持续状态”
        if (datetime.now() - last_t).total_seconds() > 6 * 3600:
            return 0.0
        return max(0.0, (last_t - first_t).total_seconds() / 3600.0)

    async def scan_delirium_risk(self) -> None:
        from .scanner_delirium_risk import DeliriumRiskScanner

        await DeliriumRiskScanner(self).scan()
