from __future__ import annotations

import re
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


class DrugSafetyScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="drug_safety",
                interval_key="drug_safety",
                default_interval=1800,
                initial_delay=45,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
             "weight": 1, "bodyWeight": 1, "body_weight": 1, "weightKg": 1, "weight_kg": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        heparin_kw = self.engine._get_cfg_list(("alert_engine", "drug_mapping", "heparin"), ["肝素"])
        vanco_kw = self.engine._get_cfg_list(("alert_engine", "drug_mapping", "vancomycin"), ["万古霉素"])
        sedative_kw = self.engine._get_cfg_list(
            ("alert_engine", "drug_mapping", "sedatives"),
            ["咪达唑仑", "丙泊酚", "右美托咪定", "地西泮", "芬太尼", "瑞芬太尼"],
        )
        qt_drugs = self.engine._get_cfg_list(
            ("alert_engine", "drug_mapping", "qt_risk"),
            ["胺碘酮", "左氧氟沙星", "环丙沙星", "红霉素", "阿奇霉素", "氟哌啶醇", "奥氮平", "喹硫平"],
        )
        steroid_kw = self.engine._get_cfg_list(
            ("alert_engine", "drug_mapping", "steroids"),
            ["氢化可的松", "甲泼尼龙", "地塞米松", "泼尼松", "泼尼松龙", "methylpred", "hydrocortisone", "dexamethasone"],
        )
        opioid_kw = self.engine._get_cfg_list(
            ("alert_engine", "drug_mapping", "opioids"),
            ["吗啡", "芬太尼", "舒芬太尼", "瑞芬太尼", "羟考酮", "氢吗啡酮", "哌替啶", "曲马多", "可待因", "布托啡诺", "opioid"],
        )

        opioid_cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("drug_safety", {})
        opioid_med_warn = float(opioid_cfg.get("opioid_med_warning_mg_per_day", 200))
        opioid_min_days = float(opioid_cfg.get("opioid_min_long_term_days", 3))
        opioid_stop_gap_h = float(opioid_cfg.get("opioid_stop_gap_hours", 24))
        opioid_withdraw_window_h = float(opioid_cfg.get("opioid_withdrawal_window_hours", 72))
        opioid_course_gap_h = float(opioid_cfg.get("opioid_course_gap_hours", 36))
        rr_threshold = float(opioid_cfg.get("opioid_resp_rr_threshold", 10))
        rr_critical = float(opioid_cfg.get("opioid_resp_rr_critical", 8))
        spo2_low = float(opioid_cfg.get("opioid_spo2_low_threshold", 92))
        spo2_critical = float(opioid_cfg.get("opioid_spo2_critical_threshold", 90))
        spo2_drop_th = float(opioid_cfg.get("opioid_spo2_drop_threshold", 4))
        spo2_drop_window_h = float(opioid_cfg.get("opioid_spo2_drop_window_hours", 2))
        opioid_med_factors = opioid_cfg.get("opioid_med_factors", {}) if isinstance(opioid_cfg, dict) else {}

        triggered = 0
        now = datetime.now()
        for p in patients:
            pid = p.get("_id")
            if not pid:
                continue

            pid_str = str(pid)
            drugs = await self.engine._get_recent_drugs(pid, hours=72)
            if not drugs:
                continue

            if any(any(k in d for k in heparin_kw) for d in drugs):
                his_pid = p.get("hisPid")
                if his_pid:
                    plt_drop = await self.engine._get_platelet_drop(his_pid, days=7)
                    if plt_drop and plt_drop["drop_ratio"] >= 0.5:
                        rule_id = "DRUG_HIT"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="疑似HIT(肝素相关血小板减少)",
                                category="drug_safety",
                                alert_type="hit",
                                severity="high",
                                parameter="plt",
                                condition={"drop_ratio": plt_drop["drop_ratio"]},
                                value=plt_drop["current"],
                                patient_id=pid_str,
                                patient_doc=p,
                                device_id=None,
                                source_time=plt_drop.get("time"),
                                extra=plt_drop,
                            )
                            if alert:
                                triggered += 1

            if any(any(k in d for k in vanco_kw) for d in drugs):
                his_pid = p.get("hisPid")
                if his_pid:
                    aki = await self.engine._calc_aki_stage(p, pid, his_pid)
                    if aki and aki.get("stage", 0) >= 1:
                        rule_id = "DRUG_VANCO_NEPHRO"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="万古霉素相关肾毒性风险",
                                category="drug_safety",
                                alert_type="nephrotoxicity",
                                severity="warning",
                                parameter="creatinine",
                                condition=aki.get("condition", {}),
                                value=aki.get("current"),
                                patient_id=pid_str,
                                patient_doc=p,
                                device_id=None,
                                source_time=aki.get("time"),
                                extra=aki,
                            )
                            if alert:
                                triggered += 1

            if any(any(k in d for k in sedative_kw) for d in drugs):
                rass_info = await self.engine._get_rass_status(pid)
                if rass_info and rass_info.get("over_sedation"):
                    rule_id = "DRUG_OVER_SEDATION"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="过度镇静风险",
                            category="drug_safety",
                            alert_type="sedation",
                            severity="warning",
                            parameter="rass",
                            condition={"rass": rass_info.get("rass")},
                            value=rass_info.get("rass"),
                            patient_id=pid_str,
                            patient_doc=p,
                            device_id=None,
                            source_time=rass_info.get("time"),
                            extra=rass_info,
                        )
                        if alert:
                            triggered += 1

            qt_count = sum(1 for d in drugs if any(k in d for k in qt_drugs))
            if qt_count >= 2:
                rule_id = "DRUG_QT_RISK"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="QTc延长风险(多种药物)",
                        category="drug_safety",
                        alert_type="qt_risk",
                        severity="warning",
                        parameter="qt_risk",
                        condition={"qt_drugs": qt_count},
                        value=qt_count,
                        patient_id=pid_str,
                        patient_doc=p,
                        device_id=None,
                        source_time=None,
                        extra={"drugs": drugs},
                    )
                    if alert:
                        triggered += 1

            # 阿片类相关规则
            since_10d = now - timedelta(days=10)
            opioid_docs_all = await self.engine._get_recent_drug_docs(pid_str, since_10d)
            opioid_events = []
            for d in opioid_docs_all:
                text = " ".join(str(d.get(k) or "") for k in ("drugName", "orderName", "drugSpec", "route", "routeName")).lower()
                if not self.engine._text_has_any(text, opioid_kw):
                    continue
                factor = self.engine._opioid_med_factor(text, opioid_med_factors)
                if factor is None:
                    factor = 1.0
                dose_mg = self.engine._extract_dose_mg(d)
                med_mg = (dose_mg * factor) if (dose_mg is not None) else None
                opioid_events.append({**d, "_opioid_text": text, "_med_mg": med_mg})

            if opioid_events:
                # (1) 高剂量阿片（MED > 200 mg/d）
                med_24h = sum(
                    float(e["_med_mg"])
                    for e in opioid_events
                    if e.get("_med_mg") is not None and (now - e["_event_time"]).total_seconds() <= 24 * 3600
                )
                if med_24h > opioid_med_warn:
                    rule_id = "DRUG_OPIOID_HIGH_DOSE_RESP_RISK"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="高剂量阿片用药呼吸抑制风险",
                            category="drug_safety",
                            alert_type="opioid_high_dose_resp_risk",
                            severity="high",
                            parameter="opioid_med_24h",
                            condition={"operator": ">", "threshold_mg_per_day": opioid_med_warn},
                            value=round(med_24h, 2),
                            patient_id=pid_str,
                            patient_doc=p,
                            device_id=None,
                            source_time=now,
                            extra={"opioid_med_24h_mg": round(med_24h, 2), "threshold_mg_per_day": opioid_med_warn},
                        )
                        if alert:
                            triggered += 1

                # (2) 阿片 + RR<10 或 SpO2突然下降 => 呼吸抑制
                opioid_active = any((now - e["_event_time"]).total_seconds() <= 24 * 3600 for e in opioid_events)
                if opioid_active:
                    vitals = await self.engine._get_latest_vitals_by_patient(pid)
                    rr = _to_float(vitals.get("rr")) if isinstance(vitals, dict) else None
                    rr_low = rr is not None and rr < rr_threshold

                    spo2_series = await self.engine._get_param_series_by_pid(
                        pid,
                        "param_spo2",
                        now - timedelta(hours=max(1.0, spo2_drop_window_h)),
                    )
                    latest_spo2 = None
                    spo2_drop = None
                    spo2_sudden_drop = False
                    if spo2_series:
                        latest_spo2 = _to_float(spo2_series[-1].get("value"))
                        if len(spo2_series) >= 2 and latest_spo2 is not None:
                            prev_vals = [_to_float(x.get("value")) for x in spo2_series[:-1]]
                            prev_vals = [x for x in prev_vals if x is not None]
                            if prev_vals:
                                prev_high = max(prev_vals)
                                spo2_drop = round(prev_high - latest_spo2, 2)
                                spo2_sudden_drop = spo2_drop >= spo2_drop_th and latest_spo2 <= spo2_low

                    if rr_low or spo2_sudden_drop:
                        sev = "high"
                        if (rr is not None and rr < rr_critical) or (latest_spo2 is not None and latest_spo2 <= spo2_critical):
                            sev = "critical"
                        rule_id = "DRUG_OPIOID_RESP_DEPRESSION"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="阿片相关呼吸抑制风险",
                                category="drug_safety",
                                alert_type="opioid_respiratory_depression",
                                severity=sev,
                                parameter="respiratory_status",
                                condition={
                                    "opioid_active": True,
                                    "rr_lt": rr_threshold,
                                    "spo2_drop_ge": spo2_drop_th,
                                    "spo2_low_le": spo2_low,
                                },
                                value=rr if rr is not None else latest_spo2,
                                patient_id=pid_str,
                                patient_doc=p,
                                device_id=None,
                                source_time=vitals.get("time") if isinstance(vitals, dict) else now,
                                extra={
                                    "rr": rr,
                                    "latest_spo2": latest_spo2,
                                    "spo2_drop": spo2_drop,
                                    "spo2_sudden_drop": spo2_sudden_drop,
                                    "opioid_med_24h_mg": round(med_24h, 2),
                                },
                            )
                            if alert:
                                triggered += 1

                # (3) 长期阿片后突然停药 => 戒断风险
                course = self.engine._continuous_opioid_course(opioid_events, now, opioid_course_gap_h)
                if course:
                    long_term = course["duration_hours"] >= opioid_min_days * 24
                    stopped = course["since_last_hours"] >= opioid_stop_gap_h
                    still_in_withdraw_window = course["since_last_hours"] <= opioid_withdraw_window_h
                    if long_term and stopped and still_in_withdraw_window:
                        rule_id = "DRUG_OPIOID_WITHDRAWAL_RISK"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="阿片停药后戒断风险",
                                category="drug_safety",
                                alert_type="opioid_withdrawal_risk",
                                severity="warning",
                                parameter="opioid_stop_gap_hours",
                                condition={
                                    "long_term_days_gte": opioid_min_days,
                                    "stop_gap_hours_gte": opioid_stop_gap_h,
                                },
                                value=round(course["since_last_hours"], 2),
                                patient_id=pid_str,
                                patient_doc=p,
                                device_id=None,
                                source_time=course["last"],
                                extra={
                                    "course_start": course["start"],
                                    "course_last": course["last"],
                                    "course_duration_hours": course["duration_hours"],
                                    "since_last_opioid_hours": course["since_last_hours"],
                                },
                            )
                            if alert:
                                triggered += 1

            # 激素相关规则
            steroid_docs = await self.engine._find_recent_drug_docs(pid, steroid_kw, hours=24 * 14, limit=1000)
            if steroid_docs:
                last_steroid = steroid_docs[-1]
                had_vaso_48h = await self.engine._has_recent_drug(pid, ["去甲肾上腺素", "肾上腺素", "多巴胺", "血管加压素"], hours=48)
                on_vaso_12h = await self.engine._has_recent_drug(pid, ["去甲肾上腺素", "肾上腺素", "多巴胺", "血管加压素"], hours=12)
                if had_vaso_48h and not on_vaso_12h:
                    rule_id = "DRUG_STEROID_TAPER_AFTER_VASO"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="评估激素减停（升压药已停用）",
                            category="drug_safety",
                            alert_type="steroid_taper_after_vaso",
                            severity="warning",
                            parameter="steroid_vaso_linkage",
                            condition={"vasopressor_off_hours": 12},
                            value=12,
                            patient_id=pid_str,
                            patient_doc=p,
                            device_id=None,
                            source_time=last_steroid.get("_event_time"),
                            extra={
                                "steroids": [self.engine._drug_text(d) for d in steroid_docs[-5:]],
                                "vasopressor_off_gt_hours": 12,
                            },
                        )
                        if alert:
                            triggered += 1

                duration_hours = 0.0
                if steroid_docs and steroid_docs[0].get("_event_time") and steroid_docs[-1].get("_event_time"):
                    duration_hours = (steroid_docs[-1]["_event_time"] - steroid_docs[0]["_event_time"]).total_seconds() / 3600.0
                if duration_hours >= 7 * 24:
                    rule_id = "DRUG_LONG_TERM_STEROID_TAPER"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="长程激素减停提醒",
                            category="drug_safety",
                            alert_type="steroid_long_term_taper",
                            severity="warning",
                            parameter="steroid_duration_days",
                            condition={"operator": ">=", "threshold_days": 7},
                            value=round(duration_hours / 24.0, 1),
                            patient_id=pid_str,
                            patient_doc=p,
                            device_id=None,
                            source_time=last_steroid.get("_event_time"),
                            extra={
                                "duration_days": round(duration_hours / 24.0, 1),
                                "message": "需要逐步减量，警惕肾上腺功能不全",
                            },
                        )
                        if alert:
                            triggered += 1

                his_pid = p.get("hisPid")
                if his_pid:
                    glu_series = await self.engine._get_lab_series(his_pid, "glu", now - timedelta(hours=24), limit=200)
                    high_glu = [x for x in glu_series if x.get("value") is not None and x["value"] > 10]
                    if len(high_glu) >= 2:
                        rule_id = "DRUG_STEROID_HYPERGLYCEMIA"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="激素相关高血糖",
                                category="drug_safety",
                                alert_type="steroid_hyperglycemia",
                                severity="high",
                                parameter="glu",
                                condition={"consecutive_gt_mmol": 10, "count": 2},
                                value=high_glu[-1]["value"],
                                patient_id=pid_str,
                                patient_doc=p,
                                device_id=None,
                                source_time=high_glu[-1]["time"],
                                extra={
                                    "latest_glucose": high_glu[-1]["value"],
                                    "high_glucose_count": len(high_glu),
                                    "message": "建议评估胰岛素方案调整",
                                },
                            )
                            if alert:
                                triggered += 1

        if triggered > 0:
            self.engine._log_info("药物安全", triggered)
