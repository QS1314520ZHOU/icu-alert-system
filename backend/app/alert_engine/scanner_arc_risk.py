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


class ArcRiskScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="arc_risk",
                interval_key="arc_risk",
                default_interval=300,
                initial_delay=46,
            ),
        )

    async def scan(self) -> None:
        now = datetime.now()
        patient_cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1})
        patients = [p async for p in patient_cursor]
        if not patients:
            return
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = self.engine._pid_str(pid)
            result = await self.engine.assess_arc_risk(patient_doc, now)
            await self.engine._persist_arc_risk(patient_doc, result, now)
            if result.get("arc_risk") != "high":
                continue
            rule_id = "ARC_RISK_HIGH"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            explanation = await self.engine._polish_structured_alert_explanation({"summary": "患者存在 ARC 高风险，关键抗菌药物可能清除过快。", "evidence": [result.get("explanation") or "ARC 风险评分高"], "suggestion": result.get("suggested_pk_adjustment") or "建议复核抗菌药物暴露和给药方案。", "text": ""})
            alert = await self.engine._create_alert(rule_id=rule_id, name="ARC 高风险提示", category="drug_pk", alert_type="arc_risk", severity="warning", parameter="arc_score", condition={"operator": ">=", "threshold": 6}, value=result.get("score"), patient_id=pid_str, patient_doc=patient_doc, device_id=None, source_time=now, explanation=explanation, extra=result)
            if alert:
                triggered += 1
        if triggered > 0:
            self.engine._log_info("ARC识别", triggered)
