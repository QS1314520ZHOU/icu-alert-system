<template>
  <div class="evidence-chain">
    <div v-if="loading" class="chain-loading">
      <a-spin tip="加载证据链..." />
    </div>

    <template v-else>
      <!-- 证据完整度 -->
      <div v-if="completeness" class="completeness-bar">
        <div class="completeness-header">
          <span class="completeness-title">证据完整度</span>
          <span class="completeness-score">{{ completenessScore }}%</span>
        </div>
        <a-progress
          :percent="completenessScore"
          :stroke-color="completenessColor"
          :show-info="false"
          size="small"
        />
        <div class="completeness-detail">
          <span v-for="(item, idx) in completenessList" :key="idx" class="completeness-item">
            <span class="dot" :style="{ background: item.color }" />
            {{ item.label }}: {{ item.value }}
          </span>
        </div>
      </div>

      <!-- 筛选 -->
      <div class="chain-filter">
        <a-select
          v-model:value="filterType"
          placeholder="证据类型"
          allow-clear
          style="width: 150px"
          @change="loadEvidence"
        >
          <a-select-option v-for="t in evidenceTypes" :key="t.value" :value="t.value">
            {{ t.label }}
          </a-select-option>
        </a-select>
        <a-select
          v-model:value="filterMatched"
          placeholder="匹配状态"
          allow-clear
          style="width: 120px"
          @change="loadEvidence"
        >
          <a-select-option :value="true">已匹配</a-select-option>
          <a-select-option :value="false">未匹配</a-select-option>
        </a-select>
      </div>

      <!-- 证据链节点 -->
      <div v-if="evidenceList.length === 0" class="chain-empty">
        <a-empty description="暂无证据数据" />
      </div>

      <div v-else class="chain-nodes">
        <div v-for="evidence in evidenceList" :key="evidence.id" class="chain-node">
          <!-- 连接线 -->
          <div class="node-connector">
            <div class="connector-line" />
            <div class="connector-dot" :class="getNodeStatusClass(evidence)" />
          </div>

          <!-- 节点内容 -->
          <div class="node-content">
            <!-- 阶段标签 -->
            <div class="node-stage">
              <a-tag :color="getStageColor(evidence)" size="small">
                {{ getStageLabel(evidence) }}
              </a-tag>
              <span class="node-time">{{ formatTime(evidence.observed_at) }}</span>
            </div>

            <!-- 数据链路 -->
            <div class="chain-pipeline">
              <!-- 原始数据 -->
              <div class="pipeline-step">
                <span class="step-label">原始数据</span>
                <span class="step-value">
                  {{ evidence.raw_value ?? '-' }}
                  <span v-if="evidence.raw_unit" class="step-unit">{{ evidence.raw_unit }}</span>
                </span>
                <span class="step-source">{{ evidence.source_collection || '-' }}</span>
              </div>

              <span class="pipeline-arrow">→</span>

              <!-- 标准化 -->
              <div class="pipeline-step">
                <span class="step-label">标准化</span>
                <span class="step-value">
                  {{ evidence.normalized_value ?? '-' }}
                  <span v-if="evidence.normalized_unit" class="step-unit">{{ evidence.normalized_unit }}</span>
                </span>
              </div>

              <span class="pipeline-arrow">→</span>

              <!-- 规则判断 -->
              <div class="pipeline-step">
                <span class="step-label">规则判断</span>
                <span class="step-value">
                  <span v-if="evidence.threshold !== null && evidence.threshold !== undefined">
                    {{ evidence.threshold_operator || '>' }} {{ evidence.threshold }}
                  </span>
                  <span v-else>-</span>
                </span>
                <a-tag
                  :color="evidence.matched ? '#52c41a' : '#d9d9d9'"
                  size="small"
                >
                  {{ evidence.matched ? '匹配' : '不匹配' }}
                </a-tag>
              </div>

              <span class="pipeline-arrow">→</span>

              <!-- 置信度 -->
              <div class="pipeline-step">
                <span class="step-label">置信度</span>
                <span class="step-value" :class="getConfidenceClass(evidence.confidence)">
                  {{ (evidence.confidence * 100).toFixed(0) }}%
                </span>
              </div>
            </div>

            <!-- 说明 -->
            <div v-if="evidence.explanation" class="node-explanation">
              {{ evidence.explanation }}
            </div>

            <!-- 质量标记 -->
            <div v-if="evidence.quality_flags && evidence.quality_flags.length > 0" class="node-flags">
              <a-tag
                v-for="flag in evidence.quality_flags"
                :key="flag"
                :color="getFlagColor(flag)"
                size="small"
              >
                {{ getFlagLabel(flag) }}
              </a-tag>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Empty as AEmpty, Progress as AProgress, Select as ASelect, SelectOption as ASelectOption, Spin as ASpin, Tag as ATag } from 'ant-design-vue'
