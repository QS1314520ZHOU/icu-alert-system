# ICU 智能预警系统（ICU Alert System）

面向重症监护病区的全栈智能预警、流程监测、AI 决策支持与病区运营平台。系统把床旁监护、检验、药物执行、护理评估、设备管理、实时预警、Analytics、数字孪生、MDT 和知识库统一到同一套后端规则引擎与前端工作台里。

这份 README 以当前代码实现为准，重点回答 5 个问题：

1. 这个项目解决什么问题。
2. 系统整体是怎么跑起来的。
3. 每个主要模块负责什么、怎么用。
4. 每个扫描器当前按什么逻辑计算和触发。
5. 页面、接口、运行方式、扩展方式分别是什么。

---

## 1. 项目定位

系统不是一个单纯的 ICU 看板，而是一套围绕 ICU 临床场景构建的综合智能预警系统，覆盖四类核心任务：

1. 实时风险识别  
   把原始监护和检验数据转换成“结论 + 严重度 + 证据 + 建议 + 上下文”。
2. 治疗过程监测  
   连续监测撤机、CRRT、抗菌药、镇静镇痛、VTE 预防、装置管理、Bundle 合规等流程。
3. 护理与病区运营  
   关注护理评估超时、护理文本风险信号、工作量预测、排班热力图、病区级风险态势。
4. AI 辅助决策  
   提供 AI 推理、相似病例、交班摘要、数字孪生、反事实模拟、多智能体协作、知识检索。

---

## 2. 总体架构

```text
SmartCare / DataCenter / Redis
│
├─ patient / bedside / deviceCap / deviceBind / drugExe
├─ VI_ICU_EXAM / VI_ICU_EXAM_ITEM / VI_ICU_report
└─ score_records / alert_records / nurse_reminders / ai_monitor_logs
                │
                ▼
         AlertEngine + Scanners + Mixins
                │
     规则预警 / 评分记录 / 聚合分析 / AI降级结果
                │
                ▼
       FastAPI Routers + WebSocket + AI Services
                │
                ▼
     Vue 前端总览 / 详情 / 大屏 / Analytics / MDT / AI Ops
```

### 2.1 运行时数据流

1. `backend/app/main.py` 启动 FastAPI。
2. `backend/app/database.py` 连接 SmartCare、DataCenter、Redis。
3. `backend/app/alert_engine/__init__.py` 初始化 `AlertEngine`，注册全部扫描器。
4. 扫描器按配置周期运行，读取患者、监护、检验、药物、评估数据。
5. 命中规则后写入 `alert_records`，评分/状态写入 `score_records`。
6. 路由层对外提供 REST API，WebSocket 推送实时事件。
7. 前端页面按业务场景消费这些接口和实时流。
8. AI 服务在可用时生成增强解释，不可用时按规则回退。

### 2.2 目录结构

- `backend/app/main.py`  
  FastAPI 主入口，负责生命周期、路由注册、静态文件挂载。
- `backend/app/alert_engine/`  
  规则引擎核心。扫描器只是调度层，真正临床逻辑大量在 mixin 中。
- `backend/app/routers/`  
  对外 API，按患者、告警、Analytics、AI、知识库、系统拆分。
- `backend/app/services/`  
  AI 服务层，含 LLM 运行时、RAG、临床推理、数字孪生、反事实、文书生成、多智能体、亚表型。
- `backend/app/utils/`  
  数据抽取、序列化、床位匹配、告警状态归一、实验室单位处理等工具。
- `frontend/src/views/`  
  页面级视图。
- `frontend/src/components/`  
  患者详情、总览、大屏等可复用业务组件。
- `backend/config.yaml`  
  业务配置中心，绝大多数阈值、扫描周期、关键词、评分权重都在这里。

---

## 3. 数据源与关键映射

### 3.1 SmartCare

- `patient`  
  患者主档、床位、科室、诊断、部分状态字段。
- `bedside`  
  床旁记录与文本型护理/事件信息。
- `deviceCap`  
  监护仪、呼吸机、CRRT 等设备的时间序列参数。
- `deviceBind`  
  设备与患者绑定关系，系统靠它把设备参数映射到患者。
- `drugExe`  
  药物执行记录，用于用药风险、抗菌药、镇静、升压药等判断。
- `alert_records`  
  所有实时预警记录。
- `score_records`  
  评分、Bundle 跟踪、撤机评估、SBT 记录、个体阈值建议等结构化结果。

### 3.2 DataCenter

- `VI_ICU_EXAM`
- `VI_ICU_EXAM_ITEM`
- `VI_ICU_report`

主要承载 LIS / 检验 / 检查信息，与 SmartCare 通过 `hisPid` 关联。

### 3.3 关键映射逻辑

- 患者关联  
  SmartCare 侧主要使用 `patient._id`；跨库检验关联主要使用 `patient.hisPid`。
