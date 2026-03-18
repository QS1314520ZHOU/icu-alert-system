"""生命体征阈值预警 + 心律/QTc扩展规则"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from app.utils.clinical import _eval_condition, _extract_param
from app.utils.parse import _parse_dt


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


class VitalSignsMixin:
    async def _baseline_guard(
        self,
        *,
        pid,
        patient_doc: dict | None,
        param: str,
        value: float,
        direction: str | None,
    ) -> tuple[bool, bool, dict | None]:
        cfg = self._cfg("alert_engine", "patient_baseline", default={}) or {}
        if not bool(cfg.get("enabled", True)):
            return False, False, None
        baseline = await self._get_patient_baseline(
            pid,
            param,
            hours=int(cfg.get("hours", 12)),
            patient_doc=patient_doc,
            prefer_device_types=["monitor"],
        )
        if not baseline or baseline.get("count", 0) < int(cfg.get("min_points", 3)):
            return False, False, baseline
        mean = float(baseline.get("mean") or 0.0)
        std = float(baseline.get("std") or 0.0)
        abs_floor = float(cfg.get("absolute_floor", 2.0))
        rel_floor = abs(mean) * float(cfg.get("relative_tolerance", 0.08))
        tol = max(std * float(cfg.get("zscore_tolerance", 2.0)), abs_floor, rel_floor)
        baseline["tolerance"] = round(tol, 4)
        delta = float(value) - mean
        baseline["delta"] = round(delta, 4)
        baseline["within_baseline"] = False
        baseline["deviation_triggered"] = False
        if direction == "low":
            within = float(value) >= mean - tol
            deviated = float(value) < mean - tol
        elif direction == "high":
            within = float(value) <= mean + tol
            deviated = float(value) > mean + tol
        else:
            within = abs(delta) <= tol
            deviated = abs(delta) > tol
        baseline["within_baseline"] = within
        baseline["deviation_triggered"] = deviated
        return within, deviated, baseline

    async def _confirm_vital_rule(
        self,
        *,
        pid,
        patient_doc: dict | None,
        param: str,
        value: float,
        condition: dict,
        cap: dict,
        now: datetime,
    ) -> tuple[bool, dict[str, Any]]:
        op = str((condition or {}).get("operator") or "")
        threshold = _to_float((condition or {}).get("threshold"))
        detail: dict[str, Any] = {}

        map_codes = set(self._cfg("vital_signs", "map_priority", default=["param_ibp_m", "param_nibp_m"]) or [])
        sbp_codes = set(self._cfg("vital_signs", "sbp_priority", default=["param_ibp_s", "param_nibp_s"]) or [])
        rr = _extract_param(cap, self._cfg("vital_signs", "resp_rate", "code", default="param_resp"))
        hr = _extract_param(cap, self._cfg("vital_signs", "heart_rate", "code", default="param_HR"))
        temp = _extract_param(cap, self._cfg("vital_signs", "temperature", "code", default="param_T"))

        if param in map_codes and op in {"<", "<="} and threshold is not None:
            code = param
            series = await self._get_param_series_by_pid(pid, code, now - timedelta(minutes=20), prefer_device_types=["monitor"], limit=30)
            series = self._filter_series_quality(code, series)
            low_points = [s for s in series[-3:] if _to_float(s.get("value")) is not None and float(s["value"]) < threshold]
            detail["confirm_low_points"] = len(low_points)
            if len(low_points) >= 2:
                return True, detail
            if value < threshold and hr is not None and hr > 100:
                detail["tachycardia_support"] = round(float(hr), 2)
                return True, detail
            return False, detail

        if param in sbp_codes and op in {"<", "<="} and threshold is not None:
            code = param
            series = await self._get_param_series_by_pid(pid, code, now - timedelta(minutes=20), prefer_device_types=["monitor"], limit=30)
            series = self._filter_series_quality(code, series)
            low_points = [s for s in series[-3:] if _to_float(s.get("value")) is not None and float(s["value"]) < threshold]
            detail["confirm_low_points"] = len(low_points)
            if len(low_points) >= 2:
                return True, detail
            if value < threshold and hr is not None and hr > 100:
                detail["tachycardia_support"] = round(float(hr), 2)
                return True, detail
            return False, detail

        if param == self._cfg("vital_signs", "spo2", "code", default="param_spo2") and op in {"<", "<="} and threshold is not None:
            series = await self._get_param_series_by_pid(pid, param, now - timedelta(minutes=15), prefer_device_types=["monitor"], limit=30)
            series = self._filter_series_quality(param, series)
            low_points = [s for s in series[-3:] if _to_float(s.get("value")) is not None and float(s["value"]) < threshold]
            detail["confirm_low_points"] = len(low_points)
            if len(low_points) >= 2:
                return True, detail
            if value < threshold and rr is not None and rr > 25:
                detail["rr_support"] = round(float(rr), 2)
                return True, detail
            return False, detail

        if param == self._cfg("vital_signs", "heart_rate", "code", default="param_HR") and op in {">", ">="}:
            if value >= 130:
                detail["high_hr_direct"] = round(float(value), 2)
                return True, detail
            if value > 110 and temp is not None and 36 <= temp <= 38:
                detail["normothermia_support"] = round(float(temp), 2)
                return True, detail
            return False, detail

        return True, detail

    def _text_has_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

    def _rhythm_text(self, doc: dict) -> str:
        return " ".join(
            str(doc.get(k) or "")
            for k in ("strVal", "value", "name", "paramName", "itemName", "remark", "desc", "text")
        ).lower()

    def _rhythm_point(
        self,
        doc: dict,
        af_keywords: list[str],
        afl_keywords: list[str],
        irregular_keywords: list[str],
        arrhythmia_flag_codes: list[str],
    ) -> dict | None:
        t = _parse_dt(doc.get("time"))
        if not t:
            return None
        code = str(doc.get("code") or "").strip().lower()
        text = self._rhythm_text(doc)

        is_af = self._text_has_any(text, af_keywords)
        is_afl = self._text_has_any(text, afl_keywords)
        irregular = is_af or is_afl or self._text_has_any(text, irregular_keywords)

        if (not irregular) and code and code in {str(c).lower() for c in arrhythmia_flag_codes}:
            flag_val = _to_float(doc.get("fVal"))
            if flag_val is None:
                flag_val = _to_float(doc.get("intVal"))
            if flag_val is None:
                flag_val = _to_float(doc.get("value"))
            if flag_val is None:
                flag_val = _to_float(doc.get("strVal"))
            irregular = flag_val is not None and flag_val > 0

        return {
            "time": t,
            "code": code,
            "text": text,
            "irregular": bool(irregular),
            "is_af": bool(is_af),
            "is_afl": bool(is_afl),
        }

    async def _get_rhythm_points(
        self,
        device_id: str,
        since: datetime,
        rhythm_codes: list[str],
        af_keywords: list[str],
        afl_keywords: list[str],
        irregular_keywords: list[str],
        arrhythmia_flag_codes: list[str],
    ) -> list[dict]:
        query: dict = {"deviceID": device_id, "time": {"$gte": since}}
        use_codes = [str(c).strip() for c in rhythm_codes if str(c).strip()]
        if use_codes:
            query["code"] = {"$in": use_codes}

        cursor = self.db.col("deviceCap").find(
            query,
            {
                "time": 1,
                "code": 1,
                "strVal": 1,
                "value": 1,
                "fVal": 1,
                "intVal": 1,
                "name": 1,
                "paramName": 1,
                "itemName": 1,
                "remark": 1,
                "desc": 1,
                "text": 1,
            },
        ).sort("time", 1).limit(4000)

        points: list[dict] = []
        async for doc in cursor:
            pt = self._rhythm_point(
                doc,
                af_keywords=af_keywords,
                afl_keywords=afl_keywords,
                irregular_keywords=irregular_keywords,
                arrhythmia_flag_codes=arrhythmia_flag_codes,
            )
            if pt:
                points.append(pt)
        return points

    def _find_irregular_segments(self, points: list[dict], max_gap_seconds: int) -> list[dict]:
        irregular_points = [p for p in points if p.get("irregular")]
        if not irregular_points:
            return []

        segments: list[dict] = []
        seg_start = irregular_points[0]["time"]
        seg_end = irregular_points[0]["time"]
        has_af = irregular_points[0].get("is_af", False)
        has_afl = irregular_points[0].get("is_afl", False)
        for p in irregular_points[1:]:
            t = p["time"]
            gap = (t - seg_end).total_seconds()
            if gap <= max_gap_seconds:
                seg_end = t
                has_af = has_af or p.get("is_af", False)
                has_afl = has_afl or p.get("is_afl", False)
                continue
            segments.append(
                {
                    "start": seg_start,
                    "end": seg_end,
                    "duration_seconds": max(0.0, (seg_end - seg_start).total_seconds()),
                    "has_af": has_af,
                    "has_afl": has_afl,
                }
            )
            seg_start = t
            seg_end = t
            has_af = p.get("is_af", False)
            has_afl = p.get("is_afl", False)

        segments.append(
            {
                "start": seg_start,
                "end": seg_end,
                "duration_seconds": max(0.0, (seg_end - seg_start).total_seconds()),
                "has_af": has_af,
                "has_afl": has_afl,
            }
        )
        return segments

    async def _has_prior_af_afl(
        self,
        device_id: str,
        seg_start: datetime,
        lookback_hours: float,
        rhythm_codes: list[str],
        af_keywords: list[str],
        afl_keywords: list[str],
        irregular_keywords: list[str],
        arrhythmia_flag_codes: list[str],
    ) -> bool:
        since = seg_start - timedelta(hours=max(1.0, lookback_hours))
        points = await self._get_rhythm_points(
            device_id=device_id,
            since=since,
            rhythm_codes=rhythm_codes,
            af_keywords=af_keywords,
            afl_keywords=afl_keywords,
            irregular_keywords=irregular_keywords,
            arrhythmia_flag_codes=arrhythmia_flag_codes,
        )
        for p in points:
            t = p.get("time")
            if not isinstance(t, datetime):
                continue
            if t >= seg_start:
                continue
            if p.get("is_af") or p.get("is_afl"):
                return True
        return False

    async def _latest_qtc(self, pid, qtc_codes: list[str], lookback_hours: float) -> tuple[float | None, datetime | None, str | None]:
        since = datetime.now() - timedelta(hours=max(1.0, lookback_hours))
        latest_val = None
        latest_t = None
        latest_code = None
        for code in qtc_codes:
            c = str(code).strip()
            if not c:
                continue
            series = await self._get_param_series_by_pid(pid, c, since, prefer_device_types=["monitor"], limit=2000)
            if not series:
                continue
            t = series[-1].get("time")
            v = _to_float(series[-1].get("value"))
            if v is None or not isinstance(t, datetime):
                continue
            if (latest_t is None) or (t > latest_t):
                latest_t = t
                latest_val = v
                latest_code = c
        return latest_val, latest_t, latest_code

    async def _sbp_drop(self, pid, now: datetime, window_minutes: int) -> dict | None:
        since = now - timedelta(minutes=max(5, int(window_minutes)))
        sbp_codes = self._cfg("vital_signs", "sbp_priority", default=["param_ibp_s", "param_nibp_s"]) or ["param_ibp_s", "param_nibp_s"]

        best_series: list[dict] = []
        best_code = None
        for code in sbp_codes:
            series = await self._get_param_series_by_pid(pid, str(code), since, prefer_device_types=["monitor"], limit=2000)
            if len(series) > len(best_series):
                best_series = series
                best_code = str(code)
        if len(best_series) < 2:
            return None

        latest = _to_float(best_series[-1].get("value"))
        if latest is None:
            return None
        previous_vals = [_to_float(x.get("value")) for x in best_series[:-1]]
        previous_vals = [x for x in previous_vals if x is not None]
        if not previous_vals:
            return None
        baseline = max(previous_vals)
        drop = baseline - latest
        return {
            "latest_sbp": round(latest, 2),
            "baseline_sbp": round(baseline, 2),
            "drop_sbp": round(drop, 2),
            "code": best_code,
            "latest_time": best_series[-1].get("time"),
        }

    async def scan_vital_signs(self) -> None:
        from .vital_signs_scanner import VitalSignsScanner

        await VitalSignsScanner(self).scan()