import { ref, computed, onMounted, watch } from 'vue'
import { getCaseEvidence, getEvidenceCompleteness } from '@/api/diseaseCenter'
import type { CaseEvidence, EvidenceCompleteness } from '@/api/diseaseCenter'

const props = defineProps<{
  caseId: string
}>()

const loading = ref(false)
const evidenceList = ref<CaseEvidence[]>([])
const completeness = ref<EvidenceCompleteness | null>(null)
const filterType = ref<string | undefined>(undefined)
// antd Select 的 SelectValue 不接受 boolean，模板 v-model:value 需要 any 兼容
const filterMatched = ref<any>(undefined)

const evidenceTypes = [
  { value: 'vital_sign', label: '生命体征' },
  { value: 'lab_result', label: '检验结果' },
  { value: 'drug', label: '药物' },
  { value: 'assessment', label: '评估量表' },
  { value: 'imaging', label: '影像' },
  { value: 'clinical_note', label: '临床文书' },
  { value: 'diagnosis', label: '诊断' },
  { value: 'procedure', label: '操作' },
  { value: 'device', label: '设备数据' },
  { value: 'nursing', label: '护理记录' },
]

const completenessScore = computed(() => {
  const ratio = completeness.value?.completeness_ratio
  if (ratio === null || ratio === undefined) return 0
  // 后端返回 0~1 比值，转成百分比整数
  return Math.round(ratio * 100)
})

const completenessList = computed(() => {
  if (!completeness.value?.by_type) return []
  return Object.entries(completeness.value.by_type).map(([k, v]) => ({
    label: getEvidenceTypeLabel(k),
    value: `${v.matched}/${v.total}`,
    color: v.total > 0 ? 'var(--color-success)' : 'var(--color-text-tertiary)',
  }))
})

const completenessColor = computed(() => {
  const s = completenessScore.value
  if (s >= 80) return 'var(--color-success)'
  if (s >= 50) return 'var(--color-warning)'
  return '#D92D20'
})

// --- helpers ---
function getEvidenceTypeLabel(type: string) {
  const map: Record<string, string> = {
    vital_sign: '生命体征',
    lab_result: '检验结果',
    drug: '药物',
    assessment: '评估量表',
    imaging: '影像',
    clinical_note: '临床文书',
    diagnosis: '诊断',
    procedure: '操作',
    device: '设备数据',
    nursing: '护理记录',
  }
  return map[type] || type
}

function getStageLabel(evidence: CaseEvidence) {
  if (evidence.matched) return '已匹配规则'
  if (evidence.normalized_value !== null) return '已标准化'
  return '原始数据'
}

function getStageColor(evidence: CaseEvidence) {
  if (evidence.matched) return '#52c41a'
  if (evidence.normalized_value !== null) return '#1677ff'
  return '#d9d9d9'
}

function getNodeStatusClass(evidence: CaseEvidence) {
  if (evidence.matched) return 'dot-matched'
  if (evidence.quality_flags?.includes('missing')) return 'dot-missing'
  return 'dot-normal'
}

function getConfidenceClass(confidence: number) {
  if (confidence >= 0.8) return 'confidence-high'
  if (confidence >= 0.5) return 'confidence-medium'
  return 'confidence-low'
}

