from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.utils.serialization import safe_oid

CASE_STATUSES = {"candidate", "active", "paused", "closed"}
TASK_STATUSES = {"open", "in_progress", "completed", "cancelled"}
REFERRAL_STATUSES = {"pending", "accepted", "scheduled", "completed", "rejected", "cancelled"}


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"


def _now(value: datetime | None = None) -> datetime:
    return value if isinstance(value, datetime) else datetime.now()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _patient_snapshot(patient_doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient_id": str(patient_doc.get("_id") or ""),
        "patient_name": patient_doc.get("name") or patient_doc.get("hisName") or "",
        "bed": patient_doc.get("hisBed") or patient_doc.get("bed") or "",
        "dept": patient_doc.get("hisDept") or patient_doc.get("dept") or "",
        "his_pid": patient_doc.get("hisPid") or patient_doc.get("hisPID") or "",
        "clinical_diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or patient_doc.get("hisDiagnose") or "",
    }


def _assessment_qualifies(assessment: dict[str, Any] | None) -> bool:
    if not isinstance(assessment, dict):
        return False
    severity = _text(assessment.get("severity")).lower()
    if severity in {"warning", "high", "critical"}:
        return True
    try:
        overall = float(assessment.get("overall_score") or 0.0)
    except Exception:
        overall = 0.0
    return overall >= 45.0 or bool(assessment.get("transfer_candidate"))


def _priority_from_assessment(assessment: dict[str, Any] | None) -> str:
    if not isinstance(assessment, dict):
        return "medium"
    severity = _text(assessment.get("severity")).lower()
    try:
        overall = float(assessment.get("overall_score") or 0.0)
    except Exception:
        overall = 0.0
    if severity in {"critical", "high"} or overall >= 75:
        return "high"
    if severity == "warning" or overall >= 55:
        return "medium"
    return "low"


def _case_stage(case_doc: dict[str, Any], task_rows: list[dict[str, Any]], referral_rows: list[dict[str, Any]]) -> str:
    open_tasks = [row for row in task_rows if _text(row.get("status")).lower() in {"open", "in_progress"}]
    active_referrals = [row for row in referral_rows if _text(row.get("status")).lower() in {"pending", "accepted", "scheduled"}]
    if active_referrals:
        return "rehab_referred"
    if open_tasks:
        return "task_in_progress"
    return _text(case_doc.get("stage")) or "task_ready"


