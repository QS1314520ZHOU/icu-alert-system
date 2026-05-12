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


from .scanners import BaseScanner, ScannerSpec


class NutritionMonitorScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="nutrition_monitor",
                interval_key="nutrition_monitor",
                default_interval=900,
                initial_delay=47,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("nutrition_monitor", {})
        start_delay_h = float(cfg.get("start_delay_hours", 48))
        kcal_coverage_threshold = float(cfg.get("calorie_coverage_threshold", 0.6))
        kcal_persist_h = float(cfg.get("calorie_under_target_persist_hours", 72))
        protein_coverage_threshold = float(cfg.get("protein_coverage_threshold", 0.6))
        protein_persist_h = float(cfg.get("protein_under_target_persist_hours", kcal_persist_h))
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
        refeeding_day1_kcal_max = float(cfg.get("refeeding_high_risk_day1_kcal_per_kg_max", 10))
        phosphate_monitor_h = float(cfg.get("refeeding_phosphate_monitor_interval_hours", 12))

        albumin_kw = self.engine._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "albumin_keywords"),
            ["白蛋白", "albumin", "alb"],
        )
        phosphate_kw = self.engine._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "phosphate_keywords"),
            ["磷", "无机磷", "血磷", "phosphate", "phos", "phosphorus"],
        )
        magnesium_kw = self.engine._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "magnesium_keywords"),
            ["镁", "血镁", "magnesium"],
        )

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
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
                "gender": 1,
                "sex": 1,
                "hisSex": 1,
                "icuAdmissionTime": 1,
                "admissionTime": 1,
                "inTime": 1,
                "admitTime": 1,
                "current_profile": 1,
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

            admission_t = self.engine._admission_time(patient_doc)
            stay_h = 0.0
            if admission_t:
                stay_h = max(0.0, (now - admission_t).total_seconds() / 3600.0)

            since_drug = now - timedelta(days=14)
            if admission_t:
                since_drug = min(since_drug, admission_t - timedelta(hours=1))
            nutrition_events = await self.engine._get_nutrition_drug_events(pid_str, since_drug, cfg)

            # (1) 入ICU >48h 且无EN/PN
            if stay_h >= start_delay_h:
                has_nutrition_after_adm = False
                if admission_t:
                    has_nutrition_after_adm = any(e["time"] >= admission_t for e in nutrition_events)
                else:
                    has_nutrition_after_adm = bool(nutrition_events)
                if not has_nutrition_after_adm:
                    rule_id = "NUTRITION_START_DELAY"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
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

            refeeding_risk = None
            if his_pid or patient_doc:
                refeeding_risk = await self._refeeding_risk_state(
                    patient_doc=patient_doc,
                    his_pid=his_pid,
                    reference_time=first_nutrition_t or now,
                    admission_t=admission_t,
                    albumin_kw=albumin_kw,
                    phosphate_kw=phosphate_kw,
                    magnesium_kw=magnesium_kw,
                    cfg=cfg,
                )

            # (2) 热卡达标监测：按代谢阶段/入住天数动态目标，不再固定 25 kcal/kg/d
            weight_kg = self.engine._get_patient_weight(patient_doc)
            if nutrition_events and weight_kg and weight_kg > 0:
                window_start = now - timedelta(hours=kcal_persist_h)
                usable_events = [e for e in nutrition_events if e["time"] >= window_start and e.get("kcal") is not None]
                total_kcal = round(sum(float(e["kcal"]) for e in usable_events), 2)
                target = await self._dynamic_nutrition_target(patient_doc, pid_str, stay_h, float(weight_kg), cfg)
                target_kcal_day = round(float(target["target_kcal_day_min"]), 2)
                target_kcal_window = round(target_kcal_day * (kcal_persist_h / 24.0), 2)
                coverage = (total_kcal / target_kcal_window) if target_kcal_window > 0 else 0.0

                can_eval = False
                if first_nutrition_t:
                    can_eval = (now - first_nutrition_t).total_seconds() >= kcal_persist_h * 3600
                elif admission_t:
                    can_eval = (now - admission_t).total_seconds() >= kcal_persist_h * 3600

                if can_eval and coverage < kcal_coverage_threshold:
                    rule_id = "NUTRITION_CALORIE_NOT_REACHED"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
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
                                "target_kcal_per_kg_day": target["target_kcal_per_kg_day_min"],
                            },
                            value=round(coverage * 100, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=now,
                            extra={
                                "weight_kg": weight_kg,
                                "target_weight_kg": target["target_weight_kg"],
                                "target_strategy": target["strategy"],
                                "metabolic_phase": target.get("phase"),
                                "obesity_adjusted": target["obesity_adjusted"],
                                "target_kcal_per_kg_day_range": target["target_kcal_per_kg_day_range"],
                                "target_kcal_day": target_kcal_day,
                                "target_kcal_day_range": target["target_kcal_day_range"],
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

                # 蛋白质达标监测：ICU 营养不能只盯热卡
                protein_events = [e for e in nutrition_events if e["time"] >= now - timedelta(hours=protein_persist_h)]
                total_protein = round(sum(self._estimate_protein_g(e.get("raw") or {}) or 0.0 for e in protein_events), 2)
                protein_min = float(target["target_protein_g_day_min"])
                protein_window = round(protein_min * (protein_persist_h / 24.0), 2)
                protein_coverage = (total_protein / protein_window) if protein_window > 0 else 0.0
                if can_eval and protein_window > 0 and protein_coverage < protein_coverage_threshold:
                    rule_id = "NUTRITION_PROTEIN_NOT_REACHED"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="蛋白质供给达标不足",
                            category="nutrition_monitor",
                            alert_type="nutrition_protein_not_reached",
                            severity="warning",
                            parameter="protein_coverage_ratio",
                            condition={
                                "operator": "<",
                                "threshold": protein_coverage_threshold,
                                "window_hours": protein_persist_h,
                                "target_protein_g_kg_day": target["target_protein_g_kg_day_min"],
                            },
                            value=round(protein_coverage * 100, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=now,
                            extra={
                                "weight_kg": weight_kg,
                                "target_weight_kg": target["target_weight_kg"],
                                "metabolic_phase": target.get("phase"),
                                "target_protein_g_kg_day_range": target["target_protein_g_kg_day_range"],
                                "target_protein_g_day_range": target["target_protein_g_day_range"],
                                "actual_protein_g_window": total_protein,
                                "target_protein_g_window": protein_window,
                                "coverage_ratio": round(protein_coverage, 3),
                                "coverage_percent": round(protein_coverage * 100, 1),
                            },
                        )
                        if alert:
                            triggered += 1

            # (3) 胃潴留/喂养不耐受 + 喂养中断
            feed_since = now - timedelta(hours=feeding_lookback_h)
            tolerance = await self.engine._get_tolerance_signals(pid_str, feed_since, cfg)
            high_grv_events = tolerance["high_grv_events"]
            vomit_events = tolerance["vomit_events"]
            dist_events = tolerance["dist_events"]
            interrupt_events = tolerance["interrupt_events"]
            prokinetic_events = await self._get_prokinetic_events(pid_str, feed_since, cfg)

            has_intolerance = bool(high_grv_events or vomit_events or dist_events or prokinetic_events)
            has_interrupt = bool(interrupt_events)
            if has_intolerance and has_interrupt:
                latest_intolerance_t = None
                for arr in (high_grv_events, vomit_events, dist_events, prokinetic_events):
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
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        latest_grv = high_grv_events[-1]["value_ml"] if high_grv_events else None
                        alert = await self.engine._create_alert(
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
                                "prokinetic_count": len(prokinetic_events),
                                "feeding_interrupt_count": len(interrupt_events),
                                "suggestion": "建议评估喂养方式与耐受性；GRV 阈值按 500mL 处理，可结合促动力药、幽门后喂养和 EN 中断时长优化方案。",
                            },
                        )
                        if alert:
                            triggered += 1

            # (4) 再喂养综合征：先识别高危并提醒 B1/磷监测，再监测启动后电解质下降
            if refeeding_risk and refeeding_risk.get("high_risk"):
                if not await self._has_recent_drug_keyword(
                    pid_str,
                    self.engine._get_cfg_list(
                        ("alert_engine", "nutrition_monitor", "thiamine_keywords"),
                        ["硫胺素", "维生素b1", "维生素B1", "thiamine"],
                    ),
                    (first_nutrition_t or now) - timedelta(hours=24),
                    (first_nutrition_t or now) + timedelta(hours=2),
                ):
                    rule_id = "NUTRITION_REFEEDING_HIGH_RISK_PREVENTION"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="再喂养高危启动前预防提醒",
                            category="nutrition_monitor",
                            alert_type="nutrition_refeeding_prevention",
                            severity="warning",
                            parameter="refeeding_high_risk",
                            condition={"thiamine_before_feeding": False},
                            value=len(refeeding_risk.get("risk_factors") or []),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=now,
                            extra={
                                "risk_factors": refeeding_risk.get("risk_factors") or [],
                                "suggestion": "再喂养高危患者启动营养前建议预防性补充硫胺素 B1，并同步纠正 K/P/Mg。",
                            },
                        )
                        if alert:
                            triggered += 1

                if first_nutrition_t:
                    day1_end = min(now, first_nutrition_t + timedelta(hours=24))
                    day1_events = [e for e in nutrition_events if first_nutrition_t <= e["time"] <= day1_end and e.get("kcal") is not None]
                    day1_kcal = sum(float(e["kcal"]) for e in day1_events)
                    day1_kcal_kg = day1_kcal / float(weight_kg) if weight_kg else 0.0
                    if day1_kcal_kg > refeeding_day1_kcal_max:
                        rule_id = "NUTRITION_REFEEDING_START_TOO_FAST"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="再喂养高危起始热卡过快",
                                category="nutrition_monitor",
                                alert_type="nutrition_refeeding_start_too_fast",
                                severity="high",
                                parameter="day1_kcal_kg",
                                condition={"operator": ">", "threshold_kcal_kg_day": refeeding_day1_kcal_max},
                                value=round(day1_kcal_kg, 2),
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=None,
                                source_time=day1_end,
                                extra={
                                    "day1_kcal": round(day1_kcal, 2),
                                    "day1_kcal_kg": round(day1_kcal_kg, 2),
                                    "risk_factors": refeeding_risk.get("risk_factors") or [],
                                    "suggestion": "高危患者第 1 天建议限制在 5-10 kcal/kg/d，并严密复查电解质。",
                                },
                            )
                            if alert:
                                triggered += 1

                    latest_p_time = refeeding_risk.get("latest_phosphate_time")
                    if his_pid:
                        recent_p = await self.engine._get_lab_series_by_keywords(
                            his_pid,
                            first_nutrition_t - timedelta(hours=1),
                            now,
                            phosphate_kw,
                            converter=self.engine._convert_phosphate_to_mmol_l,
                            limit=1200,
                        )
                        if recent_p:
                            latest_p_time = recent_p[-1]["time"]
                    in_first_72h = (now - first_nutrition_t).total_seconds() <= refeeding_window_h * 3600
                    p_due = latest_p_time is None or (now - latest_p_time).total_seconds() > phosphate_monitor_h * 3600
                    if in_first_72h and p_due:
                        rule_id = "NUTRITION_PHOSPHATE_MONITORING_DUE"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="再喂养高危磷监测到期",
                                category="nutrition_monitor",
                                alert_type="nutrition_phosphate_monitoring_due",
                                severity="warning",
                                parameter="phosphate_monitor_interval",
                                condition={"recommended_interval_hours": phosphate_monitor_h},
                                value=phosphate_monitor_h,
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=None,
                                source_time=now,
                                extra={
                                    "latest_phosphate_time": latest_p_time,
                                    "risk_factors": refeeding_risk.get("risk_factors") or [],
                                    "suggestion": "再喂养高危启动后 72h 内建议 q12h 复查血磷，并同步监测 K/Mg。",
                                },
                            )
                            if alert:
                                triggered += 1

            if first_nutrition_t and his_pid:
                refeed_end = min(now, first_nutrition_t + timedelta(hours=refeeding_window_h))
                if refeed_end > first_nutrition_t:
                    bmi = self.engine._patient_bmi(patient_doc)
                    malnutrition_by_bmi = bmi is not None and bmi < malnut_bmi_thr

                    alb_end = admission_t + timedelta(hours=24) if admission_t else first_nutrition_t
                    alb_since = alb_end - timedelta(days=albumin_baseline_lookback_days)
                    alb_series = await self.engine._get_lab_series_by_keywords(
                        his_pid,
                        alb_since,
                        alb_end,
                        albumin_kw,
                        converter=self.engine._convert_albumin_to_g_l,
                        limit=1200,
                    )
                    alb_latest = alb_series[-1]["value"] if alb_series else None
                    malnutrition_by_alb = alb_latest is not None and alb_latest < malnut_alb_thr
                    malnutrition = malnutrition_by_bmi or malnutrition_by_alb

                    if malnutrition:
                        k_series = await self.engine._get_lab_series(his_pid, "k", first_nutrition_t, refeed_end, limit=600)
                        p_series = await self.engine._get_lab_series_by_keywords(
                            his_pid,
                            first_nutrition_t,
                            refeed_end,
                            phosphate_kw,
                            converter=self.engine._convert_phosphate_to_mmol_l,
                            limit=1200,
                        )
                        mg_series = await self.engine._get_lab_series_by_keywords(
                            his_pid,
                            first_nutrition_t,
                            refeed_end,
                            magnesium_kw,
                            converter=self.engine._convert_magnesium_to_mmol_l,
                            limit=1200,
                        )

                        k_trend = self.engine._drop_trend(k_series, drop_ratio_thr, k_drop_abs_thr, low_k_thr)
                        p_trend = self.engine._drop_trend(p_series, drop_ratio_thr, p_drop_abs_thr, low_p_thr)
                        mg_trend = self.engine._drop_trend(mg_series, drop_ratio_thr, mg_drop_abs_thr, low_mg_thr)

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
                            if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                                max_drop_ratio = max(
                                    x["drop_ratio"] for x in (k_trend, p_trend, mg_trend) if x and x.get("triggered")
                                )
                                alert = await self.engine._create_alert(
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
            self.engine._log_info("营养监测", triggered)

    def _height_cm(self, patient_doc: dict[str, Any]) -> float | None:
        for key in ("height", "bodyHeight", "heightCm", "height_cm"):
            value = _to_float(patient_doc.get(key))
            if value is not None and 80 <= value <= 230:
                return value
            if value is not None and 0.8 <= value <= 2.3:
                return value * 100.0
        return None

    def _ideal_body_weight_kg(self, patient_doc: dict[str, Any]) -> float | None:
        height_cm = self._height_cm(patient_doc)
        if height_cm is None:
            return None
        sex = str(patient_doc.get("gender") or patient_doc.get("sex") or patient_doc.get("hisSex") or "").lower()
        base = 45.5 if any(x in sex for x in ("女", "female", "f")) else 50.0
        ibw = base + 0.91 * (height_cm - 152.4)
        return round(max(30.0, min(120.0, ibw)), 2)

    async def _latest_metabolic_phase(self, patient_doc: dict[str, Any], patient_id: str) -> dict[str, Any] | None:
        profile = patient_doc.get("current_profile") if isinstance(patient_doc.get("current_profile"), dict) else {}
        phase = profile.get("metabolic_phase") if isinstance(profile.get("metabolic_phase"), dict) else None
        if phase:
            return phase
        try:
            doc = await self.engine.db.col("score").find_one(
                {"patient_id": patient_id, "score_type": "metabolic_phase_detector"},
                sort=[("calc_time", -1)],
            )
        except Exception:
            return None
        return doc if isinstance(doc, dict) else None

    def _indirect_calorimetry_target(self, patient_doc: dict[str, Any]) -> float | None:
        profile = patient_doc.get("current_profile") if isinstance(patient_doc.get("current_profile"), dict) else {}
        ic = profile.get("indirect_calorimetry") if isinstance(profile.get("indirect_calorimetry"), dict) else {}
        for key in ("ree_kcal_day", "REE", "ree"):
            value = _to_float(ic.get(key) or profile.get(key))
            if value is not None and 500 <= value <= 5000:
                return round(value, 2)
        vco2 = _to_float(ic.get("vco2_l_day") or profile.get("vco2_l_day"))
        if vco2 is not None and 50 <= vco2 <= 800:
            return round(vco2 * 8.19, 2)
        return None

    async def _dynamic_nutrition_target(
        self,
        patient_doc: dict[str, Any],
        patient_id: str,
        stay_h: float,
        actual_weight_kg: float,
        cfg: dict[str, Any],
    ) -> dict[str, Any]:
        bmi = self.engine._patient_bmi(patient_doc)
        obese = bool(bmi is not None and bmi > float(cfg.get("obesity_bmi_threshold", 30)))
        ibw = self._ideal_body_weight_kg(patient_doc)
        target_weight = ibw if obese and ibw else actual_weight_kg
        strategy = "icu_day_phase"
        phase_name = None

        kcal_range = None
        protein_range = None
        phase = await self._latest_metabolic_phase(patient_doc, patient_id)
        if phase:
            phase_name = str(phase.get("phase") or "")
            nt = phase.get("nutrition_target") if isinstance(phase.get("nutrition_target"), dict) else {}
            if isinstance(nt.get("kcal"), list) and len(nt["kcal"]) >= 2:
                kcal_range = [_to_float(nt["kcal"][0]), _to_float(nt["kcal"][1])]
            if isinstance(nt.get("protein"), list) and len(nt["protein"]) >= 2:
                protein_range = [_to_float(nt["protein"][0]), _to_float(nt["protein"][1])]
            if kcal_range and protein_range:
                strategy = "metabolic_phase_detector"

        if not kcal_range or kcal_range[0] is None or kcal_range[1] is None:
            icu_day = stay_h / 24.0
            if icu_day <= 3:
                kcal_range = list(cfg.get("early_phase_kcal_per_kg_day", [10, 20]))
                protein_range = list(cfg.get("early_phase_protein_g_kg_day", [0.8, 1.2]))
                phase_name = phase_name or "acute_early"
            elif icu_day <= 7:
                goal = float(cfg.get("calorie_target_kcal_per_kg_day", 25))
                kcal_range = [round(goal * 0.7, 2), round(goal * 0.8, 2)]
                protein_range = list(cfg.get("late_acute_protein_g_kg_day", [1.0, 1.3]))
                phase_name = phase_name or "acute_late"
            else:
                kcal_range = list(cfg.get("recovery_phase_kcal_per_kg_day", [25, 30]))
                protein_range = list(cfg.get("recovery_phase_protein_g_kg_day", [1.3, 2.0]))
                phase_name = phase_name or "recovery"

        kcal_min = float(kcal_range[0])
        kcal_max = float(kcal_range[1])
        if obese:
            obesity_range = cfg.get("obesity_actual_weight_kcal_per_kg_day", [11, 14])
            kcal_min = float(obesity_range[0])
            kcal_max = float(obesity_range[1])
            target_weight = actual_weight_kg
            strategy = f"{strategy}+obesity_actual_weight"

        ic_target = self._indirect_calorimetry_target(patient_doc)
        if ic_target is not None:
            kcal_day_min = ic_target
            kcal_day_max = ic_target
            strategy = f"{strategy}+indirect_calorimetry"
        else:
            kcal_day_min = kcal_min * target_weight
            kcal_day_max = kcal_max * target_weight

        protein_min = float((protein_range or [1.0, 1.3])[0])
        protein_max = float((protein_range or [1.0, 1.3])[1])
        protein_weight = ibw if obese and ibw else actual_weight_kg
        return {
            "strategy": strategy,
            "phase": phase_name,
            "obesity_adjusted": obese,
            "target_weight_kg": round(target_weight, 2),
            "protein_weight_kg": round(protein_weight, 2),
            "target_kcal_per_kg_day_min": round(kcal_min, 2),
            "target_kcal_per_kg_day_range": [round(kcal_min, 2), round(kcal_max, 2)],
            "target_kcal_day_min": round(kcal_day_min, 2),
            "target_kcal_day_range": [round(kcal_day_min, 2), round(kcal_day_max, 2)],
            "target_protein_g_kg_day_min": round(protein_min, 2),
            "target_protein_g_kg_day_range": [round(protein_min, 2), round(protein_max, 2)],
            "target_protein_g_day_min": round(protein_min * protein_weight, 2),
            "target_protein_g_day_range": [round(protein_min * protein_weight, 2), round(protein_max * protein_weight, 2)],
        }

    def _estimate_protein_g(self, doc: dict[str, Any]) -> float | None:
        for key in ("protein", "proteinG", "aminoAcid", "aminoAcidG", "totalProtein"):
            value = _to_float(doc.get(key))
            if value is not None and value > 0:
                return round(value, 2)
        nitrogen = _to_float(doc.get("nitrogen") or doc.get("nitrogenG"))
        if nitrogen is not None and nitrogen > 0:
            return round(nitrogen * 6.25, 2)
        text = " ".join(str(doc.get(key) or "") for key in ("drugName", "orderName", "drugSpec", "remark"))
        match = re.search(r"(\d+(?:\.\d+)?)\s*g\s*(?:蛋白|protein|amino|氨基酸)", text, flags=re.I)
        if match:
            value = _to_float(match.group(1))
            return round(value, 2) if value is not None else None
        return None

    async def _get_prokinetic_events(self, pid_str: str, since: datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        keywords = self.engine._get_cfg_list(
            ("alert_engine", "nutrition_monitor", "prokinetic_keywords"),
            ["甲氧氯普胺", "胃复安", "红霉素", "metoclopramide", "erythromycin"],
        )
        events: list[dict[str, Any]] = []
        cursor = self.engine.db.col("drugExe").find(
            {"pid": pid_str},
            {"executeTime": 1, "startTime": 1, "orderTime": 1, "drugName": 1, "orderName": 1, "drugSpec": 1, "remark": 1},
        ).sort("executeTime", -1).limit(int(cfg.get("prokinetic_scan_limit", 800)))
        async for doc in cursor:
            t = self.engine._drug_event_time(doc)
            if not t or t < since:
                continue
            text = self.engine._event_text(doc)
            if self.engine._contains_any(text, keywords):
                events.append({"time": t, "text": text})
        return sorted(events, key=lambda row: row["time"])

    async def _has_recent_drug_keyword(self, pid_str: str, keywords: list[str], since: datetime, until: datetime) -> bool:
        cursor = self.engine.db.col("drugExe").find(
            {"pid": pid_str},
            {"executeTime": 1, "startTime": 1, "orderTime": 1, "drugName": 1, "orderName": 1, "drugSpec": 1, "remark": 1},
        ).sort("executeTime", -1).limit(1200)
        async for doc in cursor:
            t = self.engine._drug_event_time(doc)
            if not t or t < since or t > until:
                continue
            if self.engine._contains_any(self.engine._event_text(doc), keywords):
                return True
        return False

    async def _refeeding_risk_state(
        self,
        *,
        patient_doc: dict[str, Any],
        his_pid: str,
        reference_time: datetime,
        admission_t: datetime | None,
        albumin_kw: list[str],
        phosphate_kw: list[str],
        magnesium_kw: list[str],
        cfg: dict[str, Any],
    ) -> dict[str, Any]:
        factors: list[str] = []
        bmi = self.engine._patient_bmi(patient_doc)
        if bmi is not None and bmi < float(cfg.get("refeeding_high_risk_bmi_threshold", 16)):
            factors.append("BMI<16")

        latest_p_time = None
        baseline = {"albumin_g_l": None, "k": None, "phosphate": None, "magnesium": None}
        if his_pid:
            since = (admission_t or reference_time) - timedelta(days=float(cfg.get("refeeding_baseline_lookback_days", 7)))
            end = reference_time
            alb_series = await self.engine._get_lab_series_by_keywords(
                his_pid,
                since,
                end,
                albumin_kw,
                converter=self.engine._convert_albumin_to_g_l,
                limit=1200,
            )
            k_series = await self.engine._get_lab_series(his_pid, "k", since, end, limit=600)
            p_series = await self.engine._get_lab_series_by_keywords(
                his_pid,
                since,
                end,
                phosphate_kw,
                converter=self.engine._convert_phosphate_to_mmol_l,
                limit=1200,
            )
            mg_series = await self.engine._get_lab_series_by_keywords(
                his_pid,
                since,
                end,
                magnesium_kw,
                converter=self.engine._convert_magnesium_to_mmol_l,
                limit=1200,
            )
            if alb_series:
                baseline["albumin_g_l"] = alb_series[-1]["value"]
            if k_series:
                baseline["k"] = k_series[-1]["value"]
            if p_series:
                baseline["phosphate"] = p_series[-1]["value"]
                latest_p_time = p_series[-1]["time"]
            if mg_series:
                baseline["magnesium"] = mg_series[-1]["value"]
            if baseline["k"] is not None and baseline["k"] < float(cfg.get("electrolyte_low_threshold", {}).get("k", 3.5)):
                factors.append("baseline_low_k")
            if baseline["phosphate"] is not None and baseline["phosphate"] < float(cfg.get("electrolyte_low_threshold", {}).get("phosphate", 0.8)):
                factors.append("baseline_low_phosphate")
            if baseline["magnesium"] is not None and baseline["magnesium"] < float(cfg.get("electrolyte_low_threshold", {}).get("magnesium", 0.75)):
                factors.append("baseline_low_magnesium")

        poor_intake = self._contains_patient_text(
            patient_doc,
            ["禁食", "极少进食", "进食差", "poor intake", "npo", "厌食", "消瘦", "体重下降"],
        )
        if poor_intake:
            factors.append("poor_intake_or_weight_loss_documented")

        return {
            "high_risk": bool(factors),
            "risk_factors": factors,
            "bmi": bmi,
            "baseline": baseline,
            "latest_phosphate_time": latest_p_time,
        }

    def _contains_patient_text(self, patient_doc: dict[str, Any], keywords: list[str]) -> bool:
        text = " ".join(
            str(patient_doc.get(key) or "")
            for key in ("clinicalDiagnosis", "diagnosis", "chiefComplaint", "presentIllness", "remark", "nutritionRisk")
        ).lower()
        return any(str(item).lower() in text for item in keywords)
