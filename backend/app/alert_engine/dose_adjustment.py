"""肾/肝功能相关高危药剂量调整提醒。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .scanner_dose_adjustment import DoseAdjustmentScanner


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
        await DoseAdjustmentScanner(self).scan()
