"""病例管理服务。

核心业务逻辑：
- 病例 CRUD 与去重（patient_id + encounter_id + disease_code + episode_no）
- 状态机流转（通过 CaseStateService 统一管理）
- 医生确认/排除
- 证据链查询
- 路径实例管理
- 总览仪表盘数据
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.disease_center import (
    DiseaseCase,
    DiseaseCaseStatus,
    CaseEvidence,
    ClinicalConfirmation,
    ConfirmationAction,
    PathwayInstance,
    PathwayInstanceStatus,
    PathwayTask,
    TaskStatus,
    TaskApplicability,
    can_transition,
)
from app.repositories import (
    CaseRepository,
    EvidenceRepository,
    ConfirmationRepository,
    PathwayInstanceRepository,
    PathwayTaskRepository,
    DiseaseRepository,
)


# 仓储实例
_case_repo = CaseRepository()
_evidence_repo = EvidenceRepository()
_confirm_repo = ConfirmationRepository()
_pathway_repo = PathwayInstanceRepository()
_task_repo = PathwayTaskRepository()
_disease_repo = DiseaseRepository()


def _gen_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================================
# 病例 CRUD
# =========================================================================


async def get_case(case_id: str) -> Optional[dict[str, Any]]:
    """获取病例详情。"""
    return await _case_repo.find_by_id(case_id)


async def list_cases(
    disease_id: Optional[str] = None,
    status: Optional[str] = None,
    patient_id: Optional[str] = None,
    dept: Optional[str] = None,
    risk_level: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
    sort_by: str = "last_evaluated_at",
    sort_order: int = -1,
) -> tuple[list[dict[str, Any]], int]:
    """查询病例列表，返回 (列表, 总数)。"""
    cases = await _case_repo.find_all(
        disease_id=disease_id,
        status=status,
        patient_id=patient_id,
        dept=dept,
        risk_level=risk_level,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await _case_repo.count_by_filters(
        disease_id=disease_id,
        status=status,
        patient_id=patient_id,
    )
    return cases, total


async def find_or_create_case(
    patient_id: str,
    disease_code: str,
    disease_id: str = "",
    disease_name: str = "",
    scanner_id: str = "",
    rule_id: str = "",
    rule_version: str = "",
    patient_name: str = "",
    bed: str = "",
    dept: str = "",
    encounter_id: str = "",
    episode_no: int = 1,
) -> dict[str, Any]:
    """查找或创建病例（去重）。

    去重维度：patient_id + encounter_id + disease_code + episode_no
    如果已有活动病例，更新评估时间；否则创建新病例。
    """
    now = _now()

    # 优先使用新的去重键
    if encounter_id:
        existing = await _case_repo.find_active_by_dedup_key(
            patient_id, encounter_id, disease_code, episode_no
        )
    else:
        existing = await _case_repo.find_active_by_patient_disease(
            patient_id, disease_code
        )

    if existing:
        # 更新现有病例的评估时间
        await _case_repo.update(existing["id"], {
            "last_evaluated_at": now,
            "scanner_id": scanner_id or existing.get("scanner_id", ""),
            "rule_id": rule_id or existing.get("rule_id", ""),
            "rule_version": rule_version or existing.get("rule_version", ""),
        })
        existing["last_evaluated_at"] = now
        return existing

    # 创建新病例
    case_id = _gen_id()
    case_data = {
        "id": case_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "bed": bed,
        "dept": dept,
        "encounter_id": encounter_id,
        "episode_no": episode_no,
        "disease_id": disease_id,
        "disease_code": disease_code,
        "disease_name": disease_name,
        "status": DiseaseCaseStatus.SCREENING,
        "scanner_id": scanner_id,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "first_detected_at": now,
        "last_evaluated_at": now,
        "created_by": "system",
    }
    await _case_repo.create(case_data)
    return case_data


# =========================================================================
# 状态机（委托给 CaseStateService）
# =========================================================================


async def update_case_screening_result(
    case_id: str,
    screening_score: Optional[float] = None,
    confidence: Optional[float] = None,
    risk_level: str = "",
    clinical_summary: Optional[dict[str, Any]] = None,
    rule_version: str = "",
) -> None:
    """更新病例筛查结果（由扫描器调用）。"""
    updates: dict[str, Any] = {
        "last_evaluated_at": _now(),
    }
    if screening_score is not None:
        updates["screening_score"] = screening_score
    if confidence is not None:
        updates["confidence"] = confidence
    if risk_level:
        updates["risk_level"] = risk_level
    if clinical_summary:
        updates["clinical_summary"] = clinical_summary
    if rule_version:
        updates["rule_version"] = rule_version

    await _case_repo.update(case_id, updates)


# =========================================================================
# 证据链
# =========================================================================


async def get_case_evidence(
    case_id: str,
    evidence_type: Optional[str] = None,
    matched: Optional[bool] = None,
    skip: int = 0,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """获取病例证据列表。"""
    return await _evidence_repo.find_by_case(
        case_id, evidence_type=evidence_type, matched=matched,
        skip=skip, limit=limit,
    )


async def get_evidence_completeness(case_id: str) -> dict[str, Any]:
    """获取病例证据完整度。"""
    return await _evidence_repo.get_evidence_completeness(case_id)


async def get_case_timeline(case_id: str) -> list[dict[str, Any]]:
    """获取病例时间线（证据 + 确认记录合并排序）。"""
    evidence = await _evidence_repo.get_timeline(case_id)
    confirmations = await _confirm_repo.find_by_case(case_id, limit=100)

    timeline = []
    for e in evidence:
        timeline.append({
            "type": "evidence",
            "id": e.get("id"),
            "timestamp": e.get("observed_at"),
            "data": e,
        })
    for c in confirmations:
        timeline.append({
            "type": "confirmation",
            "id": c.get("id"),
            "timestamp": c.get("created_at"),
            "data": c,
        })

    # 按时间排序
    timeline.sort(
        key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min,
        reverse=False,
    )
    return timeline


async def get_confirmation_history(case_id: str) -> list[dict[str, Any]]:
    """获取病例确认历史。"""
    return await _confirm_repo.find_by_case(case_id)


# =========================================================================
# 路径实例
# =========================================================================


async def get_pathway_instance(case_id: str) -> Optional[dict[str, Any]]:
    """获取病例的路径实例。"""
    return await _pathway_repo.find_by_case(case_id)


async def get_pathway_tasks(instance_id: str) -> list[dict[str, Any]]:
    """获取路径实例的任务列表。"""
    return await _task_repo.find_by_instance(instance_id)


async def get_case_tasks(case_id: str) -> list[dict[str, Any]]:
    """获取病例的所有任务。"""
    return await _task_repo.find_by_case(case_id)


async def complete_task(
    task_id: str,
    operator_id: str,
    actual_value: Optional[float] = None,
    note: str = "",
) -> dict[str, Any]:
    """完成路径任务。"""
    task = await _task_repo.find_by_id(task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    now = _now()
    is_late = False
    due = task.get("due_at")
    if due and isinstance(due, datetime) and now > due:
        is_late = True

    new_status = TaskStatus.COMPLETED_LATE if is_late else TaskStatus.COMPLETED
    await _task_repo.update(task_id, {
        "execution_status": new_status,
        "completed_at": now,
        "completed_by": operator_id,
        "actual_value": actual_value,
        "review_note": note,
    })

    # 记录确认日志
    await _confirm_repo.create({
        "id": _gen_id(),
        "case_id": task.get("case_id", ""),
        "patient_id": task.get("patient_id", ""),
        "action": ConfirmationAction.TASK_COMPLETE,
        "previous_status": task.get("execution_status", ""),
        "new_status": new_status,
        "operator_id": operator_id,
        "task_id": task_id,
        "task_type": task.get("task_type", ""),
    })

    task["execution_status"] = new_status
    task["completed_at"] = now
    task["completed_by"] = operator_id
    return task


async def update_pathway_compliance(instance_id: str) -> dict[str, Any]:
    """重新计算路径实例的合规率。"""
    tasks = await _task_repo.find_by_instance(instance_id)
    if not tasks:
        return {"compliance_ratio": None, "completion_ratio": None}

    applicable = [
        t for t in tasks
        if t.get("applicability") in (
            TaskApplicability.REQUIRED,
            TaskApplicability.CONDITIONAL,
            TaskApplicability.INDIVIDUALIZED,
        )
    ]
    completed = [
        t for t in applicable
        if t.get("execution_status") in (
            TaskStatus.COMPLETED,
            TaskStatus.COMPLETED_LATE,
        )
    ]
    completed_on_time = [
        t for t in applicable
        if t.get("execution_status") == TaskStatus.COMPLETED
    ]

    compliance = round(len(completed_on_time) / len(applicable), 4) if applicable else None
    completion = round(len(completed) / len(applicable), 4) if applicable else None

    await _pathway_repo.update(instance_id, {
        "compliance_ratio": compliance,
        "completion_ratio": completion,
    })

    return {
        "compliance_ratio": compliance,
        "completion_ratio": completion,
        "total_tasks": len(tasks),
        "applicable_tasks": len(applicable),
        "completed_tasks": len(completed),
        "completed_on_time": len(completed_on_time),
    }


# =========================================================================
# 总览仪表盘
# =========================================================================


async def get_dashboard_data() -> dict[str, Any]:
    """获取病种中心总览仪表盘数据。"""
    # 活跃病种数
    diseases = await _disease_repo.find_all(status="published", limit=1000)
    disease_count = len(diseases)

    # 今日新增病例
    today_new = await _case_repo.count_today_new()

    # 待医生确认病例数
    pending_review = await _case_repo.count_pending_review()

    # 各状态病例统计
    status_counts = await _case_repo.count_by_status()

    # 路径执行中病例数
    pathway_active = status_counts.get("pathway_active", 0)

    # 风险分布
    risk_dist = await _case_repo.get_risk_distribution()

    # 近 30 天病例趋势
    trend_30d = await _case_repo.get_case_trend(days=30)

    # 漏斗数据
    funnel = await _case_repo.get_funnel_data()

    # 质量指标
    quality = await _case_repo.get_quality_metrics()

    return {
        "disease_count": disease_count,
        "disease_total": disease_count,
        "today_new": today_new,
        "today_new_cases": today_new,
        "pending_review": pending_review,
        "pathway_active": pathway_active,
        "active_cases": pathway_active,
        "status_counts": status_counts,
        "risk_distribution": risk_dist,
        "case_trend": trend_30d,
        "funnel": funnel,
        "quality_metrics": quality,
    }


async def get_disease_dashboard(disease_id: str) -> dict[str, Any]:
    """获取单病种仪表盘数据。"""
    # 病种信息
    disease = await _disease_repo.find_by_id(disease_id)
    if not disease:
        raise ValueError(f"病种不存在: {disease_id}")

    # 病例统计
    status_counts = await _case_repo.count_by_status(disease_id=disease_id)
    total_cases = sum(status_counts.values())

    # 待确认数
    pending = status_counts.get("pending_review", 0)

    # 今日新增
    today_new = await _case_repo.count_today_new(disease_id=disease_id)

    # 风险分布
    risk_dist = await _case_repo.get_risk_distribution(disease_id=disease_id)

    # 趋势
    trend = await _case_repo.get_case_trend(disease_id=disease_id, days=30)

    # 路径超时
    overdue = await _pathway_repo.count_active_overdue(disease_id=disease_id)

    # 漏斗
    funnel = await _case_repo.get_funnel_data(disease_id=disease_id)

    # 质量指标
    quality = await _case_repo.get_quality_metrics(disease_id=disease_id)

    return {
        "disease": {
            "id": disease.get("id"),
            "name": disease.get("name"),
            "code": disease.get("code"),
            "status": disease.get("status"),
            "version": disease.get("version"),
        },
        "total_cases": total_cases,
        "status_counts": status_counts,
        "pending_review": pending,
        "today_new": today_new,
        "risk_distribution": risk_dist,
        "trend": trend,
        "overdue_pathways": overdue,
        "funnel": funnel,
        "quality_metrics": quality,
    }


async def get_funnel_data(disease_id: str) -> dict[str, Any]:
    """获取筛查漏斗数据（按"曾到达该阶段"统计）。"""
    return await _case_repo.get_funnel_data(disease_id=disease_id if disease_id else None)


# =========================================================================
# 证据写入（供扫描器调用）
# =========================================================================


async def add_evidence(
    case_id: str,
    patient_id: str,
    evidence_type: str,
    raw_value: Any,
    observed_at: datetime,
    source_collection: str = "",
    source_record_id: str = "",
    source_field: str = "",
    raw_unit: str = "",
    normalized_value: Optional[float] = None,
    normalized_unit: str = "",
    rule_id: str = "",
    rule_version: str = "",
    threshold: Optional[float] = None,
    threshold_operator: str = "",
    matched: bool = False,
    confidence: float = 1.0,
    quality_flags: Optional[list[str]] = None,
    explanation: str = "",
    disease_code: str = "",
) -> str:
    """添加病例证据（供扫描器调用）。"""
    evidence_id = _gen_id()
    await _evidence_repo.create({
        "id": evidence_id,
        "patient_id": patient_id,
        "case_id": case_id,
        "disease_code": disease_code,
        "evidence_type": evidence_type,
        "source_collection": source_collection,
        "source_record_id": source_record_id,
        "source_field": source_field,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "observed_at": observed_at,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "threshold": threshold,
        "threshold_operator": threshold_operator,
        "matched": matched,
        "confidence": confidence,
        "quality_flags": quality_flags or [],
        "explanation": explanation,
    })
    return evidence_id


async def add_evidence_batch(evidences: list[dict[str, Any]]) -> list[str]:
    """批量添加证据。"""
    if not evidences:
        return []
    return await _evidence_repo.create_many(evidences)
