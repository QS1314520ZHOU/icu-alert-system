from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.services.ai_monitor import AiMonitor
from app.utils.parse import _parse_dt
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")


@dataclass
class PulseCandidate:
    source: str
    event_id: str
    patient_id: str
    patient_label: str
    severity: str
    raw: dict
    occurred_at: datetime
    owner_role: str


@dataclass
class ViewerContext:
    user_id: str
    role: str
    dept_code: str
    current_patient_id: str | None
    current_route: str | None


@dataclass
class PulseNarration:
    candidate_id: str
    patient_id: str
    headline: str
    action_hint: str
    tone: str
    deep_link: str
    source: str
    occurred_at: str
    dept_code: str = ""


class PulseService:
    def __init__(
        self,
        *,
        db,
        config,
        ws_mgr,
        alert_engine,
        multi_agent_orchestrator=None,
        clinical_reasoning_agent=None,
        ai_monitor: AiMonitor | None = None,
    ) -> None:
        self.db = db
        self.config = config
        self.ws_mgr = ws_mgr
        self.alert_engine = alert_engine
        self.multi_agent_orchestrator = multi_agent_orchestrator
        self.clinical_reasoning_agent = clinical_reasoning_agent
        self.ai_monitor = ai_monitor
        self._stop_event = asyncio.Event()
        self._indexes_ready = False

    def _cfg(self) -> dict[str, Any]:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("pulse", {})
        return cfg if isinstance(cfg, dict) else {}

    def is_enabled(self) -> bool:
        return bool(self._cfg().get("enabled", True))

    async def collect_candidates(self, since: datetime) -> list[PulseCandidate]:
        now = datetime.now()
        rows: list[PulseCandidate] = []
        rows.extend(await self._collect_alert_candidates(since, now))
        rows.extend(await self._collect_score_candidates(since))
        rows.extend(await self._collect_lab_drug_mismatch_candidates(since, now))
        rows.extend(await self._collect_mdt_overdue_candidates(now))
        logger.info("[pulse] candidates collected count=%s since=%s", len(rows), since.isoformat())
        return rows

    async def score_candidate(self, candidate: PulseCandidate, viewer: ViewerContext) -> float:
        severity_weight = {"critical": 1.0, "high": 0.7, "medium": 0.4, "warning": 0.4}.get(candidate.severity, 0.4)
        recent_same = await self.db.col("pulse_events").count_documents(
            {
                "viewer_id": viewer.user_id,
                "patient_id": candidate.patient_id,
                "candidate_type": self._candidate_type(candidate),
                "pushed_at": {"$gte": datetime.now() - timedelta(hours=6)},
            }
        )
        novelty = 0.3 if recent_same else 1.0
        role_fit = 1.2 if viewer.role and viewer.role == candidate.owner_role else 0.6
        patient = await self._load_patient(candidate.patient_id)
        patient_dept = self._candidate_dept_code(candidate, patient)
        if viewer.dept_code and patient_dept and viewer.dept_code != patient_dept:
            return 0.0
        patient_focus = 1.5 if viewer.current_patient_id and viewer.current_patient_id == candidate.patient_id else 1.0
        age_hours = max(0.0, (datetime.now() - candidate.occurred_at).total_seconds() / 3600)
        time_decay = (0.9 ** age_hours) if age_hours > 1 else 1.0
        raw_score = severity_weight * novelty * role_fit * patient_focus * time_decay
        # Keep the 0-1 contract without letting boosted high/medium events saturate
        # into the same score as a truly critical event.
        cap = 1.0 if candidate.severity == "critical" else 0.95 if candidate.severity == "high" else 0.8
        return round(max(0.0, min(cap, raw_score)), 4)

    async def narrate(self, candidate: PulseCandidate) -> PulseNarration:
        candidate_id = f"{candidate.source}_{candidate.event_id}"
        raw = candidate.raw if isinstance(candidate.raw, dict) else {}
        patient = await self._load_patient(candidate.patient_id)
        explanation = raw.get("explanation") if isinstance(raw.get("explanation"), dict) else {}
        compact = self._compact_existing_narration(candidate)
        headline = str(compact.get("headline") or explanation.get("summary") or raw.get("summary") or raw.get("name") or "").strip()
        action_hint = str(compact.get("action_hint") or explanation.get("suggestion") or raw.get("recommendation") or raw.get("action_hint") or "").strip()
        tone = "critical" if candidate.severity == "critical" else "warn" if candidate.severity == "high" else "info"
        if not headline or not action_hint:
            generated = await self._narrate_with_llm(candidate)
            headline = str(generated.get("headline") or headline or f"{candidate.patient_label}出现新的AI关注事件").strip()
            action_hint = str(generated.get("action_hint") or action_hint or "请查看详情并结合床旁情况处理").strip()
            tone = str(generated.get("tone") or tone).strip() or tone
        if candidate.patient_label and candidate.patient_label not in headline:
            headline = f"{candidate.patient_label}{headline}"[:60]
        headline = self._trim_cn(headline, 56)
        action_hint = self._trim_cn(action_hint, 36)
        return PulseNarration(
            candidate_id=candidate_id,
            patient_id=candidate.patient_id,
            headline=headline,
            action_hint=action_hint,
            tone=tone if tone in {"info", "warn", "critical"} else "info",
            deep_link=self._deep_link(candidate),
            source=candidate.source,
            occurred_at=candidate.occurred_at.isoformat(),
            dept_code=self._candidate_dept_code(candidate, patient),
        )

    async def push_pulse(self, viewer_id: str, narration: PulseNarration, *, score: float | None = None, ws=None, candidate_type: str | None = None) -> None:
        await self._ensure_indexes()
        now = datetime.now()
        doc = {
            **asdict(narration),
            "viewer_id": viewer_id,
            "score": score,
            "pushed_at": now,
            "feedback": None,
            "feedback_at": None,
            "candidate_type": candidate_type or narration.source,
        }
        await self.db.col("pulse_events").insert_one(doc)
        payload = {"type": "pulse", "data": serialize_doc(asdict(narration))}
        if ws is not None:
            await self.ws_mgr.send_to(ws, payload)
        else:
            await self.ws_mgr.broadcast(payload)
        logger.info("[pulse] pushed viewer_id=%s candidate_id=%s score=%s", viewer_id, narration.candidate_id, score)

    async def record_feedback(self, candidate_id: str | None, action: str, viewer_id: str) -> None:
        candidate_id = str(candidate_id or "").strip()
        if not candidate_id:
            return
        if action not in {"dismiss", "click"}:
            return
        doc = await self.db.col("pulse_events").find_one({"candidate_id": candidate_id, "viewer_id": viewer_id}, sort=[("pushed_at", -1)])
        if doc:
            await self.db.col("pulse_events").update_one(
                {"_id": doc.get("_id")},
                {"$set": {"feedback": action, "feedback_at": datetime.now()}},
            )

    async def run_loop(self) -> None:
        if not self.is_enabled():
            logger.info("[pulse] disabled by config")
            return
        await self._ensure_indexes()
        interval = int(self._cfg().get("loop_interval_seconds", 30) or 30)
        lookback = int(self._cfg().get("candidate_lookback_minutes", 5) or 5)
        logger.info("[pulse] loop started interval=%ss lookback=%sm", interval, lookback)
        while not self._stop_event.is_set():
            try:
                candidates = await self.collect_candidates(datetime.now() - timedelta(minutes=lookback))
                await self._score_and_push(candidates)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[pulse] loop error: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(5, interval))
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop_event.set()

    async def _score_and_push(self, candidates: list[PulseCandidate]) -> None:
        if not candidates:
            logger.info("[pulse] scoring skipped no candidates")
            return
        threshold = float(self._cfg().get("push_threshold", self._cfg().get("threshold", 0.55)) or 0.55)
        max_per_hour = int(self._cfg().get("max_pushes_per_viewer_per_hour", 12) or 12)
        viewers = await self.ws_mgr.online_viewers()
        logger.info("[pulse] scoring candidates=%s viewers=%s threshold=%.2f", len(candidates), len(viewers), threshold)
        for ws, meta in viewers:
            viewer = self._viewer_from_meta(ws, meta)
            if not viewer.user_id:
                continue
            recent_pushes = await self.db.col("pulse_events").count_documents(
                {"viewer_id": viewer.user_id, "pushed_at": {"$gte": datetime.now() - timedelta(hours=1)}}
            )
            if recent_pushes >= max_per_hour:
                continue
            scored = []
            for candidate in candidates:
                if await self._cooldown_active(viewer.user_id, candidate):
                    continue
                score = await self.score_candidate(candidate, viewer)
                if score >= threshold:
                    scored.append((score, candidate))
            if not scored:
                continue
            score, candidate = sorted(scored, key=lambda item: item[0], reverse=True)[0]
            narration = await self.narrate(candidate)
            await self.push_pulse(viewer.user_id, narration, score=score, ws=ws, candidate_type=self._candidate_type(candidate))

    def _viewer_from_meta(self, ws, meta: dict[str, Any]) -> ViewerContext:
        roles = meta.get("roles") or []
        ctx = meta.get("viewer_context") if isinstance(meta.get("viewer_context"), dict) else {}
        role = str(ctx.get("role") or (roles[0] if roles else "") or "doctor").lower()
        return ViewerContext(
            user_id=str(ctx.get("user_id") or ws.headers.get("x-user-id") or ws.headers.get("x-user-name") or id(ws)),
            role=role,
            dept_code=str(ctx.get("dept_code") or ws.query_params.get("dept_code") or ws.headers.get("x-dept-code") or ""),
            current_patient_id=str(ctx.get("current_patient_id") or "") or None,
            current_route=str(ctx.get("current_route") or "") or None,
        )

    async def _collect_alert_candidates(self, since: datetime, now: datetime) -> list[PulseCandidate]:
        overdue_min = int(self._cfg().get("overdue_alert_minutes", 30) or 30)
        query = {
            "$or": [
                {"severity": {"$in": ["critical", "high"]}, "created_at": {"$gte": since}},
                {"severity": "high", "created_at": {"$lte": now - timedelta(minutes=overdue_min)}},
            ],
            "$and": [{"viewed": {"$ne": True}}, {"viewed_at": {"$in": [None]}}],
        }
        cursor = self.db.col("alert_records").find(query).sort("created_at", -1).limit(80)
        return [self._candidate_from_alert(doc) async for doc in cursor]

    async def _collect_score_candidates(self, since: datetime) -> list[PulseCandidate]:
        query = {
            "score_type": {"$in": ["multi_agent_mdt_assessment", "clinical_reasoning_plan"]},
            "calc_time": {"$gte": since},
        }
        cursor = self.db.col("score").find(query).sort("calc_time", -1).limit(30)
        rows = []
        async for doc in cursor:
            patient_id = str(doc.get("patient_id") or "")
            patient = await self._load_patient(patient_id)
            rows.append(
                PulseCandidate(
                    source="reasoning",
                    event_id=str(doc.get("_id")),
                    patient_id=patient_id,
                    patient_label=self._patient_label(patient, doc),
                    severity="medium",
                    raw=doc,
                    occurred_at=_parse_dt(doc.get("calc_time")) or datetime.now(),
                    owner_role="doctor",
                )
            )
        return rows

    async def _collect_lab_drug_mismatch_candidates(self, since: datetime, now: datetime) -> list[PulseCandidate]:
        if not all(hasattr(self.alert_engine, name) for name in ("_parse_susceptibility_report", "_get_current_antibiotic_courses", "_check_coverage_mismatch")):
            return []
        rows: list[PulseCandidate] = []
        antibiotic_names, _ = await self.alert_engine._load_antibiotic_dictionary()
        cursor = self.db.col("patient").find(self.alert_engine._active_patient_query(), {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "deptCode": 1}).limit(80)
        async for patient in cursor:
            his_pid = str(patient.get("hisPid") or "").strip()
            pid = str(patient.get("_id"))
            if not his_pid:
                continue
            exam = await self.db.dc_col("VI_ICU_EXAM_ITEM").find_one(
                {"hisPid": his_pid, "authTime": {"$gte": since}, "itemCnName": {"$regex": "培养|药敏|乳酸|PCT", "$options": "i"}},
                sort=[("authTime", -1)],
            )
            if not exam:
                continue
            reports = await self.alert_engine._parse_susceptibility_report(his_pid, now - timedelta(hours=24))
            drugs = await self.alert_engine._get_current_antibiotic_courses(pid, now, antibiotic_names)
            mismatches = await self.alert_engine._check_coverage_mismatch(pid, his_pid, reports, drugs)
            for idx, mismatch in enumerate(mismatches[:2]):
                rows.append(
                    PulseCandidate("lab_drug_mismatch", f"{pid}_{idx}_{exam.get('_id')}", pid, self._patient_label(patient, {}), "high", mismatch, _parse_dt(exam.get("authTime")) or now, "pharmacist")
                )
        return rows

    async def _collect_mdt_overdue_candidates(self, now: datetime) -> list[PulseCandidate]:
        overdue_min = int(self._cfg().get("overdue_mdt_minutes", 120) or 120)
        cursor = self.db.col("mdt_workspace").find(
            {"phase": {"$ne": "closed"}, "updated_at": {"$lte": now - timedelta(minutes=overdue_min)}}
        ).sort("updated_at", 1).limit(30)
        rows = []
        async for doc in cursor:
            patient_id = str(doc.get("patient_id") or "")
            patient = await self._load_patient(patient_id)
            rows.append(PulseCandidate("mdt_overdue", str(doc.get("_id")), patient_id, self._patient_label(patient, doc), "medium", doc, _parse_dt(doc.get("updated_at")) or now, "doctor"))
        return rows

    def _candidate_from_alert(self, doc: dict[str, Any]) -> PulseCandidate:
        patient_id = str(doc.get("patient_id") or "")
        return PulseCandidate(
            source="alert",
            event_id=str(doc.get("_id")),
            patient_id=patient_id,
            patient_label=self._patient_label(None, doc),
            severity=str(doc.get("severity") or "medium").lower(),
            raw=doc,
            occurred_at=_parse_dt(doc.get("created_at")) or datetime.now(),
            owner_role=self._owner_role(doc),
        )

    async def _narrate_with_llm(self, candidate: PulseCandidate) -> dict[str, Any]:
        from app.services.llm_runtime import call_llm_chat

        prompt = json.dumps(serialize_doc(asdict(candidate)), ensure_ascii=False)
        system = "你是 ICU 协同助手。把以下事件改写成一条不超过 60 字的中文播报，必须包含床号、关键数据点、一个明确动作建议。严禁编造。"
        start = AiMonitor.now_ms()
        output = ""
        success = False
        model = str(self._cfg().get("narrate_model") or "fast")
        usage = None
        try:
            res = await call_llm_chat(cfg=self.config, system_prompt=system, user_prompt=f"{prompt}\nOutput JSON: {{\"headline\": str, \"action_hint\": str, \"tone\": \"info|warn|critical\"}}", model=model, max_tokens=320, timeout_seconds=20)
            output = str(res.get("text") or "")
            usage = res.get("usage")
            model = str(res.get("model") or model)
            success = True
            return json.loads(output)
        except Exception as exc:
            output = str(exc)
            return {}
        finally:
            if self.ai_monitor:
                await self.ai_monitor.log_llm_call(module="pulse_narrate", model=model, prompt=prompt, output=output, latency_ms=AiMonitor.now_ms() - start, success=success, usage=usage, meta={"candidate_id": f"{candidate.source}_{candidate.event_id}"})

    async def _load_patient(self, patient_id: str) -> dict | None:
        try:
            return await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            return None

    def _patient_label(self, patient: dict | None, doc: dict) -> str:
        bed = str((patient or {}).get("hisBed") or doc.get("bed") or "").strip()
        name = str((patient or {}).get("name") or doc.get("patient_name") or "").strip()
        return f"{bed}床·{name}" if bed or name else "未知床位"

    @staticmethod
    def _candidate_dept_code(candidate: PulseCandidate, patient: dict | None = None) -> str:
        raw = candidate.raw if isinstance(candidate.raw, dict) else {}
        return str(
            (patient or {}).get("deptCode")
            or raw.get("deptCode")
            or raw.get("dept_code")
            or raw.get("current_dept_code")
            or ""
        ).strip()

    @staticmethod
    def _owner_role(doc: dict[str, Any]) -> str:
        category = str(doc.get("category") or "").lower()
        if "drug" in category or "antibiotic" in category:
            return "pharmacist"
        if "nurse" in category or doc.get("alert_type") == "nurse_reminder":
            return "nurse"
        if "vent" in category or "resp" in category:
            return "rt"
        return "doctor"

    @staticmethod
    def _deep_link(candidate: PulseCandidate) -> str:
        if candidate.source in {"reasoning", "mdt_overdue"}:
            return f"/patient/{candidate.patient_id}?tab=ai"
        if candidate.source == "lab_drug_mismatch":
            return f"/patient/{candidate.patient_id}?tab=drugs"
        return f"/patient/{candidate.patient_id}?tab=alerts"

    def _compact_existing_narration(self, candidate: PulseCandidate) -> dict[str, str]:
        raw = candidate.raw if isinstance(candidate.raw, dict) else {}
        extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        condition = raw.get("condition") if isinstance(raw.get("condition"), dict) else {}
        alert_type = str(raw.get("alert_type") or "").lower()
        name = str(raw.get("name") or "")
        label = candidate.patient_label

        if alert_type == "sofa" or "SOFA" in name.upper() or "脓毒症" in name:
            score = extra.get("score", condition.get("score", raw.get("value")))
            delta = extra.get("delta", condition.get("delta"))
            delta_text = f"，较基线+{delta}" if delta not in (None, "") else ""
            return {
                "headline": f"{label}SOFA {score}分{delta_text}，建议评估脓毒症",
                "action_hint": "感染源评估 / 复苏处置",
            }

        if alert_type in {"coverage_mismatch", "mdro_detected"} or "药敏" in name or "覆盖不足" in name:
            organism = str(extra.get("organism") or extra.get("mdro_type") or "").strip()
            suffix = f"{organism} " if organism else ""
            return {
                "headline": f"{label}{suffix}药敏与当前抗菌方案需复核",
                "action_hint": "复核培养药敏 / 调整抗菌药",
            }

        if "乳酸" in name or str(raw.get("parameter") or "").lower() in {"lac", "lactate"}:
            value = raw.get("value")
            value_text = f"{value}" if value not in (None, "") else "升高"
            return {
                "headline": f"{label}乳酸{value_text}，建议复评灌注",
                "action_hint": "复查血气 / 评估补液和升压药",
            }

        if "脱机" in name or "拔管" in name or "post_extubation" in alert_type:
            return {
                "headline": f"{label}{name or '呼吸风险'}，建议床旁复评",
                "action_hint": "复查血气 / 评估氧疗升级",
            }

        return {}

    @staticmethod
    def _trim_cn(text: str, limit: int) -> str:
        value = str(text or "").strip()
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 1)].rstrip("，；、。 ") + "…"

    async def _cooldown_active(self, viewer_id: str, candidate: PulseCandidate) -> bool:
        cooldown = int(self._cfg().get("cooldown_minutes_per_patient", 10) or 10)
        return bool(await self.db.col("pulse_events").find_one({
            "viewer_id": viewer_id,
            "patient_id": candidate.patient_id,
            "candidate_type": self._candidate_type(candidate),
            "pushed_at": {"$gte": datetime.now() - timedelta(minutes=cooldown)},
        }))

    @staticmethod
    def _candidate_type(candidate: PulseCandidate) -> str:
        raw = candidate.raw if isinstance(candidate.raw, dict) else {}
        return f"{candidate.source}:{raw.get('alert_type') or raw.get('rule_id') or raw.get('score_type') or candidate.source}"

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self.db.col("pulse_events").create_index([("viewer_id", 1), ("pushed_at", -1)])
        await self.db.col("pulse_events").create_index([("patient_id", 1), ("candidate_id", 1), ("pushed_at", -1)])
        self._indexes_ready = True
