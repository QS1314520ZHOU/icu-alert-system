"""LLM 驱动的个性化报警阈值推荐。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
from app.services.llm_runtime import call_llm_chat
from .scanner_adaptive_thresholds import AdaptiveThresholdsScanner

logger = logging.getLogger("icu-alert")


POPULATION_DEFAULTS: dict[str, dict[str, float | None]] = {
    "map": {"low_critical": 55, "low_warning": 65, "high_warning": 110, "high_critical": 130},
    "hr": {"low_critical": 40, "low_warning": 50, "high_warning": 120, "high_critical": 150},
    "spo2": {"low_critical": 85, "low_warning": 90, "high_warning": None, "high_critical": None},
    "sbp": {"low_critical": 70, "low_warning": 90, "high_warning": 180, "high_critical": 200},
    "rr": {"low_critical": 6, "low_warning": 10, "high_warning": 30, "high_critical": 40},
    "temperature": {"low_critical": 34.0, "low_warning": 35.5, "high_warning": 38.5, "high_critical": 39.5},
}


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
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


class AdaptiveThresholdAdvisorMixin:
    def _threshold_advisor_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "adaptive_threshold_advisor", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _ensure_threshold_advisor_state(self) -> None:
        if not hasattr(self, "_threshold_advisor_cache"):
            self._threshold_advisor_cache: dict[str, dict[str, Any]] = {}
        if not hasattr(self, "_threshold_advisor_cache_gc_at"):
            self._threshold_advisor_cache_gc_at = 0.0

    def _threshold_cache_key(self, patient_id: str, context_hash: str) -> str:
        return f"{patient_id}:{context_hash}"

    def _threshold_context_hash(self, payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _read_threshold_cache(self, patient_id: str, context_hash: str) -> dict[str, Any] | None:
        self._ensure_threshold_advisor_state()
        cache_key = self._threshold_cache_key(patient_id, context_hash)
        cached = self._threshold_advisor_cache.get(cache_key)
        if not cached:
            return None
        if float(cached.get("expire_at") or 0) < time.time():
            self._threshold_advisor_cache.pop(cache_key, None)
            return None
        result = cached.get("result")
        return result if isinstance(result, dict) else None

    def _write_threshold_cache(self, patient_id: str, context_hash: str, result: dict[str, Any], cache_ttl_sec: int) -> None:
        self._ensure_threshold_advisor_state()
        self._threshold_advisor_cache[self._threshold_cache_key(patient_id, context_hash)] = {
            "result": result,
            "expire_at": time.time() + max(cache_ttl_sec, 60),
        }

    def _gc_threshold_cache(self, cache_ttl_sec: int) -> None:
        self._ensure_threshold_advisor_state()
        now_ts = time.time()
        if now_ts - float(self._threshold_advisor_cache_gc_at or 0.0) < min(max(cache_ttl_sec, 60), 300):
            return
        self._threshold_advisor_cache_gc_at = now_ts
        expired = [k for k, v in self._threshold_advisor_cache.items() if float(v.get("expire_at") or 0) < now_ts]
        for key in expired:
            self._threshold_advisor_cache.pop(key, None)

    def _threshold_patient_age_value(self, patient_doc: dict | None) -> float | None:
        raw = (patient_doc or {}).get("age")
        if isinstance(raw, (int, float)):
            return float(raw)
        match = re.search(r"\d+(?:\.\d+)?", str(raw or ""))
        return float(match.group(0)) if match else None

    def _threshold_patient_sex_text(self, patient_doc: dict | None) -> str:
        return str((patient_doc or {}).get("gender") or (patient_doc or {}).get("hisSex") or "").strip()

    def _threshold_diagnosis_text(self, patient_doc: dict | None) -> str:
        return "；".join(
            str((patient_doc or {}).get(key) or "").strip()
            for key in ("clinicalDiagnosis", "admissionDiagnosis", "diagnosis", "remark")
            if str((patient_doc or {}).get(key) or "").strip()
        )

    def _threshold_days_in_icu(self, patient_doc: dict | None, now: datetime) -> float | None:
        for key in ("icuAdmissionTime", "admissionTime", "admitTime", "inTime", "createTime"):
            t = _parse_dt((patient_doc or {}).get(key))
            if t:
                return round(max((now - t).total_seconds(), 0.0) / 86400.0, 2)
        return None

    def _threshold_param_code_map(self) -> dict[str, list[str]]:
        return {
            "hr": [str(self._cfg("vital_signs", "heart_rate", "code", default="param_HR") or "param_HR")],
            "map": [str(x) for x in (self._cfg("vital_signs", "map_priority", default=["param_ibp_m", "param_nibp_m"]) or ["param_ibp_m", "param_nibp_m"])],
            "sbp": [str(x) for x in (self._cfg("vital_signs", "sbp_priority", default=["param_ibp_s", "param_nibp_s"]) or ["param_ibp_s", "param_nibp_s"])],
            "spo2": [str(self._cfg("vital_signs", "spo2", "code", default="param_spo2") or "param_spo2")],
            "rr": [str(self._cfg("vital_signs", "resp_rate", "code", default="param_resp") or "param_resp")],
            "temperature": [str(self._cfg("vital_signs", "temperature", "code", default="param_T") or "param_T")],
        }

    def _threshold_compute_stats(self, series: list[dict], min_points: int) -> dict[str, Any] | None:
        values = [float(item["value"]) for item in series if _to_float(item.get("value")) is not None]
        if len(values) < max(min_points, 5):
            return None
        arr = np.asarray(values, dtype=float)
        return {
            "mean": round(float(np.mean(arr)), 2),
            "std": round(float(np.std(arr)), 2),
            "min": round(float(np.min(arr)), 2),
            "max": round(float(np.max(arr)), 2),
            "p5": round(float(np.percentile(arr, 5)), 2),
            "p25": round(float(np.percentile(arr, 25)), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p75": round(float(np.percentile(arr, 75)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "count": int(arr.size),
        }

    async def _threshold_get_param_distribution(self, pid, param_name: str, codes: list[str], since: datetime, min_points: int) -> dict[str, Any] | None:
        chosen_code = None
        chosen_series: list[dict] = []
        for code in codes:
            series = await self._get_param_series_by_pid(pid, code, since, prefer_device_types=["monitor"], limit=4000)
            if len(series) > len(chosen_series):
                chosen_series = series
                chosen_code = code
            if len(series) >= min_points:
                chosen_series = series
                chosen_code = code
                break
        stats = self._threshold_compute_stats(chosen_series, min_points)
        if not stats:
            return None
        return {
            "code": chosen_code,
            "stats": stats,
            "latest": round(float(chosen_series[-1]["value"]), 2) if chosen_series else None,
            "start_time": chosen_series[0]["time"] if chosen_series else None,
            "end_time": chosen_series[-1]["time"] if chosen_series else None,
        }

    async def _threshold_recent_active_alerts(self, pid_str: str, hours: int = 24) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(hours=max(hours, 1))
        cursor = self.db.col("alert_records").find(
            {"patient_id": pid_str, "created_at": {"$gte": since}, "is_active": True},
            {"rule_id": 1, "name": 1, "alert_type": 1, "severity": 1, "parameter": 1, "created_at": 1},
        ).sort("created_at", -1).limit(20)
        rows: list[dict[str, Any]] = []
        async for doc in cursor:
            rows.append(
                {
                    "rule_id": str(doc.get("rule_id") or ""),
                    "name": str(doc.get("name") or ""),
                    "alert_type": str(doc.get("alert_type") or ""),
                    "severity": str(doc.get("severity") or ""),
                    "parameter": str(doc.get("parameter") or ""),
                    "time": doc.get("created_at"),
                }
            )
        return rows

    def _threshold_match_any_text(self, text: str, keywords: list[str]) -> bool:
        lowered = str(text or "").lower()
        return any(str(keyword).strip().lower() in lowered for keyword in keywords if str(keyword).strip())

    def _threshold_drugexe_names(self, doc: dict) -> list[str]:
        names: list[str] = []
        for item in doc.get("drugList") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        return names

    def _threshold_latest_action_speed_safe(self, doc: dict) -> tuple[float | None, datetime | None]:
        helper = getattr(self, "_latest_action_speed", None)
        if callable(helper):
            try:
                return helper(doc)
            except Exception:
                pass
        valid: list[tuple[datetime, float]] = []
        positive: list[tuple[datetime, float]] = []
        for item in doc.get("drugActionList") or []:
            if not isinstance(item, dict):
                continue
            speed = _to_float(item.get("speed"))
            if speed is None:
                speed = _to_float(item.get("dripSpeed"))
            if speed is None:
                speed = _to_float(item.get("rate"))
            t = _parse_dt(item.get("time"))
            if speed is None or t is None:
                continue
            valid.append((t, speed))
            if speed > 0:
                positive.append((t, speed))
        if positive:
            positive.sort(key=lambda x: x[0])
            return positive[-1][1], positive[-1][0]
        if not valid:
            return None, None
        valid.sort(key=lambda x: x[0])
        return valid[-1][1], valid[-1][0]

    async def _threshold_collect_drug_context(self, pid, hours: int = 72) -> dict[str, list[dict[str, Any]]]:
        cfg = self._threshold_advisor_cfg()
        vasopressor_keywords = cfg.get("vasopressor_keywords") or []
        sedation_keywords = cfg.get("sedation_keywords") or []
        docs = await self._get_recent_drugexe_docs(pid, hours=hours, limit=800)
        latest_vasopressors: dict[str, dict[str, Any]] = {}
        latest_sedatives: dict[str, dict[str, Any]] = {}

        for doc in docs:
            names = self._threshold_drugexe_names(doc)
            if not names:
                continue
            speed, speed_time = self._threshold_latest_action_speed_safe(doc)
            event_time = speed_time or _parse_dt(doc.get("_event_time")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            for name in names:
                entry = {
                    "name": name,
                    "rate": speed,
                    "rate_time": speed_time,
                    "event_time": event_time,
                }
                if isinstance(vasopressor_keywords, list) and self._threshold_match_any_text(name, vasopressor_keywords):
                    current = latest_vasopressors.get(name)
                    if not current or (event_time or datetime.min) >= (current.get("event_time") or datetime.min):
                        latest_vasopressors[name] = entry
                if isinstance(sedation_keywords, list) and self._threshold_match_any_text(name, sedation_keywords):
                    current = latest_sedatives.get(name)
                    if not current or (event_time or datetime.min) >= (current.get("event_time") or datetime.min):
                        latest_sedatives[name] = entry

        def _serialize(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
            rows = list(items.values())
            rows.sort(key=lambda x: x.get("event_time") or datetime.min, reverse=True)
            return [
                {
                    "name": row.get("name"),
                    "rate": row.get("rate"),
                    "rate_time": row.get("rate_time"),
                    "event_time": row.get("event_time"),
                }
                for row in rows
            ]

        return {
            "vasopressors": _serialize(latest_vasopressors),
            "sedation_analgesia": _serialize(latest_sedatives),
        }

    def _threshold_simplify_labs(self, labs_map: dict[str, Any]) -> dict[str, Any]:
        important = ["lac", "cr", "pao2", "pco2", "hb", "plt", "bil", "albumin", "pct"]
        out: dict[str, Any] = {}
        for key in important:
            item = labs_map.get(key)
            if not isinstance(item, dict):
                continue
            out[key] = {
                "value": item.get("value"),
                "unit": item.get("unit"),
                "time": item.get("time"),
            }
        return out

    async def _build_threshold_patient_context(self, patient_doc: dict, now: datetime, lookback_hours: int, min_points: int) -> dict[str, Any] | None:
        pid = patient_doc.get("_id")
        pid_str = self._pid_str(pid)
        if not pid_str:
            return None
        since = now - timedelta(hours=max(lookback_hours, 24))
        distributions: dict[str, Any] = {}
        for param_name, codes in self._threshold_param_code_map().items():
            item = await self._threshold_get_param_distribution(pid, param_name, codes, since, min_points)
            if item:
                distributions[param_name] = item
        if len(distributions) < 2:
            return None

        his_pid = str(patient_doc.get("hisPid") or "").strip() or None
        labs_map = await self._get_latest_labs_map(his_pid, lookback_hours=max(lookback_hours, 72)) if his_pid else {}
        drugs = await self._threshold_collect_drug_context(pid, hours=max(lookback_hours, 72))
        active_alerts = await self._threshold_recent_active_alerts(pid_str, hours=24)

        return {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "age": self._threshold_patient_age_value(patient_doc),
            "sex": self._threshold_patient_sex_text(patient_doc),
            "diagnosis": self._threshold_diagnosis_text(patient_doc),
            "icu_days": self._threshold_days_in_icu(patient_doc, now),
            "vital_distributions": distributions,
            "current_vasopressors": drugs.get("vasopressors") or [],
            "current_sedation_analgesia": drugs.get("sedation_analgesia") or [],
            "recent_active_alerts": active_alerts,
            "latest_labs": self._threshold_simplify_labs(labs_map if isinstance(labs_map, dict) else {}),
            "population_defaults": POPULATION_DEFAULTS,
        }

    def _build_threshold_system_prompt(self) -> str:
        return (
            "你是一名 ICU 高年资主治医师兼临床监护专家。\n"
            "你的任务是根据患者过去 24-72 小时生命体征分布、诊断背景、年龄、当前血管活性药物和镇静/镇痛药物状态，"
            "推荐比群体阈值更精确的个性化报警阈值。\n"
            "推荐必须偏保守方向，宁可略微多报也不能漏报关键恶化信号。\n"
            "请逐项给出 MAP、HR、SpO2、SBP、RR、Temperature 的 low_critical、low_warning、high_warning、high_critical 和 reasoning。\n"
            "如果某参数不适合设置某个方向的阈值，可以返回 null。\n"
            "输出必须是严格 JSON，不要输出 markdown，不要输出额外说明。"
        )

    def _build_threshold_user_prompt(self, context: dict[str, Any]) -> str:
        return (
            "请基于以下患者资料生成个性化报警阈值建议。\n"
            "要求：\n"
            "1. 参考系统默认阈值，但允许因患者基础状态和用药背景做保守微调。\n"
            "2. 每个阈值都要给出简短临床依据。\n"
            "3. review_priority 只能是 low / medium / high。\n"
            "4. confidence 取 0 到 1 之间。\n"
            "5. 输出 JSON 结构必须包含 thresholds、confidence、overall_reasoning、review_priority。\n\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2, default=str)}"
        )

    async def _call_threshold_advisor_llm(self, system_prompt: str, user_prompt: str, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
        cfg = self._threshold_advisor_cfg()

        async def _run(http_client: httpx.AsyncClient) -> dict[str, Any] | None:
            result = await call_llm_chat(
                cfg=self.config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=self.config.llm_model_medical or self.config.settings.LLM_MODEL,
                temperature=float(cfg.get("llm_temperature", cfg.get("temperature", 0.1))),
                max_tokens=int(cfg.get("llm_max_tokens", cfg.get("max_tokens", 2048))),
                timeout_seconds=float(cfg.get("llm_timeout", cfg.get("timeout", 45))),
                client=http_client,
            )
            text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            text = re.sub(r"^\s*```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
            text = re.sub(r"\s*```\s*$", "", text, flags=re.IGNORECASE)
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", text)
                if not match:
                    return None
                try:
                    parsed = json.loads(match.group(0))
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None

        if client is not None:
            return await _run(client)

        timeout = httpx.Timeout(float(cfg.get("llm_timeout", cfg.get("timeout", 45)) or 45))
        async with httpx.AsyncClient(timeout=timeout) as local_client:
            return await _run(local_client)

    def _threshold_normalize_priority(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"low", "medium", "high"}:
            return text
        if text in {"urgent", "critical"}:
            return "high"
        return "medium"

    def _threshold_clip_threshold_value(self, param_name: str, key: str, value: Any, bounds_cfg: dict[str, Any]) -> tuple[float | None, bool]:
        numeric = _to_float(value)
        if numeric is None:
            return None, False
        param_bounds = bounds_cfg.get(param_name) if isinstance(bounds_cfg.get(param_name), dict) else {}
        clipped = False
        result = float(numeric)
        if key.startswith("low_"):
            lower = _to_float(param_bounds.get("low_min"))
            upper = _to_float(param_bounds.get("low_max"))
        else:
            lower = _to_float(param_bounds.get("high_min"))
            upper = _to_float(param_bounds.get("high_max"))
        if lower is not None and result < lower:
            result = lower
            clipped = True
        if upper is not None and result > upper:
            result = upper
            clipped = True
        return round(result, 2), clipped

    def _threshold_logical_thresholds_valid(self, payload: dict[str, Any]) -> bool:
        low_critical = payload.get("low_critical")
        low_warning = payload.get("low_warning")
        high_warning = payload.get("high_warning")
        high_critical = payload.get("high_critical")
        if low_critical is not None and low_warning is not None and not (float(low_critical) < float(low_warning)):
            return False
        if high_warning is not None and high_critical is not None and not (float(high_warning) < float(high_critical)):
            return False
        if low_warning is not None and high_warning is not None and not (float(low_warning) < float(high_warning)):
            return False
        if low_critical is not None and high_warning is not None and not (float(low_critical) < float(high_warning)):
            return False
        if low_warning is not None and high_critical is not None and not (float(low_warning) < float(high_critical)):
            return False
        return True

    def _threshold_sanitize_threshold_response(self, result: dict[str, Any]) -> dict[str, Any]:
        cfg = self._threshold_advisor_cfg()
        bounds_cfg = cfg.get("bounds") if isinstance(cfg.get("bounds"), dict) else {}
        thresholds_raw = result.get("thresholds") if isinstance(result.get("thresholds"), dict) else {}
        thresholds: dict[str, Any] = {}
        rejected: dict[str, Any] = {}

        for param_name in POPULATION_DEFAULTS:
            item = thresholds_raw.get(param_name)
            if not isinstance(item, dict):
                continue
            reasoning = str(item.get("reasoning") or "").strip()
            clipped_any = False
            normalized = {"reasoning": reasoning}
            for key in ("low_critical", "low_warning", "high_warning", "high_critical"):
                clipped_value, clipped = self._threshold_clip_threshold_value(param_name, key, item.get(key), bounds_cfg)
                normalized[key] = clipped_value
                clipped_any = clipped_any or clipped
            if clipped_any:
                suffix = "[已被系统约束到安全范围]"
                normalized["reasoning"] = f"{normalized['reasoning']} {suffix}".strip()
            if not self._threshold_logical_thresholds_valid(normalized):
                rejected[param_name] = {
                    "reasoning": normalized.get("reasoning") or "",
                    "invalid": True,
                    "reason": "logic_inconsistent",
                }
                continue
            thresholds[param_name] = normalized

        confidence = _to_float(result.get("confidence"))
        if confidence is None:
            confidence = 0.5
        confidence = max(0.0, min(float(confidence), 1.0))
        return {
            "thresholds": thresholds,
            "rejected_thresholds": rejected,
            "confidence": round(confidence, 3),
            "overall_reasoning": str(result.get("overall_reasoning") or "").strip(),
            "review_priority": self._threshold_normalize_priority(result.get("review_priority")),
        }

    async def _threshold_has_existing_record(self, pid_str: str, context_hash: str) -> bool:
        doc = await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "personalized_thresholds",
                "context_hash": context_hash,
            },
            {"_id": 1},
            sort=[("calc_time", -1)],
        )
        return bool(doc)

    async def _threshold_persist_personalized_thresholds(
        self,
        patient_doc: dict,
        payload: dict[str, Any],
        patient_context: dict[str, Any],
        context_hash: str,
        now: datetime,
    ) -> None:
        pid_str = self._pid_str(patient_doc.get("_id"))
        await self.db.col("score_records").insert_one(
            {
                "patient_id": pid_str,
                "patient_name": patient_doc.get("name"),
                "bed": patient_doc.get("hisBed"),
                "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
                "score_type": "personalized_thresholds",
                "status": "pending_review",
                "thresholds": payload.get("thresholds") or {},
                "reasoning": {
                    "overall_reasoning": payload.get("overall_reasoning"),
                    "confidence": payload.get("confidence"),
                    "review_priority": payload.get("review_priority"),
                    "rejected_thresholds": payload.get("rejected_thresholds") or {},
                },
                "patient_context": patient_context,
                "context_hash": context_hash,
                "calc_time": now,
                "created_at": now,
                "updated_at": now,
                "month": now.strftime("%Y-%m"),
                "day": now.strftime("%Y-%m-%d"),
            }
        )

    async def get_approved_thresholds(self, pid_str: str) -> dict | None:
        doc = await self.db.col("score_records").find_one(
            {"patient_id": pid_str, "score_type": "personalized_thresholds", "status": "approved"},
            sort=[("calc_time", -1)],
        )
        if not doc:
            return None
        thresholds = doc.get("thresholds")
        return thresholds if isinstance(thresholds, dict) else None

    async def _scan_single_patient_adaptive_thresholds(
        self,
        *,
        patient_doc: dict,
        now: datetime,
        semaphore: asyncio.Semaphore,
        cache_ttl_sec: int,
        same_rule_sec: int,
        max_per_hour: int,
        client: httpx.AsyncClient,
    ) -> bool:
        pid = patient_doc.get("_id")
        if not pid:
            return False
        pid_str = self._pid_str(pid)
        if not pid_str:
            return False

        cfg = self._threshold_advisor_cfg()
        context = await self._build_threshold_patient_context(
            patient_doc,
            now,
            int(cfg.get("stats_lookback_hours", 48)),
            int(cfg.get("min_data_points", 20)),
        )
        if not context:
            return False

        context_summary = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
        context_hash = self._threshold_context_hash(context_summary)
        if await self._threshold_has_existing_record(pid_str, context_hash):
            return False

        result = self._read_threshold_cache(pid_str, context_hash)
        if result is None:
            system_prompt = self._build_threshold_system_prompt()
            user_prompt = self._build_threshold_user_prompt(context)
            try:
                async with semaphore:
                    result = await self._call_threshold_advisor_llm(system_prompt, user_prompt, client=client)
            except Exception:
                logger.exception("adaptive threshold advisor llm failed for patient %s", pid_str)
                return False
            if not result:
                return False
            self._write_threshold_cache(pid_str, context_hash, result, cache_ttl_sec)

        sanitized = self._threshold_sanitize_threshold_response(result)
        if not sanitized.get("thresholds"):
            return False

        await self._threshold_persist_personalized_thresholds(patient_doc, sanitized, context, context_hash, now)

        if await self._is_suppressed(pid_str, "ADAPTIVE_THRESHOLD_SUGGESTION", same_rule_sec, max_per_hour):
            return True

        device_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])
        explanation = await self._polish_structured_alert_explanation(
            {
                "summary": "LLM 已生成个性化报警阈值建议，当前仅供医生审核，不会自动生效。",
                "evidence": [
                    f"覆盖参数: {', '.join(sorted(sanitized.get('thresholds', {}).keys()))}",
                    f"置信度: {sanitized.get('confidence')}",
                    f"审核优先级: {sanitized.get('review_priority')}",
                ],
                "suggestion": "请结合患者基础疾病、当前灌注状态和用药背景审核是否采用。",
                "text": sanitized.get("overall_reasoning") or "",
            }
        )
        alert = await self._create_alert(
            rule_id="ADAPTIVE_THRESHOLD_SUGGESTION",
            name="个性化报警阈值建议",
            category="ai_analysis",
            alert_type="threshold_advisor",
            severity="info",
            parameter="multi_parameter",
            condition={
                "context_hash": context_hash,
                "review_priority": sanitized.get("review_priority"),
                "confidence": sanitized.get("confidence"),
                "status": "pending_review",
            },
            value=None,
            patient_id=pid_str,
            patient_doc=patient_doc,
            device_id=device_id,
            source_time=now,
            explanation=explanation,
            extra={
                "thresholds": sanitized.get("thresholds") or {},
                "rejected_thresholds": sanitized.get("rejected_thresholds") or {},
                "confidence": sanitized.get("confidence"),
                "overall_reasoning": sanitized.get("overall_reasoning"),
                "review_priority": sanitized.get("review_priority"),
                "status": "pending_review",
                "context_hash": context_hash,
            },
        )
        return bool(alert)

    async def scan_adaptive_thresholds(self) -> None:
        await AdaptiveThresholdsScanner(self).scan()

