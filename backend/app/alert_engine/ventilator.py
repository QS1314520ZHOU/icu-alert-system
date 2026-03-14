"""呼吸机撤离筛查"""
from __future__ import annotations

from datetime import datetime


class VentilatorMixin:
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

    async def scan_ventilator_weaning(self) -> None:
        now = datetime.now()

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "height": 1, "heightCm": 1, "gender": 1, "hisSex": 1},
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
            device_id = await self._get_device_id_for_patient(patient_doc, ["vent"])
            if not device_id:
                continue

            cap = await self._get_latest_device_cap(device_id)
            if not cap:
                continue

            fio2 = self._vent_param(cap, "fio2", "param_FiO2")
            peep = self._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
            gcs = await self._get_latest_assessment(pid, "gcs")
            map_snapshot = await self._get_latest_param_snapshot_by_pid(pid, codes=["param_ibp_m", "param_nibp_m"])
            if not map_snapshot:
                monitor_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])
                map_snapshot = await self._get_latest_device_cap(monitor_id, codes=["param_ibp_m", "param_nibp_m"]) if monitor_id else None
            map_value = self._get_map(map_snapshot) if map_snapshot else None
            on_vaso = await self._has_vasopressor(pid)
            pip = self._vent_param(cap, "pip", "param_vent_pip")
            pplat = self._vent_param(cap, "pplat", "param_vent_plat_pressure")
            vte = self._vent_param_priority(cap, ["vte", "vt_set"], ["param_vent_vt", "param_vent_set_vt"])
            rr = self._vent_param_priority(cap, ["rr_measured", "rr_set"], ["param_vent_resp", "param_HuXiPinLv"])

            if fio2 is not None and peep is not None:
                fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
                if fio2_frac <= 0.4 and peep <= 8 and (map_value is None or map_value >= 65) and (not on_vaso) and (gcs is None or gcs >= 9) and (8 <= now.hour <= 10):
                    rule_id = "VENT_WEAN_READY"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="建议评估SBT自主呼吸试验",
                            category="ventilator",
                            alert_type="weaning",
                            severity="warning",
                            parameter="weaning_ready",
                            condition={"fio2": fio2, "peep": peep, "map": map_value},
                            value=None,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                            extra={"fio2": fio2, "peep": peep, "gcs": gcs, "map": map_value},
                        )
                        if alert:
                            triggered += 1

            # 呼吸力学连续监测
            driving_pressure = None
            approximate = False
            if pplat is not None and peep is not None:
                driving_pressure = pplat - peep
            elif pip is not None and peep is not None:
                driving_pressure = pip - peep
                approximate = True

            if driving_pressure is not None and driving_pressure > 15:
                rule_id = "VENT_DRIVING_PRESSURE"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
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
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
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

            pbw = self._predicted_body_weight(patient_doc)
            if vte is not None and pbw and pbw > 0:
                vt_ml_kg = vte / pbw
                if vt_ml_kg > 8:
                    rule_id = "VENT_LUNG_PROTECTIVE"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
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
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
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

        if triggered > 0:
            self._log_info("撤机筛查", triggered)

