"""DIC ISTH"""
from __future__ import annotations

from datetime import datetime, timedelta


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

            pid_str = str(p.get("_id"))
            diag = (str(p.get("clinicalDiagnosis", "")) + str(p.get("admissionDiagnosis", ""))).lower()
            dic_risk_kw = [
                "脓毒", "感染", "sepsis", "创伤", "trauma",
                "肿瘤", "恶性", "cancer", "产后", "产科",
                "烧伤", "burn", "移植", "transplant",
                "胰腺炎", "pancreatitis", "蛇咬",
                "大手术", "hellp", "羊水栓塞",
            ]
            high_risk = any(k in diag for k in dic_risk_kw)
            if not high_risk:
                recent_sepsis = await self.db.col("alert_records").find_one({
                    "patient_id": pid_str,
                    "rule_id": {"$in": ["SEPSIS_QSOFA", "SEPSIS_SOFA", "SEPSIS_SHOCK"]},
                    "created_at": {"$gte": datetime.now() - timedelta(hours=24)},
                })
                high_risk = recent_sepsis is not None
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

            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
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
                patient_id=pid_str,
                patient_doc=p,
                device_id=None,
                source_time=dic.get("time"),
                extra=dic,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("DIC预警", triggered)

