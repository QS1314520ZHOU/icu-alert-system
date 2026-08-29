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
        """Generate a full-ward summary for the current shift.

        1. Resolve shift time window
        2. Query all patients in dept
        3. Aggregate statistics
        4. Build deterministic summary text
        5. (Optional) Call AI for narrative enhancement
        """
        shift_svc = ShiftService(self.db, self.config)
        resolved = await shift_svc.resolve_shift(shift_code)

        now = datetime.now(API_TZ)
        data_start = resolved.start.astimezone(API_TZ).replace(tzinfo=None)
        data_end = min(now, resolved.end).astimezone(API_TZ).replace(tzinfo=None)

        # Query patients
        patients = await self._query_patients(dept_code)
        patient_count = len(patients)

        # Build per-patient stats
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
            high_risk_line_count += stat.get("high_risk_line_count", 0)
            total_alerts += stat.get("alert_count", 0)
            unclosed_alerts += stat.get("unclosed_alert_count", 0)
            critical_values += stat.get("critical_value_count", 0)

        # Check handover documents for completion status
        handover_docs = await self._query_handovers(dept_code, data_start, data_end)
        completed = sum(1 for d in handover_docs if d.get("status") in ("submitted", "acknowledged"))
        drafts = sum(1 for d in handover_docs if d.get("status") == "draft")
        submitted = sum(1 for d in handover_docs if d.get("status") == "submitted")
        acknowledged = sum(1 for d in handover_docs if d.get("status") == "acknowledged")

        # Build priority items
        priority_items = self._build_priority_items(patient_stats)

        # Build deterministic summary
        deterministic_summary = self._build_deterministic_summary(
            patient_count=patient_count,
            critical_count=critical_count,
            vent_count=vent_count,
            vaso_count=vaso_count,
            crrt_count=crrt_count,
            alert_count=total_alerts,
            unclosed_alerts=unclosed_alerts,
            priority_items=priority_items,
            shift_name=resolved.name,
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
            status="draft",
            created_by=operator,
            created_at=datetime.now(API_TZ).isoformat(),
        )

        # Persist
        try:
            doc_dict = summary.model_dump()
            doc_dict["_created"] = datetime.now(API_TZ).isoformat()
            await self.db.col("shift_handover_summaries").insert_one(doc_dict)
        except Exception as exc:
            logger.warning("Failed to persist shift summary: %s", exc)

        return summary

    async def _query_patients(self, dept_code: str) -> list[dict[str, Any]]:
        """Query active patients in the department."""
        query: dict[str, Any] = {
            "$or": [
                {"status": {"$nin": ["discharged", "invalid", "invaild"]}},
                {"status": {"$exists": False}},
            ]
        }
        if dept_code:
            query["$or"] = [
                {"deptCode": dept_code},
                {"dept_code": dept_code},
                {"departmentCode": dept_code},
                {"hisDeptCode": dept_code},
            ]

        cursor = self.db.col("patient").find(query)
        return await cursor.to_list(length=500)

    async def _patient_stat(
        self, pid: str, p: dict, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Build statistics for a single patient."""
        from app.utils.serialization import safe_oid

        oid = safe_oid(pid)
        p_ids = patient_his_pid_candidates(p)

        bed = str(p.get("hisBed") or p.get("showBed") or p.get("bed") or p.get("bedNo") or "")
        name = str(p.get("name") or p.get("hisName") or "")
        diagnosis = str(p.get("diagnosis") or p.get("diagnose") or p.get("hisDiagnosis") or "")
        isolation = str(p.get("isolation") or p.get("isolationType") or "")

        # Check ventilator
        has_vent = False
        try:
            vent = await self.db.col("ventilator").find_one({"pid": pid})
            if not vent and oid:
                vent = await self.db.col("ventilator").find_one({"pid": oid})
            has_vent = bool(vent)
        except Exception:
            pass

        # Check alerts
        alert_count = 0
        unclosed = 0
        crit_vals = 0
        try:
            pid_or = {"$or": [{"patient_id": oid}, {"patient_id": pid}]} if oid else {"patient_id": pid}
            alerts = await self.db.col("alert_records").find({
                **pid_or,
                "created_at": {"$gte": start, "$lte": end},
            }).to_list(length=100)
            alert_count = len(alerts)
            unclosed = sum(1 for a in alerts if not a.get("acknowledged_at") and not a.get("ack_disposition"))
            crit_vals = sum(1 for a in alerts if str(a.get("priority", "")).lower() in ("critical", "危急"))
        except Exception:
            pass

        # Check vasoactive meds
        has_vaso = False
        try:
            pid_or = {"$or": [{"patient_id": oid}, {"patient_id": pid}]} if oid else {"patient_id": pid}
            meds = await self.db.col("medication_given").find({
                **pid_or,
                "record_time": {"$gte": start, "$lte": end},
            }).to_list(length=50)
            vaso_keywords = ["去甲肾上腺素", "多巴胺", "肾上腺素", "血管加压素", "norepinephrine", "dopamine", "vasopressin"]
            for m in meds:
                drug = str(m.get("drug_name") or m.get("name") or "").lower()
                if any(kw in drug for kw in vaso_keywords):
                    has_vaso = True
                    break
        except Exception:
            pass

        return {
            "patient_id": pid,
            "bed": bed,
            "name": name,
            "diagnosis": diagnosis,
            "isolation": isolation,
            "is_critical": crit_vals > 0 or unclosed > 2,
            "has_ventilator": has_vent,
            "has_vasoactive": has_vaso,
            "has_crrt": False,  # TODO: check CRRT devices
            "alert_count": alert_count,
            "unclosed_alert_count": unclosed,
            "critical_value_count": crit_vals,
            "high_risk_line_count": 0,  # TODO: check tubeExe
        }

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
                items.append({
                    "patient_id": p["patient_id"],
                    "bed": p["bed"],
                    "name": p["name"],
                    "reason": f"未闭环危急值{p.get('critical_value_count', 0)}条",
                    "severity": "critical",
                })
            elif p.get("has_vasoactive"):
                items.append({
                    "patient_id": p["patient_id"],
                    "bed": p["bed"],
                    "name": p["name"],
                    "reason": "使用血管活性药",
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

        # Sort: critical > high > medium
        severity_order = {"critical": 0, "high": 1, "medium": 2}
        items.sort(key=lambda x: severity_order.get(x.get("severity", ""), 99))
        return items

    def _build_deterministic_summary(
        self,
        patient_count: int,
        critical_count: int,
        vent_count: int,
        vaso_count: int,
        crrt_count: int,
        alert_count: int,
        unclosed_alerts: int,
        priority_items: list[dict],
        shift_name: str,
    ) -> str:
        """Build deterministic summary text (no AI required)."""
        parts = [
            f"本{shift_name}共管理{patient_count}名患者",
        ]
        if critical_count:
            parts.append(f"其中危重{critical_count}名")
        details = []
        if vent_count:
            details.append(f"{vent_count}名患者使用有创机械通气")
        if vaso_count:
            details.append(f"{vaso_count}名患者使用血管活性药")
        if crrt_count:
            details.append(f"{crrt_count}名患者接受CRRT")
        if details:
            parts.append("，".join(details) + "。")

        if alert_count:
            parts.append(f"共有{alert_count}条高优先级告警")
            if unclosed_alerts:
                parts.append(f"其中{unclosed_alerts}条尚未闭环")
            parts.append("。")

        if priority_items:
            top3 = priority_items[:3]
            beds = "、".join(f"{item['bed']}床{item['name']}" for item in top3)
            parts.append(f"下一班应重点关注：{beds}。")

        return "".join(parts)
