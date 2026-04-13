# ICU Alert System - 扫描器与计算口径详解

本文件详细记录了 ICU 智能预警系统中所有扫描器的触发逻辑、计算公式以及严重度定义。

---

## 1. 扫描器总览与规则说明

说明：

- 扫描器是“定时调度入口”，大量实际计算在同名或相关 mixin 中完成。
- 严重度通常使用 `warning / high / critical`。
- 告警会经过抑制：同患者同规则默认 `1800s` 内不重复触发，并限制每小时最大数量。

### 1.1 生命体征、趋势与呼吸循环类

| 扫描器 | 主要逻辑 | 当前规则计算方式 |
| --- | --- | --- |
| `VitalSignsScanner` | 基础生命体征阈值扫描 | 从 `alert_rules` 读取生命体征规则；对每个参数同时看绝对阈值、个体基线偏离、多参数确认、数据质量过滤。额外识别新发房颤/房扑、心动过缓合并收缩压下降、QTc 延长。新发房颤要求不规则节律持续 `>=300s`、段内 HR 峰值 `>100` 且近 `6h` 无既往 AF/AFL；心动过缓联动要求 HR `<50` 且 `30min` 内 SBP 下降 `>20`；QTc `>500ms` 触发，高于 `550ms` 提升为 critical。 |
| `TrendScanner` | 生命体征趋势恶化 | 固定监测 HR、SpO2、RR、MAP、体温。对每个参数做三层识别：急性位移、亚急性斜率、周期性波动。急性窗口默认 `30min`，亚急性窗口 `6h`，周期窗口 `2h`。示例：SpO2 急降 `>=4` 可直接给到 critical；MAP 下降、HR/RR 上升按 high 处理；体温亚急性升高通常为 warning。 |
| `TemporalRiskScanner` | 时序风险预测 | 根据近 `12h` 时间网格序列、人口中位数补齐和多个 horizon（`4/12/24h`）预测器官风险，输出未来恶化概率，更多用于趋势提前量和 AI 风险层。 |
| `VentilatorWeaningScanner` | 撤机与 SBT 评估 | 以“闸门条件 + 加权风险分”判断。闸门含 `FiO2 > 0.4`、`PEEP > 8`、仍需升压药、`MAP < 65`、`RASS` 不在目标范围。风险因子按 `config.yaml -> weaning_assistant.factor_weights` 累加，例如 `P/F < 200`、`RSBI >= 80`、液体超负荷、既往 SBT 失败、血流动力学不稳。总分默认 `4/7/9` 对应 `warning/high/critical`。 |
| `VentilatorAsynchronyScanner` | 呼吸机不同步识别 | 每 `30min` 读取呼吸机模式、设定/实测参数、`RASS`、`P0.1/Edi` 与可选波形衍生信号，识别 `无效触发 / 双触发 / 反向触发 / 流量饥饿 / 提前终止 / 延迟终止`。按不同步事件数估算 `AI (Asynchrony Index)`，默认 `AI >= 10%` 至少 high，`AI >= 30%` 直接 critical；双触发同时结合 `VTe / PBW > 8 mL/kg`、ARDS 与撤机评估结果强化肺保护建议。 |
| `PronePositionMonitorScanner` | 俯卧位治疗监测 | 基于 `P/F < 150 + FiO₂ >= 0.6 + PEEP >= 5` 或近期 ARDS 告警筛出俯卧位候选者，并追踪最近 `24h` 俯卧位累计时长、当前是否处于俯卧位以及并发症线索（压疮、面部水肿、管路脱出等）。 |
| `DiaphragmProtectionScanner` | 膈肌保护 | 关注呼吸机支持天数、Edi、Pdi、P0.1、RR、镇静深度、驱动压、压力摆动。目的是避免过度辅助和过度自主用力两端风险。 |
| `HemodynamicAdvisorScanner` | 血流动力学建议 | 结合 MAP、乳酸、液体反应性、升压药暴露、灌注指标给出建议型结论，属于决策支持类扫描。 |
| `BetaBlockerAdvisorScanner` | β受体阻滞剂辅助决策 | 面向“脓毒症 + 持续心动过速 + 心肌损伤 + 相对稳定血流动力学”场景。结合 `HR>95` 持续 `>=2h`、肌钙蛋白/BNP、MAP 与去甲肾上腺素趋势识别候选患者，并主动筛查支气管痉挛、房室传导阻滞、近期 HR<60、钙拮抗剂等禁忌证。满足全部条件时输出短效 β 阻滞剂建议与起始剂量提示。 |
| `RightHeartMonitorScanner` | 右心负荷/衰竭趋势 | 以 `24h` CVP 变化、`72h` BNP 变化、PEEP 水平等组合计数；CVP 上升阈值默认 `3`，BNP 比值阈值 `2.0`，达到最少因子数后给出右心负荷风险。 |
| `CardiacArrestRiskScanner` | 心脏骤停前风险 | 按因子权重累计分数：交替性心动过缓/过速、极度缓慢心率、新发宽 QRS、高钾、低钾、低钙、乳酸升高伴 MAP 下降、PEA 模式等。默认 `4/6/8` 分对应 `warning/high/critical`。 |
| `AdaptiveThresholdsScanner` | 个体化阈值建议 | 不是直接出床旁告警，而是根据近 `48h` 数据分布生成个体化阈值建议。要求最少数据点、受总体漂移上限约束，并识别升压药/镇静药背景。输出 `pending_review -> approved/rejected` 的审核流。 |
| `AiRiskScanner` | AI 风险评分 | 通过 AI/模型生成风险预测和解释，用于风险展望、AI 页签和辅助分析，不作为唯一临床依据。 |

