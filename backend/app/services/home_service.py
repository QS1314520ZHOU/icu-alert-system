from __future__ import annotations

import asyncio
import uuid
import re
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.services.alert_outcome_service import AlertOutcomeService
from app.services.clinical_adoption_service import ClinicalAdoptionService
from app.services.shift_service import ShiftInfo, ShiftService
from app.utils.patient_helpers import admitted_patient_query, patient_his_pid_candidates
from app.utils.serialization import serialize_doc

API_TZ = ZoneInfo("Asia/Shanghai")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _as_api_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=API_TZ)
    return value.astimezone(API_TZ)


def _contains_any(value: Any, keywords: Iterable[str]) -> bool:
    text = _text(value).lower()
    return bool(text) and any(_text(keyword).lower() in text for keyword in keywords if _text(keyword))


async def _empty_async_cursor():
    """Yield nothing — used as a safe fallback when a collection query fails."""
    return
    yield  # pragma: no cover


def _patient_id(patient: dict[str, Any]) -> str:
    return str(patient.get("_id") or patient.get("patientId") or patient.get("pid") or "")


def _bed(patient: dict[str, Any]) -> str:
    return _text(patient.get("hisBed") or patient.get("bed") or patient.get("bedNo"))


def _name(patient: dict[str, Any]) -> str:
    return _text(patient.get("name") or patient.get("hisName")) or "未知患者"


