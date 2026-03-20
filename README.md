# ICU 智能预警系统（ICU Alert System）

面向重症监护病区的全栈智能预警与临床决策支持平台。系统将床旁监护、检验、药物执行、护理评估、设备管理、AI 推理和病区可视化统一到一套后端规则引擎与前端工作台中。

本文档按当前代码实现整理，目标是把“系统功能、计算口径、页面入口、接口能力、运行方式”写清楚，便于交付、联调和二次开发。

---

## 1. 项目定位

系统解决的是 ICU 场景下三类核心问题：

1. 实时风险识别
   从“单参数越界报警”升级为“结论 + 证据 + 建议 + 上下文快照”。
2. 治疗过程监测
   把撤机、CRRT、抗菌药、镇静镇痛、Bundle 合规、装置管理等流程性问题做成连续监测。
3. 病区级运营与 AI 辅助
   提供患者总览、大屏、Analytics、MDT、多智能体、相似病例回顾、What-if 干预模拟等能力。

---

## 2. 总体架构

```text
监护/床旁数据(deviceCap, bedside)
检验数据(VI_ICU_EXAM_ITEM)
药物执行(drugExe)
护理评分/护理记录(score, score_records, nursing notes)
                │
                ▼
         AlertEngine / Scanners
                │
        alert_records / cache / analytics
                │
   REST API + WebSocket + AI services + Frontend
```

### 2.1 主要目录

- `backend/app/main.py`
  FastAPI 主应用，统一注册路由与运行时依赖。
- `backend/app/alert_engine/`
  规则引擎、扫描器、综合征识别、护理分析、个性化阈值、相似病例分析等核心逻辑。
- `backend/app/routers/`
  对外 API 路由，包括患者、告警、Analytics、AI、知识库、系统健康检查。
- `backend/app/services/`
  LLM、RAG、多智能体、反事实模型、亚表型分析、文书生成等服务层。
- `backend/app/utils/`
  序列化、患者数据查询、临床辅助函数、WebSocket 鉴权等通用工具。
- `frontend/src/views/`
  前端页面：患者总览、患者详情、大屏、Analytics、MDT、AI Ops。
- `frontend/src/components/`
  业务组件，含大屏卡片、患者详情页子标签、图表模块。

---

## 3. 前端页面与入口

### 3.1 页面路由

- `/`
  患者总览工作台（Patient Overview）
- `/patient/:id`
  单患者详情页（趋势、检验、告警、相似病例、数字孪生、AI、eCASH、活动等级等）
- `/bigscreen`
  护士站监控大屏
- `/analytics`
  运营分析页，当前支持 `alerts / sepsis / weaning / nursing / scenarios`
- `/mdt`
  MDT 临床协作工作站
- `/ai-ops`
  AI 运行态与质量运营页

### 3.2 当前主要 UI 能力

- 患者总览：风险卡、床位总览、实时预警、Bundle 状态、hover 摘要
- 患者详情：Vitals、Labs、Drugs、Assessments、Alerts、SBT 时间线、相似病例、数字孪生、AI、eCASH、Mobility、PE 风险
- 大屏：左侧实时预警流、中间床位监控、右侧统计图卡
- Analytics：预警频率、规则热力图、科室/床位排名、Sepsis 1h Bundle、脱机/再插管、扩展场景覆盖、护理工作量预测与排班热力图
- MDT：多智能体工作台、协作会诊视图
- AI Ops：AI 调用质量、模块映射、运营跳转

---

## 4. 后端能力总表

### 4.1 已注册扫描器

当前扫描器注册表位于 `backend/app/alert_engine/scanner_registry.py`，按代码实际注册顺序包含：

- VitalSignsScanner
- LabResultsScanner
- SepsisScanner
- AkiScanner
- TrendScanner
- CrrtScanner
- ArdsScanner
- DicScanner
- TbiScanner
- BleedingScanner
- TemporalRiskScanner
- VentilatorWeaningScanner
- DiaphragmProtectionScanner
- DrugSafetyScanner
- AntibioticStewardshipScanner
- ArcRiskScanner
- AntimicrobialPkScanner
- VancoTdmClosedLoopScanner
- ImmunocompromisedMonitorScanner
- DeliriumRiskScanner
- CircadianProtectorScanner
- DeviceManagementScanner
- HaiBundleScanner
- FluidBalanceScanner
- GlycemicControlScanner
- VteProphylaxisScanner
- PeRiskScanner
- PalliativeTriggerScanner
- PostopComplicationsScanner
- NutritionMonitorScanner
- CompositeDeteriorationScanner
- CardiacArrestRiskScanner
- LiberationBundleScanner
- EcashBundleScanner
- IcuAwMobilityScanner
- MicrobiologyScanner
- HemodynamicAdvisorScanner
- RightHeartMonitorScanner
- DoseAdjustmentScanner
- DischargeReadinessScanner
- AdaptiveThresholdsScanner
- ProactiveManagementScanner
- ExtendedScenariosScanner
- AiRiskScanner
- AlertReasoningScanner
- NurseRemindersScanner
- NursingNoteAnalyzerScanner
- NursingWorkloadScanner

