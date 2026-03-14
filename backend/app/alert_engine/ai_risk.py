"""AI 综合风险分析"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime
from typing import Any

import httpx


class AiRiskMixin:
    def _ensure_ai_runtime_state(self) -> None:
        if not hasattr(self, "_ai_result_cache"):
            self._ai_result_cache: dict[str, dict[str, Any]] = {}
        if not hasattr(self, "_ai_cache_gc_at"):
            self._ai_cache_gc_at = 0.0

    async def scan_ai_risk(self) -> None:
        ai_cfg = self.config.yaml_cfg.get("ai_service", {})
        if not ai_cfg:
            return

        llm_cfg = ai_cfg.get("llm", {}) if isinstance(ai_cfg, dict) else {}
        timeout_sec = float(llm_cfg.get("timeout", 30) or 30)
        max_concurrency = max(1, int(llm_cfg.get("max_concurrency", 4) or 4))
        cache_ttl_sec = max(60, int(llm_cfg.get("cache_ttl_seconds", 1800) or 1800))
        max_patients = max(1, int(ai_cfg.get("max_patients", 20) or 20))
        suppression_sec = max(60, int(ai_cfg.get("suppression_seconds", 3600) or 3600))

        base_url = str(self.config.settings.LLM_BASE_URL or "").lower()
        llm_key = self.config.settings.LLM_API_KEY
        is_ollama = ("ollama" in base_url) or ("11434" in base_url)
        if not is_ollama:
            if not llm_key or llm_key in ("your_api_key", ""):
                return

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
             "clinicalDiagnosis": 1, "admissionDiagnosis": 1, "nursingLevel": 1, "icuAdmissionTime": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        self._ensure_ai_runtime_state()

        now = datetime.now()
        semaphore = asyncio.Semaphore(max_concurrency)

        try:
            timeout = httpx.Timeout(timeout_sec)
        except Exception:
            timeout = httpx.Timeout(30)

        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [
                asyncio.create_task(
                    self._scan_single_patient_ai_risk(
                        patient_doc=patient_doc,
                        now=now,
                        suppression_sec=suppression_sec,
                        cache_ttl_sec=cache_ttl_sec,
                        semaphore=semaphore,
                        client=client,
                    )
                )
                for patient_doc in patients[:max_patients]
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        triggered = 0
        for item in results:
            if item is True:
                triggered += 1

        if triggered > 0:
            self._log_info("AI预警", triggered)

        self._gc_ai_result_cache(cache_ttl_sec)

    def _cache_key(self, patient_id: str, context_hash: str) -> str:
        return f"{patient_id}:{context_hash}"

    def _read_ai_cache(self, patient_id: str, context_hash: str) -> dict | None:
        self._ensure_ai_runtime_state()
        cache_key = self._cache_key(patient_id, context_hash)
        cached = self._ai_result_cache.get(cache_key)
        if not cached:
            return None
        if cached.get("expire_at", 0) < time.time():
            self._ai_result_cache.pop(cache_key, None)
            return None
        result = cached.get("result")
        return result if isinstance(result, dict) else None

    def _write_ai_cache(self, patient_id: str, context_hash: str, result: dict, cache_ttl_sec: int) -> None:
        self._ensure_ai_runtime_state()
        cache_key = self._cache_key(patient_id, context_hash)
        self._ai_result_cache[cache_key] = {
            "result": result,
            "expire_at": time.time() + cache_ttl_sec,
        }

    def _gc_ai_result_cache(self, cache_ttl_sec: int) -> None:
        self._ensure_ai_runtime_state()
        now_ts = time.time()
        if (now_ts - self._ai_cache_gc_at) < min(cache_ttl_sec, 300):
            return
        self._ai_cache_gc_at = now_ts
        expired = [k for k, v in self._ai_result_cache.items() if v.get("expire_at", 0) < now_ts]
        for k in expired:
            self._ai_result_cache.pop(k, None)
        if len(self._ai_result_cache) > 5000:
            for k in list(self._ai_result_cache.keys())[: len(self._ai_result_cache) - 5000]:
                self._ai_result_cache.pop(k, None)

    def _context_hash(self, patient_summary: str) -> str:
        return hashlib.sha256(patient_summary.encode("utf-8")).hexdigest()

    async def _scan_single_patient_ai_risk(
        self,
        *,
        patient_doc: dict,
        now: datetime,
        suppression_sec: int,
        cache_ttl_sec: int,
        semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
    ) -> bool:
        pid = patient_doc.get("_id")
        if not pid:
            return False

        pid_str = str(pid)
        if await self._is_suppressed(pid_str, "AI_RISK_ANALYSIS", suppression_sec, 5):
            return False

        try:
            patient_summary = await self._build_patient_context(patient_doc, pid)
        except Exception:
            return False

        context_hash = self._context_hash(patient_summary)
        cached_result = self._read_ai_cache(pid_str, context_hash)
        source = "cache"
        result = cached_result
        if not result:
            source = "llm"
            try:
                async with semaphore:
                    result = await self._call_ai_analysis(patient_summary, client=client)
            except Exception:
                return False
            if not result:
                return False
            self._write_ai_cache(pid_str, context_hash, result, cache_ttl_sec)

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
            return False

        device_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])
        explainability = self._build_explainability(result)

        alert = await self._create_alert(
            rule_id="AI_RISK_ANALYSIS",
            name=f"AI风险预测: {result.get('primary_risk', '综合风险')}",
            category="ai_analysis",
            alert_type="ai_risk",
            severity=severity,
            parameter="multi_parameter",
            condition={
                "ai_model": self.config.settings.LLM_MODEL,
                "risk_level": risk_level,
                "analysis_source": source,
            },
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
                "explainability": explainability,
            },
        )
        return bool(alert)

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except Exception:
            return None

    def _clamp01(self, value: Any, default: float = 0.5) -> float:
        num = self._to_float(value)
        if num is None:
            return default
        return max(0.0, min(1.0, num))

    def _build_explainability(self, result: dict) -> dict:
        source = result.get("explainability")
        if isinstance(source, dict):
            factors = []
            raw_factors = source.get("top_factors", [])
            if isinstance(raw_factors, list):
                for factor in raw_factors[:6]:
                    if not isinstance(factor, dict):
                        continue
                    label = str(factor.get("factor") or factor.get("name") or "").strip()
                    if not label:
                        continue
                    factors.append({
                        "factor": label,
                        "direction": str(factor.get("direction") or "up"),
                        "weight": round(self._clamp01(factor.get("weight"), default=0.6), 2),
                        "evidence": str(factor.get("evidence") or ""),
                    })
            if factors:
                return {
                    "method": "llm_self_report",
                    "confidence": round(self._clamp01(source.get("confidence"), default=0.7), 2),
                    "top_factors": factors,
                    "notes": str(source.get("notes") or ""),
                }

        factors: list[dict[str, Any]] = []
        for s in result.get("deterioration_signals", [])[:3]:
            text = str(s).strip()
            if text:
                factors.append({
                    "factor": text[:40],
                    "direction": "up",
                    "weight": 0.72,
                    "evidence": text,
                })

        for syndrome in result.get("syndromes_detected", [])[:2]:
            if not isinstance(syndrome, dict):
                continue
            name = str(syndrome.get("name") or "").strip()
            if not name:
                continue
            conf = round(self._clamp01(syndrome.get("confidence"), default=0.65), 2)
            criteria = syndrome.get("criteria_met", [])
            evidence = "；".join(str(x) for x in criteria[:2]) if isinstance(criteria, list) else ""
            factors.append({
                "factor": f"综合征提示: {name}",
                "direction": "up",
                "weight": conf,
                "evidence": evidence,
            })

        organ = result.get("organ_assessment", {})
        if isinstance(organ, dict):
            for organ_name, assessment in organ.items():
                if not isinstance(assessment, dict):
                    continue
                status = str(assessment.get("status") or "").lower()
                if status in ("impaired", "failure"):
                    evidence = str(assessment.get("evidence") or "")
                    factors.append({
                        "factor": f"{organ_name}功能{status}",
                        "direction": "up",
                        "weight": 0.68 if status == "impaired" else 0.82,
                        "evidence": evidence,
                    })

        return {
            "method": "heuristic_from_llm_output",
            "confidence": 0.66,
            "top_factors": factors[:6],
            "notes": "基于LLM输出字段进行结构化提取，非模型内部注意力权重。",
        }

    async def _build_patient_context(self, patient: dict, pid) -> str:
        name = patient.get("name", "未知")
        diag = patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "未知"
        nursing = patient.get("nursingLevel", "未知")
        icu_time = patient.get("icuAdmissionTime", "未知")
        snapshot = await self._get_latest_param_snapshot_by_pid(
            pid,
            codes=["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_T"],
        )
        if not snapshot:
            monitor_id = await self._get_device_id_for_patient(patient, ["monitor"])
            snapshot = await self._get_latest_device_cap(
                monitor_id,
                codes=["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_T"],
            ) if monitor_id else None
        vitals = []
        if snapshot:
            t = snapshot.get("time")
            vitals.append({
                "time": str(t) if t else "?",
                "HR": self._get_priority_param(snapshot, ["param_HR"]),
                "SpO2": self._get_priority_param(snapshot, ["param_spo2"]),
                "RR": self._get_priority_param(snapshot, ["param_resp"]),
                "SBP": self._get_priority_param(snapshot, ["param_nibp_s", "param_ibp_s"]),
                "T": self._get_priority_param(snapshot, ["param_T"]),
            })

        his_pid = patient.get("hisPid")
        labs_text = ""
        if his_pid:
            lab_cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find(
                {"hisPid": his_pid}
            ).sort("authTime", -1).limit(10)
            labs = []
            async for doc in lab_cursor:
                labs.append({
                    "name": doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode", "?"),
                    "result": doc.get("result") or doc.get("resultValue", "?"),
                    "unit": doc.get("unit", ""),
                    "flag": doc.get("resultFlag") or doc.get("seriousFlag") or doc.get("resultStatus") or "",
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

    async def _call_ai_analysis(
        self,
        patient_context: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict | None:
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
  "recommendations": ["建议1", "建议2"],
  "explainability": {
    "confidence": 0.0-1.0,
    "top_factors": [
      {"factor": "关键风险因素", "direction": "up|down", "weight": 0.0-1.0, "evidence": "证据"}
    ],
    "notes": "解释说明"
  }
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

        async def _do_request(request_client: httpx.AsyncClient) -> str:
            resp = await request_client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        if client is None:
            ai_cfg = self.config.yaml_cfg.get("ai_service", {})
            llm_cfg = ai_cfg.get("llm", {}) if isinstance(ai_cfg, dict) else {}
            timeout_sec = float(llm_cfg.get("timeout", 30) or 30)
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as local_client:
                text = await _do_request(local_client)
        else:
            text = await _do_request(client)

        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

