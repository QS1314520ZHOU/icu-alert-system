<template>
  <div class="scores-page">
    <!-- 三栏布局 -->
    <div class="content-grid">
      <!-- 左栏：评分体系列表 -->
      <div class="panel panel--left">
        <div class="panel__header">
          <h3 class="panel__title">评分体系</h3>
        </div>
        <div class="panel__body">
          <div class="score-tree">
            <div v-for="group in scoreGroups" :key="group.name" class="score-group">
              <div class="group-header">
                <span class="group-name">{{ group.name }}</span>
              </div>
              <div
                v-for="variant in group.variants"
                :key="variant.id"
                :class="['tree-item', { 'tree-item--active': selectedRule?.id === variant.id }]"
                @click="selectRule(variant)"
              >
                <span class="tree-item__name">{{ variant.name }}</span>
                <span class="tree-item__version">{{ variant.version }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 中栏：评分详情 -->
      <div class="panel panel--center">
        <div class="panel__header">
          <h3 class="panel__title">评分详情</h3>
          <span v-if="selectedRule" class="panel__badge">{{ selectedRule.version }}</span>
        </div>
        <div class="panel__body">
          <div v-if="!selectedRule" class="empty-state">
            <span class="empty-icon">📈</span>
            <span class="empty-text">选择左侧评分体系查看详情</span>
          </div>
          <div v-else class="rule-detail">
            <!-- 基本信息 -->
            <div class="detail-section">
              <h4 class="section-title">基本信息</h4>
              <div class="detail-grid">
                <div class="detail-item">
                  <span class="detail-label">评分系统</span>
                  <span class="detail-value">{{ selectedRule.score_system }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">变体</span>
                  <span class="detail-value">{{ selectedRule.score_variant || '-' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">版本</span>
                  <span class="detail-value detail-value--code">{{ selectedRule.version }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">缺失值策略</span>
                  <span class="detail-value">{{ selectedRule.missing_policy || '默认' }}</span>
                </div>
                <div v-if="selectedRule.time_window" class="detail-item">
                  <span class="detail-label">时间窗</span>
                  <span class="detail-value">{{ selectedRule.time_window }}</span>
                </div>
              </div>
              <p v-if="selectedRule.description" class="detail-desc">{{ selectedRule.description }}</p>
            </div>

            <!-- 输入项 -->
            <div class="detail-section">
              <h4 class="section-title">输入项 ({{ selectedRule.inputs?.length || 0 }})</h4>
              <div class="input-table">
                <div class="input-header">
                  <span class="input-col input-col--name">名称</span>
                  <span class="input-col input-col--label">标签</span>
                  <span class="input-col input-col--type">类型</span>
                  <span class="input-col input-col--unit">单位</span>
                  <span class="input-col input-col--required">必填</span>
                </div>
                <div v-for="input in selectedRule.inputs" :key="input.name" class="input-row">
                  <span class="input-col input-col--name input-col--code">{{ input.name }}</span>
                  <span class="input-col input-col--label">{{ input.label }}</span>
                  <span class="input-col input-col--type">{{ input.type }}</span>
                  <span class="input-col input-col--unit">{{ input.unit || '-' }}</span>
                  <span class="input-col input-col--required">
                    <span :class="['required-dot', input.required ? 'required-dot--yes' : 'required-dot--no']"></span>
                  </span>
                </div>
              </div>
            </div>

            <!-- 阈值表 -->
            <div v-if="selectedRule.thresholds?.length" class="detail-section">
              <h4 class="section-title">阈值表</h4>
              <div class="threshold-list">
                <div v-for="(t, i) in selectedRule.thresholds" :key="i" class="threshold-item">
                  <span class="threshold-range">{{ t.range[0] }} - {{ t.range[1] }}</span>
                  <span class="threshold-label">{{ t.label }}</span>
                  <span v-if="t.severity" :class="['threshold-severity', `threshold-severity--${t.severity}`]">
                    {{ t.severity }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏：测试病例 -->
      <div class="panel panel--right">
        <div class="panel__header">
          <h3 class="panel__title">测试病例</h3>
          <button v-if="selectedRule" class="btn btn--sm btn--outline" @click="runTest">
            运行测试
          </button>
        </div>
        <div class="panel__body">
          <div v-if="!selectedRule" class="empty-state">
            <span class="empty-icon">🧪</span>
            <span class="empty-text">选择评分体系后运行测试</span>
          </div>
          <div v-else-if="testRunning" class="loading-state">
            <div class="spinner"></div>
            <span>正在计算...</span>
          </div>
          <div v-else-if="!testResult" class="empty-state">
            <span class="empty-icon">▶️</span>
            <span class="empty-text">点击"运行测试"查看结果</span>
          </div>
          <div v-else class="test-result">
            <!-- 总分 -->
            <div class="result-total">
              <span class="result-label">总分</span>
              <span class="result-score">{{ testResult.total_score }}</span>
            </div>

            <!-- 分项得分 -->
            <div class="result-section">
              <h4 class="section-title">分项得分</h4>
              <div class="component-list">
                <div v-for="(score, name) in testResult.component_scores" :key="name" class="component-item">
                  <span class="component-name">{{ name }}</span>
                  <span class="component-score">{{ score }}</span>
                </div>
              </div>
            </div>

            <!-- 元数据 -->
            <div class="result-section">
              <h4 class="section-title">评分元数据</h4>
              <div class="meta-list">
                <div class="meta-item">
                  <span class="meta-label">score_system</span>
                  <span class="meta-value meta-value--code">{{ testResult.score_system }}</span>
                </div>
                <div v-if="testResult.score_variant" class="meta-item">
                  <span class="meta-label">score_variant</span>
                  <span class="meta-value meta-value--code">{{ testResult.score_variant }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">rule_id</span>
                  <span class="meta-value meta-value--code">{{ testResult.rule_id }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">rule_version</span>
                  <span class="meta-value meta-value--code">{{ testResult.rule_version }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">evaluation_time</span>
                  <span class="meta-value">{{ testResult.evaluation_time }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">input_snapshot_hash</span>
                  <span class="meta-value meta-value--code meta-value--small">{{ testResult.input_snapshot_hash }}</span>
                </div>
              </div>
            </div>

            <!-- 缺失输入 -->
            <div v-if="testResult.missing_inputs?.length" class="result-section">
              <h4 class="section-title">缺失输入</h4>
              <div class="missing-list">
                <span v-for="m in testResult.missing_inputs" :key="m" class="missing-tag">{{ m }}</span>
              </div>
            </div>

            <!-- 输入证据 -->
            <div v-if="testResult.evidence?.length" class="result-section">
              <h4 class="section-title">输入证据</h4>
              <div class="evidence-list">
                <div v-for="e in testResult.evidence" :key="e.input" class="evidence-item">
                  <span class="evidence-input">{{ e.input }}</span>
                  <span class="evidence-value">{{ e.value }}</span>
                  <span v-if="e.source" class="evidence-source">{{ e.source }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getScoringSystems,
  evaluateScore,
  type ScoringRule,
  type ScoringResult,
} from '../../api/diseaseCenter'

// 状态
const selectedRule = ref<ScoringRule | null>(null)
const testRunning = ref(false)
const testResult = ref<ScoringResult | null>(null)

// 评分体系分组
interface ScoreGroup {
  name: string
  variants: ScoringRule[]
}

const scoreGroups = ref<ScoreGroup[]>([])

// 模拟数据
const mockGroups: ScoreGroup[] = [
  {
    name: 'SOFA',
    variants: [
      {
        id: 'sofa-classic',
        name: 'Classic SOFA 1996',
        score_system: 'SOFA',
        score_variant: 'classic_1996',
        version: 'v1.0.0',
        description: 'Sequential Organ Failure Assessment，1996年经典版本。评估6个器官系统功能障碍程度。',
        inputs: [
          { name: 'pao2_fio2', label: 'PaO2/FiO2', type: 'number', unit: 'mmHg', required: true },
          { name: 'platelets', label: '血小板', type: 'number', unit: '×10³/μL', required: true },
          { name: 'bilirubin', label: '胆红素', type: 'number', unit: 'mg/dL', required: true },
          { name: 'map', label: '平均动脉压', type: 'number', unit: 'mmHg', required: true },
          { name: 'dopamine', label: '多巴胺', type: 'number', unit: 'μg/kg/min', required: false },
          { name: 'dobutamine', label: '多巴酚丁胺', type: 'boolean', required: false },
          { name: 'epinephrine', label: '肾上腺素', type: 'number', unit: 'μg/kg/min', required: false },
          { name: 'norepinephrine', label: '去甲肾上腺素', type: 'number', unit: 'μg/kg/min', required: false },
          { name: 'gcs', label: 'GCS评分', type: 'number', required: true },
          { name: 'creatinine', label: '肌酐', type: 'number', unit: 'mg/dL', required: true },
          { name: 'urine_output', label: '尿量', type: 'number', unit: 'mL/day', required: false },
        ],
        thresholds: [
          { range: [0, 0], label: '正常', severity: 'normal' },
          { range: [1, 6], label: '轻度障碍', severity: 'mild' },
          { range: [7, 12], label: '中度障碍', severity: 'moderate' },
          { range: [13, 24], label: '重度障碍', severity: 'severe' },
        ],
        missing_policy: '使用最差值',
        time_window: '24小时',
      },
      {
        id: 'sofa-2',
        name: 'SOFA-2 2025',
        score_system: 'SOFA',
        score_variant: 'sofa2_2025',
        version: 'v2.0.0',
        description: 'SOFA 第二版，2025年更新。改进了呼吸和肾脏评估标准。',
        inputs: [
          { name: 'pao2_fio2', label: 'PaO2/FiO2', type: 'number', unit: 'mmHg', required: true },
          { name: 'platelets', label: '血小板', type: 'number', unit: '×10³/μL', required: true },
          { name: 'bilirubin', label: '胆红素', type: 'number', unit: 'mg/dL', required: true },
          { name: 'map', label: '平均动脉压', type: 'number', unit: 'mmHg', required: true },
          { name: 'vasopressor_dose', label: '血管活性药物剂量', type: 'number', unit: 'μg/kg/min', required: false },
          { name: 'gcs', label: 'GCS评分', type: 'number', required: true },
          { name: 'creatinine', label: '肌酐', type: 'number', unit: 'mg/dL', required: true },
          { name: 'urine_output', label: '尿量', type: 'number', unit: 'mL/day', required: false },
        ],
        thresholds: [
          { range: [0, 0], label: '正常', severity: 'normal' },
          { range: [1, 6], label: '轻度障碍', severity: 'mild' },
          { range: [7, 12], label: '中度障碍', severity: 'moderate' },
          { range: [13, 24], label: '重度障碍', severity: 'severe' },
        ],
        missing_policy: '使用最差值',
        time_window: '24小时',
      },
    ],
  },
  {
    name: 'qSOFA',
    variants: [
      {
        id: 'qsofa',
        name: 'qSOFA',
        score_system: 'qSOFA',
        version: 'v1.0.0',
        description: '快速SOFA评估，用于床旁快速筛查脓毒症。',
        inputs: [
          { name: 'respiratory_rate', label: '呼吸频率', type: 'number', unit: '次/分', required: true },
          { name: 'systolic_bp', label: '收缩压', type: 'number', unit: 'mmHg', required: true },
          { name: 'gcs', label: 'GCS评分', type: 'number', required: true },
        ],
        thresholds: [
          { range: [0, 0], label: '低风险', severity: 'normal' },
          { range: [1, 3], label: '高风险', severity: 'high' },
        ],
      },
    ],
  },
  {
    name: 'NEWS2',
    variants: [
      {
        id: 'news2',
        name: 'NEWS2',
        score_system: 'NEWS2',
        version: 'v1.0.0',
        description: 'National Early Warning Score 2，英国国家早期预警评分。',
        inputs: [
          { name: 'respiratory_rate', label: '呼吸频率', type: 'number', unit: '次/分', required: true },
          { name: 'spo2', label: 'SpO2', type: 'number', unit: '%', required: true },
          { name: 'temperature', label: '体温', type: 'number', unit: '°C', required: true },
          { name: 'systolic_bp', label: '收缩压', type: 'number', unit: 'mmHg', required: true },
          { name: 'heart_rate', label: '心率', type: 'number', unit: '次/分', required: true },
          { name: 'consciousness', label: '意识状态', type: 'string', required: true },
          { name: 'supplemental_oxygen', label: '吸氧', type: 'boolean', required: true },
        ],
        thresholds: [
          { range: [0, 2], label: '低风险', severity: 'normal' },
          { range: [3, 4], label: '中风险', severity: 'moderate' },
          { range: [5, 6], label: '高风险', severity: 'high' },
          { range: [7, 20], label: '极高风险', severity: 'critical' },
        ],
      },
    ],
  },
  {
    name: 'MEWS',
    variants: [
      {
        id: 'mews',
        name: 'MEWS',
        score_system: 'MEWS',
        version: 'v1.0.0',
        description: 'Modified Early Warning Score，改良早期预警评分。',
        inputs: [
          { name: 'respiratory_rate', label: '呼吸频率', type: 'number', unit: '次/分', required: true },
          { name: 'temperature', label: '体温', type: 'number', unit: '°C', required: true },
          { name: 'systolic_bp', label: '收缩压', type: 'number', unit: 'mmHg', required: true },
          { name: 'heart_rate', label: '心率', type: 'number', unit: '次/分', required: true },
          { name: 'consciousness', label: '意识状态', type: 'string', required: true },
        ],
        thresholds: [
          { range: [0, 2], label: '正常', severity: 'normal' },
          { range: [3, 4], label: '警惕', severity: 'moderate' },
          { range: [5, 20], label: '危急', severity: 'critical' },
        ],
      },
    ],
  },
  {
    name: 'GCS',
    variants: [
      {
        id: 'gcs',
        name: 'GCS',
        score_system: 'GCS',
        version: 'v1.0.0',
        description: 'Glasgow Coma Scale，格拉斯哥昏迷评分。',
        inputs: [
          { name: 'eye_opening', label: '睁眼反应', type: 'number', required: true },
          { name: 'verbal_response', label: '言语反应', type: 'number', required: true },
          { name: 'motor_response', label: '运动反应', type: 'number', required: true },
        ],
        thresholds: [
          { range: [3, 8], label: '重度昏迷', severity: 'critical' },
          { range: [9, 12], label: '中度昏迷', severity: 'moderate' },
          { range: [13, 15], label: '轻度/正常', severity: 'normal' },
        ],
      },
    ],
  },
]

// 模拟测试结果
const mockResult: ScoringResult = {
  score_system: 'SOFA',
  score_variant: 'classic_1996',
  rule_id: 'sofa-classic',
  rule_version: 'v1.0.0',
  evaluation_time: '2024-03-15T10:30:00Z',
  component_scores: {
    respiratory: 3,
    coagulation: 1,
    liver: 0,
    cardiovascular: 2,
    cns: 1,
    renal: 2,
  },
  total_score: 9,
  missing_inputs: ['urine_output'],
  evidence: [
    { input: 'pao2_fio2', value: 180, source: '血气分析' },
    { input: 'platelets', value: 120, source: '血常规' },
    { input: 'bilirubin', value: 1.2, source: '肝功能' },
    { input: 'map', value: 65, source: '有创血压' },
    { input: 'dopamine', value: 5, source: '医嘱' },
    { input: 'gcs', value: 12, source: '护理评估' },
    { input: 'creatinine', value: 2.1, source: '肾功能' },
  ],
  input_snapshot_hash: 'a1b2c3d4e5f6',
}

// 选择评分规则
function selectRule(rule: ScoringRule) {
  selectedRule.value = rule
  testResult.value = null
}

// 运行测试
async function runTest() {
  if (!selectedRule.value) return

  testRunning.value = true
  testResult.value = null

  try {
    const { data } = await evaluateScore({
      patient_id: 'test-patient',
      score_system: selectedRule.value.score_system,
      score_variant: selectedRule.value.score_variant,
    })
    testResult.value = data
  } catch {
    // 规则核心不可用时使用模拟数据
    await new Promise((resolve) => setTimeout(resolve, 800))
    testResult.value = {
      ...mockResult,
      score_system: selectedRule.value.score_system,
      score_variant: selectedRule.value.score_variant,
      rule_id: selectedRule.value.id,
      rule_version: selectedRule.value.version,
    }
  } finally {
    testRunning.value = false
  }
}

// 初始化
onMounted(async () => {
  try {
    const { data } = await getScoringSystems()
    if (data.systems?.length) {
      scoreGroups.value = data.systems.map((sys) => ({
        name: sys.name,
        variants: sys.variants?.map((v) => ({
          id: v.id,
          name: v.name,
          score_system: sys.name,
          score_variant: v.id,
          version: v.version || 'v1.0.0',
          inputs: [],
        })) || [],
      }))
    }
  } catch {
    scoreGroups.value = mockGroups
  }
})
</script>

<style scoped>
.scores-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 三栏布局 */
.content-grid {
  display: grid;
  grid-template-columns: 200px 1fr 360px;
  gap: 16px;
  min-height: 600px;
}

/* 面板 */
.panel {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.panel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.panel__badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--color-primary, #2563EB);
}

.panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

/* 评分树 */
.score-tree {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.score-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.group-header {
  padding: 4px 8px;
}

.group-name {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-secondary, #667085);
}

.tree-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.tree-item:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.tree-item--active {
  background: rgba(37, 99, 235, 0.08);
  color: var(--color-primary, #2563EB);
}

.tree-item__name {
  font-size: 13px;
  font-weight: 500;
}

.tree-item__version {
  font-size: 11px;
  color: var(--color-text-secondary, #667085);
  font-family: 'SF Mono', 'Consolas', monospace;
}

.tree-item--active .tree-item__version {
  color: var(--color-primary, #2563EB);
}

/* 规则详情 */
.rule-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0f0;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.detail-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

.detail-value--code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
}

.detail-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
  line-height: 1.6;
  margin: 0;
  padding: 10px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: 6px;
}

/* 输入项表格 */
.input-table {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: 6px;
  overflow: hidden;
}

.input-header,
.input-row {
  display: grid;
  grid-template-columns: 1fr 1fr 80px 80px 50px;
  gap: 8px;
  padding: 8px 12px;
}

.input-header {
  background: var(--color-bg-surface-secondary, #F9FAFB);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary, #667085);
  text-transform: uppercase;
}

.input-row {
  font-size: 12px;
  border-top: 1px solid var(--color-border, #E3E7EC);
}

.input-row:first-of-type {
  border-top: none;
}

.input-col--code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 11px;
}

.required-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.required-dot--yes {
  background: var(--color-danger, #D92D20);
}

.required-dot--no {
  background: var(--color-border, #E3E7EC);
}

/* 阈值表 */
.threshold-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.threshold-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
}

.threshold-range {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
  min-width: 60px;
}

.threshold-label {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
}

.threshold-severity {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 3px;
}

.threshold-severity--normal {
  color: var(--color-success, #16845B);
  background: rgba(22, 132, 91, 0.1);
}

.threshold-severity--mild {
  color: var(--color-info, #2563EB);
  background: rgba(37, 99, 235, 0.1);
}

.threshold-severity--moderate {
  color: var(--color-warning, #B54708);
  background: rgba(181, 71, 8, 0.1);
}

.threshold-severity--high,
.threshold-severity--critical,
.threshold-severity--severe {
  color: var(--color-danger, #D92D20);
  background: rgba(217, 45, 32, 0.1);
}

/* 测试结果 */
.test-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-total {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.05), rgba(37, 99, 235, 0.1));
  border-radius: 8px;
  border: 1px solid rgba(37, 99, 235, 0.15);
}

.result-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.result-score {
  font-size: 36px;
  font-weight: 700;
  color: var(--color-primary, #2563EB);
  line-height: 1;
}

.result-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 分项得分 */
.component-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}

.component-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-radius: 4px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
}

.component-name {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.component-score {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

/* 元数据 */
.meta-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta-label {
  font-size: 11px;
  font-family: 'SF Mono', 'Consolas', monospace;
  color: var(--color-text-secondary, #667085);
  min-width: 130px;
}

.meta-value {
  font-size: 12px;
  color: var(--color-text-primary, #18212B);
}

.meta-value--code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 11px;
  padding: 1px 4px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border-radius: 3px;
}

.meta-value--small {
  font-size: 10px;
  word-break: break-all;
}

/* 缺失输入 */
.missing-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.missing-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(181, 71, 8, 0.1);
  color: var(--color-warning, #B54708);
  font-family: 'SF Mono', 'Consolas', monospace;
}

/* 证据列表 */
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.evidence-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
}

.evidence-input {
  font-size: 11px;
  font-family: 'SF Mono', 'Consolas', monospace;
  color: var(--color-text-secondary, #667085);
  min-width: 100px;
}

.evidence-value {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

.evidence-source {
  font-size: 10px;
  color: var(--color-text-tertiary, #98A2B3);
}

/* 按钮 */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.btn--sm {
  padding: 3px 8px;
  font-size: 11px;
}

.btn--outline {
  background: #fff;
  color: var(--color-text-primary, #18212B);
  border-color: var(--color-border, #D0D5DD);
}

.btn--outline:hover {
  background: var(--color-bg-surface-secondary, #F9FAFB);
}

/* 加载和空状态 */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  text-align: center;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border, #E3E7EC);
  border-top-color: var(--color-primary, #2563EB);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 32px;
  opacity: 0.6;
}

.empty-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

/* 响应式 */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr 300px;
  }

  .panel--left {
    display: none;
  }
}

@media (max-width: 768px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .panel--right {
    display: none;
  }
}
</style>
