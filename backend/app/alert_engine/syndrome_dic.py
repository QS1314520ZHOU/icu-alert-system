"""DIC ISTH"""
from __future__ import annotations


class DicMixin:
    async def scan_dic(self) -> None:
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

            diag = (str(p.get("clinicalDiagnosis", "")) + str(p.get("admissionDiagnosis", ""))).lower()
            high_risk = any(k in diag for k in ["脓毒", "感染", "sepsis", "创伤", "肿瘤", "恶性", "产后"])
            if not high_risk:
                continue

            dic = await self._calc_dic_score(his_pid)
            if not dic:
                continue

            total = dic["score"]
            if total < 3:
                continue

            rule_id = "DIC_OVERT" if total >= 5 else "DIC_SUSPECT"
            severity = "critical" if total >= 5 else "warning"
            name = "显性DIC" if total >= 5 else "疑似DIC"

            if await self._is_suppressed(str(p.get("_id")), rule_id, same_rule_sec, max_per_hour):
                continue

            alert = await self._create_alert(
                rule_id=rule_id,
                name=name,
                category="syndrome",
                alert_type="dic",
                severity=severity,
                parameter="dic_score",
                condition={"score": total},
                value=total,
                patient_id=str(p.get("_id")),
                patient_doc=p,
                device_id=None,
                source_time=dic.get("time"),
                extra=dic,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("DIC预警", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条预警")