### 1.2 检验、综合征与恶化识别类

| 扫描器 | 主要逻辑 | 当前规则计算方式 |
| --- | --- | --- |
| `LabResultsScanner` | 固定检验阈值扫描 | 内置硬编码阈值：高钾 `>5.5 / >6.5`、低钾 `<3.5 / <2.5`、高钠 `>160`、低钠 `<120`、iCa `<0.8`、PO4 `<1.0`、Mg `<1.0`、乳酸 `>2 / >4`、血糖 `<3 / >20`、Hb `<70 / <60`、PLT `<50 / <20`、PCT `>2 / >10`、INR `>3`、肌钙蛋白、BNP 等。每个组只触发优先级最高的一条；同时会结合 `AKI`、`地高辛`、电解质纠正方案调整严重度。 |
| `SepsisScanner` | 脓毒症与 1h Bundle 跟踪 | 先算 qSOFA，`qSOFA >= 2` 触发 warning；再算 SOFA，如果 `SOFA Δ >= 2` 且存在基线或 qSOFA 已提示，则触发 high；若使用升压药且乳酸 `>=2` 且 MAP 缺失或 `<65`，触发脓毒性休克 critical。与此同时会启动或刷新脓毒症 1h Bundle tracker。 |
| `SepsisSubphenotypeScanner` | 脓毒症亚表型分型 | 面向已识别脓毒症患者，提取炎症、免疫抑制、凝血、器官功能、血流动力学与体温模式 6 个复合轴，使用 `Prototype Centroids + softmax` 输出 `α高炎症 / β免疫抑制 / γ高凝 / δ混合` 亚型及归属概率。结果持久化为 `sepsis_subphenotype_profile` 并同步到 `patient.current_profile.sepsis_subphenotype`。 |
| `AkiScanner` | AKI 分期 | 调用 KDIGO 计算，综合肌酐和尿量，按分期 `1/2/3` 映射到 `warning/high/critical`。 |
| `ArdsScanner` | ARDS 风险识别 | 主要基于 `P/F` 比值、PEEP、氧合恶化和呼吸机背景识别，符合 Berlin 思路。 |
| `DicScanner` | DIC 风险识别 | 以 ISTH 评分体系为核心，综合血小板、凝血、D-dimer、纤维蛋白原等。 |
| `FibrinolysisMonitorScanner` | 纤溶功能监测 | 在 DIC / 出血背景上继续区分 `高纤溶 / 纤溶关闭` 两类状态。优先读取 TEG/ROTEM 风格 `LY30 / Maximum Lysis` 指标；缺失时退化为 `D-dimer + Fib + PLT + INR/PT + 出血/DIC` 的纤溶表型近似识别。 |
| `BleedingScanner` | 出血风险 | 关注 Hb 快速下降、凝血恶化、出血文本提示、术后引流、消化道线索等，输出 GI/活动性出血风险。 |
| `TbiScanner` | 神经重症/TBI | 结合 GCS、瞳孔、ICP、CPP、神经恶化文本、镇静背景判断颅脑风险。 |
| `CompositeDeteriorationScanner` | 多器官恶化聚合 | 在 `4h` 窗口内把已有告警映射到呼吸、循环、肾脏、凝血、肝脏、神经等器官域。默认至少 `3` 个器官域活跃且源告警达到要求时，触发多器官恶化趋势预警。 |
| `PeRiskScanner` | PE 风险识别 | 基于急性低氧、D-dimer、心动过速、术后/制动等模式识别，并结合配置里的 Wells 权重。 |
| `PostopComplicationsScanner` | 术后并发症 | 监测 Hb 下降、引流增多、肠胀气/无排气、胃残余量、体温反跳等。默认 Hb 下降阈值 `20 g/L`，`6h` 引流量阈值 `200ml`，每小时 `100ml`，肠梗阻样风险 `72h` 无排气。 |
| `ImmunocompromisedMonitorScanner` | 免疫抑制风险 | 识别免疫抑制药、化疗/移植背景、中性粒细胞绝对值低、发热、低血压、心动过速等，提示中性粒细胞减少性败血风险。 |
| `MicrobiologyScanner` | 微生物与耐药风险 | 识别培养、药敏、MDRO、万古霉素谷浓度、碳青霉烯类暴露等，用于耐药提示、覆盖不足和后续抗菌药优化。 |
| `ImagingReportAnalyzerScanner` | 影像报告文本分析 | 读取近 `96h` 影像报告，抽取感染灶、积液、肺部进展、导管位置、血栓/梗阻等文本信号，并转成结构化告警或解释补充。 |
| `ExtendedScenariosScanner` | 扩展场景引擎 | 根据 `config.yaml -> extended_scenarios` 注册的目录，对罕见危重、移植术后、器械并发症、复杂休克等场景做命中。它更像场景规则容器，输出归类到 `extended_scenarios`。 |

