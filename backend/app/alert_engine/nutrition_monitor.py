"""营养监测预警（启动时机/热卡达标/喂养耐受/再喂养风险）"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable


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


class NutritionMonitorMixin:
    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

    def _patient_age_years(self, patient_doc: dict) -> float | None:
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
                d = _to_float(s)
                return (d / 365.0) if d is not None else None
            if s.endswith("月"):
                m = _to_float(s)
                return (m / 12.0) if m is not None else None
            n = _to_float(s)
            if n is not None:
                return n
        return None

    def _patient_bmi(self, patient_doc: dict) -> float | None:
        for key in ("bmi", "BMI", "bodyMassIndex"):
            n = _to_float(patient_doc.get(key))
            if n is not None and 10 <= n <= 80:
                return n
        weight = self._get_patient_weight(patient_doc)
        if weight is None:
            return None
        height = None
        for key in ("height", "bodyHeight", "heightCm", "height_cm"):
            h = _to_float(patient_doc.get(key))
            if h is not None:
                height = h
                break
        if height is None:
            return None
        h_m = height / 100.0 if height > 3 else height
        if h_m <= 0:
            return None
        bmi = weight / (h_m * h_m)
        return round(bmi, 2) if 10 <= bmi <= 80 else None

    def _admission_time(self, patient_doc: dict) -> datetime | None:
        for key in ("icuAdmissionTime", "admissionTime", "inTime", "admitTime", "createTime"):
            t = _parse_dt(patient_doc.get(key))
            if t:
                return t
        return None

    def _drug_event_time(self, doc: dict) -> datetime | None:
        return (
            _parse_dt(doc.get("executeTime"))
            or _parse_dt(doc.get("startTime"))
            or _parse_dt(doc.get("orderTime"))
        )

    def _event_text(self, doc: dict) -> str:
        return " ".join(
            str(doc.get(k) or "")
            for k in (
                "drugName",
                "orderName",
                "drugSpec",
                "route",
                "routeName",
                "orderType",
                "exeMethod",
                "remark",
            )
        ).lower()

    def _parse_kcal_per_ml(self, doc: dict, text: str) -> float | None:
        for key in ("kcalPerMl", "calorieDensity", "energyDensity", "formulaKcalPerMl"):
            n = _to_float(doc.get(key))
            if n is not None and 0 < n <= 5:
                return n

        m = re.search(r"(\d+(?:\.\d+)?)\s*kcal\s*/\s*(ml|mL|ML|l|L)", text, flags=re.I)
        if m:
            n = _to_float(m.group(1))
            unit = str(m.group(2)).lower()
            if n is not None and n > 0:
                if unit == "l":
                    return n / 1000.0
                return n
        return None

    def _parse_volume_ml(self, doc: dict, text: str) -> float | None:
        unit_candidates = [
            doc.get("volumeUnit"),
            doc.get("doseUnit"),
            doc.get("unit"),
        ]

        for key in ("volume", "totalVolume", "infusionVolume", "inputVolume"):
            n = _to_float(doc.get(key))
            if n is None or n <= 0:
                continue
            unit = str(unit_candidates[0] or "").lower().replace(" ", "")
            if any(k in unit for k in ("ml", "毫升", "cc")):
                return n
            if ("l" in unit or "升" in unit) and "ml" not in unit:
                return n * 1000.0
            if "dl" in unit:
                return n * 100.0
            return n

        m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|l|L|升|毫升|cc)", text)
        if not m:
            return None
        n = _to_float(m.group(1))
        u = str(m.group(2)).lower()
        if n is None or n <= 0:
            return None
        if u in ("l", "升"):
            return n * 1000.0
        return n

    def _parse_rate_ml_h(self, doc: dict, text: str) -> float | None:
        for key in ("rate", "pumpRate", "infusionRate", "speed", "flowRate", "rateMlPerHour"):
            n = _to_float(doc.get(key))
            if n is not None and n > 0:
                return n
        m = re.search(r"(\d+(?:\.\d+)?)\s*(ml/h|ml/hr|mL/h|ml每小时|ml每h)", text, flags=re.I)
        if not m:
            return None
        n = _to_float(m.group(1))
        return n if (n is not None and n > 0) else None

    def _parse_duration_h(self, doc: dict, default_hours: float) -> float:
        for key in ("durationHours", "duration", "infusionHours", "planHours", "orderHours"):
            n = _to_float(doc.get(key))
            if n is not None and 0 < n <= 72:
                return n
        start_t = _parse_dt(doc.get("startTime"))
        end_t = _parse_dt(doc.get("endTime"))
        if start_t and end_t and end_t > start_t:
            h = (end_t - start_t).total_seconds() / 3600.0
            if 0 < h <= 72:
                return h
        return max(0.5, float(default_hours))

    def _estimate_event_kcal(self, doc: dict, nutrition_type: str, cfg: dict) -> float | None:
        text = self._event_text(doc)

        for key in (
            "kcal",
            "calorie",
            "calories",
            "totalKcal",
            "totalCalories",
            "energyKcal",
            "heat",
            "totalHeat",
        ):
            n = _to_float(doc.get(key))
            if n is not None and n > 0:
                return round(n, 2)

        dose = _to_float(doc.get("dose"))
        dose_unit = str(doc.get("doseUnit") or doc.get("unit") or "").lower()
        if dose is not None and dose > 0 and "kcal" in dose_unit:
            return round(dose, 2)

        m_kcal = re.search(r"(\d+(?:\.\d+)?)\s*(kcal|千卡)", text, flags=re.I)
        if m_kcal:
            n = _to_float(m_kcal.group(1))
            if n is not None and n > 0:
                return round(n, 2)

        kcal_per_ml = self._parse_kcal_per_ml(doc, text)
        volume_ml = self._parse_volume_ml(doc, text)
        rate_ml_h = self._parse_rate_ml_h(doc, text)
        default_rate_hours = float(cfg.get("default_rate_duration_hours", 1.0))
        duration_h = self._parse_duration_h(doc, default_rate_hours)

        if volume_ml is None and rate_ml_h is not None:
            volume_ml = rate_ml_h * duration_h

        if kcal_per_ml is None:
            if nutrition_type == "enteral":
                kcal_per_ml = float(cfg.get("default_enteral_kcal_per_ml", 1.0))
            elif nutrition_type == "parenteral":
                kcal_per_ml = float(cfg.get("default_parenteral_kcal_per_ml", 0.8))

        if volume_ml is None or kcal_per_ml is None:
            return None
        kcal = volume_ml * kcal_per_ml
        if kcal <= 0:
            return None
        return round(kcal, 2)

    async def _get_nutrition_drug_events(self, pid_str: str, since: datetime, cfg: dict) -> list[dict]:
        enteral_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "enteral_keywords"),
            ["肠内营养", "鼻饲", "胃管", "enteral", "tube feeding", "营养泵"],
        )
        parenteral_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "parenteral_keywords"),
            ["肠外营养", "tpn", "全肠外", "静脉营养", "脂肪乳", "复方氨基酸", "葡萄糖注射液"],
        )

        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1,
                "startTime": 1,
                "endTime": 1,
                "orderTime": 1,
                "drugName": 1,
                "orderName": 1,
                "drugSpec": 1,
                "route": 1,
                "routeName": 1,
                "orderType": 1,
                "exeMethod": 1,
                "remark": 1,
                "dose": 1,
                "doseUnit": 1,
                "unit": 1,
                "volume": 1,
                "totalVolume": 1,
                "inputVolume": 1,
                "infusionVolume": 1,
                "volumeUnit": 1,
                "rate": 1,
                "pumpRate": 1,
                "infusionRate": 1,
                "speed": 1,
                "flowRate": 1,
                "rateMlPerHour": 1,
                "durationHours": 1,
                "duration": 1,
                "infusionHours": 1,
                "planHours": 1,
                "orderHours": 1,
                "kcal": 1,
                "calorie": 1,
                "calories": 1,
                "totalKcal": 1,
                "totalCalories": 1,
                "energyKcal": 1,
                "heat": 1,
                "totalHeat": 1,
                "kcalPerMl": 1,
                "calorieDensity": 1,
                "energyDensity": 1,
                "formulaKcalPerMl": 1,
            },
        ).sort("executeTime", -1).limit(6000)

        events: list[dict] = []
        async for doc in cursor:
            t = self._drug_event_time(doc)
            if not t or t < since:
                continue
            text = self._event_text(doc)
            ntype = None
            if self._contains_any(text, enteral_kw):
                ntype = "enteral"
            elif self._contains_any(text, parenteral_kw):
                ntype = "parenteral"
            if not ntype:
                continue

            kcal = self._estimate_event_kcal(doc, ntype, cfg)
            events.append(
                {
                    "time": t,
                    "type": ntype,
                    "kcal": kcal,
                    "raw": doc,
                }
            )
        events.sort(key=lambda x: x["time"])
        return events

    async def _get_tolerance_signals(self, pid_str: str, since: datetime, cfg: dict) -> dict:
        grv_threshold = float(cfg.get("grv_threshold_ml", 500))
        grv_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "grv_keywords"),
            ["胃残余", "胃潴留", "grv", "gastric residual"],
        )
        vomit_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "vomit_keywords"),
            ["呕吐", "返流", "反流", "vomit", "emesis", "regurgitation"],
        )
        dist_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "abdominal_distension_keywords"),
            ["腹胀", "腹部膨隆", "abdominal distension", "bloating"],
        )
        interrupt_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "feeding_interrupt_keywords"),
            ["中断喂养", "暂停喂养", "停止喂养", "禁食", "npo", "hold feeding", "feeding interrupted"],
        )

        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {
                "time": 1,
                "code": 1,
                "name": 1,
                "paramName": 1,
                "itemName": 1,
                "remark": 1,
                "strVal": 1,
                "fVal": 1,
                "intVal": 1,
                "value": 1,
                "unit": 1,
            },
        ).sort("time", -1).limit(4000)

        high_grv_events: list[dict] = []
        vomit_events: list[dict] = []
        dist_events: list[dict] = []
        interrupt_events: list[dict] = []

        async for doc in cursor:
            t = _parse_dt(doc.get("time"))
            if not t:
                continue
            text = " ".join(
                str(doc.get(k) or "")
                for k in ("code", "name", "paramName", "itemName", "remark", "strVal")
            ).lower()
            if not text:
                continue

            if self._contains_any(text, interrupt_kw):
                interrupt_events.append({"time": t, "text": text})
            if self._contains_any(text, vomit_kw):
                vomit_events.append({"time": t, "text": text})
            if self._contains_any(text, dist_kw):
                dist_events.append({"time": t, "text": text})

            if self._contains_any(text, grv_kw):
                v = _to_float(doc.get("fVal"))
                if v is None:
                    v = _to_float(doc.get("intVal"))
                if v is None:
                    v = _to_float(doc.get("value"))
                if v is None:
                    v = _to_float(doc.get("strVal"))
                if v is None:
                    continue
                unit = str(doc.get("unit") or "").lower().replace(" ", "")
                if ("l" in unit or "升" in unit) and "ml" not in unit:
                    v *= 1000.0
                if v > grv_threshold:
                    high_grv_events.append({"time": t, "value_ml": round(v, 1), "text": text})

        return {
            "high_grv_events": sorted(high_grv_events, key=lambda x: x["time"]),
            "vomit_events": sorted(vomit_events, key=lambda x: x["time"]),
            "dist_events": sorted(dist_events, key=lambda x: x["time"]),
            "interrupt_events": sorted(interrupt_events, key=lambda x: x["time"]),
            "grv_threshold_ml": grv_threshold,
        }

    async def _get_lab_series_by_keywords(
        self,
        his_pid: str,
        since: datetime,
        end: datetime,
        keywords: list[str],
        converter: Callable[[float, str], float | None] | None = None,
        limit: int = 4000,
    ) -> list[dict]:
        if not his_pid:
            return []
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(limit)
        out: list[dict] = []
        async for doc in cursor:
            t = (
                _parse_dt(doc.get("authTime"))
                or _parse_dt(doc.get("collectTime"))
                or _parse_dt(doc.get("requestTime"))
                or _parse_dt(doc.get("reportTime"))
                or _parse_dt(doc.get("resultTime"))
                or _parse_dt(doc.get("time"))
            )
            if not t or t < since or t > end:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").lower()
            if not self._contains_any(name, keywords):
                continue
            raw = doc.get("result") or doc.get("resultValue") or doc.get("value")
            v = _to_float(raw)
            if v is None:
                continue
            unit = str(doc.get("unit") or doc.get("resultUnit") or "")
            if converter:
                converted = converter(v, unit)
                if converted is None:
                    continue
                v = converted
            out.append({"time": t, "value": float(v), "unit": unit, "name": name})
        out.sort(key=lambda x: x["time"])
        return out

    def _convert_albumin_to_g_l(self, value: float, unit: str) -> float | None:
        u = str(unit or "").lower().replace(" ", "")
        if "g/dl" in u:
            return value * 10.0
        if "mg/dl" in u:
            return value * 0.01
        if "g/l" in u or "gl" in u or not u:
            return value
        return value

    def _convert_phosphate_to_mmol_l(self, value: float, unit: str) -> float | None:
        u = str(unit or "").lower().replace(" ", "")
        if "mg/dl" in u:
            return value * 0.3229
        if "mmol/l" in u or "mmol" in u or not u:
            return value
        if "mg/l" in u:
            return value * 0.003229
        return value

    def _convert_magnesium_to_mmol_l(self, value: float, unit: str) -> float | None:
        u = str(unit or "").lower().replace(" ", "")
        if "mg/dl" in u:
            return value * 0.4114
        if "mmol/l" in u or "mmol" in u or not u:
            return value
        if "mg/l" in u:
            return value * 0.04114
        return value

    def _drop_trend(
        self,
        series: list[dict],
        drop_ratio_threshold: float,
        drop_abs_threshold: float,
        low_threshold: float | None,
    ) -> dict | None:
        if len(series) < 2:
            return None
        vals = [float(x["value"]) for x in series if x.get("value") is not None]
        if len(vals) < 2:
            return None
        baseline = max(vals)
        latest = vals[-1]
        if baseline <= 0:
            return None
        drop_abs = max(0.0, baseline - latest)
        drop_ratio = drop_abs / baseline
        low_flag = (low_threshold is not None) and (latest < low_threshold)
        triggered = (drop_ratio >= drop_ratio_threshold and drop_abs >= drop_abs_threshold) or (low_flag and drop_abs > 0)
        return {
            "baseline": round(baseline, 3),
            "latest": round(latest, 3),
            "drop_abs": round(drop_abs, 3),
            "drop_ratio": round(drop_ratio, 3),
            "low_threshold": low_threshold,
            "triggered": bool(triggered),
            "latest_time": series[-1].get("time"),
        }

    async def scan_nutrition_monitor(self) -> None:
        from .scanner_nutrition_monitor import NutritionMonitorScanner

        await NutritionMonitorScanner(self).scan()
