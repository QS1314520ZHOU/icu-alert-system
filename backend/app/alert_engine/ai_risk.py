"""AI 综合风险分析"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
from app.services.ai_monitor import AiMonitor
from app.services.rag_service import RagService


class AiRiskMixin:
    def _ensure_ai_runtime_state(self) -> None:
        if not hasattr(self, "_ai_result_cache"):
            self._ai_result_cache: dict[str, dict[str, Any]] = {}
        if not hasattr(self, "_ai_cache_gc_at"):
            self._ai_cache_gc_at = 0.0
        if not hasattr(self, "_rag_service"):
            self._rag_service = None
        if not hasattr(self, "_ai_monitor"):
            self._ai_monitor = None

    def _get_rag_service(self) -> RagService | None:
        self._ensure_ai_runtime_state()
        if self._rag_service is None:
            try:
                self._rag_service = RagService(self.config)
            except Exception:
                self._rag_service = False
        return self._rag_service if isinstance(self._rag_service, RagService) else None

    def _get_ai_monitor(self) -> AiMonitor | None:
        self._ensure_ai_runtime_state()
        if self._ai_monitor is None:
            try:
                self._ai_monitor = AiMonitor(self.db, self.config)
            except Exception:
                self._ai_monitor = False
        return self._ai_monitor if isinstance(self._ai_monitor, AiMonitor) else None

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
            facts = await self._collect_patient_facts(patient_doc, pid)
            patient_summary = await self._build_patient_context(patient_doc, pid, facts=facts)
        except Exception:
            return False

        rag_hits = self._retrieve_guideline_evidence(patient_summary, patient_doc, facts)
        prompt_context = self._compose_prompt_context(patient_summary, rag_hits)
        context_hash = self._context_hash(prompt_context)
        cached_result = self._read_ai_cache(pid_str, context_hash)
        source = "cache"
        result = cached_result
        if not result:
            source = "llm"
            try:
                async with semaphore:
                    result = await self._call_ai_analysis(prompt_context, client=client)
            except Exception:
                return False
            if not result:
                return False
            self._write_ai_cache(pid_str, context_hash, result, cache_ttl_sec)

        result = self._normalize_ai_output(result, rag_hits)
        validation = await self._validate_ai_output(result, facts)
        hallucination_flags = self._detect_hallucinations(result, facts)
        blocked = set(validation.get("blocked_recommendations", []))
        if blocked:
            result["recommendations"] = [x for x in result.get("recommendations", []) if x not in blocked]
        result["safety_validation"] = validation
        result["hallucination_flags"] = hallucination_flags

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
                "primary_risk": result.get("primary_risk"),
                "risk_level": risk_level,
                "organ_assessment": result.get("organ_assessment", {}),
                "syndromes_detected": result.get("syndromes_detected", []),
                "deterioration_signals": result.get("deterioration_signals", []),
                "recommendations": result.get("recommendations", []),
                "evidence_sources": result.get("evidence_sources", []),
                "confidence": result.get("confidence", {}),
                "safety_validation": validation,
                "hallucination_flags": hallucination_flags,
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

    def _confidence_bucket(self, value: Any) -> str:
        num = self._clamp01(value, default=0.5)
        if num >= 0.75:
            return "high"
        if num >= 0.45:
            return "medium"
        return "low"

    async def _collect_patient_facts(self, patient_doc: dict, pid) -> dict[str, Any]:
        his_pid = patient_doc.get("hisPid")
        snapshot = await self._get_latest_param_snapshot_by_pid(
            pid,
            codes=["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_T"],
        )
        if not snapshot:
            monitor_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])
            snapshot = await self._get_latest_device_cap(
                monitor_id,
                codes=["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_T"],
            ) if monitor_id else None

        params = snapshot.get("params", snapshot) if isinstance(snapshot, dict) else {}
        vitals = {
            "hr": self._get_priority_param(params, ["param_HR"]) if params else None,
            "spo2": self._get_priority_param(params, ["param_spo2"]) if params else None,
            "rr": self._get_priority_param(params, ["param_resp"]) if params else None,
            "sbp": self._get_priority_param(params, ["param_nibp_s", "param_ibp_s"]) if params else None,
            "temp": self._get_priority_param(params, ["param_T"]) if params else None,
            "time": snapshot.get("time") if isinstance(snapshot, dict) else None,
        }

        labs = await self._get_latest_labs_map(his_pid, lookback_hours=72) if his_pid else {}
        aki_stage = None
        if his_pid:
            try:
                aki = await self._calc_aki_stage(patient_doc, pid, his_pid)
                aki_stage = int(aki.get("stage")) if isinstance(aki, dict) and aki.get("stage") is not None else None
            except Exception:
                aki_stage = None

        alert_cursor = self.db.col("alert_records").find(
            {
                "patient_id": {"$in": [str(pid), pid]},
                "created_at": {"$gte": datetime.now() - timedelta(hours=24)},
            },
            {"alert_type": 1, "rule_id": 1, "severity": 1, "created_at": 1},
        ).sort("created_at", -1).limit(80)
        active_alerts = [a async for a in alert_cursor]

        return {
            "vitals": vitals,
            "labs": labs,
            "aki_stage": aki_stage,
            "active_alerts": active_alerts,
            "allergies": self._extract_allergies(patient_doc),
            "diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "",
        }

    def _extract_allergies(self, patient_doc: dict) -> list[str]:
        values: list[str] = []

        def _walk(node: Any, key: str = "") -> None:
            if node is None:
                return
            if isinstance(node, dict):
                for k, v in node.items():
                    _walk(v, str(k))
                return
            if isinstance(node, list):
                for item in node:
                    _walk(item, key)
                return
            if not isinstance(node, (str, int, float)):
                return
            s = str(node).strip()
            if not s:
                return
            k = key.lower()
            if any(x in k for x in ["allerg", "过敏"]):
                values.append(s)
            elif any(x in s.lower() for x in ["过敏", "allergy", "allergic"]):
                values.append(s)

        _walk(patient_doc)
        items: list[str] = []
        for text in values:
            for token in re.split(r"[，,；;、/|\s]+", text):
                t = token.strip().strip("。")
                if t and t not in items:
                    items.append(t)
        return items[:20]

    def _retrieve_guideline_evidence(self, patient_summary: str, patient_doc: dict, facts: dict[str, Any]) -> list[dict[str, Any]]:
        rag = self._get_rag_service()
        if rag is None:
            return []
        rag_cfg = self.config.yaml_cfg.get("ai_service", {}).get("rag", {})
        top_k = max(1, int((rag_cfg or {}).get("top_k", 4) or 4))
        tags = self._infer_rag_tags(patient_doc, facts)
        try:
            return rag.search(patient_summary, top_k=top_k, tags=tags or None)
        except Exception:
            return []

    def _infer_rag_tags(self, patient_doc: dict, facts: dict[str, Any]) -> list[str]:
        tags: set[str] = set()
        diag = str(facts.get("diagnosis") or "").lower()
        if any(k in diag for k in ["脓毒", "感染", "sepsis", "休克", "shock"]):
            tags.add("sepsis")
        if any(k in diag for k in ["ards", "急性呼吸窘迫", "低氧", "呼衰"]):
            tags.add("ards")
        if any(k in diag for k in ["肾", "aki", "少尿", "crrt"]):
            tags.add("aki")
        if any(k in diag for k in ["dic", "凝血", "出血"]):
            tags.add("dic")

        for a in facts.get("active_alerts", []) or []:
            t = str(a.get("alert_type") or "").lower()
            if t in {"septic_shock", "qsofa", "sofa"}:
                tags.add("sepsis")
            elif t in {"ards", "aki", "dic"}:
                tags.add(t)
            elif t in {"glucose_variability", "hypoglycemia", "hyperglycemia_no_insulin"}:
                tags.add("glucose")
            elif t in {"delirium_risk", "sedation_delirium_conversion"}:
                tags.add("delirium")

        if isinstance(facts.get("aki_stage"), int) and int(facts.get("aki_stage")) >= 1:
            tags.add("aki")
        return sorted(tags)

    def _compose_prompt_context(self, patient_summary: str, rag_hits: list[dict[str, Any]]) -> str:
        if not rag_hits:
            return patient_summary
        lines = [patient_summary, "", "相关指南证据(检索增强RAG):"]
        for idx, item in enumerate(rag_hits[:6], start=1):
            source = str(item.get("source") or "")
            source_url = str(item.get("source_url") or "")
            rec = str(item.get("recommendation") or "")
            rec_grade = str(item.get("recommendation_grade") or "")
            pkg = str(item.get("package_name") or "")
            pkg_ver = str(item.get("package_version") or "")
            scope = str(item.get("scope") or "")
            cid = str(item.get("chunk_id") or f"rag_{idx}")
            content = str(item.get("content") or "").strip()
            if len(content) > 320:
                content = content[:320] + "..."
            label = f"{source} | {rec}"
            if rec_grade:
                label += f" | grade={rec_grade}"
            if scope:
                label += f" | scope={scope}"
            if pkg or pkg_ver:
                label += f" | {pkg} {pkg_ver}".strip()
            if source_url:
                lines.append(f"[{idx}] id={cid} | {label} | {source_url}")
            else:
                lines.append(f"[{idx}] id={cid} | {label}")
            lines.append(content)
        return "\n".join(lines)

    def _normalize_ai_output(self, raw_result: dict, rag_hits: list[dict[str, Any]]) -> dict[str, Any]:
        result = raw_result if isinstance(raw_result, dict) else {}
        organ = result.get("organ_assessment")
        if not isinstance(organ, dict):
            organ = {}
        normalized_organ: dict[str, dict[str, Any]] = {}
        for key in ["respiratory", "cardiovascular", "renal", "hepatic", "coagulation", "neurological"]:
            item = organ.get(key) if isinstance(organ.get(key), dict) else {}
            status = str(item.get("status") or "normal").lower()
            if status not in {"normal", "impaired", "failure"}:
                status = "impaired"
            conf = self._clamp01(item.get("confidence"), default=0.6 if status == "normal" else 0.75)
            normalized_organ[key] = {
                "status": status,
                "evidence": str(item.get("evidence") or ""),
                "confidence": round(conf, 2),
                "confidence_level": str(item.get("confidence_level") or self._confidence_bucket(conf)),
            }
        result["organ_assessment"] = normalized_organ

        syndromes = result.get("syndromes_detected")
        normalized_syndromes: list[dict[str, Any]] = []
        if isinstance(syndromes, list):
            for s in syndromes[:8]:
                if not isinstance(s, dict):
                    continue
                name = str(s.get("name") or "").strip()
                if not name:
                    continue
                conf = self._clamp01(s.get("confidence"), default=0.65)
                criteria = s.get("criteria_met") if isinstance(s.get("criteria_met"), list) else []
                normalized_syndromes.append(
                    {
                        "name": name,
                        "confidence": round(conf, 2),
                        "confidence_level": str(s.get("confidence_level") or self._confidence_bucket(conf)),
                        "criteria_met": [str(x) for x in criteria[:6]],
                    }
                )
        result["syndromes_detected"] = normalized_syndromes

        det = result.get("deterioration_signals")
        if not isinstance(det, list):
            det = []
        result["deterioration_signals"] = [str(x) for x in det[:8] if str(x).strip()]

        recs = result.get("recommendations")
        if not isinstance(recs, list):
            recs = []
        result["recommendations"] = [str(x).strip() for x in recs[:10] if str(x).strip()]

        level = str(result.get("risk_level") or "medium").lower()
        if level not in {"low", "medium", "high", "critical", "低", "中", "高", "极高"}:
            level = "medium"
        result["risk_level"] = level
        result["primary_risk"] = str(result.get("primary_risk") or "综合风险")[:20]

        explainability = result.get("explainability")
        if not isinstance(explainability, dict):
            explainability = {}
        explain_conf = self._clamp01(explainability.get("confidence"), default=0.66)
        explainability["confidence"] = round(explain_conf, 2)
        explainability["confidence_level"] = str(
            explainability.get("confidence_level") or self._confidence_bucket(explain_conf)
        )
        result["explainability"] = explainability

        evidence_sources = result.get("evidence_sources")
        normalized_sources: list[dict[str, Any]] = []
        if isinstance(evidence_sources, list):
            for item in evidence_sources[:10]:
                if not isinstance(item, dict):
                    continue
                normalized_sources.append(
                    {
                        "chunk_id": str(item.get("chunk_id") or item.get("id") or ""),
                        "doc_id": str(item.get("doc_id") or ""),
                        "section_title": str(item.get("section_title") or ""),
                        "source": str(item.get("source") or ""),
                        "source_url": str(item.get("source_url") or item.get("url") or ""),
                        "recommendation": str(item.get("recommendation") or ""),
                        "recommendation_grade": str(item.get("recommendation_grade") or item.get("grade") or ""),
                        "scope": str(item.get("scope") or ""),
                        "topic": str(item.get("topic") or ""),
                        "priority": item.get("priority"),
                        "updated_at": str(item.get("updated_at") or ""),
                        "local_ref": str(item.get("local_ref") or ""),
                        "package_name": str(item.get("package_name") or ""),
                        "package_version": str(item.get("package_version") or ""),
                        "quote": str(item.get("quote") or item.get("content") or "")[:360],
                    }
                )
        if not normalized_sources and rag_hits:
            for item in rag_hits[:5]:
                normalized_sources.append(
                    {
                        "chunk_id": str(item.get("chunk_id") or ""),
                        "doc_id": str(item.get("doc_id") or ""),
                        "section_title": str(item.get("section_title") or ""),
                        "source": str(item.get("source") or ""),
                        "source_url": str(item.get("source_url") or ""),
                        "recommendation": str(item.get("recommendation") or ""),
                        "recommendation_grade": str(item.get("recommendation_grade") or ""),
                        "scope": str(item.get("scope") or ""),
                        "topic": str(item.get("topic") or ""),
                        "priority": item.get("priority"),
                        "updated_at": str(item.get("updated_at") or ""),
                        "local_ref": str(item.get("local_ref") or ""),
                        "package_name": str(item.get("package_name") or ""),
                        "package_version": str(item.get("package_version") or ""),
                        "quote": str(item.get("content") or "")[:320],
                    }
                )
        result["evidence_sources"] = normalized_sources
        result["confidence"] = {
            "overall": self._confidence_bucket(explain_conf),
            "overall_score": round(explain_conf, 2),
        }
        return result

    async def _validate_ai_output(self, result: dict, facts: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        blocked_recommendations: list[str] = []

        organ = result.get("organ_assessment") if isinstance(result.get("organ_assessment"), dict) else {}
        renal_status = str(((organ.get("renal") or {}).get("status") or "")).lower()
        aki_stage = facts.get("aki_stage")
        if renal_status == "normal" and isinstance(aki_stage, int) and aki_stage >= 2:
            issues.append(
                {
                    "type": "clinical_contradiction",
                    "level": "high",
                    "field": "organ_assessment.renal.status",
                    "message": f"AI判定肾功能正常，但KDIGO提示AKI {aki_stage}期。",
                }
            )

        cardio_status = str(((organ.get("cardiovascular") or {}).get("status") or "")).lower()
        active_alerts = facts.get("active_alerts") if isinstance(facts.get("active_alerts"), list) else []
        if cardio_status == "normal" and any(str(a.get("alert_type") or "") == "septic_shock" for a in active_alerts):
            issues.append(
                {
                    "type": "clinical_contradiction",
                    "level": "high",
                    "field": "organ_assessment.cardiovascular.status",
                    "message": "AI判定循环功能正常，但近期已触发脓毒性休克相关预警。",
                }
            )

        allergies = facts.get("allergies") if isinstance(facts.get("allergies"), list) else []
        recs = result.get("recommendations") if isinstance(result.get("recommendations"), list) else []
        for rec in recs:
            text = str(rec)
            for al in allergies:
                al_text = str(al).strip()
                if al_text and al_text in text:
                    blocked_recommendations.append(text)
                    issues.append(
                        {
                            "type": "allergy_conflict",
                            "level": "critical",
                            "field": "recommendations",
                            "message": f"推荐项涉及过敏相关内容: {al_text}",
                        }
                    )
                    break

        blocked = any(x.get("level") == "critical" for x in issues)
        status = "blocked" if blocked else ("warning" if issues else "ok")
        return {
            "status": status,
            "blocked": blocked,
            "issues": issues,
            "blocked_recommendations": blocked_recommendations,
        }

    def _detect_hallucinations(self, result: dict, facts: dict[str, Any]) -> list[dict[str, Any]]:
        text = json.dumps(result, ensure_ascii=False)
        metric_defs = self._build_metric_catalog(facts)
        flags: list[dict[str, Any]] = []
        for item in metric_defs:
            expected = item.get("expected")
            if expected is None:
                continue
            claims = self._extract_metric_values(text, item.get("keywords", []))
            if not claims:
                continue
            tol = float(item.get("tolerance", 0.0) or 0.0)
            for claim in claims[:4]:
                delta = abs(float(claim) - float(expected))
                if delta > tol:
                    flags.append(
                        {
                            "metric": item.get("name"),
                            "claimed": round(float(claim), 3),
                            "observed": round(float(expected), 3),
                            "delta": round(float(delta), 3),
                            "tolerance": tol,
                            "level": "warning" if delta <= (tol * 2.0) else "high",
                            "message": f"{item.get('name')} 可能存在幻觉: 输出{claim}, 实测{expected}",
                        }
                    )

        uniq: list[dict[str, Any]] = []
        seen: set[str] = set()
        for f in flags:
            key = f"{f.get('metric')}|{f.get('claimed')}|{f.get('observed')}"
            if key in seen:
                continue
            seen.add(key)
            uniq.append(f)
        return uniq[:10]

    def _build_metric_catalog(self, facts: dict[str, Any]) -> list[dict[str, Any]]:
        vitals = facts.get("vitals") if isinstance(facts.get("vitals"), dict) else {}
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}

        def _lab(k: str) -> float | None:
            v = labs.get(k)
            return self._to_float(v.get("value")) if isinstance(v, dict) else None

        return [
            {"name": "HR", "keywords": ["hr", "心率"], "expected": self._to_float(vitals.get("hr")), "tolerance": 8},
            {"name": "SpO2", "keywords": ["spo2", "血氧", "氧饱和度"], "expected": self._to_float(vitals.get("spo2")), "tolerance": 3},
            {"name": "RR", "keywords": ["rr", "呼吸频率", "呼吸"], "expected": self._to_float(vitals.get("rr")), "tolerance": 4},
            {"name": "SBP", "keywords": ["sbp", "收缩压", "血压"], "expected": self._to_float(vitals.get("sbp")), "tolerance": 12},
            {"name": "Temp", "keywords": ["体温", "temp", "温度"], "expected": self._to_float(vitals.get("temp")), "tolerance": 0.6},
            {"name": "Potassium", "keywords": ["血钾", "钾", "k+", "potassium"], "expected": _lab("k"), "tolerance": 0.6},
            {"name": "Lactate", "keywords": ["乳酸", "lactate", "lac"], "expected": _lab("lactate"), "tolerance": 0.8},
            {"name": "Creatinine", "keywords": ["肌酐", "creatinine", "cr"], "expected": _lab("cr"), "tolerance": 35},
            {"name": "Glucose", "keywords": ["血糖", "glucose", "glu"], "expected": _lab("glu"), "tolerance": 1.8},
            {"name": "Platelet", "keywords": ["血小板", "plt", "platelet"], "expected": _lab("plt"), "tolerance": 30},
        ]

    def _extract_metric_values(self, text: str, keywords: list[str]) -> list[float]:
        if not text or not keywords:
            return []
        safe_kw = [re.escape(k) for k in keywords if k]
        if not safe_kw:
            return []
        group = "(?:" + "|".join(safe_kw) + ")"
        patterns = [
            re.compile(rf"{group}[^0-9\-]{{0,10}}(-?\d+(?:\.\d+)?)", re.IGNORECASE),
            re.compile(rf"(-?\d+(?:\.\d+)?)[^0-9\n]{{0,8}}{group}", re.IGNORECASE),
        ]
        values: list[float] = []
        for pat in patterns:
            for m in pat.finditer(text):
                num = self._to_float(m.group(1))
                if num is not None:
                    values.append(num)
        return values

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
                    "confidence_level": str(
                        source.get("confidence_level")
                        or self._confidence_bucket(self._clamp01(source.get("confidence"), default=0.7))
                    ),
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
            "confidence_level": "medium",
            "top_factors": factors[:6],
            "notes": "基于LLM输出字段进行结构化提取，非模型内部注意力权重。",
        }

    async def _build_patient_context(self, patient: dict, pid, facts: dict[str, Any] | None = None) -> str:
        if facts is None:
            facts = await self._collect_patient_facts(patient, pid)
        name = patient.get("name", "未知")
        diag = patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "未知"
        nursing = patient.get("nursingLevel", "未知")
        icu_time = patient.get("icuAdmissionTime", "未知")
        vitals_data = facts.get("vitals") if isinstance(facts.get("vitals"), dict) else {}
        vitals = [{
            "time": str(vitals_data.get("time") or "?"),
            "HR": vitals_data.get("hr"),
            "SpO2": vitals_data.get("spo2"),
            "RR": vitals_data.get("rr"),
            "SBP": vitals_data.get("sbp"),
            "T": vitals_data.get("temp"),
        }]
        labs_text = ""
        labs_map = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        labs = []
        for key, doc in list(labs_map.items())[:10]:
            if not isinstance(doc, dict):
                continue
            labs.append({
                "name": doc.get("raw_name") or key,
                "result": doc.get("value"),
                "unit": doc.get("unit", ""),
                "flag": doc.get("raw_flag") or "",
            })
        if labs:
            labs_text = f"\n近期检验(最新10项): {json.dumps(labs, ensure_ascii=False)}"

        alerts = facts.get("active_alerts") if isinstance(facts.get("active_alerts"), list) else []
        alert_summary = [str(a.get("alert_type") or a.get("rule_id") or "") for a in alerts[:8]]

        vitals_text = json.dumps(vitals, ensure_ascii=False)
        return (
            f"患者: {name}\n"
            f"诊断: {diag}\n"
            f"护理级别: {nursing}\n"
            f"ICU入科: {icu_time}\n"
            f"近期活跃预警: {', '.join(alert_summary) if alert_summary else '无'}\n"
            f"最近生命体征(从新到旧): {vitals_text}"
            f"{labs_text}"
        )

    async def _call_ai_analysis(
        self,
        patient_context: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict | None:
        system_prompt = """你是一位ICU高年资主治医师AI助手。基于提供的患者数据和指南证据做结构化评估，不得编造。

