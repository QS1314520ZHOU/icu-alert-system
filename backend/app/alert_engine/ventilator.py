"""呼吸机撤离筛查"""
from __future__ import annotations

from datetime import datetime


class VentilatorMixin:
    async def scan_ventilator_weaning(self) -> None:
        now = datetime.now()
        if not (8 <= now.hour <= 10):
            return

        binds = [b async for b in self.db.col("deviceBind").find({"unBindTime": None}, {"pid": 1, "deviceID": 1})]
        if not binds:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for b in binds:
            pid = b.get("pid")
            device_id = b.get("deviceID")
            if not pid or not device_id:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not patient_doc or not pid_str:
                continue

            cap = await self._get_latest_device_cap(device_id)
            if not cap:
                continue

            fio2 = self._vent_param(cap, "fio2", "param_FiO2")
            peep = self._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
            gcs = await self._get_latest_assessment(pid, "gcs")
            map_value = self._get_map(cap)
            on_vaso = await self._has_vasopressor(pid)

            if fio2 is None or peep is None:
                continue

            fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
            if fio2_frac > 0.4 or peep > 8:
                continue
            if map_value is not None and map_value < 65:
                continue
            if on_vaso:
                continue
            if gcs is not None and gcs < 9:
                continue

            rule_id = "VENT_WEAN_READY"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

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

        if triggered > 0:
            self._log_info("撤机筛查", triggered)