### 4.2 能力分组

#### A. 生命体征与时间序列

- HR / RR / SpO2 / 血压 / 体温阈值预警
- 趋势恶化识别
- 时序风险扫描
- 个体基线偏离提醒
- 数据质量过滤
- 呼吸机参数、撤机、膈肌保护、右心监测、血流动力学建议

#### B. 检验与综合征识别

- 血气/酸碱解读
- 脓毒症、ARDS、AKI、DIC、出血、TBI
- Composite deterioration 多器官恶化趋势
- PE 风险识别
- 术后并发症、营养不足、免疫抑制患者风险

#### C. 治疗与流程监测

- CRRT 运行监测
- 抗菌药与药代动力学（含 ARC / TDM / 万古霉素闭环）
- 镇静、阿片、QT、激素、肾肝功能相关用药风险
- VTE 预防、装置管理、HAI Bundle
- eCASH、A-F Liberation Bundle、ICU-AW 早期活动
- 转出准备评估

#### D. 护理与病区运营

- 护理评估超时提醒
- 护理文本风险信号提取
- 护理工作量预测与排班热力图
- 扩展场景覆盖率分析

#### E. AI 与高级辅助

- AI 风险预测
- AI 规则推荐
- AI 检验摘要 / 交班摘要
- AI 临床推理 / 因果分析
- What-if 干预模拟
- 亚表型分群（Subphenotype）
- 多智能体工作台
- 文书生成
- 相似病例复盘
- 个性化报警阈值建议
- AI Monitor / 调用质量统计
- RAG / 知识库检索

---

## 5. 核心计算规则与口径

本节只写“代码中当前已经体现的主要计算口径”，不写空泛医学介绍。

### 5.1 通用告警处理规则

#### 5.1.1 数据入口

系统主要使用以下数据源：

- `patient`
  患者主档、床位、科室、诊断等
- `deviceCap`
  床旁监护时间序列
- `drugExe`
  药物执行记录
- `VI_ICU_EXAM_ITEM`
  检验结果
- `score / score_records`
  量表与护理评估
- `alert_records`
  扫描器产出的预警记录

#### 5.1.2 有效患者范围

Analytics 与患者总览默认围绕“active patient”查询，依赖 `active_patient_query()` 生成筛选条件。

#### 5.1.3 序列化规则

- 统一通过 `serialize_doc()` 输出 Mongo 文档
- 对 `None` 的处理已修正为保留 `null`，不再错误转成 `{}`
- 路由返回涉及嵌套对象时使用 `_serialize_nullable()` 或 `serialize_doc()` 处理

#### 5.1.4 严重度口径

系统内部常见严重度顺序：

- `none = 0`
- `normal = 1`
- `warning = 2`
- `high = 3`
- `critical = 4`

该顺序用于：

- 床位总览最高严重度覆盖
- 实时预警流排序
- 抢救期过滤
- 患者卡 alert level 叠加

### 5.2 生命体征规则

#### 5.2.1 规则结构

生命体征不是单纯“固定阈值超限”，而是多层判断：

- 绝对阈值
- 趋势变化
- 个体基线偏离
- 数据质量过滤
- 多参数联合确认

#### 5.2.2 个体基线建议

个体化阈值推荐由 `adaptive_threshold_advisor.py` 负责，核心思路是：

- 读取患者近 `24h~72h` 生命体征分布
- 结合诊断背景、血管活性药/镇静药状态
- 生成“医生审核版”阈值建议
- 状态流转为 `pending_review -> approved / rejected`
- 默认不自动生效，必须审核后才作为个体阈值参考

### 5.3 血气与酸碱分析规则

当前 README 要求写明的血气规则包括：