- 设备关联  
  `deviceCap.deviceID -> deviceBind.deviceID -> deviceBind.pid -> patient._id`
- 血压优先级  
  有创优先于无创：`IBP > NIBP`
- 活跃患者范围  
  API 与 Analytics 多数基于 `active_patient_query()` / `admitted_patient_query()`。

---

## 4. 启动方式与运行模式

### 4.1 后端 API

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4.2 扫描 Worker

```powershell
cd backend
python run_scan_worker.py
```

或：

```powershell
cd backend
python -m app.scan_worker
```

### 4.3 前端开发

```powershell
cd frontend
npm install
npm run dev
```

### 4.4 前端构建

```powershell
cd frontend
npm run build
```

### 4.5 运行模式说明

- `inline`  
  API 进程自身直接跑扫描循环。
- `redis_queue`  
  API 进程做任务投递，Worker 进程消费队列执行扫描。

当前配置里 `task_queue.mode` 已支持 Redis 队列化，因此更适合把 API 与扫描任务拆开部署。

---

## 5. 核心后端模块说明

### 5.1 `backend/app/main.py`

职责：

- 启动 FastAPI。
- 初始化数据库、WebSocket 管理器、AlertEngine、AI 服务。
- 注册全部路由。
- 在生产构建时托管前端静态资源。
- 对静态资源缺失返回 404，避免把 JS/CSS 错误回退到 HTML。

用法：

- 开发环境直接用 `uvicorn` 启动。
- 构建后可以同时提供 API 和前端单页应用。

### 5.2 `backend/app/database.py`

职责：

- 建立 SmartCare、DataCenter、Redis 三类连接。
- 自动创建索引。
- 在 `alert_rules` 为空时写入默认生命体征规则。

逻辑要点：

- Mongo 认证失败时会尝试无认证连接兜底。
- Redis 失败为非致命错误，系统可降级运行。
- 预警、评分、AI 监控等集合都建立了常用查询索引。

### 5.3 `backend/app/runtime.py`

职责：

- 把 `db / config / ws_mgr / alert_engine / ai_handoff_service / ai_monitor / ai_rag_service` 暴露成全局运行时单例。
- 路由层通过 `runtime.xxx` 访问共享实例。

### 5.4 `backend/app/scan_worker.py`

职责：

- 作为独立进程启动 `AlertEngine(runtime_role="worker")`。
- 用于 Redis 队列模式下的扫描任务消费。

### 5.5 `backend/app/config.py`

职责：

- 读取 `.env` 中的敏感配置。
- 读取 `backend/config.yaml` 中的业务配置。
- 统一暴露 Mongo URI、Redis URL、CORS、WebSocket Token、LLM 模型选择等。

### 5.6 `backend/config.yaml`

这是项目最重要的业务配置文件，主要包含：

- 设备与参数映射
- 生命体征、呼吸机、评估量表编码
- 扫描间隔
- 告警抑制策略
- 各模块阈值、关键词、因子权重
- AI 服务参数
- 扩展场景目录
- 护理提醒配置

如果要做二次开发，优先看这里，而不是先改代码。

---

## 6. AlertEngine 逻辑说明

`backend/app/alert_engine/__init__.py` 中的 `AlertEngine` 是系统核心。它由多个 mixin 组合而成，每个 mixin 对应一类临床能力。

### 6.1 引擎层职责

- 管理扫描器注册与启停
- 控制并发数
- 负责告警抑制
- 提供统一的 `_create_alert()`、`_is_suppressed()`、数据查询辅助方法
- 承担 AI fallback、评分持久化、上下文组装

### 6.2 重要 mixin 分组

#### A. 监护与趋势

- `VitalSignsMixin`
- `TrendMixin`
- `TemporalRiskScannerMixin`
- `DiaphragmProtectionMixin`
- `VentilatorMixin`
- `RightHeartMonitorMixin`
- `HemodynamicAdvisorMixin`

主要负责设备参数读取、趋势检测、撤机与呼吸支持分析、循环状态辅助判断。

#### B. 综合征识别

- `SepsisMixin`
- `AkiMixin`
- `ArdsMixin`
- `DicMixin`
- `TbiMixin`
- `BleedingMixin`
- `CompositeDeteriorationMixin`

主要负责把离散体征、检验、治疗信息组合成临床综合征判断。

#### C. 治疗流程与安全

- `CrrtMonitorMixin`
- `DrugSafetyMixin`
- `AntibioticStewardshipMixin`
- `AntimicrobialPKMixin`
- `DoseAdjustmentMixin`
- `FluidBalanceMixin`
- `GlycemicControlMixin`
- `VteProphylaxisMixin`
- `NutritionMonitorMixin`
- `DeviceManagementMixin`
- `HaiBundleMonitorMixin`
- `LiberationBundleMixin`
- `EcashBundleMixin`
- `IcuAwMobilityMixin`
- `DischargeReadinessMixin`

#### D. 护理与运营

