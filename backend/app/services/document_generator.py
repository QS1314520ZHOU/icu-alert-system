"""Clinical document generation service."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.services.ai_monitor import AiMonitor
from app.services.llm_runtime import call_llm_chat

logger = logging.getLogger("icu-alert")


@dataclass(frozen=True)
class DocumentTemplate:
    doc_type: str
    title: str
    writing_style: str
    required_fields: list[str]
    system_prompt: str


class ClinicalDocumentGenerator:
    def __init__(self, *, db, config, alert_engine, rag_service=None, ai_monitor=None, ai_handoff_service=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self.rag_service = rag_service
        self.ai_monitor = ai_monitor
        self.ai_handoff_service = ai_handoff_service
        self.DOCUMENT_TYPES: dict[str, DocumentTemplate] = {
            "admission_note": DocumentTemplate(
                doc_type="admission_note",
                title="入ICU记录",
                writing_style="病历书写规范、条理清晰、突出入科指征与初始评估",
                required_fields=["patient", "diagnosis", "latest_vitals", "labs_24h", "alerts_24h", "drugs_24h", "reasoning_plan"],
                system_prompt="你是ICU病历文书助手。请根据结构化数据生成规范的入ICU记录，必须忠于事实，不得编造。"
            ),
            "daily_progress": DocumentTemplate(
                doc_type="daily_progress",
                title="日常病程记录",
                writing_style="按病情变化、评估、处理、计划的病程记录风格书写",
                required_fields=["patient", "latest_vitals", "trend_24h", "labs_24h", "drugs_24h", "alerts_24h", "clinical_reasoning"],
                system_prompt="你是ICU主治医师助手。请根据近24小时数据生成规范日常病程记录，强调动态变化、评估和计划。"
            ),
            "consultation_request": DocumentTemplate(
                doc_type="consultation_request",
                title="会诊申请单",
                writing_style="简洁、聚焦会诊目的、当前问题和拟解决事项",
                required_fields=["patient", "problem_list", "latest_vitals", "labs_24h", "alerts_24h", "consult_focus"],
                system_prompt="你是ICU会诊文书助手。请生成一份清晰规范的会诊申请单，说明患者概况、会诊目的、需协助问题。"
            ),
            "mdt_summary": DocumentTemplate(
                doc_type="mdt_summary",
                title="MDT讨论材料",
                writing_style="结构化、多学科讨论提纲风格，突出争议点和决策点",
                required_fields=["patient", "problem_list", "latest_vitals", "labs_24h", "treatments", "clinical_reasoning", "evidence"],
                system_prompt="你是ICU MDT讨论秘书。请生成用于多学科讨论的材料摘要，包含核心问题、证据、待决策事项。"
            ),
            "discharge_summary": DocumentTemplate(
                doc_type="discharge_summary",
                title="转出/出科记录",
                writing_style="概括住院经过、当前状态、后续建议，适合交接下级病区",
                required_fields=["patient", "problem_list", "latest_vitals", "recent_scores", "proactive_plan", "clinical_reasoning"],
                system_prompt="你是ICU转出记录助手。请生成规范的转出/出科摘要，概括病情经过、当前问题与后续计划。"
            ),
            "nursing_handoff": DocumentTemplate(
                doc_type="nursing_handoff",
                title="护理交班记录",
                writing_style="护理交班语言，聚焦设备、风险、待执行事项、观察重点",
                required_fields=["patient", "latest_vitals", "nursing_context", "alerts_24h", "drugs_24h", "proactive_plan"],
                system_prompt="你是ICU护理交班助手。请生成规范护理交班记录，突出护理风险、装置、医嘱执行和观察重点。"
            ),
        }

    def _cfg(self) -> dict[str, Any]:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("document_generation", {})
        return cfg if isinstance(cfg, dict) else {}

    def _time_range(self, time_range: dict[str, Any] | None) -> tuple[datetime, datetime]:
        now = datetime.now()
        if not isinstance(time_range, dict):
            hours = int(self._cfg().get("default_hours", 24) or 24)
            return now - timedelta(hours=max(hours, 1)), now
        start = time_range.get("start")
        end = time_range.get("end")
        try:
            start_dt = datetime.fromisoformat(str(start)) if start else None
        except Exception:
            start_dt = None
        try:
            end_dt = datetime.fromisoformat(str(end)) if end else None
        except Exception:
            end_dt = None
        if end_dt is None:
            end_dt = now
        if start_dt is None:
            hours = int(time_range.get("hours") or self._cfg().get("default_hours", 24) or 24)
            start_dt = end_dt - timedelta(hours=max(hours, 1))
        return start_dt, end_dt

    async def _load_patient(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            return None

    async def _latest_clinical_reasoning(self, patient_id: str) -> dict[str, Any] | None:
        return await self.db.col("score_records").find_one(
            {"patient_id": patient_id, "score_type": "clinical_reasoning_plan"},
            sort=[("calc_time", -1)],
        )

    async def _latest_proactive_plan(self, patient_id: str) -> dict[str, Any] | None:
        return await self.db.col("score_records").find_one(
            {"patient_id": patient_id, "score_type": "proactive_management"},
            sort=[("calc_time", -1)],
        )

    async def extract_structured_data(self, patient_id: str, required_fields: list[str], time_range: dict[str, Any] | None = None) -> dict[str, Any] | None:
        patient_doc = await self._load_patient(patient_id)
        if not patient_doc:
            return None
        start, end = self._time_range(time_range)

        handoff_context = None
        if self.ai_handoff_service is not None and hasattr(self.ai_handoff_service, "_build_context"):
            try:
                handoff_context = await self.ai_handoff_service._build_context(patient_id, patient_doc, similar_case_review=None, nursing_context=None)
            except Exception:
                handoff_context = None

        facts = await self.alert_engine._collect_patient_facts(patient_doc, patient_doc.get("_id")) if hasattr(self.alert_engine, "_collect_patient_facts") else {}
        reasoning_doc = await self._latest_clinical_reasoning(patient_id)
        proactive_doc = await self._latest_proactive_plan(patient_id)
        nursing_context = None
        if hasattr(self.alert_engine, "_collect_nursing_context"):
            try:
                nursing_context = await self.alert_engine._collect_nursing_context(patient_doc, patient_id, hours=max(12, int((end - start).total_seconds() / 3600)))
            except Exception:
                nursing_context = None
        temporal_forecast = None
        if hasattr(self.alert_engine, "_build_temporal_risk_forecast"):
            try:
                temporal_forecast = await self.alert_engine._build_temporal_risk_forecast(
                    patient_doc,
                    patient_doc.get("_id"),
                    lookback_hours=max(12, int((end - start).total_seconds() / 3600)),
                    horizons=(4, 8, 12),
                    include_history=True,
                )
            except Exception:
                temporal_forecast = None

        alerts = [
            doc async for doc in self.db.col("alert_records").find(
                {"patient_id": {"$in": [patient_id, patient_doc.get("_id")]}, "created_at": {"$gte": start, "$lte": end}},
                {"name": 1, "alert_type": 1, "severity": 1, "created_at": 1, "explanation": 1, "parameter": 1, "value": 1},
            ).sort("created_at", -1).limit(80)
        ]
        scores = [
            doc async for doc in self.db.col("score_records").find(
                {"patient_id": {"$in": [patient_id, patient_doc.get("_id")]}, "calc_time": {"$gte": start, "$lte": end}},
                {"score_type": 1, "score": 1, "risk_level": 1, "summary": 1, "calc_time": 1, "interventions": 1, "plan": 1},
            ).sort("calc_time", -1).limit(80)
        ]
        drugs = []
        if handoff_context and isinstance(handoff_context.get("drugs_12h"), list):
            drugs = handoff_context.get("drugs_12h") or []
        labs = []
        if handoff_context and isinstance(handoff_context.get("labs_12h"), list):
            labs = handoff_context.get("labs_12h") or []

        structured = {
            "patient": {
                "id": patient_id,
                "name": patient_doc.get("name") or "",
                "bed": patient_doc.get("hisBed") or patient_doc.get("bed") or "",
                "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
                "diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "",
                "nursing_level": patient_doc.get("nursingLevel") or "",
                "icu_admission_time": patient_doc.get("icuAdmissionTime"),
            },
            "time_range": {"start": start, "end": end},
            "latest_vitals": (handoff_context or {}).get("latest_vitals") or facts.get("vitals") or {},
            "labs_24h": labs,
            "drugs_24h": drugs,
            "alerts_24h": alerts,
            "recent_scores": scores,
            "nursing_context": nursing_context or {},
            "clinical_reasoning": (reasoning_doc or {}).get("plan") or {},
            "reasoning_plan": (reasoning_doc or {}).get("plan") or {},
            "proactive_plan": proactive_doc or {},
            "problem_list": (reasoning_doc or {}).get("problem_list") or [],
            "trend_24h": temporal_forecast or {},
            "consult_focus": (reasoning_doc or {}).get("problem_list") or [],
            "treatments": drugs[:20],
            "evidence": (reasoning_doc or {}).get("evidence_sources") or [],
            "diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "",
        }
        if required_fields:
            structured["requested_fields"] = [field for field in required_fields]
        return structured

    def _rag_query(self, structured_data: dict[str, Any], doc_type: str) -> str:
        parts = [doc_type]
        patient = structured_data.get("patient") if isinstance(structured_data.get("patient"), dict) else {}
        diagnosis = str(patient.get("diagnosis") or "").strip()
        if diagnosis:
            parts.append(diagnosis)
        for item in (structured_data.get("problem_list") or [])[:6]:
            text = str(item).strip()
            if text:
                parts.append(text)
        return "；".join(parts)

    def _rag_hits(self, structured_data: dict[str, Any], doc_type: str) -> list[dict[str, Any]]:
        if self.rag_service is None:
            return []
        top_k = max(2, int(self._cfg().get("rag_top_k", 5) or 5))
        try:
            return self.rag_service.search(self._rag_query(structured_data, doc_type), top_k=top_k)
        except Exception:
            return []

    def _compose_prompt(self, template: DocumentTemplate, structured_data: dict[str, Any], rag_hits: list[dict[str, Any]]) -> str:
        lines = [
            f"文书类型: {template.title}",
            f"写作风格: {template.writing_style}",
            "结构化数据:",
            json.dumps(structured_data, ensure_ascii=False, default=str),
        ]
        if rag_hits:
            lines.append("")
            lines.append("相关文书/诊疗参考证据(RAG):")
            for idx, item in enumerate(rag_hits[:6], start=1):
                content = str(item.get("content") or "").strip()
                if len(content) > 220:
                    content = content[:220] + "..."
                lines.append(
                    f"[{idx}] chunk_id={item.get('chunk_id') or ''} | source={item.get('source') or ''} | recommendation={item.get('recommendation') or ''}"
                )
                if content:
                    lines.append(content)
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

    def _fallback_document(self, template: DocumentTemplate, structured_data: dict[str, Any]) -> dict[str, Any]:
        patient = structured_data.get("patient") if isinstance(structured_data.get("patient"), dict) else {}
        diagnosis = str(patient.get("diagnosis") or "未提供诊断").strip()
        sections = [
            {"heading": "患者概况", "content": f"患者 {patient.get('name') or '未知'}，床位 {patient.get('bed') or '未提供'}，主要诊断：{diagnosis}。"},
            {"heading": "当前情况", "content": "AI 文书结构化生成失败，当前已回退为基础内容，请结合结构化数据人工补充。"},
        ]
        text = "\n".join([f"{item['heading']}：{item['content']}" for item in sections])
        return {"title": template.title, "sections": sections, "document_text": text, "key_facts_used": []}

    def _quality_checker(self, document: dict[str, Any], structured_data: dict[str, Any]) -> dict[str, Any]:
        text = json.dumps(document, ensure_ascii=False)
        vitals = structured_data.get("latest_vitals") if isinstance(structured_data.get("latest_vitals"), dict) else {}
        issues: list[dict[str, Any]] = []

        def check_numeric(label: str, keys: list[str], tol: float) -> None:
            observed = None
            for key in keys:
                value = vitals.get(key)
                if value is not None:
                    try:
                        observed = float(value)
                        break
                    except Exception:
                        continue
            if observed is None:
                return
            for match in re.finditer(rf"{label}[^\d]{{0,6}}(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE):
                try:
                    claimed = float(match.group(1))
                except Exception:
                    continue
                if abs(claimed - observed) > tol:
                    issues.append({"type": "numeric_mismatch", "field": label, "observed": observed, "claimed": claimed})

        check_numeric("HR", ["hr"], 8.0)
        check_numeric("SpO2", ["spo2"], 3.0)
        check_numeric("RR", ["rr"], 4.0)
        check_numeric("SBP", ["sbp"], 12.0)
        check_numeric("Temp", ["temp"], 0.6)

        drug_names = {
            str(item.get("drugName") or item.get("orderName") or "").strip()
            for item in (structured_data.get("drugs_24h") if isinstance(structured_data.get("drugs_24h"), list) else [])
            if str(item.get("drugName") or item.get("orderName") or "").strip()
        }
        if drug_names:
            capitalized_mentions = {m.group(0).strip() for m in re.finditer(r"[A-Za-z\u4e00-\u9fff]{2,20}", text)}
            suspicious = [name for name in capitalized_mentions if any(token in name for token in ["mg", "ml", "h"]) is False and name not in drug_names and name in {"肝素", "万古霉素", "美罗培南", "去甲肾上腺素"}]
            for item in suspicious[:4]:
                issues.append({"type": "drug_reference_unverified", "field": "drug", "claimed": item})

        sections = document.get("sections") if isinstance(document.get("sections"), list) else []
        if not sections:
            issues.append({"type": "structure_missing", "field": "sections"})

        return {
            "status": "warning" if issues else "ok",
            "issue_count": len(issues),
            "issues": issues,
        }

    def _normalize_document(self, raw: dict[str, Any], template: DocumentTemplate, structured_data: dict[str, Any], rag_hits: list[dict[str, Any]]) -> dict[str, Any]:
        result = raw if isinstance(raw, dict) else {}
        title = str(result.get("title") or template.title).strip() or template.title
        sections = result.get("sections") if isinstance(result.get("sections"), list) else []
        normalized_sections = []
        for item in sections[:10]:
            if not isinstance(item, dict):
                continue
            heading = str(item.get("heading") or "").strip()
            content = str(item.get("content") or "").strip()
            if heading and content:
                normalized_sections.append({"heading": heading, "content": content})
        document_text = str(result.get("document_text") or "").strip()
        if not document_text and normalized_sections:
            document_text = "\n".join([f"{item['heading']}：{item['content']}" for item in normalized_sections])
        key_facts = [str(x).strip() for x in (result.get("key_facts_used") if isinstance(result.get("key_facts_used"), list) else [])[:12] if str(x).strip()]
        normalized = {
            "title": title,
            "sections": normalized_sections,
            "document_text": document_text,
            "key_facts_used": key_facts,
            "evidence_sources": [
                {
                    "chunk_id": str(item.get("chunk_id") or ""),
                    "source": str(item.get("source") or ""),
                    "recommendation": str(item.get("recommendation") or ""),
                }
                for item in rag_hits[:6]
            ],
        }
        normalized["quality_check"] = self._quality_checker(normalized, structured_data)
        return normalized

    async def _persist(self, *, patient_doc: dict[str, Any], doc_type: str, structured_data: dict[str, Any], document: dict[str, Any], generated_at: datetime) -> dict[str, Any]:
        payload = {
            "patient_id": str(patient_doc.get("_id")),
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "clinical_document",
            "doc_type": doc_type,
            "title": document.get("title"),
            "summary": (document.get("sections") or [{}])[0].get("content") if document.get("sections") else "",
            "structured_data": structured_data,
            "document": document,
            "calc_time": generated_at,
            "updated_at": generated_at,
            "month": generated_at.strftime("%Y-%m"),
            "day": generated_at.strftime("%Y-%m-%d"),
        }
        latest = await self.db.col("score_records").find_one(
            {
                "patient_id": str(patient_doc.get("_id")),
                "score_type": "clinical_document",
                "doc_type": doc_type,
                "calc_time": {"$gte": generated_at - timedelta(minutes=max(15, int(self._cfg().get("persist_window_minutes", 30) or 30)))},
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

    async def generate(self, patient_id: str, doc_type: str, time_range: dict[str, Any] | None = None) -> dict[str, Any] | None:
        template = self.DOCUMENT_TYPES.get(str(doc_type).strip())
        if template is None:
            raise ValueError(f"unsupported doc_type: {doc_type}")
        patient_doc = await self._load_patient(patient_id)
        if not patient_doc:
            return None
        structured_data = await self.extract_structured_data(patient_id, template.required_fields, time_range)
        if not structured_data:
            return None
        rag_hits = self._rag_hits(structured_data, doc_type)
        prompt = self._compose_prompt(template, structured_data, rag_hits)
        system_prompt = (
            template.system_prompt
            + " 输出严格JSON，字段仅包含 title, sections, document_text, key_facts_used。"
            + " sections 为数组，每项包含 heading 和 content。"
            + " document_text 必须是完整自然语言文书。"
        )

        llm_cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("llm", {})
        model = self.config.llm_model_medical or self.config.settings.LLM_MODEL
        start_ms = AiMonitor.now_ms() if self.ai_monitor else 0.0
        raw_text = ""
        usage = None
        meta: dict[str, Any] = {}
        parsed = None
        try:
            result = await call_llm_chat(
                cfg=self.config,
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=model,
                temperature=float(self._cfg().get("temperature", llm_cfg.get("temperature", 0.1)) or 0.1),
                max_tokens=min(3200, int(self._cfg().get("max_tokens", llm_cfg.get("max_tokens", 4096)) or 3200)),
                timeout_seconds=float(self._cfg().get("timeout", llm_cfg.get("timeout", 60)) or 60),
            )
            raw_text = str(result.get("text") or "")
            usage = result.get("usage")
            model = str(result.get("model") or model)
            meta = result.get("meta") or {}
            parsed = self._parse_json(raw_text)
        except Exception as exc:
            logger.error("document generation llm error: %s", exc)
            meta = {"error": str(exc)[:200]}

        normalized = self._normalize_document(parsed, template, structured_data, rag_hits) if isinstance(parsed, dict) else self._normalize_document(self._fallback_document(template, structured_data), template, structured_data, rag_hits)
        generated_at = datetime.now()
        record = await self._persist(patient_doc=patient_doc, doc_type=doc_type, structured_data=structured_data, document=normalized, generated_at=generated_at)

        if self.ai_monitor:
            await self.ai_monitor.log_llm_call(
                module="document_generation",
                model=model,
                prompt=prompt,
                output=raw_text or json.dumps(normalized, ensure_ascii=False, default=str),
                latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                success=bool(parsed),
                meta={**meta, "doc_type": doc_type},
                usage=usage,
            )
        return record
