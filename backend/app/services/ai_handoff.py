"""AI handoff summary service (I-PASS)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable


class AiHandoffService:
    def __init__(self, db, config) -> None:
        self.db = db
        self.config = config

    async def generate(
        self,
        *,
        patient_id: str,
        patient_doc: dict,
        similar_case_review: dict[str, Any] | None = None,
        nursing_context: dict[str, Any] | None = None,
        llm_call: Callable[[str, str, str | None], Awaitable[str]],
        model: str | None = None,
    ) -> dict[str, Any]:
        context = await self._build_context(
            patient_id,
            patient_doc,
            similar_case_review=similar_case_review,
            nursing_context=nursing_context,
        )
        system_prompt = (
            "你是ICU交班助手，按I-PASS结构生成交班摘要。"
            "只能归纳已提供数据，不得编造。必须返回严格JSON。"
        )
        user_prompt = (
            "请基于以下数据生成交班摘要，字段包括: "
            "illness_severity, patient_summary, action_list, situation_awareness, "
            "synthesis_by_receiver, confidence_level。\n"
            "其中 confidence_level 仅可取 high/medium/low。\n"
            "数据: " + json.dumps(context, ensure_ascii=False, default=str)
        )

        raw = await llm_call(system_prompt, user_prompt, model)
        parsed = self._parse_json(raw)
        if not parsed:
            parsed = {
                "illness_severity": "watcher",
                "patient_summary": "AI解析失败，请查看原始数据。",
                "action_list": [],
                "situation_awareness": [],
                "synthesis_by_receiver": "请交班医生复核关键生命体征与实验室变化。",
                "confidence_level": "low",
            }

        validation = self._validate_numeric_claims(parsed, context)
        parsed = self._apply_structured_hints(parsed, context)
        parsed["validation"] = validation
        parsed["generated_at"] = datetime.now().isoformat()
        return {"summary": parsed, "context_snapshot": context}

    async def _build_context(
        self,
        patient_id: str,
        patient_doc: dict,
        similar_case_review: dict[str, Any] | None = None,
        nursing_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now()
        since = now - timedelta(hours=12)

        pid_list = [patient_id]
        if hp := (patient_doc.get("hisPid") or patient_doc.get("hisPID")):
            if str(hp) not in pid_list: pid_list.append(str(hp))

        # 12h vitals trend (bedside)
        vitals_codes = ["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_T"]
        cursor_v = self.db.col("bedside").find(
            {"pid": {"$in": pid_list}, "code": {"$in": vitals_codes}, "time": {"$gte": since}},
            {"code": 1, "time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
        ).sort("time", -1).limit(1200)
        vitals_raw = [d async for d in cursor_v]

        latest_vitals: dict[str, float] = {}
        for doc in vitals_raw:
            code = str(doc.get("code") or "")
            if code in latest_vitals:
                continue
            val = self._num(doc.get("fVal"))
            if val is None:
                val = self._num(doc.get("intVal"))
            if val is None:
                val = self._num(doc.get("strVal"))
            if val is None:
                continue
            latest_vitals[code] = val

        # 12h alerts
        cursor_a = self.db.col("alert_records").find(
            {"patient_id": {"$in": pid_list}, "created_at": {"$gte": since}},
            {"name": 1, "alert_type": 1, "severity": 1, "created_at": 1, "extra": 1},
        ).sort("created_at", -1).limit(100)
        alerts = [d async for d in cursor_a]

        # 12h labs
        labs: list[dict[str, Any]] = []
        his_pid = patient_doc.get("hisPid")
        if his_pid:
            cursor_l = self.db.dc_col("VI_ICU_EXAM_ITEM").find(
                {"hisPid": his_pid, "authTime": {"$gte": since}},
                {
                    "itemCnName": 1,
                    "itemName": 1,
                    "itemCode": 1,
                    "result": 1,
                    "resultValue": 1,
                    "unit": 1,
                    "resultFlag": 1,
                    "seriousFlag": 1,
                    "authTime": 1,
                },
            ).sort("authTime", -1).limit(200)
            async for doc in cursor_l:
                labs.append(
                    {
                        "name": doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "?",
                        "result": doc.get("result") or doc.get("resultValue"),
                        "unit": doc.get("unit") or "",
                        "flag": doc.get("resultFlag") or doc.get("seriousFlag") or "",
                        "time": doc.get("authTime"),
                    }
                )

        # 12h drugs
        cursor_d = self.db.col("drugExe").find(
            {"pid": {"$in": pid_list}, "$or": [{"exeTime": {"$gte": since}}, {"time": {"$gte": since}}]},
            {"drugName": 1, "dosage": 1, "dose": 1, "route": 1, "exeTime": 1, "time": 1},
        ).sort("exeTime", -1).limit(120)
        drugs = [d async for d in cursor_d]

        # 12h assessments
        cursor_s = self.db.col("score_records").find(
            {"patient_id": {"$in": [patient_doc.get("_id"), patient_id]}, "calc_time": {"$gte": since}},
            {"score_type": 1, "score": 1, "calc_time": 1, "detail": 1},
        ).sort("calc_time", -1).limit(80)
        assessments = [d async for d in cursor_s]

        palliative = await self.db.col("score_records").find_one(
            {"patient_id": patient_id, "score_type": "palliative_trigger"},
            sort=[("calc_time", -1)],
        )

        return {
            "patient": {
                "name": patient_doc.get("name") or "未知",
                "diag": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "未知",
                "nursing_level": patient_doc.get("nursingLevel") or "未知",
                "icu_admission_time": patient_doc.get("icuAdmissionTime"),
            },
            "latest_vitals": {
                "hr": latest_vitals.get("param_HR"),
                "spo2": latest_vitals.get("param_spo2"),
                "rr": latest_vitals.get("param_resp"),
                "sbp": latest_vitals.get("param_nibp_s") or latest_vitals.get("param_ibp_s"),
                "temp": latest_vitals.get("param_T"),
            },
            "alerts_12h": alerts,
            "labs_12h": labs,
            "drugs_12h": drugs,
            "assessments_12h": assessments,
            "palliative_trigger": {
                "score": palliative.get("score"),
                "recommendation": palliative.get("recommendation"),
                "flags": palliative.get("flags"),
                "icu_days": palliative.get("icu_days"),
            } if palliative else None,
            "similar_case_review": similar_case_review or None,
            "nursing_context": nursing_context or None,
        }

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        t = str(text or "").strip()
        if t.startswith("```"):
            t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
            t = re.sub(r"\s*```$", "", t)
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            t = m.group(0)
        try:
            data = json.loads(t)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _ensure_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return list(value)
        if value in (None, ""):
            return []
        return [value]

    def _append_unique(self, values: list[Any], item: Any) -> list[Any]:
        text = str(item or "").strip()
        if not text:
            return values
        existing = {str(x or "").strip() for x in values}
        if text not in existing:
            values.append(text)
        return values

    def _apply_structured_hints(self, summary: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(summary, dict):
            return summary
        palliative = context.get("palliative_trigger") if isinstance(context.get("palliative_trigger"), dict) else None
        similar_case_review = context.get("similar_case_review") if isinstance(context.get("similar_case_review"), dict) else None
        nursing_context = context.get("nursing_context") if isinstance(context.get("nursing_context"), dict) else None
        if not palliative:
            pass
        else:
            recommendation = str(palliative.get("recommendation") or "").strip()
            if recommendation:
                flags = palliative.get("flags") if isinstance(palliative.get("flags"), dict) else {}
                icu_days = palliative.get("icu_days")
                reason_parts: list[str] = []
                if icu_days is not None:
                    reason_parts.append(f"ICU住院 {icu_days} 天")
                if (flags.get("aki_stage") or 0) >= 2:
                    reason_parts.append("AKI stage >= 2")
                if flags.get("ards"):
                    reason_parts.append("ARDS 持续")
                if flags.get("vasopressor_dependency_7d"):
                    reason_parts.append("血管活性药依赖 > 7 天")
                if flags.get("gcs") is not None and float(flags.get("gcs")) <= 8:
                    reason_parts.append(f"GCS 持续 <= 8（当前 {flags.get('gcs')}）")
                detailed_hint = recommendation if not reason_parts else f"{recommendation} 依据：{'；'.join(reason_parts)}。"
                summary["situation_awareness"] = self._append_unique(self._ensure_list(summary.get("situation_awareness")), detailed_hint)
                summary["action_list"] = self._append_unique(self._ensure_list(summary.get("action_list")), recommendation)
                summary["structured_hints"] = {
                    "palliative_care": {
                        "enabled": True,
                        "score": palliative.get("score"),
                        "recommendation": recommendation,
                        "icu_days": icu_days,
                        "flags": flags,
                    }
                }
        if similar_case_review:
            insight = similar_case_review.get("historical_case_insight") if isinstance(similar_case_review.get("historical_case_insight"), dict) else {}
            insight_summary = str(insight.get("summary") or "").strip()
            bullets = insight.get("pattern_bullets") if isinstance(insight.get("pattern_bullets"), list) else []
            if insight_summary:
                summary["situation_awareness"] = self._append_unique(
                    self._ensure_list(summary.get("situation_awareness")),
                    f"历史相似病例启示：{insight_summary}",
                )
            for bullet in [str(x).strip() for x in bullets[:3] if str(x).strip()]:
                summary["action_list"] = self._append_unique(self._ensure_list(summary.get("action_list")), f"参考相似病例：{bullet}")
            structured = summary.get("structured_hints") if isinstance(summary.get("structured_hints"), dict) else {}
            structured["similar_cases"] = {
                "matched_cases": ((similar_case_review.get("summary") or {}) if isinstance(similar_case_review.get("summary"), dict) else {}).get("matched_cases"),
                "survival_rate": ((similar_case_review.get("summary") or {}) if isinstance(similar_case_review.get("summary"), dict) else {}).get("survival_rate"),
                "insight_summary": insight_summary,
                "pattern_bullets": [str(x).strip() for x in bullets[:4] if str(x).strip()],
                "caution": str(insight.get("caution") or "").strip(),
            }
            summary["structured_hints"] = structured
        if nursing_context:
            record_rows = nursing_context.get("records") if isinstance(nursing_context.get("records"), list) else []
            plan_info = nursing_context.get("plans") if isinstance(nursing_context.get("plans"), dict) else {}
            top_texts = [str(row.get("text") or "").strip() for row in record_rows[:3] if str(row.get("text") or "").strip()]
            for text in top_texts:
                summary["situation_awareness"] = self._append_unique(
                    self._ensure_list(summary.get("situation_awareness")),
                    f"护理记录提示：{text}",
                )
            pending_count = int(plan_info.get("pending_count") or 0)
            delayed_count = int(plan_info.get("delayed_count") or 0)
            if pending_count > 0:
                summary["action_list"] = self._append_unique(
                    self._ensure_list(summary.get("action_list")),
                    f"存在 {pending_count} 项近期护理计划待确认是否已执行。",
                )
            if delayed_count > 0:
                summary["action_list"] = self._append_unique(
                    self._ensure_list(summary.get("action_list")),
                    f"存在 {delayed_count} 项护理计划已到计划时间但仍未开始执行。",
                )
            structured = summary.get("structured_hints") if isinstance(summary.get("structured_hints"), dict) else {}
            structured["nursing_context"] = {
                "recent_record_count": len(record_rows),
                "planned_count": int(plan_info.get("planned_count") or 0),
                "executed_count": int(plan_info.get("executed_count") or 0),
                "pending_count": pending_count,
                "delayed_count": delayed_count,
                "top_records": top_texts,
            }
            summary["structured_hints"] = structured
        return summary

    def _validate_numeric_claims(self, summary: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        text = json.dumps(summary, ensure_ascii=False)
        vitals = context.get("latest_vitals") or {}
        checks = [
            ("HR", ["hr", "心率"], self._num(vitals.get("hr")), 8.0),
            ("SpO2", ["spo2", "血氧"], self._num(vitals.get("spo2")), 3.0),
            ("RR", ["rr", "呼吸"], self._num(vitals.get("rr")), 4.0),
            ("SBP", ["sbp", "收缩压", "血压"], self._num(vitals.get("sbp")), 12.0),
            ("Temp", ["体温", "temp"], self._num(vitals.get("temp")), 0.6),
        ]
        issues: list[dict[str, Any]] = []
        for name, kws, observed, tol in checks:
            if observed is None:
                continue
            claims = self._extract_claims(text, kws)
            for c in claims[:4]:
                delta = abs(c - observed)
                if delta > tol:
                    issues.append(
                        {
                            "metric": name,
                            "claimed": round(c, 3),
                            "observed": round(observed, 3),
                            "delta": round(delta, 3),
                            "tolerance": tol,
                        }
                    )
        return {"status": "warning" if issues else "ok", "issues": issues[:10]}

    def _extract_claims(self, text: str, keywords: list[str]) -> list[float]:
        if not text or not keywords:
            return []
        group = "(?:" + "|".join(re.escape(k) for k in keywords) + ")"
        patterns = [
            re.compile(rf"{group}[^0-9\-]{{0,10}}(-?\d+(?:\.\d+)?)", re.IGNORECASE),
            re.compile(rf"(-?\d+(?:\.\d+)?)[^0-9\n]{{0,8}}{group}", re.IGNORECASE),
        ]
        vals: list[float] = []
        for p in patterns:
            for m in p.finditer(text):
                n = self._num(m.group(1))
                if n is not None:
                    vals.append(n)
        return vals

    def _num(self, v: Any) -> float | None:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).strip())
        except Exception:
            return None

