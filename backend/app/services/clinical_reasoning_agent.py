"""LLM-driven individualized ICU clinical reasoning agent."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.services.ai_monitor import AiMonitor
from app.services.llm_runtime import call_llm_chat
from app.services.patient_digital_twin import PatientDigitalTwinService

logger = logging.getLogger("icu-alert")


class ClinicalReasoningAgent:
    SYSTEM_PROMPT = """你是一位ICU重症医学专家AI助手。
基于以下患者的完整诊疗数据，请按照重症医学思维进行分析。

要求:
1) 只能依据输入数据和RAG检索到的指南证据推理，严禁编造未提供的病史、检查结果或治疗经过。
2) 明确区分“已知事实”和“推断建议”；缺失信息必须写“未见证据”。
3) 建议必须个体化、可执行，并尽量给出监测阈值。
4) 所有治疗建议都要附 evidence_level 与 guideline_refs。
5) 必须返回严格 JSON，不要输出任何额外文本。

JSON结构:
{
  "overview": {"summary": "", "core_problems": [""]},
  "dynamic_assessment": {"summary": "", "key_changes_24h": [""]},
  "risk_identification": [
    {"priority": 1, "risk": "", "urgency": "critical|high|medium", "basis": ""}
  ],
  "differential_diagnosis": [
    {"problem": "", "considerations": [""]}
  ],
  "treatment_recommendations": [
    {
      "priority": 1,
      "recommendation": "",
      "rationale": "",
      "evidence_level": "",
      "guideline_refs": ["chunk_id"],
      "safety_notes": [""]
    }
  ],
  "monitoring_focus": [
    {"item": "", "target": "", "threshold": "", "window": "6-12h"}
  ],
  "prognosis_assessment": {"summary": "", "short_term_outlook": "", "confidence": 0.0},
  "evidence_sources": [
    {"chunk_id": "", "source": "", "recommendation": "", "quote": ""}
  ]
}"""

    def __init__(self, *, db, config, alert_engine, rag_service=None, ai_monitor=None, ai_handoff_service=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self.rag_service = rag_service
        self.ai_monitor = ai_monitor
        self.ai_handoff_service = ai_handoff_service

    def _cfg(self) -> dict[str, Any]:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("clinical_reasoning", {})
        return cfg if isinstance(cfg, dict) else {}

    async def build_digital_twin(self, patient_id: str, patient_doc: dict) -> dict[str, Any]:
        twin_service = PatientDigitalTwinService(db=self.db, config=self.config, alert_engine=self.alert_engine)
        base_twin = await twin_service.get_or_build_snapshot(patient_id, patient_doc, hours=24, refresh=False, persist=True)
        pid = patient_doc.get("_id")
        facts = base_twin.get("facts") if isinstance(base_twin.get("facts"), dict) else {}
        nursing_context = None
        nursing_note_analysis = None
        if hasattr(self.alert_engine, "_collect_nursing_context"):
            try:
                nursing_context = await self.alert_engine._collect_nursing_context(patient_doc, str(pid), hours=24)
            except Exception:
                nursing_context = None
        if hasattr(self.alert_engine, "latest_nursing_note_analysis"):
            try:
                nursing_note_analysis = await self.alert_engine.latest_nursing_note_analysis(str(pid), hours=24)
            except Exception:
                nursing_note_analysis = None
        similar_case_review = None
        if hasattr(self.alert_engine, "get_similar_case_outcomes"):
            try:
                similar_case_review = await self.alert_engine.get_similar_case_outcomes(patient_doc, limit=5)
            except Exception:
                similar_case_review = None

        handoff_context = None
        if self.ai_handoff_service is not None and hasattr(self.ai_handoff_service, "_build_context"):
            try:
                handoff_context = await self.ai_handoff_service._build_context(
                    patient_id,
                    patient_doc,
                    similar_case_review=similar_case_review,
                    nursing_context=nursing_context,
                )
            except Exception:
                handoff_context = None

        temporal_forecast = None
        if hasattr(self.alert_engine, "_build_temporal_risk_forecast"):
            try:
                temporal_forecast = await self.alert_engine._build_temporal_risk_forecast(
                    patient_doc,
                    pid,
                    lookback_hours=12,
                    horizons=(4, 8, 12),
                    include_history=True,
                )
            except Exception:
                temporal_forecast = None

        proactive_plan = None
        if hasattr(self.alert_engine, "_latest_proactive_management_record"):
            try:
                proactive_plan = await self.alert_engine._latest_proactive_management_record(str(pid), hours=24)
            except Exception:
                proactive_plan = None

        recent_alerts = ((base_twin.get("alerts") or {}).get("recent") if isinstance(base_twin.get("alerts"), dict) else None) or []
        recent_scores = ((base_twin.get("scores") or {}).get("recent") if isinstance(base_twin.get("scores"), dict) else None) or []

        problem_list = self._problem_list(patient_doc=patient_doc, facts=facts, recent_alerts=recent_alerts, temporal_forecast=temporal_forecast)
        return {
            "generated_at": datetime.now(),
            "digital_twin_snapshot": base_twin,
            "patient": {
                "id": patient_id,
                "name": patient_doc.get("name") or "未知",
                "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
                "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
                "diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "",
                "nursing_level": patient_doc.get("nursingLevel") or "",
                "icu_admission_time": patient_doc.get("icuAdmissionTime"),
            },
            "problem_list": problem_list,
            "facts": facts,
            "recent_alerts_24h": recent_alerts,
            "recent_scores_24h": recent_scores,
            "temporal_forecast": temporal_forecast or {},
            "proactive_management": proactive_plan or {},
            "nursing_context": nursing_context or {},
            "nursing_note_analysis": nursing_note_analysis or {},
            "similar_case_review": similar_case_review or {},
            "handoff_context": handoff_context or {},
        }

    def _problem_list(self, *, patient_doc: dict, facts: dict[str, Any], recent_alerts: list[dict], temporal_forecast: dict[str, Any] | None) -> list[str]:
        problems: list[str] = []
        diagnosis = str(patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "").strip()
        if diagnosis:
            problems.append(diagnosis)
        vitals = facts.get("vitals") if isinstance(facts.get("vitals"), dict) else {}
        if vitals.get("spo2") is not None and float(vitals["spo2"]) < 92:
            problems.append(f"低氧血症风险 SpO2 {vitals['spo2']}%")
        if vitals.get("sbp") is not None and float(vitals["sbp"]) < 90:
            problems.append(f"低血压风险 SBP {vitals['sbp']} mmHg")
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        lactate = ((labs.get("lac") or labs.get("lactate") or {}) if isinstance(labs.get("lac") or labs.get("lactate"), dict) else {}).get("value")
        if lactate is not None:
            try:
                if float(lactate) >= 2:
                    problems.append(f"高乳酸血症 {lactate}")
            except Exception:
                pass
        for alert in recent_alerts[:8]:
            name = str(alert.get("name") or alert.get("alert_type") or "").strip()
            if name and name not in problems:
                problems.append(name)
        risk_level = str((temporal_forecast or {}).get("risk_level") or "").strip()
        current_probability = (temporal_forecast or {}).get("current_probability")
        if risk_level:
            problems.append(f"未来恶化风险 {risk_level} ({current_probability})")
        return problems[:12]

    def _rag_tags(self, patient_doc: dict, facts: dict[str, Any]) -> list[str]:
        if hasattr(self.alert_engine, "_infer_rag_tags"):
            try:
                return list(self.alert_engine._infer_rag_tags(patient_doc, facts))
            except Exception:
                return []
        return []

    def _search_guidelines(self, query: str, *, patient_doc: dict, facts: dict[str, Any]) -> list[dict[str, Any]]:
        if self.rag_service is None or not query.strip():
            return []
        cfg = self._cfg()
        top_k = max(2, int(cfg.get("rag_top_k", 6) or 6))
        raw_hits = self.rag_service.search(query, top_k=max(top_k * 2, 8), tags=self._rag_tags(patient_doc, facts) or None)
        type_filters = [str(x).strip().lower() for x in cfg.get("reference_types", ["guideline", "consensus", "meta-analysis"]) if str(x).strip()]
        if not type_filters:
            return raw_hits[:top_k]
        filtered: list[dict[str, Any]] = []
        for item in raw_hits:
            hay = " ".join(
                str(item.get(key) or "").lower()
                for key in ("category", "source", "title", "section_title", "recommendation", "content", "topic")
            )
            if any(token in hay for token in type_filters):
                filtered.append(item)
        return (filtered or raw_hits)[:top_k]

    def _compose_prompt(self, twin: dict[str, Any], rag_hits: list[dict[str, Any]]) -> str:
        lines = [
            "患者数字孪生上下文:",
            json.dumps(twin, ensure_ascii=False, default=str),
        ]
        if rag_hits:
            lines.append("")
            lines.append("相关指南与循证证据(RAG):")
            for idx, item in enumerate(rag_hits[:8], start=1):
                quote = str(item.get("content") or "").strip()
                if len(quote) > 260:
                    quote = quote[:260] + "..."
                lines.append(
                    f"[{idx}] chunk_id={item.get('chunk_id') or ''} | source={item.get('source') or ''} | "
                    f"recommendation={item.get('recommendation') or ''} | grade={item.get('recommendation_grade') or ''}"
                )
                if quote:
                    lines.append(quote)
        return "\n".join(lines)

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        content = str(text or "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content)
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _fallback_plan(self, twin: dict[str, Any], rag_hits: list[dict[str, Any]]) -> dict[str, Any]:
        problems = list(twin.get("problem_list") or [])
        first_problem = problems[0] if problems else "需结合床旁复核当前核心问题"
        return {
            "overview": {"summary": first_problem, "core_problems": problems[:6]},
            "dynamic_assessment": {"summary": "AI 结构化推理失败，已回退为基础摘要。", "key_changes_24h": problems[:4]},
            "risk_identification": [{"priority": 1, "risk": first_problem, "urgency": "high", "basis": "来自当前诊断、预警与趋势数据"}],
            "differential_diagnosis": [{"problem": first_problem, "considerations": ["请结合感染、循环、呼吸与肾功能进一步鉴别"]}],
            "treatment_recommendations": [{
                "priority": 1,
                "recommendation": "优先复核生命体征、近期化验和高等级预警，必要时升级床旁评估。",
                "rationale": "当前仅能依据结构化输入做有限总结。",
                "evidence_level": "expert_opinion",
                "guideline_refs": [str(item.get("chunk_id") or "") for item in rag_hits[:3] if item.get("chunk_id")],
                "safety_notes": ["需由临床医生结合实时病情决策"],
            }],
            "monitoring_focus": [{"item": "生命体征趋势", "target": "连续监测", "threshold": "若继续恶化需即时复评", "window": "6-12h"}],
            "prognosis_assessment": {"summary": "需结合后续动态变化判断短期预后。", "short_term_outlook": "uncertain", "confidence": 0.3},
            "evidence_sources": self._normalize_evidence(rag_hits),
        }

    def _normalize_evidence(self, rag_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in rag_hits[:8]:
            rows.append(
                {
                    "chunk_id": str(item.get("chunk_id") or ""),
                    "source": str(item.get("source") or ""),
                    "recommendation": str(item.get("recommendation") or ""),
                    "quote": str(item.get("content") or "")[:260],
                }
            )
        return rows

    def _normalize_plan(self, raw: dict[str, Any], rag_hits: list[dict[str, Any]]) -> dict[str, Any]:
        result = raw if isinstance(raw, dict) else {}
        overview = result.get("overview") if isinstance(result.get("overview"), dict) else {}
        dynamic = result.get("dynamic_assessment") if isinstance(result.get("dynamic_assessment"), dict) else {}
        prognosis = result.get("prognosis_assessment") if isinstance(result.get("prognosis_assessment"), dict) else {}
        risks = result.get("risk_identification") if isinstance(result.get("risk_identification"), list) else []
        differentials = result.get("differential_diagnosis") if isinstance(result.get("differential_diagnosis"), list) else []
        treatments = result.get("treatment_recommendations") if isinstance(result.get("treatment_recommendations"), list) else []
        monitoring = result.get("monitoring_focus") if isinstance(result.get("monitoring_focus"), list) else []

        normalized_treatments: list[dict[str, Any]] = []
        for idx, item in enumerate(treatments[:8], start=1):
            if not isinstance(item, dict):
                continue
            normalized_treatments.append(
                {
                    "priority": int(item.get("priority") or idx),
                    "recommendation": str(item.get("recommendation") or "").strip(),
                    "rationale": str(item.get("rationale") or "").strip(),
                    "evidence_level": str(item.get("evidence_level") or "unspecified").strip(),
                    "guideline_refs": [str(x) for x in (item.get("guideline_refs") if isinstance(item.get("guideline_refs"), list) else [])[:5]],
                    "safety_notes": [str(x) for x in (item.get("safety_notes") if isinstance(item.get("safety_notes"), list) else [])[:4]],
                }
            )
        evidence_sources = result.get("evidence_sources") if isinstance(result.get("evidence_sources"), list) else []
        normalized_evidence = []
        for item in evidence_sources[:8]:
            if not isinstance(item, dict):
                continue
            normalized_evidence.append(
                {
                    "chunk_id": str(item.get("chunk_id") or ""),
                    "source": str(item.get("source") or ""),
                    "recommendation": str(item.get("recommendation") or ""),
                    "quote": str(item.get("quote") or item.get("content") or "")[:260],
                }
            )
        if not normalized_evidence:
            normalized_evidence = self._normalize_evidence(rag_hits)

        return {
            "overview": {
                "summary": str(overview.get("summary") or "").strip(),
                "core_problems": [str(x).strip() for x in (overview.get("core_problems") if isinstance(overview.get("core_problems"), list) else [])[:8] if str(x).strip()],
            },
            "dynamic_assessment": {
                "summary": str(dynamic.get("summary") or "").strip(),
                "key_changes_24h": [str(x).strip() for x in (dynamic.get("key_changes_24h") if isinstance(dynamic.get("key_changes_24h"), list) else [])[:8] if str(x).strip()],
            },
            "risk_identification": [
                {
                    "priority": int(item.get("priority") or idx + 1),
                    "risk": str(item.get("risk") or "").strip(),
                    "urgency": str(item.get("urgency") or "medium").strip().lower(),
                    "basis": str(item.get("basis") or "").strip(),
                }
                for idx, item in enumerate(risks[:8]) if isinstance(item, dict) and str(item.get("risk") or "").strip()
            ],
            "differential_diagnosis": [
                {
                    "problem": str(item.get("problem") or "").strip(),
                    "considerations": [str(x).strip() for x in (item.get("considerations") if isinstance(item.get("considerations"), list) else [])[:6] if str(x).strip()],
                }
                for item in differentials[:6] if isinstance(item, dict) and str(item.get("problem") or "").strip()
            ],
            "treatment_recommendations": normalized_treatments,
            "monitoring_focus": [
                {
                    "item": str(item.get("item") or "").strip(),
                    "target": str(item.get("target") or "").strip(),
                    "threshold": str(item.get("threshold") or "").strip(),
                    "window": str(item.get("window") or "6-12h").strip(),
                }
                for item in monitoring[:10] if isinstance(item, dict) and str(item.get("item") or "").strip()
            ],
            "prognosis_assessment": {
                "summary": str(prognosis.get("summary") or "").strip(),
                "short_term_outlook": str(prognosis.get("short_term_outlook") or "").strip(),
                "confidence": max(0.0, min(1.0, float(prognosis.get("confidence") or 0.5))),
            },
            "evidence_sources": normalized_evidence,
        }

    async def _persist_plan(self, *, patient_doc: dict, twin: dict[str, Any], plan: dict[str, Any], rag_hits: list[dict[str, Any]], model: str, generated_at: datetime) -> dict[str, Any]:
        payload = {
            "patient_id": str(patient_doc.get("_id")),
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "clinical_reasoning_plan",
            "summary": (plan.get("overview") or {}).get("summary"),
            "problem_list": twin.get("problem_list") or [],
            "digital_twin": twin,
            "plan": plan,
            "evidence_sources": plan.get("evidence_sources") or self._normalize_evidence(rag_hits),
            "model": model,
            "calc_time": generated_at,
            "updated_at": generated_at,
            "month": generated_at.strftime("%Y-%m"),
            "day": generated_at.strftime("%Y-%m-%d"),
        }
        latest = await self.db.col("score_records").find_one(
            {
                "patient_id": str(patient_doc.get("_id")),
                "score_type": "clinical_reasoning_plan",
                "calc_time": {"$gte": generated_at - timedelta(minutes=max(30, int(self._cfg().get("persist_window_minutes", 60) or 60)))},
            },
            sort=[("calc_time", -1)],
        )
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
            payload["_id"] = latest["_id"]
        else:
            res = await self.db.col("score_records").insert_one(payload)
            payload["_id"] = res.inserted_id
        return payload

    async def generate_individualized_plan(self, patient_id: str) -> dict[str, Any] | None:
        try:
            patient_doc = await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            patient_doc = None
        if patient_doc is None:
            return None

        twin = await self.build_digital_twin(patient_id, patient_doc)
        query = "；".join([str(x) for x in (twin.get("problem_list") or [])[:8]])
        rag_hits = self._search_guidelines(query, patient_doc=patient_doc, facts=twin.get("facts") or {})
        prompt = self._compose_prompt(twin, rag_hits)

        model = self.config.llm_model_medical or self.config.settings.LLM_MODEL
        llm_cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("llm", {})
        start_ms = AiMonitor.now_ms() if self.ai_monitor else 0.0
        raw_text = ""
        usage = None
        meta: dict[str, Any] = {}

        try:
            result = await call_llm_chat(
                cfg=self.config,
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=prompt,
                model=model,
                temperature=float(llm_cfg.get("temperature", 0.1) or 0.1),
                max_tokens=min(3200, int(llm_cfg.get("max_tokens", 4096) or 4096)),
                timeout_seconds=float(llm_cfg.get("timeout", 60) or 60),
            )
            raw_text = str(result.get("text") or "")
            usage = result.get("usage")
            model = str(result.get("model") or model)
            meta = result.get("meta") or {}
            parsed = self._parse_json(raw_text)
        except Exception as exc:
            logger.error("clinical reasoning llm error: %s", exc)
            parsed = None
            meta = {"error": str(exc)[:200]}

        plan = self._normalize_plan(parsed, rag_hits) if isinstance(parsed, dict) else self._fallback_plan(twin, rag_hits)
        generated_at = datetime.now()
        record = await self._persist_plan(
            patient_doc=patient_doc,
            twin=twin,
            plan=plan,
            rag_hits=rag_hits,
            model=model,
            generated_at=generated_at,
        )

        if self.ai_monitor:
            await self.ai_monitor.log_llm_call(
                module="clinical_reasoning",
                model=model,
                prompt=prompt,
                output=raw_text or json.dumps(plan, ensure_ascii=False, default=str),
                latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                success=bool(parsed),
                meta=meta,
                usage=usage,
            )
        return record
