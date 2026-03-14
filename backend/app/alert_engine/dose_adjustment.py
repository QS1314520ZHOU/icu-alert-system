"""肾/肝功能相关高危药剂量调整提醒。"""
from __future__ import annotations

from datetime import datetime
from typing import Any


class DoseAdjustmentMixin:
    RENAL_DRUG_TABLE = [
        {
            "name": "万古霉素",
            "keywords": ["万古霉素", "vancomycin"],
            "suggestion": "建议结合 TDM 与肾功能调整给药间隔；AKI/CRRT 时优先复核谷浓度。",
            "reference": "IDSA/TDM 共识；肾功能剂量调整常规参考",
        },
        {
            "name": "氨基糖苷类",
            "keywords": ["阿米卡星", "庆大霉素", "妥布霉素", "依替米星", "奈替米星", "链霉素"],
            "suggestion": "建议延长给药间隔并结合 TDM，避免累积性耳/肾毒性。",
            "reference": "肾功能剂量调整常规参考",
        },
        {
            "name": "亚胺培南",
            "keywords": ["亚胺培南", "imipenem"],
            "suggestion": "eGFR 10-25 mL/min：常见方案 0.25-0.5 g q6-8h，需结合感染严重度。",
            "reference": "说明书 / Sanford Guide / 肾功能剂量调整参考",
        },
        {
            "name": "美罗培南",
            "keywords": ["美罗培南", "meropenem"],
            "suggestion": "美罗培南 eGFR 10-25 mL/min：1 g q12h 常需调整为 0.5 g q12h。",
            "reference": "说明书 / Sanford Guide / 肾功能剂量调整参考",
        },
        {
            "name": "氟康唑",
            "keywords": ["氟康唑", "fluconazole"],
            "suggestion": "负荷剂量后维持剂量常需减半；CRRT 需结合滤过剂量再评估。",
            "reference": "说明书 / 肾功能剂量调整参考",
        },
        {
            "name": "阿昔洛韦",
            "keywords": ["阿昔洛韦", "acyclovir"],
            "suggestion": "重度肾损害需显著延长给药间隔，并警惕结晶肾病。",
            "reference": "说明书 / 肾功能剂量调整参考",
        },
        {
            "name": "依诺肝素",
            "keywords": ["依诺肝素", "enoxaparin"],
            "suggestion": "eGFR <30 mL/min 时考虑减量或改用 UFH，并结合抗 Xa 监测。",
            "reference": "CHEST / 肾功能剂量调整参考",
        },
    ]

    HEPATIC_DRUG_TABLE = [
        {
            "name": "甲硝唑",
            "keywords": ["甲硝唑", "metronidazole"],
            "suggestion": "明显肝功能不全时可考虑减量至常规剂量的约 50% 或延长给药间隔。",
            "reference": "说明书 / 肝功能不全给药参考",
        },
        {
            "name": "阿奇霉素",
            "keywords": ["阿奇霉素", "azithromycin"],
            "suggestion": "肝胆淤积或转氨酶显著升高时建议复核适应证，必要时停用或改药。",
            "reference": "说明书 / 肝毒性监测建议",
        },
        {
            "name": "伏立康唑",
            "keywords": ["伏立康唑", "voriconazole"],
            "suggestion": "Child-Pugh A/B 常需减半维持剂量；重度肝损害需个体化并结合 TDM。",
            "reference": "说明书 / IDSA / 肝功能不全给药参考",
        },
    ]

    def _match_drug_docs(self, docs: list[dict], keywords: list[str]) -> list[dict]:
        kw = [str(k).lower() for k in keywords if str(k).strip()]
        return [doc for doc in docs if any(k in self._drug_text(doc).lower() for k in kw)]

    def _dose_signature(self, doc: dict) -> str:
        return " ".join(
            str(doc.get(k) or "").strip().lower()
            for k in ("dose", "doseUnit", "frequency", "route", "routeName")
        ).strip()

    def _dose_changed_recently(self, docs: list[dict]) -> bool:
        signatures = {self._dose_signature(doc) for doc in docs if self._dose_signature(doc)}
        return len(signatures) >= 2

    def _format_current_dose(self, doc: dict) -> str:
        text = " ".join(str(doc.get(k) or "") for k in ("dose", "doseUnit", "frequency")).strip()
        return text or "当前剂量待核对"

    def _hepatic_risk_summary(self, labs: dict[str, Any]) -> dict[str, Any]:
        bil = labs.get("bil", {}).get("value")
        alt = labs.get("alt", {}).get("value")
        ast = labs.get("ast", {}).get("value")

        reasons: list[str] = []
        severity = "none"
        if bil is not None and bil >= 34:
            reasons.append(f"TBil {round(float(bil), 1)} μmol/L")
            severity = "moderate"
        if alt is not None and alt >= 120:
            reasons.append(f"ALT {round(float(alt), 1)} U/L")
            severity = "moderate"
        if ast is not None and ast >= 120:
            reasons.append(f"AST {round(float(ast), 1)} U/L")
            severity = "moderate"
        if (bil is not None and bil >= 51) or (alt is not None and alt >= 200) or (ast is not None and ast >= 200):
            severity = "high"

        return {
            "risk": bool(reasons),
            "severity": severity,
            "reasons": reasons,
            "bilirubin": bil,
            "alt": alt,
            "ast": ast,
        }

    async def _create_dose_adjustment_alert(
        self,
        *,
        patient_doc: dict,
        pid_str: str,
        latest_doc: dict,
        rule_id: str,
        name: str,
        alert_type: str,
        severity: str,
        value: Any,
        extra: dict[str, Any],
    ) -> bool:
        alert = await self._create_alert(
            rule_id=rule_id,
            name=name,
            category="dose_adjustment",
            alert_type=alert_type,
            severity=severity,
            parameter=extra.get("drug_name"),
            condition=extra.get("condition") or {},
            value=value,
            patient_id=pid_str,
            patient_doc=patient_doc,
            source_time=latest_doc.get("_event_time") or datetime.now(),
            extra=extra,
        )
        return alert is not None

    async def scan_dose_adjustment(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "gender": 1, "hisSex": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            his_pid = patient_doc.get("hisPid")
            if not pid or not his_pid:
                continue

            pid_str = str(pid)
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
            if not labs:
                continue

            aki = await self._calc_aki_stage(patient_doc, pid, his_pid)
            crrt = await self._get_device_id_for_patient(patient_doc, ["crrt"])
            cr = labs.get("cr", {}).get("value")
            egfr = labs.get("egfr", {}).get("value") or self._estimate_egfr(patient_doc, cr)
            renal_risk = bool((egfr is not None and egfr < 30) or (aki and aki.get("stage", 0) >= 2) or crrt)
            hepatic = self._hepatic_risk_summary(labs)

            if not renal_risk and not hepatic["risk"]:
                continue

            recent_docs = await self._get_recent_drug_docs_window(pid, hours=24, limit=800)
            if not recent_docs:
                continue

            if renal_risk:
                for drug in self.RENAL_DRUG_TABLE:
                    matched = self._match_drug_docs(recent_docs, drug["keywords"])
                    if not matched:
                        continue
                    if self._dose_changed_recently(matched):
                        continue
                    latest = matched[-1]
                    rule_id = f"RENAL_DOSE_{drug['name']}"
                    if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    if await self._create_dose_adjustment_alert(
                        patient_doc=patient_doc,
                        pid_str=pid_str,
                        latest_doc=latest,
                        rule_id=rule_id,
                        name=f"{drug['name']}需评估肾功能剂量调整",
                        alert_type="renal_dose_adjustment",
                        severity="high",
                        value=egfr if egfr is not None else (aki.get("stage") if aki else None),
                        extra={
                            "drug_name": drug["name"],
                            "current_dose": self._format_current_dose(latest),
                            "suggestion": drug["suggestion"],
                            "reference": drug["reference"],
                            "recent_order_count_24h": len(matched),
                            "recent_adjustment_detected": False,
                            "eGFR": egfr,
                            "aki_stage": aki.get("stage") if aki else None,
                            "on_crrt": bool(crrt),
                            "condition": {"renal_risk": True},
                        },
                    ):
                        triggered += 1

            if hepatic["risk"]:
                for drug in self.HEPATIC_DRUG_TABLE:
                    matched = self._match_drug_docs(recent_docs, drug["keywords"])
                    if not matched:
                        continue
                    if self._dose_changed_recently(matched):
                        continue
                    latest = matched[-1]
                    rule_id = f"HEPATIC_DOSE_{drug['name']}"
                    if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    severity = "high" if hepatic["severity"] == "high" else "warning"
                    if await self._create_dose_adjustment_alert(
                        patient_doc=patient_doc,
                        pid_str=pid_str,
                        latest_doc=latest,
                        rule_id=rule_id,
                        name=f"{drug['name']}需评估肝功能相关剂量/停药",
                        alert_type="hepatic_dose_adjustment",
                        severity=severity,
                        value=hepatic["bilirubin"] or hepatic["alt"] or hepatic["ast"],
                        extra={
                            "drug_name": drug["name"],
                            "current_dose": self._format_current_dose(latest),
                            "suggestion": drug["suggestion"],
                            "reference": drug["reference"],
                            "recent_order_count_24h": len(matched),
                            "recent_adjustment_detected": False,
                            "bilirubin": hepatic["bilirubin"],
                            "alt": hepatic["alt"],
                            "ast": hepatic["ast"],
                            "hepatic_severity": hepatic["severity"],
                            "hepatic_reasons": hepatic["reasons"],
                            "condition": {"hepatic_risk": True, "hepatic_severity": hepatic["severity"]},
                        },
                    ):
                        triggered += 1

        if triggered > 0:
            self._log_info("剂量调整", triggered)
