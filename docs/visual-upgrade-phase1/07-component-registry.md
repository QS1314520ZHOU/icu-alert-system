# 可复用可视化组件注册表

## 说明

本表列出本次升级需要新建的所有可视化组件。每个组件必须满足：
- TypeScript Props 类型定义
- 加载状态 / 空状态 / 错误状态 / 无权限状态 / 数据过期状态
- 响应式布局
- 演示数据
- 真实接口适配层

---

## 基础组件（所有页面共用）

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `ClinicalMetricCard` | 临床指标卡片（大数字+趋势+状态） | CSS | P0 | ⏳ |
| `VitalSparkline` | 迷你趋势线（嵌入表格/卡片） | ECharts mini | P0 | ⏳ |
| `DataCompletenessRing` | 数据完整度环图 | ECharts gauge | P0 | ⏳ |
| `DataFreshnessBadge` | 数据新鲜度标识 | CSS | P0 | ⏳ |
| `ChartExplanation` | 图表下方图文说明 | CSS | P0 | ⏳ |
| `ClinicalEmptyState` | 临床空状态组件 | CSS | P0 | ⏳ |
| `MissingDataPanel` | 缺失数据面板 | CSS | P0 | ⏳ |
| `StatusBadge` | 统一状态标签（已有，需扩展） | CSS | P0 | 已有 |

## 趋势类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `ClinicalTrendChart` | 单指标临床趋势（含正常范围带+事件标记） | ECharts line | P0 | ⏳ |
| `MultiVitalTrendChart` | 多指标生命体征趋势（多Y轴） | ECharts line | P0 | ⏳ |
| `ScoreTrendChart` | 评分趋势图（SOFA/NEWS2/qSOFA） | ECharts line | P0 | ⏳ |
| `ScoreComponentChart` | 评分分项堆叠图 | ECharts stacked bar | P1 | ⏳ |

## 风险类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `RiskMatrix` | 患者风险矩阵散点图 | ECharts scatter | P0 | ⏳ |
| `RiskDistributionChart` | 风险等级分布图 | ECharts pie/bar | P1 | ⏳ |
| `OrganRiskMap` | 器官风险人体图 | SVG + CSS | P0 | ⏳ |
| `BedRiskCard` | 床位风险卡片 | CSS | P0 | ⏳ |
| `ICUBedMap` | ICU床位风险地图 | CSS Grid | P0 | ⏳ |

## 时间线/事件类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `ClinicalTimeline` | 临床事件时间线（水平/垂直） | ECharts custom / CSS | P0 | ⏳ |
| `EventSwimlane` | 事件泳道图（多泳道） | ECharts custom | P0 | ⏳ |

## 流程类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `WorkflowDiagram` | 可交互流程图（节点+连线） | ECharts Graph / SVG | P1 | ⏳ |
| `EvidenceGraph` | 证据关系有向图 | ECharts Graph | P1 | ⏳ |
| `TaskStatusFlow` | 任务状态流转图 | CSS / SVG | P1 | ⏳ |

## 告警类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `AlertFunnel` | 告警处置漏斗图 | ECharts funnel | P0 | ⏳ |

## 质控类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `QualityControlChart` | 质控控制图（含目标线/UCL/LCL） | ECharts line | P2 | ⏳ |
| `QualityHeatmap` | 质控指标热力图 | ECharts heatmap | P2 | ⏳ |

## 规则/AI类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `ScannerTopology` | 规则依赖拓扑图 | ECharts Graph | P2 | ⏳ |
| `ModelRoutingDiagram` | AI路由图 | ECharts Graph | P2 | ⏳ |
| `ServiceTopology` | 系统服务拓扑图 | ECharts Graph | P2 | ⏳ |

## 科研类组件

| 组件名 | 说明 | 图表类型 | 优先级 | 状态 |
|--------|------|----------|--------|------|
| `CohortFlowDiagram` | 队列筛选流程图 | ECharts funnel | P3 | ⏳ |
| `TrialScreeningFunnel` | 试验筛选漏斗 | ECharts funnel | P3 | ⏳ |
| `BeforeAfterComparison` | 治疗前后对比图 | ECharts bar | P1 | ⏳ |

---

## 组件接口规范

每个组件必须暴露以下Props：