class FollowupService:
    def __init__(self, *, db, config: Any | None = None) -> None:
        self.db = db
        self.config = config

    async def list_followup_cases(
        self,
        *,
        status: str | None = None,
        source_module: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if _text(status):
            query["status"] = _text(status).lower()
        if _text(source_module):
            query["source_module"] = _text(source_module).lower()
        cursor = self.db.col("followup_cases").find(query).sort("updated_at", -1).limit(max(1, min(limit, 200)))
        return [doc async for doc in cursor]

    async def get_patient_followup_case(self, patient_id: str) -> dict[str, Any] | None:
        return await self.db.col("followup_cases").find_one({"patient_id": str(patient_id)}, sort=[("updated_at", -1)])

    async def latest_pics_record(self, patient_id: str) -> dict[str, Any] | None:
        return await self.db.col("score").find_one(
            {"patient_id": str(patient_id), "score_type": "pics_risk_assessment"},
            sort=[("calc_time", -1)],
        )

    async def ensure_case_from_latest_pics(self, *, patient_doc: dict[str, Any]) -> dict[str, Any] | None:
        patient_id = str(patient_doc.get("_id") or "")
        if not patient_id:
            return None
        latest = await self.latest_pics_record(patient_id)
        existing = await self.get_patient_followup_case(patient_id)
        if not latest:
            return existing
        assessment = latest.get("assessment") if isinstance(latest.get("assessment"), dict) else {}
        if existing or _assessment_qualifies(assessment):
            return await self.sync_case_from_pics(
                patient_doc=patient_doc,
                assessment=assessment,
                risk_record_id=latest.get("_id"),
                now=latest.get("updated_at") or latest.get("calc_time") or datetime.now(),
            )
        return existing

    async def enroll_case(
        self,
        *,
        patient_doc: dict[str, Any],
        source_module: str = "pics_risk",
        actor: str = "",
        note: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        now = _now(now)
        source = _text(source_module).lower() or "pics_risk"
        if source == "pics_risk":
            latest = await self.latest_pics_record(str(patient_doc.get("_id") or ""))
            assessment = (latest or {}).get("assessment") if isinstance((latest or {}).get("assessment"), dict) else {}
            if latest and (_assessment_qualifies(assessment) or await self.get_patient_followup_case(str(patient_doc.get("_id") or ""))):
                return await self.sync_case_from_pics(
                    patient_doc=patient_doc,
                    assessment=assessment,
                    risk_record_id=latest.get("_id"),
                    now=now,
                )
            return None

        existing = await self.db.col("followup_cases").find_one(
            {"patient_id": str(patient_doc.get("_id") or ""), "source_module": source},
            sort=[("updated_at", -1)],
        )
        snapshot = _patient_snapshot(patient_doc)
        if existing:
            updates = {
                **snapshot,
                "status": _text(existing.get("status")).lower() or "candidate",
                "stage": _text(existing.get("stage")) or "pool_enrolled",
                "updated_at": now,
            }
            if actor:
                updates["last_actor"] = actor
            if note:
                updates["note"] = note
            await self.db.col("followup_cases").update_one({"_id": existing.get("_id")}, {"$set": updates})
            existing.update(updates)
            await self._update_patient_followup_snapshot(patient_id=snapshot["patient_id"], case_doc=existing, now=now)
            return existing

        doc = {
            **snapshot,
            "case_id": _gen_id("fu_case"),
            "source_module": source,
            "status": "candidate",
            "priority": "medium",
            "stage": "pool_enrolled",
            "latest_assessment": None,
            "note": note,
            "created_by": actor,
            "last_actor": actor,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.col("followup_cases").insert_one(doc)
        doc["_id"] = result.inserted_id
        await self._update_patient_followup_snapshot(patient_id=snapshot["patient_id"], case_doc=doc, now=now)
        return doc

    async def sync_case_from_pics(
        self,
        *,
        patient_doc: dict[str, Any],
        assessment: dict[str, Any],
        risk_record_id: Any = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        now = _now(now)
        patient_id = str(patient_doc.get("_id") or "")
        if not patient_id:
            return None
        existing = await self.db.col("followup_cases").find_one(
            {"patient_id": patient_id, "source_module": "pics_risk"},
            sort=[("updated_at", -1)],
        )
        if not existing and not _assessment_qualifies(assessment):
            return None

        snapshot = _patient_snapshot(patient_doc)
        latest_assessment = {
            "overall_score": assessment.get("overall_score"),
            "severity": assessment.get("severity"),
            "summary": assessment.get("summary"),
            "suggestion": assessment.get("suggestion"),
            "transfer_candidate": bool(assessment.get("transfer_candidate")),
            "icu_days": assessment.get("icu_days"),
            "dimensions": assessment.get("dimensions") if isinstance(assessment.get("dimensions"), dict) else {},
            "evidence": assessment.get("evidence") if isinstance(assessment.get("evidence"), list) else [],
            "risk_record_id": risk_record_id,
            "updated_at": now,
        }
        priority = _priority_from_assessment(assessment)
        if existing:
            updates = {
                **snapshot,
                "priority": priority,
                "latest_assessment": latest_assessment,
                "updated_at": now,
                "stage": _text(existing.get("stage")) or "task_ready",
            }
            if not _text(existing.get("status")):
                updates["status"] = "candidate"
            await self.db.col("followup_cases").update_one({"_id": existing.get("_id")}, {"$set": updates})
            existing.update(updates)
            await self._update_patient_followup_snapshot(patient_id=patient_id, case_doc=existing, now=now)
            return existing

        doc = {
            **snapshot,
            "case_id": _gen_id("fu_case"),
            "source_module": "pics_risk",
            "status": "candidate",
            "priority": priority,
            "stage": "task_ready",
            "latest_assessment": latest_assessment,
            "created_by": "system:pics_risk",
            "last_actor": "system:pics_risk",
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.col("followup_cases").insert_one(doc)
        doc["_id"] = result.inserted_id
        await self._update_patient_followup_snapshot(patient_id=patient_id, case_doc=doc, now=now)
        return doc

    async def update_case_status(self, case_id: str, *, status: str, actor: str = "", note: str = "", now: datetime | None = None) -> dict[str, Any]:
        normalized_status = _text(status).lower()
        if normalized_status not in CASE_STATUSES:
            raise ValueError("随访案状态仅支持 candidate / active / paused / closed")
        case_doc = await self._find_by_business_id("followup_cases", "case_id", case_id)
        if not case_doc:
            raise ValueError("随访案不存在")
        now = _now(now)
        updates = {"status": normalized_status, "updated_at": now}
        if actor:
            updates["last_actor"] = actor
        if note:
            updates["note"] = note
        if normalized_status == "closed":
            updates["closed_at"] = now
        await self.db.col("followup_cases").update_one({"_id": case_doc.get("_id")}, {"$set": updates})
        case_doc.update(updates)
        await self._update_patient_followup_snapshot(patient_id=str(case_doc.get("patient_id") or ""), case_doc=case_doc, now=now)
        return case_doc

    async def list_followup_tasks(
        self,
        *,
        patient_id: str | None = None,
        case_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if _text(patient_id):
            query["patient_id"] = _text(patient_id)
        if _text(case_id):
            query["case_id"] = _text(case_id)
        if _text(status):
            query["status"] = _text(status).lower()
        cursor = self.db.col("followup_tasks").find(query).sort("created_at", -1).limit(max(1, min(limit, 200)))
        return [doc async for doc in cursor]

    async def create_followup_task(
        self,
        *,
        patient_doc: dict[str, Any],
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        now = _now(now)
        patient_id = str(patient_doc.get("_id") or "")
        if not patient_id:
            raise ValueError("缺少患者ID")
        case_doc = await self.get_patient_followup_case(patient_id)
        if not case_doc:
            case_doc = await self.ensure_case_from_latest_pics(patient_doc=patient_doc)
        if not case_doc:
            raise ValueError("未找到可用的长期随访案，请先生成或刷新 PICS 风险评估")

        template_key = _text(payload.get("template_key")).lower()
        existing = None
        if template_key:
            existing = await self.db.col("followup_tasks").find_one(
                {
                    "patient_id": patient_id,
                    "template_key": template_key,
                    "status": {"$in": ["open", "in_progress"]},
                },
                sort=[("created_at", -1)],
            )
        if existing:
            return existing

        defaults = self._task_defaults(template_key=template_key, case_doc=case_doc, now=now)
        due_at = _parse_datetime(payload.get("due_at")) or defaults.get("due_at")
        doc = {
            "task_id": _gen_id("fu_task"),
            "case_id": case_doc.get("case_id"),
            "patient_id": patient_id,
            "patient_name": case_doc.get("patient_name") or patient_doc.get("name") or "",
            "title": _text(payload.get("title")) or defaults["title"],
            "description": _text(payload.get("description")) or defaults["description"],
            "category": _text(payload.get("category")) or defaults["category"],
            "template_key": template_key or defaults.get("template_key"),
            "priority": _text(payload.get("priority")).lower() or defaults["priority"],
            "status": "open",
            "owner": _text(payload.get("owner")),
            "created_by": _text(payload.get("actor")),
            "note": _text(payload.get("note")),
            "due_at": due_at,
            "risk_snapshot": case_doc.get("latest_assessment"),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.col("followup_tasks").insert_one(doc)
        doc["_id"] = result.inserted_id
        await self._promote_case(case_doc=case_doc, now=now, actor=_text(payload.get("actor")), stage="task_in_progress", last_task=True)
        return doc

    async def update_followup_task_status(
        self,
        task_id: str,
        *,
        status: str,
        actor: str = "",
        note: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_status = _text(status).lower()
        if normalized_status not in TASK_STATUSES:
            raise ValueError("任务状态仅支持 open / in_progress / completed / cancelled")
        task_doc = await self._find_by_business_id("followup_tasks", "task_id", task_id)
        if not task_doc:
            raise ValueError("随访任务不存在")
        now = _now(now)
        updates = {"status": normalized_status, "updated_at": now}
        if actor:
            updates["last_actor"] = actor
        if note:
            updates["note"] = note
        if normalized_status == "completed":
            updates["completed_at"] = now
        await self.db.col("followup_tasks").update_one({"_id": task_doc.get("_id")}, {"$set": updates})
        task_doc.update(updates)
        await self._refresh_case_stage(patient_id=str(task_doc.get("patient_id") or ""), now=now)
        return task_doc

    async def list_rehab_referrals(
        self,
        *,
        patient_id: str | None = None,
        case_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if _text(patient_id):
            query["patient_id"] = _text(patient_id)
        if _text(case_id):
            query["case_id"] = _text(case_id)
        if _text(status):
            query["status"] = _text(status).lower()
        cursor = self.db.col("rehab_referrals").find(query).sort("created_at", -1).limit(max(1, min(limit, 200)))
        return [doc async for doc in cursor]

    async def create_rehab_referral(
        self,
        *,
        patient_doc: dict[str, Any],
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        now = _now(now)
        patient_id = str(patient_doc.get("_id") or "")
        if not patient_id:
            raise ValueError("缺少患者ID")
        case_doc = await self.get_patient_followup_case(patient_id)
        if not case_doc:
            case_doc = await self.ensure_case_from_latest_pics(patient_doc=patient_doc)
        if not case_doc:
            raise ValueError("未找到可用的长期随访案，请先生成或刷新 PICS 风险评估")

        template_key = _text(payload.get("template_key")).lower()
        existing = None
        if template_key:
            existing = await self.db.col("rehab_referrals").find_one(
                {
                    "patient_id": patient_id,
                    "template_key": template_key,
                    "status": {"$in": ["pending", "accepted", "scheduled"]},
                },
                sort=[("created_at", -1)],
            )
        if existing:
            return existing

        defaults = self._referral_defaults(template_key=template_key, case_doc=case_doc)
        scheduled_at = _parse_datetime(payload.get("scheduled_at"))
        status = _text(payload.get("status")).lower() or defaults["status"]
        if status not in REFERRAL_STATUSES:
            status = defaults["status"]
        doc = {
            "referral_id": _gen_id("rehab_ref"),
            "case_id": case_doc.get("case_id"),
            "patient_id": patient_id,
            "patient_name": case_doc.get("patient_name") or patient_doc.get("name") or "",
            "template_key": template_key or defaults.get("template_key"),
            "referral_type": _text(payload.get("referral_type")) or defaults["referral_type"],
            "target_service": _text(payload.get("target_service")) or defaults["target_service"],
            "reason": _text(payload.get("reason")) or defaults["reason"],
            "recommendation": _text(payload.get("recommendation")) or defaults["recommendation"],
            "status": status,
            "requested_by": _text(payload.get("actor")),
            "owner": _text(payload.get("owner")),
            "scheduled_at": scheduled_at,
            "note": _text(payload.get("note")),
            "risk_snapshot": case_doc.get("latest_assessment"),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.col("rehab_referrals").insert_one(doc)
        doc["_id"] = result.inserted_id
        await self._promote_case(case_doc=case_doc, now=now, actor=_text(payload.get("actor")), stage="rehab_referred", last_referral=True)
        return doc

    async def update_rehab_referral_status(
        self,
        referral_id: str,
        *,
        status: str,
        actor: str = "",
        note: str = "",
        scheduled_at: Any = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_status = _text(status).lower()
        if normalized_status not in REFERRAL_STATUSES:
            raise ValueError("转介状态仅支持 pending / accepted / scheduled / completed / rejected / cancelled")
        referral_doc = await self._find_by_business_id("rehab_referrals", "referral_id", referral_id)
        if not referral_doc:
            raise ValueError("康复转介不存在")
        now = _now(now)
        updates = {"status": normalized_status, "updated_at": now}
        if actor:
            updates["last_actor"] = actor
        if note:
            updates["note"] = note
        parsed_schedule = _parse_datetime(scheduled_at)
        if parsed_schedule:
            updates["scheduled_at"] = parsed_schedule
        if normalized_status == "completed":
            updates["completed_at"] = now
        await self.db.col("rehab_referrals").update_one({"_id": referral_doc.get("_id")}, {"$set": updates})
        referral_doc.update(updates)
        await self._refresh_case_stage(patient_id=str(referral_doc.get("patient_id") or ""), now=now)
        return referral_doc

    async def build_patient_overview(self, *, patient_id: str) -> dict[str, Any]:
        case_doc = await self.get_patient_followup_case(patient_id)
        tasks = await self.list_followup_tasks(patient_id=patient_id, limit=100)
        referrals = await self.list_rehab_referrals(patient_id=patient_id, limit=100)
        case_summary = {
            "open_tasks": sum(1 for row in tasks if _text(row.get("status")).lower() in {"open", "in_progress"}),
            "completed_tasks": sum(1 for row in tasks if _text(row.get("status")).lower() == "completed"),
            "pending_referrals": sum(1 for row in referrals if _text(row.get("status")).lower() in {"pending", "accepted", "scheduled"}),
            "completed_referrals": sum(1 for row in referrals if _text(row.get("status")).lower() == "completed"),
        }
        if case_doc:
            case_doc = dict(case_doc)
            case_doc["stage"] = _case_stage(case_doc, tasks, referrals)
        return {
            "case": case_doc,
            "tasks": tasks,
            "referrals": referrals,
            "summary": case_summary,
        }

    def _task_defaults(self, *, template_key: str, case_doc: dict[str, Any], now: datetime) -> dict[str, Any]:
        risk = case_doc.get("latest_assessment") or {}
        summary = _text(risk.get("summary")) or "基于住院期 PICS 风险识别结果，建立长期随访任务。"
        defaults: dict[str, dict[str, Any]] = {
            "pics_7d_call": {
                "template_key": "pics_7d_call",
                "title": "PICS 7天电话随访",
                "description": f"{summary} 建议在出院后 7 天内确认睡眠、焦虑、活动能力和家属照护问题。",
                "category": "telephone_followup",
                "priority": "high" if _priority_from_assessment(risk) == "high" else "medium",
                "due_at": now + timedelta(days=7),
            },
            "pics_30d_clinic": {
                "template_key": "pics_30d_clinic",
                "title": "PICS 30天门诊/视频复评",
                "description": "安排出院后 30 天门诊或视频复评，联合复核身体、认知和心理恢复情况。",
                "category": "clinic_followup",
                "priority": "medium",
                "due_at": now + timedelta(days=30),
            },
            "pics_screening": {
                "template_key": "pics_screening",
                "title": "PICS 量表筛查补录",
                "description": "补录功能、认知、睡眠/焦虑相关量表，形成长期随访基线。",
                "category": "screening",
                "priority": "medium",
                "due_at": now + timedelta(days=14),
            },
        }
        return defaults.get(
            template_key,
            {
                "template_key": template_key or "manual",
                "title": "PICS 长期随访任务",
                "description": summary or "长期随访任务",
                "category": "followup",
                "priority": _priority_from_assessment(risk),
                "due_at": now + timedelta(days=7),
            },
        )

    def _referral_defaults(self, *, template_key: str, case_doc: dict[str, Any]) -> dict[str, Any]:
        risk = case_doc.get("latest_assessment") or {}
        summary = _text(risk.get("summary")) or "住院期存在 PICS 风险。"
        suggestion = _text(risk.get("suggestion")) or "建议进入康复评估闭环。"
        defaults: dict[str, dict[str, Any]] = {
            "pics_rehab": {
                "template_key": "pics_rehab",
                "referral_type": "comprehensive_rehab",
                "target_service": "康复医学科 / ICU康复治疗师",
                "reason": summary,
                "recommendation": suggestion,
                "status": "pending",
            },
            "pics_psychology": {
                "template_key": "pics_psychology",
                "referral_type": "psychology_support",
                "target_service": "心理支持 / 睡眠门诊",
                "reason": summary,
                "recommendation": "针对焦虑、睡眠障碍或创伤后表现进行进一步评估。",
                "status": "pending",
            },
        }
        return defaults.get(
            template_key,
            {
                "template_key": template_key or "manual",
                "referral_type": "rehabilitation",
                "target_service": "康复医学科",
                "reason": summary,
                "recommendation": suggestion,
                "status": "pending",
            },
        )

    async def _promote_case(
        self,
        *,
        case_doc: dict[str, Any],
        now: datetime,
        actor: str = "",
        stage: str,
        last_task: bool = False,
        last_referral: bool = False,
    ) -> None:
        updates = {
            "status": "active" if _text(case_doc.get("status")).lower() != "closed" else "closed",
            "stage": stage,
            "updated_at": now,
        }
        if actor:
            updates["last_actor"] = actor
        if last_task:
            updates["last_task_created_at"] = now
        if last_referral:
            updates["last_referral_created_at"] = now
        await self.db.col("followup_cases").update_one({"_id": case_doc.get("_id")}, {"$set": updates})
        case_doc.update(updates)
        await self._update_patient_followup_snapshot(patient_id=str(case_doc.get("patient_id") or ""), case_doc=case_doc, now=now)

    async def _refresh_case_stage(self, *, patient_id: str, now: datetime) -> None:
        case_doc = await self.get_patient_followup_case(patient_id)
        if not case_doc:
            return
        tasks = await self.list_followup_tasks(patient_id=patient_id, limit=100)
        referrals = await self.list_rehab_referrals(patient_id=patient_id, limit=100)
        updates = {
            "stage": _case_stage(case_doc, tasks, referrals),
            "updated_at": now,
        }
        await self.db.col("followup_cases").update_one({"_id": case_doc.get("_id")}, {"$set": updates})
        case_doc.update(updates)
        await self._update_patient_followup_snapshot(patient_id=patient_id, case_doc=case_doc, now=now)

    async def _update_patient_followup_snapshot(self, *, patient_id: str, case_doc: dict[str, Any], now: datetime) -> None:
        pid = safe_oid(patient_id)
        selector = {"_id": pid} if pid is not None else {"_id": patient_id}
        snapshot = {
            "case_id": case_doc.get("case_id"),
            "status": case_doc.get("status"),
            "stage": case_doc.get("stage"),
            "priority": case_doc.get("priority"),
            "source_module": case_doc.get("source_module"),
            "latest_severity": ((case_doc.get("latest_assessment") or {}) if isinstance(case_doc.get("latest_assessment"), dict) else {}).get("severity"),
            "updated_at": now,
        }
        await self.db.col("patient").update_one(selector, {"$set": {"current_profile.followup_case": snapshot}})

    async def _find_by_business_id(self, collection_name: str, field_name: str, raw_id: str) -> dict[str, Any] | None:
        clauses = [{field_name: _text(raw_id)}]
        oid = safe_oid(raw_id)
        if oid is not None:
            clauses.append({"_id": oid})
        query = clauses[0] if len(clauses) == 1 else {"$or": clauses}
        return await self.db.col(collection_name).find_one(query)
