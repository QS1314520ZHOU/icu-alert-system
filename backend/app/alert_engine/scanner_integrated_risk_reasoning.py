from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.services.llm_runtime import call_llm_chat
from app.services.rag_service import RagService

from .scanners import BaseScanner, ScannerSpec


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).strip())
    if not match:
        return None
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None


def _parse_json_block(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    raw = re.sub(r"^\s*```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```\s*$", "", raw, flags=re.IGNORECASE)
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _severity_rank(value: str) -> int:
    return {"warning": 1, "high": 2, "critical": 3}.get(str(value or "").lower(), 0)


class IntegratedRiskReasoningScanner(BaseScanner):
    """多告警聚合的 ICU 综合风险推理报告扫描器。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="integrated_risk_reasoning",
                interval_key="integrated_risk_reasoning",
                default_interval=3600,
                initial_delay=98,
            ),
        )
        self._rag_service: RagService | None = None

    def is_enabled(self) -> bool:
        return super().is_enabled() and bool(self._cfg().get("enabled", True))

    def interval_seconds(self) -> int:
        value = self._cfg().get("scan_interval")
        try:
            return max(300, int(value))
        except (TypeError, ValueError):
            return super().interval_seconds()

    def _cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "integrated_risk_reasoning", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        patients = await self._target_patients(patient_id)
        if not patients:
            return []
        now = datetime.now()
        reports: list[dict[str, Any]] = []
        for patient_doc in patients:
            report = await self._scan_patient(patient_doc=patient_doc, now=now)
            if report:
                reports.append(report)
        if reports:
            self.engine._log_info("综合风险推理", len(reports))
        return reports

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        projection = {
            "_id": 1,
            "name": 1,
            "hisPid": 1,
            "hisBed": 1,
            "dept": 1,
            "hisDept": 1,
            "clinicalDiagnosis": 1,
            "admissionDiagnosis": 1,
            "gender": 1,
            "hisSex": 1,
            "age": 1,
            "hisAge": 1,
            "icuAdmissionTime": 1,
            "current_profile": 1,
        }
        if patient_id:
            patient_doc, _ = await self.engine._load_patient(patient_id)
            return [patient_doc] if isinstance(patient_doc, dict) else []
        cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), projection)
        return [row async for row in cursor]

    async def _scan_patient(self, *, patient_doc: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        patient_id = patient_doc.get("_id")
        if not patient_id:
            return None
        patient_id_str = str(patient_id)
        cfg = self._cfg()
        lookback_seconds = int(cfg.get("lookback_window", 7200) or 7200)
        cooldown_seconds = int(cfg.get("cooldown", 7200) or 7200)
        active_alerts = await self._active_alerts(patient_id_str, now, lookback_seconds)
        if not active_alerts:
            return None

        grouped_alerts = self._group_alerts(active_alerts)
        density = self._alert_density(active_alerts, now, lookback_seconds)
        cluster_signature = self._cluster_signature(active_alerts)
        latest_report = await self.engine.db.col("integrated_risk_reports").find_one(
            {"patient_id": patient_id_str},
            sort=[("created_at", -1)],
        )
        if not self._should_trigger(latest_report=latest_report, alerts=active_alerts, now=now, cooldown_seconds=cooldown_seconds, force_trigger_on_new_critical=bool(cfg.get("force_trigger_on_new_critical", True)), cluster_signature=cluster_signature):
            return None

        facts = await self._collect_facts(patient_doc, patient_id)
        rag_hits = self._retrieve_rag_hits(patient_doc=patient_doc, grouped_alerts=grouped_alerts, facts=facts, top_k=max(1, int(cfg.get("rag_top_k", 5) or 5)))
        prompt_context = self._build_prompt_context(
            patient_doc=patient_doc,
            grouped_alerts=grouped_alerts,
            density=density,
            facts=facts,
            rag_hits=rag_hits,
        )
        llm_output = await self._call_reasoning_llm(prompt_context=prompt_context)
        report_payload = self._normalize_report(
            llm_output=llm_output,
            patient_doc=patient_doc,
            grouped_alerts=grouped_alerts,
            density=density,
            facts=facts,
            rag_hits=rag_hits,
        )
        risk_level = self._risk_level_from_actions(report_payload.get("top3_actions") if isinstance(report_payload.get("top3_actions"), list) else [])
        report_doc = await self._persist_report(
            patient_doc=patient_doc,
            report_payload=report_payload,
            active_alerts=active_alerts,
            grouped_alerts=grouped_alerts,
            density=density,
            rag_hits=rag_hits,
            cluster_signature=cluster_signature,
            risk_level=risk_level,
            now=now,
        )
        await self._broadcast_report(report_doc)
        await self.engine._create_alert(
            rule_id="INTEGRATED_RISK_REASONING",
            name="综合风险推理报告",
            category="ai_analysis",
            alert_type="integrated_risk_reasoning",
            severity=risk_level,
            parameter="integrated_risk",
            condition={"active_alert_count": len(active_alerts), "cluster_signature": cluster_signature},
            value=len(active_alerts),
            patient_id=patient_id_str,
            patient_doc=patient_doc,
            device_id=None,
            source_time=now,
            explanation={
                "summary": str(report_payload.get("summary") or "").strip(),
                "evidence": [f"{system}: {row.get('count')}条" for system, row in grouped_alerts.items()][:5],
                "suggestion": "；".join(str(item.get("action") or "").strip() for item in (report_payload.get("top3_actions") or [])[:3]),
                "text": "",
            },
            extra={"detail": report_doc},
        )
        return report_doc

    async def _active_alerts(self, patient_id: str, now: datetime, lookback_seconds: int) -> list[dict[str, Any]]:
        since = now - timedelta(seconds=max(lookback_seconds, 300))
        cursor = self.engine.db.col("alert_records").find(
            {
                "patient_id": patient_id,
                "is_active": True,
                "created_at": {"$gte": since},
                "alert_type": {"$nin": ["ai_risk", "integrated_risk_reasoning"]},
            },
            {
                "_id": 1,
                "rule_id": 1,
                "name": 1,
                "category": 1,
                "alert_type": 1,
                "severity": 1,
                "parameter": 1,
                "condition": 1,
                "value": 1,
                "created_at": 1,
                "source_time": 1,
                "extra": 1,
                "explanation": 1,
            },
        ).sort("created_at", -1).limit(80)
        return [row async for row in cursor]

    def _group_alerts(self, alerts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for alert in alerts:
            system_name = self._system_group(alert)
            bucket = groups.setdefault(
                system_name,
                {"count": 0, "highest_severity": "warning", "alerts": []},
            )
            bucket["count"] += 1
            if _severity_rank(str(alert.get("severity") or "")) > _severity_rank(str(bucket.get("highest_severity") or "")):
                bucket["highest_severity"] = str(alert.get("severity") or "warning")
            bucket["alerts"].append(
                {
                    "alert_id": str(alert.get("_id") or ""),
                    "alert_type": str(alert.get("alert_type") or ""),
                    "level": str(alert.get("severity") or ""),
                    "title": str(alert.get("name") or alert.get("rule_id") or "预警"),
                    "detail": (alert.get("extra") or {}) if isinstance(alert.get("extra"), dict) else {},
                    "timestamp": alert.get("created_at"),
                }
            )
        return groups

    def _system_group(self, alert: dict[str, Any]) -> str:
        text = " ".join(
            str(alert.get(key) or "").lower()
            for key in ("category", "alert_type", "parameter", "name", "rule_id")
        )
        mapping = [
            ("循环", ["shock", "map", "hemodynamic", "hypotension", "cardiac", "fluid_responsiveness", "心动过速", "低血压"]),
            ("呼吸", ["ards", "vent", "spo2", "oxygen", "呼吸", "weaning", "asynchrony"]),
            ("肾脏", ["aki", "cr", "creatinine", "urine", "renal", "肾"]),
            ("血液/凝血", ["dic", "coag", "plt", "inr", "bleeding", "出血", "凝血"]),
            ("神经", ["tbi", "delirium", "gcs", "icp", "cpp", "neuro", "谵妄", "瞳孔"]),
            ("感染", ["sepsis", "infection", "qsofa", "septic", "microbiology", "感染", "脓毒"]),
            ("代谢/营养", ["glucose", "glycemic", "lactate", "nutrition", "fluid_balance", "metabolic", "营养", "血糖", "乳酸"]),
        ]
        for label, keywords in mapping:
            if any(keyword in text for keyword in keywords):
                return label
        return "其他"

    def _alert_density(self, alerts: list[dict[str, Any]], now: datetime, lookback_seconds: int) -> dict[str, Any]:
        midpoint = now - timedelta(seconds=max(lookback_seconds, 300) / 2.0)
        early = [row for row in alerts if isinstance(row.get("created_at"), datetime) and row["created_at"] < midpoint]
        late = [row for row in alerts if isinstance(row.get("created_at"), datetime) and row["created_at"] >= midpoint]
        accelerating = len(late) >= len(early) + 2 if alerts else False
        return {
            "total_alerts": len(alerts),
            "critical_count": len([row for row in alerts if str(row.get("severity") or "") == "critical"]),
            "high_count": len([row for row in alerts if str(row.get("severity") or "") == "high"]),
            "highest_severity": max((str(row.get("severity") or "warning") for row in alerts), key=_severity_rank),
            "early_half_count": len(early),
            "late_half_count": len(late),
            "accelerating": accelerating,
        }

    def _cluster_signature(self, alerts: list[dict[str, Any]]) -> str:
        rows = [
            {
                "id": str(row.get("_id") or ""),
                "severity": str(row.get("severity") or ""),
                "created_at": str(row.get("created_at") or ""),
            }
            for row in alerts
        ]
        return json.dumps(rows, ensure_ascii=False, sort_keys=True)

    def _should_trigger(self, *, latest_report: dict[str, Any] | None, alerts: list[dict[str, Any]], now: datetime, cooldown_seconds: int, force_trigger_on_new_critical: bool, cluster_signature: str) -> bool:
        if latest_report is None:
            return True
        created_at = latest_report.get("created_at")
        if not isinstance(created_at, datetime):
            return True
        if created_at <= now - timedelta(seconds=max(cooldown_seconds, 300)):
            return True
        previous_ids = set(str(item) for item in (latest_report.get("source_alert_ids") or []) if str(item).strip())
        new_high = 0
        new_critical = 0
        for row in alerts:
            alert_id = str(row.get("_id") or "")
            if alert_id in previous_ids:
                continue
            sev = str(row.get("severity") or "")
            if sev == "critical":
                new_critical += 1
            if sev in {"high", "critical"}:
                new_high += 1
        if force_trigger_on_new_critical and new_critical >= 1:
            return True
        if new_high >= 2:
            return True
        return str(latest_report.get("cluster_signature") or "") != cluster_signature and new_critical >= 1

    async def _collect_facts(self, patient_doc: dict[str, Any], patient_id: Any) -> dict[str, Any]:
        facts = await self.engine._collect_patient_facts(patient_doc, patient_id) if hasattr(self.engine, "_collect_patient_facts") else {}
        facts = facts if isinstance(facts, dict) else {}
        facts["vital_trends_6h"] = await self._vital_trends(patient_id)
        facts["current_treatment"] = await self._current_treatment(patient_doc, patient_id)
        facts["subphenotype"] = await self._subphenotype(patient_doc)
        return facts

    async def _vital_trends(self, patient_id: Any) -> dict[str, Any]:
        since = datetime.now() - timedelta(hours=6)
        metrics = {
            "HR": "param_HR",
            "MAP": "param_ibp_m",
            "SpO2": "param_spo2",
            "RR": "param_resp",
            "Temp": "param_T",
        }
        trends: dict[str, Any] = {}
        for label, code in metrics.items():
            series = await self.engine._get_param_series_by_pid(patient_id, code, since, prefer_device_types=["monitor"], limit=240)
            if not series and label == "MAP":
                series = await self.engine._get_param_series_by_pid(patient_id, "param_nibp_m", since, prefer_device_types=["monitor"], limit=240)
            values = [_to_float(item.get("value")) for item in series]
            values = [float(item) for item in values if item is not None]
            if not values:
                trends[label] = {"latest": None, "delta": None}
                continue
            trends[label] = {
                "latest": round(values[-1], 2),
                "delta": round(values[-1] - values[0], 2) if len(values) >= 2 else 0.0,
                "points": len(values),
            }
        return trends

    async def _current_treatment(self, patient_doc: dict[str, Any], patient_id: Any) -> dict[str, Any]:
        treatments: dict[str, Any] = {}
        treatments["vasopressors"] = await self.engine._get_current_vasopressor_snapshot(patient_id, patient_doc, hours=8, max_items=4) if hasattr(self.engine, "_get_current_vasopressor_snapshot") else []
        active_bind = await self.engine._get_active_vent_bind(str(patient_id)) if hasattr(self.engine, "_get_active_vent_bind") else None
        if active_bind:
            cap = await self.engine._get_latest_device_cap(active_bind.get("deviceID"))
            treatments["ventilator"] = {
                "mode": str(self.engine._vent_param(cap or {}, "vent_mode", "param_HuXiMoShi") or ""),
                "fio2": self.engine._vent_param(cap or {}, "fio2", "param_FiO2"),
                "peep": self.engine._vent_param_priority(cap or {}, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"]),
                "rr": self.engine._vent_param_priority(cap or {}, ["rr_measured", "rr_set"], ["param_vent_resp", "param_HuXiPinLv"]),
            }
        else:
            treatments["ventilator"] = None
        crrt_bind = await self.engine._get_device_id_for_patient(patient_doc, ["crrt"]) if hasattr(self.engine, "_get_device_id_for_patient") else None
        treatments["crrt"] = bool(crrt_bind)
        antibiotic_names = []
        if hasattr(self.engine, "_load_antibiotic_dictionary"):
            try:
                abx_names, _ = await self.engine._load_antibiotic_dictionary()
                docs = await self.engine._get_recent_drug_docs_window(patient_id, hours=24, limit=400)
                for doc in docs:
                    name = str(doc.get("drugName") or doc.get("orderName") or "")
                    if self.engine._match_name_keywords(name, abx_names):
                        if name and name not in antibiotic_names:
                            antibiotic_names.append(name)
                treatments["antibiotics"] = antibiotic_names[:8]
            except Exception:
                treatments["antibiotics"] = []
        return treatments

    async def _subphenotype(self, patient_doc: dict[str, Any]) -> dict[str, Any] | None:
        current_profile = (patient_doc.get("current_profile") or {}) if isinstance(patient_doc.get("current_profile"), dict) else {}
        sub = current_profile.get("sepsis_subphenotype") if isinstance(current_profile.get("sepsis_subphenotype"), dict) else None
        if sub:
            return sub
        patient_id = str(patient_doc.get("_id") or "")
        if not patient_id:
            return None
        return await self.engine.db.col("score").find_one(
            {"patient_id": patient_id, "score_type": {"$in": ["sepsis_subphenotype_profile", "clinical_subphenotype_profile"]}},
            sort=[("calc_time", -1)],
        )

    def _retrieve_rag_hits(self, *, patient_doc: dict[str, Any], grouped_alerts: dict[str, dict[str, Any]], facts: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
        rag = None
        if hasattr(self.engine, "_get_rag_service"):
            rag = self.engine._get_rag_service()
        if rag is None:
            try:
                if self._rag_service is None:
                    self._rag_service = RagService(self.engine.config)
                rag = self._rag_service
            except Exception:
                rag = None
        if rag is None:
            return []
        query_parts = [
            str(patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or ""),
            " ".join(grouped_alerts.keys()),
            " ".join(alert.get("title") for group in grouped_alerts.values() for alert in (group.get("alerts") or [])[:3]),
        ]
        query = " ".join(part for part in query_parts if part).strip()
        if not query:
            return []
        try:
            return rag.search(query, top_k=top_k)
        except Exception:
            return []

    def _build_prompt_context(self, *, patient_doc: dict[str, Any], grouped_alerts: dict[str, dict[str, Any]], density: dict[str, Any], facts: dict[str, Any], rag_hits: list[dict[str, Any]]) -> str:
        age = patient_doc.get("age") or patient_doc.get("hisAge") or "?"
        gender = patient_doc.get("gender") or patient_doc.get("hisSex") or "?"
        admission_time = patient_doc.get("icuAdmissionTime")
        icu_day = "?"
        if isinstance(admission_time, datetime):
            icu_day = max(1, int((datetime.now() - admission_time).total_seconds() // 86400) + 1)
        alert_lines = []
        for system_name, row in grouped_alerts.items():
            alert_lines.append(f"[{system_name}] {row.get('count')}条 | 最高级别 {row.get('highest_severity')}")
            for alert in (row.get("alerts") or [])[:8]:
                alert_lines.append(
                    f"- {alert.get('alert_type')} | {alert.get('level')} | {alert.get('title')} | {json.dumps(alert.get('detail') or {}, ensure_ascii=False, default=str)}"
                )
        rag_lines = []
        for item in rag_hits[:5]:
            rag_lines.append(f"- {item.get('source')} | {item.get('recommendation')} | {str(item.get('content') or '')[:240]}")
        return (
            f"患者 ID: {patient_doc.get('_id')}\n"
            f"基本信息: {age}岁 {gender} | 入ICU第{icu_day}天 | 主诊断: {patient_doc.get('clinicalDiagnosis') or patient_doc.get('admissionDiagnosis') or '未知'}\n\n"
            f"== 当前活跃告警 ({density.get('total_alerts')}条) ==\n" + "\n".join(alert_lines) + "\n\n"
            f"== 告警态势 ==\n{json.dumps(density, ensure_ascii=False, default=str)}\n\n"
            f"== 关键生命体征趋势(6h) ==\n{json.dumps(facts.get('vital_trends_6h') or {}, ensure_ascii=False, default=str)}\n\n"
            f"== 关键检验结果 ==\n{json.dumps((facts.get('labs') or {}), ensure_ascii=False, default=str)}\n\n"
            f"== 当前治疗 ==\n{json.dumps(facts.get('current_treatment') or {}, ensure_ascii=False, default=str)}\n\n"
            f"== 亚表型（如有） ==\n{json.dumps(facts.get('subphenotype'), ensure_ascii=False, default=str)}\n\n"
            f"== RAG 参考 ==\n" + "\n".join(rag_lines)
        )

    async def _call_reasoning_llm(self, *, prompt_context: str) -> dict[str, Any] | None:
        cfg = self._cfg()
        system_prompt = (
            "你是一名经验丰富的 ICU 主治医师 AI 助手。"
            "你将收到一位 ICU 患者的多维度告警汇总。"
            "请用严格 JSON 输出，字段必须包含 summary, causal_chain, deterioration_forecast, top3_actions, differential_diagnosis。"
            "top3_actions 每条必须包含 priority, action, rationale, urgency。"
        )
        result = await self._safe_llm_call(
            call_llm_chat(
                cfg=self.engine.config,
                system_prompt=system_prompt,
                user_prompt=prompt_context,
                model=str(cfg.get("llm_model") or "").strip() or None,
                temperature=0.1,
                max_tokens=int(cfg.get("max_tokens", 2000) or 2000),
                timeout_seconds=float(self.engine._cfg("ai_service", "llm", "timeout", default=60) or 60),
            ),
            fallback=None,
        )
        if not isinstance(result, dict):
            return None
        return _parse_json_block(str(result.get("text") or ""))

    def _normalize_report(self, *, llm_output: dict[str, Any] | None, patient_doc: dict[str, Any], grouped_alerts: dict[str, dict[str, Any]], density: dict[str, Any], facts: dict[str, Any], rag_hits: list[dict[str, Any]]) -> dict[str, Any]:
        if isinstance(llm_output, dict):
            actions = llm_output.get("top3_actions") if isinstance(llm_output.get("top3_actions"), list) else []
            normalized_actions = []
            for idx, item in enumerate(actions[:3], start=1):
                if not isinstance(item, dict):
                    continue
                normalized_actions.append(
                    {
                        "priority": len(normalized_actions) + 1,
                        "action": str(item.get("action") or "").strip(),
                        "rationale": str(item.get("rationale") or "").strip(),
                        "urgency": int(_to_float(item.get("urgency")) or 180),
                    }
                )
            if normalized_actions:
                for fallback in self._fallback_actions(grouped_alerts, density, facts):
                    if len(normalized_actions) >= 3:
                        break
                    action_text = str(fallback.get("action") or "").strip()
                    if not action_text or any(str(item.get("action") or "").strip() == action_text for item in normalized_actions):
                        continue
                    normalized_actions.append({**fallback, "priority": len(normalized_actions) + 1})
                return {
                    "summary": str(llm_output.get("summary") or "").strip(),
                    "causal_chain": str(llm_output.get("causal_chain") or "").strip(),
                    "deterioration_forecast": str(llm_output.get("deterioration_forecast") or "").strip(),
                    "top3_actions": normalized_actions,
                    "differential_diagnosis": [str(item).strip() for item in (llm_output.get("differential_diagnosis") or []) if str(item).strip()][:6],
                    "analysis_source": "llm",
                }
        actions = self._fallback_actions(grouped_alerts, density, facts)
        systems = "、".join(grouped_alerts.keys())
        return {
            "summary": f"当前患者在 {systems or '多系统'} 同时存在活跃告警，最高级别为 {density.get('highest_severity')}，且告警密度{'呈加速' if density.get('accelerating') else '未明显加速'}。",
            "causal_chain": "感染/循环/呼吸等多系统风险可能相互放大，需把分散告警按共同病理生理过程整合处理。",
            "deterioration_forecast": "未来 4-12 小时最需警惕循环灌注进一步恶化、呼吸支持升级或器官功能持续失代偿。",
            "top3_actions": actions,
            "differential_diagnosis": ["需排除容量不足或隐匿失血", "需排除持续感染灶未控制", "需排除呼吸支持不足或肺保护失败"],
            "analysis_source": "heuristic_fallback",
        }

    def _fallback_actions(self, grouped_alerts: dict[str, dict[str, Any]], density: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if density.get("critical_count", 0) > 0 or "循环" in grouped_alerts:
            actions.append({"priority": 1, "action": "立即复核循环灌注与血流动力学支持", "rationale": "当前存在高等级循环相关风险或 critical 告警。", "urgency": 20})
        if "呼吸" in grouped_alerts:
            actions.append({"priority": 2, "action": "立即复核氧合、通气与呼吸支持参数", "rationale": "呼吸系统相关告警活跃，需防止短时内呼吸失代偿。", "urgency": 45})
        actions.append({"priority": 3, "action": "按器官系统重新排序处置优先级并完成关键复查", "rationale": "多条分散告警需整合成统一的 ICU 行动清单。", "urgency": 90})
        return actions[:3]

    def _risk_level_from_actions(self, actions: list[dict[str, Any]]) -> str:
        urgency = min((int(_to_float(item.get("urgency")) or 180) for item in actions), default=180)
        if urgency < 30:
            return "critical"
        if urgency <= 120:
            return "high"
        return "warning"

    async def _persist_report(self, *, patient_doc: dict[str, Any], report_payload: dict[str, Any], active_alerts: list[dict[str, Any]], grouped_alerts: dict[str, dict[str, Any]], density: dict[str, Any], rag_hits: list[dict[str, Any]], cluster_signature: str, risk_level: str, now: datetime) -> dict[str, Any]:
        patient_id_str = str(patient_doc.get("_id") or "")
        report_doc = {
            "patient_id": patient_id_str,
            "patient_name": patient_doc.get("name") or "",
            "bed": patient_doc.get("hisBed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
            "risk_level": risk_level,
            "summary": report_payload.get("summary"),
            "causal_chain": report_payload.get("causal_chain"),
            "deterioration_forecast": report_payload.get("deterioration_forecast"),
            "top3_actions": report_payload.get("top3_actions") or [],
            "differential_diagnosis": report_payload.get("differential_diagnosis") or [],
            "analysis_source": report_payload.get("analysis_source"),
            "grouped_alerts": grouped_alerts,
            "density": density,
            "source_alert_ids": [str(row.get("_id") or "") for row in active_alerts],
            "cluster_signature": cluster_signature,
            "rag_hits": [
                {
                    "chunk_id": item.get("chunk_id"),
                    "source": item.get("source"),
                    "recommendation": item.get("recommendation"),
                    "content": str(item.get("content") or "")[:280],
                }
                for item in rag_hits[:5]
            ],
            "created_at": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        result = await self.engine.db.col("integrated_risk_reports").insert_one(report_doc)
        report_doc["_id"] = result.inserted_id
        await self.engine.db.col("patient").update_one(
            {"_id": patient_doc.get("_id")},
            {
                "$set": {
                    "current_profile.integrated_risk": {
                        "risk_level": risk_level,
                        "summary": report_payload.get("summary"),
                        "top3_actions": report_payload.get("top3_actions") or [],
                        "updated_at": now,
                        "report_id": result.inserted_id,
                    }
                }
            },
        )
        return report_doc

    async def _broadcast_report(self, report_doc: dict[str, Any]) -> None:
        ws = getattr(self.engine, "ws", None)
        if ws:
            await ws.broadcast({"type": "integrated_risk_report", "data": report_doc})