- 主酸碱紊乱识别
- Winter 代偿判断
- 校正阴离子间隙（corrected AG）
- Delta-Delta
- 乳酸校正 AG
- 呼吸性酸碱失衡急慢性区分
- Stewart SID 分析

换句话说，系统不只是看 `pH / PaCO2 / HCO3-` 是否超界，而是做成套酸碱解释。

### 5.4 综合征识别规则

#### 5.4.1 Sepsis-3

脓毒症相关模块包含：

- qSOFA
- SOFA 变化量（`SOFA Δ`）
- 脓毒性休克识别

前端和 Analytics 里还提供：

- Sepsis 1h Bundle 合规率
- Sepsis 相关患者筛查
- 抢救期高风险联动

#### 5.4.2 ARDS

ARDS 识别口径为：

- `P/F` 比值
- `PEEP` 联动

#### 5.4.3 AKI

AKI 识别口径为：

- KDIGO
- 同时参考 `Cr` 与 `尿量`

#### 5.4.4 DIC

DIC 使用：

- ISTH 评分体系

#### 5.4.5 PE 与 VTE

- PE：模式识别 + Wells 评分
- VTE：预防是否落实、机械预防兜底检测、床旁/医嘱/文本联合判断

### 5.5 呼吸与撤机规则

系统已覆盖以下呼吸支持流程：

- 呼吸机撤机评估
- SBT 结构化记录时间线
- 拔管后再插管高风险识别
- 膈肌保护与呼吸力学监测

#### 5.5.1 再插管风险卡

前端常见字段包括：

- `rr`
- `spo2`
- `hours_since_extubation`
- `severity`
- `has_alert`

大屏和患者卡显示为：

- 当前判断
- 主要依据
- 处置建议

### 5.6 CRRT 规则

CRRT 相关监测口径包括：

- TMP 趋势
- ACT / 枸橼酸抗凝监测
- 剂量不足提醒
- 滤器时长
- `Ca_total / iCa` 比值
- 电解质复查提醒

### 5.7 抗菌药与药代规则

相关模块包括：

- 抗菌药优化（Antibiotic stewardship）
- 药敏覆盖不足
- MDRO 监测
- ARC 风险
- PK / TDM
- 万古霉素 TDM 闭环

当前文档中已明确的口径：

- PCT 停药评估以“抗生素疗程起始后的峰值”作为基线，而不是任意单点比较

### 5.8 护理与流程规则

#### 5.8.1 护理评估超时提醒

至少覆盖：

- GCS
- RASS
- 疼痛评估
- CAM-ICU
- Braden

#### 5.8.2 eCASH 闭环

实时灯态包含：

- Analgesia
- Sedation
- Delirium

并衍生：

- SAT 提醒
- 苯二氮卓用药警示

#### 5.8.3 Device management

主要跟踪：

- CVC
- Foley
- ETT

统计维度：

- 在位日
- 必要性评估
- 风险等级

### 5.9 护理工作量预测与排班热力图规则

后端接口：`GET /api/analytics/nursing-workload`

#### 5.9.1 时间窗口

当前支持：

- `24h`
- `7d`
- `14d`
- `30d`

并且在路由层使用：

- `window_to_hours(window, default=24)`
- 小时数被限制在 `8 <= hours <= 24 * 30`

也就是：

- 最短不会低于 8 小时
- 最长不会超过 30 天

#### 5.9.2 返回内容

该接口当前返回：

- `summary`
- `dept_rows`
- `patient_rows`
- `heatmap`
- `timeline`

因此前端“护理资源”视图可以同时展示：

- 总体摘要
- 科室维度工作量
- 患者维度工作量
- 排班热力图
- 时间轴趋势

### 5.10 装置热力图计算口径

后端接口：`GET /api/device-risk/heatmap`

#### 5.10.1 数据来源

每个患者通过 `runtime.alert_engine._device_management_summary(patient)` 获取装置摘要。

#### 5.10.2 风险分值映射

代码中当前写死映射为：

- `low -> 1`
- `medium -> 2`
- `high -> 3`

最终形成字段：

- `patient_id`
- `bed`
- `patient_name`
- `device_type`
- `line_days`
- `risk`
- `risk_score`

### 5.11 Bundle 概览统计口径

后端接口：`GET /api/bundle/overview`

对每个 active patient 调用：

- `runtime.alert_engine.get_liberation_bundle_status(patient)`

然后把 `status.lights` 中每个灯态累加到：

- `green`
- `yellow`
- `red`

返回结构为：

- `patient_count`
- `counts.green`
- `counts.yellow`
- `counts.red`