```typescript
interface BaseVisualizationProps {
  /** 加载状态 */
  loading?: boolean
  /** 错误信息 */
  error?: string | null
  /** 空状态提示 */
  emptyMessage?: string
  /** 数据过期时间（ISO字符串） */
  dataExpiredAt?: string
  /** 是否有权限 */
  hasPermission?: boolean
  /** 图表说明（显示在图表下方） */
  explanation?: ChartExplanation
  /** 容器高度 */
  height?: number | string
}

interface ChartExplanation {
  /** 图表说明 */
  description: string
  /** 当前关键发现 */
  keyFinding?: string
  /** 数据来源 */
  source?: string
  /** 数据时间 */
  dataTime?: string
  /** 查看原始数据入口 */
  rawDataRoute?: string
}
```

---

## 组件目录结构

```
frontend/src/components/charts/
├── base/
│   ├── ClinicalMetricCard.vue
│   ├── VitalSparkline.vue
│   ├── DataCompletenessRing.vue
│   ├── DataFreshnessBadge.vue
│   ├── ChartExplanation.vue
│   ├── ClinicalEmptyState.vue
│   └── MissingDataPanel.vue
├── trend/
│   ├── ClinicalTrendChart.vue
│   ├── MultiVitalTrendChart.vue
│   ├── ScoreTrendChart.vue
│   └── ScoreComponentChart.vue
├── risk/
│   ├── RiskMatrix.vue
│   ├── RiskDistributionChart.vue
│   ├── OrganRiskMap.vue
│   ├── BedRiskCard.vue
│   └── ICUBedMap.vue
├── timeline/
│   ├── ClinicalTimeline.vue
│   └── EventSwimlane.vue
├── flow/
│   ├── WorkflowDiagram.vue
│   ├── EvidenceGraph.vue
│   └── TaskStatusFlow.vue
├── alert/
│   └── AlertFunnel.vue
├── quality/
│   ├── QualityControlChart.vue
│   └── QualityHeatmap.vue
├── ai/
│   ├── ScannerTopology.vue
│   ├── ModelRoutingDiagram.vue
│   └── ServiceTopology.vue
└── research/
    ├── CohortFlowDiagram.vue
    ├── TrialScreeningFunnel.vue
    └── BeforeAfterComparison.vue
```

---

## 统一导出

```typescript
// frontend/src/components/charts/index.ts

// Base
export { default as ClinicalMetricCard } from './base/ClinicalMetricCard.vue'
export { default as VitalSparkline } from './base/VitalSparkline.vue'
export { default as DataCompletenessRing } from './base/DataCompletenessRing.vue'
export { default as DataFreshnessBadge } from './base/DataFreshnessBadge.vue'
export { default as ChartExplanation } from './base/ChartExplanation.vue'
export { default as ClinicalEmptyState } from './base/ClinicalEmptyState.vue'
export { default as MissingDataPanel } from './base/MissingDataPanel.vue'

// Trend
export { default as ClinicalTrendChart } from './trend/ClinicalTrendChart.vue'
export { default as MultiVitalTrendChart } from './trend/MultiVitalTrendChart.vue'
export { default as ScoreTrendChart } from './trend/ScoreTrendChart.vue'
export { default as ScoreComponentChart } from './trend/ScoreComponentChart.vue'

// Risk
export { default as RiskMatrix } from './risk/RiskMatrix.vue'
export { default as RiskDistributionChart } from './risk/RiskDistributionChart.vue'
export { default as OrganRiskMap } from './risk/OrganRiskMap.vue'
export { default as BedRiskCard } from './risk/BedRiskCard.vue'
export { default as ICUBedMap } from './risk/ICUBedMap.vue'

// Timeline
export { default as ClinicalTimeline } from './timeline/ClinicalTimeline.vue'
export { default as EventSwimlane } from './timeline/EventSwimlane.vue'

// Flow
export { default as WorkflowDiagram } from './flow/WorkflowDiagram.vue'
export { default as EvidenceGraph } from './flow/EvidenceGraph.vue'
export { default as TaskStatusFlow } from './flow/TaskStatusFlow.vue'

// Alert
export { default as AlertFunnel } from './alert/AlertFunnel.vue'

// Quality
export { default as QualityControlChart } from './quality/QualityControlChart.vue'
export { default as QualityHeatmap } from './quality/QualityHeatmap.vue'

// AI
export { default as ScannerTopology } from './ai/ScannerTopology.vue'
export { default as ModelRoutingDiagram } from './ai/ModelRoutingDiagram.vue'
export { default as ServiceTopology } from './ai/ServiceTopology.vue'

// Research
export { default as CohortFlowDiagram } from './research/CohortFlowDiagram.vue'
export { default as TrialScreeningFunnel } from './research/TrialScreeningFunnel.vue'
export { default as BeforeAfterComparison } from './research/BeforeAfterComparison.vue'
```
