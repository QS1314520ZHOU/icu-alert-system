"""护理评估提醒"""
from __future__ import annotations

import re
from datetime import datetime, timedelta


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_float(value) -> float | None:
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


class NurseReminderMixin:
    def _parse_bmi(self, patient_doc: dict) -> float | None:
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

    async def _get_last_turn_time(self, pid_str: str, now: datetime, lookback_hours: float, keywords: list[str]) -> datetime | None:
        since = now - timedelta(hours=max(1.0, float(lookback_hours)))
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "code": 1, "name": 1, "paramName": 1, "itemName": 1, "remark": 1, "strVal": 1},
        ).sort("time", -1).limit(3000)

        lowered = [str(k).strip().lower() for k in keywords if str(k).strip()]
        async for doc in cursor:
            t = _parse_dt(doc.get("time"))
            if not t:
                continue
            text = " ".join(
                str(doc.get(k) or "")
                for k in ("code", "name", "paramName", "itemName", "remark", "strVal")
            ).lower()
            if any(k in text for k in lowered):
                return t

        # 兜底: 使用最近一次翻身提醒中记录的 last_score_time
        hist = await self.db.col("nurse_reminders").find_one(
            {"patient_id": pid_str, "score_type": "turning", "last_score_time": {"$ne": None}},
            sort=[("last_score_time", -1)],
        )
        if hist:
            return _parse_dt(hist.get("last_score_time"))
        return None

    def _text_contains_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

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

    def _dose_to_ug_kg_min(self, value: float | None, unit: str, weight_kg: float | None) -> float | None:
        if value is None or value <= 0:
            return None
        u = str(unit or "").lower().replace(" ", "")
        u = u.replace("μ", "u")
        if "mcg/kg/min" in u or "ug/kg/min" in u:
            return value
        if "mg/kg/min" in u:
            return value * 1000.0
        if "mg/kg/h" in u or "mg/kg/hr" in u:
            return value * 1000.0 / 60.0
        if weight_kg is None or weight_kg <= 0:
            return None
        if "mg/h" in u or "mg/hr" in u:
            return value * 1000.0 / 60.0 / weight_kg
        if "mg/min" in u:
            return value * 1000.0 / weight_kg
        if "ug/h" in u or "mcg/h" in u:
            return value / 60.0 / weight_kg
        if "ug/min" in u or "mcg/min" in u:
            return value / weight_kg
        return None

    def _extract_norepi_dose_ug_kg_min(self, doc: dict, weight_kg: float | None) -> float | None:
        value_unit_pairs = [
            (_to_float(doc.get("dose")), str(doc.get("doseUnit") or doc.get("unit") or "")),
            (_to_float(doc.get("rate")), str(doc.get("rateUnit") or doc.get("unit") or "")),
            (_to_float(doc.get("speed")), str(doc.get("speedUnit") or doc.get("unit") or "")),
            (_to_float(doc.get("flowRate")), str(doc.get("flowRateUnit") or doc.get("unit") or "")),
        ]
        for val, unit in value_unit_pairs:
            dose = self._dose_to_ug_kg_min(val, unit, weight_kg)
            if dose is not None:
                return round(dose, 4)

        text = " ".join(str(doc.get(k) or "") for k in ("dose", "drugSpec", "orderName", "drugName", "remark"))
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(mcg/kg/min|ug/kg/min|mg/kg/min|mg/kg/h|mg/kg/hr|mg/h|mg/hr|mg/min|ug/h|mcg/h|ug/min|mcg/min)",
            text,
            flags=re.I,
        )
        if not m:
            return None
        val = _to_float(m.group(1))
        unit = m.group(2)
        dose = self._dose_to_ug_kg_min(val, unit, weight_kg)
        return round(dose, 4) if dose is not None else None

    async def _get_norepi_dose_series(
        self,
        pid_str: str,
        now: datetime,
        lookback_hours: float,
        keywords: list[str],
        weight_kg: float | None,
    ) -> list[dict]:
        since = now - timedelta(hours=max(1.0, lookback_hours))
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1,
                "startTime": 1,
                "orderTime": 1,
                "drugName": 1,
                "orderName": 1,
                "dose": 1,
                "doseUnit": 1,
                "unit": 1,
                "rate": 1,
                "rateUnit": 1,
                "speed": 1,
                "speedUnit": 1,
                "flowRate": 1,
                "flowRateUnit": 1,
                "drugSpec": 1,
                "remark": 1,
            },
        ).sort("executeTime", 1).limit(3000)

        points: list[dict] = []
        async for doc in cursor:
            t = _parse_dt(doc.get("executeTime")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            if not t or t < since:
                continue
            text = " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName", "drugSpec", "remark")).lower()
            if not self._text_contains_any(text, keywords):
                continue
            dose = self._extract_norepi_dose_ug_kg_min(doc, weight_kg)
            if dose is None:
                continue
            points.append({"time": t, "dose_ug_kg_min": float(dose)})
        points.sort(key=lambda x: x["time"])
        return points

    def _is_series_tapering(self, points: list[dict], min_drop_ratio: float = 0.1) -> bool:
        if len(points) < 2:
            return False
        latest = float(points[-1]["dose_ug_kg_min"])
        prev = float(points[-2]["dose_ug_kg_min"])
        if prev <= 0:
            return False
        if latest >= prev:
            return False
        drop_ratio = (prev - latest) / prev
        return drop_ratio >= min_drop_ratio

    async def _get_last_activity_time(self, pid_str: str, now: datetime, lookback_hours: float, keywords: list[str]) -> datetime | None:
        since = now - timedelta(hours=max(1.0, lookback_hours))
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "code": 1, "name": 1, "paramName": 1, "itemName": 1, "remark": 1, "strVal": 1},
        ).sort("time", -1).limit(3000)

        lowered = [str(k).strip().lower() for k in keywords if str(k).strip()]
        async for doc in cursor:
            t = _parse_dt(doc.get("time"))
            if not t:
                continue
            text = " ".join(
                str(doc.get(k) or "")
                for k in ("code", "name", "paramName", "itemName", "remark", "strVal")
            ).lower()
            if any(k in text for k in lowered):
                return t
        return None

    async def _get_latest_opioid_adjustment_time(
        self,
        pid_str: str,
        now: datetime,
        lookback_hours: float,
        dose_change_ratio_threshold: float,
        opioid_keywords: list[str],
    ) -> datetime | None:
        since = now - timedelta(hours=max(1.0, lookback_hours))
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1,
                "startTime": 1,
                "orderTime": 1,
                "drugName": 1,
                "orderName": 1,
                "route": 1,
                "routeName": 1,
                "dose": 1,
                "doseUnit": 1,
                "unit": 1,
                "drugSpec": 1,
            },
        ).sort("executeTime", 1).limit(3000)

        events: list[dict] = []
        async for doc in cursor:
            t = _parse_dt(doc.get("executeTime")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            if not t or t < since:
                continue
            text = " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName", "route", "routeName")).lower()
            if not self._text_contains_any(text, opioid_keywords):
                continue
            dose_mg = self._extract_dose_mg(doc)
            route = str(doc.get("route") or doc.get("routeName") or "").lower()
            name = str(doc.get("drugName") or doc.get("orderName") or "").strip().lower()
            events.append({"time": t, "name": name, "dose_mg": dose_mg, "route": route})

        if len(events) < 2:
            return events[-1]["time"] if events else None

        last_by_name: dict[str, dict] = {}
        latest_adj = None
        for e in events:
            prev = last_by_name.get(e["name"])
            if prev:
                route_changed = bool(e["route"]) and bool(prev.get("route")) and (e["route"] != prev.get("route"))
                dose_changed = False
                if e["dose_mg"] is not None and prev.get("dose_mg") is not None:
                    base = max(abs(float(prev["dose_mg"])), 1e-6)
                    ratio = abs(float(e["dose_mg"]) - float(prev["dose_mg"])) / base
                    dose_changed = ratio >= dose_change_ratio_threshold
                if route_changed or dose_changed:
                    latest_adj = e["time"]
            last_by_name[e["name"]] = e

        return latest_adj or events[-1]["time"]

    async def _has_assessment_in_window(self, pid, kind: str, start_t: datetime, end_t: datetime) -> bool:
        if end_t <= start_t:
            return False
        hours = max(1, int((datetime.now() - start_t).total_seconds() / 3600.0) + 1)
        points = await self._get_assessment_series(pid, kind, hours=hours)
        for pt in points:
            t = _parse_dt(pt.get("time"))
            if t and start_t <= t <= end_t:
                return True
        return False

    async def _process_assessment_reminder(self, p: dict, now: datetime, score_type: str, cfg: dict) -> bool:
        pid = p.get("_id")
        if not pid:
            return False
        pid_str = str(pid)
        pid_candidates = [pid, pid_str]

        code = cfg.get("code") or self._cfg("assessments", score_type, "code", default=None)
        interval_hours = float(cfg.get("interval_hours", 4))
        if not code:
            return False

        active = await self.db.col("nurse_reminders").find_one(
            {"patient_id": pid_str, "score_type": score_type, "is_active": True},
            sort=[("created_at", -1)],
        )

        # CAM-ICU 仅在 RASS >= -3 时执行定时提醒
        if score_type == "cam_icu":
            rass_gte = float(cfg.get("rass_gte", -3))
            latest_rass = await self._get_latest_assessment(pid, "rass")
            applicable = latest_rass is not None and latest_rass >= rass_gte
            if not applicable:
                if active:
                    await self.db.col("nurse_reminders").update_one(
                        {"_id": active["_id"]},
                        {"$set": {"is_active": False, "resolved_at": now, "resolve_reason": "RASS不满足CAM-ICU评估条件"}},
                    )
                return False

        # CPOT/BPS: 常规定时 + 镇痛药调整前后补充提醒
        adjustment_due = False
        adjustment_due_at = None
        if score_type in ("cpot", "bps"):
            adj_enabled = bool(cfg.get("analgesic_adjustment_enabled", True))
            if adj_enabled:
                lookback_h = float(cfg.get("adjustment_lookback_hours", 8))
                assess_before_h = float(cfg.get("assessment_before_hours", 1))
                assess_after_h = float(cfg.get("assessment_after_hours", 1))
                dose_change_ratio = float(cfg.get("dose_change_ratio_threshold", 0.25))
                opioid_kw = self._get_cfg_list(
                    ("alert_engine", "drug_mapping", "opioids"),
                    ["吗啡", "芬太尼", "舒芬太尼", "瑞芬太尼", "羟考酮", "氢吗啡酮", "哌替啶", "曲马多", "可待因", "布托啡诺", "opioid"],
                )
                adj_t = await self._get_latest_opioid_adjustment_time(
                    pid_str,
                    now,
                    lookback_h,
                    dose_change_ratio,
                    opioid_kw,
                )
                if adj_t:
                    window_start = adj_t - timedelta(hours=assess_before_h)
                    window_end = adj_t + timedelta(hours=assess_after_h)
                    has_window_assessment = await self._has_assessment_in_window(pid, score_type, window_start, window_end)
                    if not has_window_assessment:
                        adjustment_due = True
                        adjustment_due_at = window_end

        last_time = await self._get_latest_score_time(pid_candidates, code)
        if last_time is None:
            admission = _parse_dt(p.get("icuAdmissionTime"))
            if admission is None:
                overdue = True
                due_at = now
            else:
                due_at = admission + timedelta(hours=interval_hours)
                overdue = now >= due_at
        else:
            due_at = last_time + timedelta(hours=interval_hours)
            overdue = now >= due_at

        if adjustment_due:
            # 镇痛药调整窗口未评估，立即纳入逾期
            due_at = adjustment_due_at or due_at
            overdue = True

        if overdue and not active:
            reminder_doc = {
                "patient_id": pid_str,
                "patient_name": p.get("name"),
                "bed": p.get("hisBed"),
                "dept": p.get("dept") or p.get("hisDept"),
                "deptCode": p.get("deptCode"),
                "score_type": score_type,
                "code": code,
                "rule_id": cfg.get("rule_id") or f"NURSE_{score_type.upper()}",
                "name": cfg.get("name") or f"{score_type.upper()}评估超时",
                "last_score_time": last_time,
                "due_at": due_at,
                "created_at": now,
                "is_active": True,
                "severity": cfg.get("severity", "warning"),
            }
            if adjustment_due and score_type in ("cpot", "bps"):
                reminder_doc["name"] = cfg.get("adjustment_name") or f"{score_type.upper()}评估(镇痛药调整前后)"
                reminder_doc["rule_id"] = cfg.get("adjustment_rule_id") or f"NURSE_{score_type.upper()}_ANALGESIA_ADJUST"
                reminder_doc["extra"] = {
                    "reason": "analgesic_adjustment_window_missing_assessment",
                    "adjustment_due": True,
                }
            res = await self.db.col("nurse_reminders").insert_one(reminder_doc)
            reminder_doc["_id"] = res.inserted_id
            await self._create_assessment_alert(reminder_doc)
            return True
        if (not overdue) and active:
            await self.db.col("nurse_reminders").update_one(
                {"_id": active["_id"]},
                {"$set": {"is_active": False, "resolved_at": now, "last_score_time": last_time}},
            )
        return False

    async def _process_turning_reminder(self, p: dict, now: datetime, turning_cfg: dict) -> bool:
        pid = p.get("_id")
        if not pid:
            return False
        pid_str = str(pid)

        braden_threshold = float(turning_cfg.get("braden_high_risk_threshold", 12))
        interval_high_h = float(turning_cfg.get("interval_hours", 2))
        interval_very_high_h = float(turning_cfg.get("very_high_risk_interval_hours", 1.5))
        lookback_h = float(turning_cfg.get("turning_event_lookback_hours", 96))
        turn_keywords = turning_cfg.get(
            "turning_keywords",
            ["翻身", "体位变换", "更换体位", "reposition", "turn", "侧卧", "俯卧位", "半卧位", "卧位调整"],
        )
        rass_threshold = float(turning_cfg.get("deep_sedation_rass_threshold", -2))
        bmi_low = float(turning_cfg.get("bmi_low_threshold", 18.5))
        bmi_high = float(turning_cfg.get("bmi_high_threshold", 30))

        active = await self.db.col("nurse_reminders").find_one(
            {"patient_id": pid_str, "score_type": "turning", "is_active": True},
            sort=[("created_at", -1)],
        )

        braden = await self._get_latest_assessment(pid, "braden")
        high_risk = braden is not None and braden <= braden_threshold
        if not high_risk:
            if active:
                await self.db.col("nurse_reminders").update_one(
                    {"_id": active["_id"]},
                    {"$set": {"is_active": False, "resolved_at": now, "resolve_reason": "Braden风险不再满足翻身提醒条件"}},
                )
            return False

        latest_rass = await self._get_latest_assessment(pid, "rass")
        has_vaso = await self._has_vasopressor(pid)
        bmi = self._parse_bmi(p)
        bmi_extreme = bmi is not None and (bmi > bmi_high or bmi < bmi_low)

        very_high = (latest_rass is not None and latest_rass < rass_threshold) and has_vaso and bmi_extreme
        interval_h = interval_very_high_h if very_high else interval_high_h
        severity = "critical" if very_high else "high"
        risk_level = "very_high" if very_high else "high"

        last_turn_time = await self._get_last_turn_time(pid_str, now, lookback_h, turn_keywords)
        if last_turn_time is None:
            admission = _parse_dt(p.get("icuAdmissionTime"))
            if admission is None:
                due_at = now
                overdue = True
            else:
                due_at = admission + timedelta(hours=interval_h)
                overdue = now >= due_at
        else:
            due_at = last_turn_time + timedelta(hours=interval_h)
            overdue = now >= due_at

        if not overdue:
            if active:
                await self.db.col("nurse_reminders").update_one(
                    {"_id": active["_id"]},
                    {
                        "$set": {
                            "is_active": False,
                            "resolved_at": now,
                            "last_score_time": last_turn_time,
                            "resolve_reason": "检测到最新翻身记录，提醒关闭",
                        }
                    },
                )
            return False

        should_fire = False
        if not active:
            should_fire = True
        else:
            last_trigger = _parse_dt(active.get("created_at"))
            if (last_trigger is None) or (now - last_trigger >= timedelta(hours=interval_h)):
                # 到达下一轮提醒周期，关闭上一条并重发
                await self.db.col("nurse_reminders").update_one(
                    {"_id": active["_id"]},
                    {"$set": {"is_active": False, "resolved_at": now, "resolve_reason": "翻身提醒周期到达，触发下一轮提醒"}},
                )
                should_fire = True
            else:
                await self.db.col("nurse_reminders").update_one(
                    {"_id": active["_id"]},
                    {
                        "$set": {
                            "due_at": due_at,
                            "severity": severity,
                            "name": "翻身提醒(极高风险)" if very_high else "翻身提醒",
                            "extra": {
                                "risk_level": risk_level,
                                "braden": braden,
                                "rass": latest_rass,
                                "has_vasopressor": has_vaso,
                                "bmi": bmi,
                                "interval_hours": interval_h,
                                "last_turn_time": last_turn_time,
                            },
                        }
                    },
                )

        if not should_fire:
            return False

        reminder_doc = {
            "patient_id": pid_str,
            "patient_name": p.get("name"),
            "bed": p.get("hisBed"),
            "dept": p.get("dept") or p.get("hisDept"),
            "deptCode": p.get("deptCode"),
            "score_type": "turning",
            "code": turning_cfg.get("code", "nurse_turning"),
            "rule_id": "NURSE_TURNING_VERY_HIGH" if very_high else "NURSE_TURNING_HIGH",
            "name": "翻身提醒(极高风险)" if very_high else "翻身提醒",
            "last_score_time": last_turn_time,
            "due_at": due_at,
            "created_at": now,
            "is_active": True,
            "severity": severity,
            "extra": {
                "risk_level": risk_level,
                "braden": braden,
                "rass": latest_rass,
                "has_vasopressor": has_vaso,
                "bmi": bmi,
                "interval_hours": interval_h,
                "last_turn_time": last_turn_time,
            },
        }
        res = await self.db.col("nurse_reminders").insert_one(reminder_doc)
        reminder_doc["_id"] = res.inserted_id
        await self._create_assessment_alert(reminder_doc)
        return True

    async def _process_early_mobility_reminder(self, p: dict, now: datetime, cfg: dict) -> bool:
        pid = p.get("_id")
        if not pid:
            return False
        pid_str = str(pid)

        active = await self.db.col("nurse_reminders").find_one(
            {"patient_id": pid_str, "score_type": "early_mobility", "is_active": True},
            sort=[("created_at", -1)],
        )

        interval_h = float(cfg.get("interval_hours", 8))
        icu_h_threshold = float(cfg.get("icu_hours_threshold", 48))
        inactivity_h = float(cfg.get("inactivity_hours", 24))
        map_threshold = float(cfg.get("map_threshold", 60))
        norepi_threshold = float(cfg.get("norepi_threshold_ug_kg_min", 0.2))
        norepi_lookback_h = float(cfg.get("norepi_lookback_hours", 12))
        norepi_min_drop_ratio = float(cfg.get("norepi_taper_min_drop_ratio", 0.1))
        fio2_threshold = float(cfg.get("fio2_threshold", 0.6))
        peep_threshold = float(cfg.get("peep_threshold", 10))
        rass_min = float(cfg.get("rass_min", -1))
        rass_max = float(cfg.get("rass_max", 1))
        activity_keywords = cfg.get(
            "activity_keywords",
            ["活动", "下床", "坐起", "坐位", "站立", "行走", "床边活动", "早期活动", "康复训练", "转移到椅", "步行"],
        )
        norepi_keywords = cfg.get("norepi_keywords", ["去甲肾上腺素", "norepinephrine", "noradrenaline", "去甲"])

        admission = _parse_dt(p.get("icuAdmissionTime"))
        icu_hours = None
        if admission:
            icu_hours = max(0.0, (now - admission).total_seconds() / 3600.0)
        icu_ok = icu_hours is not None and icu_hours > icu_h_threshold

        # 条件(1): 血流动力学稳定
        vitals = await self._get_latest_vitals_by_patient(pid)
        map_value = _to_float(vitals.get("map")) if isinstance(vitals, dict) else None
        map_ok = map_value is not None and map_value > map_threshold

        weight_kg = self._get_patient_weight(p)
        norepi_series = await self._get_norepi_dose_series(
            pid_str,
            now,
            norepi_lookback_h,
            norepi_keywords,
            weight_kg,
        )
        norepi_latest = norepi_series[-1]["dose_ug_kg_min"] if norepi_series else None
        norepi_tapering = self._is_series_tapering(norepi_series, norepi_min_drop_ratio)
        vaso_level = await self._get_vasopressor_level(pid)

        if norepi_latest is not None:
            norepi_ok = (norepi_latest <= norepi_threshold) or norepi_tapering
        else:
            # 未检测到去甲剂量时，若无显著升压支持则视作通过
            norepi_ok = vaso_level <= 2
        hemo_ok = map_ok and norepi_ok

        # 条件(2): 呼吸支持门槛
        device_id = await self._get_device_id_for_patient(p, ["vent"])
        fio2_frac = None
        peep = None
        resp_ok = True
        if device_id:
            cap = await self._get_latest_device_cap(
                device_id,
                codes=["param_FiO2", "param_vent_measure_peep", "param_vent_peep"],
            )
            if cap:
                fio2 = self._vent_param(cap, "fio2", "param_FiO2")
                if fio2 is not None:
                    fio2_frac = (fio2 / 100.0) if fio2 > 1 else fio2
                peep = self._vent_param_priority(
                    cap,
                    ["peep_measured", "peep_set"],
                    ["param_vent_measure_peep", "param_vent_peep"],
                )
                resp_ok = (
                    (fio2_frac is not None and fio2_frac <= fio2_threshold)
                    and (peep is not None and peep <= peep_threshold)
                )
            else:
                resp_ok = False

        # 条件(3): 意识状态可配合
        rass = await self._get_latest_assessment(pid, "rass")
        rass_ok = rass is not None and rass_min <= rass <= rass_max

        # 条件(4): ICU>48h 且近24h无活动
        last_activity = await self._get_last_activity_time(pid_str, now, inactivity_h, activity_keywords)
        no_recent_activity = last_activity is None
        activity_ok = icu_ok and no_recent_activity

        eligible = hemo_ok and resp_ok and rass_ok and activity_ok
        if not eligible:
            if active:
                reasons = []
                if not map_ok:
                    reasons.append("MAP不达标")
                if not norepi_ok:
                    reasons.append("去甲肾上腺素条件不达标")
                if not resp_ok:
                    reasons.append("呼吸支持参数不达标")
                if not rass_ok:
                    reasons.append("RASS不在-1~+1")
                if not activity_ok:
                    reasons.append("近24h已有活动或ICU时长不足")
                await self.db.col("nurse_reminders").update_one(
                    {"_id": active["_id"]},
                    {
                        "$set": {
                            "is_active": False,
                            "resolved_at": now,
                            "resolve_reason": "；".join(reasons) if reasons else "早期活动触发条件不满足",
                        }
                    },
                )
            return False

        due_at = now
        should_fire = False
        if not active:
            should_fire = True
        else:
            last_trigger = _parse_dt(active.get("created_at"))
            if (last_trigger is None) or (now - last_trigger >= timedelta(hours=interval_h)):
                await self.db.col("nurse_reminders").update_one(
                    {"_id": active["_id"]},
                    {"$set": {"is_active": False, "resolved_at": now, "resolve_reason": "早期活动提醒周期到达，触发下一轮提醒"}},
                )
                should_fire = True
            else:
                await self.db.col("nurse_reminders").update_one(
                    {"_id": active["_id"]},
                    {
                        "$set": {
                            "due_at": due_at,
                            "severity": cfg.get("severity", "warning"),
                            "extra": {
                                "icu_hours": round(float(icu_hours or 0), 2),
                                "map": map_value,
                                "norepi_latest_ug_kg_min": norepi_latest,
                                "norepi_tapering": norepi_tapering,
                                "vasopressor_level": vaso_level,
                                "fio2_fraction": fio2_frac,
                                "peep": peep,
                                "rass": rass,
                                "last_activity_time": last_activity,
                                "condition_check": {
                                    "hemodynamic_ok": hemo_ok,
                                    "resp_ok": resp_ok,
                                    "rass_ok": rass_ok,
                                    "icu_and_inactivity_ok": activity_ok,
                                },
                                "interval_hours": interval_h,
                            },
                        }
                    },
                )

        if not should_fire:
            return False

        reminder_doc = {
            "patient_id": pid_str,
            "patient_name": p.get("name"),
            "bed": p.get("hisBed"),
            "dept": p.get("dept") or p.get("hisDept"),
            "deptCode": p.get("deptCode"),
            "score_type": "early_mobility",
            "code": cfg.get("code", "nurse_early_mobility"),
            "rule_id": cfg.get("rule_id", "NURSE_EARLY_MOBILITY"),
            "name": cfg.get("name", "建议评估早期活动"),
            "last_score_time": last_activity,
            "due_at": due_at,
            "created_at": now,
            "is_active": True,
            "severity": cfg.get("severity", "warning"),
            "extra": {
                "icu_hours": round(float(icu_hours or 0), 2),
                "map": map_value,
                "norepi_latest_ug_kg_min": norepi_latest,
                "norepi_tapering": norepi_tapering,
                "vasopressor_level": vaso_level,
                "fio2_fraction": fio2_frac,
                "peep": peep,
                "rass": rass,
                "last_activity_time": last_activity,
                "condition_check": {
                    "hemodynamic_ok": hemo_ok,
                    "resp_ok": resp_ok,
                    "rass_ok": rass_ok,
                    "icu_and_inactivity_ok": activity_ok,
                },
                "interval_hours": interval_h,
            },
        }
        res = await self.db.col("nurse_reminders").insert_one(reminder_doc)
        reminder_doc["_id"] = res.inserted_id
        await self._create_assessment_alert(reminder_doc)
        return True

    async def scan_nurse_reminders(self) -> None:
        reminders_cfg = self.config.yaml_cfg.get("nurse_reminders", {})
        if not reminders_cfg:
            return

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {
                "name": 1,
                "hisBed": 1,
                "icuAdmissionTime": 1,
                "dept": 1,
                "hisDept": 1,
                "deptCode": 1,
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
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        triggered = 0

        for p in patients:
            for score_type, cfg in reminders_cfg.items():
                if not isinstance(cfg, dict):
                    continue
                if score_type in ("turning", "early_mobility"):
                    continue
                if await self._process_assessment_reminder(p, now, score_type, cfg):
                    triggered += 1

            turning_cfg = reminders_cfg.get("turning", {}) if isinstance(reminders_cfg, dict) else {}
            if await self._process_turning_reminder(p, now, turning_cfg):
                triggered += 1

            early_mobility_cfg = reminders_cfg.get("early_mobility", {}) if isinstance(reminders_cfg, dict) else {}
            if await self._process_early_mobility_reminder(p, now, early_mobility_cfg):
                triggered += 1

        if triggered > 0:
            self._log_info("护理提醒", triggered)

