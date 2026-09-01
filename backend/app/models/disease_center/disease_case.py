"""病种病例模型。

扫描器检出的临床病例，支持状态机流转和医生确认/排除。
去重维度：patient_id + encounter_id + disease_code + episode_no
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DiseaseCaseStatus(StrEnum):
    """病例状态。

    状态流转：
      screening → screen_positive → pending_review → confirmed → pathway_active → completed
                                  ↘ excluded
      confirmed → reconsideration_pending → excluded 或 confirmed
      completed/excluded → reopened（仅满足新证据条件）
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
    RECONSIDERATION_PENDING = "reconsideration_pending"
    REOPENED = "reopened"


# 允许的状态转换（统一状态机）
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
        DiseaseCaseStatus.RECONSIDERATION_PENDING,
    ],
    DiseaseCaseStatus.EXCLUDED: [
        DiseaseCaseStatus.REOPENED,  # 新证据重开
    ],
    DiseaseCaseStatus.PATHWAY_ACTIVE: [
        DiseaseCaseStatus.COMPLETED,
        DiseaseCaseStatus.TRANSFERRED,
        DiseaseCaseStatus.DECEASED,
    ],
    DiseaseCaseStatus.COMPLETED: [
        DiseaseCaseStatus.REOPENED,  # 新发事件重开
    ],
    DiseaseCaseStatus.TRANSFERRED: [],
    DiseaseCaseStatus.DECEASED: [],
    DiseaseCaseStatus.RECONSIDERATION_PENDING: [
        DiseaseCaseStatus.CONFIRMED,  # 重新确认
        DiseaseCaseStatus.EXCLUDED,   # 排除
    ],
    DiseaseCaseStatus.REOPENED: [
        DiseaseCaseStatus.SCREENING,  # 重新进入筛查
        DiseaseCaseStatus.SCREEN_POSITIVE,
    ],
}


def can_transition(current: str, target: str) -> bool:
    """检查状态转换是否合法。"""
    allowed = VALID_TRANSITIONS.get(current, [])
    return target in allowed


def compute_evidence_hash(
    case_id: str,
    source_collection: str,
    source_record_id: str,
    rule_id: str,
    rule_version: str,
) -> str:
    """计算证据唯一哈希，用于幂等写入。"""
    raw = f"{case_id}:{source_collection}:{source_record_id}:{rule_id}:{rule_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class DiseaseCase(BaseModel):
    """病种病例。

    由扫描器自动创建或医生手动创建，支持：
    - 自动筛查与去重（patient_id + encounter_id + disease_code + episode_no）
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

    # 去重维度
    encounter_id: str = ""      # 住院/就诊 ID
    episode_no: int = 1         # 同一住院内的事件序号

    # 活动病例唯一键（用于并发安全去重）
    # 格式: tenant_id:hospital_id:patient_id:encounter_id:disease_code:episode_no
    # 病例终结时清空，重开时重建
    active_case_key: str = ""

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

    # 时间戳（timezone-aware UTC）
    first_detected_at: Optional[datetime] = None
    last_evaluated_at: Optional[datetime] = None
    screen_positive_at: Optional[datetime] = None
    pending_review_at: Optional[datetime] = None

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

    # 病例生命周期
    resolved_at: Optional[datetime] = None
    reopened_at: Optional[datetime] = None
    suppressed_until: Optional[datetime] = None
    last_evidence_hash: str = ""
    last_material_change_at: Optional[datetime] = None
    source_alert_ids: list[str] = Field(default_factory=list)

    # 元数据
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
            DiseaseCaseStatus.RECONSIDERATION_PENDING,
        )
