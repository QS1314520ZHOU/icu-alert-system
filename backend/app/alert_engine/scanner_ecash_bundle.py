from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class EcashBundleScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="ecash_bundle",
                interval_key="ecash_bundle",
                default_interval=600,
                initial_delay=66,
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

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            status = await self.engine.get_ecash_status(patient_doc)
            analgesia = status.get("analgesia") or {}
            sedation = status.get("sedation") or {}
            delirium = status.get("delirium") or {}

            # 1. 疼痛评估过期
            pain_hours = analgesia.get("last_assessed_hours_ago")
            if analgesia.get("status") == "red" and pain_hours is not None and float(pain_hours) > 8:
                rule_id = "ECASH_PAIN_ASSESSMENT_OVERDUE"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
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
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
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
                gap = self.engine._sedation_off_target_gap(float(latest_rass), target_low, target_high) or 0.0
                severity = "warning" if gap <= 1 else "high"
                rule_id = "ECASH_RASS_OFF_TARGET"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    over_sedation = bool(sedation.get("over_sedation"))
                    alert = await self.engine._create_alert(
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
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
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
            benzo_kw = self.engine._get_cfg_list(
                ("alert_engine", "ecash", "benzo_keywords"),
                ["咪达唑仑", "地西泮", "劳拉西泮", "阿普唑仑", "艾司唑仑", "氯硝西泮"],
            )
            benzo_drugs = [x for x in (sedation.get("current_sedatives") or []) if self.engine._match_name_keywords(x, benzo_kw)]
            if benzo_drugs:
                rule_id = "ECASH_BENZO_IN_USE"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
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
            sat_stress = await self.engine._detect_sat_stress_reaction(patient_doc, status.get("updated_at") or datetime.now())
            if sat_stress:
                rule_id = str(sat_stress.get("rule_id") or "ECASH_SAT_STRESS_REACTION")
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
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
            self.engine._log_info("eCASH", triggered)
