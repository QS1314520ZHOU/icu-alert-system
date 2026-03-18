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
from .scanners import BaseScanner, ScannerSpec


class VentilatorWeaningScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="ventilator",
                interval_key="ventilator",
                default_interval=3600,
                initial_delay=40,
            ),
        )

    async def scan(self) -> None:
        now = datetime.now()

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "height": 1, "heightCm": 1, "gender": 1, "hisSex": 1, "weight": 1, "bodyWeight": 1, "weightKg": 1, "weight_kg": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        post_cfg = self.engine._weaning_cfg()
        extub_hours = int(post_cfg.get("extubation_monitor_hours", 48))
        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)

            active_vent_bind = await self.engine._get_active_vent_bind(pid_str)
            device_id = active_vent_bind.get("deviceID") if active_vent_bind else await self.engine._get_device_id_for_patient(patient_doc, ["vent"])
            cap = await self.engine._get_latest_device_cap(device_id) if device_id else None

            if active_vent_bind and cap:
                risk = await self.engine._build_weaning_recommendation(patient_doc=patient_doc, pid_str=pid_str, cap=cap, now=now)
                if risk:
                    await self.engine._persist_weaning_assessment(
                        pid_str=pid_str,
                        patient_doc=patient_doc,
                        now=now,
                        assessment=risk,
                    )
                    sbt = (risk.get("extra") or {}).get("previous_sbt")
                    if isinstance(sbt, dict):
                        await self.engine._persist_sbt_assessment(
                            pid_str=pid_str,
                            patient_doc=patient_doc,
                            now=now,
                            sbt=sbt,
                        )
                    rule_id = risk["rule_id"]
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name=risk["name"],
                            category="ventilator",
                            alert_type="weaning",
                            severity=risk["severity"],
                            parameter="weaning_failure_score",
                            condition={"recommendation": risk["recommendation"], "risk_level": risk["risk_level"]},
                            value=risk["risk_score"],
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                            extra=risk["extra"],
                            explanation=risk["explanation"],
                        )
                        if alert:
                            triggered += 1

                fio2 = self.engine._vent_param(cap, "fio2", "param_FiO2")
                peep = self.engine._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
                pip = self.engine._vent_param(cap, "pip", "param_vent_pip")
                pplat = self.engine._vent_param(cap, "pplat", "param_vent_plat_pressure")
                vte = self.engine._vent_param_priority(cap, ["vte", "vt_set"], ["param_vent_vt", "param_vent_set_vt"])
                rr = self.engine._vent_param_priority(cap, ["rr_measured", "rr_set"], ["param_vent_resp", "param_HuXiPinLv"])

                driving_pressure = None
                approximate = False
                if pplat is not None and peep is not None:
                    driving_pressure = pplat - peep
                elif pip is not None and peep is not None:
                    driving_pressure = pip - peep
                    approximate = True

                if driving_pressure is not None and driving_pressure > 15:
                    rule_id = "VENT_DRIVING_PRESSURE"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="驱动压偏高",
                            category="ventilator",
                            alert_type="driving_pressure",
                            severity="critical" if driving_pressure > 18 else "warning",
                            parameter="driving_pressure",
                            condition={"operator": ">", "threshold": 15},
                            value=round(driving_pressure, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                            extra={"pplat": pplat, "pip": pip, "peep": peep, "approximate": approximate},
                        )
                        if alert:
                            triggered += 1

                if pplat is not None and pplat > 30:
                    rule_id = "VENT_PPLAT_HIGH"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="平台压升高",
                            category="ventilator",
                            alert_type="pplat_high",
                            severity="critical",
                            parameter="pplat",
                            condition={"operator": ">", "threshold": 30},
                            value=round(pplat, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                            extra={"recommendation": "考虑降低潮气量或评估胸壁顺应性"},
                        )
                        if alert:
                            triggered += 1

                pbw = self.engine._predicted_body_weight(patient_doc)
                if vte is not None and pbw and pbw > 0:
                    vt_ml_kg = vte / pbw
                    if vt_ml_kg > 8:
                        rule_id = "VENT_LUNG_PROTECTIVE"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="肺保护性通气未达标",
                                category="ventilator",
                                alert_type="lung_protective_ventilation",
                                severity="warning",
                                parameter="vt_ml_kg_pbw",
                                condition={"operator": ">", "threshold": 8},
                                value=round(vt_ml_kg, 2),
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=device_id,
                                source_time=cap.get("time"),
                                extra={"vte_ml": vte, "predicted_body_weight": pbw},
                            )
                            if alert:
                                triggered += 1

                if rr is not None and vte is not None and pip is not None and peep is not None:
                    vt_l = vte / 1000.0
                    mech_power = 0.098 * rr * vt_l * (pip - 0.5 * max(pip - peep, 0))
                    if mech_power > 17:
                        rule_id = "VENT_MECHANICAL_POWER"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="机械功率升高",
                                category="ventilator",
                                alert_type="mechanical_power",
                                severity="high",
                                parameter="mechanical_power",
                                condition={"operator": ">", "threshold": 17},
                                value=round(mech_power, 2),
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=device_id,
                                source_time=cap.get("time"),
                                extra={"rr": rr, "vte_ml": vte, "pip": pip, "peep": peep},
                            )
                            if alert:
                                triggered += 1

            recent_extubation = await self.engine._get_recent_extubation_bind(pid_str, now, hours=extub_hours)
            if recent_extubation and not active_vent_bind:
                extub_time = _parse_dt(recent_extubation.get("unBindTime"))
                vitals = await self.engine._get_latest_vitals_by_patient(pid)
                rr_now = vitals.get("rr") if isinstance(vitals, dict) else None
                spo2_now = vitals.get("spo2") if isinstance(vitals, dict) else None
                accessory = await self.engine._get_accessory_muscle_sign(pid, now, hours=12)
                if rr_now is not None and float(rr_now) > float(post_cfg.get("post_extub_rr_threshold", 30)) and spo2_now is not None and float(spo2_now) < float(post_cfg.get("post_extub_spo2_threshold", 92)):
                    severity = "critical" if accessory else "high"
                    rule_id = "VENT_POST_EXTUBATION_FAILURE_RISK"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        evidence_factors = [
                            {"factor": "tachypnea", "weight": 1, "evidence": f"RR {rr_now} 次/分"},
                            {"factor": "hypoxemia", "weight": 1, "evidence": f"SpO₂ {spo2_now}%"},
                        ]
                        if accessory:
                            evidence_factors.append({"factor": "accessory_muscle_use", "weight": 1, "evidence": "存在辅助呼吸肌动用"})
                        explanation = await self.engine._polish_structured_alert_explanation(
                            {
                                "summary": "拔管后48h内出现呼吸恶化信号，存在再插管/NIV 风险。",
                                "evidence": [str(x.get("evidence") or "") for x in evidence_factors],
                                "suggestion": "建议立即评估血气、分泌物负荷与上气道通畅性，尽早决定 NIV/HFNC 或再插管。",
                                "text": "",
                            }
                        )
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="拔管后呼吸衰竭风险",
                            category="ventilator",
                            alert_type="post_extubation_failure_risk",
                            severity=severity,
                            parameter="post_extubation_resp_failure",
                            condition={"rr_threshold": 30, "spo2_threshold": 92, "extubation_window_h": extub_hours},
                            value=round(float(rr_now), 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=extub_time or now,
                            extra={
                                "extubation_time": extub_time,
                                "hours_since_extubation": round(max(0.0, ((now - extub_time).total_seconds() / 3600.0)) if isinstance(extub_time, datetime) else 0.0, 2),
                                "rr": rr_now,
                                "spo2": spo2_now,
                                "accessory_muscle_use": bool(accessory),
                                "accessory_muscle_record": accessory,
                                "factors": evidence_factors,
                            },
                            explanation=explanation,
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self.engine._log_info("撤机筛查", triggered)
