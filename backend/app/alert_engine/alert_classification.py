"""
告警分类模型 — 七维度正交分类 + 版本化精确注册表 + 升级链支持。

维度：
  1. alert_domain          — 告警领域（physiologic_alarm / clinical_risk / workflow_reminder / …）
  2. clinical_severity     — 临床严重度（仅临床域有效，nullable）
  3. priority              — 响应优先级（p0 / p1 / p2 / p3），仅用于排序
  4. workflow_urgency      — 流程紧迫度（overdue / due_soon / informational），仅流程域有效
  5. source_type           — 告警来源（rule / trained_model / heuristic / llm / manual / device_native / hybrid / unknown）
  6. response_target_seconds — SLA 响应目标（秒），允许每条规则覆盖
  7. route_targets         — 显式路由目标（owner_role + escalation_targets）

升级链字段（告警文档级别）：
  - alert_episode_id      — 同一临床事件的 episode 标识
  - escalation_of         — 被升级的原告警 _id
  - previous_priority     — 升级前的 priority
  - priority_history      — [{from, to, reason, time}] 升级历史
  - escalation_reason     — 升级原因说明
  - escalated_to          — 升级后的告警 _id（在原告警上标记）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# 枚举常量
# ═══════════════════════════════════════════════════════════════════════════════

ALERT_DOMAINS = frozenset({
    "physiologic_alarm",
    "clinical_risk",
    "workflow_reminder",
    "quality_gap",
    "data_quality",
    "ai_advisory",
    "unknown",
})

PRIORITIES = frozenset({"p0", "p1", "p2", "p3"})

SOURCE_TYPES = frozenset({
    "rule",
    "trained_model",
    "heuristic",
    "llm",
    "manual",
    "device_native",
    "hybrid",
    "unknown",
})

CLASSIFICATION_CONFIDENCE = frozenset({"high", "medium", "low"})

OWNER_ROLES = frozenset({"nurse", "doctor", "pharmacist", "head_nurse", "device_engineer", "it_staff"})

ESCALATION_POLICIES = frozenset({
    "immediate_escalation",
    "standard_escalation",
    "nursing_workflow",
    "routine_review",
    "data_quality_escalation",
})

DISPLAY_TONES = frozenset({"red", "orange", "amber", "yellow", "blue", "slate"})

WORKFLOW_URGENCIES = frozenset({"overdue", "due_soon", "informational"})

CLINICAL_SEVERITIES = frozenset({None, "mild", "moderate", "severe", "critical"})

# ═══════════════════════════════════════════════════════════════════════════════
# 优先级 → 默认 SLA（秒），但允许每条规则覆盖
# ═══════════════════════════════════════════════════════════════════════════════

PRIORITY_DEFAULT_SLA: dict[str, int] = {
    "p0": 300,      #  5 分钟
    "p1": 1800,     # 30 分钟
    "p2": 14400,    #  4 小时（本班处理）
    "p3": 86400,    # 24 小时
}


@dataclass
class AlertClassification:
    """一条告警的完整七维度分类 + 升级配置。"""

    alert_domain: str = "unknown"
    clinical_severity: str | None = None
    priority: str = "p2"
    workflow_urgency: str | None = None
    source_type: str = "rule"
    response_target_seconds: int = 14400
    escalation_policy: str = "nursing_workflow"
    display_tone: str = "amber"
    owner_role: str = "nurse"
    route_targets: list[str] = field(default_factory=lambda: ["nurse"])
    escalation_targets: list[str] = field(default_factory=list)
    classification_confidence: str = "high"
    # 升级触发条件（规则级默认值）
    escalation_after_minutes: int = 0   # 0=不自动升级
    escalation_after_repeats: int = 0   # 0=不按重复次数升级

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_domain": self.alert_domain,
            "clinical_severity": self.clinical_severity,
            "priority": self.priority,
            "workflow_urgency": self.workflow_urgency,
            "source_type": self.source_type,
            "response_target_seconds": self.response_target_seconds,
            "escalation_policy": self.escalation_policy,
            "display_tone": self.display_tone,
            "owner_role": self.owner_role,
            "route_targets": self.route_targets,
            "escalation_targets": self.escalation_targets,
            "classification_confidence": self.classification_confidence,
            "escalation_after_minutes": self.escalation_after_minutes,
            "escalation_after_repeats": self.escalation_after_repeats,
        }

    def apply_to_alert_doc(self, alert_doc: dict[str, Any]) -> dict[str, Any]:
        """将分类字段写入 alert_doc，保留 severity 向后兼容。"""
        d = self.to_dict()
        for key, value in d.items():
            alert_doc[key] = value
        return alert_doc


# ═══════════════════════════════════════════════════════════════════════════════
# 版本化精确分类注册表
# ═══════════════════════════════════════════════════════════════════════════════

REGISTRY_VERSION = "1.1.0"

_EXACT_CLASSIFICATION_MAP: dict[str, AlertClassification] = {}


def _register(rule_id: str, **kwargs: Any) -> None:
    """在注册表中注册一条分类。"""
    c = AlertClassification(**kwargs)  # type: ignore[arg-type]
    if c.alert_domain not in ALERT_DOMAINS:
        raise ValueError(f"Invalid alert_domain: {c.alert_domain}")
    if c.priority not in PRIORITIES:
        raise ValueError(f"Invalid priority: {c.priority}")
    if c.source_type not in SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {c.source_type}")
    _EXACT_CLASSIFICATION_MAP[rule_id] = c


# ── 生理危急告警（p0，路由护士+医生，立即升级） ──────────────────────────

_register("SEPSIS_SHOCK", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("CARDIAC_ARREST_RISK", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="trained_model", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("ARDS_SEVERE", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("LAB_K_CRIT_HIGH", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("LAB_K_CRIT_LOW", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("LAB_NA_CRIT_HIGH", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("LAB_NA_CRIT_LOW", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("LAB_LAC_CRIT", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("LAB_GLU_LOW", alert_domain="physiologic_alarm", clinical_severity="severe",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("LAB_HB_CRIT", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=600,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=10)

_register("LAB_PLT_CRIT", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=600,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=10)

_register("LAB_PCT_CRIT", alert_domain="physiologic_alarm", clinical_severity="severe",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("PE_SUSPECTED_HIGH", alert_domain="physiologic_alarm", clinical_severity="critical",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

# ── 临床风险（p1，路由护士+医生，标准升级） ──────────────────────────────

_register("AKI_STAGE_2", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("AKI_STAGE_3", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="rule", response_target_seconds=900,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=15)

_register("SOFA_ELEVATED", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("DIC_SCORE", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("DIC_SCORE_CRITICAL", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="rule", response_target_seconds=900,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=15)

_register("DELIRIUM_CAM_ICU_POSITIVE", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("DELIRIUM_RISK_HIGH", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="heuristic", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

_register("SEDATION_DELIRIUM_CONVERSION", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="heuristic", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("RESPIRATORY_DETERIORATION", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="trained_model", response_target_seconds=900,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=15)

_register("MULTI_ORGAN_DETERIORATION", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="trained_model", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("TEMPORAL_RISK_HIGH", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="trained_model", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

# ── 护理流程提醒（p2/p3，路由护士，升级护士长） ─────────────────────────
# source_type=rule：这些是基于规则的评估周期检查，不是启发式算法

_register("NURSE_CAM_ICU", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_CAM_ICU_UNASSESSABLE", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_PAIN", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_CPOT", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_CPOT_ANALGESIA_ADJUST", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=7200, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=120, escalation_after_repeats=2)

_register("NURSE_BPS", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_BPS_ANALGESIA_ADJUST", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=7200, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=120, escalation_after_repeats=2)

_register("NURSE_DELIRIUM", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_RASS", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_GCS", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_BRADEN", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=3)

_register("NURSE_TURNING_HIGH", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=7200, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=120, escalation_after_repeats=3)

_register("NURSE_TURNING_VERY_HIGH", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="overdue", source_type="rule",
          response_target_seconds=5400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=90, escalation_after_repeats=2)

_register("NURSE_TURNING_VERY_HIGH_ESCALATED", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule",
          response_target_seconds=1800, escalation_policy="standard_escalation",
          display_tone="orange", owner_role="nurse",
          route_targets=["nurse", "doctor"], escalation_targets=["head_nurse", "doctor"],
          escalation_after_minutes=30)

_register("NURSE_EARLY_MOBILITY", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p3", workflow_urgency="informational", source_type="rule",
          response_target_seconds=86400, escalation_policy="routine_review",
          display_tone="blue", owner_role="nurse",
          route_targets=["nurse"], escalation_targets=[])

# ── 质控缺项（p2，路由护士+护士长） ──────────────────────────────────────

_register("VTE_PROPHYLAXIS_OMISSION", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "head_nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("ECASH_BUNDLE_MISSING", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "head_nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("ABX_TIMEOUT", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor", "pharmacist"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("NUTRITION_START_DELAY", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("LIBERATION_BUNDLE_OVERDUE", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

# ── 数据质量（p1 关键中断 / p3 普通缺失） ────────────────────────────────

_register("DATA_MONITOR_INTERRUPTION", alert_domain="data_quality", clinical_severity=None,
          priority="p1", source_type="device_native", response_target_seconds=600,
          escalation_policy="data_quality_escalation", display_tone="slate",
          owner_role="nurse", route_targets=["nurse", "device_engineer", "it_staff"],
          escalation_targets=["device_engineer"],
          escalation_after_minutes=10, escalation_after_repeats=3)

_register("DATA_DEVICE_BIND_ERROR", alert_domain="data_quality", clinical_severity=None,
          priority="p1", source_type="device_native", response_target_seconds=600,
          escalation_policy="data_quality_escalation", display_tone="slate",
          owner_role="nurse", route_targets=["nurse", "device_engineer", "it_staff"],
          escalation_targets=["device_engineer"],
          escalation_after_minutes=10, escalation_after_repeats=3)

_register("DATA_MISSING_LAB", alert_domain="data_quality", clinical_severity=None,
          priority="p3", source_type="heuristic", response_target_seconds=86400,
          escalation_policy="routine_review", display_tone="slate",
          owner_role="nurse", route_targets=["nurse"], escalation_targets=[])

# ── AI 辅助建议（p3，路由医生） ────────────────────────────────────────────

_register("AI_RISK_ADVISORY", alert_domain="ai_advisory", clinical_severity=None,
          priority="p3", source_type="llm", response_target_seconds=86400,
          escalation_policy="routine_review", display_tone="blue",
          owner_role="doctor", route_targets=["doctor"], escalation_targets=[])

_register("AI_PERSONALIZED_THRESHOLD", alert_domain="ai_advisory", clinical_severity=None,
          priority="p3", source_type="trained_model", response_target_seconds=86400,
          escalation_policy="routine_review", display_tone="blue",
          owner_role="doctor", route_targets=["doctor"], escalation_targets=[])

# ── 临床风险扩展 ────────────────────────────────────────────────────────────

_register("SEPSIS_SOFA", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("SEPSIS_QSOFA", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("GI_BLEED", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("TRAJECTORY_DRIFT", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="trained_model", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

_register("FIBRINOLYSIS_HYPER", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("FIBRINOLYSIS_SHUTDOWN", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="rule", response_target_seconds=900,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=15)

# ── 药物安全 ────────────────────────────────────────────────────────────────

_register("DRUG_OVER_SEDATION", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="heuristic", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("DRUG_QT_RISK", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

_register("DRUG_OPIOID_HIGH_DOSE_RESP_RISK", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("DRUG_VANCO_NEPHRO", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

_register("DRUG_HIT", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("ARC_RISK_HIGH", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

# ── 抗菌药管理 ──────────────────────────────────────────────────────────────

_register("ABX_TIMEOUT_DEESCALATION", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("ABX_PCT_STOP_EVAL", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("ABX_TDM_VANCO_MISSING", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("ABX_DURATION_EXCEEDED_NO_CULTURE", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="doctor", route_targets=["doctor", "pharmacist"], escalation_targets=["doctor"],
          escalation_after_minutes=240, escalation_after_repeats=2)

# ── 营养监测 ────────────────────────────────────────────────────────────────

_register("NUTRITION_CALORIE_NOT_REACHED", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("NUTRITION_FEEDING_INTOLERANCE", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("NUTRITION_REFEEDING_RISK", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

# ── VTE 预防 ────────────────────────────────────────────────────────────────

_register("VTE_BLEEDING_LINKAGE", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "head_nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

_register("VTE_IMMOBILITY_NO_PROPHYLAXIS", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=7200,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "head_nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=120, escalation_after_repeats=2)

# ── 血糖管理 ────────────────────────────────────────────────────────────────

_register("GLU_HYPO", alert_domain="physiologic_alarm", clinical_severity="severe",
          priority="p0", source_type="rule", response_target_seconds=300,
          escalation_policy="immediate_escalation", display_tone="red",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=5)

_register("GLU_HYPER_CRITICAL", alert_domain="physiologic_alarm", clinical_severity="severe",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("GLU_VARIABILITY_HIGH", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p2", source_type="rule", response_target_seconds=7200,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=120)

# ── 呼吸机 / 撤机 ────────────────────────────────────────────────────────────

_register("VENT_DRIVING_PRESSURE", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("VENT_LUNG_PROTECTIVE", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=7200,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=120, escalation_after_repeats=2)

_register("VENT_POST_EXTUBATION_FAILURE_RISK", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="trained_model", response_target_seconds=900,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=15)

_register("VENT_WEAN_READY", alert_domain="workflow_reminder", clinical_severity=None,
          priority="p2", workflow_urgency="informational", source_type="rule",
          response_target_seconds=14400, escalation_policy="nursing_workflow",
          display_tone="amber", owner_role="nurse",
          route_targets=["nurse", "doctor"], escalation_targets=["doctor", "head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

# ── 昼夜节律 ────────────────────────────────────────────────────────────────

_register("CIRCADIAN_NIGHT_ALERT_SUMMARY", alert_domain="clinical_risk", clinical_severity=None,
          priority="p2", source_type="heuristic", response_target_seconds=28800,
          escalation_policy="routine_review", display_tone="blue",
          owner_role="nurse", route_targets=["nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=480)

# ── 脓毒症 bundle ────────────────────────────────────────────────────────────

_register("SEPSIS_BUNDLE_OVER_1H", alert_domain="quality_gap", clinical_severity=None,
          priority="p1", source_type="rule", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

_register("SEPSIS_BUNDLE_OVER_3H", alert_domain="quality_gap", clinical_severity=None,
          priority="p1", source_type="rule", response_target_seconds=10800,
          escalation_policy="standard_escalation", display_tone="yellow",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=180)

# ── 院感防控 ────────────────────────────────────────────────────────────────

_register("HAI_VAP_BUNDLE_MISSING", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "head_nurse"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)

# ── 复合恶化 ────────────────────────────────────────────────────────────────

_register("COMPOSITE_MODI_CRITICAL", alert_domain="clinical_risk", clinical_severity="severe",
          priority="p1", source_type="trained_model", response_target_seconds=900,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="doctor", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=15)

# ── CRRT ────────────────────────────────────────────────────────────────────

_register("CRRT_FILTER_CLOTTING", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="device_native", response_target_seconds=1800,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=30)

_register("CRRT_CITRATE_ICA", alert_domain="clinical_risk", clinical_severity="moderate",
          priority="p1", source_type="rule", response_target_seconds=3600,
          escalation_policy="standard_escalation", display_tone="orange",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["doctor"],
          escalation_after_minutes=60)

_register("CRRT_DOSE_INADEQUATE", alert_domain="quality_gap", clinical_severity=None,
          priority="p2", source_type="rule", response_target_seconds=14400,
          escalation_policy="nursing_workflow", display_tone="yellow",
          owner_role="nurse", route_targets=["nurse", "doctor"], escalation_targets=["head_nurse"],
          escalation_after_minutes=240, escalation_after_repeats=2)


# ═══════════════════════════════════════════════════════════════════════════════
# 精确查找
# ═══════════════════════════════════════════════════════════════════════════════

def lookup_classification(rule_id: str | None) -> AlertClassification | None:
    """在注册表中精确查找 rule_id。返回 None 表示需要推断。"""
    if not rule_id:
        return None
    return _EXACT_CLASSIFICATION_MAP.get(str(rule_id).strip())


def get_registry() -> dict[str, AlertClassification]:
    """返回完整注册表（只读副本）。"""
    return dict(_EXACT_CLASSIFICATION_MAP)


# ═══════════════════════════════════════════════════════════════════════════════
# 路由决策（统一入口）
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_route_targets(
    rule_id: str | None = None,
    alert_type: str = "",
    category: str = "",
    explicit_targets: list[str] | None = None,
) -> list[str]:
    """
    统一路由决策。

    优先级：
      1. 扫描器显式 route_targets（参数传入）
      2. rule_id 精确注册表
      3. alert_type 推断
      4. category 推断
      5. domain 兜底
    """
    # 1) 扫描器显式
    if explicit_targets:
        return list(dict.fromkeys(explicit_targets))

    # 2) rule_id 精确注册表
    cls = lookup_classification(rule_id)
    if cls is not None:
        return list(cls.route_targets)

    # 3-5) 推断
    inferred = infer_alert_classification({
        "rule_id": rule_id or "",
        "alert_type": alert_type,
        "category": category,
        "severity": "warning",
    })
    return list(inferred.route_targets)


# ═══════════════════════════════════════════════════════════════════════════════
# 注册表覆盖率报告
# ═══════════════════════════════════════════════════════════════════════════════

def generate_coverage_report() -> dict[str, Any]:
    """
    生成注册表覆盖率报告 — 扫描源码中所有静态 rule_id，
    对比注册表，输出精确匹配/模板匹配/alert_type推断/category推断/unknown。
    """
    import os
    import re

    registry = get_registry()
    registered = set(registry.keys())

    # 扫描源码中所有静态 rule_id
    source_rule_ids: set[str] = set()
    scan_root = os.path.dirname(os.path.abspath(__file__))
    for root, _dirs, files in os.walk(scan_root):
        for f in files:
            if not f.endswith('.py'):
                continue
            try:
                with open(os.path.join(root, f), encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
            except Exception:
                continue
            for m in re.finditer(r'rule_id\s*=\s*"([A-Za-z_][A-Za-z0-9_]*)"', content):
                source_rule_ids.add(m.group(1))
            for m in re.finditer(r'"rule_id"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"', content):
                source_rule_ids.add(m.group(1))

    # 分类
    exact_match = source_rule_ids & registered
    template_only = set()
    # Dynamic/f-string patterns: scan for f"..." rule_id patterns
    dynamic_count = 0
    for root, _dirs, files in os.walk(scan_root):
        for f in files:
            if not f.endswith('.py'):
                continue
            try:
                with open(os.path.join(root, f), encoding='utf-8', errors='ignore') as fh:
                    for line in fh:
                        if 'rule_id' in line and ('f"' in line or "f'" in line):
                            dynamic_count += 1
                            break
            except Exception:
                continue

    unregistered_exact = source_rule_ids - registered
    alert_type_inferrable = set()
    category_inferrable = set()
    unknown_from_source = set()

    for rid in unregistered_exact:
        rid_lower = rid.lower()
        # Check alert_type inference
        matched_at = False
        for at_key in _INFERENCE_ALERT_TYPE_MAP:
            if at_key in rid_lower:
                alert_type_inferrable.add(rid)
                matched_at = True
                break
        if matched_at:
            continue
        # Check if any registered rule_id is a prefix/suffix match (template)
        matched_template = False
        for reg_rid in registered:
            if rid.startswith(reg_rid) or reg_rid.startswith(rid):
                template_only.add(rid)
                matched_template = True
                break
            # Check suffix patterns like _CRIT, _HIGH, _LOW etc
            rid_parts = rid.split('_')
            reg_parts = reg_rid.split('_')
            if len(rid_parts) >= 3 and len(reg_parts) >= 3:
                if rid_parts[:2] == reg_parts[:2] or rid_parts[-2:] == reg_parts[-2:]:
                    template_only.add(rid)
                    matched_template = True
                    break
        if matched_template:
            continue
        unknown_from_source.add(rid)

    return {
        "registry_version": REGISTRY_VERSION,
        "source_total_static_rule_ids": len(source_rule_ids),
        "source_dynamic_fstring_patterns": dynamic_count,
        "registry_registered": len(registered),
        "exact_match": len(exact_match),
        "exact_match_rate": f"{len(exact_match) / max(len(source_rule_ids), 1) * 100:.1f}%",
        "template_match": len(template_only),
        "alert_type_inferrable": len(alert_type_inferrable),
        "category_inferrable": len(category_inferrable),
        "unknown_from_source": len(unknown_from_source),
        "unregistered_rule_ids": sorted(unregistered_exact),
        "template_matched_ids": sorted(template_only),
        "unknown_rule_ids": sorted(unknown_from_source),
        "p0_rules_exact": len([r for r, c in registry.items() if c.priority == "p0"]),
        "speech_rules_exact": len([r for r, c in registry.items()
                                   if c.alert_domain == "physiologic_alarm" and c.priority == "p0"]),
        "nursing_rules_exact": len([r for r, c in registry.items() if c.alert_domain == "workflow_reminder"]),
        "all_p0_exact": all(
            lookup_classification(r) is not None
            for r, c in registry.items() if c.priority == "p0"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 历史推断（版本化、置信度标注）
# ═══════════════════════════════════════════════════════════════════════════════

_INFERENCE_CATEGORY_MAP: dict[str, dict[str, str]] = {
    "vital_signs": {"default_domain": "physiologic_alarm", "default_priority": "p1"},
    "lab_results": {"default_domain": "physiologic_alarm", "default_priority": "p1"},
    "syndrome": {"default_domain": "clinical_risk", "default_priority": "p1"},
    "trend": {"default_domain": "clinical_risk", "default_priority": "p1"},
    "ventilator": {"default_domain": "clinical_risk", "default_priority": "p1"},
    "hemodynamic": {"default_domain": "clinical_risk", "default_priority": "p1"},
    "tbi": {"default_domain": "clinical_risk", "default_priority": "p1"},
    "drug_safety": {"default_domain": "quality_gap", "default_priority": "p2"},
    "antibiotic_stewardship": {"default_domain": "quality_gap", "default_priority": "p2"},
    "assessments": {"default_domain": "workflow_reminder", "default_priority": "p2"},
    "ai_analysis": {"default_domain": "ai_advisory", "default_priority": "p3"},
    "fluid_balance": {"default_domain": "clinical_risk", "default_priority": "p2"},
    "glycemic_control": {"default_domain": "clinical_risk", "default_priority": "p1"},
    "vte_prophylaxis": {"default_domain": "quality_gap", "default_priority": "p2"},
    "nutrition_monitor": {"default_domain": "quality_gap", "default_priority": "p2"},
    "composite_deterioration": {"default_domain": "clinical_risk", "default_priority": "p1"},
    "device_management": {"default_domain": "quality_gap", "default_priority": "p2"},
    "bundle": {"default_domain": "quality_gap", "default_priority": "p2"},
    "crrt": {"default_domain": "clinical_risk", "default_priority": "p2"},
    "dose_adjustment": {"default_domain": "clinical_risk", "default_priority": "p2"},
}

_INFERENCE_ALERT_TYPE_MAP: dict[str, dict[str, str]] = {
    "septic_shock": {"domain": "physiologic_alarm", "priority": "p0"},
    "cardiac_arrest": {"domain": "physiologic_alarm", "priority": "p0"},
    "nurse_reminder": {"domain": "workflow_reminder", "priority": "p2"},
    "cam_icu_positive": {"domain": "clinical_risk", "priority": "p1"},
    "delirium_risk": {"domain": "clinical_risk", "priority": "p1"},
    "ai_risk": {"domain": "ai_advisory", "priority": "p3"},
    "ards": {"domain": "clinical_risk", "priority": "p1"},
    "aki": {"domain": "clinical_risk", "priority": "p1"},
    "sofa": {"domain": "clinical_risk", "priority": "p1"},
    "qsofa": {"domain": "clinical_risk", "priority": "p1"},
    "dic": {"domain": "clinical_risk", "priority": "p1"},
    "pe_suspected": {"domain": "physiologic_alarm", "priority": "p0"},
    "pe_wells_high": {"domain": "physiologic_alarm", "priority": "p0"},
    "post_extubation": {"domain": "clinical_risk", "priority": "p1"},
    "weaning": {"domain": "clinical_risk", "priority": "p1"},
    "lab_threshold": {"domain": "physiologic_alarm", "priority": "p1"},
    "trend_analysis": {"domain": "clinical_risk", "priority": "p1"},
    "trajectory_drift": {"domain": "clinical_risk", "priority": "p1"},
    "ventilator_asynchrony": {"domain": "clinical_risk", "priority": "p1"},
    "tbi": {"domain": "clinical_risk", "priority": "p1"},
    "multi_organ_deterioration": {"domain": "clinical_risk", "priority": "p1"},
    "fluid_balance": {"domain": "clinical_risk", "priority": "p2"},
    "hypoglycemia": {"domain": "physiologic_alarm", "priority": "p0"},
    "glucose_drop_fast": {"domain": "clinical_risk", "priority": "p1"},
    "glucose_variability": {"domain": "clinical_risk", "priority": "p2"},
    "vte_prophylaxis_omission": {"domain": "quality_gap", "priority": "p2"},
    "vte_bleeding_linkage": {"domain": "quality_gap", "priority": "p2"},
    "vte_immobility": {"domain": "quality_gap", "priority": "p2"},
    "abx_timeout": {"domain": "quality_gap", "priority": "p2"},
    "abx_stop": {"domain": "quality_gap", "priority": "p2"},
    "abx_tdm": {"domain": "quality_gap", "priority": "p2"},
    "abx_duration": {"domain": "quality_gap", "priority": "p2"},
    "nutrition_start_delay": {"domain": "quality_gap", "priority": "p2"},
    "nutrition_calorie": {"domain": "quality_gap", "priority": "p2"},
    "nutrition_feeding": {"domain": "clinical_risk", "priority": "p1"},
    "nutrition_refeeding": {"domain": "clinical_risk", "priority": "p1"},
    "bundle": {"domain": "quality_gap", "priority": "p2"},
    "crrt": {"domain": "clinical_risk", "priority": "p1"},
    "vap": {"domain": "quality_gap", "priority": "p2"},
    "pupil": {"domain": "clinical_risk", "priority": "p1"},
    "icp": {"domain": "clinical_risk", "priority": "p1"},
    "cpp": {"domain": "clinical_risk", "priority": "p1"},
    "gi_bleeding": {"domain": "clinical_risk", "priority": "p1"},
    "sedation": {"domain": "clinical_risk", "priority": "p1"},
    "qt_risk": {"domain": "clinical_risk", "priority": "p1"},
    "qtc": {"domain": "clinical_risk", "priority": "p1"},
    "opioid": {"domain": "clinical_risk", "priority": "p1"},
    "ecash": {"domain": "quality_gap", "priority": "p2"},
    "liberation": {"domain": "quality_gap", "priority": "p2"},
    "cvc": {"domain": "quality_gap", "priority": "p2"},
    "foley": {"domain": "quality_gap", "priority": "p2"},
    "ett": {"domain": "quality_gap", "priority": "p2"},
    "pics": {"domain": "clinical_risk", "priority": "p2"},
    "hai": {"domain": "quality_gap", "priority": "p2"},
    "driving_pressure": {"domain": "clinical_risk", "priority": "p1"},
    "pplat": {"domain": "clinical_risk", "priority": "p1"},
    "mechanical_power": {"domain": "clinical_risk", "priority": "p2"},
    "right_heart": {"domain": "clinical_risk", "priority": "p1"},
    "proactive": {"domain": "ai_advisory", "priority": "p3"},
    "immuno": {"domain": "clinical_risk", "priority": "p1"},
    "micro": {"domain": "clinical_risk", "priority": "p1"},
    "postop": {"domain": "clinical_risk", "priority": "p1"},
    "steroid": {"domain": "clinical_risk", "priority": "p2"},
    "fibrinolysis": {"domain": "clinical_risk", "priority": "p1"},
    "nephrotoxicity": {"domain": "clinical_risk", "priority": "p1"},
    "vanco": {"domain": "quality_gap", "priority": "p2"},
    "beta_blocker": {"domain": "clinical_risk", "priority": "p1"},
    "aw_mobility": {"domain": "clinical_risk", "priority": "p2"},
    "early_mobility": {"domain": "workflow_reminder", "priority": "p3"},
    "prone": {"domain": "clinical_risk", "priority": "p1"},
    "forecast": {"domain": "ai_advisory", "priority": "p2"},
    "integrated_risk": {"domain": "ai_advisory", "priority": "p2"},
    "circadian": {"domain": "clinical_risk", "priority": "p2"},
}


def infer_alert_classification(alert_doc: dict[str, Any]) -> AlertClassification:
    """
    历史告警推断：当 alert_doc 缺少 alert_domain 时使用。

    推断优先级：
      1. 在注册表中精确匹配 rule_id
      2. 精确匹配 alert_type 映射
      3. 通过 category 映射
      4. 兜底：unknown / low 置信度
    """
    rule_id = str(alert_doc.get("rule_id") or "").strip()

    # 1) 精确注册表匹配
    exact = lookup_classification(rule_id)
    if exact is not None:
        return exact

    category = str(alert_doc.get("category") or "").strip().lower()
    alert_type = str(alert_doc.get("alert_type") or "").strip().lower()
    severity = str(alert_doc.get("severity") or "warning").strip().lower()

    # 2) alert_type 精确映射
    if alert_type in _INFERENCE_ALERT_TYPE_MAP:
        m = _INFERENCE_ALERT_TYPE_MAP[alert_type]
        domain = m["domain"]
        priority = m.get("priority", _severity_to_priority(severity))
        return _build_inferred(domain, priority, severity, alert_type, category, "high")

    # 3) category 映射
    if category in _INFERENCE_CATEGORY_MAP:
        m = _INFERENCE_CATEGORY_MAP[category]
        domain = m["default_domain"]
        priority = m.get("default_priority", _severity_to_priority(severity))
        return _build_inferred(domain, priority, severity, alert_type, category, "medium")

    # 4) 兜底：unknown
    return AlertClassification(
        alert_domain="unknown",
        priority=_severity_to_priority(severity),
        source_type="unknown",
        classification_confidence="low",
    )


def _severity_to_priority(severity: str) -> str:
    """旧 severity 到 priority 的降级映射（仅用于历史推断兜底）。"""
    s = str(severity or "").lower()
    if s in ("critical",):
        return "p0"
    if s in ("high",):
        return "p1"
    if s in ("warning",):
        return "p2"
    return "p3"


def _build_inferred(
    domain: str,
    priority: str,
    severity: str,
    alert_type: str,
    category: str,
    confidence: str,
) -> AlertClassification:
    """根据推断参数构建 AlertClassification。"""
    sla = PRIORITY_DEFAULT_SLA.get(priority, 14400)

    tone_map = {
        "physiologic_alarm": "red", "clinical_risk": "orange",
        "workflow_reminder": "amber", "quality_gap": "yellow",
        "data_quality": "slate", "ai_advisory": "blue", "unknown": "slate",
    }
    escalation_map = {
        "physiologic_alarm": "immediate_escalation", "clinical_risk": "standard_escalation",
        "workflow_reminder": "nursing_workflow", "quality_gap": "nursing_workflow",
        "data_quality": "data_quality_escalation", "ai_advisory": "routine_review",
        "unknown": "routine_review",
    }
    owner_map = {
        "physiologic_alarm": "doctor", "clinical_risk": "doctor",
        "workflow_reminder": "nurse", "quality_gap": "nurse",
        "data_quality": "nurse", "ai_advisory": "doctor", "unknown": "nurse",
    }

    route_targets: list[str] = [owner_map.get(domain, "nurse")]
    escalation_targets: list[str] = []
    if priority in ("p0", "p1") and domain in ("physiologic_alarm", "clinical_risk"):
        for r in ("nurse", "doctor"):
            if r not in route_targets:
                route_targets.append(r)
    if domain == "quality_gap" and "head_nurse" not in route_targets:
        route_targets.append("head_nurse")
    if domain == "workflow_reminder" and "head_nurse" not in escalation_targets:
        escalation_targets.append("head_nurse")

    clinical_severity = None
    if domain in ("physiologic_alarm", "clinical_risk"):
        sev_map = {"critical": "critical", "high": "severe", "warning": "moderate"}
        clinical_severity = sev_map.get(severity)

    workflow_urgency = "overdue" if domain == "workflow_reminder" else None

    return AlertClassification(
        alert_domain=domain, clinical_severity=clinical_severity,
        priority=priority, workflow_urgency=workflow_urgency,
        source_type="unknown", response_target_seconds=sla,
        escalation_policy=escalation_map.get(domain, "routine_review"),
        display_tone=tone_map.get(domain, "slate"),
        owner_role=owner_map.get(domain, "nurse"),
        route_targets=route_targets, escalation_targets=escalation_targets,
        classification_confidence=confidence,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 告警文档标准化（读取时 / API 返回前）
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_alert_doc(alert_doc: dict[str, Any]) -> dict[str, Any]:
    """确保告警文档包含完整的分类字段（历史记录读取时推断，不持久化）。"""
    if alert_doc.get("alert_domain"):
        return alert_doc
    classification = infer_alert_classification(alert_doc)
    enhanced = dict(alert_doc)
    classification.apply_to_alert_doc(enhanced)
    return enhanced


# ═══════════════════════════════════════════════════════════════════════════════
# 升级 episode 链辅助
# ═══════════════════════════════════════════════════════════════════════════════

def build_escalation_alert_doc(
    original_alert: dict[str, Any],
    new_rule_id: str,
    new_priority: str,
    reason: str,
    episode_id: str | None = None,
) -> dict[str, Any]:
    """
    构建升级告警文档。
    - 设置 escalation_of、previous_priority、priority_history
    - 使用新的 rule_id（绕过同规则抑制）
    - 继承 episode_id
    """
    now = datetime.now()
    episode = episode_id or original_alert.get("alert_episode_id") or str(original_alert.get("_id", ""))

    prev_history = original_alert.get("priority_history") or []
    if isinstance(prev_history, list):
        prev_history = list(prev_history)

    prev_history.append({
        "from": original_alert.get("priority", "p2"),
        "to": new_priority,
        "reason": reason,
        "time": now.isoformat(),
    })

    classification = lookup_classification(new_rule_id)
    escalated_doc = {
        "rule_id": new_rule_id,
        "name": original_alert.get("name", "升级告警"),
        "category": original_alert.get("category", ""),
        "alert_type": original_alert.get("alert_type", ""),
        "severity": original_alert.get("severity", "warning"),
        "parameter": original_alert.get("parameter"),
        "condition": original_alert.get("condition"),
        "value": original_alert.get("value"),
        "patient_id": original_alert.get("patient_id"),
        "patient_name": original_alert.get("patient_name"),
        "bed": original_alert.get("bed"),
        "dept": original_alert.get("dept"),
        "deptCode": original_alert.get("deptCode"),
        "device_id": original_alert.get("device_id"),
        "source_time": original_alert.get("source_time"),
        "created_at": now,
        "is_active": True,
        # 升级链字段
        "alert_episode_id": episode,
        "escalation_of": str(original_alert.get("_id", "")),
        "previous_priority": original_alert.get("priority", "p2"),
        "priority_history": prev_history,
        "escalation_reason": reason,
        "escalated_to": None,
    }
    if classification is not None:
        classification.apply_to_alert_doc(escalated_doc)
        # 覆盖为升级后的 priority
        escalated_doc["priority"] = new_priority

    return escalated_doc
