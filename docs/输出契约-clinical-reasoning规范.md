# 输出契约 · `clinical_reasoning` 字段规范（D1–2 拍板版）

> 状态：**已拍板**（2026-10-10）。本文档是微调数据合成、验证门禁、前端可解释性展示的唯一"北极星标准"。
> 取代《提示词手册与4090D微调方案》第三节中 `reasoning` 字段的泛化命名。
> 适用范围：**强制 JSON 输出的 T0 模块**（警报推理、AI 风险评估、临床推理 SPAR、文书 6 模板、交接班）。T2 短文本任务（播报、润色、摘要）不加此字段。

---

## 一、三项契约

1. **键名统一为 `clinical_reasoning`**
   不用 `reasoning` / `thought` 等泛化名，语义明确、避免与业务字段撞名。

2. **生成顺序置顶（First Key）——仅约束生成，不约束消费**
   模型必须先输出 `clinical_reasoning`，在其中完成病理生理推导、指标矛盾排查、指南标准对照，再输出具体动作与结构化字段（自回归顺序即思考顺序）。
   **消费端不得依赖键序**（JSON 规范不保证键序）：下游一律按键名取值。

3. **下游完全解耦（可选字段）**
   各模块 Pydantic 模型统一增加：

   ```python
   clinical_reasoning: Optional[str] = Field(
       default=None, description="临床思考链推理（可解释性回溯/医生审查展示用）"
   )
   ```

   业务逻辑不依赖该字段即可原样运行；前端/日志按需取用。
   `response_format=json_object` 与现有 `json.loads()` 解析流程**零改动**。

---

## 二、T0 四类场景标准模板

> ⚠️ 以下字段为**方向示例**。合成与生产样本前，必须与代码中的真实 schema 逐一核对：
> `alert_engine/alert_reasoning_agent.py`、`services/clinical_reasoning_agent.py`、
> `services/document_generator.py`、`app/services/handover/schemas.py`。
> 模板字段与真实 schema 冲突时，**以代码为准**。

### 1. 警报推理 / 风险归因

```json
{
  "clinical_reasoning": "1. 患者近2h MAP由75降至58mmHg，心率代偿性升至130bpm；2. 乳酸由1.8升至4.1mmol/L，提示外周微循环灌注急剧恶化；3. 结合体温38.8℃及PCT明显升高，排除心源性，高度支持脓毒性休克早期失代偿。",
  "risk_level": "CRITICAL",
  "primary_syndrome": "Septic Shock",
  "root_cause_summary": "腹腔重症感染继发严重全身炎症反应与血管麻痹性休克",
  "requires_doctor_confirm": true,
  "priority_actions": [
    "立即启动晶体液快速扩容试验（30mL/kg）并评估容量反应性",
    "去甲肾上腺素泵注维持 MAP ≥ 65 mmHg",
    "1小时内完成血培养复查并优化广谱抗生素方案"
  ]
}
```

### 2. 临床推理 SPAR

```json
{
  "clinical_reasoning": "根据S-P-A-R逻辑：【Strategy】首要假设为急性左心衰加重伴肺水肿，次要假设为重症肺炎合并ARDS；【Plan】需比对BNP/NT-proBNP与床旁超声彗尾征；【Action】下调入量，利尿并高流量吸氧；【Reflect】警惕肾功能恶化。",
  "hypotheses": [
    {"rank": 1, "condition": "Acute Heart Failure with Pulmonary Edema", "probability": "HIGH"},
    {"rank": 2, "condition": "Severe Pneumonia / ARDS", "probability": "MEDIUM"}
  ],
  "recommendations": [
    "行床旁心肺重症超声评估LVEF及下腔静脉塌陷率",
    "静脉注射呋塞米 20mg，严格控制出入量"
  ],
  "monitoring_plan": "严密监测每小时尿量、血气 PaO2/FiO2 及电解质变化"
}
```

### 3. 文书生成 / 查房记录

```json
{
  "clinical_reasoning": "基于患者入科24h内生命体征波动、实验室血气及机械通气参数进行系统性归纳，输入中未提供之既往史绝不补充，严格按器官系统组织。",
  "document_type": "daily_progress_note",
  "organ_systems": {
    "cardiovascular": "心率95-115bpm，窦性，去甲肾上腺素0.15 ug/kg/min维持下MAP稳定在68-75mmHg。",
    "respiratory": "SIMV模式，FiO2 40%，PEEP 8cmH2O，血气提示PaO2/FiO2为245，中度ARDS好转期。",
    "renal": "24小时总尿量1850mL，肌酐较昨日下降至110umol/L，体液平衡呈负平衡500mL。"
  },
  "assessment_and_plan": "循环趋稳，继续原剂量血管活性药物维持；尝试下调氧浓度，评估脱机指征。"
}
```

### 4. 边界对抗样本（拒绝契约）

```json
{
  "clinical_reasoning": "输入数据出现生理指标严重逻辑冲突：MAP仅为52 mmHg处于极危休克状态，但输入标签标注为'循环平稳'；且生化指标中肌酐缺失却要求计算完整SOFA评分。根据医疗安全守则，判定为矛盾数据并拒绝静默推断。",
  "status": "DATA_ANOMALY_REJECTED",
  "anomaly_reasons": [
    "MAP 52 mmHg 与'循环平稳'描述直接矛盾",
    "缺少必需的生化参数（肌酐/总胆红素），无法合规计算SOFA评分"
  ],
  "action": "建议临床医护核实传感器接触状态及实验室报告完整性后再行评估"
}
```

---

## 三、样本生产要求（合成与日志采集共用）

| # | 要求 | 门禁 |
|---|---|---|
| 1 | system 必须还原**对应模块原生 system**，尾接 `LLM_PROMPT_SOURCE_RULES` | `validate_train_data.py` system 覆盖率 = 100%、守则命中 = 100% |
| 2 | output 为合法 JSON，**首个键为 `clinical_reasoning`** | `validate_train_data.py --contract` |
| 3 | 种子数据必须**全合成**（外部 API 场景严禁真实病例）；日志来源走 `deidentify_text` | 人工抽查 + `lora_training_corpus_audit` |
| 4 | 数值零编造：输出中的每个数值必须能在输入中找到（反例样本除外，其 output 必须是拒绝契约） | 数值一致性测试脚本（第二轮建） |
| 5 | 每条样本带 `prompt_module` 元数据，便于分模块评估 | 合成脚本/采集脚本负责写入 |

## 四、验收指标（灰度放行标准）

- JSON 可解析率 100%
- `clinical_reasoning` 覆盖率 100%、首键率 100%（生成顺序）
- schema 字段完整率 ≥ 99%
- 数值零幻觉率达标（数值一致性测试）
- 边界反例拒绝率 100%（100 条对抗样本全过）