### 1.3 CRRT、药物与治疗监测类

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
| `MetabolicPhaseDetectorScanner` | 代谢阶段检测 | 依据乳酸、血糖变异、CRP、SOFA、血管活性药、前白蛋白、活动情况和营养供给，将患者划分为 `急性分解期 / 稳定过渡期 / 合成代谢期`。同时把实际热卡/蛋白与阶段目标比对：`Ebb` 期过喂、`Anabolic` 期低喂都会触发高优先级营养时机提醒。 |
| `DischargeReadinessScanner` | ICU 转出准备 | 依据近 `12h` 高等级告警、近 `24h` SOFA、近 `6h` 尿量、监测密度是否下降、文本里是否已有转出候选等综合判断适不适合离开 ICU。 |
| `ProactiveManagementScanner` | 主动管理建议 | 从近 `6h` 轨迹、近 `24h` 检验与药物、重点实验室项目构造管理建议，如果触发概率高于配置阈值，就把“下一步可能要做什么”持久化出来。 |

### 1.4 护理、装置与流程闭环类

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
| `PicsRiskScanner` | PICS 风险预警 | 综合 `身体功能障碍 / 认知障碍 / 心理障碍` 三个维度，整合 ICU-AW、谵妄、深镇静、长期机械通气、焦虑/睡眠障碍护理文本和转出候选信号，输出 ICU 转出前的康复与随访风险提醒。 |
| `NurseRemindersScanner` | 护理超时提醒 | 不是疾病风险，而是流程提醒。检查 GCS、RASS、疼痛、CPOT、BPS、谵妄、Braden、CAM-ICU、翻身、早期活动是否超过规定间隔。 |
| `NursingNoteAnalyzerScanner` | 护理文本分析 | 读取近 `12h` 护理记录，抽取风险信号、执行障碍、护理任务延迟、特殊事件，并给相似病例和 AI 页签提供文本证据。 |
| `NursingWorkloadScanner` | 护理工作量预测 | 以基础分、机械通气、CRRT、升压药、近期告警、护理上下文计算护理负荷，再映射到 NAS 风格指数，用于 `summary / dept_rows / patient_rows / heatmap / timeline`。 |
| `AlertReasoningScanner` | 告警解释增强 | 不是新病种扫描器，而是把近 `30min` 活跃告警组合交给规则/AI 解释器，补充“为什么发生、最可能关联什么、建议先做什么”。 |
| `IntegratedRiskReasoningScanner` | 综合风险推理报告 | 聚合患者近 `2h` 活跃告警，按循环、呼吸、肾脏、凝血、神经、感染、代谢/营养等系统重新组织，再调用 `RAG + LLM` 输出结构化综合推理报告：`summary / causal_chain / deterioration_forecast / top3_actions / differential_diagnosis`。报告写入 `integrated_risk_reports`，并同步推送 Dashboard 综合态势卡片。 |

---

## 2. 核心评分与计算口径

这一节把项目里最容易被问到的“怎么算”统一写清楚。

### 2.1 告警严重度

项目里常见严重度顺序为：

- `none = 0`
- `normal = 1`
- `warning = 2`
- `high = 3`
- `critical = 4`

### 2.2 告警抑制

默认配置：

