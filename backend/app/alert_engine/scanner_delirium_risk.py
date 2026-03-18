from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
def _to_num(value: Any) -> float | None:
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
def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
def _lab_time(doc: dict) -> datetime | None:
    return (
        _parse_dt(doc.get("authTime"))
        or _parse_dt(doc.get("collectTime"))
        or _parse_dt(doc.get("requestTime"))
        or _parse_dt(doc.get("reportTime"))
        or _parse_dt(doc.get("resultTime"))
        or _parse_dt(doc.get("time"))
    )
def _severity_rank(severity: str) -> int:
    return {"warning": 1, "high": 2, "critical": 3}.get(str(severity), 0)
from .scanners import BaseScanner, ScannerSpec


class DeliriumRiskScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="delirium_risk",
                interval_key="delirium_risk",
                default_interval=900,
                initial_delay=35,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1,
                "age": 1, "hisAge": 1, "admissionType": 1, "admitType": 1, "inType": 1,
                "admissionSource": 1, "admissionWay": 1, "source": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("delirium_risk", {})
        weights = cfg.get("factor_weights", {}) if isinstance(cfg, dict) else {}
        warning_score = float(cfg.get("warning_score", 4))
        high_score = float(cfg.get("high_score", 7))
        critical_score = float(cfg.get("critical_score", 10))

        benzodiazepines = self.engine._get_cfg_list(
            ("alert_engine", "delirium_risk", "benzodiazepine_keywords"),
            ["咪达唑仑", "地西泮", "劳拉西泮", "阿普唑仑", "艾司唑仑", "氯硝西泮"],
        )
        morphine_kw = self.engine._get_cfg_list(
            ("alert_engine", "delirium_risk", "morphine_keywords"),
            ["吗啡", "morphine"],
        )
        sedative_kw = self.engine._get_cfg_list(
            ("alert_engine", "drug_mapping", "sedatives"),
            ["咪达唑仑", "丙泊酚", "右美托咪定", "地西泮", "芬太尼", "瑞芬太尼"],
        )

        triggered_risk = 0
        triggered_conversion = 0
        now = datetime.now()

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            cam_status = await self.engine._get_latest_cam_icu_status(pid, lookback_hours=24)
            if cam_status and cam_status.get("positive"):
                rule_id = "DELIRIUM_CAM_ICU_POSITIVE"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="CAM-ICU 阳性：谵妄已发生",
                        category="syndrome",
                        alert_type="cam_icu_positive",
                        severity="critical",
                        parameter="cam_icu",
                        condition={"operator": "positive"},
                        value=1,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=cam_status.get("time") or now,
                        extra=cam_status,
                    )
                    if alert:
                        triggered_risk += 1
                continue

            age_years = self.engine._parse_age_years(patient_doc)
            has_age_risk = age_years is not None and age_years > 65

            drugs_24h = await self.engine._get_recent_drugs(pid, hours=24)
            has_benzo = self.engine._contains_any(drugs_24h, benzodiazepines)
            has_morphine = self.engine._contains_any(drugs_24h, morphine_kw)
            has_sedatives = self.engine._contains_any(drugs_24h, sedative_kw)

            emergency_adm = self.engine._is_emergency_admission(patient_doc)
            mech_vent = await self.engine._has_mechanical_ventilation(patient_doc)

            his_pid = patient_doc.get("hisPid")
            labs = await self.engine._load_delirium_labs(his_pid, lookback_hours=72) if his_pid else {}
            bun_high = self.engine._bun_is_high(labs.get("bun"))
            has_acidosis, acidosis_flags = self.engine._metabolic_acidosis(labs)

            latest_rass = await self.engine._get_latest_assessment(pid, "rass")
            latest_gcs = await self.engine._get_latest_assessment(pid, "gcs")
            deep_sed_hours = await self.engine._deep_sedation_duration_hours(pid, hours=48)
            deep_sed_over_24h = deep_sed_hours > 24

            factors: list[dict] = []
            score = 0.0

            def add_factor(key: str, matched: bool, evidence: str, default_weight: float):
                nonlocal score
                if not matched:
                    return
                w = float(weights.get(key, default_weight))
                score += w
                factors.append({"factor": key, "weight": w, "evidence": evidence})

            add_factor("age_gt_65", has_age_risk, f"年龄={age_years}", 1.0)
            add_factor("benzodiazepine", has_benzo, "24h内使用苯二氮卓类镇静药", 2.0)
            add_factor("emergency_admission", emergency_adm, "急诊入院", 1.0)
            add_factor("mechanical_ventilation", mech_vent, "存在机械通气支持", 2.0)
            add_factor("metabolic_acidosis", has_acidosis, f"代谢性酸中毒证据={acidosis_flags}", 2.0)
            add_factor("morphine_use", has_morphine, "24h内使用吗啡", 1.0)
            add_factor("bun_elevated", bun_high, f"BUN={labs.get('bun')}", 2.0)
            add_factor("deep_sedation", latest_rass is not None and latest_rass < -3, f"RASS={latest_rass}", 1.0)
            add_factor("gcs_low", latest_gcs is not None and latest_gcs < 13, f"GCS={latest_gcs}", 1.0)

            severity = None
            if score >= critical_score:
                severity = "critical"
            elif score >= high_score:
                severity = "high"
            elif score >= warning_score:
                severity = "warning"

            if severity:
                rule_id = f"DELIRIUM_RISK_{severity.upper()}"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="谵妄高风险(PRE-DELIRIC近似)",
                        category="syndrome",
                        alert_type="delirium_risk",
                        severity=severity,
                        parameter="delirium_risk_score",
                        condition={
                            "model": "PRE-DELIRIC-approx",
                            "score": round(score, 2),
                            "warning_score": warning_score,
                            "high_score": high_score,
                            "critical_score": critical_score,
                        },
                        value=round(score, 2),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        extra={
                            "factors": factors,
                            "observations": {
                                "age_years": age_years,
                                "latest_rass": latest_rass,
                                "latest_gcs": latest_gcs,
                                "labs": labs,
                                "deep_sedation_hours": round(deep_sed_hours, 2),
                            },
                        },
                    )
                    if alert:
                        triggered_risk += 1

            # 第三层：镇静药 + RASS<-3 持续>24h，触发转化预警
            if has_sedatives and deep_sed_over_24h:
                conversion_sev = "high"
                if latest_gcs is not None and latest_gcs <= 8:
                    conversion_sev = "critical"
                if _severity_rank(severity or "") >= _severity_rank("high"):
                    conversion_sev = "critical"
                rule_id = f"DELIRIUM_CONVERSION_{conversion_sev.upper()}"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="过度镇静向谵妄转化风险",
                        category="drug_safety",
                        alert_type="sedation_delirium_conversion",
                        severity=conversion_sev,
                        parameter="rass",
                        condition={
                            "requires": "sedative + RASS<-3 >24h",
                            "deep_sedation_hours": round(deep_sed_hours, 2),
                        },
                        value=latest_rass,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        extra={
                            "latest_rass": latest_rass,
                            "latest_gcs": latest_gcs,
                            "deep_sedation_hours": round(deep_sed_hours, 2),
                            "sedatives_24h": [d for d in drugs_24h if any(k in d for k in sedative_kw)],
                        },
                    )
                    if alert:
                        triggered_conversion += 1

        if triggered_risk > 0:
            self.engine._log_info("谵妄风险", triggered_risk)
        if triggered_conversion > 0:
            self.engine._log_info("谵妄转化", triggered_conversion)
