"""导管/气道装置管理与 bundle 风险。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class DeviceManagementMixin:
    async def _infer_device_insert_time(self, pid, keywords: list[str], hours: int = 24 * 30) -> datetime | None:
        events = await self._get_recent_text_events(pid, keywords, hours=hours, limit=2000)
        times = [e.get("time") for e in events if e.get("time")]
        if not times:
            return None
        return min(times)

    async def _has_central_line_indication(self, pid) -> bool:
        vaso = await self._has_vasopressor(pid)
        if vaso:
            return True
        tpn = await self._has_recent_drug(pid, ["tpn", "全肠外", "肠外营养", "静脉营养", "脂肪乳", "复方氨基酸"], hours=24)
        if tpn:
            return True
        return False

    async def _device_management_summary(self, patient_doc: dict) -> dict[str, Any]:
        pid = patient_doc.get("_id")
        if not pid:
            return {"devices": [], "max_risk": "low"}
        now = datetime.now()
        pid_str = str(pid)
        his_pid = patient_doc.get("hisPid")
        aki = await self._calc_aki_stage(patient_doc, pid, his_pid) if his_pid else None
        on_vaso = await self._has_vasopressor(pid)

        cvc_time = await self._infer_device_insert_time(pid, ["中心静脉", "cvc", "picc", "深静脉", "central line"])
        foley_time = await self._infer_device_insert_time(pid, ["导尿", "foley", "尿管", "导尿管"])
        ett_time = await self._infer_device_insert_time(pid, ["气管插管", "ett", "endotracheal", "经口气管插管"])

        devices: list[dict[str, Any]] = []
        max_risk = "low"

        if cvc_time:
            line_days = max(1, (now - cvc_time).days + 1)
            indication = await self._has_central_line_indication(pid)
            risk = "high" if line_days >= 7 else "medium" if line_days >= 3 else "low"
            if risk == "high":
                max_risk = "high"
            elif risk == "medium" and max_risk != "high":
                max_risk = "medium"
            devices.append({
                "type": "cvc",
                "line_days": line_days,
                "inserted_at": cvc_time,
                "risk": risk,
                "needs_assessment": line_days >= 3,
                "can_remove": (line_days >= 3 and not indication) or line_days >= 7,
            })

        if foley_time:
            line_days = max(1, (now - foley_time).days + 1)
            strict_uo = bool(aki and aki.get("stage", 0) >= 3)
            spontaneous_void = not any(k in str(patient_doc.get("clinicalDiagnosis", "")).lower() for k in ["尿潴留", "前列腺", "retention"])
            can_remove = (not on_vaso) and (not strict_uo) and spontaneous_void
            risk = "high" if line_days >= 7 else "medium" if line_days >= 3 else "low"
            if risk == "high":
                max_risk = "high"
            elif risk == "medium" and max_risk != "high":
                max_risk = "medium"
            devices.append({
                "type": "foley",
                "line_days": line_days,
                "inserted_at": foley_time,
                "risk": risk,
                "needs_assessment": True,
                "can_remove": can_remove,
            })

        if ett_time:
            line_days = max(1, (now - ett_time).days + 1)
            sbt_alert = await self._get_latest_active_alert(pid_str, ["weaning"], hours=48)
            overdue = False
            if sbt_alert and isinstance(sbt_alert.get("created_at"), datetime):
                overdue = (now - sbt_alert["created_at"]).total_seconds() >= 24 * 3600
            risk = "high" if overdue else "medium" if line_days >= 3 else "low"
            if risk == "high":
                max_risk = "high"
            elif risk == "medium" and max_risk != "high":
                max_risk = "medium"
            devices.append({
                "type": "ett",
                "line_days": line_days,
                "inserted_at": ett_time,
                "risk": risk,
                "sbt_passed_no_extubation": overdue,
            })

        return {"devices": devices, "max_risk": max_risk}

    async def scan_device_management(self) -> None:
        now = datetime.now()
        if not (7 <= now.hour <= 9):
            return

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "clinicalDiagnosis": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for patient_doc in patients:
            summary = await self._device_management_summary(patient_doc)
            pid_str = str(patient_doc.get("_id"))
            for device in summary.get("devices", []):
                if device["type"] == "cvc" and device.get("can_remove"):
                    rule_id = "DEVICE_CVC_REVIEW"
                    if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="CVC必要性评估",
                        category="device_management",
                        alert_type="cvc_review",
                        severity="high" if device.get("line_days", 0) >= 7 else "warning",
                        parameter="cvc_line_days",
                        condition={"operator": ">=", "threshold": 3},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device,
                    )
                    if alert:
                        triggered += 1

                if device["type"] == "foley" and device.get("can_remove"):
                    rule_id = "DEVICE_FOLEY_REVIEW"
                    if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="导尿管必要性评估",
                        category="device_management",
                        alert_type="foley_review",
                        severity="warning",
                        parameter="foley_line_days",
                        condition={"operator": ">=", "threshold": 1},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device,
                    )
                    if alert:
                        triggered += 1

                if device["type"] == "ett" and device.get("sbt_passed_no_extubation"):
                    rule_id = "DEVICE_ETT_EXTUBATION_DELAY"
                    if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="SBT通过后24h未尝试拔管",
                        category="device_management",
                        alert_type="ett_extubation_delay",
                        severity="high",
                        parameter="ett_line_days",
                        condition={"operator": ">=", "threshold_hours": 24},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device,
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self._log_info("装置管理", triggered)