- 同患者同规则 `1800s` 内不重复触发
- 每患者每小时最多 `10` 条

### 2.3 个体基线偏离

个体阈值不是简单固定阈值，而是：

1. 读取近 `12h~48h` 基线分布。
2. 结合 `z-score`、相对偏移、绝对最小偏移量判断。
3. 受总体安全边界限制，不能把阈值漂移到脱离医学常识。
4. 考虑升压药、镇静药背景。
5. 最终只给“建议阈值”，需要审核后才生效。

### 2.4 血气与酸碱分析

系统当前支持把血气做成结构化解释，不只是单个数值超界。核心包括：

- 主酸碱紊乱识别
- Winter 代偿判断
- 校正阴离子间隙
- Delta-Delta
- 乳酸校正 AG
- 呼吸性酸碱急慢性区分
- Stewart SID 分析

### 2.5 脓毒症 1h Bundle

数据来源：

- `score_records.score_type in {sepsis_bundle_tracker, sepsis_antibiotic_bundle}`
- `bundle_type in {sepsis_hour1_bundle, sepsis_1h_antibiotic}`

状态派生：

- `met` / `met_late` / `pending` / `overdue_1h` / `overdue_3h`

### 2.6 撤机评估

SBT 记录解析规则：

- 文本含 `通过 / 成功 / 耐受 / passed / success` 视为 `passed`
- 文本含 `失败 / 不通过 / 终止 / failed / abort / intolerant` 视为 `failed`
- `1 / true` 视为通过，`0 / false` 视为失败
- 能取到 `RR / VTe / minute ventilation` 时会计算 `RSBI`

撤机风险评分逻辑：

- 以 `factor_weights` 加权累积分
- 以 `FiO2/PEEP/MAP/血管活性药/RASS` 作为就绪闸门

### 2.7 护理工作量 (Nursing Workload)

工作量构成：

- 基础分 + 机械通气分 + CRRT 分 + 升压药分 + 近期告警负荷 + 护理文本和任务上下文。
- 最终映射到 NAS (Nursing Activities Score) 风格指数。

### 2.8 相似病例 (Similar Cases)

综合评分公式：

- `embedding_similarity * 0.4`
- `token_similarity * 0.1`
- `age_score * 0.15`
- `sofa_score * 0.25`
- `support_score * 0.1`

---

## 3. 亚表型分析 (Subphenotype)

当前实现不是历史全集重聚类，而是：

- 使用原型中心 (Prototype Centroids)
- 计算欧式距离/余弦距离
- softmax 得到软分群概率 (Soft Assignment)

## 4. 呼吸机不同步识别

- `VentilatorAsynchronyScanner` 采用“可选波形标志优先、结构化参数回退”的双通路策略：若系统能直接提供不同步计数/标志位，优先使用；若缺失，则退化为 `RR 失配 + VT 叠加 + RASS/P0.1/Edi` 的启发式近似识别。
- 扫描结果会持久化为 `score_type = ventilator_asynchrony_assessment`，供撤机、膈肌保护与 ARDS 模块主动读取，而不仅是独立出一条告警。
- 告警统一使用 `alert_type = ventilator_asynchrony`，但 `detail.asynchrony_type` 区分具体类型；这样前端和 `AlertReasoningScanner` 可以按一个主类型聚合，同时保留子类型细节。
- 与现有模块联动包括：`VentilatorWeaningScanner` 将近期不同步直接纳入撤机风险评分与闸门；`DiaphragmProtectionScanner` 将不同步作为 VIDD/驱动异常联合证据；`ARDS` 背景双触发叠加高 VT 时会主动升级肺保护提示。

## 5. 综合风险与代谢阶段

- `IntegratedRiskReasoningScanner` 不是简单把多条告警拼起来，而是先做告警系统分组、密度趋势判断和冷却去重，再把结构化上下文送入 `LLM + RAG`。同患者 `2h` 内默认不重复生成，除非出现新 `critical` 或新增 `>=2` 条高等级告警。
- `MetabolicPhaseDetectorScanner` 会把阶段判定结果持久化到 `score_type = metabolic_phase_detector`，同时同步到 `patient.current_profile.metabolic_phase`，这样 `AlertReasoningScanner` 与其他 AI 模块可以直接引用当前代谢阶段和推荐热卡/蛋白窗口。
- `BetaBlockerAdvisorScanner` 走的是“先筛适应证、再排禁忌证、再给剂量建议”的临床路径，避免把持续心动过速机械等同于 β 阻滞剂适应证。只有在脓毒症、心肌损伤、相对稳定血流动力学且无明显禁忌证时，才会上升到高等级建议。
