"""临床确认记录模型。

记录医生对病例的所有人工操作：确认、排除、修改、重新计算。
不可变审计日志——记录一旦创建不可修改或删除。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ConfirmationAction(StrEnum):
    """确认操作类型。"""
    CONFIRM = "confirm"            # 医生确认病例
    EXCLUDE = "exclude"            # 医生排除病例
    MODIFY = "modify"              # 修改病例信息
    RECALCULATE = "recalculate"    # 触发重新计算
    TASK_COMPLETE = "task_complete"  # 完成路径任务
    STATUS_CHANGE = "status_change"  # 状态变更


class ClinicalConfirmation(BaseModel):
    """临床确认记录。

    不可变审计日志——每次医生操作创建一条记录。
    支持操作回溯和审计。
    """
    id: str = ""
    case_id: str
    patient_id: str

    # 操作信息
    action: ConfirmationAction
    previous_status: str = ""
    new_status: str = ""

    # 操作人
    operator_id: str
    operator_name: str = ""
    operator_role: str = ""

    # 操作原因和备注
    reason: str = ""
    clinical_note: str = ""

    # 关联的任务（如果是完成任务）
    task_id: str = ""
    task_type: str = ""

    # 变更详情
    changes: dict[str, Any] = Field(default_factory=dict)

    # 时间戳（不可变）
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
