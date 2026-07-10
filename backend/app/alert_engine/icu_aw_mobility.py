"""ICU-AW 风险分层与早期活动推荐。"""
from __future__ import annotations

import math
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


class IcuAwMobilityMixin:
    def _icu_aw_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("icu_aw", {})
        return cfg if isinstance(cfg, dict) else {}

    def _icu_aw_admission_time(self, patient_doc: dict) -> datetime | None:
        for key in (
            "icuAdmissionTime",
            "admissionTime",
            "inTime",
            "icuInTime",
            "createTime",
        ):
            t = _parse_dt(patient_doc.get(key))
            if isinstance(t, datetime):
                return t
        return None

    def _normalize_fraction(self, value: Any) -> float | None:
        try:
            v = float(value)
        except Exception:
            return None
        if v <= 0:
            return None
        return round(v / 100.0, 4) if v > 1 else round(v, 4)

    def _hours_between(self, start: datetime | None, end: datetime) -> float | None:
        if not isinstance(start, datetime):
            return None
        return round(max(0.0, (end - start).total_seconds() / 3600.0), 2)

    def _dedupe_names(self, names: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for name in names:
            s = str(name or "").strip()
            if not s:
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    def _risk_severity(self, score: float, warning: float, high: float, critical: float) -> str | None:
        if score >= critical:
            return "critical"
        if score >= high:
            return "high"
        if score >= warning:
            return "warning"
        return None

    async def _get_ventilation_days(self, pid, now: datetime, admission_time: datetime | None) -> dict:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return {"days": 0.0, "hours": 0.0, "currently_on_vent": False}

        cfg = self._icu_aw_cfg()
        max_lookback_days = int(cfg.get("max_lookback_days", 21))
        since = max(admission_time or (now - timedelta(days=max_lookback_days)), now - timedelta(days=max_lookback_days))

        cursor = self.db.col("deviceBind").find(
            {"pid": pid_str},
            {"type": 1, "bindTime": 1, "unBindTime": 1, "deviceID": 1},
        ).sort("bindTime", 1).limit(500)

        total_hours = 0.0
        currently_on_vent = False
        async for doc in cursor:
            type_text = str(doc.get("type") or "").lower()
            if not any(k in type_text for k in ["vent", "ventilator", "呼吸", "breath"]):
                continue
            bind_time = _parse_dt(doc.get("bindTime"))
            if not isinstance(bind_time, datetime):
                continue
            unbind_time = _parse_dt(doc.get("unBindTime")) or now
            start = max(bind_time, since)
            end = min(unbind_time, now)
            if end <= start:
                continue
            total_hours += (end - start).total_seconds() / 3600.0
            if doc.get("unBindTime") is None:
                currently_on_vent = True

        return {
            "days": round(total_hours / 24.0, 2),
            "hours": round(total_hours, 2),
            "currently_on_vent": currently_on_vent,
        }

    async def _get_sedative_exposure(self, pid, now: datetime, admission_time: datetime | None) -> dict:
        cfg = self._icu_aw_cfg()
        max_lookback_days = int(cfg.get("max_lookback_days", 21))
        start = max(admission_time or (now - timedelta(days=max_lookback_days)), now - timedelta(days=max_lookback_days))
        lookback_hours = max(24, min(int(math.ceil((now - start).total_seconds() / 3600.0)) + 1, max_lookback_days * 24))
        docs = await self._get_recent_drug_docs_window(pid, hours=lookback_hours, limit=1600)
        docs = [doc for doc in docs if isinstance(doc.get("_event_time"), datetime) and doc["_event_time"] >= start]

        sedative_kw = self._get_cfg_list(
            ("alert_engine", "icu_aw", "sedative_keywords"),
            self._get_cfg_list(("alert_engine", "drug_mapping", "sedatives"), ["咪达唑仑", "丙泊酚", "右美托咪定", "地西泮", "劳拉西泮"]),
        )
        benzo_kw = self._get_cfg_list(
            ("alert_engine", "icu_aw", "benzodiazepine_keywords"),
            ["咪达唑仑", "地西泮", "劳拉西泮", "阿普唑仑", "艾司唑仑", "氯硝西泮"],
        )
        propofol_kw = self._get_cfg_list(("alert_engine", "icu_aw", "propofol_keywords"), ["丙泊酚", "propofol"])
        dex_kw = self._get_cfg_list(("alert_engine", "icu_aw", "dexmedetomidine_keywords"), ["右美托咪定", "dexmedetomidine"])
        opioid_kw = self._get_cfg_list(("alert_engine", "icu_aw", "opioid_sedation_keywords"), ["芬太尼", "舒芬太尼", "瑞芬太尼"])

        matched_names: list[str] = []
        day_set: set[str] = set()
        class_set: set[str] = set()
        for doc in docs:
            text = self._drug_text(doc)
            if not self._contains_any(text, sedative_kw):
                continue
            matched_names.append(str(doc.get("drugName") or doc.get("orderName") or "").strip())
            day_set.add(doc["_event_time"].strftime("%Y-%m-%d"))
            if self._contains_any(text, benzo_kw):
                class_set.add("benzodiazepine")
            elif self._contains_any(text, propofol_kw):
                class_set.add("propofol")
            elif self._contains_any(text, dex_kw):
                class_set.add("dexmedetomidine")
            elif self._contains_any(text, opioid_kw):
                class_set.add("opioid_assisted")
            else:
                class_set.add("other")

        return {
            "days": float(len(day_set)),
            "classes": sorted(class_set),
            "class_count": len(class_set),
            "drugs": self._dedupe_names(matched_names),
        }

    async def _get_steroid_exposure(self, pid, now: datetime, admission_time: datetime | None) -> dict:
        cfg = self._icu_aw_cfg()
        max_lookback_days = int(cfg.get("max_lookback_days", 21))
        start = max(admission_time or (now - timedelta(days=max_lookback_days)), now - timedelta(days=max_lookback_days))
        lookback_hours = max(24, min(int(math.ceil((now - start).total_seconds() / 3600.0)) + 1, max_lookback_days * 24))
        steroid_kw = self._get_cfg_list(
            ("alert_engine", "icu_aw", "steroid_keywords"),
            ["地塞米松", "甲强龙", "甲泼尼龙", "氢化可的松", "泼尼松", "methylprednisolone", "dexamethasone", "hydrocortisone"],
        )
        docs = await self._find_recent_drug_docs(pid, steroid_kw, hours=lookback_hours, limit=800)
        docs = [doc for doc in docs if isinstance(doc.get("_event_time"), datetime) and doc["_event_time"] >= start]
        day_set = {doc["_event_time"].strftime("%Y-%m-%d") for doc in docs if isinstance(doc.get("_event_time"), datetime)}
        return {
            "days": float(len(day_set)),
            "drugs": self._dedupe_names([str(doc.get("drugName") or doc.get("orderName") or "").strip() for doc in docs]),
        }

    async def _get_glucose_instability(self, pid_str: str, his_pid: str | None, now: datetime) -> dict:
        cfg = self._icu_aw_cfg()
        glucose_window_hours = int(cfg.get("glucose_window_hours", 48))
        since = now - timedelta(hours=max(12, glucose_window_hours))
        glucose_codes = self._get_cfg_list(
            ("alert_engine", "data_mapping", "glucose", "codes"),
            ["param_blood_glucose", "param_glu", "param_血糖", "blood_glucose"],
        )
        bedside_points = await self._get_bedside_glucose_points(pid_str, since, glucose_codes)
        lab_points = await self._get_lab_glucose_points(his_pid, since) if his_pid else []
        points = sorted([*bedside_points, *lab_points], key=lambda x: x.get("time") or datetime.min)
        values = [float(p["value"]) for p in points if p.get("value") is not None]
        cv = self._calc_cv_percent(values)
        min_val = min(values) if values else None
        max_val = max(values) if values else None
        cv_warn = float(cfg.get("glucose_cv_threshold", self._icu_aw_cfg().get("glucose_cv_threshold", 36)))
        low_thr = float(cfg.get("glucose_low_threshold", 3.9))
        high_thr = float(cfg.get("glucose_high_threshold", 10.0))
        unstable = bool((cv is not None and cv >= cv_warn) or (min_val is not None and min_val < low_thr) or (max_val is not None and max_val > high_thr))
        return {
            "unstable": unstable,
            "cv_percent": cv,
            "min": round(min_val, 2) if min_val is not None else None,
            "max": round(max_val, 2) if max_val is not None else None,
            "points": len(points),
        }

    async def _get_icu_aw_sepsis_sofa_signal(self, patient_doc: dict, pid, device_id: str | None, his_pid: str | None) -> dict:
        pid_str = self._pid_str(pid)
        sofa = await self._calc_sofa(patient_doc, pid, device_id, his_pid) if his_pid else None
        sepsis_alert = await self._get_latest_active_alert(pid_str, ["septic_shock", "sofa", "qsofa"], hours=72) if pid_str else None
        return {
            "sofa": sofa,
            "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
            "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
            "sepsis_active": bool(sepsis_alert),
            "sepsis_alert_type": sepsis_alert.get("alert_type") if isinstance(sepsis_alert, dict) else None,
        }

    async def _has_active_bleeding(self, pid_str: str, patient_doc: dict) -> bool:
        alert_types = self._get_cfg_list(
            ("alert_engine", "icu_aw", "active_bleeding_alert_types"),
            ["gi_bleeding", "postop_bleeding"],
        )
        active = await self._get_latest_active_alert(pid_str, alert_types, hours=48)
        if active:
            return True
        text = " ".join(
            str(patient_doc.get(k) or "")
            for k in ("clinicalDiagnosis", "admissionDiagnosis", "history", "diagnosisHistory")
        ).lower()
        bleed_kw = self._get_cfg_list(("alert_engine", "icu_aw", "active_bleeding_keywords"), ["活动性出血", "active bleeding"])
        return self._contains_any(text, bleed_kw)

    def _has_unstable_fracture(self, patient_doc: dict) -> bool:
        text = " ".join(
            str(patient_doc.get(k) or "")
            for k in ("clinicalDiagnosis", "admissionDiagnosis", "history", "diagnosisHistory", "surgeryHistory")
        ).lower()
        fracture_kw = self._get_cfg_list(
            ("alert_engine", "icu_aw", "unstable_fracture_keywords"),
            ["不稳定骨折", "unstable fracture", "骨盆不稳", "脊柱不稳", "骨折未固定"],
        )
        return self._contains_any(text, fracture_kw)

    async def _assess_early_mobility_readiness(
        self,
        patient_doc: dict,
        *,
        pid,
        pid_str: str,
        now: datetime,
        immobility_hours: float,
    ) -> dict:
        cfg = self._icu_aw_cfg()
        mobility_cfg = cfg.get("mobility", {}) if isinstance(cfg.get("mobility"), dict) else {}
        nurse_cfg = self.config.yaml_cfg.get("nurse_reminders", {}).get("early_mobility", {})

        fio2_threshold = float(mobility_cfg.get("fio2_threshold", nurse_cfg.get("fio2_threshold", 0.6)))
        peep_threshold = float(mobility_cfg.get("peep_threshold", nurse_cfg.get("peep_threshold", 10)))
        norepi_threshold = float(mobility_cfg.get("norepi_threshold_ug_kg_min", nurse_cfg.get("norepi_threshold_ug_kg_min", 0.2)))
        norepi_lookback_h = float(mobility_cfg.get("norepi_lookback_hours", nurse_cfg.get("norepi_lookback_hours", 12)))
        norepi_min_drop_ratio = float(mobility_cfg.get("norepi_taper_min_drop_ratio", nurse_cfg.get("norepi_taper_min_drop_ratio", 0.1)))
        rass_min = float(mobility_cfg.get("rass_min", -2))
        rass_max = float(mobility_cfg.get("rass_max", 1))
        map_threshold = float(mobility_cfg.get("map_threshold", nurse_cfg.get("map_threshold", 60)))
        activity_keywords = self._get_cfg_list(
            ("alert_engine", "icu_aw", "activity_keywords"),
            nurse_cfg.get("activity_keywords", ["活动", "下床", "坐起", "坐位", "站立", "行走", "床边活动", "早期活动", "康复训练", "转移到椅", "步行"]),
        )
        norepi_keywords = self._get_cfg_list(
            ("alert_engine", "icu_aw", "norepi_keywords"),
            nurse_cfg.get("norepi_keywords", ["去甲肾上腺素", "norepinephrine", "noradrenaline", "去甲"]),
        )

        vitals = await self._get_latest_vitals_by_patient(pid)
        map_value = vitals.get("map") if isinstance(vitals, dict) else None
        hr = vitals.get("hr") if isinstance(vitals, dict) else None
        spo2 = vitals.get("spo2") if isinstance(vitals, dict) else None

        weight_kg = self._get_patient_weight(patient_doc)
        norepi_series = await self._get_norepi_dose_series(pid_str, now, norepi_lookback_h, norepi_keywords, weight_kg)
        norepi_latest = norepi_series[-1]["dose_ug_kg_min"] if norepi_series else None
        norepi_tapering = self._is_series_tapering(norepi_series, norepi_min_drop_ratio)
        current_vasopressors = await self._get_current_vasopressor_snapshot(pid, patient_doc, hours=8, max_items=4)
        has_vaso = bool(current_vasopressors)
        if norepi_latest is not None:
            vasopressor_ok = bool(norepi_latest <= norepi_threshold or norepi_tapering)
        else:
            vasopressor_ok = not has_vaso

        vent_device_id = await self._get_device_id_for_patient(patient_doc, ["vent"])
        vent_cap = await self._get_latest_device_cap(vent_device_id) if vent_device_id else None
        fio2_raw = self._vent_param(vent_cap or {}, "fio2", "param_FiO2") if vent_cap else None
        fio2_frac = self._normalize_fraction(fio2_raw) if fio2_raw is not None else None
        peep = self._vent_param_priority(vent_cap or {}, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"]) if vent_cap else None
        resp_ok = True if not vent_cap else bool((fio2_frac is not None and fio2_frac <= fio2_threshold) and (peep is not None and peep <= peep_threshold))

        latest_rass = await self._get_latest_assessment(pid, "rass")
        rass_ok = latest_rass is not None and rass_min <= float(latest_rass) <= rass_max
        last_activity_time = await self._get_last_activity_time(pid_str, now, 96, activity_keywords)
        hours_since_activity = self._hours_between(last_activity_time, now)
        bleeding_active = await self._has_active_bleeding(pid_str, patient_doc)
        unstable_fracture = self._has_unstable_fracture(patient_doc)
        map_ok = map_value is None or float(map_value) >= map_threshold
        eligible = bool(resp_ok and vasopressor_ok and rass_ok and map_ok and not bleeding_active and not unstable_fracture)

        reasons: list[str] = []
        if not map_ok:
            reasons.append(f"MAP<{map_threshold:.0f}mmHg")
        if not vasopressor_ok:
            reasons.append("血管活性药未稳定或未递减")
        if not resp_ok:
            reasons.append(f"FiO₂/PEEP 未达到 {fio2_threshold:.2f}/{peep_threshold:.0f} 门槛")
        if not rass_ok:
            reasons.append(f"RASS不在 {rass_min:.0f}~{rass_max:.0f}")
        if bleeding_active:
            reasons.append("存在活动性出血")
        if unstable_fracture:
            reasons.append("存在不稳定骨折")

        level = 1
        label = "1级：床上被动活动/关节活动"
        if eligible:
            level = 2
            label = "2级：床上主动活动/抬头坐起"
            if (not has_vaso) and (fio2_frac is None or fio2_frac <= 0.5) and (peep is None or peep <= 8):
                level = 3
                label = "3级：床缘坐起/转移至椅旁"
            if level >= 3 and (spo2 is None or float(spo2) >= 92) and (hr is None or 50 <= float(hr) <= 130):
                level = 4
                label = "4级：站立/床旁踏步"
            if level >= 4 and not vent_cap and not has_vaso and (fio2_frac is None or fio2_frac <= 0.4):
                level = 5
                label = "5级：下床行走"

        return {
            "eligible": eligible,
            "recommended_level": level,
            "recommended_level_label": label,
            "reasons": reasons,
            "map": round(float(map_value), 1) if map_value is not None else None,
            "hr": round(float(hr), 1) if hr is not None else None,
            "spo2": round(float(spo2), 1) if spo2 is not None else None,
            "fio2_fraction": fio2_frac,
            "peep": round(float(peep), 1) if peep is not None else None,
            "rass": round(float(latest_rass), 1) if latest_rass is not None else None,
            "norepi_latest_ug_kg_min": round(float(norepi_latest), 4) if norepi_latest is not None else None,
            "norepi_tapering": norepi_tapering,
            "current_vasopressors": current_vasopressors,
            "bleeding_active": bleeding_active,
            "unstable_fracture": unstable_fracture,
            "last_activity_time": last_activity_time,
            "hours_since_activity": hours_since_activity,
            "immobility_hours": immobility_hours,
        }

    async def _build_icu_aw_explanation(self, *, severity: str, score: float, factors: list[dict], readiness: dict | None = None) -> dict:
        top_evidence = [str(item.get("evidence") or "").strip() for item in factors[:3] if isinstance(item, dict) and str(item.get("evidence") or "").strip()]
        summary = f"ICU-AW 风险{('极高' if severity == 'critical' else '升高')}，建议尽早进入康复评估闭环。"
        suggestion = "请联合医生、护理与康复治疗师评估镇静、卧床和活动计划。"
        if readiness and readiness.get("eligible"):
            lvl = readiness.get("recommended_level")
            label = readiness.get("recommended_level_label")
            summary = f"ICU-AW 高风险，且当前已满足早期活动启动条件，可考虑启动{lvl}级活动。"
            suggestion = f"建议今日启动{label}，并同步记录活动耐受性与中止原因。"
        return await self._polish_structured_alert_explanation(
            {
                "summary": summary,
                "evidence": [f"ICU-AW评分 {round(score, 1)}"] + top_evidence,
                "suggestion": suggestion,
                "text": "",
            }
        )

    async def scan_icu_aw_mobility(self) -> None:
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
                "weightKg": 1,
                "weight_kg": 1,
                "icuAdmissionTime": 1,
                "admissionTime": 1,
                "inTime": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "history": 1,
                "diagnosisHistory": 1,
                "surgeryHistory": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self._icu_aw_cfg()
        weights = cfg.get("factor_weights", {}) if isinstance(cfg.get("factor_weights"), dict) else {}
        warning_score = float(cfg.get("warning_score", 4))
        high_score = float(cfg.get("high_score", 7))
        critical_score = float(cfg.get("critical_score", 10))
        vent_days_warn = float(cfg.get("ventilation_days_warning", 3))
        vent_days_high = float(cfg.get("ventilation_days_high", 7))
        sed_days_thr = float(cfg.get("sedative_days_threshold", 3))
        sofa_thr = float(cfg.get("sofa_threshold", 8))
        immobility_thr = float(cfg.get("immobility_hours_threshold", 72))
        mobility_opportunity_thr = float(cfg.get("mobility_opportunity_immobility_hours", immobility_thr))

        now = datetime.now()
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip() or None
            admission_time = self._icu_aw_admission_time(patient_doc)
            device_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])

            vent_info = await self._get_ventilation_days(pid, now, admission_time)
            sed_info = await self._get_sedative_exposure(pid, now, admission_time)
            steroid_info = await self._get_steroid_exposure(pid, now, admission_time)
            glucose_info = await self._get_glucose_instability(pid_str, his_pid, now)
            sepsis_sofa = await self._get_icu_aw_sepsis_sofa_signal(patient_doc, pid, device_id, his_pid)
            immobility_hours = await self._immobility_hours(patient_doc, pid, now)
            readiness = await self._assess_early_mobility_readiness(
                patient_doc,
                pid=pid,
                pid_str=pid_str,
                now=now,
                immobility_hours=immobility_hours,
            )

            age_years = self._parse_age_years(patient_doc)
            score = 0.0
            factors: list[dict] = []

            def add_factor(key: str, matched: bool, evidence: str, default_weight: float) -> None:
                nonlocal score
                if not matched:
                    return
                w = float(weights.get(key, default_weight))
                score += w
                factors.append({"factor": key, "weight": w, "evidence": evidence})

            add_factor("age_ge_65", age_years is not None and age_years >= 65, f"年龄 {round(float(age_years), 1) if age_years is not None else '—'} 岁", 1)
            add_factor("mechanical_ventilation_ge_3d", float(vent_info.get("days") or 0) >= vent_days_warn, f"机械通气 {vent_info.get('days')} 天", 2)
            add_factor("mechanical_ventilation_ge_7d", float(vent_info.get("days") or 0) >= vent_days_high, f"长程机械通气 {vent_info.get('days')} 天", 3)
            add_factor("sedative_exposure_ge_3d", float(sed_info.get("days") or 0) >= sed_days_thr, f"镇静药暴露 {sed_info.get('days')} 天", 2)
            add_factor("sedative_multiclass", int(sed_info.get("class_count") or 0) >= 2, f"镇静类别 {','.join(sed_info.get('classes') or [])}", 1)
            add_factor("sofa_ge_8", (sepsis_sofa.get("sofa_score") or 0) >= sofa_thr, f"SOFA {sepsis_sofa.get('sofa_score')} 分", 2)
            add_factor("sepsis_active", bool(sepsis_sofa.get("sepsis_active")), f"近72h存在脓毒症相关预警({sepsis_sofa.get('sepsis_alert_type')})", 2)
            add_factor(
                "glucose_instability",
                bool(glucose_info.get("unstable")),
                f"血糖波动异常 CV={glucose_info.get('cv_percent')}%, 范围 {glucose_info.get('min')}~{glucose_info.get('max')} mmol/L",
                1,
            )
            add_factor("steroid_exposure", float(steroid_info.get("days") or 0) >= 2, f"激素暴露 {steroid_info.get('days')} 天", 1)
            add_factor("immobility_ge_72h", immobility_hours >= immobility_thr, f"卧床/制动 {round(immobility_hours, 1)} h", 2)

            severity = self._risk_severity(score, warning_score, high_score, critical_score)
            if severity in {"high", "critical"}:
                rule_id = f"ICU_AW_RISK_{severity.upper()}"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    explanation = await self._build_icu_aw_explanation(severity=severity, score=score, factors=factors)
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="ICU-AW高风险",
                        category="rehabilitation",
                        alert_type="icu_aw_risk",
                        severity=severity,
                        parameter="icu_aw_score",
                        condition={
                            "warning_score": warning_score,
                            "high_score": high_score,
                            "critical_score": critical_score,
                        },
                        value=round(score, 1),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=now,
                        explanation=explanation,
                        extra={
                            "risk_score": round(score, 1),
                            "factors": factors,
                            "age": round(float(age_years), 1) if age_years is not None else None,
                            "ventilation_days": vent_info.get("days"),
                            "currently_on_vent": vent_info.get("currently_on_vent"),
                            "sedative_days": sed_info.get("days"),
                            "sedative_classes": sed_info.get("classes"),
                            "sedative_drugs": sed_info.get("drugs"),
                            "steroid_days": steroid_info.get("days"),
                            "steroid_drugs": steroid_info.get("drugs"),
                            "sofa_score": sepsis_sofa.get("sofa_score"),
                            "sofa_delta": sepsis_sofa.get("sofa_delta"),
                            "sepsis_active": sepsis_sofa.get("sepsis_active"),
                            "glucose_instability": glucose_info,
                            "immobility_hours": round(immobility_hours, 1),
                            "mobility_readiness": readiness,
                            "recommended_level": readiness.get("recommended_level"),
                            "recommended_level_label": readiness.get("recommended_level_label"),
                            "last_activity_time": readiness.get("last_activity_time"),
                        },
                    )
                    if alert:
                        triggered += 1

            if score < high_score:
                continue
            no_recent_activity = readiness.get("last_activity_time") is None
            if not (readiness.get("eligible") and immobility_hours >= mobility_opportunity_thr and no_recent_activity):
                continue

            rule_id = "ICU_AW_MOBILITY_OPPORTUNITY"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            level = readiness.get("recommended_level")
            label = readiness.get("recommended_level_label")
            explanation = await self._build_icu_aw_explanation(severity="high", score=score, factors=factors, readiness=readiness)
            alert = await self._create_alert(
                rule_id=rule_id,
                name="早期活动时机已到",
                category="rehabilitation",
                alert_type="early_mobility_recommendation",
                severity="high",
                parameter="mobility_level",
                condition={
                    "icu_aw_high_risk": True,
                    "mobility_ready": True,
                    "immobility_hours": round(immobility_hours, 1),
                },
                value=level,
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                source_time=now,
                explanation=explanation,
                extra={
                    "risk_score": round(score, 1),
                    "factors": factors,
                    "immobility_hours": round(immobility_hours, 1),
                    "mobility_readiness": readiness,
                    "recommended_level": level,
                    "recommended_level_label": label,
                    "last_activity_time": readiness.get("last_activity_time"),
                    "hours_since_activity": readiness.get("hours_since_activity"),
                    "current_vasopressors": readiness.get("current_vasopressors"),
                    "message": f"当前满足活动条件，建议启动{label}。",
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("ICU-AW/早期活动", triggered)