function getFlagColor(flag: string) {
  const map: Record<string, string> = {
    normal: '#d9d9d9',
    missing: '#ff4d4f',
    stale: '#faad14',
    conflict: '#ff4d4f',
    low_confidence: '#faad14',
    unit_mismatch: '#faad14',
    outlier: '#faad14',
    manual_override: '#1677ff',
  }
  return map[flag] || '#d9d9d9'
}

function getFlagLabel(flag: string) {
  const map: Record<string, string> = {
    normal: '正常',
    missing: '缺失',
    stale: '过期',
    conflict: '冲突',
    low_confidence: '低置信',
    unit_mismatch: '单位不匹配',
    outlier: '异常值',
    manual_override: '人工覆盖',
  }
  return map[flag] || flag
}

function formatTime(t?: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

// --- data loading ---
async function loadEvidence() {
  loading.value = true
  try {
    evidenceList.value = (await getCaseEvidence(props.caseId, {
      evidence_type: filterType.value,
      matched: filterMatched.value,
    })).data
  } catch {
    evidenceList.value = []
  } finally {
    loading.value = false
  }
}

async function loadCompleteness() {
  try {
    completeness.value = (await getEvidenceCompleteness(props.caseId)).data
  } catch {
    completeness.value = null
  }
}

watch(() => props.caseId, () => {
  if (props.caseId) {
    loadEvidence()
    loadCompleteness()
  }
}, { immediate: true })

onMounted(() => {
  if (props.caseId) {
    loadEvidence()
    loadCompleteness()
  }
})
</script>

<style scoped>.evidence-chain { display: flex; flex-direction: column; gap: 16px }
.chain-loading { display: flex; justify-content: center; padding: 40px 0 }

/* Completeness */ .completeness-bar { padding: 12px 16px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px) }
.completeness-header { display: flex; justify-content: space-between; margin-bottom: 8px }
.completeness-title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }
.completeness-score { font-size: var(--text-body, 13px); font-weight: 700; color: var(--color-primary, #2F6FED) }
.completeness-detail { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px }
.completeness-item { display: flex; align-items: center; gap: 4px; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.dot { width: 6px; height: 6px; border-radius: 50% }

/* Filter */ .chain-filter { display: flex; gap: 8px }

/* Chain Nodes */ .chain-nodes { display: flex; flex-direction: column; gap: 0 }
.chain-node { display: flex; gap: 12px; min-height: 80px }
.node-connector { display: flex; flex-direction: column; align-items: center; width: 20px; flex-shrink: 0 }
.connector-line { flex: 1; width: 2px; background: var(--color-border, #E5E7EB) }
.connector-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--color-border, #E5E7EB); flex-shrink: 0 }
.dot-matched { background: var(--color-success, #16845B) }
.dot-missing { background: var(--color-danger, #D92D20) }
.dot-normal { background: var(--color-primary, #2F6FED) }
.node-content { flex: 1; padding: 8px 12px; background: var(--color-bg-surface, #FFFFFF); border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); margin-bottom: 8px }
.node-stage { display: flex; align-items: center; gap: 8px; margin-bottom: 8px }
.node-time { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }

/* Pipeline */ .chain-pipeline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 0 }
.pipeline-step { display: flex; flex-direction: column; gap: 2px; min-width: 80px }
.step-label { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.step-value { font-size: var(--text-body, 13px); font-weight: 500; color: var(--color-text-primary, #111827) }
.step-unit { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); font-weight: 400 }
.step-source { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.pipeline-arrow { color: var(--color-text-tertiary, #9CA3AF); font-size: var(--text-body, 13px) }

/* Confidence */ .confidence-high { color: var(--color-success, #16845B) }
.confidence-medium { color: var(--color-warning, #B54708) }
.confidence-low { color: var(--color-danger, #D92D20) }

/* Explanation */ .node-explanation { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); padding: 6px 0; border-top: 1px dashed var(--color-border, #E5E7EB); margin-top: 6px }

/* Quality flags */ .node-flags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px }

</style>
