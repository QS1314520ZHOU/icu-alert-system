"""历史相似病例结局回溯。"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from typing import Any

from app.services.ai_monitor import AiMonitor
from app.services.llm_runtime import call_llm_chat

logger = logging.getLogger("icu-alert")


class SimilarCaseReviewMixin:
    def _similar_case_cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("similar_case_review", {})
        return cfg if isinstance(cfg, dict) else {}

    def _similar_case_age_years(self, patient_doc: dict) -> float | None:
        parser = getattr(self, "_parse_age_years", None)
        if callable(parser):
            try:
                val = parser(patient_doc)
                if val is not None:
                    return float(val)
            except Exception:
                pass
        for key in ("age", "hisAge"):
            raw = patient_doc.get(key)
            if raw is None:
                continue
            try:
                return float(raw)
            except Exception:
                pass
            s = str(raw).strip()
            if not s:
                continue
            m = re.search(r"(\d+(?:\.\d+)?)", s)
            if not m:
                continue
            val = float(m.group(1))
            if "天" in s:
                return round(val / 365.0, 2)
            if "月" in s:
                return round(val / 12.0, 2)
            return val
        return None

    def _similar_case_diag_text(self, patient_doc: dict) -> str:
        return " ".join(
            str(patient_doc.get(k) or "")
            for k in (
                "clinicalDiagnosis",
                "admissionDiagnosis",
                "diagnosis",
                "diagnosisHistory",
                "history",
                "surgeryHistory",
            )
        ).strip()

    def _similar_case_diag_tokens(self, text: str) -> list[str]:
        blob = str(text or "").lower()
        if not blob:
            return []
        raw_tokens = re.findall(r"[\u4e00-\u9fff]{2,12}|[a-z0-9\-\+]{2,24}", blob)
        stopwords = {
            "患者", "入院", "术后", "待查", "重症", "监护", "收住", "伴", "并", "及", "icu",
            "the", "with", "and", "postop", "post", "status",
        }
        tokens: list[str] = []
        seen: set[str] = set()
        for token in raw_tokens:
            t = token.strip().lower()
            if len(t) < 2 or t in stopwords:
                continue
            if t in seen:
                continue
            seen.add(t)
            tokens.append(t)
        return tokens[:16]

    def _similar_case_diag_similarity(self, base_tokens: list[str], candidate_tokens: list[str]) -> float:
        if not base_tokens or not candidate_tokens:
            return 0.0
        a = set(base_tokens)
        b = set(candidate_tokens)
        inter = len(a & b)
        if inter <= 0:
            return 0.0
        return round(inter / max(len(a | b), 1), 3)

    def _similar_case_discharged_query(self) -> dict[str, Any]:
        return {
            "$or": [
                {"status": {"$in": ["discharged", "dead", "death", "deceased", "auto_discharged", "auto_discharge"]}},
                {"dischargeTime": {"$exists": True}},
                {"outTime": {"$exists": True}},
                {"leaveTime": {"$exists": True}},
                {"deathTime": {"$exists": True}},
            ]
        }

    def _patient_end_time(self, patient_doc: dict) -> datetime | None:
        for key in ("dischargeTime", "outTime", "leaveTime", "deathTime", "updatedAt", "updateTime"):
            val = patient_doc.get(key)
            if isinstance(val, datetime):
                return val
        return None

    def _patient_outcome_label(self, patient_doc: dict) -> str:
        text = " ".join(
            str(patient_doc.get(k) or "")
            for k in ("status", "outcome", "leaveType", "dischargeType", "dischargeDisposition", "remark", "deathReason")
        ).lower()
        if any(k in text for k in ["死亡", "death", "dead", "deceased", "抢救无效"]):
            return "死亡"
        if any(k in text for k in ["自动出院", "自行出院", "auto discharge", "against medical advice", "放弃治疗"]):
            return "自动出院"
        if any(k in text for k in ["好转", "转出", "转科", "出院", "home", "improved", "stable"]):
            return "好转出科"
        return "已出院"

    def _safe_days(self, start: datetime | None, end: datetime | None) -> float | None:
        if not isinstance(start, datetime) or not isinstance(end, datetime) or end < start:
            return None
        return round((end - start).total_seconds() / 86400.0, 2)

    def _support_summary_from_binds(self, rows: list[dict], stay_end: datetime | None) -> dict[str, Any]:
        summary = {
            "vent_used": False,
            "vent_days": 0.0,
            "crrt_used": False,
            "crrt_days": 0.0,
        }
        for row in rows:
            bind_time = row.get("bindTime") if isinstance(row.get("bindTime"), datetime) else None
            unbind_time = row.get("unBindTime") if isinstance(row.get("unBindTime"), datetime) else None
            end_time = unbind_time or stay_end or bind_time
            duration = self._safe_days(bind_time, end_time) or 0.0
            dtype = str(row.get("type") or "").lower()
            device_name = str(row.get("deviceName") or row.get("name") or "").lower()
            if dtype == "vent" or "呼吸机" in device_name or "vent" in device_name:
                summary["vent_used"] = True
                summary["vent_days"] = round(summary["vent_days"] + duration, 2)
            if dtype == "crrt" or "crrt" in device_name or "血滤" in device_name or "血液净化" in device_name:
                summary["crrt_used"] = True
                summary["crrt_days"] = round(summary["crrt_days"] + duration, 2)
        return summary

    def _extract_initial_sofa(
        self,
        patient_doc: dict,
        score_rows: list[dict],
        alert_rows: list[dict],
    ) -> float | None:
        admission = self._patient_icu_start_time(patient_doc)
        window_end = admission
        if isinstance(admission, datetime):
            from datetime import timedelta
            window_end = admission + timedelta(hours=24)

        def _in_window(t: datetime | None) -> bool:
            if not isinstance(t, datetime):
                return False
            if admission and t < admission:
                return False
            if window_end and t > window_end:
                return False
            return True

        for row in score_rows:
            t = row.get("calc_time") if isinstance(row.get("calc_time"), datetime) else row.get("created_at") if isinstance(row.get("created_at"), datetime) else None
            if not _in_window(t):
                continue
            for key in ("sofa_score", "score", "value", "score_value"):
                val = row.get(key)
                if val is None:
                    continue
                try:
                    return float(val)
                except Exception:
                    continue

        for row in alert_rows:
            t = row.get("created_at") if isinstance(row.get("created_at"), datetime) else None
            if not _in_window(t):
                continue
            extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
            for val in (extra.get("score"), row.get("value")):
                if val is None:
                    continue
                try:
                    return float(val)
                except Exception:
                    continue
        return None

    def _get_similar_case_embed_model(self):
        if hasattr(self, "_similar_case_embed_model"):
            return self._similar_case_embed_model
        model_name = str(self._similar_case_cfg().get("embedding_model") or "BAAI/bge-small-zh-v1.5").strip()
        try:
            from sentence_transformers import SentenceTransformer
            self._similar_case_embed_model = SentenceTransformer(model_name)
        except Exception:
            self._similar_case_embed_model = None
        return self._similar_case_embed_model

    async def _ensure_patient_diagnosis_embedding(self, patient_doc: dict) -> dict[str, Any] | None:
        pid = patient_doc.get("_id")
        if pid is None:
            return None
        pid_str = str(pid)
        text = self._similar_case_diag_text(patient_doc)
        if not text:
            return None

        latest = await self.db.col("score_records").find_one(
            {"patient_id": pid_str, "score_type": "diagnosis_embedding"},
            sort=[("calc_time", -1)],
        )
        if isinstance(latest, dict):
            stored_text = str(latest.get("diagnosis_text") or "").strip()
            embedding = latest.get("diagnosis_embedding")
            if stored_text == text and isinstance(embedding, list) and embedding:
                return latest

        model = self._get_similar_case_embed_model()
        if model is None:
            return None
        try:
            vec = model.encode([text], show_progress_bar=False, normalize_embeddings=True)[0]
            vector = [round(float(x), 8) for x in vec.tolist()]
        except Exception:
            return None

        now = datetime.now()
        payload = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "diagnosis_embedding",
            "diagnosis_text": text,
            "diagnosis_tokens": self._similar_case_diag_tokens(text),
            "diagnosis_embedding": vector,
            "embedding_model": str(self._similar_case_cfg().get("embedding_model") or "BAAI/bge-small-zh-v1.5"),
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        if latest and latest.get("_id") is not None:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
            payload["_id"] = latest["_id"]
            return payload
        res = await self.db.col("score_records").insert_one(payload)
        payload["_id"] = res.inserted_id
        return payload

    def _cosine_similarity(self, a: list[float] | None, b: list[float] | None) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(float(x) * float(y) for x, y in zip(a, b))
        na = math.sqrt(sum(float(x) * float(x) for x in a))
        nb = math.sqrt(sum(float(y) * float(y) for y in b))
        if na <= 1e-12 or nb <= 1e-12:
            return 0.0
        return round(dot / (na * nb), 4)

    async def _build_vasopressor_usage_map(self, patient_ids: list[str]) -> dict[str, bool]:
        if not patient_ids:
            return {}
        keywords = self._get_cfg_list(("alert_engine", "drug_mapping", "vasopressors"), ["去甲肾上腺素", "肾上腺素", "多巴胺", "去氧肾上腺素", "血管加压素"])
        regex = "|".join(re.escape(str(k)) for k in keywords if str(k).strip())
        if not regex:
            return {}
        result = {pid: False for pid in patient_ids}
        cursor = self.db.col("drugExe").find(
            {"pid": {"$in": patient_ids}, "drugName": {"$regex": regex, "$options": "i"}},
            {"pid": 1},
        ).limit(max(50, len(patient_ids) * 4))
        async for row in cursor:
            result[str(row.get("pid") or "")] = True
        return result

    def _interventions_from_case(self, *, support: dict[str, Any], vasopressor_used: bool) -> list[str]:
        rows: list[str] = []
        if support.get("vent_used"):
            rows.append(f"机械通气 {support.get('vent_days') or 0} 天")
        if support.get("crrt_used"):
            rows.append(f"CRRT {support.get('crrt_days') or 0} 天")
        if vasopressor_used:
            rows.append("血管活性药支持")
        return rows or ["未见关键器官支持"]

    async def _interpret_similar_case_patterns(
        self,
        *,
        current_profile: dict[str, Any],
        cases: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not cases:
            return None
        cfg = self.config
        model = cfg.llm_model_medical or cfg.settings.LLM_MODEL
        if not model:
            return None

        prompt = {
            "current_patient": current_profile,
            "similar_cases_top5": cases[:5],
            "task": "请总结历史相似病例启示，强调结局模式、干预差异和对当前患者的参考价值。",
        }
        system_prompt = (
            "你是ICU相似病例结局解读助手。"
            "只能使用输入的当前患者画像和相似病例数据，不得编造。"
            "必须返回严格JSON，字段包括 summary, pattern_bullets, caution。"
            "summary 是 1-2 句中文摘要；pattern_bullets 是最多4条结构化观察；caution 是一句提醒。"
        )

        monitor = self._get_ai_monitor() if hasattr(self, "_get_ai_monitor") else None
        start_ms = AiMonitor.now_ms() if monitor else 0.0
        raw_text = ""
        usage = None
        meta: dict[str, Any] = {}
        try:
            result = await call_llm_chat(
                cfg=cfg,
                system_prompt=system_prompt,
                user_prompt=json.dumps(prompt, ensure_ascii=False, default=str),
                model=model,
                temperature=0.1,
                max_tokens=900,
                timeout_seconds=30,
            )
            raw_text = str(result.get("text") or "")
            usage = result.get("usage")
            meta = result.get("meta") or {}
            model = str(result.get("model") or model)
        except Exception:
            if monitor:
                await monitor.log_llm_call(
                    module="similar_case_review",
                    model=model,
                    prompt=json.dumps(prompt, ensure_ascii=False, default=str),
                    output=raw_text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=False,
                    meta=meta or {"stage": "case_interpretation"},
                    usage=usage,
                )
            return None

        text = str(raw_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return None
            if monitor:
                await monitor.log_llm_call(
                    module="similar_case_review",
                    model=model,
                    prompt=json.dumps(prompt, ensure_ascii=False, default=str),
                    output=text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=True,
                    meta=meta or {"stage": "case_interpretation"},
                    usage=usage,
                )
            bullets = parsed.get("pattern_bullets") if isinstance(parsed.get("pattern_bullets"), list) else []
            return {
                "summary": str(parsed.get("summary") or "").strip(),
                "pattern_bullets": [str(x).strip() for x in bullets[:4] if str(x).strip()],
                "caution": str(parsed.get("caution") or "").strip(),
                "generated_at": datetime.now(),
            }
        except Exception:
            if monitor:
                await monitor.log_llm_call(
                    module="similar_case_review",
                    model=model,
                    prompt=json.dumps(prompt, ensure_ascii=False, default=str),
                    output=text,
                    latency_ms=max(0.0, AiMonitor.now_ms() - start_ms),
                    success=False,
                    meta={**(meta or {}), "stage": "case_interpretation", "error": "json_decode_error"},
                    usage=usage,
                )
            return None

    def _heuristic_case_insight(self, current_profile: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
        top = cases[:5]
        if not top:
            return {}
        crrt_cases = [x for x in top if x.get("crrt_used")]
        crrt_survivors = [x for x in crrt_cases if str(x.get("outcome") or "") != "死亡"]
        non_crrt_cases = [x for x in top if not x.get("crrt_used")]
        non_crrt_deaths = [x for x in non_crrt_cases if str(x.get("outcome") or "") == "死亡"]
        deaths = [x for x in top if str(x.get("outcome") or "") == "死亡"]
        summary = f"{len(top)} 例相似患者中，{len(deaths)} 例死亡，支持模式主要集中在{ 'CRRT/机械通气' if crrt_cases else '机械通气或保守支持' }。"
        bullets: list[str] = []
        if crrt_cases:
            bullets.append(f"{len(crrt_cases)} 例使用 CRRT，其中 {len(crrt_survivors)} 例非死亡结局。")
        if non_crrt_cases:
            bullets.append(f"{len(non_crrt_cases)} 例未使用 CRRT，其中 {len(non_crrt_deaths)} 例死亡。")
        avg_days = [float(x.get("icu_days")) for x in top if x.get("icu_days") is not None]
        if avg_days:
            bullets.append(f"Top-5 相似病例平均 ICU 住院约 {round(sum(avg_days) / len(avg_days), 1)} 天。")
        if current_profile.get("initial_sofa") is not None:
            bullets.append(f"当前患者入科 SOFA {current_profile.get('initial_sofa')}，建议对照相似病例的器官支持启动时点。")
        return {
            "summary": summary,
            "pattern_bullets": bullets[:4],
            "caution": "相似病例仅供参考，不替代当前床旁病情判断。",
            "generated_at": datetime.now(),
        }

    def _degraded_similar_case_result(
        self,
        patient_doc: dict,
        *,
        error: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        pid = patient_doc.get("_id")
        pid_str = str(pid) if pid is not None else ""
        current_profile = {
            "patient_id": pid_str,
            "diagnosis_tokens": self._similar_case_diag_tokens(self._similar_case_diag_text(patient_doc))[:8],
            "diagnosis_text": self._similar_case_diag_text(patient_doc)[:160],
            "age_years": round(self._similar_case_age_years(patient_doc), 1) if self._similar_case_age_years(patient_doc) is not None else None,
            "initial_sofa": None,
            "vent_used": False,
            "crrt_used": False,
            "vasopressor_used": False,
            "interventions": ["AI服务繁忙，暂回退为基础展示"],
            "admission_time": self._patient_icu_start_time(patient_doc),
        }
        message = "AI服务暂时繁忙，已自动降级为基础模式，可稍后刷新重试。"
        if error:
            lower_error = str(error).lower()
            if "429" in lower_error or "too many requests" in lower_error:
                message = "AI服务触发限流，已自动降级为基础模式，可稍后刷新重试。"
            elif "circuit" in lower_error:
                message = "AI服务暂时熔断，已自动降级为基础模式，可稍后刷新重试。"
        return {
            "current_profile": current_profile,
            "summary": {
                "matched_cases": 0,
                "displayed_cases": 0,
                "candidate_pool": 0,
                "embedding_enabled": False,
                "avg_icu_days": None,
                "avg_vent_days": None,
                "survival_rate": None,
                "outcomes": {"好转出科": 0, "自动出院": 0, "死亡": 0, "已出院": 0},
                "degraded": True,
                "fallback_message": message,
                "requested_limit": max(1, int(limit or 10)),
            },
            "cases": [],
            "historical_case_insight": {
                "summary": message,
                "pattern_bullets": ["已切换为非AI降级路径，本次不展示LLM结局解读。"],
                "caution": "当前页面仍可继续查看基础病历信息，AI能力恢复后可刷新重试。",
                "generated_at": datetime.now(),
                "degraded": True,
            },
        }

    async def get_similar_case_outcomes(self, patient_doc: dict, limit: int = 10) -> dict[str, Any]:
        pid = patient_doc.get("_id")
        if not pid:
            return {"current_profile": {}, "summary": {}, "cases": []}
        limit = max(1, int(limit or 10))

        try:
            cfg = self._similar_case_cfg()
            max_candidates = int(cfg.get("max_candidates", 200) or 200)
            age_band = float(cfg.get("age_band_years", 10) or 10)
            sofa_band = float(cfg.get("sofa_band", 2) or 2)
            top_keywords = int(cfg.get("diagnosis_keyword_limit", 6) or 6)
            min_diag_similarity = float(cfg.get("min_diagnosis_similarity", 0.15) or 0.15)
            embedding_weight = float(cfg.get("embedding_weight", 0.65) or 0.65)
            token_weight = float(cfg.get("token_weight", 0.15) or 0.15)

            current_text = self._similar_case_diag_text(patient_doc)
            current_tokens = self._similar_case_diag_tokens(current_text)
            current_age = self._similar_case_age_years(patient_doc)
            current_admission = self._patient_icu_start_time(patient_doc)

            current_embedding_doc = await self._ensure_patient_diagnosis_embedding(patient_doc)
            current_embedding = (
                current_embedding_doc.get("diagnosis_embedding")
                if isinstance(current_embedding_doc, dict) and isinstance(current_embedding_doc.get("diagnosis_embedding"), list)
                else None
            )

            current_bind_rows = [
                row async for row in self.db.col("deviceBind").find(
                    {"pid": str(pid)},
                    {"pid": 1, "type": 1, "bindTime": 1, "unBindTime": 1, "deviceName": 1, "name": 1},
                )
            ]
            current_support = self._support_summary_from_binds(current_bind_rows, self._patient_end_time(patient_doc))
            current_vaso_map = await self._build_vasopressor_usage_map([str(pid)])
            current_vaso_used = bool(current_vaso_map.get(str(pid)))

            current_score_rows = [
                row async for row in self.db.col("score_records").find(
                    {
                        "patient_id": str(pid),
                        "score_type": {"$in": ["sepsis_antibiotic_bundle", "sofa", "sepsis_sofa", "sofa_score"]},
                    },
                    {"patient_id": 1, "score_type": 1, "calc_time": 1, "created_at": 1, "sofa_score": 1, "score": 1, "value": 1},
                ).sort("calc_time", 1).limit(120)
            ]
            current_alert_rows = [
                row async for row in self.db.col("alert_records").find(
                    {"patient_id": str(pid), "$or": [{"alert_type": "sofa"}, {"rule_id": "SEPSIS_SOFA"}]},
                    {"patient_id": 1, "created_at": 1, "value": 1, "extra": 1},
                ).sort("created_at", 1).limit(40)
            ]
            current_sofa = self._extract_initial_sofa(patient_doc, current_score_rows, current_alert_rows)

            query: dict[str, Any] = {
                "$and": [
                    self._similar_case_discharged_query(),
                    {"_id": {"$ne": pid}},
                ]
            }
            if current_age is not None:
                query["$and"].append({"$or": [{"age": {"$exists": True}}, {"hisAge": {"$exists": True}}]})

            regex_clauses: list[dict[str, Any]] = []
            for token in current_tokens[:top_keywords]:
                rx = {"$regex": re.escape(token), "$options": "i"}
                for field in ("clinicalDiagnosis", "admissionDiagnosis", "diagnosis", "diagnosisHistory", "history"):
                    regex_clauses.append({field: rx})
            if regex_clauses and current_embedding is None:
                query["$and"].append({"$or": regex_clauses})

            projection = {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "age": 1,
                "hisAge": 1,
                "status": 1,
                "outcome": 1,
                "leaveType": 1,
                "dischargeType": 1,
                "dischargeDisposition": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "diagnosis": 1,
                "diagnosisHistory": 1,
                "history": 1,
                "icuAdmissionTime": 1,
                "admissionTime": 1,
                "admitTime": 1,
                "inTime": 1,
                "createTime": 1,
                "dischargeTime": 1,
                "outTime": 1,
                "leaveTime": 1,
                "deathTime": 1,
                "remark": 1,
            }
            candidate_docs = [doc async for doc in self.db.col("patient").find(query, projection).limit(max_candidates)]
            if not candidate_docs:
                return {
                    "current_profile": {
                        "patient_id": str(pid),
                        "diagnosis_tokens": current_tokens[:8],
                        "initial_sofa": current_sofa,
                        "age_years": current_age,
                        "vent_used": current_support["vent_used"],
                        "crrt_used": current_support["crrt_used"],
                        "vasopressor_used": current_vaso_used,
                        "admission_time": current_admission,
                    },
                    "summary": {"matched_cases": 0},
                    "cases": [],
                }

            candidate_ids = [str(doc["_id"]) for doc in candidate_docs if doc.get("_id") is not None]

            bind_map: dict[str, list[dict]] = {}
            async for row in self.db.col("deviceBind").find(
                {"pid": {"$in": candidate_ids}},
                {"pid": 1, "type": 1, "bindTime": 1, "unBindTime": 1, "deviceName": 1, "name": 1},
            ):
                bind_map.setdefault(str(row.get("pid") or ""), []).append(row)

            score_map: dict[str, list[dict]] = {}
            async for row in self.db.col("score_records").find(
                {
                    "patient_id": {"$in": candidate_ids},
                    "score_type": {"$in": ["sepsis_antibiotic_bundle", "sofa", "sepsis_sofa", "sofa_score"]},
                },
                {"patient_id": 1, "score_type": 1, "calc_time": 1, "created_at": 1, "sofa_score": 1, "score": 1, "value": 1},
            ).sort("calc_time", 1):
                score_map.setdefault(str(row.get("patient_id") or ""), []).append(row)

            alert_map: dict[str, list[dict]] = {}
            async for row in self.db.col("alert_records").find(
                {
                    "patient_id": {"$in": candidate_ids},
                    "$or": [{"alert_type": "sofa"}, {"rule_id": "SEPSIS_SOFA"}],
                },
                {"patient_id": 1, "created_at": 1, "value": 1, "extra": 1},
            ).sort("created_at", 1):
                alert_map.setdefault(str(row.get("patient_id") or ""), []).append(row)

            embedding_rows = [
                row async for row in self.db.col("score_records").find(
                    {"patient_id": {"$in": candidate_ids}, "score_type": "diagnosis_embedding"},
                    {"patient_id": 1, "diagnosis_embedding": 1},
                )
            ]
            embedding_map = {str(row.get("patient_id") or ""): row for row in embedding_rows}
            vaso_map = await self._build_vasopressor_usage_map(candidate_ids)

            matched_cases: list[dict[str, Any]] = []
            for doc in candidate_docs:
                pid_str = str(doc.get("_id"))
                cand_age = self._similar_case_age_years(doc)
                if current_age is not None and cand_age is not None and abs(cand_age - current_age) > age_band:
                    continue

                support = self._support_summary_from_binds(bind_map.get(pid_str, []), self._patient_end_time(doc))
                if support["vent_used"] != current_support["vent_used"]:
                    continue
                if current_support["crrt_used"] and not support["crrt_used"]:
                    continue

                cand_sofa = self._extract_initial_sofa(doc, score_map.get(pid_str, []), alert_map.get(pid_str, []))
                if current_sofa is not None and cand_sofa is not None and abs(cand_sofa - current_sofa) > sofa_band:
                    continue

                cand_text = self._similar_case_diag_text(doc)
                cand_tokens = self._similar_case_diag_tokens(cand_text)
                token_similarity = self._similar_case_diag_similarity(current_tokens, cand_tokens)

                embedding_doc = embedding_map.get(pid_str)
                cand_embedding = embedding_doc.get("diagnosis_embedding") if isinstance(embedding_doc, dict) else None
                embedding_similarity = self._cosine_similarity(current_embedding, cand_embedding)
                if current_embedding is not None and cand_embedding is None:
                    ensured = await self._ensure_patient_diagnosis_embedding(doc)
                    cand_embedding = ensured.get("diagnosis_embedding") if isinstance(ensured, dict) else None
                    embedding_similarity = self._cosine_similarity(current_embedding, cand_embedding)
                if current_embedding is None and current_tokens and token_similarity < min_diag_similarity:
                    continue
                if current_embedding is not None and embedding_similarity <= 0 and token_similarity < min_diag_similarity:
                    continue

                icu_days = self._safe_days(self._patient_icu_start_time(doc), self._patient_end_time(doc))
                age_score = 1.0 if current_age is None or cand_age is None else max(0.0, 1 - abs(cand_age - current_age) / max(age_band, 1))
                sofa_score = 1.0 if current_sofa is None or cand_sofa is None else max(0.0, 1 - abs(cand_sofa - current_sofa) / max(sofa_band, 1))
                support_score = 1.0 if bool(vaso_map.get(pid_str)) == current_vaso_used else 0.75
                total_score = round(
                    embedding_similarity * embedding_weight +
                    token_similarity * token_weight +
                    age_score * 0.1 +
                    sofa_score * 0.1 +
                    support_score * 0.05,
                    3,
                )

                matched_dims: list[str] = []
                if embedding_similarity > 0:
                    matched_dims.append(f"诊断embedding余弦 {embedding_similarity}")
                elif token_similarity > 0:
                    matched_dims.append("诊断关键词相似")
                if current_age is not None and cand_age is not None:
                    matched_dims.append("年龄±10岁")
                if current_sofa is not None and cand_sofa is not None:
                    matched_dims.append("入科SOFA±2")
                if current_support["vent_used"]:
                    matched_dims.append("同样使用呼吸机")
                if current_support["crrt_used"]:
                    matched_dims.append("同样接受CRRT")
                if current_vaso_used and vaso_map.get(pid_str):
                    matched_dims.append("同样需要血管活性药")

                interventions = self._interventions_from_case(
                    support=support,
                    vasopressor_used=bool(vaso_map.get(pid_str)),
                )
                matched_cases.append(
                    {
                        "patient_id": pid_str,
                        "patient_name": doc.get("name") or "",
                        "bed": doc.get("hisBed"),
                        "age_years": round(cand_age, 1) if cand_age is not None else None,
                        "initial_sofa": cand_sofa,
                        "diagnosis_excerpt": cand_text[:120],
                        "embedding_similarity": embedding_similarity,
                        "diag_similarity": token_similarity,
                        "similarity_score": total_score,
                        "vent_used": support["vent_used"],
                        "vent_days": support["vent_days"],
                        "crrt_used": support["crrt_used"],
                        "crrt_days": support["crrt_days"],
                        "vasopressor_used": bool(vaso_map.get(pid_str)),
                        "interventions": interventions,
                        "icu_days": icu_days,
                        "outcome": self._patient_outcome_label(doc),
                        "matched_dimensions": matched_dims,
                        "admission_time": self._patient_icu_start_time(doc),
                        "discharge_time": self._patient_end_time(doc),
                    }
                )

            matched_cases.sort(
                key=lambda x: (
                    x.get("similarity_score") or 0,
                    x.get("embedding_similarity") or 0,
                    x.get("diag_similarity") or 0,
                ),
                reverse=True,
            )
            top_cases = matched_cases[:limit]
            if hasattr(self, "_collect_nursing_context"):
                for item in top_cases[:5]:
                    candidate_doc = next((doc for doc in candidate_docs if str(doc.get("_id")) == str(item.get("patient_id"))), None)
                    if candidate_doc is None:
                        continue
                    try:
                        nursing_context = await self._collect_nursing_context(candidate_doc, str(item.get("patient_id") or ""), hours=72)
                    except Exception:
                        nursing_context = {}
                    item["nursing_signals"] = [row.get("text") for row in (nursing_context.get("records") or [])[:3] if str(row.get("text") or "").strip()]
                    item["nursing_plan_summary"] = nursing_context.get("plans") or {}
                    item["nursing_pending_count"] = ((nursing_context.get("plans") or {}) if isinstance(nursing_context.get("plans"), dict) else {}).get("pending_count")
                    item["nursing_delayed_count"] = ((nursing_context.get("plans") or {}) if isinstance(nursing_context.get("plans"), dict) else {}).get("delayed_count")

            outcomes = {"好转出科": 0, "自动出院": 0, "死亡": 0, "已出院": 0}
            icu_days_list: list[float] = []
            vent_days_list: list[float] = []
            for item in matched_cases:
                outcome = str(item.get("outcome") or "已出院")
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
                if item.get("icu_days") is not None:
                    icu_days_list.append(float(item["icu_days"]))
                vent_days_list.append(float(item.get("vent_days") or 0.0))

            current_profile = {
                "patient_id": str(pid),
                "diagnosis_tokens": current_tokens[:8],
                "diagnosis_text": current_text[:160],
                "initial_sofa": current_sofa,
                "age_years": round(current_age, 1) if current_age is not None else None,
                "vent_used": current_support["vent_used"],
                "crrt_used": current_support["crrt_used"],
                "vasopressor_used": current_vaso_used,
                "interventions": self._interventions_from_case(support=current_support, vasopressor_used=current_vaso_used),
                "admission_time": current_admission,
            }
            if hasattr(self, "_collect_nursing_context"):
                try:
                    current_nursing_context = await self._collect_nursing_context(patient_doc, str(pid), hours=72)
                except Exception:
                    current_nursing_context = {}
                current_profile["nursing_signals"] = [
                    row.get("text") for row in (current_nursing_context.get("records") or [])[:4] if str(row.get("text") or "").strip()
                ]
                current_profile["nursing_plan_summary"] = current_nursing_context.get("plans") or {}
                current_profile["nursing_pending_count"] = ((current_nursing_context.get("plans") or {}) if isinstance(current_nursing_context.get("plans"), dict) else {}).get("pending_count")
                current_profile["nursing_delayed_count"] = ((current_nursing_context.get("plans") or {}) if isinstance(current_nursing_context.get("plans"), dict) else {}).get("delayed_count")
            survival_count = sum(1 for item in matched_cases if str(item.get("outcome")) != "死亡")
            summary = {
                "matched_cases": len(matched_cases),
                "displayed_cases": len(top_cases),
                "candidate_pool": len(candidate_docs),
                "embedding_enabled": current_embedding is not None,
                "avg_icu_days": round(sum(icu_days_list) / len(icu_days_list), 2) if icu_days_list else None,
                "avg_vent_days": round(sum(vent_days_list) / len(vent_days_list), 2) if vent_days_list else None,
                "survival_rate": round(survival_count / len(matched_cases), 3) if matched_cases else None,
                "outcomes": outcomes,
            }

            interpretation = await self._interpret_similar_case_patterns(current_profile=current_profile, cases=top_cases[:5])
            if not interpretation:
                interpretation = self._heuristic_case_insight(current_profile, top_cases[:5])

            return {
                "current_profile": current_profile,
                "summary": summary,
                "cases": top_cases,
                "historical_case_insight": interpretation,
            }
        except Exception as exc:
            logger.warning("similar_case_review degraded pid=%s error=%s", str(pid), exc)
            return self._degraded_similar_case_result(patient_doc, error=str(exc), limit=limit)
