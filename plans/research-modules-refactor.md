# 科研模块重构计划

## 当前状态

| 文件 | 行数 | 核心问题 |
|------|------|----------|
| ResearchWorkbench.vue | ~1900 | 巨型组件，7种分析+变量筛选+会话+AI+平台状态全部内联 |
| ResearchExport.vue | ~1000 | 所有表单+预览+历史同时展示，无步骤流程 |
| AcademicResearchDashboard.vue | ~856 | 项目+数据质量+课题推荐+OMOP导出全在一个页面 |
| ClinicalTrialScreening.vue | ~780 | 试验列表+候选患者+匹配详情全在一个页面 |

## 设计原则

- 使用已有的 design-system 组件（PageHeader, MetricStrip, SectionHeader, ActionBar, EmptyState）
- 使用已有的 design-system.css 变量（字号、间距、颜色、圆角）
- 采用 composable 模式提取业务逻辑（参考 useNurseHome）
- 使用 Ant Design Steps 组件实现步骤式流程
- 低频/复杂内容放入抽屉
- 不修改后端 API

## 改造方案

### 1. ResearchWorkbench.vue（科研分析工作台）

**核心问题**：页面承载过多业务职责，左侧导航有12个标签。

**改造策略**：拆分为步骤式流程 + 独立子组件。

**步骤流程**：
1. 数据准备（队列选择、变量筛选、分组设置）
2. 数据质量检查（变量完整性摘要）
3. 选择分析方法（基线特征/生存/回归/ROC/亚组/趋势/相关性）
4. 预览结果
5. 导出

**拆分文件**：
- `composables/useResearchWorkbench.ts` — 所有状态、API调用、计算属性
- `components/research/StepDataPrep.vue` — 步骤1：数据准备
- `components/research/StepDataQuality.vue` — 步骤2：数据质量
- `components/research/StepAnalysis.vue` — 步骤3：分析方法选择与执行
- `components/research/StepResults.vue` — 步骤4：结果预览
- `components/research/StepExport.vue` — 步骤5：导出
- `components/research/VariableCatalog.vue` — 变量目录（从StepDataPrep中提取）
- `components/research/AnalysisPanel.vue` — 分析结果面板（复用table1/survival等）
- `views/ResearchWorkbench.vue` — 主文件，只负责步骤编排

**保留功能**：队列选择、变量筛选、7种分析、AI对话配置、会话管理、平台状态、导出中心。平台状态和会话管理移入顶部工具栏或抽屉。

### 2. ResearchExport.vue（科研数据导出）

**核心问题**：所有配置和预览同时展示。

**改造策略**：5步流程。

**步骤流程**：
1. 选择数据范围（队列、科室、患者范围、时间范围）
2. 选择字段（数据类型、导出模式）
3. 脱敏检查（脱敏选项、数据字典）
4. 预览（命中量、样本预览、警告）
5. 提交导出任务

**拆分文件**：
- `composables/useResearchExport.ts` — 状态、API、计算属性
- `views/ResearchExport.vue` — 重写为步骤式布局

**保留功能**：队列选择、科室锁定、数据类型选择、脱敏选项、预览、任务跟踪、历史记录。历史记录移入底部折叠区域或抽屉。

### 3. AcademicResearchDashboard.vue（学术科研支撑）

**核心问题**：项目看板+数据质量+课题推荐+OMOP导出全在一个页面。

**改造策略**：使用 Tab 划分主区域 + 步骤式。

**布局**：
- 顶部：PageHeader + MetricStrip（项目数、课题数、患者数、数据问题数）
- Tab 1：项目管理（项目列表 + 新建）
- Tab 2：数据质量（缺失率、异常值、治理建议）
- Tab 3：AI课题推荐（课题列表 + 转为项目）
- 底部：OMOP导出（折叠面板）

**拆分文件**：
- `composables/useAcademicResearch.ts` — 状态、API
- `views/AcademicResearchDashboard.vue` — 重写

### 4. ClinicalTrialScreening.vue（临床试验筛选）

**核心问题**：试验列表+候选患者+匹配详情全在一个页面。

**改造策略**：5步流程。

**步骤流程**：
1. 选择试验（试验列表、新建/编辑/启用招募）
2. 查看候选患者（只显示：床号姓名、匹配度、主要条件、缺失数据数、排除风险、确认状态）
3. 查看匹配依据（抽屉）
4. 医生确认（状态流转）
5. 跟踪状态

**拆分文件**：
- `composables/useClinicalTrial.ts` — 状态、API
- `views/ClinicalTrialScreening.vue` — 重写为步骤式

**保留功能**：试验CRUD、AI解析标准、筛选、候选状态流转、演示模板。完整入排条件进入抽屉。

## 新增文件清单

```
frontend/src/composables/useResearchWorkbench.ts
frontend/src/composables/useResearchExport.ts
frontend/src/composables/useAcademicResearch.ts
frontend/src/composables/useClinicalTrial.ts
frontend/src/components/research/StepDataPrep.vue
frontend/src/components/research/StepDataQuality.vue
frontend/src/components/research/StepAnalysis.vue
frontend/src/components/research/StepResults.vue
frontend/src/components/research/StepExport.vue
frontend/src/components/research/VariableCatalog.vue
frontend/src/components/research/AnalysisPanel.vue
```

## 修改文件清单

```
frontend/src/views/ResearchWorkbench.vue （重写）
frontend/src/views/ResearchExport.vue （重写）
frontend/src/views/AcademicResearchDashboard.vue （重写）
frontend/src/views/ClinicalTrialScreening.vue （重写）
```

## 执行顺序

1. 创建 composables（提取状态和API逻辑）
2. 创建 research 子组件（步骤式UI）
3. 重写4个主视图文件
4. TypeScript 类型检查
5. Vite 生产构建
6. 修复编译错误
7. 检查布局（1440/1280/1024/390px）
