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
        llm_call: Callable[[str, str, str | None], Awaitable[str]],
        model: str | None = None,
    ) -> dict[str, Any]:
        context = await self._build_context(patient_id, patient_doc)
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
        parsed["validation"] = validation
        parsed["generated_at"] = datetime.now().isoformat()
        return {"summary": parsed, "context_snapshot": context}

    async def _build_context(self, patient_id: str, patient_doc: dict) -> dict[str, Any]:
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