### 5.12 扩展场景覆盖率统计口径

后端接口：`GET /api/analytics/scenario-coverage`

#### 5.12.1 场景目录来源

- 从 `config.yaml -> extended_scenarios` 读取场景目录
- 用 `group / scenario / title` 组织 catalog

#### 5.12.2 触发统计来源

- 读取 `alert_records`
- 过滤 `category = extended_scenarios`
- 按 `window` 统计命中情况

#### 5.12.3 输出口径

- `summary.coverage_ratio = triggered_catalog_scenarios / total_catalog_scenarios`
- `group_rows`
  按场景组统计 catalog 数、触发数、覆盖率
- `heatmap`
  取 TopN 高频场景，做 group × scenario 热力矩阵
- `top_scenarios`
  返回场景级 `alert_count / patient_count / critical / high / warning`

### 5.13 亚表型（Subphenotype）规则

后端接口：`GET /api/ai/subphenotype/{patient_id}`

当前实现已经从“实时历史队列聚类”优化为“原型中心快速软聚类”，核心特点：

- 使用特征到原型中心的距离
- 用 softmax 形成软分群概率
- 当前实测从约 `125s` 降到约 `1.4s`

这意味着它更适合作为临床页面实时接口，不再是离线分析专用。

### 5.14 What-if / 反事实模拟规则

后端接口：`POST /api/ai/what-if/{patient_id}`

当前依赖：

- `SemiMechanisticCounterfactualModel`

定位是：

- 输入干预假设
- 输出干预后的趋势/结局方向变化
- 给数字孪生页和 MDT 提供可视化模拟能力

### 5.15 相似病例规则

后端接口：`GET /api/patients/{patient_id}/similar-case-outcomes`

增强版 Similar Case Review 目前是：

- 诊断 embedding
- 余弦相似度匹配
- Top-K 相似病例结局统计
- ICU 天数 / 呼吸机天数 / 转归信息
- 可叠加 LLM 做结构化总结

---

## 6. AI 能力说明

### 6.1 直接可见的 AI 功能

- 交班摘要（handoff summary）
- 规则推荐（rule recommendations）
- 风险预测（risk forecast）
- 主动管理建议（proactive management）
- 临床推理（clinical reasoning）
- 因果分析（causal analysis）
- 护理文本信号（nursing note signals）
- What-if 干预模拟
- 亚表型分析
- 多智能体协作
- 系统面板 / 文书生成 / MDT 工作区
- 检验摘要

### 6.2 AI 运行韧性

代码和现有文档里已体现：

- fallback model
- circuit breaker
- 调用 hash / latency / success 监控
- token usage 统计
- 前端降级提示
- Similar Case / PatientDetail / BigScreen 超时降级

---

## 7. 对外 API 清单

以下为当前主要接口路径。

### 7.1 系统与基础

- `GET /health`
- `GET /api/departments`
- `GET /api/patients`
- `GET /api/patients/{patient_id}`

### 7.2 患者数据

- `GET /api/patients/{patient_id}/vitals`
- `GET /api/patients/{patient_id}/labs`
- `GET /api/patients/{patient_id}/vitals/trend`
- `GET /api/patients/{patient_id}/drugs`
- `GET /api/patients/{patient_id}/assessments`
- `GET /api/patients/{patient_id}/alerts`
- `GET /api/patients/{patient_id}/bedcard`

### 7.3 患者流程与阈值

- `POST /api/patients/bundle-status`
- `GET /api/patients/{patient_id}/discharge-readiness`
- `GET /api/patients/{patient_id}/similar-case-outcomes`
- `GET /api/patients/{patient_id}/personalized-thresholds`
- `GET /api/patients/{patient_id}/personalized-thresholds/history`
- `POST /api/patients/{patient_id}/personalized-thresholds/{record_id}/review`
- `GET /api/personalized-thresholds/review-center`
- `GET /api/patients/{patient_id}/ecash-status`
- `GET /api/patients/{patient_id}/sepsis-bundle-status`
- `GET /api/patients/{patient_id}/weaning-status`
- `GET /api/patients/{patient_id}/sbt-records`

### 7.4 告警与 Analytics

- `GET /api/alerts/recent`
- `GET /api/alerts/stats`
- `GET /api/bundle/overview`
- `GET /api/device-risk/heatmap`
- `GET /api/analytics/nursing-workload`
- `GET /api/analytics/scenario-coverage`
- `GET /api/analytics/sepsis-bundle/compliance`
- `GET /api/analytics/weaning-summary`
- `GET /api/alerts/analytics/frequency`
- `GET /api/alerts/analytics/heatmap`
- `GET /api/alerts/analytics/rankings`

