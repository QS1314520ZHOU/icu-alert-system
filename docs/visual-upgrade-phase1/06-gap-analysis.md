# 差距清单

## 说明

本清单明确区分每项改造所需的数据和资源来源，避免在没有可靠数据的情况下强行实现图表。

---

## 一、前端已有数据，可直接实现

以下数据已在前端组件或composables中获取，可直接用于图表渲染。

| 序号 | 数据 | 当前位置 | 可视化机会 | 优先级 |
|------|------|----------|-----------|--------|
| 1 | 患者列表（含风险等级） | `useNurseHome.ts` | 床位风险地图、风险分布图 | P0 |
| 2 | 告警列表 | 多个composable | 告警漏斗、告警趋势 | P0 |
| 3 | 患者基本信息 | `usePatientDetail.ts` | 患者信息条 | P0 |
| 4 | 生命体征数据 | `usePatientDetail.ts` | 多指标趋势图 | P0 |
| 5 | 风险评分 | `usePatientDetail.ts` | 评分趋势图 | P0 |
| 6 | 器官严重度 | `useOrganSeverity.ts` | 器官风险图 | P0 |
| 7 | 护理任务 | `useNurseHome.ts` | 任务完成率 | P0 |
| 8 | MDT会诊数据 | `useMdtWorkspace.ts` | 多学科意见图、共识矩阵 | P1 |
| 9 | 营养数据 | `useNutritionDashboard.ts` | 热量/蛋白趋势 | P1 |
| 10 | 呼吸治疗数据 | `useRespiratoryDashboard.ts` | 通气参数趋势 | P1 |
| 11 | 临床工作流数据 | `useClinicalWorkflow.ts` | 任务状态流转 | P1 |
| 12 | 科研队列数据 | `useResearchWorkbench.ts` | 筛选漏斗 | P3 |
| 13 | 临床试验数据 | `useClinicalTrial.ts` | 筛选漏斗 | P3 |

---

## 二、后端已有数据，需要聚合接口

以下数据后端已有原始数据，但需要新增聚合接口以支持图表渲染。

| 序号 | 所需聚合接口 | 原始数据来源 | 说明 | 优先级 |
|------|-------------|-------------|------|--------|
| 1 | `GET /api/dashboard/doctor-summary` | patients, alerts, tasks | 医生首页聚合指标+风险矩阵 | P0 |
| 2 | `GET /api/dashboard/nurse-summary` | patients, alerts, tasks, beds | 护士首页聚合指标+床位数据 | P0 |
| 3 | `GET /api/patients/{id}/clinical-timeline` | events, orders, alerts, notes | 24h临床事件时间线 | P0 |
| 4 | `GET /api/patients/{id}/organ-risk` | vitals, labs, scores | 器官风险聚合 | P0 |
| 5 | `GET /api/patients/{id}/score-trends` | scores | SOFA/NEWS2/qSOFA趋势 | P0 |
| 6 | `GET /api/patients/{id}/treatment-response` | orders, vitals, labs | 治疗前后对比数据 | P0 |
| 7 | `GET /api/patients/{id}/vital-trends` | vitals | 生命体征趋势（含正常范围） | P0 |
| 8 | `GET /api/alerts/funnel` | alerts | 告警漏斗统计 | P0 |
| 9 | `GET /api/alerts/trends` | alerts | 告警时间趋势 | P1 |
| 10 | `GET /api/quality/overview` | quality_metrics | 质控指标总览 | P2 |
| 11 | `GET /api/quality/indicator/{id}/drilldown` | quality_metrics, patients | 质控指标四级下钻 | P2 |
| 12 | `GET /api/rules/health` | rule_executions | 规则健康指标 | P2 |
| 13 | `GET /api/rules/topology` | rules, scanners | 规则依赖拓扑 | P2 |
| 14 | `GET /api/ai/operations` | ai_logs | AI运营指标 | P2 |
| 15 | `GET /api/research/cohort-summary` | research_cohorts | 队列摘要 | P3 |
| 16 | `GET /api/trials/screening-funnel` | trials, patients | 试验筛选漏斗 | P3 |

### 接口返回格式统一规范

```typescript
interface ApiResponse<T> {
  data: T
  timeRange: { start: string; end: string }
  unit: string
  source: string
  updatedAt: string
  isPartial: boolean
  missingFields: string[]
  version: string
  timezone: string
}

// 评分接口额外字段
interface ScoreResponse extends ApiResponse<ScoreData> {
  scoreName: string
  scoreVersion: string
  totalScore: number
  components: ScoreComponent[]
  missingPolicy: string
  calculatedAt: string
}
```

---

## 三、规则项目已有能力，可复用

以下能力在 `D:\critical-care-alert-platform` 中已实现，可直接复用或参考。

