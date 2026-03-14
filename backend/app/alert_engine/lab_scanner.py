"""检验结果自动扫描。"""
from __future__ import annotations

from datetime import datetime

from .base import _eval_condition


class LabScannerMixin:
    def _lab_correction_plan(
        self,
        test: str,
        value: float,
        labs: dict,
        *,
        aki: dict | None,
        on_digoxin: bool,
    ) -> dict | None:
        mg = labs.get("mg", {}).get("value")
        plan: dict | None = None

        if test == "k" and value < 3.5:
            actions = []
            recommended_severity = "warning"
            if value < 3.0:
                actions.extend(["口服 KCl 40 mEq", "IV KCl 20 mEq/h（中心静脉）", "2h 后复查血钾"])
                recommended_severity = "high"
            else:
                actions.extend(["口服 KCl 20 mEq × 2", "4h 后复查血钾"])
            if mg is not None and mg < 1.6:
                actions.insert(0, "先补 MgSO₄ 2g IV over 1h，再补钾")
            if on_digoxin:
                recommended_severity = "critical"
            plan = {
                "title": "低钾纠正建议",
                "actions": actions,
                "recommended_severity": recommended_severity,
            }
            if mg is not None and mg < 1.6:
                plan["magnesium_linkage"] = "Mg < 1.6 mg/dL，先补镁"
            if on_digoxin:
                plan["digoxin_note"] = "使用地高辛，低钾增加中毒风险"

        elif test == "po4" and value < 1.0:
            plan = {
                "title": "低磷纠正建议",
                "actions": ["K-Phos 或 Na-Phos 30 mmol IV over 6h", "不要与钙同一静脉通路"],
                "recommended_severity": "high",
            }

        elif test == "ica" and value < 0.8:
            plan = {
                "title": "低离子钙纠正建议",
                "actions": [
                    "CaCl₂ 1g IV over 30min（中心静脉）",
                    "或 Ca Gluconate 3g IV over 1h（外周）",
                    "8h 后复查 iCa",
                ],
                "recommended_severity": "high",
            }

        elif test == "mg" and value < 1.0:
            plan = {
                "title": "低镁纠正建议",
                "actions": ["MgSO₄ 4g IV over 2h", "后续 2g over 8h"],
                "recommended_severity": "high",
            }

        if plan and aki:
            plan["aki_note"] = "肾功能不全——减量或延长复查间隔"
        return plan

    async def scan_lab_results(self) -> None:
        now = datetime.now()
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        lab_rules = [
            {"rule_id": "LAB_K_CRIT_HIGH", "test": "k", "name": "高钾血症(危急)", "condition": {">": 6.5}, "severity": "critical", "group": "k_high", "priority": 1},
            {"rule_id": "LAB_K_HIGH", "test": "k", "name": "高钾血症", "condition": {">": 5.5}, "severity": "warning", "group": "k_high", "priority": 2},
            {"rule_id": "LAB_K_CRIT_LOW", "test": "k", "name": "低钾血症(危急)", "condition": {"<": 2.5}, "severity": "critical", "group": "k_low", "priority": 1},
            {"rule_id": "LAB_K_LOW", "test": "k", "name": "低钾血症", "condition": {"<": 3.5}, "severity": "warning", "group": "k_low", "priority": 2},
            {"rule_id": "LAB_NA_CRIT_HIGH", "test": "na", "name": "高钠血症(危急)", "condition": {">": 160}, "severity": "critical", "group": "na_high", "priority": 1},
            {"rule_id": "LAB_NA_CRIT_LOW", "test": "na", "name": "低钠血症(危急)", "condition": {"<": 120}, "severity": "critical", "group": "na_low", "priority": 1},
            {"rule_id": "LAB_ICA_LOW", "test": "ica", "name": "低离子钙", "condition": {"<": 0.8}, "severity": "high", "group": "ica_low", "priority": 1},
            {"rule_id": "LAB_PO4_LOW", "test": "po4", "name": "低磷血症", "condition": {"<": 1.0}, "severity": "high", "group": "po4_low", "priority": 1},
            {"rule_id": "LAB_MG_LOW", "test": "mg", "name": "低镁血症", "condition": {"<": 1.0}, "severity": "high", "group": "mg_low", "priority": 1},
            {"rule_id": "LAB_LAC_CRIT", "test": "lac", "name": "乳酸危急", "condition": {">": 4.0}, "severity": "critical", "group": "lac_high", "priority": 1},
            {"rule_id": "LAB_LAC_HIGH", "test": "lac", "name": "乳酸升高", "condition": {">": 2.0}, "severity": "warning", "group": "lac_high", "priority": 2},
            {"rule_id": "LAB_GLU_LOW", "test": "glu", "name": "低血糖", "condition": {"<": 3.0}, "severity": "critical", "group": "glu_low", "priority": 1},
            {"rule_id": "LAB_GLU_HIGH", "test": "glu", "name": "高血糖", "condition": {">": 20.0}, "severity": "warning", "group": "glu_high", "priority": 1},
            {"rule_id": "LAB_HB_CRIT", "test": "hb", "name": "重度贫血", "condition": {"<": 60}, "severity": "critical", "group": "hb_low", "priority": 1},
            {"rule_id": "LAB_HB_LOW", "test": "hb", "name": "贫血", "condition": {"<": 70}, "severity": "warning", "group": "hb_low", "priority": 2},
            {"rule_id": "LAB_PLT_CRIT", "test": "plt", "name": "严重血小板减少", "condition": {"<": 20}, "severity": "critical", "group": "plt_low", "priority": 1},
            {"rule_id": "LAB_PLT_LOW", "test": "plt", "name": "血小板减少", "condition": {"<": 50}, "severity": "warning", "group": "plt_low", "priority": 2},
            {"rule_id": "LAB_PCT_CRIT", "test": "pct", "name": "PCT危急升高", "condition": {">": 10}, "severity": "critical", "group": "pct_high", "priority": 1},
            {"rule_id": "LAB_PCT_HIGH", "test": "pct", "name": "PCT升高", "condition": {">": 2}, "severity": "warning", "group": "pct_high", "priority": 2},
            {"rule_id": "LAB_INR_HIGH", "test": "inr", "name": "INR升高", "condition": {">": 3.0}, "severity": "warning", "group": "inr_high", "priority": 1},
            {"rule_id": "LAB_TROP_HIGH", "test": "trop", "name": "肌钙蛋白显著升高", "condition": {">": 5.0}, "severity": "high", "group": "trop_high", "priority": 1},
            {"rule_id": "LAB_BNP_HIGH", "test": "bnp", "name": "BNP/NT-proBNP升高", "condition": {">": 1000}, "severity": "warning", "group": "bnp_high", "priority": 1},
        ]
        lab_rules.sort(key=lambda r: (r.get("group", ""), r.get("priority", 99)))

        triggered = 0
        for p in patients:
            his_pid = p.get("hisPid")
            pid = p.get("_id")
            if not his_pid or not pid:
                continue

            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
            if not labs:
                continue

            pid_str = str(pid)
            fired_groups: set[str] = set()
            aki = await self._calc_aki_stage(p, pid, his_pid)
            on_digoxin = await self._has_recent_drug(pid, ["地高辛", "digoxin"], hours=72)

            for rule in lab_rules:
                group = rule.get("group")
                if group and group in fired_groups:
                    continue

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
                        op, thr = list(rule["condition"].items())[0]
                        if not _eval_condition(value, {"operator": op, "threshold": thr}):
                            continue
                        condition = {"operator": op, "threshold": thr}
                else:
                    op, thr = list(rule["condition"].items())[0]
                    if not _eval_condition(value, {"operator": op, "threshold": thr}):
                        continue
                    condition = {"operator": op, "threshold": thr}

                correction_plan = self._lab_correction_plan(rule["test"], value, labs, aki=aki, on_digoxin=on_digoxin)
                if correction_plan and correction_plan.get("recommended_severity"):
                    severity = str(correction_plan["recommended_severity"])
                if rule["test"] == "k" and on_digoxin and value < 3.5:
                    severity = "critical"
                    name = "低钾血症（地高辛中毒风险）"

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
                    extra={
                        "unit": item.get("unit"),
                        "raw_name": item.get("raw_name"),
                        "raw_flag": raw_flag,
                        "correction_plan": correction_plan,
                        "aki_context": aki,
                        "on_digoxin": on_digoxin,
                    },
                )
                if alert:
                    triggered += 1
                    if group:
                        fired_groups.add(group)

        if triggered > 0:
            self._log_info("检验预警", triggered)