- `NurseReminderMixin`
- `NursingNoteAnalyzerMixin`
- `NursingWorkloadPredictorMixin`
- `CircadianProtectorMixin`
- `PalliativeTriggerMixin`

#### E. AI 与增强解释

- `AiRiskMixin`
- `AdaptiveThresholdAdvisorMixin`
- `AlertReasoningAgentMixin`
- `AlertIntelligenceMixin`
- `SimilarCaseReviewMixin`
- `ProactiveManagementEngineMixin`
- `ExtendedScenarioMixin`

---

## 7. 扫描器总览与规则说明

说明：

- 扫描器是“定时调度入口”，大量实际计算在同名或相关 mixin 中完成。
- 严重度通常使用 `warning / high / critical`。
- 告警会经过抑制：同患者同规则默认 `1800s` 内不重复触发，并限制每小时最大数量。

### 7.1 生命体征、趋势与呼吸循环类

| 扫描器 | 主要逻辑 | 当前规则计算方式 |
| --- | --- | --- |
| `VitalSignsScanner` | 基础生命体征阈值扫描 | 从 `alert_rules` 读取生命体征规则；对每个参数同时看绝对阈值、个体基线偏离、多参数确认、数据质量过滤。额外识别新发房颤/房扑、心动过缓合并收缩压下降、QTc 延长。新发房颤要求不规则节律持续 `>=300s`、段内 HR 峰值 `>100` 且近 `6h` 无既往 AF/AFL；心动过缓联动要求 HR `<50` 且 `30min` 内 SBP 下降 `>20`；QTc `>500ms` 触发，高于 `550ms` 提升为 critical。 |
| `TrendScanner` | 生命体征趋势恶化 | 固定监测 HR、SpO2、RR、MAP、体温。对每个参数做三层识别：急性位移、亚急性斜率、周期性波动。急性窗口默认 `30min`，亚急性窗口 `6h`，周期窗口 `2h`。示例：SpO2 急降 `>=4` 可直接给到 critical；MAP 下降、HR/RR 上升按 high 处理；体温亚急性升高通常为 warning。 |
| `TemporalRiskScanner` | 时序风险预测 | 根据近 `12h` 时间网格序列、人口中位数补齐和多个 horizon（`4/12/24h`）预测器官风险，输出未来恶化概率，更多用于趋势提前量和 AI 风险层。 |
| `VentilatorWeaningScanner` | 撤机与 SBT 评估 | 以“闸门条件 + 加权风险分”判断。闸门含 `FiO2 > 0.4`、`PEEP > 8`、仍需升压药、`MAP < 65`、`RASS` 不在目标范围。风险因子按 `config.yaml -> weaning_assistant.factor_weights` 累加，例如 `P/F < 200`、`RSBI >= 80`、液体超负荷、既往 SBT 失败、血流动力学不稳。总分默认 `4/7/9` 对应 `warning/high/critical`。 |
| `DiaphragmProtectionScanner` | 膈肌保护 | 关注呼吸机支持天数、Edi、Pdi、P0.1、RR、镇静深度、驱动压、压力摆动。目的是避免过度辅助和过度自主用力两端风险。 |
| `HemodynamicAdvisorScanner` | 血流动力学建议 | 结合 MAP、乳酸、液体反应性、升压药暴露、灌注指标给出建议型结论，属于决策支持类扫描。 |
| `RightHeartMonitorScanner` | 右心负荷/衰竭趋势 | 以 `24h` CVP 变化、`72h` BNP 变化、PEEP 水平等组合计数；CVP 上升阈值默认 `3`，BNP 比值阈值 `2.0`，达到最少因子数后给出右心负荷风险。 |
| `CardiacArrestRiskScanner` | 心脏骤停前风险 | 按因子权重累计分数：交替性心动过缓/过速、极度缓慢心率、新发宽 QRS、高钾、低钾、低钙、乳酸升高伴 MAP 下降、PEA 模式等。默认 `4/6/8` 分对应 `warning/high/critical`。 |
| `AdaptiveThresholdsScanner` | 个体化阈值建议 | 不是直接出床旁告警，而是根据近 `48h` 数据分布生成个体化阈值建议。要求最少数据点、受总体漂移上限约束，并识别升压药/镇静药背景。输出 `pending_review -> approved/rejected` 的审核流。 |
| `AiRiskScanner` | AI 风险评分 | 通过 AI/模型生成风险预测和解释，用于风险展望、AI 页签和辅助分析，不作为唯一临床依据。 |

### 7.2 检验、综合征与恶化识别类

