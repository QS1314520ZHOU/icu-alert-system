"""呼吸机撤离筛查 / 困难脱机研判 / 拔管后追踪。"""
from __future__ import annotations

from datetime import datetime, timedelta
import re
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


class VentilatorMixin:
    def _is_sbt_code(self, code: Any) -> bool:
        text = str(code or "").strip().lower()
        if not text:
            return False
        exact = {
            "param_sbt",
            "param_sbt_result",
            "param_vent_sbt",
            "param_vent_sbt_result",
            "sbt",
            "sbt_result",
            "weaning_sbt",
            "weaning_sbt_result",
            "自主呼吸试验",
            "自主呼吸试验结果",
            "sbt结果",
        }
        if text in exact:
            return True
        return any(k in text for k in ["sbt", "自主呼吸试验", "spontaneous breathing", "撤机试验"])

    def _parse_sbt_result_text(self, value: Any) -> tuple[str | None, bool | None]:
        text = str(value or "").strip().lower()
        if not text:
            return None, None
        positive_kw = ["通过", "成功", "耐受", "passed", "pass", "success", "tolerated", "yes", "阳性可耐受"]
        negative_kw = ["失败", "不通过", "failed", "终止", "耐受差", "unable", "abort", "intolerant"]
        if any(k in text for k in negative_kw):
            return "failed", False
        if any(k in text for k in positive_kw):
            return "passed", True
        if text in {"1", "true"}:
            return "passed", True
        if text in {"0", "false"}:
            return "failed", False
        return "documented", None

    def _parse_sbt_duration_minutes(self, text: str) -> float | None:
        raw = str(text or "")
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:min|mins|minute|分钟)", raw, re.I)
        if m:
            try:
                return round(float(m.group(1)), 1)
            except Exception:
                return None
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|小时)", raw, re.I)
        if m:
            try:
                return round(float(m.group(1)) * 60.0, 1)
            except Exception:
                return None
        return None

    async def _persist_sbt_assessment(
        self,
        *,
        pid_str: str,
        patient_doc: dict,
        now: datetime,
        sbt: dict,
    ) -> None:
        trial_time = _parse_dt(sbt.get("time")) or now
        payload = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "sbt_assessment",
            "result": sbt.get("result"),
            "passed": sbt.get("passed"),
            "trial_time": trial_time,
            "calc_time": trial_time,
            "source": sbt.get("source"),
            "source_code": sbt.get("code"),
            "raw_text": sbt.get("text"),
            "duration_minutes": sbt.get("duration_minutes"),
            "rr": sbt.get("rr"),
            "vte_ml": sbt.get("vte_ml"),
            "rsbi": sbt.get("rsbi"),
            "fio2": sbt.get("fio2"),
            "peep": sbt.get("peep"),
            "minute_vent": sbt.get("minute_vent"),
            "created_at": now,
            "updated_at": now,
            "month": trial_time.strftime("%Y-%m"),
            "day": trial_time.strftime("%Y-%m-%d"),
        }
        existing = await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "sbt_assessment",
                "trial_time": trial_time,
            }
        )
        if existing:
            await self.db.col("score_records").update_one(
                {"_id": existing["_id"]},
                {"$set": {k: v for k, v in payload.items() if k not in {"created_at"}}},
            )
        else:
            await self.db.col("score_records").insert_one(payload)

    async def _persist_weaning_assessment(
        self,
        *,
        pid_str: str,
        patient_doc: dict,
        now: datetime,
        assessment: dict,
    ) -> None:
        extra = assessment.get("extra") or {}
        payload = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "weaning_assessment",
            "score": assessment.get("risk_score"),
            "risk_score": assessment.get("risk_score"),
            "risk_level": assessment.get("risk_level"),
            "severity": assessment.get("severity"),
            "recommendation": assessment.get("recommendation"),
            "factors": extra.get("factors") or assessment.get("factors") or [],
            "pf_ratio": extra.get("pf_ratio"),
            "fio2": extra.get("fio2"),
            "peep": extra.get("peep"),
            "rsbi": extra.get("rsbi"),
            "rr": extra.get("rr"),
            "vte_ml": extra.get("vte_ml"),
            "map": extra.get("map"),
            "rass": extra.get("rass"),
            "gcs": extra.get("gcs"),
            "on_vasopressor": extra.get("on_vasopressor"),
            "fluid_overload_pct": extra.get("fluid_overload_pct"),
            "ventilation_days": extra.get("ventilation_days"),
            "previous_sbt": extra.get("previous_sbt"),
            "gate_failures": extra.get("gate_failures") or [],
            "calc_time": now,
            "created_at": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        latest = await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "weaning_assessment",
                "calc_time": {"$gte": now - timedelta(minutes=20)},
            },
            sort=[("calc_time", -1)],
        )
        if latest:
            await self.db.col("score_records").update_one(
                {"_id": latest["_id"]},
                {"$set": {k: v for k, v in payload.items() if k not in {"created_at"}}},
            )
        else:
            await self.db.col("score_records").insert_one(payload)

    def _patient_height_cm(self, patient_doc: dict) -> float | None:
        for key in ("height", "heightCm", "height_cm", "bodyHeight"):
            value = patient_doc.get(key)
            try:
                num = float(value)
            except Exception:
                continue
            if 100 <= num <= 230:
                return num
        return None

    def _predicted_body_weight(self, patient_doc: dict) -> float | None:
        height_cm = self._patient_height_cm(patient_doc)
        if height_cm is None:
            return None
        sex_text = str(patient_doc.get("gender") or patient_doc.get("hisSex") or "").lower()
        female = any(k in sex_text for k in ["female", "女", "f"])
        base = 45.5 if female else 50.0
        return round(base + 0.91 * (height_cm - 152.4), 2)

    def _weaning_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("weaning_assistant", {})
        return cfg if isinstance(cfg, dict) else {}

    def _risk_level(self, score: float, warning: float, high: float, critical: float) -> str | None:
        if score >= critical:
            return "critical"
        if score >= high:
            return "high"
        if score >= warning:
            return "warning"
        return None

    def _vent_bind_is_vent(self, bind_doc: dict) -> bool:
        t = str(bind_doc.get("type") or "").lower()
        return any(k in t for k in ["vent", "ventilator", "呼吸"])

    async def _get_active_vent_bind(self, pid_str: str) -> dict | None:
        cursor = self.db.col("deviceBind").find(
            {"pid": pid_str, "unBindTime": None},
            {"type": 1, "bindTime": 1, "deviceID": 1, "unBindTime": 1},
        ).sort("bindTime", -1).limit(20)
        async for doc in cursor:
            if self._vent_bind_is_vent(doc):
                return doc
        return None

    async def _get_recent_extubation_bind(self, pid_str: str, now: datetime, hours: int = 48) -> dict | None:
        since = now - timedelta(hours=max(1, hours))
        cursor = self.db.col("deviceBind").find(
            {"pid": pid_str, "unBindTime": {"$gte": since}},
            {"type": 1, "bindTime": 1, "deviceID": 1, "unBindTime": 1},
        ).sort("unBindTime", -1).limit(20)
        async for doc in cursor:
            if self._vent_bind_is_vent(doc):
                return doc
        return None

    async def _get_current_ventilation_days(self, pid_str: str, now: datetime) -> float:
        bind = await self._get_active_vent_bind(pid_str)
        bind_time = _parse_dt(bind.get("bindTime")) if bind else None
        if not isinstance(bind_time, datetime):
            return 0.0
        return round(max(0.0, (now - bind_time).total_seconds() / 86400.0), 2)

    async def _get_pf_snapshot(self, his_pid: str | None, cap: dict | None, now: datetime) -> dict:
        fio2 = self._vent_param(cap or {}, "fio2", "param_FiO2") if cap else None
        fio2_frac = None
        if fio2 is not None:
            fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
        if not his_pid or not fio2_frac or fio2_frac <= 0:
            return {"pf_ratio": None, "trend": None, "latest_pao2": None, "baseline_pao2": None, "fio2_fraction": fio2_frac}

        series = await self._get_lab_series(his_pid, "pao2", now - timedelta(hours=24), limit=80)
        if not series:
            return {"pf_ratio": None, "trend": None, "latest_pao2": None, "baseline_pao2": None, "fio2_fraction": fio2_frac}

        latest_pao2 = series[-1].get("value")
        baseline_pao2 = series[0].get("value")
        pf_ratio = round(float(latest_pao2) / float(fio2_frac), 1) if latest_pao2 is not None else None
        baseline_pf = round(float(baseline_pao2) / float(fio2_frac), 1) if baseline_pao2 is not None else None
        trend = None
        if pf_ratio is not None and baseline_pf is not None:
            delta = pf_ratio - baseline_pf
            if delta >= 20:
                trend = "improving"
            elif delta <= -20:
                trend = "worsening"
            else:
                trend = "stable"
        return {
            "pf_ratio": pf_ratio,
            "baseline_pf_ratio": baseline_pf,
            "trend": trend,
            "latest_pao2": latest_pao2,
            "baseline_pao2": baseline_pao2,
            "fio2_fraction": fio2_frac,
        }

    def _calc_rsbi(self, rr: float | None, vte_ml: float | None) -> float | None:
        if rr is None or vte_ml is None or vte_ml <= 0:
            return None
        vt_l = float(vte_ml) / 1000.0
        if vt_l <= 0:
            return None
        return round(float(rr) / vt_l, 1)

    async def _get_recent_fluid_overload_pct(self, pid_str: str, patient_doc: dict, now: datetime, hours: int = 24) -> float | None:
        if not hasattr(self, "_collect_intake_events"):
            return None
        weight_kg = self._get_patient_weight(patient_doc)
        if not weight_kg:
            return None
        since = now - timedelta(hours=max(6, hours))
        intake = await self._collect_intake_events(pid_str, since)
        output = await self._collect_output_events(pid_str, since)
        net = self._sum_window(intake, hours, now) - self._sum_window(output, hours, now)
        return round((float(net) / (float(weight_kg) * 1000.0)) * 100.0, 2)

    async def _get_bnp_trend(self, his_pid: str | None, now: datetime, hours: int = 72) -> dict:
        if not his_pid:
            return {"latest": None, "baseline": None, "ratio": None, "trend": None}
        series = await self._get_lab_series(his_pid, "bnp", now - timedelta(hours=max(24, hours)), limit=60)
        if not series:
            return {"latest": None, "baseline": None, "ratio": None, "trend": None}
        latest = series[-1].get("value")
        baseline = min(float(row.get("value")) for row in series if row.get("value") is not None)
        ratio = round(float(latest) / float(baseline), 2) if latest not in (None, 0) and baseline not in (None, 0) else None
        trend = None
        if ratio is not None:
            if ratio >= 1.5:
                trend = "up"
            elif ratio <= 0.8:
                trend = "down"
            else:
                trend = "stable"
        return {"latest": latest, "baseline": baseline, "ratio": ratio, "trend": trend}

    async def _get_recent_sbt_result(self, pid, now: datetime, hours: int = 72) -> dict | None:
        pid_str = str(pid)
        since = now - timedelta(hours=max(24, hours))

        recorded = await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "sbt_assessment",
                "trial_time": {"$gte": since},
            },
            sort=[("trial_time", -1)],
        )
        if recorded:
            return {
                "result": recorded.get("result"),
                "passed": recorded.get("passed"),
                "time": recorded.get("trial_time") or recorded.get("calc_time"),
                "text": recorded.get("raw_text"),
                "source": recorded.get("source") or "score_records",
                "code": recorded.get("source_code"),
                "duration_minutes": recorded.get("duration_minutes"),
                "rr": recorded.get("rr"),
                "vte_ml": recorded.get("vte_ml"),
                "rsbi": recorded.get("rsbi"),
                "fio2": recorded.get("fio2"),
                "peep": recorded.get("peep"),
                "minute_vent": recorded.get("minute_vent"),
            }

        score_doc = await self.db.col("score").find_one(
            {
                "pid": pid_str,
                "time": {"$gte": since},
                "$or": [
                    {"scoreType": {"$regex": "sbt|spontaneous|自主呼吸试验|撤机试验", "$options": "i"}},
                    {"name": {"$regex": "sbt|spontaneous|自主呼吸试验|撤机试验", "$options": "i"}},
                ],
            },
            sort=[("time", -1)],
        )
        if score_doc:
            raw = score_doc.get("result") or score_doc.get("score") or score_doc.get("total") or score_doc.get("value")
            result, passed = self._parse_sbt_result_text(raw)
            return {
                "result": result,
                "passed": passed,
                "time": score_doc.get("time"),
                "text": str(raw or ""),
                "source": "score",
                "code": score_doc.get("scoreType") or score_doc.get("name"),
            }

        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "code": 1, "strVal": 1, "value": 1},
        ).sort("time", -1).limit(500)
        exact_docs: list[dict] = []
        async for doc in cursor:
            if self._is_sbt_code(doc.get("code")):
                exact_docs.append(doc)
        for doc in exact_docs:
            raw = doc.get("strVal")
            if raw in (None, ""):
                raw = doc.get("value")
            result, passed = self._parse_sbt_result_text(raw)
            if result:
                return {
                    "result": result,
                    "passed": passed,
                    "time": doc.get("time"),
                    "text": str(raw or ""),
                    "source": "bedside_exact",
                    "code": doc.get("code"),
                    "duration_minutes": self._parse_sbt_duration_minutes(str(raw or "")),
                }

        keywords = ["sbt", "自主呼吸试验", "spontaneous breathing", "撤机试验"]
        docs = await self._get_recent_text_events(pid, keywords, hours=max(24, hours), limit=400)
        if not docs:
            return None
        for doc in docs:
            text = " ".join(str(doc.get(k) or "") for k in ("code", "strVal", "value"))
            result, passed = self._parse_sbt_result_text(text)
            if result:
                return {
                    "result": result,
                    "passed": passed,
                    "time": doc.get("time"),
                    "text": text,
                    "source": "bedside_text",
                    "code": doc.get("code"),
                    "duration_minutes": self._parse_sbt_duration_minutes(text),
                }
        return None

    async def _get_accessory_muscle_sign(self, pid, now: datetime, hours: int = 12) -> dict | None:
        keywords = ["辅助呼吸肌", "呼吸肌动用", "三凹征", "鼻翼扇动", "耸肩呼吸", "胸锁乳突肌"]
        docs = await self._get_recent_text_events(pid, keywords, hours=max(6, hours), limit=200)
        if not docs:
            return None
        negative_kw = ["无", "未见", "否认"]
        for doc in docs:
            text = " ".join(str(doc.get(k) or "") for k in ("code", "strVal", "value")).lower()
            if any(k in text for k in negative_kw):
                continue
            return {"present": True, "time": doc.get("time"), "text": text}
        return None

    async def _build_weaning_recommendation(
        self,
        *,
        patient_doc: dict,
        pid_str: str,
        cap: dict,
        now: datetime,
    ) -> dict | None:
        cfg = self._weaning_cfg()
        weights = cfg.get("factor_weights", {}) if isinstance(cfg.get("factor_weights"), dict) else {}
        warning_score = float(cfg.get("warning_score", 4))
        high_score = float(cfg.get("high_score", 7))
        critical_score = float(cfg.get("critical_score", 9))

        pid = patient_doc.get("_id")
        his_pid = patient_doc.get("hisPid")
        if not pid:
            return None
        pid_str = str(pid)
        vent_days = await self._get_current_ventilation_days(pid_str, now)
        fio2 = self._vent_param(cap, "fio2", "param_FiO2")
        peep = self._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
        rr = self._vent_param_priority(cap, ["rr_measured", "rr_set"], ["param_vent_resp", "param_HuXiPinLv"])
        vte = self._vent_param_priority(cap, ["vte", "vt_set"], ["param_vent_vt", "param_vent_set_vt"])
        rsbi = self._calc_rsbi(rr, vte)
        latest_rass = await self._get_latest_assessment(pid, "rass")
        gcs = await self._get_latest_assessment(pid, "gcs")
        monitor_vitals = await self._get_latest_vitals_by_patient(pid)
        map_value = monitor_vitals.get("map") if isinstance(monitor_vitals, dict) else None
        on_vaso = await self._has_vasopressor(pid)
        pf = await self._get_pf_snapshot(his_pid, cap, now)
        fluid_pct = await self._get_recent_fluid_overload_pct(pid_str, patient_doc, now, hours=24)
        bnp = await self._get_bnp_trend(his_pid, now, hours=72)
        sbt_result = await self._get_recent_sbt_result(pid, now, hours=72)
        if isinstance(sbt_result, dict):
            sbt_result = {
                **sbt_result,
                "rr": sbt_result.get("rr", rr),
                "vte_ml": sbt_result.get("vte_ml", vte),
                "rsbi": sbt_result.get("rsbi", rsbi),
                "fio2": sbt_result.get("fio2", fio2),
                "peep": sbt_result.get("peep", peep),
            }

        score = 0.0
        factors: list[dict] = []
        suggestions: list[str] = []

        def add_factor(key: str, matched: bool, evidence: str, default_weight: float, suggestion: str | None = None) -> None:
            nonlocal score
            if not matched:
                return
            w = float(weights.get(key, default_weight))
            score += w
            factors.append({"factor": key, "weight": w, "evidence": evidence})
            if suggestion:
                suggestions.append(suggestion)

        add_factor("vent_days_ge_5", vent_days >= float(cfg.get("vent_days_warning", 5)), f"机械通气 {vent_days} 天", 1, None)
        add_factor("vent_days_ge_7", vent_days >= float(cfg.get("vent_days_high", 7)), f"长程机械通气 {vent_days} 天", 2, None)

        pf_ratio = pf.get("pf_ratio")
        add_factor("pf_lt_200", pf_ratio is not None and pf_ratio < float(cfg.get("pf_warning", 200)), f"P/F {pf_ratio}", 2, "先优化氧合/肺水肿后再试 SBT")
        add_factor("pf_lt_150", pf_ratio is not None and pf_ratio < float(cfg.get("pf_high", 150)), f"重度氧合受损 P/F {pf_ratio}", 3, "当前不宜脱机，先处理氧合问题")
        add_factor("pf_worsening", pf.get("trend") == "worsening", f"P/F 趋势下降 {pf.get('baseline_pf_ratio')}→{pf_ratio}", 1, "请先复查肺部影像、分泌物与液体负荷")

        add_factor("rsbi_ge_80", rsbi is not None and rsbi >= float(cfg.get("rsbi_warning", 80)), f"RSBI {rsbi}", 2, "建议先降低呼吸负荷/优化肌力后再试 SBT")
        add_factor("rsbi_ge_105", rsbi is not None and rsbi >= float(cfg.get("rsbi_high", 105)), f"高 RSBI {rsbi}", 3, "当前脱机失败风险高，暂不建议拔管")

        add_factor("rass_outside_target", latest_rass is not None and not (float(cfg.get("rass_min", -2)) <= float(latest_rass) <= float(cfg.get("rass_max", 1))), f"RASS {latest_rass}", 2, "请先调整镇静，使 RASS 达 -2~+1")
        add_factor("deep_sedation", latest_rass is not None and latest_rass < float(cfg.get("rass_min", -2)), f"镇静偏深 RASS {latest_rass}", 2, "建议先减轻镇静并评估咳嗽/保护气道能力")

        add_factor("fluid_overload_gt_5", fluid_pct is not None and fluid_pct > float(cfg.get("fluid_overload_warning_pct", 5)), f"%FO {fluid_pct}%", 2, "建议先利尿/负平衡，减轻肺水肿后再试 SBT")
        add_factor("fluid_overload_gt_10", fluid_pct is not None and fluid_pct > float(cfg.get("fluid_overload_high_pct", 10)), f"明显液体过负荷 %FO {fluid_pct}%", 3, "液体负荷偏重，当前不宜脱机")

        add_factor("bnp_surge", (bnp.get("ratio") or 0) >= float(cfg.get("bnp_surge_ratio", 1.5)), f"BNP {bnp.get('baseline')}→{bnp.get('latest')} (x{bnp.get('ratio')})", 2, "请先评估心功能/容量状态，必要时先利尿")
        add_factor("previous_sbt_failure", isinstance(sbt_result, dict) and sbt_result.get("result") == "failed", f"近72h SBT 失败", 3, "请针对上次 SBT 失败原因先处理后再尝试")
        add_factor("vasopressor_support", bool(on_vaso), "仍需血管活性药支持", 2, "请先稳定循环再考虑脱机")
        add_factor("gcs_low", gcs is not None and gcs < float(cfg.get("gcs_min", 9)), f"GCS {gcs}", 1, "请先确认意识/保护气道能力")
        add_factor("map_low", map_value is not None and map_value < float(cfg.get("map_min", 65)), f"MAP {map_value}", 1, "请先稳定循环后再试 SBT")

        severity = self._risk_level(score, warning_score, high_score, critical_score)
        fio2_frac = fio2 / 100.0 if fio2 is not None and fio2 > 1 else fio2
        gate_failures: list[str] = []
        if fio2_frac is not None and fio2_frac > float(cfg.get("ready_fio2_max", 0.4)):
            gate_failures.append("FiO₂ 偏高")
        if peep is not None and peep > float(cfg.get("ready_peep_max", 8)):
            gate_failures.append("PEEP 偏高")
        if on_vaso:
            gate_failures.append("仍需血管活性药")
        if map_value is not None and map_value < float(cfg.get("map_min", 65)):
            gate_failures.append("MAP 未达标")
        if latest_rass is not None and not (float(cfg.get("rass_min", -2)) <= float(latest_rass) <= float(cfg.get("rass_max", 1))):
            gate_failures.append("RASS 未达标")

        recommendation = "可以尝试 SBT"
        rule_id = "VENT_WEAN_READY"
        name = "可尝试SBT自主呼吸试验"
        alert_severity = "warning"
        if gate_failures or severity in {"warning", "high"}:
            recommendation = "SBT 前建议先处理"
            rule_id = "VENT_WEAN_OPTIMIZE"
            name = "SBT前建议先处理"
            alert_severity = "high" if severity in {"high", "critical"} or len(gate_failures) >= 2 else "warning"
        if severity == "critical" or (severity == "high" and len(gate_failures) >= 2):
            recommendation = "暂不建议脱机"
            rule_id = "VENT_WEAN_DEFER"
            name = "暂不建议脱机"
            alert_severity = "high"

        if recommendation == "可以尝试 SBT" and (8 <= now.hour <= 22):
            suggestion = "建议安排 SBT，并同步评估分泌物清除、咳嗽与拔管耐受性。"
        elif recommendation == "SBT 前建议先处理":
            suggestion = "；".join(dict.fromkeys(suggestions or gate_failures or ["请先优化氧合、容量状态与镇静深度"]))
        else:
            suggestion = "；".join(dict.fromkeys(suggestions or gate_failures or ["当前脱机失败风险高，建议先纠正可逆因素"]))

        explanation = await self._polish_structured_alert_explanation(
            {
                "summary": f"脱机失败风险评分 {round(score, 1)} 分，当前建议：{recommendation}。",
                "evidence": [str(item.get("evidence") or "") for item in factors[:4] if str(item.get("evidence") or "").strip()],
                "suggestion": suggestion,
                "text": "",
            }
        )

        return {
            "rule_id": rule_id,
            "name": name,
            "severity": alert_severity,
            "recommendation": recommendation,
            "risk_score": round(score, 1),
            "risk_level": severity or "low",
            "factors": factors,
            "explanation": explanation,
            "extra": {
                "risk_score": round(score, 1),
                "risk_level": severity or "low",
                "recommendation": recommendation,
                "ventilation_days": vent_days,
                "pf_ratio": pf_ratio,
                "pf_trend": pf.get("trend"),
                "pao2": pf.get("latest_pao2"),
                "fio2": fio2,
                "peep": peep,
                "rsbi": rsbi,
                "rr": rr,
                "vte_ml": vte,
                "rass": latest_rass,
                "gcs": gcs,
                "map": map_value,
                "on_vasopressor": on_vaso,
                "fluid_overload_pct": fluid_pct,
                "bnp_trend": bnp,
                "previous_sbt": sbt_result,
                "gate_failures": gate_failures,
                "factors": factors,
                "suggestion": suggestion,
            },
        }

    async def scan_ventilator_weaning(self) -> None:
        from .scanner_ventilator_weaning import VentilatorWeaningScanner

        await VentilatorWeaningScanner(self).scan()
