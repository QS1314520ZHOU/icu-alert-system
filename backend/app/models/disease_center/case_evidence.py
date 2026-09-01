"""病例证据模型。

每条证据记录一个临床数据点从原始值到规则判断的完整链路。
支持证据链可视化和数据溯源。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvidenceType(StrEnum):
    """证据类型。"""
    VITAL_SIGN = "vital_sign"          # 生命体征
    LAB_RESULT = "lab_result"          # 检验结果
    DRUG = "drug"                      # 药物
    ASSESSMENT = "assessment"          # 评估量表
    IMAGING = "imaging"                # 影像
    CLINICAL_NOTE = "clinical_note"    # 临床文书
    DIAGNOSIS = "diagnosis"            # 诊断
    PROCEDURE = "procedure"            # 操作
    DEVICE = "device"                  # 设备数据
    NURSING = "nursing"                # 护理记录
    CONCLUSION = "conclusion"          # 综合结论
    MISSING_DATA = "missing_data"      # 数据缺失
    QUALITY_FLAG = "quality_flag"      # 数据质量标记


class EvidenceQualityFlag(StrEnum):
    """证据质量标记。"""
    NORMAL = "normal"
    MISSING = "missing"                # 数据缺失
    STALE = "stale"                    # 数据过期
    CONFLICT = "conflict"              # 数据冲突
    LOW_CONFIDENCE = "low_confidence"  # 低置信度
    UNIT_MISMATCH = "unit_mismatch"    # 单位不匹配
    OUTLIER = "outlier"                # 异常值
    MANUAL_OVERRIDE = "manual_override"  # 人工覆盖


class CaseEvidence(BaseModel):
    """病例证据。

    记录一个临床数据点的完整链路：
    原始值 → 标准化 → 规则判断 → 医生确认

    每条证据关联到具体的源记录，支持数据溯源。
    使用 evidence_hash 实现幂等写入。
    """
    id: str = ""
    patient_id: str
    case_id: str
    disease_code: str = ""

    # 证据分类
    evidence_type: EvidenceType

    # 数据来源（支持溯源）
    source_collection: str = ""    # MongoDB 集合名
    source_record_id: str = ""     # 来源记录 _id
    source_field: str = ""         # 来源字段名

    # 原始值
    raw_value: Any = None
    raw_unit: str = ""

    # 标准化值
    normalized_value: Optional[float] = None
    normalized_unit: str = ""

    # 观测时间
    observed_at: Optional[datetime] = None

    # 规则关联
    rule_id: str = ""
    rule_version: str = ""

    # 增强规则表达（替代简单 threshold）
    criterion_id: str = ""
    criterion: dict[str, Any] = Field(default_factory=dict)
    # criterion 示例：
    # {
    #     "type": "temporal_ratio",
    #     "field": "creatinine",
    #     "operator": "gte",
    #     "value": 2,
    #     "window_hours": 168,
    #     "baseline_strategy": "stable_pre_admission",
    #     "display": "7天内肌酐达到基线2倍"
    # }

    # 指南来源
    guideline_source: str = ""
    guideline_version: str = ""
    guideline_reference: str = ""

    # 基线值
    baseline_value: Any = None
    baseline_source: str = ""
    baseline_confidence: Optional[float] = None

    # 聚合方式
    aggregation_method: str = ""  # max, min, mean, latest, delta, ratio
    time_window: dict[str, Any] = Field(default_factory=dict)

    # 旧字段兼容
    threshold: Optional[float] = None
    threshold_operator: str = ""   # gt, gte, lt, lte, eq, neq
    matched: bool = False
    confidence: float = 1.0

    # 幂等哈希
    evidence_hash: str = ""

    # 证据版本管理
    supersedes_evidence_id: str = ""  # 被此证据取代的旧证据 ID
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

    # 质量标记
    quality_flags: list[str] = Field(default_factory=list)

    # 可读说明（由规则引擎生成，非 AI 生成）
    explanation: str = ""

    # 特征名称（用于证据链展示）
    feature_name: str = ""

    # 元数据
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_chain_node(self) -> dict[str, Any]:
        """转换为证据链节点格式（供前端 EvidenceChain 组件使用）。"""
        return {
            "id": self.id,
            "evidence_type": self.evidence_type,
            "feature_name": self.feature_name,
            "data_name": self.source_field or self.evidence_type,
            "raw_value": self.raw_value,
            "raw_unit": self.raw_unit,
            "normalized_value": self.normalized_value,
            "normalized_unit": self.normalized_unit,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "source": self.source_collection,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "criterion": self.criterion,
            "threshold": self.threshold,
            "threshold_operator": self.threshold_operator,
            "matched": self.matched,
            "confidence": self.confidence,
            "quality_flags": self.quality_flags,
            "explanation": self.explanation,
            "guideline_source": self.guideline_source,
            "baseline_value": self.baseline_value,
            "baseline_source": self.baseline_source,
        }
