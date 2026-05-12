# ICU 智能预警系统（ICU Alert System）

![ICU Alert System Logo](docs/images/logo.png)

面向重症监护病区（ICU）的全栈平台，集成了实时临床数据采集、智能风险预警、数字孪生可视化、大模型（LLM）临床辅助推理以及强大的科研分析与导出引擎。

---

## 目录

- [1. 系统所有功能模块](#1-系统所有功能模块)
- [2. 完整后端 API 接口清单](#2-完整后端-api-接口清单)
- [3. 部署与如何配置 docker-compose.yml](#3-部署与如何配置-docker-composeyml)
- [4. 快速启动与开发构建](#4-快速启动与开发构建)
- [5. 仓库结构](#5-仓库结构)
- [6. 相关文档](#6-相关文档)

---

## 1. 系统所有功能模块

系统为 ICU 医护人员与科研人员提供了全工作流的支持，核心功能如下：

### 1.1 全景监控与大屏 (Big Screen)
- **病区宏观视角**：展示 ICU 病区全部床位的占用情况、风险等级分布、当日预警总数与处置率。
- **危急告警播报**：实时滚动播报高优先级（Critical / High）的临床预警事件，确保零漏报。

### 1.2 患者总览工作台 (Patient Overview)
- **卡片化监控**：以网格卡片形式展示全科患者的核心生命体征、主要阳性体征与当前高优预警。
- **智能筛选**：支持按风险级别（红黄绿）、按病种、按责任护士或床位号进行多维度过滤。

### 1.3 多维患者详情 (Patient Detail Workbench)
- **数字孪生与人体图 (Digital Twin & Body Map)**：采用 3D/2D 可视化交互，直观映射患者器官风险热力分布。
- **装置管路与 HAI 并发症**：可视化展现导尿管、中心静脉导管、人工气道等装置的留置位置，联动评估 VAP、CRBSI、CAUTI 等院内感染风险。
- **生命体征波形与趋势**：高频波形数据回放与多日趋势曲线横向对比叠加显示。
- **检验检查与用药轨迹**：结构化展示最新检验异常指标靶向提示，并追踪血管活性药物等重症专科用药的给药轨迹与出入量平衡。
- **重症 Bundle 质控**：提供重症集束化治疗（如感染性休克 Bundle、VAP Bundle）的依从性清单与自动勾选评估。

### 1.4 AI 临床大脑 (AI Clinical Assistant)
- **AI 查房助手 (AI Consult)**：基于 LLM 与 RAG 技术，医护可直接与系统对话，系统根据患者既往病史、当前体征自动进行病历推理与诊断建议（H&P）。
- **指标智能解读**：自动分析复杂的血气、肝肾功等化验单，指出异常指标间的相互关联及潜在临床意义。
- **自动交接班摘要与文书生成**：根据当班的护理事件与病情变化，一键自动生成 SBAR 格式的交班记录以及相关的医疗文书草稿。
- **多智能体 MDT 会诊工作站 (Multi-Agent MDT)**：基于多智能体编排技术，自动模拟呼吸、心血管、感染等多学科专家的联合讨论逻辑。系统可自动提取指征生成 MDT 讨论材料，智能汇总各科意见，最终输出结构化的医嘱草稿与诊疗决议。

### 1.5 临床预警与底层规则引擎 (Clinical Alert Engine)
后台驻留超过 30 种专科医学扫描器，涵盖：
- **生命体征与恶化预警**：生命体征多维绝对值与相对个体基线偏离报警，以及基于时间序列的 Temporal Risk 时序恶化预测。
- **专科综合征风险引擎**：内置脓毒症 (Sepsis/qSOFA)、ARDS、AKI、DIC、PE 等复杂重症并发症的自动分期与风险提示。
- **治疗设备与给药监控**：CRRT 滤器凝堵预警、万古霉素/碳青霉烯等抗菌药 TDM 闭环建议、俯卧位治疗时间监测等。
- **动态阈值与抑制逻辑**：支持告警同类事件限流（如半小时内免打扰）、基于个体生理分布建议自适应动态报警阈值。

### 1.6 实时波形与血流动力学 (Waveform & Hemodynamics)
- **高频波形流集成**：对接床旁监护仪与呼吸机高频数据，获取实时心电图 (ECG) 与呼吸波形片段。
- **呼吸机不同步识别**：自动分析呼吸波形，计算人机不同步指数 (AI)，识别无效触发、双触发、反向触发等异常状态。
- **右心负荷与血流动力学建议**：综合 CVP、BNP、乳酸及升压药物使用情况，智能输出右心负荷及 β 受体阻滞剂用药决策建议。

### 1.7 重症护理负荷与流程闭环 (Nursing & Workflow)
- **NAS 护理负荷预测**：根据基础病情、机械通气、CRRT、升压药使用情况等自动评估每位患者的护理负荷。
- **重症专科评估超时提醒**：智能跟踪 GCS、RASS、CPOT、CAM-ICU 等量表评估频次，防范评估遗漏。
- **PICS / eCASH / 谵妄预防**：监控镇静、镇痛、早期活动是否达标，提前阻断 ICU 获得性衰弱 (ICU-AW) 与认知障碍。

### 1.8 科研与数据导出平台 (Research Workbench)
- **可视化队列构建 (Cohort Builder)**：提供所见即所得的患者筛选条件配置，支持组合逻辑并保存为专属科研队列。
- **在线统计分析引擎**：
  - 基线特征表 (Table 1) 自动生成。
  - 生存分析 (KM 曲线 / Cox 比例风险回归)。
  - 多因素线性与逻辑斯蒂回归分析。
  - 诊断试验与 ROC 曲线绘制。
  - 亚组分析与相关性热力图。
- **图表与宽表导出**：支持生成出版级高清科研图表下载，以及结构化脱敏临床宽表导出，供 SPSS/R/Python 做进一步分析。

### 1.9 临床知识库与 RAG 检索引擎 (Knowledge Base)
- **本地医学文献库**：集成 ICU 临床指南、最新文献及操作规范，支持离线或热更新知识包。
- **智能循证支持**：通过 RAG (检索增强生成) 架构，在 AI 对话和告警解释中自动提取原始文献片段（Chunk）作为循证证据支持。

### 1.10 长期随访与康复管理 (Follow-up & Rehab)
- **PICS 风险转出评估**：基于量表和临床数据，在患者离开 ICU 时自动评估 ICU后综合征 (PICS) 风险（认知、心理及身体功能）。
- **随访任务与转诊闭环**：为高风险患者建立长期随访档案，自动生成随访任务清单（如 30天/90天 电话回访），并支持向康复科一键发起康复转诊请求 (Rehab Referrals)。

### 1.11 系统后台管理与运行控制 (System Admin)
- **运行时配置中心 (Runtime Config Center)**：全新的 Web 界面配置中心，支持在不重启系统的情况下，热更新并动态配置：
  - **各个业务功能模块**（如医生查房、营养支持等）的界面显隐与开关。
  - **AI 多模型与地址池配置**：直接在前端界面中构建模型池，配置多个不同供应商的模型接口地址、API Key 及超时设置。
  - **动态模型路由**：将不同的临床推理任务（如快速摘要、医疗推理、复杂推理、长上下文及高可用兜底）动态分配给适合的模型，即时生效。
  - **预警引擎与扫描规则调整**：实时修改预警规则的条件参数或阈值（如心率上下限等）并立即生效。
  - **数据字段映射**：支持动态修改底层核心表和数据的标准化映射关系。
- **特定扫描器管控**：提供系统运行时接口，支持对特定医学扫描器的强制紧急触发，用于系统调试或人工高优告警重算。

### 1.12 智能查房报告 (Rounding Sheet)
- **过夜摘要**：按 8/12/24/48 小时时间窗汇总预警、生命体征、实验室、用药、呼吸机、护理、出入量、感染与营养变化。
- **器官系统视图**：按神经、呼吸、循环、肾脏/液体、感染、营养、凝血和其他事件分类展示查房重点。
- **AI 关注点**：复用 LLM runtime 生成 3-5 条可审计关注点，所有输出均标注“仅供临床决策支持，不替代医生判断”。

### 1.13 呼吸治疗师工作面板 (Respiratory Dashboard)
- **机械通气患者一览**：统一计算 Driving Pressure、P/F Ratio、SBT 候选状态与风险标签。
- **SBT 待办**：复用/扩展撤机扫描能力，输出可评估、暂不适合、已完成和失败原因。
- **气道管理**：支持气囊压、吸痰、人工气道、VAP bundle、困难气道预案记录与提醒。

### 1.14 科室学术与科研支撑 (Academic & Research Support)
- **科研项目看板**：管理论文、课题、基金、伦理、专利与指南共识等项目全生命周期。
- **AI 课题推荐**：基于可追溯聚合数据和质量差距生成课题建议，输出数据依据、限制和可行性评分。
- **OMOP 最小导出**：提供 PERSON、VISIT_OCCURRENCE、CONDITION_OCCURRENCE、DRUG_EXPOSURE、MEASUREMENT、PROCEDURE_OCCURRENCE、OBSERVATION 的脱敏 CSV ZIP 导出框架和数据质量检查。

### 1.15 临床试验智能筛选 (Clinical Trial Screening)
- **试验配置与规则引擎**：支持结构化入排标准、时间窗、规则解释和 AI 辅助自然语言解析草案。
- **自动候选筛选**：新增 ClinicalTrialScreeningScanner，当前患者满足入组且未触发排除时，仅提示“可能符合”。
- **医生确认闭环**：候选状态流转、匹配依据、缺失数据和置信度均可审计，患者详情页同步展示提醒卡片。

---

## 2. 完整后端 API 接口清单

后端采用 FastAPI 提供了全面且高性能的 RESTful 与 WebSocket API：

### 2.1 基础与系统接口
- `GET /health` : 系统健康检查，检测数据库与 Redis 连接状态。
- `GET /api/departments` : 获取所有注册的 ICU 科室与病区列表。

### 2.2 患者管理与详情数据获取
- `GET /api/patients` : 分页获取患者列表（支持床号、风险、科室筛选）。
- `GET /api/patients/{patient_id}` : 获取单个患者的基础静态详情。
- `GET /api/patients/{patient_id}/vitals` : 获取当前生命体征快照。
- `GET /api/patients/{patient_id}/vitals/trend` : 获取生命体征历史趋势图数据。
- `GET /api/patients/{patient_id}/labs` : 获取该患者全部化验指标。
- `GET /api/patients/{patient_id}/drugs` : 获取给药记录与医嘱。
- `GET /api/patients/{patient_id}/assessments` : 获取护理评估（如 GCS, APACHE II, 压疮风险）。
- `GET /api/patients/{patient_id}/bedcard` : 获取床头卡信息以及装置和管路留置记录。
- `GET /api/patients/{patient_id}/discharge-readiness` : AI 或规则评估的出院准备度。
- `GET /api/patients/{patient_id}/similar-case-outcomes` : 检索与该患者病情相似的历史病例及其预后情况。

### 2.3 临床预警与实时数据推送
- `GET /api/patients/{patient_id}/alerts` : 获取患者的临床预警历史列表。
- `POST /api/patients/{patient_id}/alerts/view` : 临床人员标记预警为已读/已响应，闭环预警。
- `POST /api/patients/bundle-status` : 更新或确认患者 Bundle（集束化治疗）项目的完成状态。
- `WS /ws/alerts` : **WebSocket 推送通道**，向前端大屏和护士站实时推送新产生的报警。
- `GET /patients/{patient_id}/channels` : 获取实时心电/波形可用通道。
- `GET /patients/{patient_id}/segments` : 拉取高频波形历史片段。

### 2.4 AI 大语言模型与知识计算接口
- `POST /ai/chat` : 临床智能对话接口，支持连续对话与上下文关联（支持流式响应）。
- `POST /ai/plan` : 传入患者状态，由 AI 生成个性化的临床诊疗建议与计划。
- `POST /ai/interpret` : 针对传入的单个或组套检验指标，返回专家级别的详细解读与临床提示。
- `GET /api/ai/mdt-workspace/{patient_id}` : 获取患者多智能体 MDT 会诊工作站当前的会话材料、讨论记录与生成的医嘱草稿。
- `POST /api/ai/mdt-workspace/{patient_id}` : 保存或推进 MDT 会诊讨论状态。
- `GET /api/ai/mdt-workspace/{patient_id}/sessions` : 获取患者历史的 MDT 会诊记录列表。

### 2.5 科研平台与数据分析统计
- `POST /analytics/cohort/preview` : 预览患者队列筛选条件结果。
- `POST /analytics/cohort/save` : 保存自定义的患者科研队列。
- `GET /analytics/cohort/list` : 获取当前用户保存的全部队列。
- `POST /analytics/table1` : 根据所选队列生成基线特征表 (Table 1)。
- `POST /analytics/survival` : 提交时间与事件数据，执行生存分析并返回 KM 数据点。
- `POST /analytics/regression` : 执行回归分析，返回 OR/HR 值及 P 值。
- `POST /analytics/roc` : 计算灵敏度/特异度，返回 ROC 曲线与 AUC 值。
- `POST /analytics/export-figure` : 将分析所得的高级图表（PNG/SVG）保存并导出。
- `POST /analytics/export-table` : 导出多维分析表格为 CSV/Excel。
- `POST /export` : 提交异步脱敏宽表导出任务。
- `GET /export/{task_id}/status` : 轮询导出任务的完成状态。
- `GET /export/{task_id}/download` : 任务完成后下载对应的数据压缩包。

### 2.6 临床知识库接口 (Knowledge & RAG)
- `GET /api/knowledge/documents` : 获取本地离线知识包与指南文档列表。
- `GET /api/knowledge/chunks/{chunk_id}` : 获取特定的文献证据片段详情，供前端循证高亮展示。
- `POST /api/knowledge/reload` : 不停机热更新系统的本地向量知识库。

### 2.7 长期随访与康复接口 (Follow-up)
- `GET /api/followup_cases` : 获取目前在管的随访病例库列表。
- `POST /api/followup_cases/patients/{patient_id}` : 根据最新 PICS 风险，将患者正式纳入长期随访池。
- `GET /api/followup_tasks/patients/{patient_id}` : 查询针对该患者设定的定期回访任务。
- `GET /api/rehab_referrals/patients/{patient_id}` : 查询或下达针对该患者的早期/出院后康复治疗转诊记录。

### 2.8 后台管理与运行时配置接口 (Admin)
- `POST /api/admin/scanner/trigger` : 手动触发底层的离线预警引擎特定扫描器（Scanner）立刻执行。
- `GET /api/admin/runtime-config` : 获取系统的完整运行时配置。
- `POST /api/admin/runtime-config/modules` : 热更新各个模块开启状态。
- `POST /api/admin/runtime-config/ai` : 热更新 AI 多模型配置与供应商地址池。
- `POST /api/admin/runtime-config/alert-rules/{rule_id}` : 修改底层的临床预警报警规则阈值。
- `POST /api/admin/runtime-config/field-mapping` : 修改核心字段标准化字典映射。

### 2.9 智能查房报告接口 (Rounding Sheet)
- `GET /api/rounding/patients` : 获取今日需要查房的 ICU 患者列表和基础风险信息。
- `GET /api/rounding/{patient_id}/summary?hours=24` : 获取单个患者过去 N 小时结构化查房摘要。
- `POST /api/rounding/{patient_id}/ai-insights` : 生成并审计 AI 查房关注点。
- `POST /api/rounding/export` : 导出 Markdown 或 HTML 查房报告。

### 2.10 呼吸治疗师接口 (Respiratory Dashboard)
- `GET /api/respiratory/ventilated-patients` : 获取全科机械通气患者和统一计算指标。
- `GET /api/respiratory/sbt-candidates` : 获取 SBT 候选和暂不适合原因。
- `POST /api/respiratory/sbt/{patient_id}/status` : 更新 SBT 状态。
- `GET /api/respiratory/{patient_id}/ventilator-timeline?hours=72` : 获取呼吸机参数变化时间线。
- `GET /api/respiratory/{patient_id}/airway-records` : 获取气道管理记录。
- `POST /api/respiratory/{patient_id}/airway-records` : 新增气道管理记录。
- `GET /api/respiratory/{patient_id}/airway-plan` : 获取困难气道预案。
- `POST /api/respiratory/{patient_id}/airway-plan` : 保存困难气道预案并写入审计日志。

### 2.11 学术科研支撑接口 (Academic & Research Support)
- `GET /api/research/projects` : 获取科研项目列表。
- `POST /api/research/projects` : 新建科研项目。
- `PUT /api/research/projects/{project_id}` : 更新科研项目。
- `DELETE /api/research/projects/{project_id}` : 删除科研项目。
- `GET /api/research/topic-suggestions` : 获取已生成课题建议。
- `POST /api/research/topic-suggestions/generate` : 基于数据摘要生成 AI 课题建议。
- `POST /api/research/omop/export` : 提交 OMOP CDM 最小脱敏导出任务。
- `GET /api/research/omop/export/{task_id}/status` : 查询 OMOP 导出任务状态。
- `GET /api/research/omop/export/{task_id}/download` : 下载 OMOP CSV ZIP。
- `GET /api/research/data-quality` : 获取科研导出数据质量报告。

### 2.12 临床试验筛选接口 (Clinical Trial Screening)
- `GET /api/clinical-trials` : 获取临床试验列表。
- `POST /api/clinical-trials` : 新建临床试验。
- `GET /api/clinical-trials/{trial_id}` : 获取试验详情。
- `PUT /api/clinical-trials/{trial_id}` : 更新试验。
- `DELETE /api/clinical-trials/{trial_id}` : 删除试验。
- `POST /api/clinical-trials/{trial_id}/parse-criteria` : AI 解析自然语言入排标准草案。
- `POST /api/clinical-trials/{trial_id}/activate` : 启用试验筛选。
- `POST /api/clinical-trials/{trial_id}/deactivate` : 停用试验筛选。
- `POST /api/clinical-trials/screen` : 手动触发当前患者试验筛选。
- `GET /api/clinical-trials/candidates` : 获取候选患者列表。
- `GET /api/clinical-trials/patients/{patient_id}/matches` : 获取患者详情页临床试验匹配提醒。
- `POST /api/clinical-trials/candidates/{candidate_id}/status` : 更新候选状态并记录审计日志。

---

## 3. 部署与环境配置

系统采用 Docker 化一键部署，核心服务包括 `api`（FastAPI 服务）和 `redis`（缓存与消息队列）。业务数据依赖 MongoDB。

### 3.1 配置文件 (`docker-compose.yml`) 结构解析

`docker-compose.yml` 里面通过 `${VARIABLE_NAME}` 读取环境变量。它的关键配置块如下：

```yaml
services:
  api:
    image: icu_alert_api
    ports:
      - "8000:8000"
    environment:
      - SMARTCARE_DB_HOST=${SMARTCARE_DB_HOST:-127.0.0.1}
      - LLM_BASE_URL=${LLM_BASE_URL:-https://notion.jylb.fun/v1}
      # 更多环境变量...
    depends_on:
      - redis
```

### 3.2 动态配置中心与 .env 文件

为了支持高度定制和不停机的动态更新，本系统采用 **双层配置架构**：

1. **部署基础变量 (.env)**
   要修改基础环境变量，请复制并编辑同级目录或 `backend/` 下的 `.env` 文件：
   ```bash
   cp backend/.env.example backend/.env
   ```
   **数据库配置**：在 `.env` 内配置 MongoDB IP（`SMARTCARE_DB_HOST`）和可选的账号密码。
   **Redis 缓存**：默认无需修改 `REDIS_HOST=icu_alert_redis`，可通过 `REDIS_PASSWORD` 加密。

2. **运行时配置中心 (Runtime Config Center - 推荐 AI 配置方式)**
   大模型 API 路由和医学预警规则在部署后，推荐通过系统内置的**运行时配置中心页面**进行可视化动态配置：
   
   在浏览器进入 `配置中心`，即可完成以下操作（写入数据库后立即生效，**无需重启容器**）：
   - **模型供应商池管理**：您可以任意新增多个大模型的接口地址（比如同时添加本地的 Ollama 服务和公有云的 API，配置各自的 API Key、模型标识及超时时间）。
   - **多路路由分发**：系统可根据任务特征自动分流请求，您可在前端页面分别指定：
     - **快速摘要 (Fast)**: 用于快速总结、基础图文。
     - **医疗推理 (Medical)**: 处理病历提取、专科检验解读。
     - **复杂推理 (Reasoning)**: 科研级多步长逻辑推理（支持思维链）。
     - **高可用兜底 (Fallback)**: 遇到网络波动或并发熔断时，自动回滚重试的兜底模型。
   - **阈值热更新**：直接在页面更改诸如“危急心率上限”等预警规则阈值，引擎扫描时将自动采用新参数。

> **提示：** 
> 运行时配置中心启用的配置将自动覆盖对应的 `.env` 初始配置。如配置中心为空，系统会降级回退读取 `.env` 中定义的 `LLM_BASE_URL` 等环境变量兜底。

**步骤 3：启动容器**
确保 `.env` 及所需环境就绪后，在 `docker-compose.yml` 所在目录执行：

```bash
# 启动所有服务
docker-compose up -d

# 查看 API 运行日志，验证配置是否生效
docker-compose logs -f api
```

---

## 4. 快速启动与开发构建

### 4.1 本地开发运行 (非 Docker)

**后端：**
```bash
cd backend
pip install -r requirements.txt
# 启动 API 服务
python run_server.py
# 启动离线预警规则扫描引擎 (新开终端)
python run_scan_worker.py
```

**启用轨迹预测的可选依赖：**
Chronos/TimesFM 轨迹预测属于可选本地模型能力。若需要加载 `model.safetensors` 形式的 Chronos 模型，请安装运行时依赖并配置模型根目录：

```bash
pip install chronos-forecasting
export ICU_MODELS_DIR=/opt/icu-models
# 期望模型目录：/opt/icu-models/chronos/model.safetensors
```

未安装 `chronos-forecasting` 时，API 会保持可启动并返回 `unavailable` 状态。

**前端：**
```bash
cd frontend
npm install
npm run dev
```
前端默认地址：`http://127.0.0.1:5173`。

**新增模块验证：**
```bash
# 后端关键服务单元测试
python -m pytest backend/tests/test_rounding_service.py backend/tests/test_respiratory_service.py backend/tests/test_omop_export_service.py backend/tests/test_clinical_trial_service.py

# 前端类型检查与生产构建
cd frontend
npm run build
```

### 4.2 打包与发行

系统支持编译为独立的可执行文件（无需依赖 Python 环境）：
- Windows EXE：运行 `build_exe.ps1`
- Linux Binary：运行 `build.sh`
- Oracle Linux (OEL 8)：运行 `build_oel8.ps1`

打包后的前端产物会自动通过 `postbuild` 脚本挂载到后端的 `static/` 目录中，实现前后端一体化单文件/单镜像部署。

---

## 5. 仓库结构

```text
icu-alert-system/
├─ backend/                    # FastAPI + 扫描引擎 + AI 服务
│  ├─ app/
│  │  ├─ alert_engine/         # 扫描器与预警规则引擎
│  │  ├─ routers/              # 上述提到的所有 API 路由
│  │  ├─ services/             # 核心服务 (llm_runtime, research_analytics)
│  │  └─ main.py               # FastAPI 入口
│  ├─ run_server.py            # 后端启动脚本
│  └─ run_scan_worker.py       # 扫描 Worker 后台任务入口
├─ frontend/                   # Vue 3 前端
│  ├─ src/
│  │  ├─ components/           # (BigScreen, PatientDetail 等)
│  │  ├─ views/                # (病区概览, 大屏, 配置中心等)
│  │  └─ api/                  # 前端 Axios 接口定义
│  └─ package.json
├─ docs/                       # 文档与图片资源
├─ SCANNERS.md                 # 扫描器医学口径与算法说明
└─ docker-compose.yml          # Docker 服务编排文件
```

---

## 6. 相关文档

- 预警口径与医学规则：[SCANNERS.md](SCANNERS.md)
- Windows 可执行打包指引：[EXE_BUILD.md](EXE_BUILD.md)
- Linux 二进制构建指引：[LINUX_BINARY_BUILD.md](LINUX_BINARY_BUILD.md)
- OEL8 离线环境构建指引：[OEL8_BUILD.md](OEL8_BUILD.md)