### 7.5 AI 接口

- `GET /api/patients/{patient_id}/handoff-summary`
- `POST /api/ai/feedback`
- `GET /api/ai/feedback/summary`
- `GET /api/ai/monitor/summary`
- `GET /api/ai/rule-recommendations/{patient_id}`
- `GET /api/ai/risk-forecast/{patient_id}`
- `GET /api/ai/proactive-management/{patient_id}`
- `POST /api/ai/proactive-management/{patient_id}/interventions/{intervention_id}/feedback`
- `GET /api/ai/clinical-reasoning/{patient_id}`
- `POST /api/ai/causal-analysis/{patient_id}`
- `GET /api/ai/intervention-effects`
- `GET /api/ai/nursing-note-signals/{patient_id}`
- `POST /api/ai/what-if/{patient_id}`
- `GET /api/ai/subphenotype/{patient_id}`
- `GET /api/ai/multi-agent/{patient_id}`
- `GET /api/ai/system-panels/{patient_id}`
- `POST /api/ai/documents/{patient_id}`
- `GET /api/ai/mdt-workspace/{patient_id}`
- `POST /api/ai/mdt-workspace/{patient_id}`
- `GET /api/ai/lab-summary/{patient_id}`

### 7.6 知识库接口

- `GET /api/knowledge/chunks/{chunk_id}`
- `GET /api/knowledge/documents`
- `GET /api/knowledge/status`
- `GET /api/knowledge/documents/{doc_id}`
- `POST /api/knowledge/reload`

---

## 8. 运行与开发

### 8.1 后端启动

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 8.2 扫描 Worker 启动

```powershell
cd backend
python run_scan_worker.py
```

或：

```powershell
cd backend
python -m app.scan_worker
```

### 8.3 前端启动

```powershell
cd frontend
npm install
npm run dev
```

### 8.4 前端构建

```powershell
cd frontend
npm run build
```

---

## 9. 推荐验收路径

### 9.1 页面验收

1. 打开 `/`
   检查患者总览、告警卡、床位筛选、风险层级。
2. 打开 `/patient/:id`
   检查趋势、检验、相似病例、数字孪生、AI 标签页。
3. 打开 `/bigscreen`
   检查实时预警、床位卡、统计图、图表 tooltip 与 legend。
4. 打开 `/analytics?section=nursing`
   检查护理工作量预测与排班热力图。
5. 打开 `/mdt`
   检查 MDT 协作页、数字孪生联动。

### 9.2 接口验收

至少建议抽查：

- `/health`
- `/api/alerts/recent`
- `/api/device-risk/heatmap`
- `/api/analytics/nursing-workload?window=24h`
- `/api/ai/nursing-note-signals/{patient_id}`
- `/api/ai/what-if/{patient_id}`
- `/api/ai/subphenotype/{patient_id}`

---

## 10. 最近已落地的重要实现

### 10.1 护理与病区运营

- 新增护理文本分析能力
- 新增护理工作量预测与排班热力图
- Analytics 已支持 `24h / 7d / 14d / 30d` 窗口

### 10.2 运行时修复

- `/api/analytics/nursing-workload` 返回序列化问题已修复
- `serialize_doc(None)` 不再错误返回 `{}`
- 亚表型接口已从重计算优化为原型中心快速软聚类

### 10.3 大屏与前端

- 护士站大屏已完成中文化与重排
- 右侧统计卡、左侧实时预警、中间床位卡的视觉语言已统一
- 大屏图表 tooltip / legend / 语义色已统一到整页风格

---

## 11. 维护建议

如果后续继续扩展，建议同步维护以下文档项：

- 新增 scanner 时，把它补到“已注册扫描器”列表
- 新增 Analytics 指标时，把“计算口径”补到第 5 节
- 新增 AI 接口时，把路由补到第 7 节
- 若某项规则存在“审核后生效”或“前端降级”逻辑，必须在 README 明写

---

## 12. 一句话总结

这不是一个单纯的“ICU 看板”，而是一套围绕 ICU 抢救、治疗过程、护理闭环、AI 辅助和病区运营搭建的综合智能预警系统；当前代码已经同时覆盖了床旁、病区、Analytics、MDT、数字孪生和 AI 工作流。
