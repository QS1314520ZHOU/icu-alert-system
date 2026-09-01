"""临床路径实例模型。

PathwayInstance: 一个患者的一次路径执行实例
PathwayTask: 路径中的具体任务项（Bundle 元素）
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PathwayInstanceStatus(StrEnum):
    """路径实例状态。"""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    TRANSFERRED = "transferred"


class TaskType(StrEnum):
    """任务类型。"""
    BUNDLE_ITEM = "bundle_item"        # Bundle 元素
    ASSESSMENT = "assessment"          # 评估
    LAB_ORDER = "lab_order"            # 检验
    DRUG_ORDER = "drug_order"          # 药物
    IMAGING = "imaging"                # 影像
    CONSULTATION = "consultation"      # 会诊
    NURSING = "nursing"                # 护理
    DOCUMENTATION = "documentation"    # 文书


class TaskStatus(StrEnum):
    """任务状态。"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_LATE = "completed_late"
    OVERDUE = "overdue"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    NOT_APPLICABLE = "not_applicable"


class TaskApplicability(StrEnum):
    """任务适用性。"""
    REQUIRED = "required"
    CONDITIONAL = "conditional"
    INDIVIDUALIZED = "individualized"
    NOT_APPLICABLE = "not_applicable"
    CONTRAINDICATED = "contraindicated"
    REVIEW_PENDING = "review_pending"


class PathwayInstance(BaseModel):
    """临床路径实例。

    一个患者的一次路径执行。从路径定义初始化任务列表，
    随着临床操作逐步完成任务。
    """
    id: str = ""
    case_id: str
    patient_id: str
    patient_name: str = ""
    pathway_id: str          # 关联的路径定义 ID
    disease_id: str
    disease_code: str = ""

    status: PathwayInstanceStatus = PathwayInstanceStatus.ACTIVE
    current_node_id: str = ""

    # 时间管理
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadline_1h: Optional[datetime] = None
    deadline_3h: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 合规统计
    compliance_ratio: Optional[float] = None
    completion_ratio: Optional[float] = None

    # 元数据
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PathwayTask(BaseModel):
    """路径任务。

    路径实例中的具体任务项。跟踪每个 Bundle 元素的执行状态。
    """
    id: str = ""
    instance_id: str         # 关联的路径实例 ID
    case_id: str
    patient_id: str = ""

    # 任务信息
    task_type: TaskType = TaskType.BUNDLE_ITEM
    task_key: str = ""       # 如 lactate, blood_culture, antibiotic_assessment
    name: str
    description: str = ""

    # 适用性（四维独立）
    applicability: TaskApplicability = TaskApplicability.REVIEW_PENDING
    execution_status: TaskStatus = TaskStatus.PENDING

    # 时间管理
    due_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    completed_by: str = ""

    # 关联证据
    evidence_ids: list[str] = Field(default_factory=list)

    # 临床审查
    review_status: str = "pending"  # pending, confirmed, overridden
    reviewed_by: str = ""
    reviewed_at: Optional[datetime] = None
    review_note: str = ""

    # 目标值（如补液目标）
    target_value: Optional[float] = None
    target_unit: str = ""
    actual_value: Optional[float] = None
    actual_unit: str = ""

    # 条件（条件触发的任务）
    condition_met: Optional[bool] = None
    condition_evidence: list[str] = Field(default_factory=list)

    # 元数据
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
