"""历史相似病例结局回溯。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any


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
        return round(inter / max(len(a), 1), 3)

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
        window_end = admission if isinstance(admission, datetime) else None
        if window_end is not None:
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

    async def get_similar_case_outcomes(self, patient_doc: dict, limit: int = 10) -> dict[str, Any]:
        pid = patient_doc.get("_id")
        if not pid:
            return {"current_profile": {}, "summary": {}, "cases": []}

        cfg = self._similar_case_cfg()
        max_candidates = int(cfg.get("max_candidates", 200) or 200)
        age_band = float(cfg.get("age_band_years", 10) or 10)
        sofa_band = float(cfg.get("sofa_band", 2) or 2)
        top_keywords = int(cfg.get("diagnosis_keyword_limit", 6) or 6)
        min_diag_similarity = float(cfg.get("min_diagnosis_similarity", 0.15) or 0.15)

        current_text = self._similar_case_diag_text(patient_doc)
        current_tokens = self._similar_case_diag_tokens(current_text)
        current_age = self._similar_case_age_years(patient_doc)
        current_admission = self._patient_icu_start_time(patient_doc)

        current_bind_rows = [
            row async for row in self.db.col("deviceBind").find(
                {"pid": str(pid)},
                {"pid": 1, "type": 1, "bindTime": 1, "unBindTime": 1, "deviceName": 1, "name": 1},
            )
        ]
        current_support = self._support_summary_from_binds(current_bind_rows, self._patient_end_time(patient_doc))

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
        if regex_clauses:
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

        matched_cases: list[dict[str, Any]] = []
        for doc in candidate_docs:
            pid_str = str(doc.get("_id"))
            cand_age = self._similar_case_age_years(doc)
            if current_age is not None and cand_age is not None and abs(cand_age - current_age) > age_band:
                continue

            support = self._support_summary_from_binds(bind_map.get(pid_str, []), self._patient_end_time(doc))
            if support["vent_used"] != current_support["vent_used"]:
                continue
            if support["crrt_used"] != current_support["crrt_used"]:
                continue

            cand_sofa = self._extract_initial_sofa(doc, score_map.get(pid_str, []), alert_map.get(pid_str, []))
            if current_sofa is not None and cand_sofa is not None and abs(cand_sofa - current_sofa) > sofa_band:
                continue

            cand_text = self._similar_case_diag_text(doc)
            cand_tokens = self._similar_case_diag_tokens(cand_text)
            diag_similarity = self._similar_case_diag_similarity(current_tokens, cand_tokens)
            if current_tokens and diag_similarity < min_diag_similarity:
                continue

            icu_days = self._safe_days(self._patient_icu_start_time(doc), self._patient_end_time(doc))
            age_score = 1.0 if current_age is None or cand_age is None else max(0.0, 1 - abs(cand_age - current_age) / max(age_band, 1))
            sofa_score = 1.0 if current_sofa is None or cand_sofa is None else max(0.0, 1 - abs(cand_sofa - current_sofa) / max(sofa_band, 1))
            support_score = 1.0
            total_score = round(diag_similarity * 0.55 + age_score * 0.15 + sofa_score * 0.15 + support_score * 0.15, 3)

            matched_dims: list[str] = []
            if diag_similarity > 0:
                matched_dims.append("诊断相似")
            if current_age is not None and cand_age is not None:
                matched_dims.append("年龄±10岁")
            if current_sofa is not None and cand_sofa is not None:
                matched_dims.append("入科SOFA±2")
            if current_support["vent_used"]:
                matched_dims.append("同样使用呼吸机")
            if current_support["crrt_used"]:
                matched_dims.append("同样接受CRRT")

            matched_cases.append(
                {
                    "patient_id": pid_str,
                    "patient_name": doc.get("name") or "",
                    "bed": doc.get("hisBed"),
                    "age_years": round(cand_age, 1) if cand_age is not None else None,
                    "initial_sofa": cand_sofa,
                    "diagnosis_excerpt": cand_text[:120],
                    "diag_similarity": diag_similarity,
                    "similarity_score": total_score,
                    "vent_used": support["vent_used"],
                    "vent_days": support["vent_days"],
                    "crrt_used": support["crrt_used"],
                    "crrt_days": support["crrt_days"],
                    "icu_days": icu_days,
                    "outcome": self._patient_outcome_label(doc),
                    "matched_dimensions": matched_dims,
                    "admission_time": self._patient_icu_start_time(doc),
                    "discharge_time": self._patient_end_time(doc),
                }
            )

        matched_cases.sort(key=lambda x: (x.get("similarity_score") or 0, x.get("diag_similarity") or 0), reverse=True)
        top_cases = matched_cases[: max(1, int(limit or 10))]

        outcomes = {"好转出科": 0, "自动出院": 0, "死亡": 0, "已出院": 0}
        icu_days_list: list[float] = []
        vent_days_list: list[float] = []
        for item in matched_cases:
            outcome = str(item.get("outcome") or "已出院")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            if item.get("icu_days") is not None:
                icu_days_list.append(float(item["icu_days"]))
            vent_days_list.append(float(item.get("vent_days") or 0.0))

        survival_count = sum(1 for item in matched_cases if str(item.get("outcome")) != "死亡")
        summary = {
            "matched_cases": len(matched_cases),
            "displayed_cases": len(top_cases),
            "candidate_pool": len(candidate_docs),
            "avg_icu_days": round(sum(icu_days_list) / len(icu_days_list), 2) if icu_days_list else None,
            "avg_vent_days": round(sum(vent_days_list) / len(vent_days_list), 2) if vent_days_list else None,
            "survival_rate": round(survival_count / len(matched_cases), 3) if matched_cases else None,
            "outcomes": outcomes,
        }

        return {
            "current_profile": {
                "patient_id": str(pid),
                "diagnosis_tokens": current_tokens[:8],
                "initial_sofa": current_sofa,
                "age_years": round(current_age, 1) if current_age is not None else None,
                "vent_used": current_support["vent_used"],
                "crrt_used": current_support["crrt_used"],
                "admission_time": current_admission,
            },
            "summary": summary,
            "cases": top_cases,
        }
