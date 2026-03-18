"""检验结果自动扫描。"""
from __future__ import annotations


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
        from .lab_results_scanner import LabResultsScanner

        await LabResultsScanner(self).scan()
