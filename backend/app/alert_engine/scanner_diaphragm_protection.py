from __future__ import annotations

from datetime import datetime
from .scanners import BaseScanner, ScannerSpec


class DiaphragmProtectionScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="diaphragm_protection",
                interval_key="diaphragm_protection",
                default_interval=900,
                initial_delay=34,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._diaphragm_cfg()
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "weight": 1, "bodyWeight": 1, "weightKg": 1, "weight_kg": 1},
        )
        patients = [p async for p in patient_cursor]
        triggered = 0
        now = datetime.now()

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            active_bind = await self.engine._get_active_vent_bind(pid_str) if hasattr(self, "_get_active_vent_bind") else None
            if not active_bind:
                continue
            vent_days = await self.engine._get_current_ventilation_days(pid_str, now) if hasattr(self, "_get_current_ventilation_days") else 0.0
            if vent_days < float(cfg.get("min_ventilation_days", 0.5)):
                continue

            device_id = active_bind.get("deviceID")
            cap = await self.engine._get_latest_device_cap(device_id) if device_id else None
            if not cap:
                continue

            rr_measured = self.engine._vent_param_priority(cap, ["rr_measured", "rr_set"], ["param_vent_resp", "param_HuXiPinLv"])
            rr_set = self.engine._vent_param(cap, "rr_set", "param_HuXiPinLv")
            vte_ml = self.engine._vent_param_priority(cap, ["vte", "vt_set"], ["param_vent_vt", "param_vent_set_vt"])
            peep = self.engine._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
            pip = self.engine._vent_param(cap, "pip", "param_vent_pip")
            pplat = self.engine._vent_param(cap, "pplat", "param_vent_plat_pressure")
            weight_kg = self.engine._get_patient_weight(patient_doc) or 70.0
            vt_ml_kg = round(float(vte_ml) / float(weight_kg), 2) if vte_ml is not None and weight_kg > 0 else None
            latest_rass = await self.engine._get_latest_assessment(pid, "rass")
            accessory = await self.engine._get_accessory_muscle_sign(pid, now, hours=12) if hasattr(self, "_get_accessory_muscle_sign") else None
            drive = await self.engine._latest_diaphragm_drive(pid, device_id)

            underassist = False
            overassist = False
            evidence: list[str] = []
            suggestion = ""
            severity = "warning"

            if (
                (drive.get("edi") is not None and float(drive["edi"]) >= float(cfg.get("edi_high_threshold", 15)))
                or (drive.get("pdi") is not None and float(drive["pdi"]) >= float(cfg.get("pdi_high_threshold", 12)))
                or (drive.get("p0_1") is not None and float(drive["p0_1"]) >= float(cfg.get("p0_1_high_threshold", 3.5)))
                or (rr_measured is not None and float(rr_measured) >= float(cfg.get("rr_high_threshold", 30)) and accessory)
            ):
                underassist = True
                severity = "high"
                if drive.get("edi") is not None:
                    evidence.append(f"Edi {drive.get('edi')}")
                if drive.get("pdi") is not None:
                    evidence.append(f"Pdi {drive.get('pdi')} cmH2O")
                if drive.get("p0_1") is not None:
                    evidence.append(f"P0.1 {drive.get('p0_1')}")
                if rr_measured is not None:
                    evidence.append(f"RR {rr_measured}")
                if accessory:
                    evidence.append("存在辅助呼吸肌动用")
                suggestion = "提示吸气驱动偏高，建议复核触发敏感度、压力支持/镇静镇痛与呼吸负荷，避免膈肌过度用力。"

            elif (
                (drive.get("edi") is not None and float(drive["edi"]) <= float(cfg.get("edi_low_threshold", 5)))
                or (drive.get("pdi") is not None and float(drive["pdi"]) <= float(cfg.get("pdi_low_threshold", 3)))
                or (
                    latest_rass is not None
                    and float(latest_rass) <= float(cfg.get("deep_sedation_rass_threshold", -3))
                    and rr_measured is not None
                    and rr_set is not None
                    and float(rr_measured) <= float(rr_set) + 1
                )
            ):
                overassist = True
                if drive.get("edi") is not None:
                    evidence.append(f"Edi {drive.get('edi')}")
                if drive.get("pdi") is not None:
                    evidence.append(f"Pdi {drive.get('pdi')} cmH2O")
                if latest_rass is not None:
                    evidence.append(f"RASS {latest_rass}")
                if rr_measured is not None and rr_set is not None:
                    evidence.append(f"RR测量/设定 {rr_measured}/{rr_set}")
                if vt_ml_kg is not None:
                    evidence.append(f"VT {vt_ml_kg} mL/kg")
                suggestion = "提示膈肌负荷过低，建议评估是否过度辅助，结合镇静深度、支持水平与SAT/SBT计划下调辅助。"

            if not (underassist or overassist):
                continue

            if pplat is not None and peep is not None and float(pplat) - float(peep) > float(cfg.get("driving_pressure_warning", 15)):
                evidence.append(f"Driving pressure {round(float(pplat) - float(peep), 1)}")
                severity = "high"
            if pip is not None and peep is not None and float(pip) - float(peep) > float(cfg.get("pressure_swing_warning", 15)):
                evidence.append(f"PIP-PEEP {round(float(pip) - float(peep), 1)}")

            alert_type = "diaphragm_underassist" if underassist else "diaphragm_overassist"
            rule_id = "VENT_DIAPHRAGM_UNDERASSIST" if underassist else "VENT_DIAPHRAGM_OVERASSIST"
            name = "膈肌保护性通气提示: 驱动偏高" if underassist else "膈肌保护性通气提示: 可能过度辅助"
            value = drive.get("edi")
            if value is None:
                value = drive.get("pdi")
            if value is None:
                value = rr_measured
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            explanation = await self.engine._polish_structured_alert_explanation(
                {
                    "summary": "机械通气过程中出现膈肌负荷异常信号，建议按膈肌保护策略复核通气支持。",
                    "evidence": evidence[:5],
                    "suggestion": suggestion,
                    "text": "",
                }
            )
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name=name,
                category="ventilator",
                alert_type=alert_type,
                severity=severity,
                parameter="diaphragm_drive",
                condition={
                    "ventilation_days_min": float(cfg.get("min_ventilation_days", 0.5)),
                    "edi_low_threshold": float(cfg.get("edi_low_threshold", 5)),
                    "edi_high_threshold": float(cfg.get("edi_high_threshold", 15)),
                },
                value=value,
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                source_time=drive.get("time") or cap.get("time") or now,
                extra={
                    "ventilation_days": vent_days,
                    "edi": drive.get("edi"),
                    "pdi": drive.get("pdi"),
                    "p0_1": drive.get("p0_1"),
                    "rr_measured": rr_measured,
                    "rr_set": rr_set,
                    "vte_ml": vte_ml,
                    "vt_ml_kg": vt_ml_kg,
                    "peep": peep,
                    "pip": pip,
                    "pplat": pplat,
                    "latest_rass": latest_rass,
                    "accessory_muscle_use": bool(accessory),
                    "mode": "underassist" if underassist else "overassist",
                },
                explanation=explanation,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("膈肌保护", triggered)
