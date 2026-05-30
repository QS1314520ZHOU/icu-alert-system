from __future__ import annotations

import asyncio
import statistics
import uuid
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from app.services.alert_outcome_service import AlertOutcomeService
from app.services.audit_service import write_audit_log
from app.utils.patient_helpers import admitted_patient_query, patient_his_pid_candidates
from app.utils.serialization import serialize_doc


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


CLINICAL_LABELS: dict[str, str] = {
    "clinical_document": "临床文书记录",
    "prone_position_monitor": "俯卧位通气监测",
    "pre-deliric": "谵妄高风险",
    "deliric": "谵妄风险",
    "sofa": "SOFA 器官功能评分",
    "qsofa": "qSOFA 感染风险评分",
    "sepsis": "脓毒症风险",
    "septic_shock": "脓毒性休克风险",
    "ards": "ARDS 风险",
    "aki": "急性肾损伤风险",
    "ventilator_asynchrony": "呼吸机不同步",
    "driving_pressure": "驱动压偏高",
    "mechanical_power": "机械功率升高",
    "lung_protective_ventilation": "肺保护性通气未达标",
    "post_extubation_failure_risk": "拔管后失败风险",
    "extubation_failure_risk": "拔管失败风险",
    "weaning": "撤机评估",
    "pplat_high": "平台压升高",
    "oxygenation": "氧合异常",
    "spo2": "血氧饱和度异常",
    "hypotension": "低血压",
    "shock": "休克风险",
    "lactate": "乳酸异常",
    "infection": "感染风险",
    "renal": "肾功能风险",
    "fluid_balance": "液体平衡异常",
    "vte_prophylaxis_omission": "VTE 预防遗漏",
    "vte_bleeding_linkage": "VTE 与出血风险联动",
    "icu_aw_risk": "ICU 获得性衰弱风险",
    "early_mobility_recommendation": "早期活动建议",
    "temporal_deterioration_risk": "短期恶化风险",
    "multi_organ_deterioration_trend": "多器官恶化趋势",
    "organ_deterioration_trend": "器官恶化趋势",
    "threshold": "阈值提醒",
    "trend_analysis": "趋势分析",
}


ROLE_ALIASES: dict[str, str] = {
    "主任": "director",
    "科主任": "director",
    "主任医师": "director",
    "副主任": "director",
    "副主任医师": "director",
    "director": "director",
    "dept_director": "director",
    "department_director": "director",
    "departmentdirector": "director",
    "deputy_director": "director",
    "deputydirector": "director",
    "护士长": "head_nurse",
    "护理组长": "head_nurse",
    "head_nurse": "head_nurse",
    "headnurse": "head_nurse",
    "head nurse": "head_nurse",
    "nurse_leader": "head_nurse",
    "nurseleader": "head_nurse",
    "matron": "head_nurse",
    "护士": "nurse",
    "护理": "nurse",
    "nurse": "nurse",
    "practice_nurse": "nurse",
    "practicenurse": "nurse",
    "医生": "doctor",
    "医师": "doctor",
    "住院医": "doctor",
    "主治": "doctor",
    "doctor": "doctor",
    "physician": "doctor",
    "residentdoctor": "doctor",
    "attendingdoctor": "doctor",
}


