"""检验结果自动扫描"""
from __future__ import annotations

from datetime import datetime

from .base import _eval_condition


class LabScannerMixin:
    async def scan_lab_results(self) -> None:
        now = datetime.now()
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        patient_cursor = self.db.col("patient").find(
            {"isLeave": {"$ne": True}},
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        lab_rules = [
            {"rule_id": "LAB_K_CRIT_HIGH", "test": "k", "name": "高钾血症(危急)", "condition": {">": 6.5}, "severity": "critical"},
            {"rule_id": "LAB_K_HIGH", "test": "k", "name": "高钾血症", "condition": {">": 5.5}, "severity": "warning"},
            {"rule_id": "LAB_K_CRIT_LOW", "test": "k", "name": "低钾血症(危急)", "condition": {"<": 2.5}, "severity": "critical"},
            {"rule_id": "LAB_K_LOW", "test": "k", "name": "低钾血症", "condition": {"<": 3.0}, "severity": "warning"},
            {"rule_id": "LAB_NA_CRIT_HIGH", "test": "na", "name": "高钠血症(危急)", "condition": {">": 160}, "severity": "critical"},
            {"rule_id": "LAB_NA_CRIT_LOW", "test": "na", "name": "低钠血症(危急)", "condition": {"<": 120}, "severity": "critical"},
            {"rule_id": "LAB_ICA_LOW", "test": "ica", "name": "低离子钙", "condition": {"<": 0.8}, "severity": "high"},
            {"rule_id": "LAB_LAC_HIGH", "test": "lac", "name": "乳酸升高", "condition": {">": 2.0}, "severity": "warning"},
            {"rule_id": "LAB_LAC_CRIT", "test": "lac", "name": "乳酸危急", "condition": {">": 4.0}, "severity": "critical"},
            {"rule_id": "LAB_GLU_LOW", "test": "glu", "name": "低血糖", "condition": {"<": 3.0}, "severity": "critical"},
            {"rule_id": "LAB_GLU_HIGH", "test": "glu", "name": "高血糖", "condition": {">": 20.0}, "severity": "warning"},
            {"rule_id": "LAB_HB_CRIT", "test": "hb", "name": "重度贫血", "condition": {"<": 60}, "severity": "critical"},
            {"rule_id": "LAB_HB_LOW", "test": "hb", "name": "贫血", "condition": {"<": 70}, "severity": "warning"},
            {"rule_id": "LAB_PLT_CRIT", "test": "plt", "name": "严重血小板减少", "condition": {"<": 20}, "severity": "critical"},
            {"rule_id": "LAB_PLT_LOW", "test": "plt", "name": "血小板减少", "condition": {"<": 50}, "severity": "warning"},
            {"rule_id": "LAB_PCT_CRIT", "test": "pct", "name": "PCT危急升高", "condition": {">": 10}, "severity": "critical"},
            {"rule_id": "LAB_PCT_HIGH", "test": "pct", "name": "PCT升高", "condition": {">": 2}, "severity": "warning"},
            {"rule_id": "LAB_INR_HIGH", "test": "inr", "name": "INR升高", "condition": {">": 3.0}, "severity": "warning"},
            {"rule_id": "LAB_TROP_HIGH", "test": "trop", "name": "肌钙蛋白显著升高", "condition": {">": 5.0}, "severity": "high"},
            {"rule_id": "LAB_BNP_HIGH", "test": "bnp", "name": "BNP/NT-proBNP升高", "condition": {">": 1000}, "severity": "warning"},
        ]

        triggered = 0
        for p in patients:
            his_pid = p.get("hisPid")
            if not his_pid:
                continue

            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
            if not labs:
                continue

            pid_str = str(p.get("_id"))

            for rule in lab_rules:
                item = labs.get(rule["test"])
                if not item:
                    continue
                value = item["value"]
                raw_flag = str(item.get("raw_flag") or "").strip()

                rule_id = rule["rule_id"]
                severity = rule["severity"]
                name = rule["name"]
                condition = None

                if rule["test"] == "trop":
                    flag_lower = raw_flag.lower()
                    if ("危急" in raw_flag) or ("critical" in flag_lower) or ("↑↑" in raw_flag):
                        rule_id = "LAB_TROP_CRIT"
                        severity = "critical"
                        name = "肌钙蛋白危急升高"
                        condition = {"flag": raw_flag}
                    elif ("↑" in raw_flag) or ("high" in flag_lower):
                        severity = "high"
                        name = "肌钙蛋白显著升高"
                        condition = {"flag": raw_flag}
                    else:
                        cond = rule["condition"]
                        op, thr = list(cond.items())[0]
                        if not _eval_condition(value, {"operator": op, "threshold": thr}):
                            continue
                        condition = {"operator": op, "threshold": thr}
                else:
                    cond = rule["condition"]
                    op, thr = list(cond.items())[0]
                    if not _eval_condition(value, {"operator": op, "threshold": thr}):
                        continue
                    condition = {"operator": op, "threshold": thr}

                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue

                alert = await self._create_alert(
                    rule_id=rule_id,
                    name=name,
                    category="lab_results",
                    alert_type="lab_threshold",
                    severity=severity,
                    parameter=rule["test"],
                    condition=condition or {},
                    value=value,
                    patient_id=pid_str,
                    patient_doc=p,
                    device_id=None,
                    source_time=item.get("time") or now,
                    extra={"unit": item.get("unit"), "raw_name": item.get("raw_name"), "raw_flag": raw_flag},
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("检验预警", triggered)

