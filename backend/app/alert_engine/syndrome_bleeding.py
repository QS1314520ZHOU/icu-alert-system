"""消化道出血识别"""
from __future__ import annotations


class BleedingMixin:
    async def scan_bleeding(self) -> None:
        patient_cursor = self.db.col("patient").find(
            {"isLeave": {"$ne": True}},
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
             "clinicalDiagnosis": 1, "admissionDiagnosis": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for p in patients:
            his_pid = p.get("hisPid")
            if not his_pid:
                continue

            hb_drop = await self._get_hb_drop(his_pid, hours=24)
            if not hb_drop or hb_drop["drop"] < 20:
                continue

            pid_str = str(p.get("_id"))
            latest_vitals = await self._get_latest_vitals_by_patient(p.get("_id"))
            hr = latest_vitals.get("hr")
            sbp = latest_vitals.get("sbp")

            diag = (str(p.get("clinicalDiagnosis", "")) + str(p.get("admissionDiagnosis", ""))).lower()
            has_bleed_tag = any(k in diag for k in ["消化道出血", "黑便", "呕血", "hematemesis", "melena"])

            severity = "warning"
            name = "疑似消化道出血"
            if hb_drop["current"] is not None and hb_drop["current"] < 60 and (hr and hr > 110) and (sbp and sbp < 90):
                severity = "critical"
                name = "消化道出血(休克风险)"
            elif hb_drop["current"] is not None and hb_drop["current"] < 70 and (hr and hr > 110):
                severity = "high"
                name = "消化道出血风险"

            if not has_bleed_tag and severity == "warning":
                continue

            rule_id = f"GI_BLEED_{severity.upper()}"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            alert = await self._create_alert(
                rule_id=rule_id,
                name=name,
                category="syndrome",
                alert_type="gi_bleeding",
                severity=severity,
                parameter="hb_drop",
                condition={"drop": hb_drop["drop"], "hours": 24},
                value=hb_drop["current"],
                patient_id=pid_str,
                patient_doc=p,
                device_id=None,
                source_time=hb_drop.get("time"),
                extra={"hr": hr, "sbp": sbp, "has_bleed_tag": has_bleed_tag},
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("出血预警", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条预警")