| 扫描器 | 主要逻辑 | 当前规则计算方式 |
| --- | --- | --- |
| `LabResultsScanner` | 固定检验阈值扫描 | 内置硬编码阈值：高钾 `>5.5 / >6.5`、低钾 `<3.5 / <2.5`、高钠 `>160`、低钠 `<120`、iCa `<0.8`、PO4 `<1.0`、Mg `<1.0`、乳酸 `>2 / >4`、血糖 `<3 / >20`、Hb `<70 / <60`、PLT `<50 / <20`、PCT `>2 / >10`、INR `>3`、肌钙蛋白、BNP 等。每个组只触发优先级最高的一条；同时会结合 `AKI`、`地高辛`、电解质纠正方案调整严重度。 |
| `SepsisScanner` | 脓毒症与 1h Bundle 跟踪 | 先算 qSOFA，`qSOFA >= 2` 触发 warning；再算 SOFA，如果 `SOFA Δ >= 2` 且存在基线或 qSOFA 已提示，则触发 high；若使用升压药且乳酸 `>=2` 且 MAP 缺失或 `<65`，触发脓毒性休克 critical。与此同时会启动或刷新脓毒症 1h Bundle tracker。 |
| `AkiScanner` | AKI 分期 | 调用 KDIGO 计算，综合肌酐和尿量，按分期 `1/2/3` 映射到 `warning/high/critical`。 |
| `ArdsScanner` | ARDS 风险识别 | 主要基于 `P/F` 比值、PEEP、氧合恶化和呼吸机背景识别，符合 Berlin 思路。 |
| `DicScanner` | DIC 风险识别 | 以 ISTH 评分体系为核心，综合血小板、凝血、D-dimer、纤维蛋白原等。 |
| `BleedingScanner` | 出血风险 | 关注 Hb 快速下降、凝血恶化、出血文本提示、术后引流、消化道线索等，输出 GI/活动性出血风险。 |
| `TbiScanner` | 神经重症/TBI | 结合 GCS、瞳孔、ICP、CPP、神经恶化文本、镇静背景判断颅脑风险。 |
| `CompositeDeteriorationScanner` | 多器官恶化聚合 | 在 `4h` 窗口内把已有告警映射到呼吸、循环、肾脏、凝血、肝脏、神经等器官域。默认至少 `3` 个器官域活跃且源告警达到要求时，触发多器官恶化趋势预警。 |
| `PeRiskScanner` | PE 风险识别 | 基于急性低氧、D-dimer、心动过速、术后/制动等模式识别，并结合配置里的 Wells 权重。 |
| `PostopComplicationsScanner` | 术后并发症 | 监测 Hb 下降、引流增多、肠胀气/无排气、胃残余量、体温反跳等。默认 Hb 下降阈值 `20 g/L`，`6h` 引流量阈值 `200ml`，每小时 `100ml`，肠梗阻样风险 `72h` 无排气。 |
| `ImmunocompromisedMonitorScanner` | 免疫抑制风险 | 识别免疫抑制药、化疗/移植背景、中性粒细胞绝对值低、发热、低血压、心动过速等，提示中性粒细胞减少性败血风险。 |
| `MicrobiologyScanner` | 微生物与耐药风险 | 识别培养、药敏、MDRO、万古霉素谷浓度、碳青霉烯类暴露等，用于耐药提示、覆盖不足和后续抗菌药优化。 |
| `ImagingReportAnalyzerScanner` | 影像报告文本分析 | 读取近 `96h` 影像报告，抽取感染灶、积液、肺部进展、导管位置、血栓/梗阻等文本信号，并转成结构化告警或解释补充。 |
| `ExtendedScenariosScanner` | 扩展场景引擎 | 根据 `config.yaml -> extended_scenarios` 注册的目录，对罕见危重、移植术后、器械并发症、复杂休克等场景做命中。它更像场景规则容器，输出归类到 `extended_scenarios`。 |

### 7.3 CRRT、药物与治疗监测类