class RoleHomeService:
    def __init__(self, db, config=None, ai_handoff_service=None, llm_call=None) -> None:
        self.db = db
        self.config = config
        self.ai_handoff_service = ai_handoff_service
        self.llm_call = llm_call
        self.shift_service = ShiftService(db)
        self.adoption = ClinicalAdoptionService(db)
        self.outcomes = AlertOutcomeService(db)

    async def _account_by_user_id(self, user_id: str) -> dict[str, Any]:
        uid = _text(user_id)
        if not uid:
            return {"user_id": "", "userName": "", "display_name": "未识别用户", "role": "doctor", "found": False}
        query = {
            "$or": [
                {"_id": ObjectId(uid)} if ObjectId.is_valid(uid) else {"_id": uid},
                {"userId": uid},
                {"user_id": uid},
                {"userName": uid},
                {"username": uid},
                {"trueName": uid},
                {"name": uid},
                {"realName": uid},
                {"account": uid},
                {"loginName": uid},
                {"工号": uid},
            ]
        }
        row = await self.db.col("account").find_one(query)
        if not row:
            return {"user_id": uid, "userName": uid, "display_name": uid, "role": "doctor", "found": False}
        role = self.adoption._normalize_role(row, "doctor")
        return {
            "user_id": _text(row.get("username") or row.get("userName") or row.get("userId") or uid),
            "requested_user_id": uid,
            "userName": row.get("userName") or row.get("username") or row.get("account") or uid,
            "trueName": row.get("trueName"),
            "display_name": row.get("trueName") or row.get("name") or row.get("realName") or row.get("userName") or uid,
            "role": role,
            "dept": row.get("deptName") or row.get("departmentName") or row.get("dept"),
            "dept_code": row.get("deptCode") or row.get("departmentCode"),
            "found": True,
        }

    def _account_patient_user_id(self, account: dict[str, Any], fallback: str) -> str:
        return _text(account.get("userName") or account.get("user_id") or fallback)

    def _department_scope_query(self, *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any] | None:
        dept_text = _text(dept)
        dept_code_text = _text(dept_code)
        if dept_text and not dept_code_text and dept_text.isdigit():
            dept_code_text = dept_text
            dept_text = ""
        clauses: list[dict[str, Any]] = []
        if dept_code_text:
            codes = [item.strip() for item in dept_code_text.split(",") if item.strip()]
            if codes:
                clauses.append({"deptCode": {"$in": codes}})
        if dept_text:
            clauses.append(
                {
                    "$or": [
                        {"dept": dept_text},
                        {"hisDept": dept_text},
                        {"department": dept_text},
                        {"deptName": dept_text},
                    ]
                }
            )
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$or": clauses}

    def _with_department_scope(self, base_query: dict[str, Any], *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        scope = self._department_scope_query(dept=dept, dept_code=dept_code)
        if not scope:
            return base_query
        return {"$and": [base_query, scope]}

    def _account_scoped_dept(self, account: dict[str, Any], *, dept: str | None = None, dept_code: str | None = None) -> tuple[str | None, str | None]:
        return _text(dept) or None, _text(dept_code) or _text(account.get("dept_code")) or None

    def _patient_alert_keys(self, patient: dict[str, Any]) -> list[Any]:
        keys: list[Any] = []
        oid = patient.get("_id")
        if oid is not None:
            keys.extend([oid, str(oid)])
        keys.extend(patient_his_pid_candidates(patient))
        out: list[Any] = []
        seen: set[str] = set()
        for key in keys:
            marker = f"{type(key).__name__}:{key}"
            if _text(key) and marker not in seen:
                seen.add(marker)
                out.append(key)
        return out

    async def _doctor_patients(self, user_id: str, *, dept: str | None = None, dept_code: str | None = None) -> list[dict[str, Any]]:
        query = {"$and": [admitted_patient_query(), {"bedDoctorId": _text(user_id)}]}
        query = self._with_department_scope(query, dept=dept, dept_code=dept_code)
        cursor = self.db.col("patient").find(
            query,
            {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "bedNo": 1, "bedDoctorId": 1, "hisPid": 1, "hisPID": 1, "pid": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1, "dept": 1, "hisDept": 1, "deptCode": 1},
        ).limit(120)
        return [row async for row in cursor]

    async def _fetch_alerts_for_patients(self, patients: list[dict[str, Any]], hours: int = 12) -> list[dict[str, Any]]:
        """批量获取患者告警记录。"""
        if not patients:
            return []
        patient_keys: list[Any] = []
        for patient in patients:
            patient_keys.extend(self._patient_alert_keys(patient))
        if not patient_keys:
            return []
        since = datetime.now(API_TZ) - timedelta(hours=hours)
        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": patient_keys}, "created_at": {"$gte": since}},
            {"patient_id": 1, "rule_id": 1, "severity": 1, "created_at": 1, "acknowledged_at": 1, "ack_disposition": 1, "suppressed": 1, "auto_suppressed": 1, "pushed_at": 1, "clicked_at": 1, "adopted": 1},
        ).sort("created_at", -1).limit(1000)
        return [row async for row in cursor]

    async def _latest_integrated_risk(self, patients: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """批量查询综合风险推理（单次查询替代 N 次）。"""
        if not patients:
            return {}
        all_keys: list[Any] = []
        key_to_pid: dict[str, str] = {}
        for patient in patients:
            pid = _patient_id(patient)
            for key in self._patient_alert_keys(patient):
                if _text(key):
                    all_keys.append(key)
                    key_to_pid[str(key)] = pid
        if not all_keys:
            return {}
        # 批量查询所有患者的 INTEGRATED_RISK_REASONING
        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": all_keys}, "rule_id": "INTEGRATED_RISK_REASONING"},
            {"patient_id": 1, "rule_id": 1, "severity": 1, "created_at": 1, "extra": 1, "name": 1},
        ).sort("created_at", -1).limit(len(patients) * 2)
        result: dict[str, dict[str, Any]] = {}
        async for row in cursor:
            pid = key_to_pid.get(str(row.get("patient_id")), "")
            if pid and pid not in result:
                result[pid] = row
        return result

    def _patient_by_id(self, patients: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {_patient_id(patient): patient for patient in patients if _patient_id(patient)}

    def _alert_keys_for_patient_ids(self, patients_by_id: dict[str, dict[str, Any]], patient_ids: list[str]) -> list[Any]:
        keys: list[Any] = []
        seen: set[str] = set()
        for pid in patient_ids:
            patient = patients_by_id.get(_text(pid))
            raw_keys = self._patient_alert_keys(patient) if patient else [_text(pid)]
            for key in raw_keys:
                marker = f"{type(key).__name__}:{key}"
                if _text(key) and marker not in seen:
                    seen.add(marker)
                    keys.append(key)
        return keys

    def _patient_id_from_alert_key(self, patients_by_id: dict[str, dict[str, Any]], value: Any) -> str:
        marker = _text(value)
        for pid, patient in patients_by_id.items():
            if any(_text(key) == marker for key in self._patient_alert_keys(patient)):
                return pid
        return marker

    def _risk_score(self, row: dict[str, Any] | None) -> int:
        if not row:
            return 0
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        for key in ("risk_score", "score", "priority_score", "actionability_score"):
            value = row.get(key, extra.get(key))
            try:
                return int(float(value))
            except Exception:
                pass
        sev = _text(row.get("severity")).lower()
        return {"critical": 95, "high": 82, "warning": 60, "info": 35}.get(sev, 20)

    def _top_action(self, row: dict[str, Any] | None) -> str:
        if not row:
            return "暂无综合风险推理输出，建议进入患者详情复核趋势。"
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        for value in (extra.get("top_actions"), row.get("top_actions"), extra.get("actions"), row.get("recommendations")):
            if isinstance(value, list) and value:
                return self._format_action_text(value[0])
            if isinstance(value, dict):
                return self._format_action_text(value)
        return self._format_action_text(row.get("explanation") or row.get("name") or row.get("alert_type"))

    def _format_action_text(self, value: Any) -> str:
        if isinstance(value, dict):
            summary = _text(value.get("summary") or value.get("text") or value.get("title") or value.get("problem"))
            suggestion = _text(value.get("suggestion") or value.get("recommendation") or value.get("action"))
            evidence = value.get("evidence")
            if isinstance(evidence, list):
                evidence_text = "；".join(_text(item) for item in evidence[:2] if _text(item))
            else:
                evidence_text = _text(evidence)
            parts = []
            if summary:
                parts.append(summary)
            if evidence_text:
                parts.append(f"依据：{evidence_text}")
            if suggestion:
                parts.append(f"建议：{suggestion}")
            return "。".join(parts[:3]) or "进入患者详情复核。"
        text = _text(value)
        if not text:
            return "进入患者详情复核。"
        if "'summary'" in text or '"summary"' in text:
            return "综合风险推理已生成结构化结论，建议进入患者详情查看证据和处置建议。"
        return text

    async def doctor_home(self, user_id: str, *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        shift = await self.shift_service.get_current_shift()
        dept, dept_code = self._account_scoped_dept(account, dept=dept, dept_code=dept_code)
        doctor_user_id = self._account_patient_user_id(account, user_id)
        patients = await self._doctor_patients(doctor_user_id, dept=dept, dept_code=dept_code)

        # 并行获取风险、告警、任务、质控
        patient_ids = [_patient_id(patient) for patient in patients]
        risk_task = self._latest_integrated_risk(patients)
        alerts_task = self._fetch_alerts_for_patients(patients, hours=12)
        tasks_task = self._open_tasks_for_patients(patient_ids)
        quality_task = self.adoption.quality_summary(days=7, dept=dept or account.get("dept"), dept_code=dept_code)

        risk_by_patient, alerts, open_tasks, quality = await asyncio.gather(
            risk_task, alerts_task, tasks_task, quality_task,
            return_exceptions=True,
        )
        if isinstance(risk_by_patient, Exception):
            risk_by_patient = {}
        if isinstance(alerts, Exception):
            alerts = []
        if isinstance(open_tasks, Exception):
            open_tasks = []
        if isinstance(quality, Exception):
            quality = {}

        focus = []
        for patient in patients:
            pid = _patient_id(patient)
            risk = risk_by_patient.get(pid)
            focus.append(
                {
                    "patient_id": pid,
                    "bed": _bed(patient),
                    "name": _name(patient),
                    "risk_level": _text((risk or {}).get("severity") or ((risk or {}).get("extra") or {}).get("risk_level") or "unknown").lower(),
                    "risk_score": self._risk_score(risk),
                    "reason": self._top_action(risk),
                }
            )
        focus.sort(key=lambda row: (-int(row.get("risk_score") or 0), _text(row.get("bed"))))

        ai_watch = {
            "total_alerts": len(alerts),
            "auto_suppressed": sum(1 for row in alerts if row.get("suppressed") or row.get("auto_suppressed")),
            "pushed": sum(1 for row in alerts if row.get("pushed_at")),
            "handled": sum(1 for row in alerts if row.get("acknowledged_at") or row.get("ack_disposition")),
            "pending_followup": sum(1 for row in alerts if not row.get("acknowledged_at") and not row.get("ack_disposition")),
            "integrated_reasoning": sum(1 for row in alerts if row.get("rule_id") == "INTEGRATED_RISK_REASONING"),
            "integrated_adopted": sum(1 for row in alerts if row.get("rule_id") == "INTEGRATED_RISK_REASONING" and row.get("adopted")),
            "pulse_pushes": sum(1 for row in alerts if row.get("pushed_at")),
            "pulse_clicks": sum(1 for row in alerts if row.get("clicked_at")),
        }
        data_state = {
            "account_found": bool(account.get("found")),
            "doctor_user_id": doctor_user_id,
            "dept": dept,
            "dept_code": dept_code,
            "managed_beds": len(patients),
            "empty_reason": "",
        }
        if not account.get("found"):
            data_state["empty_reason"] = "当前账号未完成医生身份识别，请确认已使用医生账号进入。"
        elif not patients:
            data_state["empty_reason"] = "当前账号暂未匹配到分管在科患者，请确认患者主管医生信息已维护。"
        return {
            "account": account,
            "doctor_user_id": doctor_user_id,
            "data_state": data_state,
            "shift": shift.to_dict() if shift else None,
            "managed_beds": len(patients),
            "focus_patients": focus[:5],
            "ai_night_watch": ai_watch,
            "pending_tasks": open_tasks,
            "quality_summary": quality,
            "generated_at": datetime.now(API_TZ),
        }

    def _record_user_id(self, row: dict[str, Any]) -> str:
        return _text(row.get("userId") or row.get("recorderId") or row.get("recordUserId") or row.get("operatorId") or row.get("creatorId"))

    def _record_user_name(self, row: dict[str, Any]) -> str:
        return _text(row.get("userName") or row.get("username") or row.get("trueName") or row.get("name") or row.get("recorderName"))

    def _record_user_values(self, row: dict[str, Any]) -> set[str]:
        return {
            value
            for value in (
                self._record_user_id(row),
                _text(row.get("userName")),
                _text(row.get("username")),
                _text(row.get("trueName")),
                _text(row.get("name")),
                _text(row.get("recorderName")),
                _text(row.get("工号")),
                _text(row.get("account")),
                _text(row.get("loginName")),
            )
            if value
        }

    def _record_time_query(self, start: datetime, end: datetime) -> dict[str, Any]:
        return {"$or": [{"recordTime": {"$gte": start, "$lt": end}}, {"time": {"$gte": start, "$lt": end}}, {"created_at": {"$gte": start, "$lt": end}}, {"createTime": {"$gte": start, "$lt": end}}]}

    def _record_time_value(self, row: dict[str, Any]) -> datetime | None:
        return _dt(row.get("recordTime") or row.get("time") or row.get("created_at") or row.get("createTime"))

    def _record_patient_value(self, row: dict[str, Any]) -> Any:
        return row.get("pid") or row.get("patient_id") or row.get("patientId") or row.get("hisPid")

    def _patients_key_index(self, patients_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
        index: dict[str, str] = {}
        for pid, patient in patients_by_id.items():
            for key in self._patient_alert_keys(patient):
                if _text(key):
                    index[_text(key)] = pid
        return index

    async def _nursing_records_for_patients(
        self,
        patients_by_id: dict[str, dict[str, Any]],
        *,
        start: datetime,
        end: datetime,
        limit: int = 5000,
        collections: tuple[str, ...] = ("nurseRecords", "nursing_record"),
    ) -> list[dict[str, Any]]:
        keys: list[Any] = []
        seen: set[str] = set()
        for patient in patients_by_id.values():
            for key in self._patient_alert_keys(patient):
                marker = f"{type(key).__name__}:{key}"
                if _text(key) and marker not in seen:
                    seen.add(marker)
                    keys.append(key)
        if not keys:
            return []
        query = {
            "$and": [
                self._record_time_query(start, end),
                {"$or": [{"pid": {"$in": keys}}, {"patient_id": {"$in": keys}}, {"patientId": {"$in": keys}}, {"hisPid": {"$in": keys}}]},
            ]
        }
        projection = {
            "pid": 1,
            "patient_id": 1,
            "patientId": 1,
            "hisPid": 1,
            "recordTime": 1,
            "time": 1,
            "created_at": 1,
            "createTime": 1,
            "careType": 1,
            "task_type": 1,
            "task_id": 1,
            "content": 1,
            "recordTitle": 1,
            "title": 1,
            "name": 1,
            "userName": 1,
            "username": 1,
            "trueName": 1,
            "userId": 1,
            "recorderId": 1,
            "recordUserId": 1,
            "operatorId": 1,
            "creatorId": 1,
        }
        rows: list[dict[str, Any]] = []
        for collection in collections:
            try:
                cursor = self.db.col(collection).find(query, projection).sort([("recordTime", 1), ("time", 1), ("created_at", 1), ("createTime", 1)]).limit(limit)
                rows.extend([row async for row in cursor])
            except Exception:
                continue
        rows.sort(key=lambda row: _as_api_tz(self._record_time_value(row) or datetime.max.replace(tzinfo=API_TZ)))
        return rows

    def _record_matches_task(self, row: dict[str, Any], keywords: list[str]) -> bool:
        return any(
            _contains_any(row.get(field), keywords)
            for field in ("careType", "task_type", "task_id", "content", "recordTitle", "title", "name")
        )

    async def _latest_nursing_task_records_by_patient(
        self,
        patient_ids: list[str],
        patients_by_id: dict[str, dict[str, Any]],
        catalog: list[dict[str, Any]],
        shift: ShiftInfo,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not patient_ids or not catalog:
            return {}
        start = shift.start - timedelta(hours=24)
        records = await self._nursing_records_for_patients(patients_by_id, start=start, end=shift.end, limit=8000)
        key_index = self._patients_key_index(patients_by_id)
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        latest_time: dict[tuple[str, str], datetime] = {}
        patient_filter = set(patient_ids)
        for row in records:
            pid = key_index.get(_text(self._record_patient_value(row)))
            if not pid or pid not in patient_filter:
                continue
            when = self._record_time_value(row)
            if not when:
                continue
            when_api = _as_api_tz(when)
            for spec in catalog:
                if not self._record_matches_task(row, spec["keywords"]):
                    continue
                marker = (pid, spec["key"])
                if marker not in latest_time or when_api > latest_time[marker]:
                    latest_time[marker] = when_api
                    latest[marker] = row
        return latest

    async def nurse_patient_assignments(self, user_id: str, shift: ShiftInfo, *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        query = self._with_department_scope(admitted_patient_query(), dept=dept, dept_code=dept_code)
        patients = [row async for row in self.db.col("patient").find(query, {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "hisPID": 1, "pid": 1, "dept": 1, "hisDept": 1, "deptCode": 1}).limit(160)]
        if not patients and (dept or dept_code):
            patients = [row async for row in self.db.col("patient").find(admitted_patient_query(), {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "hisPID": 1, "pid": 1, "dept": 1, "hisDept": 1, "deptCode": 1}).limit(160)]
        patients_by_id = {_patient_id(patient): patient for patient in patients if _patient_id(patient)}
        key_index = self._patients_key_index(patients_by_id)
        records = await self._nursing_records_for_patients(patients_by_id, start=shift.start, end=shift.end, limit=8000, collections=("nurseRecords",))
        first_by_patient: dict[str, dict[str, Any]] = {}
        for row in records:
            pid = key_index.get(_text(self._record_patient_value(row)))
            if pid and pid not in first_by_patient:
                first_by_patient[pid] = row
        assigned: list[dict[str, Any]] = []
        pending_handover: list[dict[str, Any]] = []
        for patient in patients:
            pid = _patient_id(patient)
            first = first_by_patient.get(pid)
            patient_row = {"patient_id": _patient_id(patient), "bed": _bed(patient), "name": _name(patient)}
            if not first:
                pending_handover.append(patient_row)
                continue
            owner_id = self._record_user_id(first)
            owner_name = self._record_user_name(first)
            if _text(user_id) in self._record_user_values(first):
                assigned.append({**patient_row, "patient_doc": patient, "responsible_nurse": owner_name or owner_id, "first_record_time": self._record_time_value(first)})
        return {"assigned": assigned, "pending_handover": pending_handover}

    async def _open_tasks_for_patients(self, patient_ids: list[str], limit: int = 20) -> list[dict[str, Any]]:
        ids = [pid for pid in {_text(pid) for pid in patient_ids} if pid]
        if not ids:
            return []
        cursor = self.db.col("clinical_tasks").find(
            {"patient_id": {"$in": ids}, "status": {"$in": ["open", "in_progress", "pending"]}},
            {"_id": 0, "task_id": 1, "patient_id": 1, "bed": 1, "name": 1, "module": 1, "task_type": 1, "title": 1, "detail": 1, "priority": 1, "status": 1, "updated_at": 1, "created_at": 1},
        ).sort([("priority", -1), ("updated_at", -1)]).limit(max(1, int(limit or 20)))
        return [serialize_doc(row) async for row in cursor]

    async def _latest_scores_by_patient(self, patient_ids: list[str], scanner_names: list[str], patients_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
        if not patient_ids:
            return {}
        patient_map = patients_by_id or {}
        alert_keys = self._alert_keys_for_patient_ids(patient_map, patient_ids) if patient_map else patient_ids
        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": alert_keys}, "$or": [{"rule_id": {"$in": scanner_names}}, {"alert_type": {"$in": scanner_names}}, {"scanner_name": {"$in": scanner_names}}]},
            {"patient_id": 1, "rule_id": 1, "alert_type": 1, "scanner_name": 1, "severity": 1, "name": 1, "created_at": 1, "extra": 1, "acknowledged_at": 1, "ack_disposition": 1},
        ).sort("created_at", -1).limit(600)
        grouped: dict[str, list[dict[str, Any]]] = {}
        async for row in cursor:
            pid = self._patient_id_from_alert_key(patient_map, row.get("patient_id")) if patient_map else _text(row.get("patient_id"))
            grouped.setdefault(pid, []).append(row)
        return grouped

    def _task_status(self, due_at: datetime, done: bool = False) -> str:
        if done:
            return "done"
        now = datetime.now(API_TZ)
        minutes = (due_at - now).total_seconds() / 60
        if minutes > 15:
            return "future"
        if 0 <= minutes <= 15:
            return "soon"
        if -5 <= minutes < 0:
            return "due"
        return "overdue"

    def _nursing_task_catalog(self) -> list[dict[str, Any]]:
        cfg_obj = self.config
        if cfg_obj is None:
            return []
        yaml_cfg = getattr(cfg_obj, "yaml_cfg", None) or {}
        reminders_cfg = yaml_cfg.get("nurse_reminders", {})
        if not isinstance(reminders_cfg, dict) or not reminders_cfg:
            return []
        default_titles = {
            "gcs": "GCS评估",
            "rass": "RASS评估",
            "pain": "疼痛评估",
            "cpot": "CPOT评估",
            "bps": "BPS评估",
            "delirium": "谵妄评估",
            "braden": "Braden压疮评估",
            "cam_icu": "CAM-ICU评估",
            "turning": "翻身",
            "early_mobility": "早期活动",
        }
        catalog: list[dict[str, Any]] = []
        for score_type, score_cfg in reminders_cfg.items():
            if not isinstance(score_cfg, dict):
                continue
            interval_h = float(score_cfg.get("interval_hours", 4))
            title = score_cfg.get("name") or default_titles.get(score_type, f"{score_type.upper()}评估")
            code = score_cfg.get("code", "")
            keywords = [_text(score_type), _text(code)]
            if score_type == "turning":
                keywords.extend(score_cfg.get("turning_keywords", []))
            elif score_type == "early_mobility":
                keywords.extend(score_cfg.get("activity_keywords", []))
            catalog.append({
                "key": score_type,
                "title": title,
                "code": code,
                "keywords": [k for k in keywords if _text(k)],
                "period": timedelta(hours=interval_h),
                "rule_id": score_cfg.get("rule_id", f"NURSE_{score_type.upper()}"),
            })
        return catalog

    async def _nursing_reminder_matrix(
        self,
        patient_ids: list[str],
        patients_by_id: dict[str, dict[str, Any]],
        shift: ShiftInfo,
        catalog: list[dict[str, Any]],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not patient_ids or not catalog:
            return {}
        score_types = [spec["key"] for spec in catalog]
        try:
            active_cursor = self.db.col("nurse_reminders").find(
                {"patient_id": {"$in": patient_ids}, "score_type": {"$in": score_types}, "is_active": True},
                {"patient_id": 1, "score_type": 1, "due_at": 1, "last_score_time": 1, "severity": 1, "name": 1, "_id": 1, "code": 1},
            ).limit(500)
        except Exception:
            active_cursor = _empty_async_cursor()
        since = shift.start - timedelta(hours=48)
        try:
            resolved_cursor = self.db.col("nurse_reminders").find(
                {"patient_id": {"$in": patient_ids}, "score_type": {"$in": score_types}, "is_active": False, "resolved_at": {"$gte": since}},
                {"patient_id": 1, "score_type": 1, "due_at": 1, "last_score_time": 1, "resolved_at": 1, "severity": 1, "name": 1, "_id": 1, "code": 1},
            ).sort("resolved_at", -1).limit(500)
        except Exception:
            resolved_cursor = _empty_async_cursor()
        matrix: dict[tuple[str, str], dict[str, Any]] = {}
        async for row in active_cursor:
            pid = _text(row.get("patient_id"))
            st = _text(row.get("score_type"))
            if pid and st:
                matrix[(pid, st)] = row
        async for row in resolved_cursor:
            pid = _text(row.get("patient_id"))
            st = _text(row.get("score_type"))
            key = (pid, st)
            if pid and st and key not in matrix:
                matrix[key] = row
        return matrix

    def _record_patient_query(self, patient: dict[str, Any] | None, pid: str) -> dict[str, Any]:
        keys = self._patient_alert_keys(patient) if patient else [pid]
        keys = [key for key in keys if _text(key)]
        return {"$or": [{"pid": {"$in": keys}}, {"patient_id": {"$in": keys}}, {"patientId": {"$in": keys}}, {"hisPid": {"$in": keys}}]}

    def _record_task_text_query(self, keywords: list[str]) -> dict[str, Any]:
        regex = "|".join(re.escape(keyword) for keyword in keywords if _text(keyword))
        return {
            "$or": [
                {"careType": {"$regex": regex, "$options": "i"}},
                {"task_type": {"$regex": regex, "$options": "i"}},
                {"task_id": {"$regex": regex, "$options": "i"}},
                {"content": {"$regex": regex, "$options": "i"}},
                {"recordTitle": {"$regex": regex, "$options": "i"}},
                {"title": {"$regex": regex, "$options": "i"}},
                {"name": {"$regex": regex, "$options": "i"}},
            ]
        }

    async def _latest_nursing_task_record(self, patient: dict[str, Any] | None, pid: str, keywords: list[str]) -> dict[str, Any] | None:
        query = {"$and": [self._record_patient_query(patient, pid), self._record_task_text_query(keywords)]}
        projection = {"recordTime": 1, "time": 1, "created_at": 1, "createTime": 1, "careType": 1, "content": 1, "title": 1, "recordTitle": 1}
        for collection in ("nurseRecords", "nursing_record"):
            try:
                row = await self.db.col(collection).find_one(query, projection, sort=[("recordTime", -1), ("time", -1), ("created_at", -1), ("createTime", -1)])
                if row:
                    return row
            except Exception:
                continue
        return None

    def _due_from_last_done(self, last_done_at: datetime | None, period: timedelta | None, shift: ShiftInfo) -> datetime:
        if period is None:
            return shift.end - timedelta(hours=1)
        base = _as_api_tz(last_done_at) if last_done_at else shift.start
        due_at = base + period
        while due_at < shift.start:
            due_at += period
        return due_at

    def _all_patient_keys(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]]) -> list[Any]:
        """收集所有患者的 alert keys，用于批量查询。"""
        keys: list[Any] = []
        seen: set[str] = set()
        for pid in patient_ids:
            patient = patients_by_id.get(pid)
            for key in (self._patient_alert_keys(patient) if patient else [pid]):
                marker = f"{type(key).__name__}:{key}"
                if _text(key) and marker not in seen:
                    seen.add(marker)
                    keys.append(key)
        return keys

    async def _latest_record_by_keywords(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]], keywords: list[str], hours: int) -> tuple[bool, str, datetime | None]:
        """批量查询 nurseRecords 关键词匹配（单次查询替代 N 次）。"""
        since = datetime.now(API_TZ) - timedelta(hours=max(1, hours))
        regex = "|".join(re.escape(k) for k in keywords if _text(k))
        if not regex or not patient_ids:
            return False, "", None
        keys = self._all_patient_keys(patient_ids, patients_by_id)
        if not keys:
            return False, "", None
        text_cond = {"$or": [
            {"content": {"$regex": regex, "$options": "i"}},
            {"recordTitle": {"$regex": regex, "$options": "i"}},
            {"title": {"$regex": regex, "$options": "i"}},
            {"careType": {"$regex": regex, "$options": "i"}},
            {"name": {"$regex": regex, "$options": "i"}},
        ]}
        query = {"$and": [
            {"$or": [{"pid": {"$in": keys}}, {"patient_id": {"$in": keys}}]},
            {"time": {"$gte": since}},
            text_cond,
        ]}
        latest: datetime | None = None
        for col_name in ("nurseRecords", "nursing_record"):
            try:
                row = await self.db.col(col_name).find_one(query, {"recordTime": 1, "time": 1, "created_at": 1, "createTime": 1}, sort=[("time", -1)])
                if row:
                    when = _dt(row.get("recordTime") or row.get("time") or row.get("created_at") or row.get("createTime"))
                    if when and (latest is None or _as_api_tz(when) > latest):
                        latest = _as_api_tz(when)
            except Exception:
                continue
        return bool(latest), "nurseRecords" if latest else "", latest

    async def _latest_bedside_by_keywords(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]], keywords: list[str], hours: int) -> tuple[bool, str, datetime | None]:
        """批量查询 bedside 关键词匹配（单次查询替代 N 次）。"""
        since = datetime.now(API_TZ) - timedelta(hours=max(1, hours))
        regex = "|".join(re.escape(k) for k in keywords if _text(k))
        if not regex or not patient_ids:
            return False, "", None
        keys = self._all_patient_keys(patient_ids, patients_by_id)
        if not keys:
            return False, "", None
        query = {"$and": [
            {"pid": {"$in": keys}},
            {"time": {"$gte": since}},
            {"$or": [
                {"code": {"$regex": regex, "$options": "i"}},
                {"name": {"$regex": regex, "$options": "i"}},
                {"paramName": {"$regex": regex, "$options": "i"}},
                {"strVal": {"$regex": regex, "$options": "i"}},
                {"value": {"$regex": regex, "$options": "i"}},
            ]},
        ]}
        try:
            row = await self.db.col("bedside").find_one(query, {"time": 1}, sort=[("time", -1)])
        except Exception:
            row = None
        when = _dt((row or {}).get("time"))
        latest = _as_api_tz(when) if when else None
        return bool(latest), "bedside" if latest else "", latest

    async def _latest_bed_angle_done(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]]) -> tuple[bool, str, datetime | None]:
        """批量查询床头抬高（单次查询替代 N 次）。"""
        since = datetime.now(API_TZ) - timedelta(hours=4)
        keys = self._all_patient_keys(patient_ids, patients_by_id)
        if not keys:
            return False, "", None
        query = {"$and": [
            {"pid": {"$in": keys}},
            {"time": {"$gte": since}},
            {"$or": [{"code": "param_bed_angle"}, {"paramCode": "param_bed_angle"}, {"name": {"$regex": "床头|床角度|bed_angle", "$options": "i"}}]},
        ]}
        try:
            cursor = self.db.col("bedside").find(query, {"time": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1}).sort("time", -1).limit(50)
            rows = [row async for row in cursor]
        except Exception:
            rows = []
        latest: datetime | None = None
        for row in rows:
            value = None
            for field in ("fVal", "intVal", "strVal", "value"):
                try:
                    value = float(str(row.get(field)).replace("°", ""))
                    break
                except Exception:
                    pass
            if value is not None and value >= 30:
                when = _as_api_tz(_dt(row.get("time")) or datetime.now(API_TZ))
                if latest is None or when > latest:
                    latest = when
        if latest:
            return True, "bedside:param_bed_angle", latest
        return await self._latest_bedside_by_keywords(patient_ids, patients_by_id, ["床头抬高", "抬高床头", "半卧位", "30°", "30度"], 24)

    async def _latest_drug_or_order_by_keywords(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]], keywords: list[str], hours: int) -> tuple[bool, str, datetime | None]:
        """批量查询 drugExe 关键词匹配（单次查询替代 N 次）。"""
        since = datetime.now(API_TZ) - timedelta(hours=max(1, hours))
        regex = "|".join(re.escape(k) for k in keywords if _text(k))
        if not regex or not patient_ids:
            return False, "", None
        keys = self._all_patient_keys(patient_ids, patients_by_id)
        if not keys:
            return False, "", None
        query = {"$and": [
            {"pid": {"$in": keys}},
            {"$or": [{"exeTime": {"$gte": since}}, {"executeTime": {"$gte": since}}, {"time": {"$gte": since}}, {"startTime": {"$gte": since}}, {"orderTime": {"$gte": since}}]},
            {"$or": [{"drugName": {"$regex": regex, "$options": "i"}}, {"orderName": {"$regex": regex, "$options": "i"}}, {"name": {"$regex": regex, "$options": "i"}}]},
        ]}
        try:
            row = await self.db.col("drugExe").find_one(query, {"exeTime": 1, "executeTime": 1, "time": 1, "startTime": 1, "orderTime": 1}, sort=[("exeTime", -1), ("executeTime", -1), ("time", -1)])
        except Exception:
            row = None
        when = _dt((row or {}).get("exeTime") or (row or {}).get("executeTime") or (row or {}).get("time") or (row or {}).get("startTime") or (row or {}).get("orderTime"))
        latest = _as_api_tz(when) if when else None
        return bool(latest), "drugExe" if latest else "", latest

    async def _bundle_hob_done(self, patient_ids, patients_by_id, label):
        return await self._latest_bed_angle_done(patient_ids, patients_by_id)

    async def _bundle_oral_care_done(self, patient_ids, patients_by_id, label):
        return await self._latest_record_by_keywords(patient_ids, patients_by_id, ["口腔护理", "口护", "口腔清洁", "oral_care", "oral care"], 4)

    async def _bundle_subglottic_done(self, patient_ids, patients_by_id, label):
        return await self._latest_record_by_keywords(patient_ids, patients_by_id, ["声门下", "吸引", "subglottic"], 8)

    async def _bundle_sat_done(self, patient_ids, patients_by_id, label):
        record = await self._latest_record_by_keywords(patient_ids, patients_by_id, ["镇静中断", "自主清醒", "SAT", "停镇静", "暂停镇静"], 24)
        if record[0]:
            return record
        return await self._latest_drug_or_order_by_keywords(patient_ids, patients_by_id, ["停用咪达唑仑", "停用丙泊酚", "暂停咪达唑仑", "暂停丙泊酚", "SAT"], 24)

    async def _bundle_stress_ulcer_done(self, patient_ids, patients_by_id, label):
        return await self._latest_drug_or_order_by_keywords(patient_ids, patients_by_id, ["奥美拉唑", "泮托拉唑", "兰索拉唑", "雷贝拉唑", "法莫替丁", "雷尼替丁", "PPI", "H2RA"], 48)

    async def _bundle_foley_review_done(self, patient_ids, patients_by_id, label):
        return await self._latest_record_by_keywords(patient_ids, patients_by_id, ["尿管必要", "导尿管评估", "尿管评估", "foley"], 24)

    async def _bundle_perineal_care_done(self, patient_ids, patients_by_id, label):
        return await self._latest_record_by_keywords(patient_ids, patients_by_id, ["尿道口护理", "会阴护理", "尿管护理"], 24)

    async def _bundle_cvc_review_done(self, patient_ids, patients_by_id, label):
        return await self._latest_record_by_keywords(patient_ids, patients_by_id, ["CVC必要", "中心静脉", "深静脉", "导管必要", "置管评估"], 24)

    async def _bundle_dressing_done(self, patient_ids, patients_by_id, label):
        return await self._latest_record_by_keywords(patient_ids, patients_by_id, ["敷料", "换药", "穿刺点", "贴膜"], 24)

    async def _bundle_shift_assessment_done(self, patient_ids, patients_by_id, label):
        return await self._latest_record_by_keywords(patient_ids, patients_by_id, [label, f"{label}评估", "护理评估"], 12)

    async def nurse_timeline(self, user_id: str, shift_code: str | ShiftInfo | None = "auto", *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        if isinstance(shift_code, ShiftInfo):
            shift = shift_code
        else:
            shift = await self.shift_service.resolve_shift(shift_code)
        if not shift:
            return {"shift": None, "beds": [], "tasks": [], "degraded": "未配置 banCiInfoList，无法计算本班时间轴。"}
        assignments = await self.nurse_patient_assignments(user_id, shift, dept=dept, dept_code=dept_code)
        beds = assignments["assigned"]
        patients_by_id = {row["patient_id"]: row.get("patient_doc") for row in beds if row.get("patient_doc")}
        scanner_names = [
            "scanner_nurse_reminders", "NURSE_REMINDER", "scanner_vanco_tdm_closed_loop", "delirium_risk",
            "scanner_ventilator_weaning", "crrt_monitor", "fluid_balance", "scanner_nutrition_monitor",
        ]
        grouped = await self._latest_scores_by_patient([row["patient_id"] for row in beds], scanner_names, patients_by_id)
        tasks: list[dict[str, Any]] = []
        catalog = self._nursing_task_catalog()
        reminder_matrix: dict[tuple[str, str], dict[str, Any]] = {}
        if catalog:
            reminder_matrix = await self._nursing_reminder_matrix(
                [row["patient_id"] for row in beds],
                patients_by_id,
                shift,
                catalog,
            )
        for bed in beds:
            pid = bed["patient_id"]
            rows = grouped.get(pid, [])
            for idx, spec in enumerate(catalog):
                reminder = reminder_matrix.get((pid, spec["key"]))
                if not reminder:
                    continue
                is_active = reminder.get("is_active", False)
                last_score_time = _dt(reminder.get("last_score_time"))
                if is_active:
                    due_at = _as_api_tz(_dt(reminder.get("due_at")) or datetime.now(API_TZ))
                    last_done_at = _as_api_tz(last_score_time) if last_score_time else None
                    done = False
                else:
                    last_done_at = _as_api_tz(last_score_time) if last_score_time else None
                    if last_done_at and spec.get("period"):
                        due_at = self._due_from_last_done(last_done_at, spec["period"], shift)
                    else:
                        due_at = _as_api_tz(_dt(reminder.get("due_at")) or datetime.now(API_TZ))
                    done = bool(last_done_at and shift.start <= last_done_at < shift.end and due_at >= shift.end)
                reminder_id = _text(reminder.get("_id"))
                tasks.append(
                    {
                        "task_id": reminder_id or f"{pid}-{spec['key']}",
                        "alert_id": reminder_id,
                        "patient_id": pid,
                        "bed": bed["bed"],
                        "patient_name": bed["name"],
                        "title": spec["title"],
                        "source": f"nurse_reminders:{spec['key']}",
                        "due_at": due_at,
                        "status": self._task_status(due_at, done),
                        "last_done_at": last_done_at,
                        "period_minutes": int(spec["period"].total_seconds() / 60) if spec.get("period") else None,
                        "detail": _text(reminder.get("name") or spec["title"]),
                    }
                )
            for row in rows[:4]:
                title = _text(row.get("name") or row.get("alert_type") or row.get("rule_id"))
                if not title or any(_contains_any(title, spec["keywords"]) for spec in catalog):
                    continue
                due_at = _as_api_tz(_dt(row.get("created_at")) or datetime.now(API_TZ))
                tasks.append(
                    {
                        "task_id": _text(row.get("_id")) or f"{pid}-alert-{len(tasks)}",
                        "alert_id": _text(row.get("_id")) if row.get("_id") else "",
                        "patient_id": pid,
                        "bed": bed["bed"],
                        "patient_name": bed["name"],
                        "title": title,
                        "source": _text(row.get("rule_id") or row.get("scanner_name") or row.get("alert_type")),
                        "due_at": due_at,
                        "status": self._task_status(due_at, bool(row.get("acknowledged_at") or row.get("ack_disposition"))),
                        "detail": _text(((row.get("extra") or {}) if isinstance(row.get("extra"), dict) else {}).get("suggestion") or title),
                    }
                )
        clean_beds = [{k: v for k, v in row.items() if k != "patient_doc"} for row in beds]
        return {
            "shift": shift.to_dict(),
            "beds": clean_beds,
            "pending_handover": assignments["pending_handover"],
            "tasks": tasks,
            "_patients_by_id": patients_by_id,
        }

    async def nurse_bundles(self, patient_ids: list[str], shift_code: str | None = "auto", patients_by_id: dict[str, dict[str, Any]] | None = None, *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        patient_map = patients_by_id or await self._patients_by_ids(patient_ids, dept=dept, dept_code=dept_code)
        patient_ids = [pid for pid in patient_ids if pid in patient_map]
        rows = await self._latest_scores_by_patient(patient_ids, ["HAI_VAP_BUNDLE_MISSING", "HAI_CVC_REVIEW", "HAI_CAUTI_RISK", "scanner_hai_bundle", "hai_bundle_monitor"], patient_map)
        bundles = []
        checks = [
            ("vap", "VAP 预防清单", [
                ("床头抬高30度", self._bundle_hob_done),
                ("口腔护理q4h", self._bundle_oral_care_done),
                ("声门下吸引", self._bundle_subglottic_done),
                ("镇静中断", self._bundle_sat_done),
                ("消化道溃疡预防", self._bundle_stress_ulcer_done),
            ]),
            ("cauti", "CAUTI 预防", [
                ("尿管必要性", self._bundle_foley_review_done),
                ("尿道口护理", self._bundle_perineal_care_done),
            ]),
            ("clabsi", "CLABSI 预防", [
                ("CVC必要性评估", self._bundle_cvc_review_done),
                ("敷料评估", self._bundle_dressing_done),
            ]),
            ("shift_assessment", "跌倒/压疮/约束/管路评估", [
                ("跌倒", self._bundle_shift_assessment_done),
                ("压疮", self._bundle_shift_assessment_done),
                ("约束", self._bundle_shift_assessment_done),
                ("管路", self._bundle_shift_assessment_done),
            ]),
        ]
        for code, name, item_specs in checks:
            check_results = await asyncio.gather(
                *(checker(patient_ids, patient_map, label) for label, checker in item_specs),
                return_exceptions=True,
            )
            item_rows = []
            for (label, _checker), result in zip(item_specs, check_results):
                if isinstance(result, Exception):
                    done, source, last_done_at = False, "", None
                else:
                    done, source, last_done_at = result
                item_rows.append({"name": label, "done": done, "source": source, "last_done_at": last_done_at})
            related_alerts = [
                row for group in rows.values() for row in group
                if code in _text(row.get("rule_id") or row.get("alert_type") or row.get("scanner_name") or row.get("name")).lower()
                or (code == "vap" and _text(row.get("rule_id")) == "HAI_VAP_BUNDLE_MISSING")
                or (code == "clabsi" and _text(row.get("rule_id")) == "HAI_CVC_REVIEW")
                or (code == "cauti" and _text(row.get("rule_id")) == "HAI_CAUTI_RISK")
            ]
            if related_alerts:
                for row in related_alerts:
                    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
                    missing = extra.get("missing_items") or extra.get("pending_items") or []
                    missing_text = " ".join(_text(item) for item in missing) if isinstance(missing, list) else _text(missing)
                    for item in item_rows:
                        if missing_text and _contains_any(missing_text, [item["name"].replace("30度", ""), item["name"].replace("q4h", "")]):
                            item["done"] = False
                            item["source"] = _text(row.get("rule_id")) or item["source"]
            complete = sum(1 for item in item_rows if item.get("done"))
            total = len(item_rows)
            has_any_source = any(_text(item.get("source")) for item in item_rows) or bool(related_alerts)
            tone = "green" if complete == total else "yellow" if complete >= max(1, total // 2) else "red"
            bundles.append({"code": code, "name": name, "completed": complete, "total": total, "tone": tone, "data_state": "synced" if has_any_source else "missing", "items": item_rows})
        return {"bundles": bundles}

    async def _nursing_workload(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        alert_keys = self._alert_keys_for_patient_ids(patients_by_id or {}, patient_ids) if patients_by_id else patient_ids
        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": alert_keys}, "$or": [{"rule_id": "scanner_nursing_workload"}, {"alert_type": "scanner_nursing_workload"}, {"scanner_name": "scanner_nursing_workload"}]},
            {"extra": 1, "created_at": 1},
        ).sort("created_at", -1).limit(50)
        used = 0
        estimated = 0
        async for row in cursor:
            extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
            for key in ("used_minutes", "spent_minutes", "completed_minutes", "workload_minutes"):
                if extra.get(key) in (None, ""):
                    continue
                try:
                    used += int(float(extra.get(key)))
                    break
                except Exception:
                    pass
            try:
                estimated += int(float(extra.get("predicted_next_shift_minutes") or extra.get("predicted_minutes") or 0))
            except Exception:
                pass
        estimated = estimated or max(0, len(patient_ids) * 60)
        return {"used_minutes": used, "estimated_minutes": estimated, "percent": min(100, round(used * 100 / estimated)) if estimated else 0}

    def _nursing_alert_allowed(self, row: dict[str, Any]) -> bool:
        text = " ".join(_text(row.get(k)) for k in ("name", "alert_type", "rule_id", "scanner_name")).lower()
        blocked = ["diagnosis", "诊断", "抗生素更换", "升压药", "医嘱", "会诊", "clinical_reasoning"]
        allowed = ["复测", "生命体征", "镇静", "入量", "出量", "管路", "皮肤", "压力", "尿量", "护理", "bundle", "rass", "cam"]
        return any(k.lower() in text for k in allowed) and not any(k.lower() in text for k in blocked)

    async def _nurse_ai_reminders(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]], shift: ShiftInfo) -> list[dict[str, Any]]:
        if not patient_ids:
            return []
        alert_keys = self._alert_keys_for_patient_ids(patients_by_id, patient_ids)
        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": alert_keys}, "created_at": {"$gte": shift.start}},
            {"name": 1, "rule_id": 1, "alert_type": 1, "scanner_name": 1, "patient_id": 1, "severity": 1, "created_at": 1},
        ).sort("created_at", -1).limit(80)
        alerts = [row async for row in cursor]
        return [row for row in alerts if self._nursing_alert_allowed(row)][:8]

    async def nurse_home(self, user_id: str, shift_code: str | None = "auto", *, view: str | None = None, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        dept, dept_code = self._account_scoped_dept(account, dept=dept, dept_code=dept_code)
        shift = await self.shift_service.resolve_shift(shift_code)
        if not shift:
            return {"account": account, "shift": None, "beds": [], "degraded": "未配置 banCiInfoList，无法识别当前班次。"}
        timeline = await self.nurse_timeline(user_id, shift, dept=dept, dept_code=dept_code)
        patient_ids = [row["patient_id"] for row in timeline.get("beds") or []]
        patients_by_id = timeline.get("_patients_by_id") or {}
        if patient_ids and not patients_by_id:
            patients_by_id = await self._patients_by_ids(patient_ids, dept=dept, dept_code=dept_code)
        workload_task = self._nursing_workload(patient_ids, patients_by_id)
        reminders_task = self._nurse_ai_reminders(patient_ids, patients_by_id, shift)
        bundles_task = self.nurse_bundles(patient_ids, shift.code, patients_by_id, dept=dept, dept_code=dept_code)
        workload, nursing_alerts = await asyncio.gather(workload_task, reminders_task)
        bundle_degraded = ""
        try:
            bundles = await asyncio.wait_for(bundles_task, timeout=1.5)
        except Exception:
            bundle_degraded = "安全清单数据同步较慢，已先展示本班任务。"
            bundles = {"bundles": []}
        head_mode = view == "head" or account.get("role") in {"head_nurse", "charge_nurse"}
        head = None
        head_degraded = ""
        if head_mode:
            try:
                head = await asyncio.wait_for(self._head_nurse_view(shift, dept=dept, dept_code=dept_code), timeout=1.5)
            except Exception:
                head_degraded = "护士长扩展数据同步较慢，已先展示床位和任务。"
        return {
            "account": account,
            "shift": shift.to_dict(),
            "data_state": {
                "account_found": bool(account.get("found")),
                "dept": dept,
                "dept_code": dept_code,
                "assigned_beds": len(timeline.get("beds") or []),
                "pending_handover_beds": len(timeline.get("pending_handover") or []),
                "empty_reason": "" if timeline.get("beds") else "本班次尚未找到第一条护理记录归属当前护士；护士长视图仍可查看全科。",
            },
            "beds": timeline.get("beds") or [],
            "pending_handover": timeline.get("pending_handover") or [],
            "workload": workload,
            "timeline": timeline.get("tasks") or [],
            "bundles": bundles.get("bundles") or [],
            "bundle_degraded": bundle_degraded,
            "ai_reminders": nursing_alerts,
            "head_view": head,
            "head_degraded": head_degraded,
            "generated_at": datetime.now(API_TZ),
        }

    async def _patients_by_ids(self, patient_ids: list[str], *, dept: str | None = None, dept_code: str | None = None) -> dict[str, dict[str, Any]]:
        if not patient_ids:
            return {}
        result: dict[str, dict[str, Any]] = {}
        dept_scope = self._department_scope_query(dept=dept, dept_code=dept_code)
        # 分离 ObjectId 和字符串 ID
        oid_ids = [pid for pid in patient_ids if ObjectId.is_valid(pid)]
        str_ids = [pid for pid in patient_ids if not ObjectId.is_valid(pid)]
        or_clauses: list[dict[str, Any]] = []
        if oid_ids:
            or_clauses.append({"_id": {"$in": [ObjectId(pid) for pid in oid_ids]}})
        if str_ids:
            or_clauses.extend([
                {"_id": {"$in": str_ids}},
                {"pid": {"$in": str_ids}},
                {"hisPid": {"$in": str_ids}},
                {"patientId": {"$in": str_ids}},
            ])
        if not or_clauses:
            return {}
        query: dict[str, Any] = {"$or": or_clauses}
        if dept_scope:
            query = {"$and": [query, dept_scope]}
        cursor = self.db.col("patient").find(query).limit(len(patient_ids) + 10)
        async for row in cursor:
            result[_patient_id(row)] = row
        return result

    async def _head_nurse_view(self, shift: ShiftInfo, *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        query = self._with_department_scope(admitted_patient_query(), dept=dept, dept_code=dept_code)
        all_patients = [row async for row in self.db.col("patient").find(query, {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "pid": 1, "dept": 1, "hisDept": 1, "deptCode": 1}).limit(160)]
        patients_by_id = {_patient_id(row): row for row in all_patients if _patient_id(row)}
        patient_ids = list(patients_by_id.keys())
        if (dept or dept_code) and not patient_ids:
            return {"beds": [], "workload_heatmap": [], "events": [], "quality": {"falls": 0, "pressure_ulcers": 0, "line_displacement": 0, "medication_errors": 0}}
        record_query: dict[str, Any] = self._record_time_query(shift.start, shift.end)
        if patients_by_id:
            patient_keys = self._alert_keys_for_patient_ids(patients_by_id, patient_ids)
            record_query = {
                "$and": [
                    record_query,
                    {"$or": [{"pid": {"$in": patient_keys}}, {"patient_id": {"$in": patient_keys}}, {"patientId": {"$in": patient_keys}}, {"hisPid": {"$in": patient_keys}}]},
                ]
            }
        quality_keywords = {
            "falls": ["跌倒", "坠床"],
            "pressure_ulcers": ["压疮", "压力性损伤"],
            "line_displacement": ["管路脱出", "非计划拔管", "脱管"],
            "medication_errors": ["给药差错", "用药错误"],
        }
        default_quality = {key: 0 for key in quality_keywords}

        async def build_workload_and_quality() -> tuple[list[dict[str, Any]], dict[str, int]]:
            counts: dict[str, int] = {}
            hourly: dict[str, dict[str, int]] = {}
            quality = dict(default_quality)
            projection = {"userName": 1, "username": 1, "trueName": 1, "userId": 1, "recordTime": 1, "time": 1, "content": 1, "recordTitle": 1, "title": 1, "careType": 1}
            cursor = self.db.col("nurseRecords").find(record_query, projection).limit(1200)
            async for row in cursor:
                name = self._record_user_name(row) or self._record_user_id(row) or "未识别护士"
                counts[name] = counts.get(name, 0) + 1
                when = _dt(row.get("recordTime") or row.get("time"))
                bucket = _as_api_tz(when).strftime("%H:00") if when else "未识别"
                hourly.setdefault(name, {})[bucket] = hourly.setdefault(name, {}).get(bucket, 0) + 1
                text = " ".join(_text(row.get(key)) for key in ("content", "recordTitle", "title", "careType"))
                for key, keywords in quality_keywords.items():
                    if _contains_any(text, keywords):
                        quality[key] += 1
            heatmap = [
                {
                    "nurse": nurse,
                    "task_density": count,
                    "tone": "high" if count > 20 else "medium" if count > 8 else "low",
                    "buckets": [{"time": key, "count": value} for key, value in sorted(hourly.get(nurse, {}).items())],
                }
                for nurse, count in sorted(counts.items(), key=lambda item: -item[1])
            ]
            return heatmap, quality

        async def build_events() -> list[dict[str, Any]]:
            events: list[dict[str, Any]] = []
            if not patient_ids:
                return events
            alert_keys = self._alert_keys_for_patient_ids(patients_by_id, patient_ids)
            cursor_alerts = self.db.col("alert_records").find(
                {"patient_id": {"$in": alert_keys}, "created_at": {"$gte": shift.start}, "$or": [{"acknowledged_at": {"$exists": False}}, {"acknowledged_at": None}, {"ack_disposition": {"$in": [None, ""]}}]},
                {"patient_id": 1, "name": 1, "rule_id": 1, "alert_type": 1, "scanner_name": 1, "severity": 1, "created_at": 1},
            ).sort("created_at", -1).limit(80)
            async for row in cursor_alerts:
                if not self._nursing_alert_allowed(row):
                    continue
                pid = self._patient_id_from_alert_key(patients_by_id, row.get("patient_id"))
                patient = patients_by_id.get(pid, {})
                events.append(
                    {
                        "type": "未闭环护理提醒",
                        "patient_id": pid,
                        "bed": _bed(patient),
                        "name": _name(patient),
                        "title": _text(row.get("name") or row.get("alert_type") or row.get("rule_id")) or "护理提醒",
                        "severity": _text(row.get("severity") or "warning"),
                        "time": row.get("created_at"),
                    }
                )
                if len(events) >= 12:
                    break
            return events

        heatmap: list[dict[str, Any]] = []
        quality = default_quality
        events: list[dict[str, Any]] = []
        try:
            heatmap, quality = await asyncio.wait_for(build_workload_and_quality(), timeout=0.8)
        except Exception:
            pass
        try:
            events = await asyncio.wait_for(build_events(), timeout=0.5)
        except Exception:
            pass
        return {
            "beds": [{"patient_id": _patient_id(row), "bed": _bed(row), "name": _name(row)} for row in all_patients],
            "workload_heatmap": heatmap,
            "events": events,
            "quality": quality,
        }

    async def execute_nurse_task(self, task_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        now = datetime.now(API_TZ)
        doc = {
            "task_id": _text(task_id),
            "pid": _text(payload.get("patient_id")),
            "patient_id": _text(payload.get("patient_id")),
            "recordTime": now,
            "time": now,
            "username": _text(payload.get("actor_name") or actor),
            "userId": _text(actor),
            "content": _text(payload.get("note") or payload.get("action") or "护理任务已执行"),
            "source": "role_home_timeline",
            "created_at": now,
        }
        action = _text(payload.get("action") or "executed")
        if action == "executed":
            await self.db.col("nurseRecords").insert_one(doc)
        await self.db.col("nursing_task_executions").update_one(
            {"task_id": _text(task_id)},
            {"$set": {**doc, "status": action, "updated_at": now}},
            upsert=True,
        )
        return {"task_id": _text(task_id), "status": action, "recorded_at": now, "nursing_record_written": action == "executed"}

    def _isbar_from_ipass(self, patient: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
        actions = summary.get("action_list") if isinstance(summary.get("action_list"), list) else []
        awareness = summary.get("situation_awareness") if isinstance(summary.get("situation_awareness"), list) else []
        severity = _text(summary.get("illness_severity") or "watcher")
        severity_label = {
            "stable": "稳定",
            "watcher": "需关注",
            "unstable": "不稳定",
            "critical": "危重",
        }.get(severity.lower(), severity or "需关注")
        return {
            "identify": f"{_bed(patient) or '--'}床 {_name(patient)}，当前病情：{severity_label}。",
            "situation": _text(summary.get("patient_summary")) or "本班需结合最新生命体征和护理记录交接。",
            "background": "；".join(_text(item) for item in awareness[:3] if _text(item)) or "基础诊断、管路、治疗和护理风险请接班后复核。",
            "assessment": "；".join(_text(item) for item in awareness[3:6] if _text(item)) or _text(summary.get("synthesis_by_receiver")) or "目前结构化数据有限，需床旁复核。",
            "recommendation": "；".join(_text(item) for item in actions[:4] if _text(item)) or "接班后优先核对生命体征、管路、皮肤、入出量和未完成任务。",
        }

    async def generate_nurse_handoff(self, user_id: str, patient_ids: list[str], shift_code: str | None = "auto", *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        dept, dept_code = self._account_scoped_dept(account, dept=dept, dept_code=dept_code)
        shift = await self.shift_service.resolve_shift(shift_code)
        rows = []
        dept_scope = self._department_scope_query(dept=dept, dept_code=dept_code)
        for pid in patient_ids[:8]:
            patient_query = {"_id": ObjectId(pid)} if ObjectId.is_valid(pid) else {"$or": [{"_id": pid}, {"pid": pid}, {"hisPid": pid}]}
            if dept_scope:
                patient_query = {"$and": [patient_query, dept_scope]}
            patient = await self.db.col("patient").find_one(patient_query)
            if not patient:
                continue
            summary = None
            if self.ai_handoff_service and self.llm_call:
                try:
                    generated = await self.ai_handoff_service.generate(patient_id=pid, patient_doc=patient, nursing_context={"shift": shift.to_dict() if shift else None}, llm_call=self.llm_call)
                    summary = generated.get("summary")
                except Exception:
                    summary = None
            if not summary:
                summary = {
                    "illness_severity": "watcher",
                    "patient_summary": f"{_bed(patient)}床 {_name(patient)}，本班交班需结合最新生命体征、护理记录和未闭环提醒复核。",
                    "action_list": ["核对本班未完成护理任务。"],
                    "situation_awareness": ["AI 交班生成服务不可用时使用结构化兜底摘要。"],
                    "synthesis_by_receiver": "请下一班接班后复核床旁监护、管路、皮肤和入出量。",
                    "confidence_level": "low",
                }
            rows.append({"patient_id": pid, "bed": _bed(patient), "name": _name(patient), "ipass": summary, "isbar": self._isbar_from_ipass(patient, summary)})
        doc = {"handoff_id": str(uuid.uuid4()), "user_id": _text(user_id), "userName": account.get("userName"), "dept": dept, "dept_code": dept_code, "shift": shift.to_dict() if shift else None, "items": rows, "created_at": datetime.now(API_TZ)}
        await self.db.col("handoff_record").insert_one(doc)
        return doc

    async def head_nurse_home(self, user_id: str, shift_code: str | None = "auto", *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        dept, dept_code = self._account_scoped_dept(account, dept=dept, dept_code=dept_code)
        shift = await self.shift_service.resolve_shift(shift_code)
        if not shift:
            return {"account": account, "shift": None, "beds": [], "degraded": "未配置 banCiInfoList，无法识别当前班次。"}

        # 复用 _head_nurse_view 获取全科床位、热力图、质控事件
        head_view_task = self._head_nurse_view(shift, dept=dept, dept_code=dept_code)
        # 获取全科患者用于后续聚合
        query = self._with_department_scope(admitted_patient_query(), dept=dept, dept_code=dept_code)
        all_patients = [row async for row in self.db.col("patient").find(query, {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "pid": 1, "dept": 1, "hisDept": 1, "deptCode": 1}).limit(160)]
        patients_by_id = {_patient_id(row): row for row in all_patients if _patient_id(row)}
        patient_ids = list(patients_by_id.keys())

        # 并行获取所有数据
        workload_task = self._nursing_workload(patient_ids, patients_by_id)
        compliance_task = self._assessment_compliance_stats(patient_ids, shift)
        alert_task = self._alert_handling_stats(patient_ids, patients_by_id, shift)
        scanner_task = self.outcomes.scanner_health(days=7, dept=dept, dept_code=dept_code)

        head_view, workload, assessment_compliance, alert_stats, scanner_health = await asyncio.gather(
            head_view_task, workload_task, compliance_task, alert_task, scanner_task,
            return_exceptions=True,
        )
        # 降级处理
        if isinstance(head_view, Exception):
            head_view = {"beds": [], "workload_heatmap": [], "events": [], "quality": {}}
        if isinstance(workload, Exception):
            workload = {"used_minutes": 0, "estimated_minutes": 0, "percent": 0}
        if isinstance(assessment_compliance, Exception):
            assessment_compliance = {"total_reminders": 0, "active_overdue": 0, "resolved_ontime": 0, "compliance_rate": 0.0, "by_type": []}
        if isinstance(alert_stats, Exception):
            alert_stats = {"total_alerts": 0, "handled": 0, "pending": 0, "handle_rate": 0.0, "avg_response_minutes": 0.0}
        if isinstance(scanner_health, Exception):
            scanner_health = {"rows": []}

        data_state = {
            "account_found": bool(account.get("found")),
            "dept": dept,
            "dept_code": dept_code,
            "total_beds": len(all_patients),
            "empty_reason": "" if all_patients else "当前科室暂无在科患者。",
        }

        return {
            "account": account,
            "shift": shift.to_dict(),
            "data_state": data_state,
            "beds": head_view.get("beds", []),
            "pending_handover": [{"patient_id": pid, "bed": _bed(patients_by_id.get(pid, {})), "name": _name(patients_by_id.get(pid, {}))} for pid in patient_ids if pid not in {b.get("patient_id") for b in head_view.get("beds", [])}],
            "workload": {
                **workload,
                "heatmap": head_view.get("workload_heatmap", []),
            },
            "assessment_compliance": assessment_compliance,
            "alert_stats": alert_stats,
            "quality_events": head_view.get("events", []),
            "quality_summary": head_view.get("quality", {}),
            "scanner_health": scanner_health,
            "generated_at": datetime.now(API_TZ),
        }

    async def _assessment_compliance_stats(self, patient_ids: list[str], shift: ShiftInfo) -> dict[str, Any]:
        """统计评估依从率"""
        if not patient_ids:
            return {"total_reminders": 0, "active_overdue": 0, "resolved_ontime": 0, "compliance_rate": 0.0, "by_type": []}

        # 查询本班次的提醒
        cursor = self.db.col("nurse_reminders").find(
            {"patient_id": {"$in": patient_ids}},
            {"patient_id": 1, "score_type": 1, "is_active": 1, "due_at": 1, "resolved_at": 1, "name": 1}
        ).limit(500)

        reminders = [row async for row in cursor]
        if not reminders:
            return {"total_reminders": 0, "active_overdue": 0, "resolved_ontime": 0, "compliance_rate": 0.0, "by_type": []}

        # 按 score_type 分组统计
        by_type: dict[str, dict[str, Any]] = {}
        total = len(reminders)
        active_overdue = 0
        resolved_ontime = 0

        for row in reminders:
            score_type = _text(row.get("score_type"))
            if not score_type:
                continue
            if score_type not in by_type:
                by_type[score_type] = {"score_type": score_type, "title": _text(row.get("name")) or score_type, "total": 0, "overdue": 0}
            by_type[score_type]["total"] += 1

            if row.get("is_active"):
                active_overdue += 1
                by_type[score_type]["overdue"] += 1
            else:
                resolved_ontime += 1

        # 计算每个类型的依从率
        for item in by_type.values():
            item["compliance_rate"] = round((1 - item["overdue"] / item["total"]) * 100, 1) if item["total"] > 0 else 0.0

        compliance_rate = round(resolved_ontime / total * 100, 1) if total > 0 else 0.0

        return {
            "total_reminders": total,
            "active_overdue": active_overdue,
            "resolved_ontime": resolved_ontime,
            "compliance_rate": compliance_rate,
            "by_type": sorted(by_type.values(), key=lambda x: -x.get("overdue", 0)),
        }

    async def _alert_handling_stats(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]], shift: ShiftInfo) -> dict[str, Any]:
        """统计告警处置率和响应时长"""
        if not patient_ids:
            return {"total_alerts": 0, "handled": 0, "pending": 0, "handle_rate": 0.0, "avg_response_minutes": 0.0}

        alert_keys = self._alert_keys_for_patient_ids(patients_by_id, patient_ids)
        since = shift.start - timedelta(hours=12)

        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": alert_keys}, "created_at": {"$gte": since}},
            {"created_at": 1, "acknowledged_at": 1, "ack_disposition": 1}
        ).sort("created_at", -1).limit(1000)

        alerts = [row async for row in cursor]
        if not alerts:
            return {"total_alerts": 0, "handled": 0, "pending": 0, "handle_rate": 0.0, "avg_response_minutes": 0.0}

        total = len(alerts)
        handled = 0
        response_times = []

        for row in alerts:
            if row.get("acknowledged_at") or row.get("ack_disposition"):
                handled += 1
                # 计算响应时长
                created = _dt(row.get("created_at"))
                acked = _dt(row.get("acknowledged_at"))
                if created and acked:
                    diff_minutes = (acked - created).total_seconds() / 60
                    if diff_minutes >= 0:
                        response_times.append(diff_minutes)

        pending = total - handled
        handle_rate = round(handled / total * 100, 1) if total > 0 else 0.0
        avg_response = round(sum(response_times) / len(response_times), 1) if response_times else 0.0

        return {
            "total_alerts": total,
            "handled": handled,
            "pending": pending,
            "handle_rate": handle_rate,
            "avg_response_minutes": avg_response,
        }

    async def director_home(self, user_id: str, *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        dept, dept_code = self._account_scoped_dept(account, dept=dept, dept_code=dept_code)
        shift = await self.shift_service.get_current_shift()

        # 获取全科患者
        query = self._with_department_scope(admitted_patient_query(), dept=dept, dept_code=dept_code)
        all_patients = [row async for row in self.db.col("patient").find(query, {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "pid": 1, "dept": 1, "hisDept": 1, "deptCode": 1, "bedDoctorId": 1}).limit(200)]
        patients_by_id = {_patient_id(row): row for row in all_patients if _patient_id(row)}
        patient_ids = list(patients_by_id.keys())

        # 并行获取所有数据
        overview_task = self._department_overview(all_patients, dept, dept_code)
        quality_task = self._quality_dashboard(patient_ids, patients_by_id, dept, dept_code)
        kpi_task = self._kpi_summary(patient_ids, patients_by_id)
        research_task = self._research_summary(user_id)
        role_task = self._role_distribution(dept, dept_code)

        department_overview, quality_dashboard, kpi_summary, research_summary, role_distribution = await asyncio.gather(
            overview_task, quality_task, kpi_task, research_task, role_task,
            return_exceptions=True,
        )
        # 降级处理
        if isinstance(department_overview, Exception):
            department_overview = {"total_beds": 0, "occupied_beds": 0, "occupancy_rate": 0, "doctors": [], "nurses": []}
        if isinstance(quality_dashboard, Exception):
            quality_dashboard = {"period_days": 7, "scanner_health": {"rows": []}, "adjudication_summary": {}, "quality_events": {}}
        if isinstance(kpi_summary, Exception):
            kpi_summary = {"alert_stats": {}, "ai_stats": {}, "adjudication_stats": {}, "workload_stats": {}}
        if isinstance(research_summary, Exception):
            research_summary = {"total": 0, "pending": 0, "completed": 0, "recent_exports": []}
        if isinstance(role_distribution, Exception):
            role_distribution = {"doctors": 0, "nurses": 0, "pharmacists": 0, "head_nurses": 0}

        data_state = {
            "account_found": bool(account.get("found")),
            "dept": dept,
            "dept_code": dept_code,
            "total_beds": len(all_patients),
            "empty_reason": "" if all_patients else "当前科室暂无在科患者。",
        }

        return {
            "account": account,
            "shift": shift.to_dict() if shift else None,
            "data_state": data_state,
            "department_overview": department_overview,
            "quality_dashboard": quality_dashboard,
            "kpi_summary": kpi_summary,
            "research_summary": research_summary,
            "role_distribution": role_distribution,
            "generated_at": datetime.now(API_TZ),
        }

    async def _department_overview(self, all_patients: list[dict[str, Any]], dept: str | None, dept_code: str | None) -> dict[str, Any]:
        """科室概览：床位使用率、医生/护士分布"""
        total_beds = len(all_patients)
        occupied_beds = total_beds  # admitted_patient_query 已过滤在科患者

        # 统计医生分管床位
        doctor_beds: dict[str, list[str]] = {}
        for patient in all_patients:
            doctor_id = _text(patient.get("bedDoctorId"))
            if doctor_id:
                doctor_beds.setdefault(doctor_id, []).append(_bed(patient))

        # 批量获取医生信息（避免 N+1）
        doctors = []
        if doctor_beds:
            doctor_ids = list(doctor_beds.keys())
            or_clauses: list[dict[str, Any]] = [
                {"userId": {"$in": doctor_ids}},
                {"userName": {"$in": doctor_ids}},
                {"username": {"$in": doctor_ids}},
                {"trueName": {"$in": doctor_ids}},
            ]
            # 也尝试 ObjectId 匹配
            oid_ids = [did for did in doctor_ids if ObjectId.is_valid(did)]
            if oid_ids:
                or_clauses.append({"_id": {"$in": [ObjectId(did) for did in oid_ids]}})
            account_map: dict[str, dict[str, Any]] = {}
            try:
                cursor = self.db.col("account").find({"$or": or_clauses}).limit(len(doctor_ids) + 5)
                async for row in cursor:
                    for key in ("userId", "userName", "username", "trueName", "_id"):
                        val = _text(row.get(key))
                        if val and val in doctor_beds:
                            account_map[val] = row
            except Exception:
                pass
            for doctor_id, beds in doctor_beds.items():
                account = account_map.get(doctor_id, {})
                doctors.append({
                    "user_id": doctor_id,
                    "name": _text(account.get("trueName") or account.get("userName") or account.get("name")) or doctor_id,
                    "managed_beds": len(beds),
                })

        # 统计护士（从护理记录推断）
        nurse_beds: dict[str, int] = {}
        since = datetime.now(API_TZ) - timedelta(hours=8)
        try:
            cursor = self.db.col("nurseRecords").find(
                {"created_at": {"$gte": since}},
                {"userId": 1, "userName": 1, "trueName": 1, "pid": 1}
            ).limit(2000)
            async for row in cursor:
                nurse_id = _text(row.get("userId") or row.get("userName") or row.get("trueName"))
                if nurse_id:
                    nurse_beds[nurse_id] = nurse_beds.get(nurse_id, 0) + 1
        except Exception:
            pass

        nurses = [{"user_id": nid, "name": nid, "assigned_beds": count} for nid, count in sorted(nurse_beds.items(), key=lambda x: -x[1])[:20]]

        return {
            "total_beds": total_beds,
            "occupied_beds": occupied_beds,
            "occupancy_rate": round(occupied_beds / total_beds * 100, 1) if total_beds > 0 else 0.0,
            "doctors": sorted(doctors, key=lambda x: -x.get("managed_beds", 0)),
            "nurses": nurses,
        }

    async def _quality_dashboard(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]], dept: str | None, dept_code: str | None) -> dict[str, Any]:
        """质控大屏：scanner_health + adjudication_summary + quality_events"""
        scanner_health = await self.outcomes.scanner_health(days=7, dept=dept, dept_code=dept_code)

        # Adjudication stats from alert_adjudications (NOT adoption_summary)
        since_7d = datetime.now(API_TZ) - timedelta(days=7)
        adj_count = await self.db.col("alert_adjudications").count_documents(
            {"created_at": {"$gte": since_7d}},
        )
        adj_tp = await self.db.col("alert_adjudications").count_documents(
            {"created_at": {"$gte": since_7d}, "alert_validity": "true_positive"},
        )
        adj_fp = await self.db.col("alert_adjudications").count_documents(
            {"created_at": {"$gte": since_7d}, "alert_validity": "false_positive"},
        )
        determinate = adj_tp + adj_fp
        adj_ppv = round(adj_tp / determinate, 3) if determinate > 0 else None

        adjudication_summary = {
            "total_formally_reviewed": adj_count,
            "determinate": determinate,
            "true_positive": adj_tp,
            "false_positive": adj_fp,
            "reviewed_sample_ppv": adj_ppv,
            "note": "Based on formal adjudications only — feedback excluded. PPV=TP/(TP+FP).",
        }

        quality_events = {"falls": 0, "pressure_ulcers": 0, "line_displacement": 0, "medication_errors": 0}
        if patient_ids:
            try:
                head_view = await asyncio.wait_for(self._head_nurse_view(await self.shift_service.get_current_shift(), dept=dept, dept_code=dept_code), timeout=1.0)
                quality_events = head_view.get("quality", quality_events)
            except Exception:
                pass

        return {
            "period_days": 7,
            "scanner_health": scanner_health,
            "adjudication_summary": adjudication_summary,
            "quality_events": quality_events,
        }

    async def _kpi_summary(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """KPI 摘要：告警统计、AI推理、人工复核、护理负荷"""
        if not patient_ids:
            return {"alert_stats": {}, "ai_stats": {}, "adjudication_stats": {}, "workload_stats": {}}

        alert_keys = self._alert_keys_for_patient_ids(patients_by_id, patient_ids)
        since_24h = datetime.now(API_TZ) - timedelta(hours=24)

        # 告警统计
        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": alert_keys}, "created_at": {"$gte": since_24h}},
            {"acknowledged_at": 1, "ack_disposition": 1, "rule_id": 1, "heuristic_attention_score": 1, "manual_adjudication": 1, "action_linkage": 1},
        ).limit(2000)

        total_24h = 0
        handled_24h = 0
        integrated_reasoning = 0
        suspected_linkage = 0
        clinician_confirmed = 0

        async for row in cursor:
            total_24h += 1
            if row.get("acknowledged_at") or row.get("ack_disposition"):
                handled_24h += 1
            if _text(row.get("rule_id")) == "INTEGRATED_RISK_REASONING":
                integrated_reasoning += 1
            linkage = row.get("action_linkage")
            if isinstance(linkage, dict):
                suspected_linkage += 1
                if linkage.get("status") == "clinician_confirmed":
                    clinician_confirmed += 1

        pending_24h = total_24h - handled_24h
        handle_rate = round(handled_24h / total_24h * 100, 1) if total_24h > 0 else 0.0

        # 人工复核统计（最近24小时内）
        adj_count = await self.db.col("alert_adjudications").count_documents(
            {"patient_id": {"$in": alert_keys}, "created_at": {"$gte": since_24h}},
        )

        # 护理负荷
        workload = await self._nursing_workload(patient_ids, patients_by_id)

        return {
            "alert_stats": {
                "total_24h": total_24h,
                "handled_24h": handled_24h,
                "pending_24h": pending_24h,
                "handle_rate": handle_rate,
                "suspected_linkage": suspected_linkage,
                "clinician_confirmed_linkage": clinician_confirmed,
            },
            "ai_stats": {
                "integrated_reasoning": integrated_reasoning,
                "note": "AI推理生成数（adopted字段仅表示前端点击，非临床确认采纳）",
            },
            "adjudication_stats": {
                "total_24h": adj_count,
                "note": "人工复核数 — 此为正式统计口径。快速反馈不计入。",
            },
            "workload_stats": {
                "avg_nursing_workload_percent": workload.get("percent", 0),
                "high_workload_beds": len([p for p in patient_ids if workload.get("percent", 0) > 80]),
            },
        }

    async def _research_summary(self, user_id: str) -> dict[str, Any]:
        """科研动态：从 research_platform_service 获取"""
        try:
            from app.services.research_platform_service import job_summary
            return await job_summary(db=self.db, user_id=user_id)
        except Exception:
            return {"total": 0, "pending": 0, "completed": 0, "recent_exports": []}

    async def _role_distribution(self, dept: str | None, dept_code: str | None) -> dict[str, Any]:
        """角色分布：从 account 集合统计"""
        try:
            query: dict[str, Any] = {}
            if dept_code:
                query["deptCode"] = dept_code
            elif dept:
                query["$or"] = [{"dept": dept}, {"deptName": dept}]

            cursor = self.db.col("account").find(query, {"role": 1}).limit(500)
            roles: dict[str, int] = {}
            async for row in cursor:
                role = _text(row.get("role")) or "unknown"
                roles[role] = roles.get(role, 0) + 1

            return {
                "doctors": roles.get("doctor", 0),
                "nurses": roles.get("nurse", 0) + roles.get("head_nurse", 0) + roles.get("charge_nurse", 0),
                "pharmacists": roles.get("pharmacist", 0),
                "head_nurses": roles.get("head_nurse", 0) + roles.get("charge_nurse", 0),
            }
        except Exception:
            return {"doctors": 0, "nurses": 0, "pharmacists": 0, "head_nurses": 0}

    async def compliance_dashboard(self, user_id: str, shift_code: str | None = "auto", *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        """护理依从性看板：时间线热力图 + 逾期TOP床位 + 班次对比"""
        account = await self._account_by_user_id(user_id)
        dept, dept_code = self._account_scoped_dept(account, dept=dept, dept_code=dept_code)
        shift = await self.shift_service.resolve_shift(shift_code)
        if not shift:
            return {"account": account, "shift": None, "degraded": "未配置 banCiInfoList，无法识别当前班次。"}

        # 获取全科患者
        query = self._with_department_scope(admitted_patient_query(), dept=dept, dept_code=dept_code)
        all_patients = [row async for row in self.db.col("patient").find(query, {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "pid": 1}).limit(160)]
        patients_by_id = {_patient_id(row): row for row in all_patients if _patient_id(row)}
        patient_ids = list(patients_by_id.keys())

        if not patient_ids:
            return {
                "account": account,
                "shift": shift.to_dict(),
                "compliance_overview": self._empty_compliance_overview(),
                "heatmap": [],
                "overdue_top_beds": [],
                "by_type_comparison": [],
                "generated_at": datetime.now(API_TZ),
            }

        # 获取上班次信息
        prev_shift = await self._get_previous_shift(shift)

        # 并行查询数据
        current_reminders_task = self._query_shift_reminders(patient_ids, shift)
        prev_reminders_task = self._query_shift_reminders(patient_ids, prev_shift) if prev_shift else asyncio.sleep(0, result=[])
        heatmap_task = self._query_heatmap_data(patient_ids, shift)

        current_reminders, prev_reminders, heatmap_data = await asyncio.gather(
            current_reminders_task, prev_reminders_task, heatmap_task
        )

        # 计算当前班次统计
        current_stats = self._calculate_shift_stats(current_reminders, shift)
        prev_stats = self._calculate_shift_stats(prev_reminders, prev_shift) if prev_shift else self._empty_shift_stats()

        # 计算趋势
        trend = round(current_stats["compliance_rate"] - prev_stats["compliance_rate"], 1)
        trend_text = f"+{trend}%" if trend >= 0 else f"{trend}%"

        # 逾期TOP床位
        overdue_top_beds = await self._get_overdue_top_beds(patient_ids, patients_by_id)

        # 按类型对比
        by_type_comparison = self._calculate_by_type_comparison(current_reminders, prev_reminders, shift, prev_shift)

        return {
            "account": account,
            "shift": shift.to_dict(),
            "compliance_overview": {
                "current_shift": current_stats,
                "previous_shift": prev_stats,
                "trend": trend_text,
            },
            "heatmap": heatmap_data,
            "overdue_top_beds": overdue_top_beds,
            "by_type_comparison": by_type_comparison,
            "generated_at": datetime.now(API_TZ),
        }

    def _empty_compliance_overview(self) -> dict[str, Any]:
        """空的依从率概览"""
        return {
            "current_shift": self._empty_shift_stats(),
            "previous_shift": self._empty_shift_stats(),
            "trend": "0%",
        }

    def _empty_shift_stats(self) -> dict[str, Any]:
        """空的班次统计"""
        return {
            "total_expected": 0,
            "total_completed": 0,
            "total_overdue": 0,
            "compliance_rate": 0.0,
            "overdue_rate": 0.0,
            "avg_response_minutes": 0.0,
        }

    async def _get_previous_shift(self, current_shift: ShiftInfo) -> ShiftInfo | None:
        """获取上班次信息"""
        try:
            # 尝试获取上班次（通过 shift_service 的 shifts 列表）
            shifts = await self.shift_service.list_shifts()
            if not shifts or len(shifts) < 2:
                return None

            # 找到当前班次的索引
            current_idx = -1
            for i, s in enumerate(shifts):
                if s.get("code") == current_shift.code:
                    current_idx = i
                    break

            if current_idx <= 0:
                # 如果是第一个班次，取最后一个作为上班次
                prev_shift_data = shifts[-1]
            else:
                prev_shift_data = shifts[current_idx - 1]

            # 构建 ShiftInfo（简化版，仅用于查询）
            return ShiftInfo(
                code=prev_shift_data.get("code", ""),
                name=prev_shift_data.get("name", ""),
                start_time=prev_shift_data.get("start_time", ""),
                end_time=prev_shift_data.get("end_time", ""),
                start=current_shift.start - timedelta(hours=12),  # 简化：向前推12小时
                end=current_shift.start,
            )
        except Exception:
            return None

    async def _query_shift_reminders(self, patient_ids: list[str], shift: ShiftInfo | None) -> list[dict[str, Any]]:
        """查询班次内的提醒数据"""
        if not shift or not patient_ids:
            return []

        try:
            cursor = self.db.col("nurse_reminders").find(
                {
                    "patient_id": {"$in": patient_ids},
                    "$or": [
                        {"created_at": {"$gte": shift.start, "$lt": shift.end}},
                        {"resolved_at": {"$gte": shift.start, "$lt": shift.end}},
                        {"is_active": True, "due_at": {"$lt": datetime.now(API_TZ)}},
                    ],
                },
                {
                    "patient_id": 1,
                    "patient_name": 1,
                    "bed": 1,
                    "score_type": 1,
                    "is_active": 1,
                    "due_at": 1,
                    "resolved_at": 1,
                    "last_score_time": 1,
                    "severity": 1,
                    "created_at": 1,
                },
            ).limit(1000)
            return [row async for row in cursor]
        except Exception:
            return []

    def _calculate_shift_stats(self, reminders: list[dict[str, Any]], shift: ShiftInfo | None) -> dict[str, Any]:
        """计算班次统计数据"""
        if not reminders:
            return self._empty_shift_stats()

        total = len(reminders)
        completed = sum(1 for r in reminders if not r.get("is_active"))
        overdue = sum(1 for r in reminders if r.get("is_active") and r.get("due_at") and r["due_at"] < datetime.now(API_TZ))

        # 计算响应时长
        response_times = []
        for r in reminders:
            if not r.get("is_active") and r.get("resolved_at") and r.get("due_at"):
                diff = (r["resolved_at"] - r["due_at"]).total_seconds() / 60
                if diff > 0:
                    response_times.append(diff)

        avg_response = round(sum(response_times) / len(response_times), 1) if response_times else 0.0
        compliance_rate = round(completed / total * 100, 1) if total > 0 else 0.0
        overdue_rate = round(overdue / total * 100, 1) if total > 0 else 0.0

        return {
            "total_expected": total,
            "total_completed": completed,
            "total_overdue": overdue,
            "compliance_rate": compliance_rate,
            "overdue_rate": overdue_rate,
            "avg_response_minutes": avg_response,
        }

    async def _query_heatmap_data(self, patient_ids: list[str], shift: ShiftInfo) -> list[dict[str, Any]]:
        """查询热力图数据（按小时聚合）"""
        if not patient_ids:
            return []

        try:
            # 按小时聚合查询
            pipeline = [
                {"$match": {
                    "patient_id": {"$in": patient_ids},
                    "created_at": {"$gte": shift.start, "$lt": shift.end},
                }},
                {"$addFields": {
                    "hour": {"$dateToString": {"format": "%H:00", "date": "$created_at"}},
                }},
                {"$group": {
                    "_id": {"hour": "$hour", "score_type": "$score_type"},
                    "total": {"$sum": 1},
                    "overdue": {"$sum": {"$cond": ["$is_active", 1, 0]}},
                    "completed": {"$sum": {"$cond": ["$is_active", 0, 1]}},
                }},
                {"$sort": {"_id.hour": 1, "_id.score_type": 1}},
            ]

            cursor = self.db.col("nurse_reminders").aggregate(pipeline)
            results = [row async for row in cursor]

            # 转换为前端需要的格式
            heatmap: dict[str, list[dict[str, Any]]] = {}
            for row in results:
                hour = row["_id"]["hour"]
                score_type = row["_id"]["score_type"]
                if hour not in heatmap:
                    heatmap[hour] = []

                total = row["total"]
                completed = row["completed"]
                overdue = row["overdue"]
                compliance_rate = round(completed / total * 100, 1) if total > 0 else 0.0

                heatmap[hour].append({
                    "score_type": score_type,
                    "label": self._score_type_label(score_type),
                    "total": total,
                    "completed": completed,
                    "overdue": overdue,
                    "compliance_rate": compliance_rate,
                })

            # 转换为数组格式
            return [{"hour": hour, "by_type": types} for hour, types in sorted(heatmap.items())]
        except Exception:
            return []

    def _score_type_label(self, score_type: str) -> str:
        """score_type 到中文标签的映射"""
        labels = {
            "gcs": "GCS评估",
            "rass": "RASS评估",
            "pain": "疼痛评估",
            "cpot": "CPOT评估",
            "bps": "BPS评估",
            "delirium": "谵妄评估",
            "braden": "Braden评估",
            "cam_icu": "CAM-ICU",
            "turning": "翻身",
            "early_mobility": "早期活动",
        }
        return labels.get(score_type, score_type)

    async def _get_overdue_top_beds(self, patient_ids: list[str], patients_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """获取逾期TOP床位"""
        if not patient_ids:
            return []

        try:
            now = datetime.now(API_TZ)
            pipeline = [
                {"$match": {
                    "patient_id": {"$in": patient_ids},
                    "is_active": True,
                    "due_at": {"$lt": now},
                }},
                {"$group": {
                    "_id": "$patient_id",
                    "bed": {"$first": "$bed"},
                    "name": {"$first": "$patient_name"},
                    "overdue_count": {"$sum": 1},
                    "overdue_types": {"$addToSet": "$score_type"},
                    "worst_severity": {"$max": "$severity"},
                    "latest_due_at": {"$min": "$due_at"},
                }},
                {"$sort": {"overdue_count": -1}},
                {"$limit": 10},
            ]

            cursor = self.db.col("nurse_reminders").aggregate(pipeline)
            results = [row async for row in cursor]

            top_beds = []
            for row in results:
                patient_id = row["_id"]
                patient = patients_by_id.get(patient_id, {})
                top_beds.append({
                    "patient_id": patient_id,
                    "bed": _text(row.get("bed") or patient.get("bed") or patient.get("hisBed")),
                    "name": _text(row.get("name") or patient.get("name") or patient.get("hisName")),
                    "overdue_count": row.get("overdue_count", 0),
                    "overdue_types": row.get("overdue_types", []),
                    "worst_severity": _text(row.get("worst_severity", "warning")),
                    "latest_due_at": row.get("latest_due_at"),
                })

            return top_beds
        except Exception:
            return []

    def _calculate_by_type_comparison(
        self,
        current_reminders: list[dict[str, Any]],
        prev_reminders: list[dict[str, Any]],
        current_shift: ShiftInfo | None,
        prev_shift: ShiftInfo | None,
    ) -> list[dict[str, Any]]:
        """计算按类型对比数据"""
        # 定义所有需要对比的类型
        score_types = ["assessment", "turning", "cam_icu", "early_mobility"]
        type_mapping = {
            "assessment": ["gcs", "rass", "pain", "cpot", "bps", "delirium", "braden"],
            "turning": ["turning"],
            "cam_icu": ["cam_icu"],
            "early_mobility": ["early_mobility"],
        }

        def calc_type_stats(reminders: list[dict[str, Any]], types: list[str]) -> dict[str, Any]:
            filtered = [r for r in reminders if r.get("score_type") in types]
            total = len(filtered)
            completed = sum(1 for r in filtered if not r.get("is_active"))
            overdue = sum(1 for r in filtered if r.get("is_active") and r.get("due_at") and r["due_at"] < datetime.now(API_TZ))
            compliance_rate = round(completed / total * 100, 1) if total > 0 else 0.0
            return {
                "expected": total,
                "completed": completed,
                "overdue": overdue,
                "compliance_rate": compliance_rate,
            }

        comparison = []
        for score_type in score_types:
            types = type_mapping[score_type]
            current = calc_type_stats(current_reminders, types)
            prev = calc_type_stats(prev_reminders, types)
            trend = round(current["compliance_rate"] - prev["compliance_rate"], 1)
            trend_text = f"+{trend}%" if trend >= 0 else f"{trend}%"

            comparison.append({
                "score_type": score_type,
                "label": self._score_type_label(score_type),
                "interval_hours": self._get_interval_hours(score_type),
                "current": current,
                "previous": prev,
                "trend": trend_text,
            })

        return comparison

    def _get_interval_hours(self, score_type: str) -> int:
        """获取评估间隔小时数"""
        intervals = {
            "assessment": 4,
            "turning": 2,
            "cam_icu": 8,
            "early_mobility": 8,
        }
        return intervals.get(score_type, 4)