| 序号 | 能力 | 位置 | 复用方式 | 优先级 |
|------|------|------|---------|--------|
| 1 | Classic SOFA 评分计算 | `ccalert` | API调用或前端复用公式 | P0 |
| 2 | SOFA-2 评分计算 | `ccalert` | API调用或前端复用公式 | P0 |
| 3 | NEWS2 评分计算 | `ccalert` | API调用或前端复用公式 | P0 |
| 4 | qSOFA 评分计算 | `ccalert` | API调用或前端复用公式 | P0 |
| 5 | MEWS 评分计算 | `ccalert` | API调用或前端复用公式 | P1 |
| 6 | GCS 评分计算 | `ccalert` | API调用或前端复用公式 | P0 |
| 7 | AKI 分期判断 | `ccalert` | API调用 | P1 |
| 8 | 规则引擎执行 | `ccalert` | 直接调用 | P0 |
| 9 | 告警分类逻辑 | `ccalert` | 直接复用 | P0 |

---

## 四、当前没有可靠数据，暂时不能实现

以下可视化需求因缺乏可靠数据源，建议暂不实现或仅展示框架。

| 序号 | 需求 | 缺失原因 | 建议 |
|------|------|---------|------|
| 1 | 呼吸机波形/环图 | 无高频呼吸机原始数据源 | 明确显示"暂无波形数据"，不模拟 |
| 2 | 实时监护数据流 | 需要WebSocket或高频轮询 | 先用30s轮询，后续升级WebSocket |
| 3 | 高频生命体征（秒级） | 监护仪数据可能未入库 | 确认数据采集频率后再实现 |
| 4 | 精确的用药时间标记 | 用药记录时间精度不足 | 先用医嘱时间，后续对接药房系统 |
| 5 | 精确的液体出入量 | 出入量记录可能不完整 | 显示数据完整度，缺失时不画图 |
| 6 | Kaplan-Meier/ROC等统计图 | 需要后端统计分析能力 | 先实现基础分布图 |
| 7 | 3D人体器官定位图 | 需要3D模型资源 | 先用2D SVG人体图 |
| 8 | 护理人力热力图 | 缺乏排班数据 | 后续对接排班系统 |

---

## 五、需要临床专家确认

以下设计决策需要临床专家审核确认。

| 序号 | 问题 | 影响范围 | 状态 |
|------|------|---------|------|
| 1 | 器官风险阈值定义 | 器官风险图颜色映射 | ⏳ 待确认 |
| 2 | 风险矩阵坐标轴定义 | 医生首页风险矩阵 | ⏳ 待确认 |
| 3 | 临床事件分类体系 | 事件时间线/河流图 | ⏳ 待确认 |
| 4 | 评分版本选择（SOFA vs SOFA-2） | 评分趋势图 | ⏳ 待确认 |
| 5 | 正常范围参考值 | 趋势图正常范围带 | ⏳ 待确认 |
| 6 | AI摘要免责措辞 | AI问诊/查房页面 | ⏳ 待确认 |
| 7 | 告警严重度分级标准 | 告警漏斗/列表 | ⏳ 待确认 |
| 8 | 质控指标目标值 | 质控控制图 | ⏳ 待确认 |

---

## 六、需要UI资源或本地SVG

| 序号 | 资源 | 说明 | 获取方式 | 优先级 |
|------|------|------|---------|--------|
| 1 | 人体正面SVG | 器官风险图基础 | 自建或购买授权 | P0 |
| 2 | 人体背面SVG | 器官风险图（可选） | 自建或购买授权 | P1 |
| 3 | 器官图标集 | 循环/呼吸/神经等 | Ant Design Icons 或自建 | P0 |
| 4 | 设备图标集 | 呼吸机/CVC/导尿管等 | 自建 | P1 |
| 5 | 流程节点图标 | 完成/进行中/失败等 | Ant Design Icons | P0 |

### SVG资源约束
- 必须本地打包，禁止运行时从公网加载
- 必须有明确的许可证
- 支持通过CSS变量控制颜色
- 支持点击交互

---

## 总结

| 类别 | 数量 | 可立即开始 | 需要后端配合 | 需要外部资源 |
|------|------|-----------|-------------|-------------|
| 前端已有数据 | 13 | 13 | 0 | 0 |
| 需要聚合接口 | 16 | 0 | 16 | 0 |
| 规则项目可复用 | 9 | 9 | 0 | 0 |
| 暂不能实现 | 8 | 0 | 0 | 8 |
| 需临床确认 | 8 | 0 | 0 | 0 |
| 需UI资源 | 5 | 0 | 0 | 5 |

### 第一批可立即开始的工作

1. 建立设计Token（颜色、字体、间距、图表主题）
2. 建立基础可视化组件库（MetricCard、TrendChart、Timeline、FlowDiagram等）
3. 使用mock数据开发患者详情页的器官风险图、多指标趋势图、评分趋势图
4. 使用mock数据开发医生首页的风险矩阵、告警漏斗
5. 使用mock数据开发智能查房的事件河流图、器官热力图

### 需要后端优先配合的接口

按优先级排序：
1. `/api/dashboard/doctor-summary`
2. `/api/dashboard/nurse-summary`
3. `/api/patients/{id}/clinical-timeline`
4. `/api/patients/{id}/organ-risk`
5. `/api/patients/{id}/vital-trends`
6. `/api/patients/{id}/score-trends`
7. `/api/alerts/funnel`
