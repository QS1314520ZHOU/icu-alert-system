from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any
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
            "user_id": uid,
            "userName": row.get("userName") or row.get("username") or row.get("account") or uid,
            "trueName": row.get("trueName"),
            "display_name": row.get("trueName") or row.get("name") or row.get("realName") or row.get("userName") or uid,
            "role": role,
            "dept": row.get("deptName") or row.get("departmentName") or row.get("dept"),
            "dept_code": row.get("deptCode") or row.get("departmentCode"),
            "found": True,
        }

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

    async def _doctor_patients(self, user_id: str) -> list[dict[str, Any]]:
        query = {"$and": [admitted_patient_query(), {"bedDoctorId": _text(user_id)}]}
        cursor = self.db.col("patient").find(
            query,
            {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "bedNo": 1, "bedDoctorId": 1, "hisPid": 1, "hisPID": 1, "pid": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1},
        ).limit(120)
        return [row async for row in cursor]

    async def _latest_integrated_risk(self, patients: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for patient in patients:
            keys = self._patient_alert_keys(patient)
            if not keys:
                continue
            row = await self.db.col("alert_records").find_one(
                {"patient_id": {"$in": keys}, "rule_id": "INTEGRATED_RISK_REASONING"},
                sort=[("created_at", -1)],
            )
            if row:
                result[_patient_id(patient)] = row
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

    async def doctor_home(self, user_id: str) -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        shift = await self.shift_service.get_current_shift()
        patients = await self._doctor_patients(user_id)
        risk_by_patient = await self._latest_integrated_risk(patients)
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

        patient_keys: list[Any] = []
        for patient in patients:
            patient_keys.extend(self._patient_alert_keys(patient))
        since = datetime.now(API_TZ) - timedelta(hours=12)
        alerts = []
        if patient_keys:
            cursor = self.db.col("alert_records").find(
                {"patient_id": {"$in": patient_keys}, "created_at": {"$gte": since}},
                {"patient_id": 1, "rule_id": 1, "severity": 1, "created_at": 1, "acknowledged_at": 1, "ack_disposition": 1, "suppressed": 1, "auto_suppressed": 1, "pushed_at": 1, "clicked_at": 1, "adopted": 1},
            ).sort("created_at", -1).limit(1000)
            alerts = [row async for row in cursor]
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
        open_tasks = await self._open_tasks_for_patients([_patient_id(patient) for patient in patients])
        quality = await self.adoption.quality_summary(days=7, dept=account.get("dept"), dept_code=account.get("dept_code"))
        return {
            "account": account,
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

    def _record_time_query(self, start: datetime, end: datetime) -> dict[str, Any]:
        return {"$or": [{"recordTime": {"$gte": start, "$lt": end}}, {"time": {"$gte": start, "$lt": end}}, {"created_at": {"$gte": start, "$lt": end}}, {"createTime": {"$gte": start, "$lt": end}}]}

    async def nurse_patient_assignments(self, user_id: str, shift: ShiftInfo) -> dict[str, Any]:
        patients = [row async for row in self.db.col("patient").find(admitted_patient_query(), {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "hisPID": 1, "pid": 1}).limit(160)]
        assigned: list[dict[str, Any]] = []
        pending_handover: list[dict[str, Any]] = []
        for patient in patients:
            keys = self._patient_alert_keys(patient)
            query = {
                "$and": [
                    {"$or": [{"pid": {"$in": keys}}, {"patient_id": {"$in": keys}}, {"patientId": {"$in": keys}}, {"hisPid": {"$in": keys}}]},
                    self._record_time_query(shift.start, shift.end),
                ]
            }
            first = await self.db.col("nurseRecords").find_one(query, sort=[("recordTime", 1), ("time", 1), ("created_at", 1)])
            patient_row = {"patient_id": _patient_id(patient), "bed": _bed(patient), "name": _name(patient)}
            if not first:
                pending_handover.append(patient_row)
                continue
            owner_id = self._record_user_id(first)
            owner_name = self._record_user_name(first)
            if owner_id == _text(user_id) or owner_name == _text(user_id):
                assigned.append({**patient_row, "patient_doc": patient, "responsible_nurse": owner_name or owner_id, "first_record_time": first.get("recordTime") or first.get("time") or first.get("created_at")})
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

    async def nurse_timeline(self, user_id: str, shift_code: str | ShiftInfo | None = "auto") -> dict[str, Any]:
        if isinstance(shift_code, ShiftInfo):
            shift = shift_code
        else:
            shift = await self.shift_service.resolve_shift(shift_code)
        if not shift:
            return {"shift": None, "beds": [], "tasks": [], "degraded": "未配置 banCiInfoList，无法计算本班时间轴。"}
        assignments = await self.nurse_patient_assignments(user_id, shift)
        beds = assignments["assigned"]
        patients_by_id = {row["patient_id"]: row.get("patient_doc") for row in beds if row.get("patient_doc")}
        scanner_names = [
            "scanner_nurse_reminders", "NURSE_REMINDER", "scanner_vanco_tdm_closed_loop", "delirium_risk",
            "scanner_ventilator_weaning", "crrt_monitor", "fluid_balance", "scanner_nutrition_monitor",
        ]
        grouped = await self._latest_scores_by_patient([row["patient_id"] for row in beds], scanner_names, patients_by_id)
        tasks: list[dict[str, Any]] = []
        for bed in beds:
            pid = bed["patient_id"]
            rows = grouped.get(pid, [])
            seeds = rows[:8] or [
                {"name": "q2h 翻身", "rule_id": "scanner_nurse_reminders"},
                {"name": "q4h 口腔护理", "rule_id": "scanner_nurse_reminders"},
                {"name": "q-shift 评估", "rule_id": "scanner_nurse_reminders"},
            ]
            for idx, row in enumerate(seeds):
                due_at = shift.start + timedelta(minutes=30 + idx * 60)
                if due_at < datetime.now(API_TZ) - timedelta(hours=1):
                    due_at = datetime.now(API_TZ) + timedelta(minutes=10 + idx * 20)
                done = bool(row.get("acknowledged_at") or row.get("ack_disposition"))
                tasks.append(
                    {
                        "task_id": _text(row.get("_id")) or f"{pid}-{idx}",
                        "alert_id": _text(row.get("_id")) if row.get("_id") else "",
                        "patient_id": pid,
                        "bed": bed["bed"],
                        "patient_name": bed["name"],
                        "title": _text(row.get("name") or row.get("alert_type") or row.get("rule_id")) or "护理任务",
                        "source": _text(row.get("rule_id") or row.get("scanner_name") or row.get("alert_type")),
                        "due_at": due_at,
                        "status": self._task_status(due_at, done),
                        "detail": _text(((row.get("extra") or {}) if isinstance(row.get("extra"), dict) else {}).get("suggestion") or row.get("name")),
                    }
                )
        clean_beds = [{k: v for k, v in row.items() if k != "patient_doc"} for row in beds]
        return {"shift": shift.to_dict(), "beds": clean_beds, "pending_handover": assignments["pending_handover"], "tasks": tasks}

    async def nurse_bundles(self, patient_ids: list[str], shift_code: str | None = "auto", patients_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        rows = await self._latest_scores_by_patient(patient_ids, ["scanner_hai_bundle", "hai_bundle_monitor", "scanner_nurse_reminders"], patients_by_id)
        bundle_names = [
            ("vap", "VAP 预防清单", ["床头抬高30度", "口腔护理q4h", "声门下吸引", "镇静中断", "消化道溃疡预防"]),
            ("cauti", "CAUTI 预防", ["尿管必要性", "尿道口护理"]),
            ("clabsi", "CLABSI 预防", ["CVC必要性评估", "敷料评估"]),
            ("shift_assessment", "跌倒/压疮/约束/管路评估", ["跌倒", "压疮", "约束", "管路"]),
        ]
        bundles = []
        for code, name, items in bundle_names:
            related = [row for group in rows.values() for row in group if code in _text(row.get("rule_id") or row.get("alert_type") or row.get("scanner_name") or row.get("name")).lower() or name.split()[0].lower() in _text(row.get("name")).lower()]
            if not related:
                complete = 0
                data_state = "missing"
            else:
                missing_count = 0
                for row in related:
                    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
                    missing = extra.get("missing_items") or extra.get("pending_items") or []
                    if isinstance(missing, list):
                        missing_count += len(missing)
                    elif missing:
                        missing_count += 1
                complete = max(0, len(items) - min(len(items), missing_count))
                data_state = "synced"
            tone = "green" if complete == len(items) else "yellow" if complete >= max(1, len(items) // 2) else "red"
            bundles.append({"code": code, "name": name, "completed": complete, "total": len(items), "tone": tone, "data_state": data_state, "items": [{"name": item, "done": idx < complete} for idx, item in enumerate(items)]})
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

    async def nurse_home(self, user_id: str, shift_code: str | None = "auto", *, view: str | None = None) -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        shift = await self.shift_service.resolve_shift(shift_code)
        if not shift:
            return {"account": account, "shift": None, "beds": [], "degraded": "未配置 banCiInfoList，无法识别当前班次。"}
        timeline = await self.nurse_timeline(user_id, shift)
        patient_ids = [row["patient_id"] for row in timeline.get("beds") or []]
        patients_by_id = await self._patients_by_ids(patient_ids)
        workload = await self._nursing_workload(patient_ids, patients_by_id)
        bundles = await self.nurse_bundles(patient_ids, shift.code, patients_by_id)
        alerts = []
        if patient_ids:
            alert_keys = self._alert_keys_for_patient_ids(patients_by_id, patient_ids)
            cursor = self.db.col("alert_records").find({"patient_id": {"$in": alert_keys}, "created_at": {"$gte": shift.start}}, {"name": 1, "rule_id": 1, "alert_type": 1, "scanner_name": 1, "patient_id": 1, "severity": 1, "created_at": 1}).sort("created_at", -1).limit(80)
            alerts = [row async for row in cursor]
        nursing_alerts = [row for row in alerts if self._nursing_alert_allowed(row)][:8]
        head_mode = view == "head" or account.get("role") in {"head_nurse", "charge_nurse"}
        head = await self._head_nurse_view(shift) if head_mode else None
        return {
            "account": account,
            "shift": shift.to_dict(),
            "beds": timeline.get("beds") or [],
            "pending_handover": timeline.get("pending_handover") or [],
            "workload": workload,
            "timeline": timeline.get("tasks") or [],
            "bundles": bundles.get("bundles") or [],
            "ai_reminders": nursing_alerts,
            "head_view": head,
            "generated_at": datetime.now(API_TZ),
        }

    async def _patients_by_ids(self, patient_ids: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for pid in patient_ids:
            patient = await self.db.col("patient").find_one({"_id": ObjectId(pid)} if ObjectId.is_valid(pid) else {"$or": [{"_id": pid}, {"pid": pid}, {"hisPid": pid}, {"patientId": pid}]})
            if patient:
                result[_patient_id(patient)] = patient
        return result

    async def _head_nurse_view(self, shift: ShiftInfo) -> dict[str, Any]:
        all_patients = [row async for row in self.db.col("patient").find(admitted_patient_query(), {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisPid": 1, "pid": 1}).limit(160)]
        cursor = self.db.col("nurseRecords").find(self._record_time_query(shift.start, shift.end), {"userName": 1, "username": 1, "trueName": 1, "userId": 1, "recordTime": 1, "time": 1}).limit(3000)
        counts: dict[str, int] = {}
        async for row in cursor:
            name = self._record_user_name(row) or self._record_user_id(row) or "未识别护士"
            counts[name] = counts.get(name, 0) + 1
        heatmap = [{"nurse": nurse, "task_density": count, "tone": "high" if count > 20 else "medium" if count > 8 else "low"} for nurse, count in sorted(counts.items(), key=lambda item: -item[1])]
        return {
            "beds": [{"patient_id": _patient_id(row), "bed": _bed(row), "name": _name(row)} for row in all_patients],
            "workload_heatmap": heatmap,
            "events": [],
            "quality": {"falls": 0, "pressure_ulcers": 0, "line_displacement": 0, "medication_errors": 0},
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

    async def generate_nurse_handoff(self, user_id: str, patient_ids: list[str], shift_code: str | None = "auto") -> dict[str, Any]:
        account = await self._account_by_user_id(user_id)
        shift = await self.shift_service.resolve_shift(shift_code)
        rows = []
        for pid in patient_ids[:8]:
            patient = await self.db.col("patient").find_one({"_id": ObjectId(pid)} if ObjectId.is_valid(pid) else {"$or": [{"_id": pid}, {"pid": pid}, {"hisPid": pid}]})
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
            rows.append({"patient_id": pid, "bed": _bed(patient), "name": _name(patient), "ipass": summary})
        doc = {"handoff_id": str(uuid.uuid4()), "user_id": _text(user_id), "userName": account.get("userName"), "shift": shift.to_dict() if shift else None, "items": rows, "created_at": datetime.now(API_TZ)}
        await self.db.col("handoff_record").insert_one(doc)
        return doc
