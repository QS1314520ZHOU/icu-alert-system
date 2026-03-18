"""AI报警归因摘要代理。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.services.ai_monitor import AiMonitor
from app.services.llm_runtime import call_llm_chat

from .scanner_alert_reasoning import AlertReasoningScanner

logger = logging.getLogger("icu-alert")
API_TZ = ZoneInfo("Asia/Shanghai")


class AlertReasoningAgentMixin:
    def _local_iso(self, value: datetime | None) -> str | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=API_TZ)
        return value.astimezone(API_TZ).isoformat()

    def _alert_reasoning_cfg(self) -> dict[str, Any]:
        cfg = self._cfg("alert_engine", "alert_reasoning_agent", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan_alert_reasoning(self) -> None:
        await AlertReasoningScanner(self).scan()

    async def _scan_single_patient_alert_reasoning(
        self,
        *,
        patient_doc: dict[str, Any],
        now: datetime,
        semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
    ) -> bool:
        pid = patient_doc.get("_id")
        if not pid:
            return False

        cfg = self._alert_reasoning_cfg()
        pid_str = str(pid)
        window_minutes = max(5, int(cfg.get("trigger_window_minutes", 30) or 30))
        min_active_alerts = max(2, int(cfg.get("min_active_alerts", 3) or 3))
        context_hours = max(1, int(cfg.get("recent_context_hours", 24) or 24))

        active_alerts = await self._reasoning_active_alerts(pid_str, window_minutes)
        if len(active_alerts) < min_active_alerts:
            return False

        cluster_signature = self._reasoning_cluster_signature(active_alerts)
        if self._reasoning_already_up_to_date(active_alerts, cluster_signature):
            return False

        try:
            facts = await self._collect_patient_facts(patient_doc, pid)
            facts["nursing_context"] = await self._collect_nursing_context(patient_doc, pid_str, hours=12)
        except Exception:
            return False

        recent_alerts = await self._reasoning_recent_alerts(pid_str, context_hours)
        context_snapshot = await self._build_alert_context_snapshot(
            patient_id=pid_str,
            patient_doc=patient_doc,
        )
        prompt_payload = self._build_alert_reasoning_payload(
            patient_doc=patient_doc,
            facts=facts,
            active_alerts=active_alerts,
            recent_alerts=recent_alerts,
            context_snapshot=context_snapshot,
            now=now,
            trigger_window_minutes=window_minutes,
        )
        prompt_text = self._compose_alert_reasoning_context(prompt_payload)
        rag_hits = self._retrieve_guideline_evidence(prompt_text, patient_doc, facts)
        full_prompt = self._compose_alert_reasoning_context(prompt_payload, rag_hits=rag_hits)

        cache_hash = hashlib.sha256(
            f"{cluster_signature}\n{full_prompt}".encode("utf-8")
        ).hexdigest()
        cached = self._read_ai_cache(pid_str, cache_hash) if hasattr(self, "_read_ai_cache") else None
        source = "cache"
        result = cached
        if not isinstance(result, dict):
            source = "llm"
            try:
                async with semaphore:
                    result = await self._call_alert_reasoning_analysis(full_prompt, client=client)
            except Exception:
                return False
            if not isinstance(result, dict):
                return False
            if hasattr(self, "_write_ai_cache"):
                self._write_ai_cache(pid_str, cache_hash, result, max(300, int(cfg.get("cache_ttl_seconds", 900) or 900)))

        normalized = self._normalize_alert_reasoning_output(
            result,
            active_alerts=active_alerts,
            rag_hits=rag_hits,
            cluster_signature=cluster_signature,
            analysis_source=source,
        )
        validation = await self._validate_alert_reasoning_output(normalized, facts)
        hallucination_flags = self._detect_hallucinations(normalized, facts)
        blocked_actions = set(validation.get("blocked_actions", []))
        if blocked_actions:
            normalized["priority_actions"] = [
                item for item in normalized.get("priority_actions", []) if str(item.get("action") or "") not in blocked_actions
            ]
            normalized["most_urgent_action"] = (
                normalized["priority_actions"][0]["action"] if normalized.get("priority_actions") else ""
            )
        normalized["safety_validation"] = validation
        normalized["hallucination_flags"] = hallucination_flags
        normalized["context_snapshot"] = context_snapshot or {}

        alert_ids = [row.get("_id") for row in active_alerts if row.get("_id") is not None]
        if not alert_ids:
            return False

        await self.db.col("alert_records").update_many(
            {"_id": {"$in": alert_ids}},
            {
                "$set": {
                    "reasoning": normalized,
                    "reasoning_updated_at": now,
                }
            },
        )
        return True

    async def _reasoning_active_alerts(self, patient_id: str, window_minutes: int) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(minutes=max(window_minutes, 1))
        cursor = self.db.col("alert_records").find(
            {
                "patient_id": patient_id,
                "is_active": True,
                "created_at": {"$gte": since},
                "alert_type": {"$nin": ["ai_risk"]},
                "category": {"$ne": "ai_analysis"},
            },
            {
                "_id": 1,
                "rule_id": 1,
                "name": 1,
                "alert_type": 1,
                "category": 1,
                "severity": 1,
                "parameter": 1,
                "condition": 1,
                "value": 1,
                "created_at": 1,
                "source_time": 1,
                "explanation": 1,
                "reasoning": 1,
            },
        ).sort("created_at", -1).limit(20)
        return [doc async for doc in cursor]

    async def _reasoning_recent_alerts(self, patient_id: str, hours: int) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(hours=max(hours, 1))
        cursor = self.db.col("alert_records").find(
            {
                "patient_id": patient_id,
                "created_at": {"$gte": since},
                "alert_type": {"$nin": ["ai_risk"]},
                "category": {"$ne": "ai_analysis"},
            },
            {
                "_id": 1,
                "rule_id": 1,
                "name": 1,
                "alert_type": 1,
                "category": 1,
                "severity": 1,
                "parameter": 1,
                "condition": 1,
                "value": 1,
                "created_at": 1,
                "source_time": 1,
                "is_active": 1,
                "explanation": 1,
            },
        ).sort("created_at", -1).limit(60)
        return [doc async for doc in cursor]

    def _reasoning_cluster_signature(self, alerts: list[dict[str, Any]]) -> str:
        rows = []
        for row in alerts:
            rows.append(
                {
                    "id": str(row.get("_id") or ""),
                    "rule_id": str(row.get("rule_id") or ""),
                    "alert_type": str(row.get("alert_type") or ""),
                    "severity": str(row.get("severity") or ""),
                    "created_at": str(row.get("created_at") or ""),
                }
            )
        return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _reasoning_already_up_to_date(self, alerts: list[dict[str, Any]], cluster_signature: str) -> bool:
        if not alerts:
            return True
        for row in alerts:
            reasoning = row.get("reasoning") if isinstance(row.get("reasoning"), dict) else {}
            if reasoning.get("cluster_signature") != cluster_signature:
                return False
        return True

    def _build_alert_reasoning_payload(
        self,
        *,
        patient_doc: dict[str, Any],
        facts: dict[str, Any],
        active_alerts: list[dict[str, Any]],
        recent_alerts: list[dict[str, Any]],
        context_snapshot: dict[str, Any] | None,
        now: datetime,
        trigger_window_minutes: int,
    ) -> dict[str, Any]:
        nursing_context = facts.get("nursing_context") if isinstance(facts.get("nursing_context"), dict) else {}
        return {
            "task": {
                "name": "alert_reasoning_agent",
                "goal": "对同一患者短时聚集报警进行共同根因归因，并给出优先级和合并展示方案",
                "generated_at": self._local_iso(now),
            },
            "patient": {
                "id": str(patient_doc.get("_id") or ""),
                "name": patient_doc.get("name"),
                "bed": patient_doc.get("hisBed"),
                "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
                "diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "",
                "nursing_level": patient_doc.get("nursingLevel"),
                "icu_admission_time": patient_doc.get("icuAdmissionTime"),
                "allergies": facts.get("allergies") or [],
            },
            "trigger": {
                "window_minutes": trigger_window_minutes,
                "active_alert_count": len(active_alerts),
                "active_alert_ids": [str(row.get("_id") or "") for row in active_alerts],
            },
            "latest_vitals": facts.get("vitals") or {},
            "latest_labs": self._reasoning_pick_labs(facts.get("labs") or {}),
            "nursing_observations": nursing_context.get("records") or [],
            "nursing_plan_execution": nursing_context.get("plans") or {},
            "context_snapshot": context_snapshot or {},
            "active_alerts": [self._serialize_reasoning_alert(row) for row in active_alerts],
            "recent_alert_timeline": [self._serialize_reasoning_alert(row) for row in recent_alerts[:20]],
        }

    def _reasoning_pick_labs(self, labs: dict[str, Any]) -> list[dict[str, Any]]:
        preferred_keys = ["lac", "pct", "cr", "wbc", "plt", "glu", "hb", "bil", "ddimer", "inr"]
        rows: list[dict[str, Any]] = []
        for key in preferred_keys:
            item = labs.get(key)
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if value is None or value == "":
                continue
            rows.append(
                {
                    "key": key,
                    "name": item.get("raw_name") or key,
                    "value": value,
                    "unit": item.get("unit"),
                    "flag": item.get("raw_flag"),
                    "time": item.get("time"),
                }
            )
        return rows

    def _nurse_pid_filters(self, patient_doc: dict[str, Any], patient_id: str) -> list[dict[str, Any]]:
        values = []
        for value in [
            patient_id,
            patient_doc.get("_id"),
            patient_doc.get("hisPid"),
            patient_doc.get("hisPID"),
        ]:
            if value is None:
                continue
            s = str(value).strip()
            if s and s not in values:
                values.append(s)
        clauses: list[dict[str, Any]] = []
        for key in ("pid", "patient_id", "patientId", "hisPid", "hisPID"):
            clauses.append({key: {"$in": values}})
        return clauses

    def _nurse_time(self, doc: dict[str, Any]) -> datetime | None:
        for key in ("time", "recordTime", "created_at", "createTime", "updateTime", "exeTime", "planTime", "startTime", "endTime"):
            value = doc.get(key)
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except Exception:
                    pass
        return None

    def _nurse_text(self, doc: dict[str, Any]) -> str:
        parts: list[str] = []
        for key in (
            "recordContent", "content", "note", "remark", "description", "summary",
            "recordTitle", "title", "itemName", "orderName", "planName", "taskName",
        ):
            value = doc.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text and text not in parts:
                parts.append(text)
        nurse_measure = doc.get("nurseMeasure") if isinstance(doc.get("nurseMeasure"), dict) else {}
        measure_name = str(nurse_measure.get("name") or "").strip()
        measure_freq = str(nurse_measure.get("freq") or "").strip()
        if measure_name and measure_name not in parts:
            parts.append(measure_name if not measure_freq else f"{measure_name} ({measure_freq})")
        return "；".join(parts)[:240]

    async def _collect_nursing_context(self, patient_doc: dict[str, Any], patient_id: str, hours: int = 12) -> dict[str, Any]:
        since = datetime.now() - timedelta(hours=max(hours, 1))
        pid_filters = self._nurse_pid_filters(patient_doc, patient_id)
        if not pid_filters:
            return {"records": [], "plans": {}}

        records: list[dict[str, Any]] = []
        try:
            cursor = self.db.col("nurseRecords").find(
                {
                    "$and": [
                        {"$or": pid_filters},
                        {"$or": [
                            {"time": {"$gte": since}},
                            {"recordTime": {"$gte": since}},
                            {"created_at": {"$gte": since}},
                            {"createTime": {"$gte": since}},
                        ]},
                    ]
                }
            ).sort("time", -1).limit(40)
            async for row in cursor:
                text = self._nurse_text(row)
                if not text:
                    continue
                records.append(
                    {
                        "time": self._nurse_time(row),
                        "text": text,
                    }
                )
        except Exception:
            records = []

        plans: list[dict[str, Any]] = []
        plan_ids: list[Any] = []
        try:
            cursor = self.db.col("nurseOrder").find(
                {"$or": pid_filters}
            ).sort("createTime", -1).limit(60)
            async for row in cursor:
                t = self._nurse_time(row)
                if t and t < since:
                    continue
                text = self._nurse_text(row)
                if not text:
                    continue
                plan_id = row.get("_id")
                if plan_id is not None:
                    plan_ids.append(plan_id)
                plans.append(
                    {
                        "plan_id": str(plan_id) if plan_id is not None else "",
                        "time": t,
                        "text": text,
                        "status": str(row.get("status") or row.get("state") or ""),
                        "frequency": str((((row.get("nurseMeasure") or {}) if isinstance(row.get("nurseMeasure"), dict) else {}).get("freq")) or ""),
                    }
                )
        except Exception:
            plans = []
            plan_ids = []

        executions: list[dict[str, Any]] = []
        try:
            exe_query: dict[str, Any] = {"$or": pid_filters}
            if plan_ids:
                exe_query = {"$or": [exe_query, {"orderId": {"$in": plan_ids}}, {"planId": {"$in": plan_ids}}]}
            cursor = self.db.col("nurseOrderExe").find(exe_query).sort("exeTime", -1).limit(80)
            async for row in cursor:
                t = self._nurse_time(row)
                if t and t < since:
                    continue
                text = self._nurse_text(row)
                executions.append(
                    {
                        "time": t,
                        "plan_start_time": self._nurse_time({"time": row.get("planStartTime")}),
                        "start_time": self._nurse_time({"time": row.get("startTime")}),
                        "text": text,
                        "status": str(row.get("status") or row.get("state") or row.get("result") or ""),
                        "order_id": str(row.get("nurseOrderId") or row.get("orderId") or row.get("planId") or ""),
                    }
                )
        except Exception:
            executions = []

        executed_ids = {
            str(item.get("order_id") or "").strip()
            for item in executions
            if str(item.get("order_id") or "").strip()
        }
        delayed_executions = [
            item for item in executions
            if str(item.get("status") or "").lower() == "ready"
            and isinstance(item.get("plan_start_time"), datetime)
            and item["plan_start_time"] <= datetime.now()
            and not item.get("start_time")
        ]
        pending_plans = [
            item for item in plans
            if item.get("plan_id") and str(item.get("plan_id")) not in executed_ids
        ]
        return {
            "records": records[:10],
            "plans": {
                "planned_count": len(plans),
                "executed_count": len(executions),
                "pending_count": len(pending_plans),
                "delayed_count": len(delayed_executions),
                "recent_plans": plans[:8],
                "recent_executions": executions[:8],
                "delayed_executions": delayed_executions[:8],
            },
        }

    def _serialize_reasoning_alert(self, row: dict[str, Any]) -> dict[str, Any]:
        explanation = row.get("explanation") if isinstance(row.get("explanation"), dict) else {}
        return {
            "alert_id": str(row.get("_id") or ""),
            "rule_id": str(row.get("rule_id") or ""),
            "name": str(row.get("name") or row.get("rule_id") or "预警"),
            "alert_type": str(row.get("alert_type") or ""),
            "category": str(row.get("category") or ""),
            "severity": str(row.get("severity") or ""),
            "parameter": str(row.get("parameter") or ""),
            "value": row.get("value"),
            "condition": row.get("condition") if isinstance(row.get("condition"), dict) else {},
            "is_active": bool(row.get("is_active", True)),
            "created_at": row.get("created_at"),
            "source_time": row.get("source_time"),
            "explanation_summary": str(explanation.get("summary") or row.get("explanation_text") or ""),
        }

    def _compose_alert_reasoning_context(
        self,
        payload: dict[str, Any],
        *,
        rag_hits: list[dict[str, Any]] | None = None,
    ) -> str:
        lines = [
            "任务说明:",
            "当患者在短时间内出现多条活跃报警时，请做共同根因归因，而不是逐条重复解释。",
            "只能依据输入报警、生命体征、检验和RAG指南证据推理；缺失信息必须写“未见证据”。",
            "",
            "结构化输入:",
            json.dumps(payload, ensure_ascii=False, default=str),
        ]
        if rag_hits:
            lines.append("")
            lines.append("相关指南证据(RAG):")
            for idx, item in enumerate(rag_hits[:6], start=1):
                quote = str(item.get("content") or "").strip()
                if len(quote) > 280:
                    quote = quote[:280] + "..."
                lines.append(
                    f"[{idx}] id={item.get('chunk_id') or f'rag_{idx}'} | "
                    f"source={item.get('source') or ''} | recommendation={item.get('recommendation') or ''}"
                )
                if quote:
                    lines.append(quote)
        return "\n".join(lines)

    async def _call_alert_reasoning_analysis(
        self,
        prompt_context: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any] | None:
        system_prompt = """你是一位ICU高年资主治医师AI助手，负责对短时聚集报警做共同根因归因。

