"""统一病例状态机服务。

所有状态转换必须通过此服务，确保：
- 转换合法性验证
- 不可变事件日志
- 时间戳更新
- 权限检查
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.disease_center import (
    DiseaseCaseStatus,
    ClinicalConfirmation,
    ConfirmationAction,
    can_transition,
)
from app.repositories import CaseRepository, ConfirmationRepository


_case_repo = CaseRepository()
_confirm_repo = ConfirmationRepository()


def _gen_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StateTransitionError(Exception):
    """状态转换错误。"""
    pass


class StateTransitionConflict(Exception):
    """状态转换并发冲突（CAS失败）。"""
    pass


class PermissionDeniedError(Exception):
    """权限不足。"""
    pass


# 权限矩阵：哪些角色可以执行哪些操作
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"confirm", "exclude", "recalculate", "complete_task", "reconsider"},
    "doctor": {"confirm", "exclude", "recalculate", "complete_task", "reconsider"},
    "nurse": {"complete_task"},
    "head_nurse": {"complete_task"},
    "charge_nurse": {"complete_task"},
    "director": {"confirm", "exclude", "recalculate", "complete_task", "reconsider"},
    "researcher": set(),
    "viewer": set(),
}


def check_permission(role: str, action: str) -> bool:
    """检查角色是否有执行操作的权限。"""
    allowed = ROLE_PERMISSIONS.get(role, set())
    return action in allowed


async def transition_case(
    case_id: str,
    new_status: str,
    operator_id: str,
    operator_name: str = "",
    operator_role: str = "",
    reason: str = "",
    clinical_note: str = "",
    action: ConfirmationAction = ConfirmationAction.STATUS_CHANGE,
    extra_updates: Optional[dict[str, Any]] = None,
    task_id: str = "",
    task_type: str = "",
) -> dict[str, Any]:
    """执行病例状态转换（原子CAS）。

    使用 MongoDB find_one_and_update 实现原子 Compare-And-Set：
    只有当病例当前状态等于预期状态时才执行更新。
    并发请求中只有一个能成功，其余返回 StateTransitionConflict。

    Raises:
        StateTransitionError: 非法状态转换或病例不存在
        StateTransitionConflict: 并发状态冲突
        PermissionDeniedError: 权限不足
    """
    # 先查询当前状态用于合法性验证和事件日志
    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise StateTransitionError(f"病例不存在: {case_id}")

    current_status = case.get("status", "")

    # 验证转换合法性
    if not can_transition(current_status, new_status):
        raise StateTransitionError(
            f"非法状态转换: {current_status} → {new_status}"
        )

    # 权限检查
    action_map = {
        ConfirmationAction.CONFIRM: "confirm",
        ConfirmationAction.EXCLUDE: "exclude",
        ConfirmationAction.RECALCULATE: "recalculate",
        ConfirmationAction.TASK_COMPLETE: "complete_task",
        ConfirmationAction.STATUS_CHANGE: "system-transition",
    }
    required_permission = action_map.get(action, "system-transition")
    if operator_role and not check_permission(operator_role, required_permission):
        raise PermissionDeniedError(
            f"角色 {operator_role} 无权执行 {required_permission} 操作"
        )

    now = _now()
    updates: dict[str, Any] = {}

    # 设置特定状态的时间戳
    if new_status == DiseaseCaseStatus.SCREEN_POSITIVE:
        updates["screen_positive_at"] = now
    elif new_status == DiseaseCaseStatus.PENDING_REVIEW:
        updates["pending_review_at"] = now
    elif new_status == DiseaseCaseStatus.CONFIRMED:
        updates["confirmed_at"] = now
        updates["confirmed_by"] = operator_id
    elif new_status == DiseaseCaseStatus.EXCLUDED:
        updates["excluded_at"] = now
        updates["excluded_by"] = operator_id
    elif new_status == DiseaseCaseStatus.REOPENED:
        updates["reopened_at"] = now
    elif new_status == DiseaseCaseStatus.COMPLETED:
        updates["resolved_at"] = now
    elif new_status == DiseaseCaseStatus.PATHWAY_ACTIVE:
        updates["pathway_started_at"] = now

    if extra_updates:
        updates.update(extra_updates)

    # 终结状态清空 active_case_key，允许同一去重键创建新病例
    if new_status in (
        DiseaseCaseStatus.COMPLETED,
        DiseaseCaseStatus.EXCLUDED,
        DiseaseCaseStatus.TRANSFERRED,
        DiseaseCaseStatus.DECEASED,
    ):
        updates["active_case_key"] = ""

    # 重开时需要重建 active_case_key（由调用方负责设置）

    # 原子CAS：只有当前状态匹配时才更新
    updated_case = await _case_repo.transition_status_atomic(
        case_id=case_id,
        expected_status=current_status,
        new_status=new_status,
        extra_updates=updates,
    )

    if updated_case is None:
        raise StateTransitionConflict(
            f"病例状态已被其他用户修改（当前状态可能已非 {current_status}），请刷新后重试"
        )

    # 记录不可变事件日志
    await _confirm_repo.create({
        "id": _gen_id(),
        "case_id": case_id,
        "patient_id": case.get("patient_id", ""),
        "action": action,
        "previous_status": current_status,
        "new_status": new_status,
        "operator_id": operator_id,
        "operator_name": operator_name,
        "operator_role": operator_role,
        "reason": reason,
        "clinical_note": clinical_note,
        "task_id": task_id,
        "task_type": task_type,
        "created_at": now,
    })

    return updated_case


async def confirm_case(
    case_id: str,
    operator_id: str,
    operator_name: str = "",
    operator_role: str = "doctor",
    reason: str = "",
    clinical_note: str = "",
) -> dict[str, Any]:
    """医生确认病例（纳入）。"""
    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise StateTransitionError(f"病例不存在: {case_id}")

    current = case.get("status", "")
    if current not in (
        DiseaseCaseStatus.PENDING_REVIEW,
        DiseaseCaseStatus.RECONSIDERATION_PENDING,
    ):
        raise StateTransitionError(f"当前状态 {current} 不允许确认")

    return await transition_case(
        case_id=case_id,
        new_status=DiseaseCaseStatus.CONFIRMED,
        operator_id=operator_id,
        operator_name=operator_name,
        operator_role=operator_role,
        reason=reason,
        clinical_note=clinical_note,
        action=ConfirmationAction.CONFIRM,
    )


async def exclude_case(
    case_id: str,
    operator_id: str,
    operator_name: str = "",
    operator_role: str = "doctor",
    reason: str = "",
    clinical_note: str = "",
    exclude_type: str = "other",  # false_positive, data_error, disease_change, differential, other
) -> dict[str, Any]:
    """医生排除病例。

    排除必须填写原因。
    """
    if not reason:
        raise StateTransitionError("排除操作必须填写原因")

    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise StateTransitionError(f"病例不存在: {case_id}")

    current = case.get("status", "")
    if current not in (
        DiseaseCaseStatus.SCREEN_POSITIVE,
        DiseaseCaseStatus.PENDING_REVIEW,
        DiseaseCaseStatus.RECONSIDERATION_PENDING,
    ):
        raise StateTransitionError(f"当前状态 {current} 不允许排除")

    return await transition_case(
        case_id=case_id,
        new_status=DiseaseCaseStatus.EXCLUDED,
        operator_id=operator_id,
        operator_name=operator_name,
        operator_role=operator_role,
        reason=reason,
        clinical_note=clinical_note,
        action=ConfirmationAction.EXCLUDE,
        extra_updates={"exclude_type": exclude_type},
    )


async def recalculate_case(
    case_id: str,
    operator_id: str = "system",
    operator_name: str = "",
    operator_role: str = "",
    reason: str = "手动触发重新计算",
) -> dict[str, Any]:
    """触发病例重新计算。"""
    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise StateTransitionError(f"病例不存在: {case_id}")

    current = case.get("status", "")
    # 只有特定状态允许重新计算
    if current not in (
        DiseaseCaseStatus.SCREENING,
        DiseaseCaseStatus.SCREEN_POSITIVE,
        DiseaseCaseStatus.PENDING_REVIEW,
        DiseaseCaseStatus.EXCLUDED,
    ):
        raise StateTransitionError(f"当前状态 {current} 不允许重新计算")

    return await transition_case(
        case_id=case_id,
        new_status=DiseaseCaseStatus.SCREENING,
        operator_id=operator_id,
        operator_name=operator_name,
        operator_role=operator_role,
        reason=reason,
        action=ConfirmationAction.RECALCULATE,
        extra_updates={
            "screening_score": None,
            "confidence": None,
            "risk_level": "",
        },
    )


async def reopen_case(
    case_id: str,
    operator_id: str = "system",
    operator_name: str = "",
    reason: str = "新证据触发重开",
) -> dict[str, Any]:
    """重开已完成或已排除的病例。

    仅在满足新证据条件时允许。
    """
    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise StateTransitionError(f"病例不存在: {case_id}")

    current = case.get("status", "")
    if current not in (
        DiseaseCaseStatus.COMPLETED,
        DiseaseCaseStatus.EXCLUDED,
    ):
        raise StateTransitionError(f"当前状态 {current} 不允许重开")

    return await transition_case(
        case_id=case_id,
        new_status=DiseaseCaseStatus.REOPENED,
        operator_id=operator_id,
        operator_name=operator_name,
        reason=reason,
        action=ConfirmationAction.STATUS_CHANGE,
    )