| 扫描器 | 主要逻辑 | 当前规则计算方式 |
| --- | --- | --- |
| `CrrtScanner` | CRRT 连续监测 | TMP `>250` 或上升斜率 `>10` 提示滤器凝堵风险；滤器运行时长 `>=24h` warning、`>=48h` high；枸橼酸抗凝时 iCa 不在 `0.9~1.3` 触发；`Ca_total / iCa > 2.5` 提示枸橼酸蓄积；肝素抗凝时 ACT 不在 `180~220` 提示；按 `effluent_rate / 体重 < 20 ml/kg/h` 且持续 `6h` 触发剂量不足；电解质超过 `6h` 未复查给提醒。 |
| `DrugSafetyScanner` | 用药安全 | 关注阿片累计剂量、长期用药后停药间隔、呼吸抑制、SpO2 下降、QT 风险、器官功能与药物组合等。 |
| `AntibioticStewardshipScanner` | 抗菌药管理 | 监测经验性抗菌药超时、培养是否补齐、药敏回报后是否去-escalation、PCT 停药评估、疗程过长、万古霉素/氨基糖苷 TDM 是否完成。 |
| `ArcRiskScanner` | ARC 风险 | 依据年龄、CrCl、肌酐偏低、尿量偏高、创伤/神外背景识别增强肾清除风险，为药代不足做前置提示。 |
| `AntimicrobialPkScanner` | 抗菌药 PopPK 估算 | 针对万古霉素、美罗培南、哌拉西林他唑巴坦等做 ICU 简化一室模型估算。根据基础 CL/Vd、体重、CrCl、ARC、CRRT、低白蛋白修正后推算暴露不足或过量风险。 |
| `VancoTdmClosedLoopScanner` | 万古霉素闭环 TDM | 结合谷浓度、AUC/MIC 目标区间 `400~600`、Bayes/简化参数更新，形成“检测结果 -> 暴露判断 -> 调整建议”的闭环。 |
| `DoseAdjustmentScanner` | 剂量调整 | 按肾功能、CRRT、肝功能、体重等背景，对需要肾剂量或特殊调整的药物给出提醒。 |
| `FluidBalanceScanner` | 液体平衡 | 计算 `6/12/24h` 净出入量与液体超负荷比例。默认 `%FO > 5%` warning，`>10%` high；同时看快速输液后 MAP/乳酸是否改善，以及是否进入 deresuscitation 阶段。 |
| `GlycemicControlScanner` | 血糖控制 | 低血糖阈值 `3.9`，危急低血糖 `2.2`；高血糖阈值 `10`；连续高值次数、单位时间下降速度、胰岛素后复测间隔、血糖变异系数 `CV > 36%` 都会参与判断。 |
| `NutritionMonitorScanner` | 营养支持 | ICU `48h` 后仍未起始营养、热量覆盖率低于目标、持续喂养不足、喂养不耐受、再喂养综合征风险、电解质下降、低 BMI、低白蛋白都可能触发。 |
| `DischargeReadinessScanner` | ICU 转出准备 | 依据近 `12h` 高等级告警、近 `24h` SOFA、近 `6h` 尿量、监测密度是否下降、文本里是否已有转出候选等综合判断适不适合离开 ICU。 |
| `ProactiveManagementScanner` | 主动管理建议 | 从近 `6h` 轨迹、近 `24h` 检验与药物、重点实验室项目构造管理建议，如果触发概率高于配置阈值，就把“下一步可能要做什么”持久化出来。 |

### 7.4 护理、装置与流程闭环类

| 扫描器 | 主要逻辑 | 当前规则计算方式 |
| --- | --- | --- |
| `DeliriumRiskScanner` | 谵妄风险 | 因子加权模型。常见因子包括年龄 `>65`、苯二氮卓、急诊入 ICU、机械通气、代谢性酸中毒、吗啡、BUN 升高、深镇静、低 GCS。默认 `4/7/10` 分对应 `warning/high/critical`。 |
| `CircadianProtectorScanner` | 昼夜节律保护 | 识别夜间 `22:00~06:00` 的护理/操作过多、夜间 RASS 波动大、夜班 warning 聚集，提示睡眠和节律破坏风险。 |
| `DeviceManagementScanner` | 装置管理 | 跟踪 CVC、Foley、ETT 等装置的在位天数、必要性、感染与损伤风险，并为设备热力图提供结构化摘要。 |
| `HaiBundleScanner` | HAI Bundle | 检查中心静脉、尿管、机械通气相关 bundle 是否完整，例如床头抬高、口腔护理、导管必要性复审、血培养等。 |
| `VteProphylaxisScanner` | VTE 预防 | 结合 Padua / Caprini 因子、卧床时间、恶性肿瘤、既往 VTE、手术、感染、激素等计算风险，再核对药物预防和机械预防是否落实。 |
| `PalliativeTriggerScanner` | 姑息触发 | ICU 住院天数长、神经功能差、高龄、多病共存、负担因子累积时触发沟通建议。默认 ICU 天数阈值 `14d`、年龄阈值 `80`、GCS 阈值 `8`。 |
| `LiberationBundleScanner` | A-F Liberation Bundle | 计算 A-F 各灯态，形成 `green/yellow/red` 状态，用于患者总览、大屏和 Bundle 总览。 |
| `EcashBundleScanner` | eCASH 闭环 | 围绕 Analgesia、Sedation、Delirium 三个灯态，识别过镇静、SAT 提醒、苯二氮卓暴露、疼痛评估超时、谵妄风险等。 |
| `IcuAwMobilityScanner` | ICU-AW 与早期活动 | 使用因子加权法：机械通气天数、镇静暴露、多类镇静药、SOFA、活动缺失、败血症、糖代谢波动、激素等。默认 `4/7/10` 分对应 `warning/high/critical`，并附带活动机会窗判断。 |
| `NurseRemindersScanner` | 护理超时提醒 | 不是疾病风险，而是流程提醒。检查 GCS、RASS、疼痛、CPOT、BPS、谵妄、Braden、CAM-ICU、翻身、早期活动是否超过规定间隔。 |
| `NursingNoteAnalyzerScanner` | 护理文本分析 | 读取近 `12h` 护理记录，抽取风险信号、执行障碍、护理任务延迟、特殊事件，并给相似病例和 AI 页签提供文本证据。 |
| `NursingWorkloadScanner` | 护理工作量预测 | 以基础分、机械通气、CRRT、升压药、近期告警、护理上下文计算护理负荷，再映射到 NAS 风格指数，用于 `summary / dept_rows / patient_rows / heatmap / timeline`。 |
| `AlertReasoningScanner` | 告警解释增强 | 不是新病种扫描器，而是把近 `30min` 活跃告警组合交给规则/AI 解释器，补充“为什么发生、最可能关联什么、建议先做什么”。 |

