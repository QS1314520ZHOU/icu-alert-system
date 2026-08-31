"""病种病例模型。

扫描器检出的临床病例，支持状态机流转和医生确认/排除。
同一患者 + 同一病种 = 同一活动病例（去重）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DiseaseCaseStatus(StrEnum):
    """病例状态。

    状态流转：
      screening → screen_positive → pending_review → confirmed → pathway_active → completed
                                  ↘ excluded（医生排除）
      screening → screen_positive → screening（重新计算，证据变化）
    """
    SCREENING = "screening"
    SCREEN_POSITIVE = "screen_positive"
    PENDING_REVIEW = "pending_review"
    CONFIRMED = "confirmed"
    EXCLUDED = "excluded"
    PATHWAY_ACTIVE = "pathway_active"
    COMPLETED = "completed"
    TRANSFERRED = "transferred"
    DECEASED = "deceased"


# 允许的状态转换
VALID_TRANSITIONS: dict[str, list[str]] = {
    DiseaseCaseStatus.SCREENING: [
        DiseaseCaseStatus.SCREEN_POSITIVE,
        DiseaseCaseStatus.SCREENING,  # 重新计算
    ],
    DiseaseCaseStatus.SCREEN_POSITIVE: [
        DiseaseCaseStatus.PENDING_REVIEW,
        DiseaseCaseStatus.SCREENING,  # 重新计算后降级
        DiseaseCaseStatus.EXCLUDED,   # 自动排除（罕见）
    ],
    DiseaseCaseStatus.PENDING_REVIEW: [
        DiseaseCaseStatus.CONFIRMED,
        DiseaseCaseStatus.EXCLUDED,
        DiseaseCaseStatus.SCREENING,  # 重新计算
    ],
    DiseaseCaseStatus.CONFIRMED: [
        DiseaseCaseStatus.PATHWAY_ACTIVE,
        DiseaseCaseStatus.COMPLETED,
        DiseaseCaseStatus.TRANSFERRED,
        DiseaseCaseStatus.DECEASED,
    ],
    DiseaseCaseStatus.EXCLUDED: [
        DiseaseCaseStatus.PENDING_REVIEW,  # 新证据重新触发
        DiseaseCaseStatus.SCREENING,
    ],
    DiseaseCaseStatus.PATHWAY_ACTIVE: [
        DiseaseCaseStatus.COMPLETED,
        DiseaseCaseStatus.TRANSFERRED,
        DiseaseCaseStatus.DECEASED,
    ],
    DiseaseCaseStatus.COMPLETED: [],
    DiseaseCaseStatus.TRANSFERRED: [],
    DiseaseCaseStatus.DECEASED: [],
}


def can_transition(current: str, target: str) -> bool:
    """检查状态转换是否合法。"""
    allowed = VALID_TRANSITIONS.get(current, [])
    return target in allowed


class DiseaseCase(BaseModel):
    """病种病例。

    由扫描器自动创建或医生手动创建，支持：
    - 自动筛查与去重（同一患者+同一病种=同一活动病例）
    - 状态机流转
    - 医生确认/排除
    - 临床路径关联
    - 规则版本追踪
    """
    id: str = ""
    patient_id: str
    patient_name: str = ""
    bed: str = ""
    dept: str = ""

    # 病种关联
    disease_id: str = ""
    disease_code: str
    disease_name: str = ""

    # 状态
    status: DiseaseCaseStatus = DiseaseCaseStatus.SCREENING

    # 扫描器信息
    scanner_id: str = ""
    rule_id: str = ""
    rule_version: str = ""

    # 筛查信息
    screening_score: Optional[float] = None
    confidence: Optional[float] = None
    risk_level: str = ""  # low, warning, high, critical

    # 临床摘要（结构化，由扫描器填充）
    clinical_summary: dict[str, Any] = Field(default_factory=dict)

    # 时间戳
    first_detected_at: Optional[datetime] = None
    last_evaluated_at: Optional[datetime] = None
    screen_positive_at: Optional[datetime] = None

    # 医生确认
    confirmed_by: str = ""
    confirmed_at: Optional[datetime] = None
    confirm_reason: str = ""

    # 医生排除
    excluded_by: str = ""
    excluded_at: Optional[datetime] = None
    exclude_reason: str = ""

    # 路径关联
    pathway_instance_id: str = ""

    # 元数据
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = "system"

    def is_active(self) -> bool:
        """是否为活动病例（未终结）。"""
        return self.status not in (
            DiseaseCaseStatus.COMPLETED,
            DiseaseCaseStatus.TRANSFERRED,
            DiseaseCaseStatus.DECEASED,
        )

    def is_actionable(self) -> bool:
        """是否需要临床行动（待确认或路径中）。"""
        return self.status in (
            DiseaseCaseStatus.PENDING_REVIEW,
            DiseaseCaseStatus.CONFIRMED,
            DiseaseCaseStatus.PATHWAY_ACTIVE,
        )