要求:
1) 仅允许使用输入数据与RAG证据推理，缺失信息请明确写“未见证据”。
2) 每个器官判断要包含 confidence(0-1) 与 confidence_level(high|medium|low)。
3) 每个综合征判断要包含 confidence 与 confidence_level。
4) 推荐项尽量关联 evidence_sources。
5) 必须返回严格JSON（不要任何额外文本）。

JSON结构:
{
  "organ_assessment": {
    "respiratory": {"status": "normal|impaired|failure", "evidence": "...", "confidence": 0.0-1.0, "confidence_level": "high|medium|low"},
    "cardiovascular": {"status": "normal|impaired|failure", "evidence": "...", "confidence": 0.0-1.0, "confidence_level": "high|medium|low"},
    "renal": {"status": "normal|impaired|failure", "evidence": "...", "confidence": 0.0-1.0, "confidence_level": "high|medium|low"},
    "hepatic": {"status": "normal|impaired|failure", "evidence": "...", "confidence": 0.0-1.0, "confidence_level": "high|medium|low"},
    "coagulation": {"status": "normal|impaired|failure", "evidence": "...", "confidence": 0.0-1.0, "confidence_level": "high|medium|low"},
    "neurological": {"status": "normal|impaired|failure", "evidence": "...", "confidence": 0.0-1.0, "confidence_level": "high|medium|low"}
  },
  "syndromes_detected": [
    {"name": "脓毒性休克", "confidence": 0.0-1.0, "confidence_level": "high|medium|low", "criteria_met": ["..."]}
  ],
  "deterioration_signals": ["..."],
  "risk_level": "low|medium|high|critical",
  "primary_risk": "最主要风险(10字以内)",
  "recommendations": ["建议1", "建议2"],
  "evidence_sources": [
    {"chunk_id": "ssc2021_1h_bundle", "source": "SSC 2021", "recommendation": "1h Bundle", "quote": "原文摘要"}
  ],
  "explainability": {
    "confidence": 0.0-1.0,
    "confidence_level": "high|medium|low",
    "top_factors": [
      {"factor": "关键风险因素", "direction": "up|down", "weight": 0.0-1.0, "evidence": "证据"}
    ],
    "notes": "解释说明"
  }
}"""

        cfg = self.config
        ai_cfg = cfg.yaml_cfg.get("ai_service", {}) if isinstance(cfg.yaml_cfg, dict) else {}
        llm_cfg = ai_cfg.get("llm", {}) if isinstance(ai_cfg, dict) else {}
        temperature = float(llm_cfg.get("temperature", 0.1) or 0.1)
        max_tokens = int(llm_cfg.get("max_tokens", 1024) or 1024)
        url = cfg.settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
        model = cfg.settings.LLM_MODEL_MEDICAL or cfg.settings.LLM_MODEL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.settings.LLM_API_KEY}",
        }
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": patient_context},
            ],
        }

        monitor = self._get_ai_monitor()
        start_ms = AiMonitor.now_ms() if monitor else 0.0
        raw_text = ""
        usage = None

        async def _do_request(request_client: httpx.AsyncClient) -> tuple[str, dict | None]:
            resp = await request_client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"], (data.get("usage") if isinstance(data, dict) else None)

        try:
            if client is None:
                timeout_sec = float(llm_cfg.get("timeout", 30) or 30)
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as local_client:
                    raw_text, usage = await _do_request(local_client)
            else:
                raw_text, usage = await _do_request(client)
        except Exception:
            if monitor:
                await monitor.log_llm_call(
                    module="ai_risk",
                    model=model,
                    prompt=patient_context,
                    output=raw_text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=False,
                    meta={"url": url},
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
                    module="ai_risk",
                    model=model,
                    prompt=patient_context,
                    output=text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=True,
                    meta={"url": url},
                    usage=usage,
                )
            return parsed
        except json.JSONDecodeError:
            if monitor:
                await monitor.log_llm_call(
                    module="ai_risk",
                    model=model,
                    prompt=patient_context,
                    output=text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=False,
                    meta={"url": url, "error": "json_decode_error"},
                    usage=usage,
                )
            return None
