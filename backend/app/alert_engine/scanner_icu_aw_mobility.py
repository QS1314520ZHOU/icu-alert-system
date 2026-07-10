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
from .scanners import BaseScanner, ScannerSpec


class IcuAwMobilityScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="icu_aw_mobility",
                interval_key="icu_aw_mobility",
                default_interval=900,
                initial_delay=68,
            ),
        )

    async def scan(self) -> None:
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

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.engine._icu_aw_cfg()
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
            admission_time = self.engine._icu_aw_admission_time(patient_doc)
            device_id = await self.engine._get_device_id_for_patient(patient_doc, ["monitor"])

            vent_info = await self.engine._get_ventilation_days(pid, now, admission_time)
            sed_info = await self.engine._get_sedative_exposure(pid, now, admission_time)
            steroid_info = await self.engine._get_steroid_exposure(pid, now, admission_time)
            glucose_info = await self.engine._get_glucose_instability(pid_str, his_pid, now)
            sepsis_sofa = await self.engine._get_icu_aw_sepsis_sofa_signal(patient_doc, pid, device_id, his_pid)
            immobility_hours = await self.engine._immobility_hours(patient_doc, pid, now)
            readiness = await self.engine._assess_early_mobility_readiness(
                patient_doc,
                pid=pid,
                pid_str=pid_str,
                now=now,
                immobility_hours=immobility_hours,
            )

            age_years = self.engine._parse_age_years(patient_doc)
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

            severity = self.engine._risk_severity(score, warning_score, high_score, critical_score)
            if severity in {"high", "critical"}:
                rule_id = f"ICU_AW_RISK_{severity.upper()}"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    explanation = await self.engine._build_icu_aw_explanation(severity=severity, score=score, factors=factors)
                    alert = await self.engine._create_alert(
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
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            level = readiness.get("recommended_level")
            label = readiness.get("recommended_level_label")
            explanation = await self.engine._build_icu_aw_explanation(severity="high", score=score, factors=factors, readiness=readiness)
            alert = await self.engine._create_alert(
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
            self.engine._log_info("ICU-AW/早期活动", triggered)
