"""临床结论模型。

将多条证据组合为临床结论（表型/筛查结论）。
支持：多条证据 → 综合表型 → 筛查结论 → 医生确认 → 临床路径
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ConclusionLevel(StrEnum):
    """结论级别。"""
    SCREENING = "screening"              # 筛查结论
    PHENOTYPE = "phenotype"              # 表型
    RISK_STRATIFICATION = "risk"         # 风险分层
    ORGAN_DYSFUNCTION = "organ"          # 器官功能异常
    CLINICAL_DIAGNOSIS = "clinical"      # 临床诊断（仅医生可下）


class ClinicalConclusion(BaseModel):
    """临床结论。

    由规则引擎从多条证据综合生成。
    结论本身不是诊断，而是系统筛查结果，需要医生确认。
    """
    id: str = ""
    case_id: str
    patient_id: str

    # 结论标识
    conclusion_code: str       # 如 SEPSIS_SCREEN_POSITIVE, AKI_KDIGO_2
    conclusion_label: str      # 如 "脓毒症筛查阳性", "KDIGO 2期"
    conclusion_level: ConclusionLevel = ConclusionLevel.SCREENING

    # 证据关联
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)

    # 规则关联
    rule_id: str = ""
    rule_version: str = ""

    # 置信度
    confidence: float = 0.0

    # 是否需要临床确认（系统结论必须经医生确认）
    requires_clinician_confirmation: bool = True

    # 结论详情
    detail: dict[str, Any] = Field(default_factory=dict)
    # detail 示例（脓毒症）：
    # {
    #     "infection_verdict": "supported",
    #     "qsofa_score": 2,
    #     "sofa_delta": 3,
    #     "organ_dysfunction": ["coagulation", "liver"],
    #     "shock_risk": "high"
    # }

    # 时间戳
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    superseded_at: Optional[datetime] = None
    superseded_by: str = ""  # 新结论 ID

    def is_current(self) -> bool:
        """是否为当前有效结论（未被取代）。"""
        return self.superseded_at is None

    def to_display(self) -> dict[str, Any]:
        """转换为前端展示格式。"""
        return {
            "id": self.id,
            "code": self.conclusion_code,
            "label": self.conclusion_label,
            "level": self.conclusion_level,
            "confidence": self.confidence,
            "requires_confirmation": self.requires_clinician_confirmation,
            "supporting_count": len(self.supporting_evidence_ids),
            "contradicting_count": len(self.contradicting_evidence_ids),
            "missing_count": len(self.missing_evidence),
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "detail": self.detail,
        }