---

## 8. 核心评分、计算口径与中文说明

这一节把项目里最容易被问到的“怎么算”统一写清楚。

### 8.1 告警严重度

项目里常见严重度顺序为：

- `none = 0`
- `normal = 1`
- `warning = 2`
- `high = 3`
- `critical = 4`

用途：

- 患者卡风险叠加
- 大屏最高级别排序
- Analytics 聚合
- 抢救期高风险筛选

### 8.2 告警抑制

默认配置：

- 同患者同规则 `1800s` 内不重复触发
- 每患者每小时最多 `10` 条

目的：

- 避免生命体征抖动造成刷屏
- 把注意力留给真正持续、可行动的风险

### 8.3 个体基线偏离

个体阈值不是简单固定阈值，而是：

1. 读取近 `12h~48h` 基线分布。
2. 结合 `z-score`、相对偏移、绝对最小偏移量判断。
3. 受总体安全边界限制，不能把阈值漂移到脱离医学常识。
4. 考虑升压药、镇静药背景。
5. 最终只给“建议阈值”，需要审核后才生效。

### 8.4 血气与酸碱分析

系统当前支持把血气做成结构化解释，不只是单个数值超界。核心包括：

- 主酸碱紊乱识别
- Winter 代偿判断
- 校正阴离子间隙
- Delta-Delta
- 乳酸校正 AG
- 呼吸性酸碱急慢性区分
- Stewart SID 分析

这类结果会进入 AI 摘要、检验分析和患者详情页。

### 8.5 脓毒症 1h Bundle

数据来源：

- `score_records.score_type in {sepsis_bundle_tracker, sepsis_antibiotic_bundle}`
- `bundle_type in {sepsis_hour1_bundle, sepsis_1h_antibiotic}`

状态派生：

- `met`
- `met_late`
- `pending`
- `overdue_1h`
- `overdue_3h`

统计字段：

- `total_cases`
- `compliant_1h_cases`
- `compliance_rate`
- `overdue_1h_cases`
- `overdue_3h_cases`
- `met_late_cases`
- `pending_active_cases`

### 8.6 撤机评估

SBT 记录解析规则：

- 文本含 `通过 / 成功 / 耐受 / passed / success` 视为 `passed`
- 文本含 `失败 / 不通过 / 终止 / failed / abort / intolerant` 视为 `failed`
- `1 / true` 视为通过，`0 / false` 视为失败
- 能取到 `RR / VTe / minute ventilation` 时会计算 `RSBI`

撤机风险评分逻辑：

- 以 `factor_weights` 加权累积分
- 以 `FiO2/PEEP/MAP/血管活性药/RASS` 作为就绪闸门
- 默认 `4/7/9` 对应 `warning/high/critical`

撤机 Analytics 统计：

- 最近一次月内 `weaning_assessment` 计入已评估患者
- `risk_level in {high, critical}` 计入高风险
- 呼吸机解绑计入已拔管患者
- `post_extubation_failure_risk` 计入再插管风险患者

### 8.7 CRRT

CRRT 相关明确口径：

- TMP 趋势高或快速上升提示凝堵
- 枸橼酸抗凝看 iCa 与 `Ca_total / iCa`
- 肝素抗凝看 ACT
- 计算剂量用 `effluent_rate / 体重`
- 电解质超时未复查给流程提醒

### 8.8 抗菌药与药代

已在配置中明确的重点：

- ARC 风险会影响清除率估计
- PopPK 用于实时预警，不替代正式 TDM 建模
- 万古霉素目标 AUC/MIC 为 `400~600`
- PCT 停药评估以疗程起始后峰值为基线，而不是任意两点比较

### 8.9 护理工作量

当前接口：

- `GET /api/analytics/nursing-workload`

时间窗口：

- `24h`
- `7d`
- `14d`
- `30d`

工作量构成：

- 基础分
- 机械通气分
- CRRT 分
- 升压药分
- 近期告警负荷
- 护理文本和任务上下文
- NAS 映射参数

返回：

- `summary`
- `dept_rows`
- `patient_rows`
- `heatmap`
- `timeline`

### 8.10 相似病例

候选池筛选：

