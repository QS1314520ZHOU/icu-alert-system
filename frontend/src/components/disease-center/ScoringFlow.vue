<template>
  <div class="scoring-flow">
    <div class="flow-header">
      <h3 class="flow-title">评分流程</h3>
      <div class="flow-controls">
        <button class="btn btn--sm btn--outline" @click="resetFlow">重置</button>
        <button class="btn btn--sm btn--primary" @click="runFlow">运行评分</button>
      </div>
    </div>

    <div class="flow-container">
      <!-- 输入阶段 -->
      <div class="flow-stage">
        <div class="stage-header">
          <span class="stage-number">1</span>
          <span class="stage-title">数据输入</span>
        </div>
        <div class="stage-content">
          <div v-for="input in inputs" :key="input.code" class="input-item">
            <div class="input-label">{{ input.display_name }}</div>
            <div class="input-field">
              <input
                v-model="input.value"
                type="number"
                class="form-input"
                :placeholder="`输入 ${input.display_name}`"
              />
              <span v-if="input.unit" class="input-unit">{{ input.unit }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 处理阶段 -->
      <div class="flow-stage">
        <div class="stage-header">
          <span class="stage-number">2</span>
          <span class="stage-title">评分计算</span>
        </div>
        <div class="stage-content">
          <div v-if="processing" class="processing-state">
            <div class="spinner"></div>
            <span>计算中...</span>
          </div>
          <div v-else-if="result" class="calculation-result">
            <div class="result-total">
              <span class="total-label">总分</span>
              <span class="total-value">{{ result.total_score }}</span>
            </div>
            <div class="result-components">
              <div v-for="(score, name) in result.component_scores" :key="name" class="component-item">
                <span class="component-name">{{ name }}</span>
                <span class="component-score">{{ score }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">
            <span>点击"运行评分"开始计算</span>
          </div>
        </div>
      </div>

      <!-- 输出阶段 -->
      <div class="flow-stage">
        <div class="stage-header">
          <span class="stage-number">3</span>
          <span class="stage-title">结果解读</span>
        </div>
        <div class="stage-content">
          <div v-if="result" class="interpretation">
            <div class="severity-indicator" :class="`severity--${severity}`">
              <span class="severity-label">{{ severityLabel }}</span>
            </div>
            <div class="interpretation-text">
              {{ interpretation }}
            </div>
            <div v-if="result.missing_inputs?.length" class="missing-inputs">
              <span class="missing-label">缺失输入:</span>
              <span v-for="m in result.missing_inputs" :key="m" class="missing-tag">{{ m }}</span>
            </div>
          </div>
          <div v-else class="empty-state">
            <span>等待评分结果</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface ScoringInput {
  code: string
  display_name: string
  value: number | null
  unit?: string
}

interface ScoringResult {
  total_score: number
  component_scores: Record<string, number>
  missing_inputs: string[]
  thresholds?: Array<{
    range: [number, number]
    label: string
    severity?: string
  }>
}

const props = defineProps<{
  inputs: ScoringInput[]
  result: ScoringResult | null
  processing: boolean
}>()

const emit = defineEmits<{
  (e: 'update:inputs', inputs: ScoringInput[]): void
  (e: 'run'): void
  (e: 'reset'): void
}>()

const severity = computed(() => {
  if (!props.result?.thresholds) return 'unknown'
  const score = props.result.total_score
  for (const threshold of props.result.thresholds) {
    if (score >= threshold.range[0] && score <= threshold.range[1]) {
      return threshold.severity || 'unknown'
    }
  }
  return 'unknown'
})

const severityLabel = computed(() => {
  const labels: Record<string, string> = {
    low: '低风险',
    medium: '中风险',
    high: '高风险',
    critical: '危重',
    unknown: '未知'
  }
  return labels[severity.value] || '未知'
})

const interpretation = computed(() => {
  if (!props.result) return ''
  // 简化的解读逻辑
  const score = props.result.total_score
  if (score === 0) return '评分正常，无需特殊干预'
  if (score <= 3) return '轻度风险，建议密切观察'
  if (score <= 6) return '中度风险，建议加强监护'
  if (score <= 9) return '高风险，建议立即干预'
  return '危重状态，需要紧急处理'
})

function runFlow() {
  emit('run')
}

function resetFlow() {
  emit('reset')
}
</script>

<style scoped>
.scoring-flow {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 16px;
}

.flow-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.flow-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.flow-controls {
  display: flex;
  gap: 8px;
}

.flow-container {
  display: flex;
  gap: 16px;
}

.flow-stage {
  flex: 1;
  background: #f8f9fa;
  border-radius: 6px;
  overflow: hidden;
}

.stage-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #e6f7ff;
  border-bottom: 1px solid #91d5ff;
}

.stage-number {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1890ff;
  color: #fff;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
}

.stage-title {
  font-weight: 600;
  font-size: 14px;
}

.stage-content {
  padding: 16px;
}

.input-item {
  margin-bottom: 12px;
}

.input-label {
  font-size: 12px;
  font-weight: 500;
  color: #666;
  margin-bottom: 4px;
}

.input-field {
  display: flex;
  gap: 8px;
}

.form-input {
  flex: 1;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}

.input-unit {
  font-size: 12px;
  color: #999;
  line-height: 32px;
}

.processing-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: #666;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #ddd;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.calculation-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-total {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  background: #fff;
  border-radius: 4px;
}

.total-label {
  font-size: 12px;
  color: #666;
}

.total-value {
  font-size: 36px;
  font-weight: 700;
  color: #1890ff;
}

.result-components {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.component-item {
  display: flex;
  justify-content: space-between;
  padding: 8px;
  background: #fff;
  border-radius: 4px;
}

.component-name {
  font-size: 13px;
  color: #333;
}

.component-score {
  font-weight: 600;
  color: #1890ff;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #999;
  font-size: 13px;
}

.interpretation {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.severity-indicator {
  padding: 12px;
  border-radius: 4px;
  text-align: center;
}

.severity--low {
  background: #f6ffed;
  color: #52c41a;
}

.severity--medium {
  background: #fffbe6;
  color: #faad14;
}

.severity--high {
  background: #fff2f0;
  color: #ff4d4f;
}

.severity--critical {
  background: #ff4d4f;
  color: #fff;
}

.severity-label {
  font-weight: 600;
  font-size: 14px;
}

.interpretation-text {
  font-size: 13px;
  color: #333;
  line-height: 1.5;
}

.missing-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.missing-label {
  font-size: 12px;
  color: #666;
}

.missing-tag {
  padding: 4px 8px;
  background: #fff2f0;
  color: #ff4d4f;
  border-radius: 4px;
  font-size: 12px;
}
</style>
