from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any
def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None
from .scanners import BaseScanner, ScannerSpec


class AntimicrobialPkScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="antimicrobial_pk",
                interval_key="antimicrobial_pk",
                default_interval=600,
                initial_delay=48,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "weight": 1, "bodyWeight": 1, "gender": 1, "hisSex": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1})
        patients = [p async for p in patient_cursor]
        if not patients:
            return
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        rules = {"vancomycin": "VANCO_PPK_UNDEREXPOSED", "meropenem": "MEM_PPK_UNDEREXPOSED", "piperacillin_tazobactam": "TZP_PPK_UNDEREXPOSED"}
        now = datetime.now()
        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = self.engine._pid_str(pid)
            for drug_key, rule_id in rules.items():
                result = await self.engine.evaluate_antimicrobial_pk(patient_doc, drug_key, now)
                if not result:
                    continue
                await self.engine._persist_antimicrobial_pk(patient_doc, result, now)
                if result.get("target_attainment"):
                    continue
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                explanation = await self.engine._polish_structured_alert_explanation({"summary": f"{result.get('drug')} 预测暴露不足。", "evidence": [f"ARC 风险: {result.get('arc_risk')}", f"预测暴露: {result.get('predicted_exposure')}"], "suggestion": result.get("recommendation") or "建议复核给药方案。", "text": ""})
                alert = await self.engine._create_alert(rule_id=rule_id, name=f"{result.get('drug')} 暴露不足风险", category="drug_pk", alert_type="antimicrobial_pk", severity="warning" if result.get("arc_risk") != "high" else "high", parameter=result.get("drug"), condition={"target_attainment": False}, value=(result.get("predicted_exposure") or {}).get("auc24") or (result.get("predicted_exposure") or {}).get("ft_above_mic"), patient_id=pid_str, patient_doc=patient_doc, device_id=None, source_time=now, explanation=explanation, extra=result)
                if alert:
                    triggered += 1
        if triggered > 0:
            self.engine._log_info("抗菌药物PK", triggered)