要求:
1) 只允许使用输入数据与RAG证据推理，严禁编造未提供的病史、检查或治疗。
2) 输出重点是“这些报警共同由什么驱动”，而不是逐条复述报警定义。
3) 优先级排序要聚焦下一步最紧急 action。
4) 合并展示方案要告诉前端如何把多条报警折叠成一个更有临床意义的摘要卡片。
5) 必须返回严格JSON，不要输出任何额外文本。

JSON结构:
{
  "root_cause_summary": "一句话归因摘要",
  "most_urgent_action": "当前最紧急的处置动作",
  "priority_actions": [
    {"rank": 1, "action": "动作", "why": "原因", "related_alert_ids": ["id1", "id2"]}
  ],
  "alert_ranking": [
    {"alert_id": "id1", "priority": "high|medium|low", "why": "排序原因"}
  ],
  "merge_display_plan": {
    "title": "摘要卡标题",
    "summary": "合并展示摘要",
    "groups": [
      {"label": "主题", "alert_ids": ["id1"], "reason": "为何归为一组"}
    ]
  },
  "confidence": {"overall": 0.0, "level": "high|medium|low"},
  "evidence_sources": [
    {"chunk_id": "xxx", "source": "指南", "recommendation": "要点", "quote": "摘要"}
  ]
}"""

        cfg = self.config
        ai_cfg = cfg.yaml_cfg.get("ai_service", {}) if isinstance(cfg.yaml_cfg, dict) else {}
        llm_cfg = ai_cfg.get("llm", {}) if isinstance(ai_cfg, dict) else {}
        temperature = float(llm_cfg.get("temperature", 0.1) or 0.1)
        max_tokens = min(2200, int(llm_cfg.get("max_tokens", 4096) or 4096))
        model = cfg.llm_model_medical or cfg.settings.LLM_MODEL

        monitor = self._get_ai_monitor() if hasattr(self, "_get_ai_monitor") else None
        start_ms = AiMonitor.now_ms() if monitor else 0.0
        raw_text = ""
        usage = None
        meta: dict[str, Any] = {}

        try:
            timeout_sec = float(llm_cfg.get("timeout", 30) or 30)
            result = await call_llm_chat(
                cfg=cfg,
                system_prompt=system_prompt,
                user_prompt=prompt_context,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_sec,
                client=client,
            )
            raw_text = str(result.get("text") or "")
            usage = result.get("usage")
            model = str(result.get("model") or model)
            meta = result.get("meta") or {}
        except Exception:
            if monitor:
                await monitor.log_llm_call(
                    module="alert_reasoning",
                    model=model,
                    prompt=prompt_context,
                    output=raw_text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=False,
                    meta=meta or {"url": cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"},
                    usage=usage,
                )
            raise

        text = str(raw_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)

        try:
            parsed = json.loads(text)
            if monitor:
                await monitor.log_llm_call(
                    module="alert_reasoning",
                    model=model,
                    prompt=prompt_context,
                    output=text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=True,
                    meta=meta or {"url": cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"},
                    usage=usage,
                )
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            if monitor:
                await monitor.log_llm_call(
                    module="alert_reasoning",
                    model=model,
                    prompt=prompt_context,
                    output=text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=False,
                    meta={**(meta or {"url": cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"}), "error": "json_decode_error"},
                    usage=usage,
                )
            return None

    def _normalize_alert_reasoning_output(
        self,
        raw_result: dict[str, Any],
        *,
        active_alerts: list[dict[str, Any]],
        rag_hits: list[dict[str, Any]],
        cluster_signature: str,
        analysis_source: str,
    ) -> dict[str, Any]:
        result = raw_result if isinstance(raw_result, dict) else {}
        allowed_ids = {str(row.get("_id")) for row in active_alerts if row.get("_id") is not None}
        alert_name_map = {str(row.get("_id")): str(row.get("name") or row.get("rule_id") or "预警") for row in active_alerts}

        root_cause_summary = str(result.get("root_cause_summary") or "").strip()
        if not root_cause_summary:
            top_names = "、".join(list(alert_name_map.values())[:3])
            root_cause_summary = f"{top_names or '这组报警'}提示同一病理生理过程驱动，仍需结合床旁复核。"

        most_urgent_action = str(result.get("most_urgent_action") or "").strip()

        priority_actions: list[dict[str, Any]] = []
        raw_actions = result.get("priority_actions") if isinstance(result.get("priority_actions"), list) else []
        for idx, item in enumerate(raw_actions[:3], start=1):
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "").strip()
            why = str(item.get("why") or "").strip()
            if not action:
                continue
            rel = item.get("related_alert_ids") if isinstance(item.get("related_alert_ids"), list) else []
            related_ids = [str(x) for x in rel if str(x) in allowed_ids][:6]
            priority_actions.append(
                {
                    "rank": idx,
                    "action": action,
                    "why": why,
                    "related_alert_ids": related_ids,
                }
            )
        if not priority_actions and most_urgent_action:
            priority_actions.append(
                {
                    "rank": 1,
                    "action": most_urgent_action,
                    "why": root_cause_summary,
                    "related_alert_ids": list(allowed_ids)[:4],
                }
            )

        alert_ranking: list[dict[str, Any]] = []
        raw_ranking = result.get("alert_ranking") if isinstance(result.get("alert_ranking"), list) else []
        seen_alerts: set[str] = set()
        for item in raw_ranking[:10]:
            if not isinstance(item, dict):
                continue
            alert_id = str(item.get("alert_id") or "")
            if alert_id not in allowed_ids or alert_id in seen_alerts:
                continue
            seen_alerts.add(alert_id)
            priority = str(item.get("priority") or "medium").lower()
            if priority not in {"high", "medium", "low"}:
                priority = "medium"
            alert_ranking.append(
                {
                    "alert_id": alert_id,
                    "alert_name": alert_name_map.get(alert_id) or "预警",
                    "priority": priority,
                    "why": str(item.get("why") or "").strip(),
                }
            )
        if not alert_ranking:
            for row in active_alerts[:6]:
                alert_id = str(row.get("_id") or "")
                sev = str(row.get("severity") or "").lower()
                priority = "high" if sev in {"critical", "high"} else "medium"
                alert_ranking.append(
                    {
                        "alert_id": alert_id,
                        "alert_name": alert_name_map.get(alert_id) or "预警",
                        "priority": priority,
                        "why": str(row.get("alert_type") or row.get("rule_id") or ""),
                    }
                )

        merge_display_plan = result.get("merge_display_plan") if isinstance(result.get("merge_display_plan"), dict) else {}
        raw_groups = merge_display_plan.get("groups") if isinstance(merge_display_plan.get("groups"), list) else []
        groups: list[dict[str, Any]] = []
        for item in raw_groups[:4]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            alert_ids = item.get("alert_ids") if isinstance(item.get("alert_ids"), list) else []
            ids = [str(x) for x in alert_ids if str(x) in allowed_ids][:6]
            groups.append(
                {
                    "label": label,
                    "alert_ids": ids,
                    "reason": str(item.get("reason") or "").strip(),
                }
            )
        if not groups:
            groups.append(
                {
                    "label": "共同根因主题",
                    "alert_ids": list(allowed_ids)[:6],
                    "reason": root_cause_summary,
                }
            )

        confidence = result.get("confidence") if isinstance(result.get("confidence"), dict) else {}
        overall = self._clamp01(confidence.get("overall"), default=0.68)
        level = str(confidence.get("level") or self._confidence_bucket(overall))
        if level not in {"high", "medium", "low"}:
            level = self._confidence_bucket(overall)

        evidence_sources: list[dict[str, Any]] = []
        raw_sources = result.get("evidence_sources") if isinstance(result.get("evidence_sources"), list) else []
        for item in raw_sources[:8]:
            if not isinstance(item, dict):
                continue
            evidence_sources.append(
                {
                    "chunk_id": str(item.get("chunk_id") or item.get("id") or ""),
                    "source": str(item.get("source") or ""),
                    "recommendation": str(item.get("recommendation") or ""),
                    "quote": str(item.get("quote") or item.get("content") or "")[:320],
                }
            )
        if not evidence_sources and rag_hits:
            for item in rag_hits[:4]:
                evidence_sources.append(
                    {
                        "chunk_id": str(item.get("chunk_id") or ""),
                        "source": str(item.get("source") or ""),
                        "recommendation": str(item.get("recommendation") or ""),
                        "quote": str(item.get("content") or "")[:280],
                    }
                )

        return {
            "root_cause_summary": root_cause_summary,
            "most_urgent_action": most_urgent_action or (priority_actions[0]["action"] if priority_actions else ""),
            "priority_actions": priority_actions,
            "alert_ranking": alert_ranking,
            "merge_display_plan": {
                "title": str(merge_display_plan.get("title") or "AI 归因摘要").strip() or "AI 归因摘要",
                "summary": str(merge_display_plan.get("summary") or root_cause_summary).strip() or root_cause_summary,
                "groups": groups,
            },
            "confidence": {
                "overall": round(overall, 2),
                "level": level,
            },
            "evidence_sources": evidence_sources,
            "source_alert_ids": list(allowed_ids),
            "source_alert_count": len(allowed_ids),
            "cluster_signature": cluster_signature,
            "analysis_source": analysis_source,
            "generated_at": datetime.now(API_TZ),
        }

    async def _validate_alert_reasoning_output(self, result: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        blocked_actions: list[str] = []

        allergies = facts.get("allergies") if isinstance(facts.get("allergies"), list) else []
        for item in result.get("priority_actions", []) or []:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "")
            for allergy in allergies:
                allergy_text = str(allergy or "").strip()
                if allergy_text and allergy_text in action:
                    blocked_actions.append(action)
                    issues.append(
                        {
                            "type": "allergy_conflict",
                            "level": "critical",
                            "field": "priority_actions",
                            "message": f"建议动作涉及过敏相关内容: {allergy_text}",
                        }
                    )
                    break

        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        lactate = ((labs.get("lactate") or {}) if isinstance(labs.get("lactate"), dict) else {}).get("value")
        lactate = self._to_float(lactate)
        summary = str(result.get("root_cause_summary") or "")
        if lactate is not None and lactate >= 4 and ("稳定" in summary or "无需紧急处理" in summary):
            issues.append(
                {
                    "type": "clinical_understatement",
                    "level": "high",
                    "field": "root_cause_summary",
                    "message": "乳酸明显升高时，归因摘要不应将病情表述为稳定或无需紧急处理。",
                }
            )

        blocked = any(x.get("level") == "critical" for x in issues)
        status = "blocked" if blocked else ("warning" if issues else "ok")
        return {
            "status": status,
            "blocked": blocked,
            "issues": issues,
            "blocked_actions": blocked_actions,
        }
