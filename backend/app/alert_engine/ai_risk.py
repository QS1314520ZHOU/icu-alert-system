"""AI 综合风险分析"""
from __future__ import annotations

import json
from datetime import datetime

import httpx


class AiRiskMixin:
    async def scan_ai_risk(self) -> None:
        ai_cfg = self.config.yaml_cfg.get("ai_service", {})
        if not ai_cfg:
            return

        llm_key = self.config.settings.LLM_API_KEY
        if not llm_key or llm_key in ("ollama", "your_api_key", ""):
            return

        binds = [b async for b in self.db.col("deviceBind").find({"unBindTime": None}, {"pid": 1, "deviceID": 1})]
        if not binds:
            return

        now = datetime.now()
        suppression_sec = 3600

        triggered = 0
        for b in binds[:20]:
            pid = b.get("pid")
            device_id = b.get("deviceID")
            if not pid or not device_id:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not patient_doc or not pid_str:
                continue

            if await self._is_suppressed(pid_str, "AI_RISK_ANALYSIS", suppression_sec, 5):
                continue

            try:
                patient_summary = await self._build_patient_context(patient_doc, pid, device_id)
            except Exception:
                continue

            try:
                result = await self._call_ai_analysis(patient_summary)
            except Exception:
                continue

            if not result:
                continue

            risk_level = str(result.get("risk_level", "")).lower()
            severity_map = {
                "极高": "critical",
                "高": "high",
                "中": "warning",
                "low": None,
                "medium": "warning",
                "high": "high",
                "critical": "critical",
            }
            severity = severity_map.get(risk_level)
            if not severity:
                continue

            alert = await self._create_alert(
                rule_id="AI_RISK_ANALYSIS",
                name=f"AI风险预测: {result.get('primary_risk', '综合风险')}",
                category="ai_analysis",
                alert_type="ai_risk",
                severity=severity,
                parameter="multi_parameter",
                condition={"ai_model": self.config.settings.LLM_MODEL, "risk_level": risk_level},
                value=None,
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                source_time=now,
                extra={
                    "organ_assessment": result.get("organ_assessment", {}),
                    "syndromes_detected": result.get("syndromes_detected", []),
                    "deterioration_signals": result.get("deterioration_signals", []),
                    "recommendations": result.get("recommendations", []),
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("AI预警", triggered)

    async def _build_patient_context(self, patient: dict, pid, device_id) -> str:
        name = patient.get("name", "未知")
        diag = patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "未知"
        nursing = patient.get("nursingLevel", "未知")
        icu_time = patient.get("icuAdmissionTime", "未知")

        cap_cursor = self.db.col("deviceCap").find(
            {"deviceID": device_id}, {"time": 1, "params": 1}
        ).sort("time", -1).limit(6)
        vitals = []
        async for doc in cap_cursor:
            t = doc.get("time")
            vitals.append({
                "time": str(t) if t else "?",
                "HR": self._get_priority_param(doc, ["param_HR"]),
                "SpO2": self._get_priority_param(doc, ["param_spo2"]),
                "RR": self._get_priority_param(doc, ["param_resp"]),
                "SBP": self._get_priority_param(doc, ["param_nibp_s", "param_ibp_s"]),
                "T": self._get_priority_param(doc, ["param_T"]),
            })

        his_pid = patient.get("hisPid")
        labs_text = ""
        if his_pid:
            lab_cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find(
                {"hisPid": his_pid}
            ).sort("requestTime", -1).limit(10)
            labs = []
            async for doc in lab_cursor:
                labs.append({
                    "name": doc.get("itemCnName") or doc.get("itemName", "?"),
                    "result": doc.get("result") or doc.get("resultValue", "?"),
                    "unit": doc.get("unit", ""),
                    "flag": doc.get("resultFlag", ""),
                })
            if labs:
                labs_text = f"\n近期检验(最新10项): {json.dumps(labs, ensure_ascii=False)}"

        vitals_text = json.dumps(vitals, ensure_ascii=False)
        return (
            f"患者: {name}\n"
            f"诊断: {diag}\n"
            f"护理级别: {nursing}\n"
            f"ICU入科: {icu_time}\n"
            f"最近生命体征(从新到旧): {vitals_text}"
            f"{labs_text}"
        )

    async def _call_ai_analysis(self, patient_context: str) -> dict | None:
        system_prompt = """你是一位ICU高年资主治医师AI助手。基于患者数据完成结构化评估。

必须返回严格JSON（不要其他文字），结构如下：
{
  "organ_assessment": {
    "respiratory": {"status": "normal|impaired|failure", "evidence": "..."},
    "cardiovascular": {"status": "normal|impaired|failure", "evidence": "..."},
    "renal": {"status": "normal|impaired|failure", "evidence": "..."},
    "hepatic": {"status": "normal|impaired|failure", "evidence": "..."},
    "coagulation": {"status": "normal|impaired|failure", "evidence": "..."},
    "neurological": {"status": "normal|impaired|failure", "evidence": "..."}
  },
  "syndromes_detected": [
    {"name": "脓毒性休克", "confidence": 0.0-1.0, "criteria_met": ["..."]}
  ],
  "deterioration_signals": ["..."],
  "risk_level": "low|medium|high|critical",
  "primary_risk": "最主要风险(10字以内)",
  "recommendations": ["建议1", "建议2"]
}"""

        cfg = self.config
        url = cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
        model = cfg.settings.LLM_MODEL_MEDICAL or cfg.settings.LLM_MODEL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.settings.LLM_API_KEY}",
        }
        payload = {
            "model": model,
            "temperature": 0.1,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": patient_context},
            ],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]

        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

