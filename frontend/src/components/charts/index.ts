/**
 * SmartCare AI — 可视化组件库统一导出
 *
 * 使用方式：
 *   import { ClinicalMetricCard, ClinicalTrendChart, RiskMatrix } from '@/components/charts'
 */

// ── 基础组件 ──────────────────────────────────────

export { default as ChartExplanation } from './base/ChartExplanation.vue'
export { default as ClinicalEmptyState } from './base/ClinicalEmptyState.vue'
export { default as DataFreshnessBadge } from './base/DataFreshnessBadge.vue'
export { default as ClinicalMetricCard } from './base/ClinicalMetricCard.vue'

// ── 趋势类 ────────────────────────────────────────

export { default as VitalSparkline } from './trend/VitalSparkline.vue'
export { default as ClinicalTrendChart } from './trend/ClinicalTrendChart.vue'
export { default as ScoreTrendChart } from './trend/ScoreTrendChart.vue'
export { default as MultiVitalTrendChart } from './trend/MultiVitalTrendChart.vue'

// ── 风险类 ────────────────────────────────────────

export { default as RiskMatrix } from './risk/RiskMatrix.vue'
export { default as DataCompletenessRing } from './risk/DataCompletenessRing.vue'
export { default as ICUBedMap } from './risk/ICUBedMap.vue'

// ── 时间线类 ──────────────────────────────────────

export { default as ClinicalTimeline } from './timeline/ClinicalTimeline.vue'

// ── 流程类 ────────────────────────────────────────

export { default as WorkflowDiagram } from './flow/WorkflowDiagram.vue'

// ── 告警类 ────────────────────────────────────────

export { default as AlertFunnel } from './alert/AlertFunnel.vue'

// ── 类型导出 ──────────────────────────────────────

export type { TrendSeries, ChartExplanationData } from './trend/ClinicalTrendChart.vue'
export type { VitalMetric, VitalExplanation } from './trend/MultiVitalTrendChart.vue'
export type { ScoreComponent, ScoreExplanation } from './trend/ScoreTrendChart.vue'
export type { MatrixPatient } from './risk/RiskMatrix.vue'
export type { BedInfo } from './risk/ICUBedMap.vue'
export type { TimelineEvent, TypeFilter } from './timeline/ClinicalTimeline.vue'
export type { WorkflowNode } from './flow/WorkflowDiagram.vue'
export type { FunnelStage } from './alert/AlertFunnel.vue'
