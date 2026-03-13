"""药物不良反应/相互作用"""
from __future__ import annotations


class DrugSafetyMixin:
    async def scan_drug_safety(self) -> None:
        patient_cursor = self.db.col("patient").find(
            {"isLeave": {"$ne": True}},
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
             "weight": 1, "bodyWeight": 1, "body_weight": 1, "weightKg": 1, "weight_kg": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        heparin_kw = self._get_cfg_list(("alert_engine", "drug_mapping", "heparin"), ["肝素"])
        vanco_kw = self._get_cfg_list(("alert_engine", "drug_mapping", "vancomycin"), ["万古霉素"])
        sedative_kw = self._get_cfg_list(
            ("alert_engine", "drug_mapping", "sedatives"),
            ["咪达唑仑", "丙泊酚", "右美托咪定", "地西泮", "芬太尼", "瑞芬太尼"],
        )
        qt_drugs = self._get_cfg_list(
            ("alert_engine", "drug_mapping", "qt_risk"),
            ["胺碘酮", "左氧氟沙星", "环丙沙星", "红霉素", "阿奇霉素", "氟哌啶醇", "奥氮平", "喹硫平"],
        )

        triggered = 0
        for p in patients:
            pid = p.get("_id")
            if not pid:
                continue

            pid_str = str(pid)
            drugs = await self._get_recent_drugs(pid, hours=72)
            if not drugs:
                continue

            if any(any(k in d for k in heparin_kw) for d in drugs):
                his_pid = p.get("hisPid")
                if his_pid:
                    plt_drop = await self._get_platelet_drop(his_pid, days=7)
                    if plt_drop and plt_drop["drop_ratio"] >= 0.5:
                        rule_id = "DRUG_HIT"
                        if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self._create_alert(
                                rule_id=rule_id,
                                name="疑似HIT(肝素相关血小板减少)",
                                category="drug_safety",
                                alert_type="hit",
                                severity="high",
                                parameter="plt",
                                condition={"drop_ratio": plt_drop["drop_ratio"]},
                                value=plt_drop["current"],
                                patient_id=pid_str,
                                patient_doc=p,
                                device_id=None,
                                source_time=plt_drop.get("time"),
                                extra=plt_drop,
                            )
                            if alert:
                                triggered += 1

            if any(any(k in d for k in vanco_kw) for d in drugs):
                his_pid = p.get("hisPid")
                if his_pid:
                    aki = await self._calc_aki_stage(p, pid, his_pid)
                    if aki and aki.get("stage", 0) >= 1:
                        rule_id = "DRUG_VANCO_NEPHRO"
                        if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self._create_alert(
                                rule_id=rule_id,
                                name="万古霉素相关肾毒性风险",
                                category="drug_safety",
                                alert_type="nephrotoxicity",
                                severity="warning",
                                parameter="creatinine",
                                condition=aki.get("condition", {}),
                                value=aki.get("current"),
                                patient_id=pid_str,
                                patient_doc=p,
                                device_id=None,
                                source_time=aki.get("time"),
                                extra=aki,
                            )
                            if alert:
                                triggered += 1

            if any(any(k in d for k in sedative_kw) for d in drugs):
                rass_info = await self._get_rass_status(pid)
                if rass_info and rass_info.get("over_sedation"):
                    rule_id = "DRUG_OVER_SEDATION"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="过度镇静风险",
                            category="drug_safety",
                            alert_type="sedation",
                            severity="warning",
                            parameter="rass",
                            condition={"rass": rass_info.get("rass")},
                            value=rass_info.get("rass"),
                            patient_id=pid_str,
                            patient_doc=p,
                            device_id=None,
                            source_time=rass_info.get("time"),
                            extra=rass_info,
                        )
                        if alert:
                            triggered += 1

            qt_count = sum(1 for d in drugs if any(k in d for k in qt_drugs))
            if qt_count >= 2:
                rule_id = "DRUG_QT_RISK"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="QTc延长风险(多种药物)",
                        category="drug_safety",
                        alert_type="qt_risk",
                        severity="warning",
                        parameter="qt_risk",
                        condition={"qt_drugs": qt_count},
                        value=qt_count,
                        patient_id=pid_str,
                        patient_doc=p,
                        device_id=None,
                        source_time=None,
                        extra={"drugs": drugs},
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self._log_info("药物安全", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条预警")