- 只取已离科病例
- 排除当前患者自身
- 年龄带宽默认 `±10 岁`
- SOFA 带宽默认 `±2`
- 当前患者有呼吸机或 CRRT 时，候选也要具备相同支持背景

综合评分公式：

- `embedding_similarity * 0.4`
- `token_similarity * 0.1`
- `age_score * 0.15`
- `sofa_score * 0.25`
- `support_score * 0.1`

降级策略：

- AI 解释失败时回退为启发式总结
- 全链路失败时返回基础画像和 `degraded = true`

### 8.11 亚表型分析

当前实现不是历史全集重聚类，而是：

- 使用原型中心
- 计算距离
- softmax 得到软分群概率

因此能支持实时接口级使用，而不是只能离线跑。

---

## 9. 路由与页面使用说明

### 9.1 前端页面

#### `/`

患者总览页，适合护士站/医生工作台快速筛查。

主要内容：

- 患者卡
- 实时告警
- Bundle 灯态
- 床位和科室筛选
- 风险分层

#### `/patient/:id`

单患者详情页，是最完整的临床工作台。

包含：

- 基础资料
- 生命体征趋势
- 检验
- 药物
- 护理与评估
- 告警详情
- 相似病例
- 数字孪生
- AI 分析
- eCASH
- 活动等级
- PE 风险
- SBT 与撤机时间线

#### `/bigscreen`

护士站大屏。

主要用于：

- 快速看全病区高风险患者
- 查看实时告警流
- 看床位分布和总量指标

#### `/analytics`

历史预警与运营分析页。

当前已覆盖：

- alerts
- sepsis
- weaning
- nursing
- scenarios

#### `/mdt`

MDT 多智能体协作页。

适合：

- 讨论复杂病例
- 查看数字孪生和 AI 建议
- 形成会诊结论草稿

#### `/ai-ops`

AI 运营中心。

用于：

- 观察 AI 模块调用成功率
- 查看延迟、用量、错误、模块表现
- 追踪质量反馈

### 9.2 后端路由模块

#### `backend/app/routers/patients.py`

负责：

- 科室列表
- 在院患者列表
- 单患者详情
- Bundle 状态
- 个体阈值建议与审核
- eCASH
- 脓毒症 1h Bundle 单患者状态
- 撤机状态
- SBT 记录
- 撤机时间线
- 相似病例
- 转出准备

#### `backend/app/routers/patient_data.py`

负责：

- 生命体征
- 检验
- 趋势
- 药物
- 评估
- 患者详情页所需的基础数据载荷

#### `backend/app/routers/alerts.py`

负责：

- 最近告警列表
- 告警确认
- 告警生命周期分析
- 告警时间序列统计

#### `backend/app/routers/analytics.py`

负责：

- Bundle 总览
- 装置热力图
- 护理工作量
- 扩展场景覆盖率
- 脓毒症 1h Bundle 合规
- 撤机月度汇总
- 告警频率、热力图、科室/床位排名

#### `backend/app/routers/ai_modules/ops.py`

负责：

- 交班摘要
- AI 反馈
- AI 反馈汇总
- AI 监控汇总
- AI 规则推荐
- AI 检验摘要

#### `backend/app/routers/ai_modules/reasoning.py`

负责：

- 风险预测
- 主动管理建议
- 临床推理
- 因果分析
- 干预效果查询
- 护理文本信号

#### `backend/app/routers/ai_modules/digital_twin.py`

负责：

- 数字孪生视图
- What-if 模拟
- 亚表型
- 多智能体评估
- 系统面板

#### `backend/app/routers/ai_modules/workspace.py`

负责：

- 文书生成
- MDT 工作区读取/保存
- 会诊决策草稿

#### `backend/app/routers/knowledge.py`

负责：

- 知识库文档列表
- 文档状态
- 文档与 chunk 明细
- 热重载

---

## 10. AI 服务模块说明

### 10.1 `AiHandoffService`

作用：

- 生成交班摘要
- 组合患者近期告警、检验、趋势、护理上下文

### 10.2 `AiMonitor`

作用：

- 统计各 AI 模块的成功率、延迟、用量
- 输出运营视图和异常告警

### 10.3 `RagService`

作用：

- 从 `backend/knowledge_base` 加载指南与共识
- 支持本地 TF-IDF 或 embedding 检索
- 为临床推理、文书生成、问答补充循证依据

### 10.4 `ClinicalReasoningAgent`

作用：

- 基于患者上下文 + 检索证据生成结构化临床推理
- 给出问题列表、证据链、建议动作

### 10.5 `PatientDigitalTwinService`

作用：

- 以结构化面板整合感染、呼吸、循环、趋势等状态
- 给数字孪生页提供统一数据模型

### 10.6 `SemiMechanisticCounterfactualModel`

作用：

- 接收干预假设
- 模拟指标随时间的变化方向
- 用于 What-if 场景

### 10.7 `CohortSubphenotypeProfiler`

作用：

- 计算患者在不同临床亚表型中的软归属概率
- 用于病例分层和相似病例解释

