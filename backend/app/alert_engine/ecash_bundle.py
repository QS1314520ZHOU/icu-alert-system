"""eCASH bundle 协调层。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class EcashBundleMixin:
    def _ecash_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("ecash", {})
        return cfg if isinstance(cfg, dict) else {}

    def _sat_stress_cfg(self) -> dict:
        cfg = self._ecash_cfg().get("sat_stress", {})
        return cfg if isinstance(cfg, dict) else {}

    def _status_rank(self, status: str | None) -> int:
        return {"green": 1, "yellow": 2, "red": 3}.get(str(status or "").lower(), 0)

    def _worst_status(self, *statuses: str | None) -> str:
        ranked = sorted((str(s or "green") for s in statuses), key=self._status_rank, reverse=True)
        return ranked[0] if ranked else "green"

    def _hours_ago(self, t: datetime | None, now: datetime) -> float | None:
        if not isinstance(t, datetime):
            return None
        return round(max(0.0, (now - t).total_seconds() / 3600.0), 2)

    def _coerce_time(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if value in (None, ""):
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

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

    async def _latest_assessment_entry(self, pid, kind: str, hours: int = 48) -> dict | None:
        series = await self._get_assessment_series(pid, kind, hours=hours)
        if not series:
            return None
        last = series[-1]
        t = last.get("time")
        v = last.get("value")
        if not isinstance(t, datetime) or v is None:
            return None
        return {"time": t, "value": float(v)}

    def _pain_control_flags(self, tool: str | None, score: float | None) -> tuple[bool, bool]:
        if score is None:
            return False, False
        tool_norm = str(tool or "").upper()
        if tool_norm == "CPOT":
            return score < 3, score >= 5
        if tool_norm == "BPS":
            return score < 5, score >= 8
        # NRS 兜底
        return score <= 3, score >= 7

    def _sedation_off_target_gap(self, latest_rass: float | None, target_low: float, target_high: float) -> float | None:
        if latest_rass is None:
            return None
        if latest_rass < target_low:
            return round(target_low - latest_rass, 2)
        if latest_rass > target_high:
            return round(latest_rass - target_high, 2)
        return 0.0

    async def _is_over_sedated(self, pid, target_low: float, hours: int = 24) -> bool:
        series = await self._get_assessment_series(pid, "rass", hours=hours)
        if not series:
            return False
        tail = [row for row in series if isinstance(row.get("time"), datetime) and row.get("value") is not None]
        if not tail:
            return False
        latest = tail[-1]
        if float(latest["value"]) >= target_low:
            return False
        start_time = latest["time"]
        for row in reversed(tail[:-1]):
            if float(row["value"]) < target_low:
                start_time = row["time"]
            else:
                break
        return (latest["time"] - start_time).total_seconds() >= 4 * 3600

    async def _calc_delirium_risk_score(self, patient_doc: dict, pid) -> float | None:
        age_years = self._parse_age_years(patient_doc)
        has_age_risk = age_years is not None and age_years > 65

        drugs_24h = await self._get_recent_drugs(pid, hours=24)
        benzodiazepines = self._get_cfg_list(
            ("alert_engine", "delirium_risk", "benzodiazepine_keywords"),
            ["咪达唑仑", "地西泮", "劳拉西泮", "阿普唑仑", "艾司唑仑", "氯硝西泮"],
        )
        morphine_kw = self._get_cfg_list(
            ("alert_engine", "delirium_risk", "morphine_keywords"),
            ["吗啡", "morphine"],
        )

        has_benzo = self._contains_any(drugs_24h, benzodiazepines)
        has_morphine = self._contains_any(drugs_24h, morphine_kw)
        emergency_adm = self._is_emergency_admission(patient_doc)
        mech_vent = await self._has_mechanical_ventilation(patient_doc)

        his_pid = patient_doc.get("hisPid")
        labs = await self._load_delirium_labs(his_pid, lookback_hours=72) if his_pid else {}
        bun_high = self._bun_is_high(labs.get("bun"))
        has_acidosis, _ = self._metabolic_acidosis(labs)

        latest_rass = await self._get_latest_assessment(pid, "rass")
        latest_gcs = await self._get_latest_assessment(pid, "gcs")

        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("delirium_risk", {})
        weights = cfg.get("factor_weights", {}) if isinstance(cfg, dict) else {}

        score = 0.0
        factors = {
            "age_gt_65": (has_age_risk, 1.0),
            "benzodiazepine": (has_benzo, 2.0),
            "emergency_admission": (emergency_adm, 1.0),
            "mechanical_ventilation": (mech_vent, 2.0),
            "metabolic_acidosis": (has_acidosis, 2.0),
            "morphine_use": (has_morphine, 1.0),
            "bun_elevated": (bun_high, 2.0),
            "deep_sedation": (latest_rass is not None and latest_rass < -3, 1.0),
            "gcs_low": (latest_gcs is not None and latest_gcs < 13, 1.0),
        }
        for key, (matched, default_weight) in factors.items():
            if matched:
                score += float(weights.get(key, default_weight))
        return round(score, 2)

    def _patient_diag_text(self, patient_doc: dict) -> str:
        return " ".join(
            str(patient_doc.get(k) or "")
            for k in (
                "clinicalDiagnosis",
                "admissionDiagnosis",
                "diagnosis",
                "history",
                "diagnosisHistory",
                "surgeryHistory",
                "remark",
            )
        ).lower()

    def _sat_risk_groups(self, patient_doc: dict) -> list[dict]:
        cfg = self._sat_stress_cfg()
        text = self._patient_diag_text(patient_doc)
        groups: list[dict] = []

        neuro_kw = self._get_cfg_list(
            ("alert_engine", "ecash", "sat_stress", "neurosurgery_keywords"),
            ["脑外科", "开颅", "颅脑术后", "神经外科术后"],
        )
        aorta_kw = self._get_cfg_list(
            ("alert_engine", "ecash", "sat_stress", "aortic_keywords"),
            ["夹层", "主动脉夹层", "动脉瘤", "主动脉瘤", "aortic dissection", "aneurysm"],
        )
        cad_hf_kw = self._get_cfg_list(
            ("alert_engine", "ecash", "sat_stress", "cad_hf_keywords"),
            ["冠心病", "心肌缺血", "心衰", "心力衰竭", "heart failure", "cad", "chf"],
        )

        if self._match_name_keywords(text, neuro_kw):
            groups.append(
                {
                    "key": "neurosurgery_postop",
                    "label": "脑外科术后",
                    "threshold_type": "map",
                    "threshold": float(cfg.get("map_threshold_neurosurgery", 120)),
                }
            )
        if self._match_name_keywords(text, aorta_kw):
            groups.append(
                {
                    "key": "aortic_disease",
                    "label": "主动脉疾病",
                    "threshold_type": "sbp",
                    "threshold": float(cfg.get("sbp_threshold_aorta", 140)),
                }
            )
        if self._match_name_keywords(text, cad_hf_kw):
            groups.append(
                {
                    "key": "cad_or_hf",
                    "label": "冠心病/心衰",
                    "threshold_type": "hr_or_arrhythmia",
                    "threshold": float(cfg.get("hr_threshold_cad_hf", 130)),
                }
            )
        return groups

    async def _detect_sat_in_progress(self, patient_doc: dict, now: datetime) -> dict | None:
        pid = patient_doc.get("_id")
        if not pid:
            return None

        cfg = self._ecash_cfg()
        sat_window_hours = max(1.0, float(cfg.get("sat_detection_window_hours", 2)))
        recent_sedative_hours = max(sat_window_hours + 1.0, float(cfg.get("sat_recent_sedative_hours", 6)))
        rass_rise_min = float(cfg.get("sat_rass_rise_min", 2))
        baseline_rass_max = float(cfg.get("sat_baseline_rass_max", -3))

        sedative_kw = self._get_cfg_list(
            ("alert_engine", "drug_mapping", "sedatives"),
            ["咪达唑仑", "丙泊酚", "右美托咪定", "地西泮", "劳拉西泮"],
        )
        sat_keywords = self._get_cfg_list(
            ("alert_engine", "ecash", "sat_keywords"),
            ["sat", "唤醒试验", "唤醒测试", "停镇静试验", "daily awakening"],
        )

        sedative_docs = await self._find_recent_drug_docs(pid, sedative_kw, hours=int(recent_sedative_hours + 1), limit=400)
        if not sedative_docs:
            return None

        window_start = now - timedelta(hours=sat_window_hours)
        recent_cutoff = now - timedelta(hours=recent_sedative_hours)

        pre_window_docs = [
            doc for doc in sedative_docs
            if (self._coerce_time(doc.get("_event_time")) or now) >= recent_cutoff
            and (self._coerce_time(doc.get("_event_time")) or now) < window_start
        ]
        current_window_docs = [
            doc for doc in sedative_docs
            if (self._coerce_time(doc.get("_event_time")) or datetime.min) >= window_start
        ]
        sat_events = await self._get_recent_text_events(pid, sat_keywords, hours=max(4, int(sat_window_hours * 3)), limit=200)
        sat_event = None
        for event in sat_events:
            t = self._coerce_time(event.get("time"))
            if isinstance(t, datetime) and t >= now - timedelta(hours=max(4, sat_window_hours * 2)):
                sat_event = event
                break

        rass_series = await self._get_assessment_series(pid, "rass", hours=max(24, int(recent_sedative_hours * 2) + 2))
        valid_rass = []
        for row in rass_series:
            t = self._coerce_time(row.get("time"))
            v = self._to_float(row.get("value"))
            if isinstance(t, datetime) and v is not None:
                valid_rass.append({"time": t, "value": v})
        if len(valid_rass) < 2:
            return None

        baseline_candidates = [row for row in valid_rass if recent_cutoff <= row["time"] < window_start]
        current_candidates = [row for row in valid_rass if row["time"] >= window_start]
        if not current_candidates:
            return None

        baseline = baseline_candidates[-1] if baseline_candidates else None
        if baseline is None:
            prior_rows = [row for row in valid_rass if row["time"] < current_candidates[-1]["time"]]
            baseline = prior_rows[-1] if prior_rows else None
        if baseline is None:
            return None

        latest = current_candidates[-1]
        rass_delta = round(float(latest["value"]) - float(baseline["value"]), 2)
        sedation_paused = bool(pre_window_docs) and not bool(current_window_docs)
        sat_text_hint = sat_event is not None

        if float(baseline["value"]) > baseline_rass_max:
            return None
        if rass_delta < rass_rise_min:
            return None
        if not (sedation_paused or sat_text_hint):
            return None

        started_candidates = [
            self._coerce_time((sat_event or {}).get("time")) if sat_event else None,
            self._coerce_time(current_window_docs[-1].get("_event_time")) if current_window_docs else None,
            window_start,
        ]
        started_at = None
        for candidate in started_candidates:
            if isinstance(candidate, datetime):
                started_at = candidate
                break

        return {
            "in_progress": True,
            "started_at": started_at,
            "baseline_rass": float(baseline["value"]),
            "baseline_time": baseline["time"],
            "latest_rass": float(latest["value"]),
            "latest_time": latest["time"],
            "rass_delta": rass_delta,
            "sedatives_recent": self._dedupe_names(
                [
                    str(doc.get("drugName") or doc.get("orderName") or "").strip()
                    for doc in (pre_window_docs or sedative_docs)
                    if str(doc.get("drugName") or doc.get("orderName") or "").strip()
                ]
            ),
            "sedatives_in_window": self._dedupe_names(
                [
                    str(doc.get("drugName") or doc.get("orderName") or "").strip()
                    for doc in current_window_docs
                    if str(doc.get("drugName") or doc.get("orderName") or "").strip()
                ]
            ),
            "sedation_paused": sedation_paused,
            "sat_text_event": {
                "time": self._coerce_time((sat_event or {}).get("time")),
                "text": " ".join(str((sat_event or {}).get(k) or "") for k in ("code", "strVal", "value")).strip() if sat_event else "",
            } if sat_event else None,
        }

    async def _detect_new_arrhythmia_during_sat(self, pid, now: datetime) -> dict | None:
        pid_str = str(pid or "")
        if not pid_str:
            return None

        stress_cfg = self._sat_stress_cfg()
        adv_cfg = self.config.yaml_cfg.get("alert_engine", {}).get("vital_signs_advanced", {})
        arrhythmia_keywords = self._get_cfg_list(
            ("alert_engine", "ecash", "sat_stress", "arrhythmia_keywords"),
            ["房颤", "房扑", "arrhythmia", "irregular", "室速", "室早", "心律失常"],
        )
        rhythm_codes = adv_cfg.get("rhythm_codes", ["param_xinLvLv", "rhythm_type", "param_rhythm_type", "arrhythmia_flag", "param_arrhythmia_flag"])
        arrhythmia_flag_codes = {str(x).strip().lower() for x in adv_cfg.get("arrhythmia_flag_codes", ["arrhythmia_flag", "param_arrhythmia_flag"])}
        lookback_hours = max(6, int(stress_cfg.get("arrhythmia_lookback_hours", 6)))
        recent_hours = max(2, int(stress_cfg.get("arrhythmia_recent_hours", 2)))
        prior_quiet_hours = max(2, int(stress_cfg.get("arrhythmia_prior_quiet_hours", 4)))
        since = now - timedelta(hours=lookback_hours)

        docs: list[dict] = []
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}, "code": {"$in": rhythm_codes}},
            {"time": 1, "code": 1, "strVal": 1, "value": 1, "fVal": 1, "intVal": 1},
        ).sort("time", 1).limit(400)
        docs = [doc async for doc in cursor]
        if not docs:
            device_id = await self._get_device_id(pid, ["monitor"])
            if device_id:
                cursor = self.db.col("deviceCap").find(
                    {"deviceID": device_id, "time": {"$gte": since}, "code": {"$in": rhythm_codes}},
                    {"time": 1, "code": 1, "strVal": 1, "value": 1, "fVal": 1, "intVal": 1},
                ).sort("time", 1).limit(400)
                docs = [doc async for doc in cursor]
        if not docs:
            return None

        points: list[dict] = []
        for doc in docs:
            t = self._coerce_time(doc.get("time"))
            if not isinstance(t, datetime):
                continue
            code = str(doc.get("code") or "").strip().lower()
            raw_text = " ".join(str(doc.get(k) or "") for k in ("strVal", "value", "code")).strip()
            text = raw_text.lower()
            irregular = self._match_name_keywords(text, arrhythmia_keywords)
            if (not irregular) and code in arrhythmia_flag_codes:
                numeric_flag = self._to_float(doc.get("fVal"))
                if numeric_flag is None:
                    numeric_flag = self._to_float(doc.get("intVal"))
                if numeric_flag is None:
                    numeric_flag = self._to_float(doc.get("value"))
                irregular = numeric_flag is not None and numeric_flag > 0
            points.append({"time": t, "text": raw_text, "irregular": irregular})

        recent_cutoff = now - timedelta(hours=recent_hours)
        recent_irregular = [p for p in points if p.get("irregular") and p["time"] >= recent_cutoff]
        if not recent_irregular:
            return None

        first_recent = recent_irregular[0]
        quiet_since = first_recent["time"] - timedelta(hours=prior_quiet_hours)
        had_prior_irregular = any(p.get("irregular") and quiet_since <= p["time"] < first_recent["time"] for p in points)
        if had_prior_irregular:
            return None

        latest = recent_irregular[-1]
        return {
            "time": latest["time"],
            "text": latest["text"],
            "first_detected_at": first_recent["time"],
        }

    async def _detect_sat_stress_reaction(self, patient_doc: dict, now: datetime) -> dict | None:
        pid = patient_doc.get("_id")
        if not pid:
            return None

        sat_state = await self._detect_sat_in_progress(patient_doc, now)
        if not sat_state:
            return None

        risk_groups = self._sat_risk_groups(patient_doc)
        if not risk_groups:
            return None

        vitals = await self._get_latest_vitals_by_patient(pid)
        hr = self._to_float(vitals.get("hr"))
        map_value = self._to_float(vitals.get("map"))
        sbp = self._to_float(vitals.get("sbp"))
        arrhythmia = await self._detect_new_arrhythmia_during_sat(pid, now)

        matched_signals: list[str] = []
        matched_groups: list[str] = []
        primary_group = None

        for group in risk_groups:
            key = group.get("key")
            label = group.get("label") or key
            threshold = float(group.get("threshold") or 0)
            if key == "neurosurgery_postop" and map_value is not None and map_value > threshold:
                matched_groups.append(str(key))
                matched_signals.append(f"{label}，MAP {round(map_value, 1)} mmHg > {round(threshold, 1)}")
                primary_group = primary_group or key
            elif key == "aortic_disease" and sbp is not None and sbp > threshold:
                matched_groups.append(str(key))
                matched_signals.append(f"{label}，SBP {round(sbp, 1)} mmHg > {round(threshold, 1)}")
                primary_group = primary_group or key
            elif key == "cad_or_hf":
                if hr is not None and hr > threshold:
                    matched_groups.append(str(key))
                    matched_signals.append(f"{label}，HR {round(hr, 1)} 次/分 > {round(threshold, 1)}")
                    primary_group = primary_group or key
                elif arrhythmia:
                    matched_groups.append(str(key))
                    matched_signals.append(f"{label}，SAT期间新发心律失常：{arrhythmia.get('text') or '监护提示异常'}")
                    primary_group = primary_group or key

        if not matched_signals:
            return None

        evidence = [f"SAT中 RASS {sat_state.get('baseline_rass')}→{sat_state.get('latest_rass')}"]
        evidence.extend(matched_signals[:3])
        suggestion = "建议暂停SAT、恢复镇静，并立即排查疼痛、躁动、缺氧、尿潴留等诱因。"
        explanation = await self._polish_structured_alert_explanation(
            {
                "summary": "SAT期间出现血流动力学/心律应激反应，存在安全风险。",
                "evidence": evidence,
                "suggestion": suggestion,
                "text": "",
            }
        )

        return {
            "rule_id": "ECASH_SAT_STRESS_REACTION",
            "name": "SAT期间应激反应过度",
            "category": "bundle",
            "alert_type": "ecash_sat_stress_reaction",
            "severity": "critical",
            "parameter": "sat_stress",
            "condition": {"sat_in_progress": True, "matched_groups": matched_groups},
            "value": len(matched_signals),
            "source_time": vitals.get("time") or sat_state.get("latest_time") or now,
            "extra": {
                "sat_window": sat_state,
                "risk_group": primary_group,
                "risk_groups": matched_groups,
                "matched_signals": matched_signals,
                "map": map_value,
                "sbp": sbp,
                "hr": hr,
                "rhythm": (arrhythmia or {}).get("text") if arrhythmia else None,
                "new_arrhythmia": arrhythmia,
                "suggestion": "建议恢复镇静并排查原因",
            },
            "explanation": explanation,
        }

    async def get_ecash_status(self, patient_doc: dict) -> dict:
        pid = patient_doc.get("_id")
        now = datetime.now()
        if not pid:
            empty = {
                "analgesia": {},
                "sedation": {},
                "delirium": {},
                "composite_status": "red",
                "updated_at": now,
            }
            return empty

        cfg = self._ecash_cfg()
        target_range = cfg.get("target_rass_range", [-2, 0])
        if not isinstance(target_range, list) or len(target_range) != 2:
            target_range = [-2, 0]
        target_low = float(target_range[0])
        target_high = float(target_range[1])

        analgesic_kw = self._get_cfg_list(
            ("alert_engine", "ecash", "analgesic_keywords"),
            ["芬太尼", "瑞芬太尼", "舒芬太尼", "吗啡", "布洛芬", "对乙酰氨基酚", "氟比洛芬", "帕瑞昔布", "曲马多", "氯胺酮"],
        )
        sedative_kw = self._get_cfg_list(
            ("alert_engine", "drug_mapping", "sedatives"),
            ["咪达唑仑", "丙泊酚", "右美托咪定", "地西泮", "劳拉西泮"],
        )
        benzo_kw = self._get_cfg_list(
            ("alert_engine", "ecash", "benzo_keywords"),
            ["咪达唑仑", "地西泮", "劳拉西泮", "阿普唑仑", "艾司唑仑", "氯硝西泮"],
        )
        preferred_sedatives = self._get_cfg_list(
            ("alert_engine", "ecash", "preferred_sedative_keywords"),
            ["丙泊酚", "右美托咪定"],
        )
        sat_keywords = self._get_cfg_list(
            ("alert_engine", "ecash", "sat_keywords"),
            ["sat", "唤醒试验", "唤醒测试", "停镇静试验", "daily awakening"],
        )

        recent_drugs = self._dedupe_names(await self._get_recent_drugs(pid, hours=24))
        current_analgesics = [x for x in recent_drugs if self._match_name_keywords(x, analgesic_kw)]
        current_sedatives = [x for x in recent_drugs if self._match_name_keywords(x, sedative_kw)]
        benzo_drugs = [x for x in current_sedatives if self._match_name_keywords(x, benzo_kw)]
        preferred_drugs = [x for x in current_sedatives if self._match_name_keywords(x, preferred_sedatives)]

        # Analgesia
        latest_cpot = await self._latest_assessment_entry(pid, "cpot", hours=48)
        latest_bps = await self._latest_assessment_entry(pid, "bps", hours=48)
        latest_pain = await self._latest_assessment_entry(pid, "pain", hours=48)
        analgesia_entry = None
        tool = None
        if latest_cpot and (not latest_bps or latest_cpot["time"] >= latest_bps["time"]):
            analgesia_entry = latest_cpot
            tool = "CPOT"
        elif latest_bps:
            analgesia_entry = latest_bps
            tool = "BPS"
        elif latest_pain:
            analgesia_entry = latest_pain
            tool = "NRS"

        latest_pain_score = float(analgesia_entry["value"]) if analgesia_entry else None
        pain_hours = self._hours_ago(analgesia_entry["time"], now) if analgesia_entry else None
        pain_controlled, pain_severe = self._pain_control_flags(tool, latest_pain_score)
        if pain_hours is None or pain_hours > 8 or pain_severe:
            analgesia_status = "red"
        elif (pain_hours is not None and pain_hours > 4) or not pain_controlled:
            analgesia_status = "yellow"
        else:
            analgesia_status = "green"

        analgesia_suggestion = None
        if pain_hours is None or pain_hours > 8:
            analgesia_suggestion = "建议立即完成疼痛评估并记录 CPOT/BPS。"
        elif not pain_controlled:
            analgesia_suggestion = "建议评估镇痛方案，考虑多模式镇痛。"

        analgesia = {
            "status": analgesia_status,
            "latest_score": latest_pain_score,
            "tool": tool,
            "last_assessed_hours_ago": pain_hours,
            "pain_controlled": bool(pain_controlled) if latest_pain_score is not None else False,
            "current_analgesics": current_analgesics,
            "suggestion": analgesia_suggestion,
        }

        # Sedation
        latest_rass = await self._get_latest_assessment(pid, "rass")
        rass_series = await self._get_assessment_series(pid, "rass", hours=48)
        latest_rass_time = rass_series[-1]["time"] if rass_series else None
        within_target = latest_rass is not None and target_low <= float(latest_rass) <= target_high
        over_sedation = await self._is_over_sedated(pid, target_low, hours=24)
        sat_hours = await self._latest_event_hours(pid, sat_keywords, lookback_hours=72)
        sat_due = bool(current_sedatives) and (sat_hours is None or sat_hours > 24)
        off_target_gap = self._sedation_off_target_gap(float(latest_rass) if latest_rass is not None else None, target_low, target_high)

        if over_sedation or (benzo_drugs and not within_target):
            sedation_status = "red"
        elif latest_rass is None:
            sedation_status = "yellow"
        elif within_target and (preferred_drugs or not current_sedatives):
            sedation_status = "green"
        elif (off_target_gap is not None and off_target_gap <= 1) or (benzo_drugs and within_target):
            sedation_status = "yellow"
        else:
            sedation_status = "red" if off_target_gap is not None and off_target_gap >= 2 else "yellow"

        sedation_suggestion = None
        if over_sedation:
            sedation_suggestion = "建议减量或SAT。"
        elif latest_rass is not None and not within_target:
            sedation_suggestion = "建议评估镇静深度。"
        elif benzo_drugs:
            sedation_suggestion = "指南推荐首选丙泊酚或右美托咪定。"
        elif sat_due:
            sedation_suggestion = "建议安排每日唤醒试验(SAT)。"

        sedation = {
            "status": sedation_status,
            "latest_rass": float(latest_rass) if latest_rass is not None else None,
            "target_rass_range": [target_low, target_high],
            "within_target": bool(within_target),
            "over_sedation": bool(over_sedation),
            "current_sedatives": current_sedatives,
            "sat_due": sat_due,
            "sat_last_performed_hours_ago": sat_hours,
            "suggestion": sedation_suggestion,
        }

        # Delirium
        cam_status = await self._get_latest_cam_icu_status(pid, lookback_hours=48)
        cam_positive = cam_status.get("positive") if cam_status else None
        cam_hours = self._hours_ago(cam_status.get("time"), now) if cam_status else None
        delirium_risk_score = await self._calc_delirium_risk_score(patient_doc, pid)
        delirium_cfg = self.config.yaml_cfg.get("alert_engine", {}).get("delirium_risk", {})
        warning_score = float(delirium_cfg.get("warning_score", 4))

        if cam_positive is True or cam_hours is None or cam_hours > 24:
            delirium_status = "red"
        elif (cam_hours is not None and 12 < cam_hours <= 24) or (delirium_risk_score is not None and delirium_risk_score >= warning_score):
            delirium_status = "yellow"
        else:
            delirium_status = "green"

        delirium_suggestion = None
        if cam_positive is True:
            delirium_suggestion = "CAM-ICU阳性，建议启动非药物谵妄干预并复评诱因。"
        elif cam_hours is None or cam_hours > 24:
            delirium_suggestion = "建议尽快完成 CAM-ICU 评估。"
        elif delirium_risk_score is not None and delirium_risk_score >= warning_score:
            delirium_suggestion = "存在谵妄高风险，建议加强昼夜节律与早期活动管理。"

        delirium = {
            "status": delirium_status,
            "cam_icu_positive": cam_positive,
            "cam_icu_last_assessed_hours_ago": cam_hours,
            "risk_score": delirium_risk_score,
            "suggestion": delirium_suggestion,
        }

        return {
            "analgesia": analgesia,
            "sedation": sedation,
            "delirium": delirium,
            "composite_status": self._worst_status(analgesia_status, sedation_status, delirium_status),
            "updated_at": now,
        }

    async def scan_ecash_bundle(self) -> None:
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
                "admissionType": 1,
                "admitType": 1,
                "inType": 1,
                "admissionSource": 1,
                "admissionWay": 1,
                "source": 1,
                "age": 1,
                "hisAge": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "diagnosis": 1,
                "history": 1,
                "diagnosisHistory": 1,
                "surgeryHistory": 1,
                "remark": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            status = await self.get_ecash_status(patient_doc)
            analgesia = status.get("analgesia") or {}
            sedation = status.get("sedation") or {}
            delirium = status.get("delirium") or {}

            # 1. 疼痛评估过期
            pain_hours = analgesia.get("last_assessed_hours_ago")
            if analgesia.get("status") == "red" and pain_hours is not None and float(pain_hours) > 8:
                rule_id = "ECASH_PAIN_ASSESSMENT_OVERDUE"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="疼痛评估超时(>8h)",
                        category="bundle",
                        alert_type="ecash_pain_overdue",
                        severity="warning",
                        parameter="pain_assessment_interval",
                        condition={"operator": ">", "hours": 8},
                        value=float(pain_hours),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=status.get("updated_at"),
                        extra={"analgesia": analgesia},
                    )
                    if alert:
                        triggered += 1

            # 2. 疼痛控制不佳
            if analgesia.get("latest_score") is not None and analgesia.get("pain_controlled") is False:
                rule_id = "ECASH_PAIN_UNCONTROLLED"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="疼痛控制不佳(CPOT≥3/BPS≥5)",
                        category="bundle",
                        alert_type="ecash_pain_uncontrolled",
                        severity="high",
                        parameter="pain_score",
                        condition={"tool": analgesia.get("tool")},
                        value=float(analgesia.get("latest_score")),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=status.get("updated_at"),
                        extra={
                            "current_analgesics": analgesia.get("current_analgesics") or [],
                            "suggestion": "建议评估镇痛方案，考虑多模式镇痛",
                            "analgesia": analgesia,
                        },
                    )
                    if alert:
                        triggered += 1

            # 3. RASS 偏离目标
            latest_rass = sedation.get("latest_rass")
            target_range = sedation.get("target_rass_range") or [-2, 0]
            if latest_rass is not None and sedation.get("within_target") is False:
                target_low = float(target_range[0])
                target_high = float(target_range[1])
                gap = self._sedation_off_target_gap(float(latest_rass), target_low, target_high) or 0.0
                severity = "warning" if gap <= 1 else "high"
                rule_id = "ECASH_RASS_OFF_TARGET"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    over_sedation = bool(sedation.get("over_sedation"))
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="RASS偏离目标范围",
                        category="bundle",
                        alert_type="ecash_rass_off_target",
                        severity=severity,
                        parameter="rass",
                        condition={"target_range": target_range},
                        value=float(latest_rass),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=status.get("updated_at"),
                        extra={
                            "latest_rass": latest_rass,
                            "target_range": target_range,
                            "current_sedatives": sedation.get("current_sedatives") or [],
                            "suggestion": "建议减量或SAT" if over_sedation else "建议评估镇静深度",
                        },
                    )
                    if alert:
                        triggered += 1

            # 4. SAT 提醒
            if sedation.get("current_sedatives") and sedation.get("sat_due"):
                rule_id = "ECASH_SAT_DUE"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="每日唤醒试验(SAT)未执行",
                        category="bundle",
                        alert_type="ecash_sat_due",
                        severity="warning",
                        parameter="sat_interval",
                        condition={"operator": ">", "hours": 24},
                        value=float(sedation.get("sat_last_performed_hours_ago") or 999),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=status.get("updated_at"),
                        extra={
                            "sedatives_in_use": sedation.get("current_sedatives") or [],
                            "last_sat_hours_ago": sedation.get("sat_last_performed_hours_ago"),
                        },
                    )
                    if alert:
                        triggered += 1

            # 5. 苯二氮卓使用警示
            benzo_kw = self._get_cfg_list(
                ("alert_engine", "ecash", "benzo_keywords"),
                ["咪达唑仑", "地西泮", "劳拉西泮", "阿普唑仑", "艾司唑仑", "氯硝西泮"],
            )
            benzo_drugs = [x for x in (sedation.get("current_sedatives") or []) if self._match_name_keywords(x, benzo_kw)]
            if benzo_drugs:
                rule_id = "ECASH_BENZO_IN_USE"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="苯二氮卓类镇静（谵妄风险增加）",
                        category="bundle",
                        alert_type="ecash_benzo_in_use",
                        severity="warning",
                        parameter="sedative_choice",
                        condition={"contains_benzo": True},
                        value=len(benzo_drugs),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=status.get("updated_at"),
                        extra={
                            "benzo_drugs": benzo_drugs,
                            "suggestion": "指南推荐首选丙泊酚或右美托咪定",
                        },
                    )
                    if alert:
                        triggered += 1

            # 6. SAT窗口期应激反应过度
            sat_stress = await self._detect_sat_stress_reaction(patient_doc, status.get("updated_at") or datetime.now())
            if sat_stress:
                rule_id = str(sat_stress.get("rule_id") or "ECASH_SAT_STRESS_REACTION")
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name=str(sat_stress.get("name") or "SAT期间应激反应过度"),
                        category=str(sat_stress.get("category") or "bundle"),
                        alert_type=str(sat_stress.get("alert_type") or "ecash_sat_stress_reaction"),
                        severity=str(sat_stress.get("severity") or "critical"),
                        parameter=str(sat_stress.get("parameter") or "sat_stress"),
                        condition=sat_stress.get("condition") or {"sat_in_progress": True},
                        value=sat_stress.get("value"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=sat_stress.get("source_time") or status.get("updated_at"),
                        extra=sat_stress.get("extra"),
                        explanation=sat_stress.get("explanation"),
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self._log_info("eCASH", triggered)
