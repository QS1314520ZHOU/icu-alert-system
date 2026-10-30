"""Handover — Summary Service.

Generates full-ward shift handover summaries with deterministic statistics
and optional AI-generated narrative text.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.handover.schemas import ShiftHandoverSummary
from app.services.shift_service import ShiftService
from app.utils.patient_helpers import patient_his_pid_candidates

API_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger("icu-alert")

_VASO_KEYWORDS = (
    "去甲肾上腺素", "去甲", "多巴胺", "肾上腺素", "血管加压素", "加压素",
    "去氧肾上腺素", "苯肾上腺素", "间羟胺", "多巴酚丁胺",
    "norepinephrine", "norepi", "dopamine", "epinephrine", "vasopressin",
    "phenylephrine", "dobutamine",
)
_HIGH_RISK_TUBES = (
    "中心静脉", "cvc", "picc", "动脉", "气管插管", "气管切开", "人工气道",
    "输液港", "hemodialysis", "hd管路",
)
_CRRT_KEYWORDS = ("crrt", "血滤", "血液滤过", "透析")
_VENT_DIAG_KEYWORDS = ("呼吸机", "机械通气", "气管插管", "气管切开", "ventilator")


class ShiftSummaryService:
    """Generates and manages full-ward shift handover summaries."""

    def __init__(self, db, config=None) -> None:
        self.db = db
        self.config = config

    async def generate(
        self,
        dept_code: str,
        shift_code: str = "auto",
        operator: str = "",
    ) -> ShiftHandoverSummary:
        """Generate a full-ward summary for the current shift."""
        shift_svc = ShiftService(self.db, self.config)
        resolved = await shift_svc.resolve_shift(shift_code)

        now = datetime.now(API_TZ)
        data_start = resolved.start.astimezone(API_TZ).replace(tzinfo=None)
        data_end = min(now, resolved.end).astimezone(API_TZ).replace(tzinfo=None)

        patients = await self._query_patients(dept_code)
        patient_count = len(patients)

        patient_stats = []
        critical_count = 0
        vent_count = 0
        vaso_count = 0
        crrt_count = 0
        isolation_count = 0
        high_risk_line_count = 0
        total_alerts = 0
        unclosed_alerts = 0
        critical_values = 0

        for p in patients:
            pid = str(p.get("_id", ""))
            stat = await self._patient_stat(pid, p, data_start, data_end)
            patient_stats.append(stat)

            if stat.get("is_critical"):
                critical_count += 1
            if stat.get("has_ventilator"):
                vent_count += 1
            if stat.get("has_vasoactive"):
                vaso_count += 1
            if stat.get("has_crrt"):
                crrt_count += 1
            if stat.get("isolation"):
                isolation_count += 1
            high_risk_line_count += int(stat.get("high_risk_line_count") or 0)
            total_alerts += stat.get("alert_count", 0)
            unclosed_alerts += stat.get("unclosed_alert_count", 0)
            critical_values += stat.get("critical_value_count", 0)

        handover_docs = await self._query_handovers(dept_code, data_start, data_end)
        completed = sum(1 for d in handover_docs if d.get("status") in ("submitted", "acknowledged"))
        drafts = sum(1 for d in handover_docs if d.get("status") == "draft")
        submitted = sum(1 for d in handover_docs if d.get("status") == "submitted")
        acknowledged = sum(1 for d in handover_docs if d.get("status") == "acknowledged")

        # 逐患者交班单状态（取该患者本班最新一份交班单）
        latest_by_patient: dict[str, dict[str, Any]] = {}
        for d in handover_docs:
            hpid = str(d.get("patient_id") or "")
            if not hpid:
                continue
            prev = latest_by_patient.get(hpid)
            if prev is None or str(d.get("updated_at") or d.get("created_at") or "") >= str(prev.get("updated_at") or prev.get("created_at") or ""):
                latest_by_patient[hpid] = d
        for stat in patient_stats:
            doc = latest_by_patient.get(str(stat.get("patient_id") or ""))
            stat["handover_status"] = str(doc.get("status") or "draft") if doc else "not_started"
            stat["handover_id"] = str(doc.get("handover_id") or doc.get("_id") or "") if doc else ""
            stat["handover_updated_at"] = str(doc.get("updated_at") or doc.get("created_at") or "") if doc else ""

        priority_items = self._build_priority_items(patient_stats)

        deterministic_summary = self._build_deterministic_summary(
            patient_count=patient_count,
            critical_count=critical_count,
            vent_count=vent_count,
            vaso_count=vaso_count,
            crrt_count=crrt_count,
            alert_count=total_alerts,
            unclosed_alerts=unclosed_alerts,
            high_risk_lines=high_risk_line_count,
        )

        summary = ShiftHandoverSummary(
            summary_id=str(uuid.uuid4()),
            dept_code=dept_code,
            shift_code=resolved.code,
            shift_name=resolved.name,
            scheduled_start=resolved.start.isoformat(),
            scheduled_end=resolved.end.isoformat(),
            data_start=data_start.isoformat(),
            data_end=data_end.isoformat(),
            patient_count=patient_count,
            completed_patient_count=completed,
            draft_patient_count=drafts,
            submitted_patient_count=submitted,
            acknowledged_patient_count=acknowledged,
            critical_patient_count=critical_count,
            high_priority_alert_count=total_alerts,
            unclosed_alert_count=unclosed_alerts,
            critical_value_count=critical_values,
            vasoactive_patient_count=vaso_count,
            ventilator_patient_count=vent_count,
            crrt_patient_count=crrt_count,
            isolation_patient_count=isolation_count,
            high_risk_line_count=high_risk_line_count,
            patients=patient_stats,
            priority_items=priority_items,
            deterministic_summary=deterministic_summary,
            # 医嘱执行/护理任务计数尚未接入本服务，显式标记，避免前端把 0 当成"无待办"
            missing_sources=["orders", "tasks"],
            status="draft",
            created_by=operator,
            created_at=datetime.now(API_TZ).isoformat(),
        )

        try:
            doc_dict = summary.model_dump()
            doc_dict["_created"] = datetime.now(API_TZ).isoformat()
            await self.db.col("shift_handover_summaries").insert_one(doc_dict)
        except Exception as exc:
            logger.warning("Failed to persist shift summary: %s", exc)

        return summary

    async def _query_patients(self, dept_code: str) -> list[dict[str, Any]]:
        """Query active patients in the department."""
        filters: list[dict[str, Any]] = [
            {
                "$or": [
                    {"status": {"$nin": ["discharged", "invalid", "invaild"]}},
                    {"status": {"$exists": False}},
                    {"status": None},
                    {"status": ""},
                ]
            }
        ]
        if dept_code:
            filters.append({
                "$or": [
                    {"deptCode": dept_code},
                    {"dept_code": dept_code},
                    {"departmentCode": dept_code},
                    {"hisDeptCode": dept_code},
                ]
            })
        query: dict[str, Any] = {"$and": filters} if len(filters) > 1 else filters[0]
        cursor = self.db.col("patient").find(query)
        return await cursor.to_list(length=500)

    async def _patient_stat(
        self, pid: str, p: dict, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Build statistics for a single patient."""
        from app.utils.serialization import safe_oid

        oid = safe_oid(pid)
        _ = patient_his_pid_candidates(p)

        bed = str(p.get("hisBed") or p.get("showBed") or p.get("bed") or p.get("bedNo") or "")
        name = str(p.get("name") or p.get("hisName") or "")
        diagnosis = str(
            p.get("clinicalDiagnosis")
            or p.get("diagnosis")
            or p.get("diagnose")
            or p.get("admissionDiagnosis")
            or p.get("hisDiagnosis")
            or ""
        )
        isolation = str(p.get("isolation") or p.get("isolationType") or "")

        has_vent = await self._detect_ventilator(pid, oid, p)
        alert_count, unclosed, crit_vals, has_unclosed_high = await self._detect_alerts(
            pid, oid, start, end
        )
        has_vaso = await self._detect_vasoactive(pid, oid, start, end)
        has_crrt, high_risk_lines = await self._detect_devices(pid, oid)

        is_critical = (
            crit_vals > 0
            or has_unclosed_high
            or (unclosed > 2 and (has_vent or has_vaso or has_crrt))
        )
        # 风险判定依据：与下方分级规则一一对应，供前端展示"为什么是这个等级"
        risk_reasons: list[str] = []
        if crit_vals > 0:
            risk_reasons.append(f"本班危急值{crit_vals}条")
        if has_unclosed_high:
            risk_reasons.append("存在未闭环高危/危急告警")
        if unclosed > 2 and (has_vent or has_vaso or has_crrt):
            risk_reasons.append(f"生命支持中且未闭环告警{unclosed}条(>2)")
        if has_vaso:
            risk_reasons.append("使用血管活性药")
        if has_crrt:
            risk_reasons.append("CRRT治疗中")
        if unclosed > 0 and not (unclosed > 2 and (has_vent or has_vaso or has_crrt)):
            risk_reasons.append(f"未闭环告警{unclosed}条")
        if has_vent:
            risk_reasons.append("机械通气中")
        if high_risk_lines > 0:
            risk_reasons.append(f"高危管路{high_risk_lines}条")

        if is_critical:
            risk_level = "critical"
        elif has_vaso or has_crrt or unclosed > 0:
            risk_level = "high"
        elif has_vent or high_risk_lines > 0:
            risk_level = "medium"
        else:
            risk_level = "stable"

        return {
            "patient_id": pid,
            "bed": bed,
            "name": name,
            "diagnosis": diagnosis,
            "isolation": isolation,
            "is_critical": is_critical,
            "risk_level": risk_level,
            "has_ventilator": has_vent,
            "has_vasoactive": has_vaso,
            "has_crrt": has_crrt,
            "alert_count": alert_count,
            "unclosed_alert_count": unclosed,
            "critical_value_count": crit_vals,
            "high_risk_line_count": high_risk_lines,
            "risk_reasons": risk_reasons,
            "risk_rule": "危急: 危急值>0 或 未闭环高危告警 或 (生命支持且未闭环告警>2)；高危: 血管活性药/CRRT/未闭环告警；中危: 机械通气/高危管路",
        }

    async def _detect_ventilator(self, pid: str, oid: Any, p: dict) -> bool:
        """Detect mechanical ventilation from deviceBind / diagnosis tags."""
        try:
            bind = await self.db.col("deviceBind").find_one({
                "unBindTime": None,
                "$or": [{"pid": pid}, {"patientId": pid}, {"patient_id": pid}],
                "type": {"$regex": "vent|呼吸", "$options": "i"},
            })
            if bind:
                return True
            if oid is not None:
                bind = await self.db.col("deviceBind").find_one({
                    "unBindTime": None,
                    "$or": [{"pid": oid}, {"patientId": oid}, {"patient_id": oid}],
                    "type": {"$regex": "vent|呼吸", "$options": "i"},
                })
                if bind:
                    return True
        except Exception:
            pass

        haystack = " ".join([
            str(p.get("clinicalDiagnosis") or ""),
            str(p.get("diagnosis") or ""),
            str(p.get("admissionDiagnosis") or ""),
            str(p.get("clinicalTags") or ""),
        ]).lower()
        return any(kw in haystack for kw in _VENT_DIAG_KEYWORDS)

    async def _detect_alerts(
        self, pid: str, oid: Any, start: datetime, end: datetime
    ) -> tuple[int, int, int, bool]:
        """Return (alert_count, unclosed, critical_values, has_unclosed_high)."""
        alert_count = 0
        unclosed = 0
        crit_vals = 0
        has_unclosed_high = False
        try:
            pid_or = {"$or": [{"patient_id": oid}, {"patient_id": pid}]} if oid is not None else {"patient_id": pid}
            alerts = await self.db.col("alert_records").find({
                **pid_or,
                "created_at": {"$gte": start, "$lte": end},
            }).to_list(length=100)
            alert_count = len(alerts)
            for a in alerts:
                closed = bool(a.get("acknowledged_at") or a.get("ack_disposition") or a.get("status") in ("closed", "resolved"))
                severity = str(a.get("severity") or a.get("priority") or "").lower()
                is_high = severity in ("critical", "high", "p0", "p1", "危急", "高")
                is_critical_sev = severity in ("critical", "p0", "危急")
                if not closed:
                    unclosed += 1
                    if is_high:
                        has_unclosed_high = True
                if is_critical_sev:
                    crit_vals += 1
        except Exception:
            pass
        return alert_count, unclosed, crit_vals, has_unclosed_high

    async def _detect_vasoactive(self, pid: str, oid: Any, start: datetime, end: datetime) -> bool:
        """Detect vasoactive drugs from drugExe.drugList."""
        try:
            pid_clause = {"$or": [{"pid": pid}, {"patient_id": pid}]} if oid is None else {
                "$or": [{"pid": pid}, {"patient_id": pid}, {"pid": oid}, {"patient_id": oid}]
            }
            meds = await self.db.col("drugExe").find({
                "$and": [
                    pid_clause,
                    {
                        "$or": [
                            {"orderTime": {"$gte": start, "$lte": end}},
                            {"startTime": {"$gte": start, "$lte": end}},
                            {"createdTime": {"$gte": start, "$lte": end}},
                        ]
                    },
                ],
            }).to_list(length=80)
            for m in meds:
                names = [
                    str((item or {}).get("name") or "").lower()
                    for item in (m.get("drugList") or [])
                ]
                names.append(str(m.get("drugName") or m.get("name") or "").lower())
                if any(kw in " ".join(names) for kw in _VASO_KEYWORDS):
                    return True
        except Exception:
            pass
        return False

    async def _detect_devices(self, pid: str, oid: Any) -> tuple[bool, int]:
        """Return (has_crrt, high_risk_line_count) from tubeExe."""
        has_crrt = False
        high_risk_lines = 0
        try:
            pid_clause = {"$or": [{"pid": pid}]} if oid is None else {"$or": [{"pid": pid}, {"pid": oid}]}
            tubes = await self.db.col("tubeExe").find({
                "$and": [
                    pid_clause,
                    {"$or": [{"valid": {"$ne": False}}, {"valid": {"$exists": False}}]},
                ],
            }).to_list(length=80)
            for t in tubes:
                label = f"{t.get('name') or ''} {t.get('type') or ''}".lower()
                if any(kw in label for kw in _CRRT_KEYWORDS):
                    has_crrt = True
                if any(kw in label for kw in _HIGH_RISK_TUBES):
                    high_risk_lines += 1
        except Exception:
            pass
        return has_crrt, high_risk_lines

    async def _query_handovers(
        self, dept_code: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Query handover documents for the dept and time range."""
        query: dict[str, Any] = {
            "time_window.start": {"$gte": start.isoformat()},
        }
        if dept_code:
            query["$or"] = [
                {"shift.dept_code": dept_code},
                {"dept_code": dept_code},
            ]
        try:
            cursor = self.db.col("handover_documents").find(query)
            return await cursor.to_list(length=500)
        except Exception:
            return []

    def _build_priority_items(self, patient_stats: list[dict]) -> list[dict[str, Any]]:
        """Build priority items sorted by severity."""
        items = []
        for p in patient_stats:
            if p.get("is_critical"):
                reason_parts = []
                if p.get("critical_value_count"):
                    reason_parts.append(f"危急告警{p.get('critical_value_count')}条")
                if p.get("unclosed_alert_count"):
                    reason_parts.append(f"未闭环{p.get('unclosed_alert_count')}条")
                items.append({
                    "patient_id": p["patient_id"],
                    "bed": p["bed"],
                    "name": p["name"],
                    "reason": "、".join(reason_parts) or "危急患者",
                    "severity": "critical",
                })
            elif p.get("has_vasoactive") or p.get("has_crrt"):
                items.append({
                    "patient_id": p["patient_id"],
                    "bed": p["bed"],
                    "name": p["name"],
                    "reason": "使用血管活性药/CRRT" if p.get("has_crrt") and p.get("has_vasoactive") else (
                        "使用CRRT" if p.get("has_crrt") else "使用血管活性药"
                    ),
                    "severity": "high",
                })
            elif p.get("has_ventilator"):
                items.append({
                    "patient_id": p["patient_id"],
                    "bed": p["bed"],
                    "name": p["name"],
                    "reason": "机械通气中",
                    "severity": "high",
                })
            elif p.get("unclosed_alert_count", 0) > 0:
                items.append({
                    "patient_id": p["patient_id"],
                    "bed": p["bed"],
                    "name": p["name"],
                    "reason": f"未闭环告警{p['unclosed_alert_count']}条",
                    "severity": "medium",
                })

        severity_order = {"critical": 0, "high": 1, "medium": 2}
        items.sort(key=lambda x: severity_order.get(x.get("severity", ""), 99))
        return items[:80]

    def _build_deterministic_summary(
        self,
        patient_count: int,
        critical_count: int,
        vent_count: int,
        vaso_count: int,
        crrt_count: int,
        alert_count: int,
        unclosed_alerts: int,
        high_risk_lines: int,
    ) -> str:
        details: list[str] = [f"本班共管理{patient_count}名患者"]
        if critical_count:
            details.append(f"其中危急患者{critical_count}名")
        if vent_count:
            details.append(f"{vent_count}名患者使用有创机械通气")
        if vaso_count:
            details.append(f"{vaso_count}名患者使用血管活性药")
        if crrt_count:
            details.append(f"{crrt_count}名患者使用CRRT")
        if high_risk_lines:
            details.append(f"高风险管路{high_risk_lines}条")
        if alert_count:
            details.append(f"本班告警{alert_count}条")
        if unclosed_alerts:
            details.append(f"其中未闭环{unclosed_alerts}条")
        return "；".join(details) + "。"