### 10.8 `ICUMultiAgentOrchestrator`

作用：

- 把复杂病例拆成多个专科视角评估
- 适合 MDT 页面

### 10.9 `ClinicalDocumentGenerator`

作用：

- 生成交班、会诊、病情摘要等文书草稿

### 10.10 `llm_runtime.py`

作用：

- 统一管理模型候选、超时、并发、fallback model、断路器

### 10.11 `ClinicalKnowledgeGraph`

作用：

- 以原因节点、证据节点方式组织临床知识
- 支持推理结果的结构化展示

---

## 11. 工具层模块说明

### 11.1 `app/utils/patient_data.py`

负责：

- 检验拉取
- 床旁评分提取
- 设备 ID 解析
- 参数序列查询
- 药物频次美化

### 11.2 `app/utils/alerting.py`

负责：

- window 解析
- month 归一
- 脓毒症 bundle 状态派生
- 撤机和 SBT 记录标准化
- 聚合统计投影

### 11.3 `app/utils/clinical.py`

负责：

- 阈值条件判断
- 参数抽取
- 趋势检测

### 11.4 `app/utils/labs.py`

负责：

- 检验项目别名匹配
- 单位归一
- 常见检验值转换

### 11.5 `app/utils/serialization.py`

负责：

- 把 Mongo 文档安全转换成可 JSON 输出结构
- 保证 `None` 保留为 `null`

### 11.6 `app/utils/websocket_auth.py`

负责：

- WebSocket token 校验
- 来源校验
- 角色解析

---

## 12. 主要接口清单

### 12.1 系统与基础

- `GET /health`
- `GET /api/departments`
- `GET /api/patients`
- `GET /api/patients/{patient_id}`

### 12.2 患者基础数据

- `GET /api/patients/{patient_id}/vitals`
- `GET /api/patients/{patient_id}/labs`
- `GET /api/patients/{patient_id}/vitals/trend`
- `GET /api/patients/{patient_id}/drugs`
- `GET /api/patients/{patient_id}/assessments`
- `GET /api/patients/{patient_id}/alerts`
- `GET /api/patients/{patient_id}/bedcard`

### 12.3 患者流程与监测

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
- `GET /api/patients/{patient_id}/weaning-timeline`

### 12.4 告警与运营分析

- `GET /api/alerts/recent`
- `POST /api/alerts/{alert_id}/acknowledge`
- `GET /api/alerts/lifecycle/analytics`
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

### 12.5 AI

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

### 12.6 知识库

- `GET /api/knowledge/chunks/{chunk_id}`
- `GET /api/knowledge/documents`
- `GET /api/knowledge/status`
- `GET /api/knowledge/documents/{doc_id}`
- `POST /api/knowledge/reload`

---

## 13. 推荐验收路径

### 13.1 页面

1. 打开 `/`，检查患者总览、实时告警、Bundle 灯态、风险分层。
2. 打开 `/patient/:id`，检查趋势、检验、告警、相似病例、数字孪生、AI 页签。
3. 打开 `/bigscreen`，检查床位卡、实时告警流、右侧图卡。
4. 打开 `/analytics?section=nursing`，检查护理工作量摘要、热力图、时间线。
5. 打开 `/mdt`，检查 MDT 视图与数字孪生联动。

### 13.2 接口

建议至少抽查：

- `/health`
- `/api/alerts/recent`
- `/api/device-risk/heatmap`
- `/api/analytics/nursing-workload?window=24h`
- `/api/analytics/sepsis-bundle/compliance`
- `/api/analytics/weaning-summary`
- `/api/ai/nursing-note-signals/{patient_id}`
- `/api/ai/what-if/{patient_id}`
- `/api/ai/subphenotype/{patient_id}`

---

## 14. 扩展与维护建议

### 14.1 新增扫描器时

需要同步更新：

- `backend/app/alert_engine/scanner_registry.py`
- `backend/config.yaml` 中的扫描间隔、阈值、关键词
- 本 README 第 7 节扫描器说明

### 14.2 新增统计接口时

需要同步更新：

- 本 README 的“核心口径”部分
- 对应页面说明
- 降级策略说明

### 14.3 新增 AI 能力时

建议明确写清：

- 输入来源
- 输出字段
- 是否写入 `score_records`
- 是否可降级
- 降级时返回什么结构

### 14.4 推荐的开发顺序

1. 先补 `config.yaml`
2. 再写 mixin / scanner 逻辑
3. 再补 router
4. 再补前端视图
5. 最后更新 README

---

## 15. 一句话总结

这是一个把 ICU 实时预警、治疗流程监测、护理闭环、AI 决策支持、数字孪生和病区运营整合到一起的全栈系统；当前代码不只具备“告警能力”，还已经形成了“患者总览 + 单患者工作台 + 大屏 + Analytics + MDT + AI Ops”的完整产品骨架。
