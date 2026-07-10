"""Clinical document generation service."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.services.ai_monitor import AiMonitor
from app.services.llm_runtime import call_llm_chat
from app.clinical_documents.daily_progress_renderer import render_daily_progress_from_structured

logger = logging.getLogger("icu-alert")
API_TZ = ZoneInfo("Asia/Shanghai")


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
        now = datetime.now(API_TZ)
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
        return await self.db.col("score").find_one(
            {"patient_id": patient_id, "score_type": "clinical_reasoning_plan"},
            sort=[("calc_time", -1)],
        )

    async def _latest_proactive_plan(self, patient_id: str) -> dict[str, Any] | None:
        return await self.db.col("score").find_one(
            {"patient_id": patient_id, "score_type": "proactive_management"},
            sort=[("calc_time", -1)],
        )

    async def _latest_daily_progress_summary(self, patient_id: str) -> str:
        try:
            draft = await self.db.col("clinical_document_drafts").find_one(
                {"patient_id": patient_id, "doc_type": {"$in": ["progress_note_24h", "daily_progress"]}, "status": {"$in": ["finalized", "draft", "saved"]}},
                sort=[("updated_at", -1)],
            )
            content = (draft or {}).get("current_content") if isinstance(draft, dict) else None
            preview = (content or {}).get("note_preview") if isinstance(content, dict) else {}
            text = str((preview or {}).get("final_text_override") or (preview or {}).get("generated_text") or "").strip()
            if text:
                for marker in ("今日评估：", "今日评估:"):
                    if marker in text:
                        return text.split(marker, 1)[1].split("\n", 1)[0].strip("。 ")
                return text.splitlines()[0].strip("。 ")
        except Exception:
            pass
        try:
            score = await self.db.col("score").find_one(
                {"patient_id": patient_id, "score_type": "clinical_document", "doc_type": "daily_progress"},
                sort=[("calc_time", -1)],
            )
            document = (score or {}).get("document") if isinstance(score, dict) else {}
            text = str((document or {}).get("document_text") or (score or {}).get("summary") or "").strip()
            if text:
                for marker in ("今日评估：", "今日评估:"):
                    if marker in text:
                        return text.split(marker, 1)[1].split("\n", 1)[0].strip("。 ")
                return text.splitlines()[0].strip("。 ")
        except Exception:
            pass
        return ""

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
        previous_daily_progress = await self._latest_daily_progress_summary(patient_id)
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
            doc async for doc in self.db.col("score").find(
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
            "previous_daily_progress_summary": previous_daily_progress,
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

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _fallback_mdt_summary(self, template: DocumentTemplate, structured_data: dict[str, Any]) -> dict[str, Any]:
        patient = structured_data.get("patient") if isinstance(structured_data.get("patient"), dict) else {}
        vitals = structured_data.get("latest_vitals") if isinstance(structured_data.get("latest_vitals"), dict) else {}
        alerts = structured_data.get("alerts_24h") if isinstance(structured_data.get("alerts_24h"), list) else []
        labs = structured_data.get("labs_24h") if isinstance(structured_data.get("labs_24h"), list) else []
        drugs = structured_data.get("drugs_24h") if isinstance(structured_data.get("drugs_24h"), list) else []
        problem_list = structured_data.get("problem_list") if isinstance(structured_data.get("problem_list"), list) else []
        reasoning = structured_data.get("clinical_reasoning") if isinstance(structured_data.get("clinical_reasoning"), dict) else {}

        diagnosis = str(patient.get("diagnosis") or "未提供诊断").strip()
        alert_titles = [
            self._first_text(item.get("name"), item.get("alert_type"), item.get("parameter"))
            for item in alerts[:5]
            if isinstance(item, dict)
        ]
        alert_titles = [item for item in alert_titles if item]
        problem_titles = [
            self._first_text(item.get("problem") if isinstance(item, dict) else item, item.get("title") if isinstance(item, dict) else "")
            for item in problem_list[:5]
        ]
        problem_titles = [item for item in problem_titles if item]
        vital_parts = []
        for label, key in (("HR", "hr"), ("MAP", "map"), ("SpO2", "spo2"), ("RR", "rr"), ("体温", "temp")):
            if vitals.get(key) is not None:
                vital_parts.append(f"{label} {vitals.get(key)}")
        lab_parts = []
        for item in labs[:6]:
            if not isinstance(item, dict):
                continue
            name = self._first_text(item.get("itemName"), item.get("itemCnName"), item.get("name"))
            value = self._first_text(item.get("result"), item.get("resultValue"), item.get("value"))
            if name and value:
                lab_parts.append(f"{name} {value}")
        drug_parts = [
            self._first_text(item.get("drugName"), item.get("orderName"), item.get("name"))
            for item in drugs[:6]
            if isinstance(item, dict)
        ]
        drug_parts = [item for item in drug_parts if item]

        actions = []
        for source in (reasoning.get("recommendations"), reasoning.get("action_items"), reasoning.get("plan")):
            if isinstance(source, list):
                for item in source[:5]:
                    if isinstance(item, dict):
                        text = self._first_text(item.get("action"), item.get("recommendation"), item.get("title"))
                    else:
                        text = str(item or "").strip()
                    if text:
                        actions.append(text)
            elif isinstance(source, str) and source.strip():
                actions.append(source.strip())
        if not actions and alert_titles:
            actions.append("围绕高优先级告警逐项确认问题、责任人、处理时限和复评指标。")
        if not actions:
            actions.append("先由主持医生确认主要问题，再形成不超过 3 条可执行决议。")

        sections = [
            {
                "heading": "患者概况",
                "content": f"患者 {patient.get('name') or '未知'}，床位 {patient.get('bed') or '未提供'}，主要诊断：{diagnosis}。",
            },
            {
                "heading": "本次MDT要解决的问题",
                "content": "；".join(problem_titles[:4] or alert_titles[:4] or ["当前结构化数据未形成明确问题清单，需结合床旁情况确认主要矛盾。"]),
            },
            {
                "heading": "关键证据",
                "content": "；".join((vital_parts + lab_parts + alert_titles)[:8] or ["暂无足够结构化证据，建议先核对生命体征、检验、用药和重要告警。"]),
            },
            {
                "heading": "决议草案",
                "content": "；".join(actions[:5]),
            },
            {
                "heading": "负责人和复评",
                "content": "每条决议需记录负责人、执行时限、监测指标和复评时间；建议按 6h/12h/24h 复评病情、指标变化和决议执行结果。",
            },
            {
                "heading": "安全提示",
                "content": "以上为结构化数据生成的MDT讨论草稿，仅供会诊记录整理；涉及医嘱、侵入操作、用药调整和生命支持变更，必须由执业医生确认。",
            },
        ]
        text = "\n".join([f"{item['heading']}：{item['content']}" for item in sections])
        return {"title": template.title, "sections": sections, "document_text": text, "key_facts_used": (vital_parts + lab_parts + alert_titles)[:12]}

    def _fallback_document(self, template: DocumentTemplate, structured_data: dict[str, Any]) -> dict[str, Any]:
        if template.doc_type == "mdt_summary":
            return self._fallback_mdt_summary(template, structured_data)
        patient = structured_data.get("patient") if isinstance(structured_data.get("patient"), dict) else {}
        vitals = structured_data.get("latest_vitals") if isinstance(structured_data.get("latest_vitals"), dict) else {}
        labs = structured_data.get("labs_24h") if isinstance(structured_data.get("labs_24h"), list) else []
        drugs = structured_data.get("drugs_24h") if isinstance(structured_data.get("drugs_24h"), list) else []
        problem_list = structured_data.get("problem_list") if isinstance(structured_data.get("problem_list"), list) else []
        reasoning = structured_data.get("clinical_reasoning") if isinstance(structured_data.get("clinical_reasoning"), dict) else {}
        diagnosis = str(patient.get("diagnosis") or "未提供诊断").strip()
        alerts = structured_data.get("alerts_24h") if isinstance(structured_data.get("alerts_24h"), list) else []
        alert_titles = [
            self._first_text(item.get("name"), item.get("alert_type"), item.get("parameter"))
            for item in alerts[:4]
            if isinstance(item, dict)
        ]
        alert_titles = [item for item in alert_titles if item]
        vital_parts = []
        for label, key in (("HR", "hr"), ("MAP", "map"), ("SpO2", "spo2"), ("RR", "rr"), ("体温", "temp")):
            if vitals.get(key) is not None:
                vital_parts.append(f"{label} {vitals.get(key)}")
        lab_parts = []
        for item in labs[:6]:
            if not isinstance(item, dict):
                continue
            name = self._first_text(item.get("itemName"), item.get("itemCnName"), item.get("name"))
            value = self._first_text(item.get("result"), item.get("resultValue"), item.get("value"))
            if name and value:
                lab_parts.append(f"{name} {value}")
        drug_parts = [
            self._first_text(item.get("drugName"), item.get("orderName"), item.get("name"))
            for item in drugs[:6]
            if isinstance(item, dict)
        ]
        drug_parts = [item for item in drug_parts if item]
        problem_titles = [
            self._first_text(item.get("problem") if isinstance(item, dict) else item, item.get("title") if isinstance(item, dict) else "")
            for item in problem_list[:5]
        ]
        problem_titles = [item for item in problem_titles if item]
        plan_items: list[str] = []
        for source in (reasoning.get("recommendations"), reasoning.get("action_items"), reasoning.get("plan")):
            if isinstance(source, list):
                for item in source[:5]:
                    text = self._first_text(item.get("action"), item.get("recommendation"), item.get("title")) if isinstance(item, dict) else str(item or "").strip()
                    if text:
                        plan_items.append(text)
            elif isinstance(source, str) and source.strip():
                plan_items.append(source.strip())

        if template.doc_type == "consultation_request":
            sections = [
                {"heading": "会诊目的", "content": "请相关专科协助评估当前主要问题、处理优先级和复评计划。"},
                {"heading": "患者概况", "content": f"患者 {patient.get('name') or '未知'}，床位 {patient.get('bed') or '未提供'}，主要诊断：{diagnosis}。"},
                {"heading": "申请会诊原因", "content": "；".join(problem_titles[:4] or alert_titles[:4] or ["当前结构化数据不足，需结合床旁病情明确会诊问题。"])},
                {"heading": "目前资料摘要", "content": "；".join((vital_parts + lab_parts + drug_parts)[:8] or ["暂无足够生命体征、检验或用药摘要。"])},
                {"heading": "需协助解决事项", "content": "请给出诊断判断、治疗方向、风险边界和下一次复评时间；高风险处置需由主管医生确认。"},
            ]
        elif template.doc_type == "daily_progress":
            sections = [
                {"heading": "病情变化", "content": "；".join((vital_parts + alert_titles)[:8] or ["近24小时结构化趋势不足，需补充床旁观察和监护数据。"])},
                {"heading": "今日评估", "content": f"主要诊断：{diagnosis}。当前重点问题：{'；'.join(problem_titles[:4] or alert_titles[:4] or ['暂未形成明确问题清单'])}。"},
                {"heading": "处理经过", "content": "；".join(drug_parts[:6] or ["暂无可用用药/治疗执行摘要，需由责任医生补充。"])},
                {"heading": "后续计划", "content": "；".join(plan_items[:5] or ["继续复核生命体征、检验、用药和治疗反应，按病情制定复评计划。"])},
                {"heading": "安全提示", "content": "本病程为结构化数据辅助草稿，需执业医生审核后写入正式病历。"},
            ]
        else:
            sections = [
                {"heading": "患者概况", "content": f"患者 {patient.get('name') or '未知'}，床位 {patient.get('bed') or '未提供'}，主要诊断：{diagnosis}。"},
                {"heading": "当前情况", "content": "已基于当前结构化数据生成基础草稿，需由责任医生结合床旁情况补充确认。"},
                {"heading": "重点问题", "content": "；".join(alert_titles or ["暂无足够结构化告警信息，建议先核对生命体征、检验、用药和治疗计划。"])},
            ]
        text = "\n".join([f"{item['heading']}：{item['content']}" for item in sections])
        return {"title": template.title, "sections": sections, "document_text": text, "key_facts_used": (vital_parts + lab_parts + alert_titles)[:12]}

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
        if template.doc_type == "daily_progress":
            result = render_daily_progress_from_structured(structured_data)
            normalized = {
                "title": str(result.get("title") or template.title),
                "sections": result.get("sections") or [],
                "document_text": str(result.get("document_text") or ""),
                "key_facts_used": result.get("key_facts_used") or [],
                "risk_profile": result.get("risk_profile") or "uncertain",
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
        latest = await self.db.col("score").find_one(
            {
                "patient_id": str(patient_doc.get("_id")),
                "score_type": "clinical_document",
                "doc_type": doc_type,
                "calc_time": {"$gte": generated_at - timedelta(minutes=max(15, int(self._cfg().get("persist_window_minutes", 30) or 30)))},
            },
            sort=[("calc_time", -1)],
        )
        if latest:
            await self.db.col("score").update_one({"_id": latest["_id"]}, {"$set": payload})
            payload["_id"] = latest["_id"]
        else:
            res = await self.db.col("score").insert_one(payload)
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
            + " 会诊申请单必须突出会诊目的、申请原因、需协助解决事项；日常病程记录必须突出病情变化、今日评估、处理经过、后续计划，两者不得使用同一套段落。"
        )

        llm_cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("llm", {})
        model = self.config.llm_reasoning_model or self.config.llm_model_medical or self.config.settings.LLM_MODEL
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
        generated_at = datetime.now(API_TZ)
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
