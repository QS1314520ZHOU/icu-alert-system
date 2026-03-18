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

            # (2) 热卡达标监测：不足60%持续72h
            weight_kg = self.engine._get_patient_weight(patient_doc)
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
            tolerance = await self.engine._get_tolerance_signals(pid_str, feed_since, cfg)
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
