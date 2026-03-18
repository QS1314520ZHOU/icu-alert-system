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


class VancoTdmClosedLoopScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="vanco_tdm_closed_loop",
                interval_key="vanco_tdm_closed_loop",
                default_interval=600,
                initial_delay=50,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "weight": 1, "bodyWeight": 1, "gender": 1, "hisSex": 1})
        patients = [p async for p in patient_cursor]
        if not patients:
            return
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = self.engine._pid_str(pid)
            result = await self.engine.update_vanco_tdm_state(patient_doc, now)
            if not result:
                continue
            await self.engine._persist_vanco_tdm(patient_doc, result, now)
            if result.get("target_attainment") is True:
                continue
            auc24 = _to_float(result.get("auc24"))
            mic = float(self.engine._tdm_cfg().get("vanco_mic", 1.0))
            auc_mic = auc24 / max(mic, 1e-6) if auc24 is not None else None
            if auc_mic is not None and auc_mic < float(self.engine._tdm_cfg().get("auc_mic_target_low", 400.0)):
                rule_id = "VANCO_TDM_UNDER_TARGET"
                severity = "warning"
            else:
                rule_id = "VANCO_TDM_OVER_TARGET"
                severity = "high"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            explanation = await self.engine._polish_structured_alert_explanation({"summary": "万古霉素 TDM 闭环提示当前暴露可能未达目标。", "evidence": [f"样本浓度: {result.get('sample_value')}", f"预测 AUC24: {result.get('auc24')}", f"预测下一次 trough: {result.get('predicted_trough_next')}"], "suggestion": result.get("recommendation") or "建议复核万古霉素方案。", "text": ""})
            alert = await self.engine._create_alert(rule_id=rule_id, name="万古霉素 TDM 闭环建议", category="drug_pk", alert_type="vanco_tdm", severity=severity, parameter="vancomycin_auc_mic", condition={"target_attainment": False}, value=auc_mic, patient_id=pid_str, patient_doc=patient_doc, device_id=None, source_time=result.get("sample_time"), explanation=explanation, extra=result)
            if alert:
                triggered += 1
        if triggered > 0:
            self.engine._log_info("万古TDM闭环", triggered)