def _normalize_role_key(value: Any, default: str = "doctor") -> str:
    raw = _text(value).lower()
    if not raw:
        return default
    compact = raw.replace("-", "_").replace(" ", "_")
    return ROLE_ALIASES.get(raw) or ROLE_ALIASES.get(compact) or raw


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _humanize_identifier(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    normalized = raw.strip().replace("（", "(").replace("）", ")")
    lower = normalized.lower().replace(" ", "_")
    if normalized in CLINICAL_LABELS:
        return CLINICAL_LABELS[normalized]
    if lower in CLINICAL_LABELS:
        return CLINICAL_LABELS[lower]
    hyphen_key = lower.replace("_", "-")
    if hyphen_key in CLINICAL_LABELS:
        return CLINICAL_LABELS[hyphen_key]

    result = normalized
    for key in sorted(CLINICAL_LABELS, key=len, reverse=True):
        label = CLINICAL_LABELS[key]
        result = result.replace(key, label)
        result = result.replace(key.upper(), label)
        result = result.replace(key.replace("_", "-"), label)
        result = result.replace(key.replace("_", "-").upper(), label)
    result = result.replace("->", "→").replace("_", " ")
    if _contains_cjk(result):
        return result
    return CLINICAL_LABELS.get(lower) or "临床事件"


class ClinicalAdoptionService:
    """Role-oriented clinical workflow facade.

    This is intentionally deterministic first: it organizes available facts so
    each role sees a practical worklist even when LLM services are unavailable.
    """

    def __init__(self, db, *, alert_engine=None) -> None:
        self.db = db
        self.alert_engine = alert_engine
        self.outcomes = AlertOutcomeService(db)

    def _normalize_role(self, account: dict[str, Any] | None, fallback: str = "doctor") -> str:
        if not account:
            return _normalize_role_key(fallback)
        fields = [
            "roleName",
            "role",
            "jobTitle",
            "title",
            "position",
            "profession",
            "userType",
            "postName",
            "name",
        ]
        text = " ".join(_text(account.get(field)) for field in fields).lower()
        profession = _normalize_role_key(account.get("profession"), "")
        if profession in {"director", "head_nurse", "nurse", "doctor"}:
            return profession
        if any(token in text for token in ["科主任", "主任医师", "副主任医师", "副主任", "主任", "director", "deputydirector", "deputy director"]):
            return "director"
        if any(token in text for token in ["护士长", "护理组长", "head nurse", "head_nurse"]):
            return "head_nurse"
        if any(token in text for token in ["护士", "护理", "nurse"]):
            return "nurse"
        if any(token in text for token in ["医生", "医师", "住院医", "主治", "doctor", "physician"]):
            return "doctor"
        return _normalize_role_key(fallback)

    def _dept_code_tokens(self, value: Any) -> list[str]:
        tokens: list[str] = []
        for part in _text(value).replace("，", ",").split(","):
            token = part.strip()
            if token and token not in tokens:
                tokens.append(token)
        return tokens

    async def _department_names(self, dept_code: Any) -> str:
        codes = self._dept_code_tokens(dept_code)
        if not codes:
            return ""
        names_by_code: dict[str, str] = {}
        try:
            cursor = self.db.col("department").find({"code": {"$in": codes}}, {"code": 1, "name": 1})
            async for row in cursor:
                code = _text(row.get("code"))
                name = _text(row.get("name"))
                if code and name and code not in names_by_code and name != code:
                    names_by_code[code] = name
        except Exception:
            pass
        return "、".join(names_by_code.get(code, code) for code in codes)

    async def _department_options(self, dept_code: Any, dept_name: Any = None) -> list[dict[str, str]]:
        codes = self._dept_code_tokens(dept_code)
        names = [item.strip() for item in _text(dept_name).replace("、", ",").split(",") if item.strip()]
        names_by_code: dict[str, str] = {}
        if codes:
            try:
                cursor = self.db.col("department").find({"code": {"$in": codes}}, {"code": 1, "name": 1, "dept": 1})
                async for row in cursor:
                    code = _text(row.get("code"))
                    name = _text(row.get("name") or row.get("dept"))
                    if code and name and name != code:
                        names_by_code[code] = name
            except Exception:
                pass
        options: list[dict[str, str]] = []
        for index, code in enumerate(codes):
            options.append({"deptCode": code, "dept": names_by_code.get(code) or (names[index] if index < len(names) else code)})
        if not options and names:
            options = [{"deptCode": "", "dept": name} for name in names]
        return options

    async def resolve_account(self, user_name: str | None, *, fallback_role: str | None = "doctor") -> dict[str, Any]:
        user_name = _text(user_name)
        if not user_name:
            return {"userName": "", "role": _normalize_role_key(fallback_role), "found": False}
        query = {
            "$or": [
                {"userName": user_name},
                {"username": user_name},
                {"account": user_name},
                {"loginName": user_name},
                {"工号": user_name},
            ]
        }
        projection = {
            "userName": 1,
            "username": 1,
            "trueName": 1,
            "name": 1,
            "realName": 1,
            "role": 1,
            "roleName": 1,
            "jobTitle": 1,
            "title": 1,
            "position": 1,
            "profession": 1,
            "userType": 1,
            "postName": 1,
            "deptCode": 1,
            "departmentCode": 1,
            "deptName": 1,
            "departmentName": 1,
            "dept": 1,
        }
        account = await self.db.col("account").find_one(query, projection)
        role = self._normalize_role(account, fallback_role)
        if not account:
            return {"userName": user_name, "role": role, "found": False}
        dept_code = account.get("deptCode") or account.get("departmentCode")
        dept_name = account.get("deptName") or account.get("departmentName") or account.get("dept") or await self._department_names(dept_code)
        dept_options = await self._department_options(dept_code, dept_name)
        return {
            "userName": account.get("userName") or account.get("username") or user_name,
            "trueName": account.get("trueName"),
            "display_name": account.get("trueName") or account.get("name") or account.get("realName") or account.get("userName") or user_name,
            "role": role,
            "dept_code": dept_code,
            "dept": dept_name,
            "departments": dept_options,
            "found": True,
            "raw_role": account.get("profession") or account.get("roleName") or account.get("role") or account.get("jobTitle") or account.get("title") or account.get("position") or account.get("userType"),
        }

    async def _patient_scope(self, *, dept: str | None = None, dept_code: str | None = None, limit: int = 120) -> list[dict[str, Any]]:
        base_query: dict[str, Any] = admitted_patient_query()
        scope_terms: list[dict[str, Any]] = []
        if dept:
            scope_terms.extend([{"hisDept": dept}, {"dept": dept}])
        if dept_code:
            codes = self._dept_code_tokens(dept_code)
            if codes:
                scope_terms.append({"deptCode": {"$in": codes}})
                scope_terms.append({"departmentCode": {"$in": codes}})
        scope_query = {"$or": scope_terms} if scope_terms else None
        query = {"$and": [base_query, scope_query]} if scope_query else base_query
        cursor = self.db.col("patient").find(
            query,
            {"name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "hisDept": 1, "dept": 1, "deptCode": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1, "nursingLevel": 1, "hisPid": 1},
        ).limit(max(int(limit or 120), 1))
        return [doc async for doc in cursor]

    async def _role_distribution(self, *, dept: str | None = None, dept_code: str | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if dept:
            query = {"$or": [{"deptName": dept}, {"dept": dept}, {"department": dept}]}
        elif dept_code:
            codes = self._dept_code_tokens(dept_code)
            query = {
                "$or": [
                    {"deptCode": {"$in": codes}},
                    {"dept_code": {"$in": codes}},
                    {"departmentCode": {"$in": codes}},
                    *[{"departmentCode": {"$regex": rf"(^|,){code}(,|$)"}} for code in codes],
                ]
            }
        counts = {"nurse": 0, "doctor": 0, "head_nurse": 0, "director": 0}
        try:
            cursor = self.db.col("account").find(
                query,
                {
                    "profession": 1,
                    "roleName": 1,
                    "role": 1,
                    "jobTitle": 1,
                    "title": 1,
                    "position": 1,
                    "userType": 1,
                    "postName": 1,
                    "name": 1,
                },
            ).limit(800)
            async for account in cursor:
                role = self._normalize_role(account, "")
                if role in counts:
                    counts[role] += 1
        except Exception:
            pass
        return [
            {"key": "nurse", "label": "护士", "value": counts["nurse"]},
            {"key": "doctor", "label": "医生", "value": counts["doctor"]},
            {"key": "head_nurse", "label": "护士长", "value": counts["head_nurse"]},
            {"key": "director", "label": "主任", "value": counts["director"]},
        ]

    async def _recent_alerts(self, patient_keys: list[Any], *, hours: int = 24, limit: int = 400) -> list[dict[str, Any]]:
        if not patient_keys:
            return []
        since = datetime.now() - timedelta(hours=max(int(hours or 24), 1))
        cursor = self.db.col("alert_records").find(
            {"patient_id": {"$in": patient_keys}, "created_at": {"$gte": since}},
            {"patient_id": 1, "name": 1, "alert_type": 1, "severity": 1, "created_at": 1, "acknowledged_at": 1, "ack_disposition": 1, "actionability_score": 1, "extra": 1},
        ).sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]

    def _patient_alert_keys(self, patient: dict[str, Any]) -> list[Any]:
        keys: list[Any] = []
        oid = patient.get("_id")
        if oid:
            keys.extend([oid, str(oid)])
        for field in ("hisPid", "hisPID", "pid", "patientId"):
            value = _text(patient.get(field))
            if value:
                keys.append(value)
        deduped: list[Any] = []
        seen: set[str] = set()
        for key in keys:
            marker = f"{type(key).__name__}:{key}"
            if marker not in seen:
                seen.add(marker)
                deduped.append(key)
        return deduped

    def _role_labels(self, role: str) -> dict[str, str]:
        return {
            "nurse": {"title": "护士待办", "primary": "先处理未闭环护理风险和高危床位"},
            "head_nurse": {"title": "护士长质控", "primary": "看工作量、漏评漏做和护理质量风险"},
            "doctor": {"title": "医生查房", "primary": "先看恶化链、关键证据和下一步处置"},
            "director": {"title": "主任驾驶舱", "primary": "看科室质量、规则有效性和可复盘病例"},
        }.get(role, {"title": "临床工作台", "primary": "按角色整理今日重点"})

    def _alert_text(self, alert: dict[str, Any] | None) -> str:
        if not alert:
            return ""
        parts = [
            alert.get("name"),
            alert.get("alert_type"),
            alert.get("severity"),
            alert.get("explanation"),
            alert.get("extra"),
        ]
        return " ".join(str(part or "") for part in parts).lower()

    def _event_title_from_alert(self, alert: dict[str, Any]) -> str:
        candidates = [
            alert.get("name"),
            alert.get("alert_type"),
            alert.get("rule_id"),
        ]
        for candidate in candidates:
            title = _humanize_identifier(candidate)
            if title and title != "临床事件":
                return title
        return "临床告警"

    def _task_patient_ref(self, patient: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "patient_id": str(patient.get("_id") or ""),
            "name": patient.get("name") or patient.get("hisName") or "未知患者",
            "bed": patient.get("hisBed") or patient.get("bed") or "",
            "diagnosis": patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "",
            "nursing_level": patient.get("nursingLevel") or "",
            "latest_alert": rows[0] if rows else None,
        }

    def _build_nursing_tasks(self, patients: list[dict[str, Any]], alerts_by_patient: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for patient in patients:
            pid = str(patient.get("_id") or "")
            rows = alerts_by_patient.get(pid, [])
            ref = self._task_patient_ref(patient, rows)
            unacked_high = [
                row for row in rows
                if not row.get("acknowledged_at") and str(row.get("severity") or "").lower() in {"critical", "high"}
            ]
            if unacked_high:
                tasks.append({
                    **ref,
                    "task_type": "alert_ack",
                    "title": "立即确认高危告警",
                    "detail": f"近24小时有 {len(unacked_high)} 条高危/危急告警未闭环，先确认患者现状并记录处置。",
                    "priority": 95,
                    "tone": "danger",
                })
            alert_text = " ".join(self._alert_text(row) for row in rows)
            if any(token in alert_text for token in ["oxygen", "spo2", "呼吸", "氧", "vent", "撤机", "拔管", "气道"]):
                tasks.append({
                    **ref,
                    "task_type": "respiratory_check",
                    "title": "复核氧合/管路/呼吸支持",
                    "detail": "告警提示呼吸支持相关风险，请复核氧疗方式、管路固定、痰液和最近血气/SpO2。",
                    "priority": 82,
                    "tone": "warn",
                })
            if any(token in alert_text for token in ["sepsis", "脓毒", "感染", "bundle", "乳酸", "血培养"]):
                tasks.append({
                    **ref,
                    "task_type": "sepsis_bundle",
                    "title": "追踪脓毒症 Bundle",
                    "detail": "请跟踪血培养、乳酸复查、抗菌药执行和液体复苏记录，避免交班断点。",
                    "priority": 86,
                    "tone": "danger",
                })
            if any(token in alert_text for token in ["aki", "renal", "肾", "尿量", "肌酐"]):
                tasks.append({
                    **ref,
                    "task_type": "renal_monitor",
                    "title": "复核尿量/肾功能",
                    "detail": "关注尿量趋势、出入量、肌酐/电解质复查，以及肾毒性药物执行情况。",
                    "priority": 78,
                    "tone": "warn",
                })
            nursing_level = _text(patient.get("nursingLevel"))
            if any(token in nursing_level for token in ["特级", "一级"]) and not rows:
                tasks.append({
                    **ref,
                    "task_type": "high_level_round",
                    "title": "重点巡视高护理级别床位",
                    "detail": "该患者护理级别较高但暂无近期告警，建议作为班内固定巡视对象。",
                    "priority": 54,
                    "tone": "info",
                })
        tasks.sort(key=lambda row: (-int(row.get("priority") or 0), str(row.get("bed") or "")))
        return tasks[:18]

    def _build_doctor_gaps(self, patients: list[dict[str, Any]], alerts_by_patient: dict[str, list[dict[str, Any]]], priority_queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
        themed: dict[str, dict[str, Any]] = {}
        priority_ids = {str(row.get("patient_id") or "") for row in priority_queue[:12]}

        def add_theme(patient: dict[str, Any], rows: list[dict[str, Any]], *, gap_type: str, title: str, focus: str, priority: int, tone: str) -> None:
            ref = self._task_patient_ref(patient, rows)
            theme = themed.setdefault(gap_type, {
                **ref,
                "gap_type": gap_type,
                "title": title,
                "focus": focus,
                "priority": priority,
                "tone": tone,
                "patients": [],
            })
            theme["priority"] = max(int(theme.get("priority") or 0), priority)
            theme["patients"].append({
                "patient_id": ref.get("patient_id"),
                "bed": ref.get("bed") or "--",
                "name": ref.get("name") or "未知患者",
                "alert_count": len(rows),
                "critical_count": sum(1 for row in rows if str(row.get("severity") or "").lower() in {"critical", "high"}),
            })

        for patient in patients:
            pid = str(patient.get("_id") or "")
            rows = alerts_by_patient.get(pid, [])
            alert_text = " ".join(self._alert_text(row) for row in rows)
            if any(token in alert_text for token in ["sepsis", "脓毒", "感染", "bundle", "乳酸", "血培养"]):
                add_theme(
                    patient,
                    rows,
                    gap_type="sepsis_bundle",
                    title="感染/休克证据链复核",
                    focus="查房时核对血培养、乳酸复查、抗菌药首剂时间、补液/升压药计划是否记录完整。",
                    priority=92,
                    tone="danger",
                )
            if any(token in alert_text for token in ["vent", "撤机", "拔管", "呼吸机", "sbt", "sat", "氧合"]):
                add_theme(
                    patient,
                    rows,
                    gap_type="weaning",
                    title="撤机/氧合查房缺口",
                    focus="确认镇静深度、氧合趋势、咳痰能力、SBT/SAT记录和再插管风险。",
                    priority=80,
                    tone="warn",
                )
            if any(token in alert_text for token in ["aki", "renal", "肾", "肌酐", "crrt", "剂量"]):
                add_theme(
                    patient,
                    rows,
                    gap_type="renal_dose",
                    title="肾功能/剂量调整复核",
                    focus="核对肌酐/尿量趋势、CRRT状态、抗菌药和镇静镇痛药剂量调整。",
                    priority=76,
                    tone="warn",
                )
            if pid in priority_ids and not rows:
                add_theme(
                    patient,
                    rows,
                    gap_type="rounding_entry",
                    title="无告警高风险床位抽查",
                    focus="这些床位进入优先队列但暂无可归因告警，建议先打开事件链核对过去24小时事件。",
                    priority=48,
                    tone="info",
                )

        gaps: list[dict[str, Any]] = []
        for theme in themed.values():
            patients_for_theme = sorted(
                theme.get("patients") or [],
                key=lambda row: (-int(row.get("critical_count") or 0), -int(row.get("alert_count") or 0), str(row.get("bed") or "")),
            )
            bed_list = "、".join(f"{row.get('bed') or '--'}床{row.get('name') or ''}" for row in patients_for_theme[:6])
            more = len(patients_for_theme) - 6
            more_text = f" 等 {len(patients_for_theme)} 位患者" if more > 0 else ""
            theme["detail"] = f"涉及 {bed_list}{more_text}。{theme.get('focus')}"
            theme["title"] = f"{theme.get('title')}（{len(patients_for_theme)}床）"
            theme.pop("patients", None)
            theme.pop("focus", None)
            gaps.append(theme)
        gaps.sort(key=lambda row: (-int(row.get("priority") or 0), str(row.get("bed") or "")))
        return gaps[:6]

    def _build_quality_actions(
        self,
        patients: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        alerts_by_patient: dict[str, list[dict[str, Any]]],
        scanner_health: dict[str, Any],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        unacked = [row for row in alerts if not row.get("acknowledged_at")]
        high_unacked = [row for row in unacked if str(row.get("severity") or "").lower() in {"critical", "high"}]
        if high_unacked:
            actions.append({
                "title": "追踪高危未闭环告警",
                "detail": f"近24小时仍有 {len(high_unacked)} 条高危/危急告警未闭环，建议按床位追问责任人与实际处置。",
                "metric": len(high_unacked),
                "priority": 95,
                "tone": "danger",
            })
        heavy_patients = [p for p in patients if any(token in _text(p.get("nursingLevel")) for token in ["特级", "一级"])]
        if heavy_patients:
            actions.append({
                "title": "评估护理负荷与床位分配",
                "detail": f"当前有 {len(heavy_patients)} 位特级/一级护理患者，建议结合未闭环告警调整巡视和交班重点。",
                "metric": len(heavy_patients),
                "priority": 80,
                "tone": "warn",
            })
        noisy = [row for row in scanner_health.get("rows", []) if row.get("review_suggestion")]
        if noisy:
            top = noisy[0]
            actions.append({
                "title": "复核噪音规则",
                "detail": f"{top.get('scanner_name') or top.get('name') or '某规则'} 已触发人工复核建议，请查看阳性预测值、覆盖率和最近样例。",
                "metric": len(noisy),
                "priority": 72,
                "tone": "warn",
            })
        repeated = [
            (pid, rows) for pid, rows in alerts_by_patient.items()
            if len(rows) >= 3 and any(not row.get("acknowledged_at") for row in rows)
        ]
        if repeated:
            actions.append({
                "title": "定位重复告警床位",
                "detail": f"有 {len(repeated)} 个床位近24小时重复触发且仍有未闭环记录，适合护士长/主任晨会点名复盘。",
                "metric": len(repeated),
                "priority": 68,
                "tone": "info",
            })
        if not actions:
            actions.append({
                "title": "今日质控平稳",
                "detail": "未发现高危未闭环或规则噪音集中信号，可重点抽查事件链和交班摘要质量。",
                "metric": 0,
                "priority": 20,
                "tone": "stable",
            })
        actions.sort(key=lambda row: -int(row.get("priority") or 0))
        return actions[:8]

    def _bed_label(self, patient: dict[str, Any]) -> str:
        bed = _text(patient.get("hisBed") or patient.get("bed")) or "--"
        name = _text(patient.get("name") or patient.get("hisName")) or "未知患者"
        return f"{bed}床 {name}"

    def _build_sticky_features(
        self,
        patients: list[dict[str, Any]],
        alerts_by_patient: dict[str, list[dict[str, Any]]],
        priority_queue: list[dict[str, Any]],
        nursing_tasks: list[dict[str, Any]],
        doctor_gaps: list[dict[str, Any]],
        quality_actions: list[dict[str, Any]],
        director_digest: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        patient_by_id = {str(patient.get("_id") or ""): patient for patient in patients}

        def top_patient(index: int = 0) -> dict[str, Any] | None:
            if priority_queue and index < len(priority_queue):
                return patient_by_id.get(str(priority_queue[index].get("patient_id") or ""))
            if patients and index < len(patients):
                return patients[index]
            return patients[0] if patients else None

        def alert_blob(patient: dict[str, Any] | None) -> str:
            if not patient:
                return ""
            pid = str(patient.get("_id") or "")
            rows = alerts_by_patient.get(pid, [])
            return " ".join(self._alert_text(row) for row in rows)

        def patient_ref(patient: dict[str, Any] | None) -> dict[str, Any]:
            if not patient:
                return {"patient_id": "", "bed": "--", "name": "暂无患者"}
            return {
                "patient_id": str(patient.get("_id") or ""),
                "bed": patient.get("hisBed") or patient.get("bed") or "--",
                "name": patient.get("name") or patient.get("hisName") or "未知患者",
            }

        high_rows = [row for row in priority_queue if int(row.get("risk_score") or 0) >= 4]
        todays_focus = []
        for row in (high_rows or priority_queue or [])[:8]:
            patient = patient_by_id.get(str(row.get("patient_id") or ""))
            why = "高危告警/未闭环集中"
            if int(row.get("risk_score") or 0) <= 0:
                why = "在科患者，适合常规查房抽查"
            todays_focus.append({
                **patient_ref(patient),
                "title": f"{row.get('bed') or '--'}床 {row.get('name') or '患者'}",
                "detail": f"{why}；高危 {row.get('critical_alerts') or 0} 条，未闭环 {row.get('unacked_alerts') or 0} 条。",
                "action": "看事件链",
                "kind": "story",
                "tone": "danger" if int(row.get("risk_score") or 0) >= 8 else "warn" if int(row.get("risk_score") or 0) >= 4 else "info",
            })

        rounding_checklist: list[dict[str, Any]] = []
        for gap in doctor_gaps[:6]:
            rounding_checklist.append({
                "patient_id": gap.get("patient_id"),
                "title": gap.get("title") or "查房问题",
                "detail": gap.get("detail") or "查房时复核证据链、处置链和下一步医嘱。",
                "action": "看代表病例",
                "kind": "handoff",
                "tone": gap.get("tone") or "warn",
            })
        if not rounding_checklist:
            patient = top_patient()
            rounding_checklist.append({
                **patient_ref(patient),
                "title": "每日查房五问",
                "detail": "是否能减镇静、能撤机、能降阶梯抗菌药、能启动营养/活动、能转出 ICU。",
                "action": "生成交班摘要",
                "kind": "handoff",
                "tone": "info",
            })

        nursing_radar: list[dict[str, Any]] = []
        radar_sources = nursing_tasks[:8] if nursing_tasks else []
        for task in radar_sources:
            nursing_radar.append({
                "patient_id": task.get("patient_id"),
                "title": task.get("title") or "护理风险",
                "detail": f"{task.get('bed') or '--'}床 {task.get('name') or '患者'}：{task.get('detail') or '请复核班内护理风险。'}",
                "action": "看护理事件",
                "kind": "story",
                "tone": task.get("tone") or "warn",
            })
        if not nursing_radar:
            patient = top_patient()
            nursing_radar.append({
                **patient_ref(patient),
                "title": "护理风险雷达",
                "detail": "当前无高优先级护理待办，建议按高护理级别床位抽查管路、皮肤、镇静、出入量和谵妄风险。",
                "action": "看事件链",
                "kind": "story",
                "tone": "stable",
            })

        order_gaps: list[dict[str, Any]] = []
        for patient in patients[:24]:
            blob = alert_blob(patient)
            ref = patient_ref(patient)
            if any(token in blob for token in ["sepsis", "脓毒", "感染", "乳酸"]):
                order_gaps.append({**ref, "title": "疑似感染/休克医嘱缺口", "detail": "复核血培养、乳酸复查、抗菌药首剂时间、补液和升压药目标是否完整。", "action": "看交班", "kind": "handoff", "tone": "danger"})
            if any(token in blob for token in ["vent", "撤机", "拔管", "呼吸机", "氧合"]):
                order_gaps.append({**ref, "title": "机械通气 Bundle 缺口", "detail": "复核 RASS 目标、镇痛镇静、VTE/应激溃疡预防、SBT/SAT 与口腔护理记录。", "action": "看事件链", "kind": "story", "tone": "warn"})
            if any(token in blob for token in ["aki", "renal", "肾", "肌酐", "crrt"]):
                order_gaps.append({**ref, "title": "肾功能剂量调整缺口", "detail": "复核抗菌药、抗凝、镇静镇痛、造影/肾毒性药物是否按肾功能调整。", "action": "看事件链", "kind": "story", "tone": "warn"})
        if not order_gaps:
            patient = top_patient()
            order_gaps.append({**patient_ref(patient), "title": "医嘱缺口自动检查", "detail": "当前未抓到强缺口，系统仍建议每日固定检查 VTE、营养、镇静目标、抗菌药疗程和转出条件。", "action": "看代表患者", "kind": "handoff", "tone": "info"})

        discharge_candidates: list[dict[str, Any]] = []
        for row in priority_queue:
            if int(row.get("risk_score") or 0) <= 1:
                patient = patient_by_id.get(str(row.get("patient_id") or ""))
                discharge_candidates.append({
                    **patient_ref(patient),
                    "title": f"{row.get('bed') or '--'}床可能可转出评估",
                    "detail": "近24小时风险分低且无明显未闭环告警，建议查房时核对氧合、循环、管路和护理级别是否满足转出。",
                    "action": "看交班",
                    "kind": "handoff",
                    "tone": "stable",
                })
        if not discharge_candidates:
            patient = top_patient(len(priority_queue) - 1 if priority_queue else 0)
            discharge_candidates.append({**patient_ref(patient), "title": "转出 ICU 评估池", "detail": "暂未形成低风险转出候选，建议每日由主任查房确认是否存在床位占用延迟。", "action": "看代表患者", "kind": "handoff", "tone": "info"})

        family_summaries: list[dict[str, Any]] = []
        for row in priority_queue[:4]:
            patient = patient_by_id.get(str(row.get("patient_id") or ""))
            family_summaries.append({
                **patient_ref(patient),
                "title": "家属沟通摘要",
                "detail": f"适合生成“目前问题、今天变化、主要风险、下一步计划”的白话版本，降低医生重复解释时间。",
                "action": "生成摘要",
                "kind": "handoff",
                "tone": "info",
            })

        medication_safety: list[dict[str, Any]] = []
        for item in order_gaps[:6]:
            if any(token in _text(item.get("title")) for token in ["肾功能", "剂量", "医嘱", "抗菌"]):
                medication_safety.append({
                    **item,
                    "title": item.get("title") or "用药安全复核",
                    "detail": item.get("detail") or "复核肾功能、抗菌药疗程、镇静镇痛、抗凝和相互作用。",
                    "action": "看事件链",
                    "kind": "story",
                })
        if not medication_safety:
            patient = top_patient()
            medication_safety.append({**patient_ref(patient), "title": "用药安全管家", "detail": "每日自动盯肾功能剂量、抗菌药疗程、血管活性药、镇静镇痛、胰岛素和抗凝风险。", "action": "看代表患者", "kind": "story", "tone": "info"})

        event_previews: list[dict[str, Any]] = []
        for row in priority_queue[:6]:
            patient = patient_by_id.get(str(row.get("patient_id") or ""))
            blob = alert_blob(patient)
            likely = "病情波动或交班断点"
            if any(token in blob for token in ["sepsis", "脓毒", "乳酸", "休克"]):
                likely = "感染/休克进展"
            elif any(token in blob for token in ["vent", "撤机", "拔管", "氧合"]):
                likely = "氧合恶化或拔管失败"
            elif any(token in blob for token in ["aki", "肾", "crrt"]):
                likely = "肾功能恶化或容量/电解质问题"
            event_previews.append({
                **patient_ref(patient),
                "title": f"未来24小时最可能风险：{likely}",
                "detail": "不是只给分数，而是提示如果患者出事最可能卡在哪里，方便医生提前布置复查和护理观察。",
                "action": "看事件链",
                "kind": "story",
                "tone": "danger" if int(row.get("risk_score") or 0) >= 8 else "warn",
            })

        director_dashboard = [
            {
                "title": "主任质控驾驶舱",
                "detail": director_digest.get("headline") or "汇总规则健康、告警闭环、典型病例和延迟响应，用于晨会和质控会。",
                "metric": director_digest.get("review_required") or 0,
                "action": "打开规则健康",
                "kind": "scanner_review",
                "tone": "warn" if director_digest.get("review_required") else "stable",
            },
            *[
                {
                    "title": action.get("title"),
                    "detail": action.get("detail"),
                    "metric": action.get("metric"),
                    "action": "看质控线索",
                    "kind": "scanner_review",
                    "tone": action.get("tone") or "info",
                }
                for action in quality_actions[:5]
            ],
        ]

        return {
            "todays_focus": todays_focus[:8],
            "rounding_checklist": rounding_checklist[:8],
            "nursing_radar": nursing_radar[:8],
            "order_gaps": order_gaps[:8],
            "discharge_candidates": discharge_candidates[:6],
            "family_summaries": family_summaries[:6],
            "medication_safety": medication_safety[:6],
            "event_previews": event_previews[:6],
            "director_dashboard": director_dashboard[:6],
        }

    def _build_director_digest(self, alerts: list[dict[str, Any]], scanner_health: dict[str, Any], quality_actions: list[dict[str, Any]]) -> dict[str, Any]:
        rows = scanner_health.get("rows") or []
        total_fired = sum(int(row.get("fired_count") or 0) for row in rows)
        review_required = sum(1 for row in rows if row.get("review_suggestion"))
        avg_ppv = round(sum(float(row.get("ppv") or 0) for row in rows) / len(rows), 3) if rows else 0
        high_alerts = sum(1 for row in alerts if str(row.get("severity") or "").lower() in {"critical", "high"})
        unacked = sum(1 for row in alerts if not row.get("acknowledged_at"))
        headline = "规则健康平稳，适合抽查典型病例"
        if review_required:
            headline = f"{review_required} 条规则建议人工复核，优先处理低阳性预测值、高覆盖率规则"
        elif unacked:
            headline = f"{unacked} 条告警仍未闭环，建议晨会追踪责任链"
        return {
            "headline": headline,
            "total_fired_30d": total_fired,
            "review_required": review_required,
            "avg_ppv": avg_ppv,
            "high_alerts_24h": high_alerts,
            "unacked_24h": unacked,
            "top_actions": quality_actions[:3],
        }

    async def _antibiotic_intensity(self, patients: list[dict[str, Any]], *, days: int = 7) -> dict[str, Any]:
        since = datetime.now() - timedelta(days=max(int(days or 7), 1))
        his_pids = [_text(p.get("hisPid") or p.get("hisPID") or p.get("pid")) for p in patients]
        his_pids = [pid for pid in his_pids if pid]
        empty = {
            "source": "抗菌强度",
            "available": False,
            "daily": [],
            "top_patients": [],
            "patients": [],
            "summary": {"today": 0, "decrease_today": 0, "net_today": 0, "trend": "flat"},
            "mapping": {"patient": "hisPid", "date": "recordDate", "increase": "increase", "decrease": "decrease", "dept": "deptCode"},
        }
        if not his_pids:
            return empty
        rows: list[dict[str, Any]] = []

        projection = {"hisPid": 1, "recordDate": 1, "increase": 1, "decrease": 1, "deptCode": 1, "createTime": 1}
        dept_codes = [_text(p.get("deptCode")) for p in patients]
        dept_codes = [code for code in dept_codes if code]
        try:
            query: dict[str, Any] = {"hisPid": {"$in": his_pids}, "recordDate": {"$gte": since.strftime("%Y-%m-%d %H:%M:%S")}}
            cursor = self.db.col("KJ_DDDS").find(query, projection).sort("recordDate", -1).limit(1000)
            rows = [doc async for doc in cursor]
            if not rows:
                # KJ_DDDS in SmartCare can lag behind real time in offline/demo data.
                # Fall back to the latest available record window for the scoped patients.
                cursor = self.db.col("KJ_DDDS").find({"hisPid": {"$in": his_pids}}, projection).sort("recordDate", -1).limit(1000)
                rows = [doc async for doc in cursor]
            if not rows and dept_codes:
                cursor = self.db.col("KJ_DDDS").find({"deptCode": {"$in": dept_codes}}, projection).sort("recordDate", -1).limit(1000)
                rows = [doc async for doc in cursor]
        except Exception:
            rows = []

        if not rows:
            return empty

        def row_date(row: dict[str, Any]) -> datetime | None:
            return _dt(row.get("recordDate")) or _dt(row.get("createTime"))

        def row_float(row: dict[str, Any], field: str) -> float:
            try:
                return float(str(row.get(field) or "0").strip() or 0)
            except Exception:
                return 0.0

        patient_name_by_pid = {
            _text(p.get("hisPid") or p.get("hisPID") or p.get("pid")): self._bed_label(p)
            for p in patients
        }
        anchor_dates = [row_date(row) for row in rows]
        anchor_dates = [dt for dt in anchor_dates if dt]
        anchor = max(anchor_dates) if anchor_dates else None
        if anchor and anchor < since:
            window_start = anchor - timedelta(days=max(int(days or 7), 1) - 1)
        else:
            window_start = since
        daily: dict[str, float] = {}
        daily_decrease: dict[str, float] = {}
        patient_total: dict[str, float] = {}
        patient_decrease: dict[str, float] = {}
        patient_daily: dict[str, dict[str, dict[str, float]]] = {}
        for row in rows:
            dt = row_date(row)
            if dt and dt < window_start:
                continue
            increase = row_float(row, "increase")
            decrease = row_float(row, "decrease")
            key = dt.strftime("%m-%d") if dt else "未知"
            daily[key] = daily.get(key, 0.0) + increase
            daily_decrease[key] = daily_decrease.get(key, 0.0) + decrease
            pid = _text(row.get("hisPid"))
            patient_total[pid] = patient_total.get(pid, 0.0) + increase
            patient_decrease[pid] = patient_decrease.get(pid, 0.0) + decrease
            patient_daily.setdefault(pid, {}).setdefault(key, {"value": 0.0, "decrease": 0.0})
            patient_daily[pid][key]["value"] += increase
            patient_daily[pid][key]["decrease"] += decrease

        daily_rows = [
            {
                "date": key,
                "value": round(value, 2),
                "decrease": round(daily_decrease.get(key, 0.0), 2),
                "net": round(value - daily_decrease.get(key, 0.0), 2),
            }
            for key, value in sorted(daily.items())
        ][-7:]
        top_patients = [
            {
                "patient": patient_name_by_pid.get(pid, pid or "未知"),
                "hisPid": pid,
                "value": round(value, 2),
                "decrease": round(patient_decrease.get(pid, 0.0), 2),
                "net": round(value - patient_decrease.get(pid, 0.0), 2),
            }
            for pid, value in sorted(patient_total.items(), key=lambda item: item[1], reverse=True)[:6]
        ]
        patients_detail = []
        for pid, days_map in patient_daily.items():
            rows_for_patient = [
                {
                    "date": key,
                    "value": round(values.get("value", 0.0), 2),
                    "decrease": round(values.get("decrease", 0.0), 2),
                    "net": round(values.get("value", 0.0) - values.get("decrease", 0.0), 2),
                }
                for key, values in sorted(days_map.items())
            ][-7:]
            latest = rows_for_patient[-1] if rows_for_patient else {"value": 0, "decrease": 0, "net": 0}
            prev_day = rows_for_patient[-2] if len(rows_for_patient) > 1 else latest
            task_priority = "high" if latest["net"] >= 3 or latest["value"] > prev_day.get("value", 0) else "medium" if latest["net"] > 0 else "low"
            task_title = "抗菌强度净增，复核降阶梯" if task_priority == "high" else "抗菌疗程复核" if task_priority == "medium" else "维持观察"
            patients_detail.append({
                "patient": patient_name_by_pid.get(pid, pid or "未知"),
                "hisPid": pid,
                "daily": rows_for_patient,
                "summary": {"today": latest["value"], "decrease_today": latest["decrease"], "net_today": latest["net"]},
                "task": {
                    "title": task_title,
                    "priority": task_priority,
                    "action": "感染/药学复核" if task_priority in {"high", "medium"} else "观察",
                    "reason": f"今日增 {latest['value']}，减 {latest['decrease']}，净 {latest['net']}",
                },
            })
        patients_detail.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get((item.get("task") or {}).get("priority"), 3), -float(((item.get("summary") or {}).get("net_today") or 0))))
        antibiotic_tasks = [
            {
                "patient": item.get("patient"),
                "hisPid": item.get("hisPid"),
                **(item.get("task") or {}),
            }
            for item in patients_detail
            if (item.get("task") or {}).get("priority") in {"high", "medium"}
        ][:8]
        today = daily_rows[-1]["value"] if daily_rows else 0
        decrease_today = daily_rows[-1]["decrease"] if daily_rows else 0
        net_today = daily_rows[-1]["net"] if daily_rows else 0
        prev = daily_rows[-2]["value"] if len(daily_rows) > 1 else today
        trend = "up" if today > prev else "down" if today < prev else "flat"
        return {
            "source": "抗菌强度",
            "available": True,
            "daily": daily_rows,
            "top_patients": top_patients,
            "patients": patients_detail,
            "tasks": antibiotic_tasks,
            "summary": {
                "today": today,
                "decrease_today": decrease_today,
                "net_today": net_today,
                "trend": trend,
                "latest_record_date": anchor.strftime("%Y-%m-%d") if anchor else "",
            },
            "mapping": {"patient": "hisPid", "date": "recordDate", "increase": "increase", "decrease": "decrease", "dept": "deptCode"},
        }

    async def _build_clinical_visuals(
        self,
        patients: list[dict[str, Any]],
        alerts_by_patient: dict[str, list[dict[str, Any]]],
        priority_queue: list[dict[str, Any]],
        nursing_tasks: list[dict[str, Any]],
        doctor_gaps: list[dict[str, Any]],
        quality_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        patient_by_id = {str(patient.get("_id") or ""): patient for patient in patients}
        bed_heatmap = []
        for row in (priority_queue or [])[:36]:
            score = int(row.get("risk_score") or 0)
            bed_heatmap.append({
                "patient_id": row.get("patient_id"),
                "bed": row.get("bed") or "--",
                "name": row.get("name") or "患者",
                "hisPid": row.get("hisPid") or "",
                "value": score,
                "tone": "critical" if score >= 10 else "high" if score >= 6 else "warning" if score >= 2 else "stable",
            })

        omission_defs = [
            ("pressure", "压疮", "皮肤|压疮|翻身"),
            ("line", "管路", "管路|导管|置管"),
            ("restraint", "约束", "约束"),
            ("rass", "RASS", "rass|镇静"),
            ("cam", "谵妄", "cam|谵妄|delir"),
            ("vte", "VTE", "vte|抗凝|血栓"),
            ("glucose", "血糖", "血糖|胰岛素"),
            ("io", "出入量", "尿量|出入量|液体"),
            ("turn", "翻身", "翻身|俯卧"),
        ]
        task_text = " ".join(_text(task.get("title")) + " " + _text(task.get("detail")) for task in nursing_tasks).lower()
        nursing_omissions = [
            {
                "key": key,
                "label": label,
                "status": "todo" if any(token in task_text for token in pattern.split("|")) else "ok",
                "action": "补核" if any(token in task_text for token in pattern.split("|")) else "已覆盖",
            }
            for key, label, pattern in omission_defs
        ]
        nursing_completion = {
            "percent": round(sum(1 for item in nursing_omissions if item["status"] == "ok") / max(1, len(nursing_omissions)) * 100),
            "tasks": [
                {
                    "key": item["key"],
                    "title": f"{item['label']}补核",
                    "priority": "high" if item["key"] in {"line", "glucose", "io"} else "medium",
                    "action": "生成护理任务",
                }
                for item in nursing_omissions
                if item["status"] == "todo"
            ][:6],
        }

        order_swimlanes = []
        for row in (priority_queue or [])[:5]:
            steps = [
                {"label": "告警", "status": "done" if row.get("critical_alerts") else "idle"},
                {"label": "医嘱", "status": "todo" if row.get("critical_alerts") else "idle"},
                {"label": "执行", "status": "todo" if row.get("unacked_alerts") else "done"},
                {"label": "复查", "status": "todo" if row.get("unacked_alerts") else "idle"},
                {"label": "结果", "status": "idle"},
            ]
            order_swimlanes.append({"patient_id": row.get("patient_id"), "bed": row.get("bed") or "--", "name": row.get("name") or "患者", "hisPid": row.get("hisPid") or "", "steps": steps})

        weaning_lights = []
        discharge_lights = []
        for row in (priority_queue or [])[:6]:
            score = int(row.get("risk_score") or 0)
            weaning_lights.append({"patient_id": row.get("patient_id"), "bed": row.get("bed"), "name": row.get("name"), "hisPid": row.get("hisPid") or "", "lights": [
                {"label": "氧合", "ok": score < 6},
                {"label": "循环", "ok": score < 8},
                {"label": "意识", "ok": score < 5},
                {"label": "咳痰", "ok": score < 4},
                {"label": "SBT", "ok": score < 3},
            ]})
            discharge_ok_count = 0
            discharge_items = [
                {"label": "低危", "ok": score <= 1},
                {"label": "无高危", "ok": not row.get("critical_alerts")},
                {"label": "少未闭环", "ok": int(row.get("unacked_alerts") or 0) <= 1},
                {"label": "可承接", "ok": score <= 2},
            ]
            discharge_ok_count = sum(1 for item in discharge_items if item["ok"])
            discharge_lights.append({
                "patient_id": row.get("patient_id"),
                "bed": row.get("bed"),
                "name": row.get("name"),
                "hisPid": row.get("hisPid") or "",
                "lights": discharge_items,
                "percent": round(discharge_ok_count / max(1, len(discharge_items)) * 100),
                "task": "可转出复核" if discharge_ok_count >= 3 else "继续留观",
            })

        rescue_timeline = []
        for action in quality_actions[:5]:
            rescue_timeline.append({"time": "24h", "title": action.get("title"), "tone": action.get("tone") or "info"})

        family_cards = []
        for row in (priority_queue or [])[:4]:
            family_cards.append({
                "patient_id": row.get("patient_id"),
                "bed": row.get("bed"),
                "name": row.get("name"),
                "hisPid": row.get("hisPid") or "",
                "blocks": ["问题", "变化", "风险", "计划"],
                "readiness": 75 if row.get("latest_alert") else 55,
                "task": "生成家属沟通卡",
                "tone": "danger" if int(row.get("risk_score") or 0) >= 8 else "warn" if int(row.get("risk_score") or 0) >= 3 else "info",
            })
        antibiotic_intensity = await self._antibiotic_intensity(patients)

        return {
            "bed_heatmap": bed_heatmap,
            "nursing_omissions": nursing_omissions,
            "nursing_completion": nursing_completion,
            "order_swimlanes": order_swimlanes,
            "antibiotic_intensity": antibiotic_intensity,
            "weaning_lights": weaning_lights,
            "discharge_lights": discharge_lights,
            "rescue_timeline": rescue_timeline,
            "family_cards": family_cards,
        }

    def _build_icu_day_flow(
        self,
        *,
        patients: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        priority_queue: list[dict[str, Any]],
        nursing_tasks: list[dict[str, Any]],
        doctor_gaps: list[dict[str, Any]],
        quality_actions: list[dict[str, Any]],
        director_digest: dict[str, Any],
    ) -> list[dict[str, Any]]:
        high_priority = [row for row in priority_queue if int(row.get("risk_score") or 0) > 0]
        unacked_high = [row for row in alerts if not row.get("acknowledged_at") and str(row.get("severity") or "").lower() in {"critical", "high"}]
        return [
            {
                "key": "night_handoff",
                "time": "07:30",
                "scene": "早交班",
                "owner": "医生 / 护士",
                "title": "AI 生成昨夜重点交班",
                "detail": f"自动汇总 {len(high_priority)} 个高优先级床位、{len(unacked_high)} 条高危未闭环告警、抢救/插管/撤机/感染休克线索。",
                "ai_capability": "自动写交班摘要、提取昨夜恶化链、标出未闭环事项。",
                "action": "一键生成交班摘要",
                "tone": "danger" if unacked_high else "info",
            },
            {
                "key": "morning_round",
                "time": "08:30",
                "scene": "晨查房",
                "owner": "医生",
                "title": "AI 生成每床今日问题清单",
                "detail": f"按事件链和查房缺口生成 {len(doctor_gaps)} 类主题：感染/休克、撤机/氧合、肾功能/剂量、无告警高风险床位。",
                "ai_capability": "把告警转成诊疗问题、证据缺口、下一步复查/医嘱建议。",
                "action": "生成查房问题",
                "tone": "warn" if doctor_gaps else "stable",
            },
            {
                "key": "nursing_shift",
                "time": "10:00-16:00",
                "scene": "班中护理",
                "owner": "护士",
                "title": "AI 排班内优先巡视顺序",
                "detail": f"根据高危告警、护理级别、呼吸/管路/尿量/感染任务，整理 {len(nursing_tasks)} 条班内待办。",
                "ai_capability": "预测下一个班次护理负荷，提示漏评估、漏复查、漏执行。",
                "action": "生成护理待办",
                "tone": "danger" if nursing_tasks else "stable",
            },
            {
                "key": "head_nurse_quality",
                "time": "16:30",
                "scene": "护士长质控",
                "owner": "护士长",
                "title": "AI 找交班断点和漏执行",
                "detail": f"聚合未闭环、重复告警和护理负荷，形成 {len(quality_actions)} 条质控追踪线索。",
                "ai_capability": "识别高压床位、重复噪音、护理记录断点，并生成追踪清单。",
                "action": "生成质控清单",
                "tone": "warn" if quality_actions else "stable",
            },
            {
                "key": "director_huddle",
                "time": "次日晨会",
                "scene": "主任晨会",
                "owner": "主任 / 质控",
                "title": "AI 生成科室晨会材料",
                "detail": director_digest.get("headline") or "汇总规则健康、典型病例、延迟响应和闭环趋势。",
                "ai_capability": "生成晨会摘要、病例复盘提纲、规则复核建议，但不自动改阈值。",
                "action": "生成晨会摘要",
                "tone": "warn" if director_digest.get("review_required") else "info",
            },
        ]

    def _build_ai_toolbox(
        self,
        *,
        priority_queue: list[dict[str, Any]],
        doctor_gaps: list[dict[str, Any]],
        nursing_tasks: list[dict[str, Any]],
        scanner_health: dict[str, Any],
    ) -> list[dict[str, Any]]:
        target = priority_queue[0] if priority_queue else {}
        review_count = sum(1 for row in scanner_health.get("rows", []) if row.get("review_suggestion"))
        return [
            {
                "key": "story",
                "title": "患者事件链",
                "detail": "按因果顺序串起生命体征、用药、评分和告警，减少逐页翻数据。",
                "target_patient_id": target.get("patient_id"),
                "action": "看最高风险患者",
                "count": len(priority_queue),
            },
            {
                "key": "handoff",
                "title": "交班摘要",
                "detail": "自动生成医生/护理交班重点，去重后保留未闭环问题。",
                "target_patient_id": target.get("patient_id"),
                "action": "生成代表交班",
                "count": len(priority_queue),
            },
            {
                "key": "rounding",
                "title": "查房问题生成",
                "detail": "把告警翻译成今日诊疗问题、缺失证据和复查建议。",
                "target_patient_id": (doctor_gaps[0] if doctor_gaps else target).get("patient_id"),
                "action": "看代表病例",
                "count": len(doctor_gaps),
            },
            {
                "key": "nursing",
                "title": "护理漏项雷达",
                "detail": "从高危未闭环、呼吸/管路/尿量/感染线索生成班内待办。",
                "target_patient_id": (nursing_tasks[0] if nursing_tasks else target).get("patient_id"),
                "action": "看护理事件",
                "count": len(nursing_tasks),
            },
            {
                "key": "scanner_review",
                "title": "规则健康复核",
                "detail": "识别低阳性预测值、高覆盖率、疑似噪音规则，给主任人工复核。",
                "target_patient_id": "",
                "action": "打开规则健康",
                "count": review_count,
            },
        ]

    def _build_module_completion(
        self,
        *,
        patients: list[dict[str, Any]],
        priority_queue: list[dict[str, Any]],
        nursing_tasks: list[dict[str, Any]],
        doctor_gaps: list[dict[str, Any]],
        quality_actions: list[dict[str, Any]],
        scanner_health: dict[str, Any],
        clinical_visuals: dict[str, Any],
    ) -> dict[str, Any]:
        visuals = clinical_visuals or {}
        scanner_rows = scanner_health.get("rows") or []
        antibiotic = (visuals.get("antibiotic_intensity") or {})
        nursing_completion = visuals.get("nursing_completion") or {}
        scanner_avg_closure = round(
            sum(float((row.get("closure") or {}).get("percent") or 0) for row in scanner_rows) / len(scanner_rows)
        ) if scanner_rows else 55
        antibiotic_tasks = antibiotic.get("tasks") or []
        def maturity(base: int, *signals: bool, cap: int = 96) -> int:
            score = int(base) + sum(6 for item in signals if item)
            return max(35, min(cap, score))
        modules = [
            {
                "key": "director",
                "name": "主任晨会",
                "percent": maturity(68, bool(quality_actions), bool(scanner_rows), bool(priority_queue), cap=94),
                "status": "maturing",
                "route": "/clinical-workflow",
                "metric": len(quality_actions),
                "action": "看晨会一屏",
                "gap": "需要更多真实晨会闭环记录",
            },
            {
                "key": "story",
                "name": "Story交班",
                "percent": maturity(62, bool(priority_queue), bool(doctor_gaps), bool(nursing_tasks), cap=90),
                "status": "maturing" if priority_queue else "warmup",
                "route": "/clinical-workflow",
                "metric": len(priority_queue),
                "action": "看事件链",
                "gap": "需积累医生确认和交班采纳记录",
            },
            {
                "key": "rounding",
                "name": "医生查房",
                "percent": maturity(66, bool(doctor_gaps), bool(priority_queue), cap=88),
                "status": "maturing",
                "route": "/rounding-sheet",
                "metric": len(doctor_gaps),
                "action": "开查房单",
                "gap": "需补齐查房任务关闭和病程回写",
            },
            {
                "key": "nursing",
                "name": "护理闭环",
                "percent": int(nursing_completion.get("percent") or maturity(58, bool(nursing_tasks), bool(patients), cap=86)),
                "status": "maturing",
                "route": "/clinical-workflow",
                "metric": len(nursing_tasks),
                "action": "看护理任务",
                "gap": "需接入护理执行关闭记录",
            },
            {
                "key": "respiratory",
                "name": "呼吸治疗",
                "percent": maturity(70, bool(visuals.get("weaning_lights")), bool(priority_queue), cap=90),
                "status": "maturing",
                "route": "/respiratory-dashboard",
                "metric": len(visuals.get("weaning_lights") or []),
                "action": "看撤机灯",
                "gap": "需补齐SBT/气道任务关闭率",
            },
            {
                "key": "nutrition",
                "name": "营养支持",
                "percent": 94,
                "status": "near_ready",
                "route": "/nutrition-support",
                "metric": len(patients),
                "action": "看营养床卡",
                "gap": "接近完成，仍需现场确认任务闭环率",
            },
            {
                "key": "antibiotic",
                "name": "抗菌DDDS",
                "percent": maturity(58, bool(antibiotic.get("available")), bool(antibiotic_tasks), cap=84),
                "status": "maturing" if antibiotic.get("available") else "data_waiting",
                "route": "/clinical-workflow",
                "metric": (antibiotic.get("summary") or {}).get("today") or 0,
                "action": "看抗菌强度",
                "gap": "需接入药学/感染复核关闭记录",
            },
            {
                "key": "mdt",
                "name": "MDT会诊",
                "percent": maturity(64, bool(priority_queue), cap=82),
                "status": "maturing",
                "route": "/mdt",
                "metric": len(priority_queue[:6]),
                "action": "开MDT",
                "gap": "需积累真实会诊决议完成率",
            },
            {
                "key": "scanner",
                "name": "规则健康",
                "percent": max(55, min(88, scanner_avg_closure)),
                "status": "maturing" if scanner_rows else "warmup",
                "route": "/admin/scanner-health",
                "metric": sum(1 for row in scanner_rows if row.get("review_suggestion")),
                "action": "看规则健康",
                "gap": "需补齐更多alert_outcomes结局样本",
            },
        ]
        overall = round(sum(int(item.get("percent") or 0) for item in modules) / max(1, len(modules)))
        task_templates = [
            {
                "module": item["key"],
                "title": f"{item['name']}闭环复核",
                "status": "ready" if int(item.get("percent") or 0) >= 95 else "open",
                "action": item.get("action"),
                "route": item.get("route"),
            }
            for item in modules
        ]
        gaps = [
            {"key": item["key"], "name": item["name"], "reason": item.get("gap") or ("等待真实数据同步" if item.get("status") == "data_waiting" else "等待病例触发")}
            for item in modules
            if int(item.get("percent") or 0) < 100
        ][:4]
        return {"overall": overall, "modules": modules, "tasks": task_templates, "gaps": gaps, "generated_at": datetime.now()}

    async def _open_clinical_tasks(self, patient_ids: list[str], *, limit: int = 12) -> dict[str, Any]:
        ids = [pid for pid in {_text(pid) for pid in patient_ids} if pid]
        query: dict[str, Any] = {"status": {"$in": ["open", "in_progress"]}}
        if ids:
            query["patient_id"] = {"$in": ids}
        cursor = self.db.col("clinical_tasks").find(
            query,
            {
                "_id": 0,
                "task_id": 1,
                "patient_id": 1,
                "bed": 1,
                "name": 1,
                "module": 1,
                "task_type": 1,
                "title": 1,
                "detail": 1,
                "priority": 1,
                "status": 1,
                "updated_at": 1,
                "created_at": 1,
            },
        ).sort([("priority", -1), ("updated_at", -1)]).limit(max(1, int(limit or 12)))
        rows = [serialize_doc(row) async for row in cursor]
        module_labels = {
            "clinical_workflow": "临床",
            "nutrition": "营养",
            "respiratory": "呼吸",
            "rounding": "查房",
            "scanner": "规则",
            "antibiotic": "抗菌",
            "mdt": "MDT",
        }
        for row in rows:
            module = _text(row.get("module")) or "clinical_workflow"
            row["module_label"] = module_labels.get(module, module)
            row["bed_label"] = _text(row.get("bed")) or "--"
            row["patient_label"] = _text(row.get("name")) or "患者"
        return {
            "total": await self.db.col("clinical_tasks").count_documents(query),
            "items": rows,
        }

    async def _open_clinical_tasks_fast(self, patient_ids: list[str], *, limit: int = 12) -> dict[str, Any]:
        ids = [pid for pid in {_text(pid) for pid in patient_ids} if pid]
        if not ids:
            return {"total": 0, "items": []}
        query: dict[str, Any] = {"status": {"$in": ["open", "in_progress"]}, "patient_id": {"$in": ids}}
        cursor = self.db.col("clinical_tasks").find(
            query,
            {
                "_id": 0,
                "task_id": 1,
                "patient_id": 1,
                "bed": 1,
                "name": 1,
                "module": 1,
                "task_type": 1,
                "title": 1,
                "detail": 1,
                "priority": 1,
                "status": 1,
                "updated_at": 1,
                "created_at": 1,
            },
        ).sort([("priority", -1), ("updated_at", -1)]).limit(max(1, int(limit or 12)) + 1)
        rows = [serialize_doc(row) async for row in cursor]
        has_more = len(rows) > max(1, int(limit or 12))
        rows = rows[: max(1, int(limit or 12))]
        module_labels = {
            "clinical_workflow": "临床",
            "nutrition": "营养",
            "respiratory": "呼吸",
            "rounding": "查房",
            "scanner": "规则",
            "antibiotic": "抗菌",
            "mdt": "MDT",
        }
        for row in rows:
            module = _text(row.get("module")) or "clinical_workflow"
            row["module_label"] = module_labels.get(module, module)
            row["bed_label"] = _text(row.get("bed")) or "--"
            row["patient_label"] = _text(row.get("name")) or "患者"
        return {"total": len(rows) + (1 if has_more else 0), "items": rows, "has_more": has_more}

    def _quick_scanner_health(self, alerts: list[dict[str, Any]]) -> dict[str, Any]:
        buckets: dict[str, dict[str, Any]] = {}
        for alert in alerts or []:
            key = _text(alert.get("alert_type")) or "unknown"
            row = buckets.setdefault(
                key,
                {
                    "scanner_name": key,
                    "fired_count": 0,
                    "review_suggestion": "",
                    "closure": {"percent": 75},
                    "ppv": 0,
                    "override_rate": 0,
                },
            )
            row["fired_count"] = int(row.get("fired_count") or 0) + 1
        rows = sorted(buckets.values(), key=lambda item: int(item.get("fired_count") or 0), reverse=True)[:8]
        for row in rows:
            if int(row.get("fired_count") or 0) >= 8:
                row["review_suggestion"] = "近24小时触发较多，建议质控复核"
        return {"rows": rows, "summary": {"source": "role_home_fast", "alert_types": len(rows)}, "fast": True}

    def _build_clinical_visuals_fast(
        self,
        *,
        priority_queue: list[dict[str, Any]],
        nursing_tasks: list[dict[str, Any]],
        quality_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bed_heatmap = [
            {
                "patient_id": row.get("patient_id"),
                "bed": row.get("bed") or "--",
                "name": row.get("name") or "患者",
                "hisPid": row.get("hisPid") or "",
                "value": int(row.get("risk_score") or 0),
                "tone": "critical" if int(row.get("risk_score") or 0) >= 10 else "high" if int(row.get("risk_score") or 0) >= 6 else "warning" if int(row.get("risk_score") or 0) >= 2 else "stable",
            }
            for row in (priority_queue or [])[:36]
        ]
        task_text = " ".join(_text(task.get("title")) + " " + _text(task.get("detail")) for task in nursing_tasks).lower()
        omission_defs = [
            ("pressure", "压疮", "皮肤|压疮|翻身"),
            ("line", "管路", "管路|导管|置管"),
            ("rass", "RASS", "rass|镇静"),
            ("vte", "VTE", "vte|抗凝|血栓"),
            ("io", "出入量", "尿量|出入量|液体"),
        ]
        nursing_omissions = [
            {
                "key": key,
                "label": label,
                "status": "todo" if any(token in task_text for token in pattern.split("|")) else "ok",
                "action": "补核" if any(token in task_text for token in pattern.split("|")) else "已覆盖",
            }
            for key, label, pattern in omission_defs
        ]
        nursing_completion = {
            "percent": round(sum(1 for item in nursing_omissions if item["status"] == "ok") / max(1, len(nursing_omissions)) * 100),
            "tasks": [
                {"key": item["key"], "title": f"{item['label']}补核", "priority": "medium", "action": "生成护理任务"}
                for item in nursing_omissions
                if item["status"] == "todo"
            ][:6],
        }
        order_swimlanes = [
            {
                "patient_id": row.get("patient_id"),
                "bed": row.get("bed") or "--",
                "name": row.get("name") or "患者",
                "hisPid": row.get("hisPid") or "",
                "steps": [
                    {"label": "告警", "status": "done" if row.get("critical_alerts") else "idle"},
                    {"label": "医嘱", "status": "todo" if row.get("critical_alerts") else "idle"},
                    {"label": "执行", "status": "todo" if row.get("unacked_alerts") else "done"},
                    {"label": "复查", "status": "todo" if row.get("unacked_alerts") else "idle"},
                    {"label": "结果", "status": "idle"},
                ],
            }
            for row in (priority_queue or [])[:5]
        ]
        weaning_lights = []
        discharge_lights = []
        family_cards = []
        for row in (priority_queue or [])[:6]:
            score = int(row.get("risk_score") or 0)
            common = {"patient_id": row.get("patient_id"), "bed": row.get("bed"), "name": row.get("name"), "hisPid": row.get("hisPid") or ""}
            weaning_lights.append({**common, "lights": [{"label": "氧合", "ok": score < 6}, {"label": "循环", "ok": score < 8}, {"label": "意识", "ok": score < 5}, {"label": "SBT", "ok": score < 3}]})
            discharge_lights.append({**common, "lights": [{"label": "低危", "ok": score <= 1}, {"label": "无高危", "ok": not row.get("critical_alerts")}, {"label": "少未闭环", "ok": int(row.get("unacked_alerts") or 0) <= 1}], "percent": 67 if score <= 2 else 33, "task": "可转出复核" if score <= 2 else "继续留观"})
            family_cards.append({**common, "blocks": ["问题", "变化", "风险", "计划"], "readiness": 75 if row.get("latest_alert") else 55, "task": "生成家属沟通卡", "tone": "danger" if score >= 8 else "warn" if score >= 3 else "info"})
        return {
            "bed_heatmap": bed_heatmap,
            "nursing_omissions": nursing_omissions,
            "nursing_completion": nursing_completion,
            "order_swimlanes": order_swimlanes,
            "antibiotic_intensity": {"patients": [], "summary": {}, "fast": True},
            "weaning_lights": weaning_lights,
            "discharge_lights": discharge_lights,
            "rescue_timeline": [{"time": "24h", "title": item.get("title"), "tone": item.get("tone") or "info"} for item in quality_actions[:5]],
            "family_cards": family_cards,
            "fast": True,
        }

    async def role_home(self, *, role: str | None = None, dept: str | None = None, dept_code: str | None = None, user_name: str | None = None) -> dict[str, Any]:
        try:
            account = await asyncio.wait_for(self.resolve_account(user_name, fallback_role=role), timeout=0.8)
        except Exception:
            account = {"userName": user_name or "", "display_name": user_name or "", "role": role or "doctor", "found": False}
        role = _normalize_role_key(role or account.get("role"))
        dept = dept or account.get("dept")
        dept_code = dept_code or account.get("dept_code")
        try:
            patients = await self._patient_scope(dept=dept, dept_code=dept_code, limit=80)
        except Exception:
            patients = []
        role_distribution = [
            {"key": "nurse", "label": "护士", "value": 0},
            {"key": "doctor", "label": "医生", "value": 0},
            {"key": "head_nurse", "label": "护士长", "value": 0},
            {"key": "director", "label": "主任", "value": 0},
        ]
        patient_key_map: dict[str, str] = {}
        patient_keys: list[Any] = []
        for patient in patients:
            pid = str(patient.get("_id") or "")
            for key in self._patient_alert_keys(patient):
                patient_keys.append(key)
                patient_key_map[str(key)] = pid
        try:
            alerts = await self._recent_alerts(patient_keys, hours=24, limit=240)
        except Exception:
            alerts = []
        alerts_by_patient: dict[str, list[dict[str, Any]]] = {}
        for alert in alerts:
            alert_pid = patient_key_map.get(str(alert.get("patient_id") or ""), str(alert.get("patient_id") or ""))
            alerts_by_patient.setdefault(alert_pid, []).append(alert)

        priority_queue = []
        for patient in patients:
            pid = str(patient.get("_id") or "")
            rows = alerts_by_patient.get(pid, [])
            critical = sum(1 for row in rows if str(row.get("severity")).lower() in {"critical", "high"})
            unacked = sum(1 for row in rows if not row.get("acknowledged_at"))
            score = critical * 4 + unacked * 2 + len(rows)
            if score <= 0 and role not in {"head_nurse", "director"} and len(priority_queue) >= 12:
                continue
            priority_queue.append(
                {
                    "patient_id": pid,
                    "name": patient.get("name") or patient.get("hisName") or "未知患者",
                    "bed": patient.get("hisBed") or patient.get("bed") or "",
                    "dept": patient.get("hisDept") or patient.get("dept") or "",
                    "diagnosis": patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "",
                    "nursing_level": patient.get("nursingLevel") or "",
                    "hisPid": patient.get("hisPid") or patient.get("hisPID") or patient.get("pid") or "",
                    "risk_score": score,
                    "critical_alerts": critical,
                    "unacked_alerts": unacked,
                    "latest_alert": rows[0] if rows else None,
                }
            )
        priority_queue.sort(key=lambda row: (-int(row.get("risk_score") or 0), str(row.get("bed") or "")))

        unacked_total = sum(1 for row in alerts if not row.get("acknowledged_at"))
        high_total = sum(1 for row in alerts if str(row.get("severity")).lower() in {"critical", "high"})
        actioned = sum(1 for row in alerts if row.get("acknowledged_at") or row.get("ack_disposition"))
        median_actionability = None
        scores = [float(row.get("actionability_score")) for row in alerts if isinstance(row.get("actionability_score"), (int, float))]
        if scores:
            median_actionability = round(statistics.median(scores), 1)

        scanner_health = self._quick_scanner_health(alerts)
        noisy_scanners = [row for row in scanner_health.get("rows", []) if row.get("review_suggestion")]
        nursing_tasks = self._build_nursing_tasks(patients, alerts_by_patient)
        doctor_gaps = self._build_doctor_gaps(patients, alerts_by_patient, priority_queue)
        quality_actions = self._build_quality_actions(patients, alerts, alerts_by_patient, scanner_health)
        director_digest = self._build_director_digest(alerts, scanner_health, quality_actions)
        icu_day_flow = self._build_icu_day_flow(
            patients=patients,
            alerts=alerts,
            priority_queue=priority_queue,
            nursing_tasks=nursing_tasks,
            doctor_gaps=doctor_gaps,
            quality_actions=quality_actions,
            director_digest=director_digest,
        )
        ai_toolbox = self._build_ai_toolbox(
            priority_queue=priority_queue,
            doctor_gaps=doctor_gaps,
            nursing_tasks=nursing_tasks,
            scanner_health=scanner_health,
        )
        sticky_features = self._build_sticky_features(
            patients,
            alerts_by_patient,
            priority_queue,
            nursing_tasks,
            doctor_gaps,
            quality_actions,
            director_digest,
        )
        clinical_visuals = self._build_clinical_visuals_fast(
            priority_queue=priority_queue,
            nursing_tasks=nursing_tasks,
            quality_actions=quality_actions,
        )
        patient_ids = [str(patient.get("_id") or "") for patient in patients]
        try:
            open_tasks = await self._open_clinical_tasks_fast(patient_ids)
        except Exception:
            open_tasks = {"total": 0, "items": [], "degraded": True}

        role_cards = [
            {"key": "patients", "label": "在科患者", "value": len(patients), "tone": "info"},
            {"key": "high_alerts", "label": "高危告警", "value": high_total, "tone": "danger" if high_total else "stable"},
            {"key": "unacked", "label": "未闭环", "value": unacked_total, "tone": "warn" if unacked_total else "stable"},
            {"key": "actioned", "label": "24h已响应", "value": actioned, "tone": "stable"},
            {"key": "clinical_tasks", "label": "待处理任务", "value": open_tasks.get("total") or 0, "tone": "warn" if open_tasks.get("total") else "stable"},
        ]
        if role == "head_nurse":
            role_cards[2]["label"] = "需追踪任务"
            role_cards.append({"key": "workload", "label": "工作量中位", "value": median_actionability or 0, "tone": "info"})
        if role == "director":
            role_cards.append({"key": "scanner_review", "label": "规则需复核", "value": len(noisy_scanners), "tone": "warn" if noisy_scanners else "stable"})

        playbook = self._role_playbook(role)
        labels = self._role_labels(role)
        return {
            "role": role,
            "account": account,
            "title": labels["title"],
            "primary_message": labels["primary"],
            "cards": role_cards,
            "priority_queue": priority_queue[:30],
            "playbook": playbook,
            "scanner_review": noisy_scanners[:8],
            "nursing_tasks": nursing_tasks,
            "doctor_gaps": doctor_gaps,
            "quality_actions": quality_actions,
            "director_digest": director_digest,
            "icu_day_flow": icu_day_flow,
            "ai_toolbox": ai_toolbox,
            "sticky_features": sticky_features,
            "clinical_visuals": clinical_visuals,
            "open_tasks": open_tasks,
            "role_distribution": role_distribution,
            "generated_at": datetime.now(),
        }

    def _role_playbook(self, role: str) -> list[dict[str, str]]:
        base = {
            "nurse": [
                {"title": "先看未确认高危告警", "detail": "优先处理休克、氧合、尿量、管路和跌倒/压疮相关提醒。"},
                {"title": "交班前生成护理摘要", "detail": "把未完成任务、重点观察项和已处置事项带到交班。"},
                {"title": "不相关告警要点一下", "detail": "1秒反馈会进入规则健康，后续减少噪音。"},
            ],
            "head_nurse": [
                {"title": "看全科未闭环", "detail": "按床位追踪未确认、延迟响应和重复噪音。"},
                {"title": "看护理负荷", "detail": "高危告警、护理级别、管路和抢救期患者共同决定调配优先级。"},
                {"title": "导出质控线索", "detail": "月底质控会直接使用漏评漏做和闭环响应数据。"},
            ],
            "doctor": [
                {"title": "先看事件链", "detail": "按因果链理解过去24小时，而不是逐个系统翻数据。"},
                {"title": "看下一步缺口", "detail": "关注集束化治疗未完成、复查缺口、抗菌药/撤机/肾功能剂量问题。"},
                {"title": "交班摘要可编辑", "detail": "系统只整理事实，医生保留最终判断。"},
            ],
            "director": [
                {"title": "看规则健康", "detail": "阳性预测值低且覆盖率高的规则进入人工复核，不静默改阈值。"},
                {"title": "看质控趋势", "detail": "bundle达标、响应时间、噪音规则和典型病例用于晨会/质控会。"},
                {"title": "看科研队列", "detail": "把高价值场景沉淀为可追踪队列。"},
            ],
        }
        return base.get(role, base["doctor"])

    async def patient_story(self, patient_id: str, *, hours: int = 24) -> dict[str, Any]:
        pid = _text(patient_id)
        oid = ObjectId(pid) if ObjectId.is_valid(pid) else pid
        patient = await self.db.col("patient").find_one({"_id": oid}) or await self.db.col("patient").find_one({"_id": pid})
        if not patient:
            return {"patient_id": pid, "clusters": [], "summary": "患者不存在或已出科。"}
        since = datetime.now() - timedelta(hours=max(min(int(hours or 24), 72), 6))
        patient_ids: list[Any] = []
        seen_patient_ids: set[str] = set()
        for value in [pid, patient.get("_id"), *patient_his_pid_candidates(patient)]:
            if value is None:
                continue
            text = str(value).strip()
            marker = f"{type(value).__name__}:{text}"
            if text and marker not in seen_patient_ids:
                seen_patient_ids.add(marker)
                patient_ids.append(value)
            string_marker = f"str:{text}"
            if text and not isinstance(value, str) and string_marker not in seen_patient_ids:
                seen_patient_ids.add(string_marker)
                patient_ids.append(text)
        events: list[dict[str, Any]] = []
        async for alert in self.db.col("alert_records").find(
            {"patient_id": {"$in": patient_ids}, "created_at": {"$gte": since}},
            {"name": 1, "alert_type": 1, "rule_id": 1, "severity": 1, "created_at": 1, "ack_disposition": 1, "explanation": 1},
        ).sort("created_at", 1).limit(120):
            events.append({"time": alert.get("created_at"), "type": "alert", "title": self._event_title_from_alert(alert), "severity": alert.get("severity"), "raw": alert})
        async for score in self.db.col("score").find(
            {"$and": [{"$or": [{"patient_id": {"$in": patient_ids}}, {"pid": {"$in": patient_ids}}, {"hisPid": {"$in": patient_ids}}]}, {"$or": [{"calc_time": {"$gte": since}}, {"created_at": {"$gte": since}}]}]},
            {"score_type": 1, "score": 1, "risk_level": 1, "recommendation": 1, "calc_time": 1, "created_at": 1},
        ).sort("calc_time", 1).limit(80):
            title = _humanize_identifier(score.get("recommendation") or score.get("score_type") or "评分")
            if score.get("score") not in (None, ""):
                title = f"{title} {score.get('score')}"
            events.append({"time": score.get("calc_time") or score.get("created_at"), "type": "score", "title": title, "severity": score.get("risk_level"), "raw": score})
        async for drug in self.db.col("drugExe").find(
            {"$and": [{"$or": [{"pid": {"$in": patient_ids}}, {"patient_id": {"$in": patient_ids}}, {"hisPid": {"$in": patient_ids}}]}, {"$or": [{"exeTime": {"$gte": since}}, {"time": {"$gte": since}}]}]},
            {"drugName": 1, "name": 1, "dosage": 1, "dose": 1, "route": 1, "exeTime": 1, "time": 1},
        ).sort("exeTime", 1).limit(120):
            name = drug.get("drugName") or drug.get("name") or "用药"
            events.append({"time": drug.get("exeTime") or drug.get("time"), "type": "medication", "title": name, "severity": "info", "raw": drug})

        events = [row for row in events if _dt(row.get("time"))]
        events.sort(key=lambda row: _dt(row.get("time")) or datetime.min)
        clusters = self._cluster_events(events)
        return {
            "patient_id": pid,
            "patient_name": patient.get("name") or patient.get("hisName") or "未知患者",
            "bed": patient.get("hisBed") or patient.get("bed") or "",
            "hours": hours,
            "summary": self._story_summary(clusters),
            "clusters": clusters,
            "event_count": len(events),
            "matched_ids": [str(item) for item in patient_ids],
            "generated_at": datetime.now(),
        }

    def _cluster_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clusters: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        last_time: datetime | None = None
        for event in events:
            t = _dt(event.get("time"))
            if current and last_time and t and (t - last_time).total_seconds() > 3 * 3600:
                clusters.append(self._build_cluster(current))
                current = []
            current.append(event)
            last_time = t
        if current:
            clusters.append(self._build_cluster(current))
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for cluster in clusters:
            marker = f"{_text(cluster.get('headline'))}|{_text(cluster.get('summary'))}"
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(cluster)
        return deduped[-8:]

    def _build_cluster(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        first = _dt(events[0].get("time"))
        last = _dt(events[-1].get("time"))
        titles = [str(e.get("title") or "") for e in events[:8] if str(e.get("title") or "").strip()]
        titles = [_humanize_identifier(title) for title in titles]
        severity_rank = {"critical": 4, "high": 3, "warning": 2, "info": 1}
        top = max(events, key=lambda e: severity_rank.get(str(e.get("severity") or "").lower(), 0))
        return {
            "start_time": first,
            "end_time": last,
            "severity": top.get("severity") or "info",
            "headline": " → ".join(titles[:5]) if titles else "临床事件簇",
            "summary": self._cluster_summary(events),
            "events": events,
        }

    def _cluster_summary(self, events: list[dict[str, Any]]) -> str:
        text = " ".join(str(e.get("title") or "") for e in events).lower()
        if any(k in text for k in ["sepsis", "脓毒", "感染", "抗生素", "血培养"]):
            return "感染/脓毒症相关事件簇，请关注抗菌药、培养、乳酸复查和液体复苏闭环。"
        if any(k in text for k in ["spo2", "氧", "呼吸", "vent", "撤机", "拔管"]):
            return "呼吸支持相关事件簇，请关注氧合、通气参数、SBT和拔管后风险。"
        if any(k in text for k in ["map", "血压", "休克", "去甲", "乳酸"]):
            return "循环灌注相关事件簇，请关注升压药、容量状态、乳酸和器官灌注。"
        return "过去一段时间内出现连续临床事件，建议结合原始记录复核。"

    def _story_summary(self, clusters: list[dict[str, Any]]) -> str:
        if not clusters:
            return "过去窗口内未形成明显事件簇。"
        high = sum(1 for c in clusters if str(c.get("severity")).lower() in {"critical", "high"})
        return f"共形成 {len(clusters)} 个事件簇，其中 {high} 个高危簇，建议优先查看最近且未闭环的处置链。"

    async def handoff(self, patient_id: str, *, role: str = "doctor", hours: int = 12) -> dict[str, Any]:
        story = await self.patient_story(patient_id, hours=hours)
        clusters = story.get("clusters") or []
        action_items: list[str] = []
        seen_action_items: set[str] = set()
        for cluster in clusters[-3:]:
            item = _text(cluster.get("summary"))
            if not item or item in seen_action_items:
                continue
            seen_action_items.add(item)
            action_items.append(item)
        role_title = {"nurse": "护理交班", "head_nurse": "护士长追踪", "doctor": "医生交班", "director": "主任晨会"} .get(role, "交班")
        lines = [
            f"{role_title}: {story.get('bed') or '--'}床 {story.get('patient_name') or '未知患者'}",
            f"总体: {story.get('summary')}",
            "重点:",
            *[f"- {item}" for item in action_items if item],
        ]
        return {"patient_id": patient_id, "role": role, "handoff_text": "\n".join(lines), "story": story, "generated_at": datetime.now()}

    async def quality_summary(self, *, days: int = 30, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        scanner_health = await self.outcomes.scanner_health(days=days)
        rows = scanner_health.get("rows") or []
        patients = await self._patient_scope(dept=dept, dept_code=dept_code)
        patient_key_map: dict[str, str] = {}
        patient_keys: list[Any] = []
        for patient in patients:
            pid = str(patient.get("_id") or "")
            for key in self._patient_alert_keys(patient):
                patient_keys.append(key)
                patient_key_map[str(key)] = pid
        alerts = await self._recent_alerts(patient_keys, hours=24)
        alerts_by_patient: dict[str, list[dict[str, Any]]] = {}
        for alert in alerts:
            alert_pid = patient_key_map.get(str(alert.get("patient_id") or ""), str(alert.get("patient_id") or ""))
            alerts_by_patient.setdefault(alert_pid, []).append(alert)
        priority_queue = []
        for patient in patients:
            pid = str(patient.get("_id") or "")
            patient_alerts = alerts_by_patient.get(pid, [])
            critical = sum(1 for row in patient_alerts if str(row.get("severity")).lower() in {"critical", "high"})
            unacked = sum(1 for row in patient_alerts if not row.get("acknowledged_at"))
            score = critical * 4 + unacked * 2 + len(patient_alerts)
            priority_queue.append(
                {
                    "patient_id": pid,
                    "name": patient.get("name") or patient.get("hisName") or "未知患者",
                    "bed": patient.get("hisBed") or patient.get("bed") or "",
                    "risk_score": score,
                    "critical_alerts": critical,
                    "unacked_alerts": unacked,
                }
            )
        priority_queue.sort(key=lambda row: (-int(row.get("risk_score") or 0), str(row.get("bed") or "")))
        nursing_tasks = self._build_nursing_tasks(patients, alerts_by_patient)
        doctor_gaps = self._build_doctor_gaps(patients, alerts_by_patient, priority_queue)
        quality_actions = self._build_quality_actions(patients, alerts, alerts_by_patient, scanner_health)
        clinical_visuals = await self._build_clinical_visuals(
            patients=patients,
            alerts_by_patient=alerts_by_patient,
            priority_queue=priority_queue,
            nursing_tasks=nursing_tasks,
            doctor_gaps=doctor_gaps,
            quality_actions=quality_actions,
        )
        module_completion = self._build_module_completion(
            patients=patients,
            priority_queue=priority_queue,
            nursing_tasks=nursing_tasks,
            doctor_gaps=doctor_gaps,
            quality_actions=quality_actions,
            scanner_health=scanner_health,
            clinical_visuals=clinical_visuals,
        )
        # Bundle 合规评分
        bundle_compliance: dict[str, Any] = {}
        try:
            from app.services.bundle_compliance_service import BundleComplianceService
            bcs = BundleComplianceService(self.db)
            bundle_compliance = await asyncio.wait_for(
                bcs.daily_summary(dept=dept, dept_code=dept_code),
                timeout=8.0,
            )
        except Exception:
            bundle_compliance = {"bundles": {}, "overall_score": 0, "overall_tone": "red", "error": "bundle_compliance_timeout"}

        return {
            "days": days,
            "scanner_count": len(rows),
            "review_required": sum(1 for row in rows if row.get("review_suggestion")),
            "total_fired": sum(int(row.get("fired_count") or 0) for row in rows),
            "avg_ppv": round(sum(float(row.get("ppv") or 0) for row in rows) / len(rows), 3) if rows else 0,
            "scanner_health": rows[:20],
            "module_completion": module_completion,
            "bundle_compliance": bundle_compliance,
            "generated_at": datetime.now(),
        }

    async def upsert_clinical_task(self, payload: dict[str, Any], *, actor: str = "anonymous") -> dict[str, Any]:
        now = datetime.now()
        patient_id = _text(payload.get("patient_id"))
        title = _text(payload.get("title")) or "临床任务"
        module = _text(payload.get("module")) or "clinical_workflow"
        task_type = _text(payload.get("task_type")) or _text(payload.get("mode")) or "general"
        existing = await self.db.col("clinical_tasks").find_one(
            {
                "patient_id": patient_id,
                "title": title,
                "module": module,
                "task_type": task_type,
                "status": {"$in": ["open", "in_progress"]},
            }
        )
        if existing:
            await self.db.col("clinical_tasks").update_one(
                {"_id": existing["_id"]},
                {"$set": {"updated_at": now, "last_seen_at": now, "payload": payload}},
            )
            doc = await self.db.col("clinical_tasks").find_one({"_id": existing["_id"]})
            return {"task": serialize_doc(doc), "deduped": True}
        doc = {
            "task_id": str(uuid.uuid4()),
            "patient_id": patient_id or None,
            "bed": payload.get("bed"),
            "name": payload.get("name"),
            "module": module,
            "task_type": task_type,
            "title": title,
            "detail": _text(payload.get("detail")),
            "priority": payload.get("priority") or "medium",
            "status": "open",
            "payload": payload,
            "created_by": actor,
            "updated_by": actor,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.col("clinical_tasks").insert_one(doc)
        await write_audit_log(self.db, action="create_task", module=module, actor=actor, target_type="clinical_task", target_id=doc["task_id"], detail={"title": title, "patient_id": patient_id, "task_type": task_type})
        return {"task": serialize_doc(doc), "deduped": False}

    async def close_clinical_task(self, task_id: str, payload: dict[str, Any], *, actor: str = "anonymous") -> dict[str, Any]:
        now = datetime.now()
        update = {
            "status": "completed",
            "outcome": _text(payload.get("outcome")) or "已完成",
            "closed_by": actor,
            "closed_at": now,
            "updated_by": actor,
            "updated_at": now,
        }
        await self.db.col("clinical_tasks").update_one({"task_id": task_id}, {"$set": update})
        doc = await self.db.col("clinical_tasks").find_one({"task_id": task_id})
        await write_audit_log(self.db, action="close_task", module=(doc or {}).get("module") or "clinical_workflow", actor=actor, target_type="clinical_task", target_id=task_id, detail={"outcome": update["outcome"], "patient_id": (doc or {}).get("patient_id")})
        return {"task": serialize_doc(doc or {"task_id": task_id, **update})}
