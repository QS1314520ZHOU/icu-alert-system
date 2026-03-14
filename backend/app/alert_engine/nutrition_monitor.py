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
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("nutrition_monitor", {})
        start_delay_h = float(cfg.get("start_delay_hours", 48))
        kcal_target_per_kg_day = float(cfg.get("calorie_target_kcal_per_kg_day", 25))
        kcal_coverage_threshold = float(cfg.get("calorie_coverage_threshold", 0.6))
        kcal_persist_h = float(cfg.get("calorie_under_target_persist_hours", 72))
        feeding_lookback_h = float(cfg.get("feeding_intolerance_lookback_hours", 72))
        refeeding_window_h = float(cfg.get("refeeding_monitor_hours", 72))
        malnut_bmi_thr = float(cfg.get("malnutrition_bmi_threshold", 18.5))
        malnut_alb_thr = float(cfg.get("malnutrition_albumin_g_l_threshold", 25))
        drop_ratio_thr = float(cfg.get("electrolyte_drop_ratio_threshold", 0.2))
        k_drop_abs_thr = float(cfg.get("electrolyte_drop_abs_threshold", {}).get("k", 0.5))
        p_drop_abs_thr = float(cfg.get("electrolyte_drop_abs_threshold", {}).get("phosphate", 0.3))
        mg_drop_abs_thr = float(cfg.get("electrolyte_drop_abs_threshold", {}).get("magnesium", 0.2))
        low_k_thr = float(cfg.get("electrolyte_low_threshold", {}).get("k", 3.5))
        low_p_thr = float(cfg.get("electrolyte_low_threshold", {}).get("phosphate", 0.8))
        low_mg_thr = float(cfg.get("electrolyte_low_threshold", {}).get("magnesium", 0.75))
        albumin_baseline_lookback_days = float(cfg.get("albumin_baseline_lookback_days", 7))

        albumin_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "albumin_keywords"),
            ["白蛋白", "albumin", "alb"],
        )
        phosphate_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "phosphate_keywords"),
            ["磷", "无机磷", "血磷", "phosphate", "phos", "phosphorus"],
        )
        magnesium_kw = self._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "magnesium_keywords"),
            ["镁", "血镁", "magnesium"],
        )

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "dept": 1,
                "hisDept": 1,
                "deptCode": 1,
                "age": 1,
                "hisAge": 1,
                "weight": 1,
                "bodyWeight": 1,
                "body_weight": 1,
                "weightKg": 1,
                "weight_kg": 1,
                "height": 1,
                "bodyHeight": 1,
                "heightCm": 1,
                "height_cm": 1,
                "bmi": 1,
                "BMI": 1,
                "icuAdmissionTime": 1,
                "admissionTime": 1,
                "inTime": 1,
                "admitTime": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()

            admission_t = self._admission_time(patient_doc)
            stay_h = 0.0
            if admission_t:
                stay_h = max(0.0, (now - admission_t).total_seconds() / 3600.0)

            since_drug = now - timedelta(days=14)
            if admission_t:
                since_drug = min(since_drug, admission_t - timedelta(hours=1))
            nutrition_events = await self._get_nutrition_drug_events(pid_str, since_drug, cfg)

            # (1) 入ICU >48h 且无EN/PN
            if stay_h >= start_delay_h:
                has_nutrition_after_adm = False
                if admission_t:
                    has_nutrition_after_adm = any(e["time"] >= admission_t for e in nutrition_events)
                else:
                    has_nutrition_after_adm = bool(nutrition_events)
                if not has_nutrition_after_adm:
                    rule_id = "NUTRITION_START_DELAY"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="营养支持启动延迟",
                            category="nutrition_monitor",
                            alert_type="nutrition_start_delay",
                            severity="warning",
                            parameter="icu_stay_hours",
                            condition={"operator": ">=", "threshold_hours": start_delay_h, "nutrition_order_present": False},
                            value=round(stay_h, 2),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=now,
                            extra={
                                "icu_stay_hours": round(stay_h, 2),
                                "start_delay_hours": start_delay_h,
                                "nutrition_order_found": False,
                            },
                        )
                        if alert:
                            triggered += 1

            first_nutrition_t = nutrition_events[0]["time"] if nutrition_events else None

            # (2) 热卡达标监测：不足60%持续72h
            weight_kg = self._get_patient_weight(patient_doc)
            if nutrition_events and weight_kg and weight_kg > 0:
                window_start = now - timedelta(hours=kcal_persist_h)
                usable_events = [e for e in nutrition_events if e["time"] >= window_start and e.get("kcal") is not None]
                total_kcal = round(sum(float(e["kcal"]) for e in usable_events), 2)
                target_kcal_day = round(float(weight_kg) * kcal_target_per_kg_day, 2)
                target_kcal_window = round(target_kcal_day * (kcal_persist_h / 24.0), 2)
                coverage = (total_kcal / target_kcal_window) if target_kcal_window > 0 else 0.0

                can_eval = False
                if first_nutrition_t:
                    can_eval = (now - first_nutrition_t).total_seconds() >= kcal_persist_h * 3600
                elif admission_t:
                    can_eval = (now - admission_t).total_seconds() >= kcal_persist_h * 3600

                if can_eval and coverage < kcal_coverage_threshold:
                    rule_id = "NUTRITION_CALORIE_NOT_REACHED"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="热卡供给达标不足",
                            category="nutrition_monitor",
                            alert_type="nutrition_calorie_not_reached",
                            severity="warning",
                            parameter="calorie_coverage_ratio",
                            condition={
                                "operator": "<",
                                "threshold": kcal_coverage_threshold,
                                "window_hours": kcal_persist_h,
                                "target_kcal_per_kg_day": kcal_target_per_kg_day,
                            },
                            value=round(coverage * 100, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=now,
                            extra={
                                "weight_kg": weight_kg,
                                "target_kcal_day": target_kcal_day,
                                "window_hours": kcal_persist_h,
                                "actual_kcal_window": total_kcal,
                                "target_kcal_window": target_kcal_window,
                                "coverage_ratio": round(coverage, 3),
                                "coverage_percent": round(coverage * 100, 1),
                                "enteral_kcal_window": round(sum(float(e["kcal"] or 0) for e in usable_events if e["type"] == "enteral"), 2),
                                "parenteral_kcal_window": round(sum(float(e["kcal"] or 0) for e in usable_events if e["type"] == "parenteral"), 2),
                            },
                        )
                        if alert:
                            triggered += 1

            # (3) 胃潴留/喂养不耐受 + 喂养中断
            feed_since = now - timedelta(hours=feeding_lookback_h)
            tolerance = await self._get_tolerance_signals(pid_str, feed_since, cfg)
            high_grv_events = tolerance["high_grv_events"]
            vomit_events = tolerance["vomit_events"]
            dist_events = tolerance["dist_events"]
            interrupt_events = tolerance["interrupt_events"]

            has_intolerance = bool(high_grv_events or vomit_events or dist_events)
            has_interrupt = bool(interrupt_events)
            if has_intolerance and has_interrupt:
                latest_intolerance_t = None
                for arr in (high_grv_events, vomit_events, dist_events):
                    if arr:
                        t = arr[-1]["time"]
                        latest_intolerance_t = t if (latest_intolerance_t is None or t > latest_intolerance_t) else latest_intolerance_t
                latest_interrupt_t = interrupt_events[-1]["time"]

                temporal_linked = True
                if latest_intolerance_t:
                    delta_h = abs((latest_interrupt_t - latest_intolerance_t).total_seconds()) / 3600.0
                    temporal_linked = delta_h <= 24

                if temporal_linked:
                    sev = "high" if high_grv_events else "warning"
                    rule_id = "NUTRITION_FEEDING_INTOLERANCE"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        latest_grv = high_grv_events[-1]["value_ml"] if high_grv_events else None
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="喂养不耐受风险",
                            category="nutrition_monitor",
                            alert_type="nutrition_feeding_intolerance",
                            severity=sev,
                            parameter="feeding_tolerance",
                            condition={
                                "grv_gt_ml": tolerance["grv_threshold_ml"],
                                "requires_feeding_interruption": True,
                            },
                            value=latest_grv,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=latest_interrupt_t,
                            extra={
                                "high_grv_count": len(high_grv_events),
                                "latest_grv_ml": latest_grv,
                                "vomiting_count": len(vomit_events),
                                "abdominal_distension_count": len(dist_events),
                                "feeding_interrupt_count": len(interrupt_events),
                                "suggestion": "建议评估喂养方式与耐受性，可考虑幽门后喂养。",
                            },
                        )
                        if alert:
                            triggered += 1

            # (4) 再喂养综合征风险（营养不良 + 营养启动后72h内电解质下降）
            if first_nutrition_t and his_pid:
                refeed_end = min(now, first_nutrition_t + timedelta(hours=refeeding_window_h))
                if refeed_end > first_nutrition_t:
                    bmi = self._patient_bmi(patient_doc)
                    malnutrition_by_bmi = bmi is not None and bmi < malnut_bmi_thr

                    alb_end = admission_t + timedelta(hours=24) if admission_t else first_nutrition_t
                    alb_since = alb_end - timedelta(days=albumin_baseline_lookback_days)
                    alb_series = await self._get_lab_series_by_keywords(
                        his_pid,
                        alb_since,
                        alb_end,
                        albumin_kw,
                        converter=self._convert_albumin_to_g_l,
                        limit=1200,
                    )
                    alb_latest = alb_series[-1]["value"] if alb_series else None
                    malnutrition_by_alb = alb_latest is not None and alb_latest < malnut_alb_thr
                    malnutrition = malnutrition_by_bmi or malnutrition_by_alb

                    if malnutrition:
                        k_series = await self._get_lab_series(his_pid, "k", first_nutrition_t, refeed_end, limit=600)
                        p_series = await self._get_lab_series_by_keywords(
                            his_pid,
                            first_nutrition_t,
                            refeed_end,
                            phosphate_kw,
                            converter=self._convert_phosphate_to_mmol_l,
                            limit=1200,
                        )
                        mg_series = await self._get_lab_series_by_keywords(
                            his_pid,
                            first_nutrition_t,
                            refeed_end,
                            magnesium_kw,
                            converter=self._convert_magnesium_to_mmol_l,
                            limit=1200,
                        )

                        k_trend = self._drop_trend(k_series, drop_ratio_thr, k_drop_abs_thr, low_k_thr)
                        p_trend = self._drop_trend(p_series, drop_ratio_thr, p_drop_abs_thr, low_p_thr)
                        mg_trend = self._drop_trend(mg_series, drop_ratio_thr, mg_drop_abs_thr, low_mg_thr)

                        triggered_items = []
                        if k_trend and k_trend["triggered"]:
                            triggered_items.append("K")
                        if p_trend and p_trend["triggered"]:
                            triggered_items.append("P")
                        if mg_trend and mg_trend["triggered"]:
                            triggered_items.append("Mg")

                        if triggered_items:
                            sev = "high" if len(triggered_items) >= 2 else "warning"
                            if len(triggered_items) == 3:
                                sev = "critical"
                            rule_id = "NUTRITION_REFEEDING_RISK"
                            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                                max_drop_ratio = max(
                                    x["drop_ratio"] for x in (k_trend, p_trend, mg_trend) if x and x.get("triggered")
                                )
                                alert = await self._create_alert(
                                    rule_id=rule_id,
                                    name="再喂养综合征风险",
                                    category="nutrition_monitor",
                                    alert_type="nutrition_refeeding_risk",
                                    severity=sev,
                                    parameter="electrolyte_drop",
                                    condition={
                                        "malnutrition_required": True,
                                        "window_hours": refeeding_window_h,
                                        "drop_ratio_threshold": drop_ratio_thr,
                                    },
                                    value=round(max_drop_ratio * 100, 1),
                                    patient_id=pid_str,
                                    patient_doc=patient_doc,
                                    device_id=None,
                                    source_time=refeed_end,
                                    extra={
                                        "triggered_electrolytes": triggered_items,
                                        "nutrition_start_time": first_nutrition_t,
                                        "monitor_window_hours": refeeding_window_h,
                                        "malnutrition": {
                                            "bmi": bmi,
                                            "bmi_threshold": malnut_bmi_thr,
                                            "albumin_g_l": alb_latest,
                                            "albumin_threshold_g_l": malnut_alb_thr,
                                            "by_bmi": malnutrition_by_bmi,
                                            "by_albumin": malnutrition_by_alb,
                                        },
                                        "k_trend": k_trend,
                                        "phosphate_trend": p_trend,
                                        "magnesium_trend": mg_trend,
                                    },
                                )
                                if alert:
                                    triggered += 1

        if triggered > 0:
            self._log_info("营养监测", triggered)
