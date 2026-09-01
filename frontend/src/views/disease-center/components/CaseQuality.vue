<template>
  <div class="case-quality">
    <div v-if="loading" class="quality-loading">
      <a-spin tip="加载质量数据..." />
    </div>

    <template v-else>
      <div v-if="!qualityData" class="quality-empty">
        <a-empty description="暂无质量数据" />
      </div>

      <template v-else>
        <!-- 质量概览 -->
        <div class="quality-overview">
          <div class="quality-card">
            <span class="quality-card-label">证据完整度</span>
            <span class="quality-card-value" :class="getScoreClass(qualityData.evidence_completeness?.completeness)">
              {{ qualityData.evidence_completeness?.completeness ?? '-' }}%
            </span>
          </div>
          <div class="quality-card">
            <span class="quality-card-label">确认操作数</span>
            <span class="quality-card-value">{{ qualityData.confirmation_count ?? 0 }}</span>
          </div>
          <div class="quality-card">
            <span class="quality-card-label">风险等级</span>
            <a-tag :color="getRiskColor(qualityData.risk_level)">
              {{ getRiskLabel(qualityData.risk_level) }}
            </a-tag>
          </div>
          <div class="quality-card">
            <span class="quality-card-label">置信度</span>
            <span class="quality-card-value" :class="getConfidenceClass(qualityData.confidence)">
              {{ qualityData.confidence != null ? (qualityData.confidence * 100).toFixed(0) + '%' : '-' }}
            </span>
          </div>
        </div>

        <!-- 证据类型分布 -->
        <div v-if="typeDistribution.length > 0" class="quality-section">
          <h4 class="section-title">证据类型分布</h4>
          <div class="type-grid">
            <div v-for="item in typeDistribution" :key="item.type" class="type-item">
              <span class="type-label">{{ item.label }}</span>
              <span class="type-count">{{ item.count }}</span>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getCaseQuality } from '@/api/diseaseCenter'

const props = defineProps<{
  caseId: string
}>()

const loading = ref(false)
const qualityData = ref<Record<string, any> | null>(null)

const typeDistribution = computed(() => {
  if (!qualityData.value?.evidence_completeness?.by_type) return []
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
  return Object.entries(qualityData.value.evidence_completeness.by_type).map(([k, v]) => ({
    type: k,
    label: map[k] || k,
    count: v as number,
  }))
})

function getScoreClass(score?: number | null) {
  if (score == null) return ''
  if (score >= 80) return 'score-high'
  if (score >= 50) return 'score-medium'
  return 'score-low'
}

function getRiskColor(risk?: string) {
  const map: Record<string, string> = {
    critical: 'var(--color-error)',
    high: 'var(--color-error-light)',
    medium: 'var(--color-warning-light)',
    low: 'var(--color-success-light)',
    none: 'default',
  }
  return map[risk || ''] || 'default'
}

function getRiskLabel(risk?: string) {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高风险',
    medium: '中风险',
    low: '低风险',
    none: '无风险',
  }
  return map[risk || ''] || risk || '-'
}

function getConfidenceClass(confidence?: number | null) {
  if (confidence == null) return ''
  if (confidence >= 0.8) return 'score-high'
  if (confidence >= 0.5) return 'score-medium'
  return 'score-low'
}

async function loadQuality() {
  loading.value = true
  try {
    qualityData.value = (await getCaseQuality(props.caseId)).data
  } catch {
    qualityData.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.caseId, () => {
  if (props.caseId) loadQuality()
}, { immediate: true })

onMounted(() => {
  if (props.caseId) loadQuality()
})
</script>

<style scoped>
.case-quality {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.quality-loading {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

/* Overview */
.quality-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.quality-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: var(--radius-md, 8px);
}

.quality-card-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.quality-card-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}

.score-high {
  color: var(--color-success, #16845B);
}

.score-medium {
  color: var(--color-warning, #DC6803);
}

.score-low {
  color: var(--color-error, #D92D20);
}

/* Type distribution */
.quality-section {
  padding: 12px 16px;
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 8px);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0 0 12px;
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.type-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: var(--radius-sm, 6px);
}

.type-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.type-count {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}
</style>
