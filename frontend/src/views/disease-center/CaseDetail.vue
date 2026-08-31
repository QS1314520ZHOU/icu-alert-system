<template>
  <div class="case-detail-page">
    <a-page-header
      :title="`病例详情 - ${caseData?.patient_id || ''}`"
      :sub-title="caseData?.disease_name || caseData?.disease_code || ''"
      @back="goBack"
    >
      <template #extra>
        <a-space>
          <a-tag :color="statusColor">{{ statusLabel }}</a-tag>
          <a-button
            v-if="caseData?.status === 'pending_review'"
            type="primary"
            size="small"
            @click="handleConfirm"
          >
            确认诊断
          </a-button>
          <a-button
            v-if="caseData?.status === 'pending_review'"
            size="small"
            @click="handleExclude"
          >
            排除
          </a-button>
        </a-space>
      </template>
    </a-page-header>

    <a-spin :spinning="loading">
      <div v-if="caseData" class="detail-content">
        <!-- 基本信息 -->
        <div class="info-grid">
          <div class="info-card">
            <span class="info-label">患者 ID</span>
            <span class="info-value">{{ caseData.patient_id }}</span>
          </div>
          <div class="info-card">
            <span class="info-label">关联病种</span>
            <span class="info-value">{{ caseData.disease_name || caseData.disease_code }}</span>
          </div>
          <div class="info-card">
            <span class="info-label">当前状态</span>
            <a-tag :color="statusColor">{{ statusLabel }}</a-tag>
          </div>
          <div class="info-card">
            <span class="info-label">风险等级</span>
            <span :class="riskClass">{{ riskLabel }}</span>
          </div>
          <div class="info-card">
            <span class="info-label">筛查时间</span>
            <span class="info-value">{{ formatTime(caseData.first_detected_at) }}</span>
          </div>
          <div class="info-card">
            <span class="info-label">确诊时间</span>
            <span class="info-value">{{ formatTime(caseData.confirmed_at) }}</span>
          </div>
        </div>

        <!-- Tabs -->
        <a-tabs v-model:activeKey="activeTab" type="card">
          <a-tab-pane key="evidence" tab="证据链">
            <EvidenceChain :case-id="caseId" />
          </a-tab-pane>

          <a-tab-pane key="timeline" tab="时间线">
            <CaseTimeline :case-id="caseId" />
          </a-tab-pane>

          <a-tab-pane key="pathway" tab="临床路径">
            <PathwayExecution :case-id="caseId" />
          </a-tab-pane>

          <a-tab-pane key="quality" tab="质量检查">
            <CaseQuality :case-id="caseId" />
          </a-tab-pane>
        </a-tabs>
      </div>

      <a-empty v-else-if="!loading" description="病例不存在" />
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { getCaseDetail, confirmCase, excludeCase } from '@/api/diseaseCenter'
import type { DiseaseCase } from '@/api/diseaseCenter'
import EvidenceChain from './components/EvidenceChain.vue'
import CaseTimeline from './components/CaseTimeline.vue'
import PathwayExecution from './components/PathwayExecution.vue'
import CaseQuality from './components/CaseQuality.vue'

const route = useRoute()
const router = useRouter()

const caseId = computed(() => route.params.caseId as string)
const caseData = ref<DiseaseCase | null>(null)
const loading = ref(false)
const activeTab = ref('evidence')

const statusColor = computed(() => {
  const s = caseData.value?.status
  const map: Record<string, string> = {
    screening: 'default',
    screen_positive: 'orange',
    pending_review: 'var(--color-primary-light)',
    confirmed: 'var(--color-success-light)',
    excluded: 'default',
    pathway_active: 'var(--color-primary)',
    completed: 'var(--color-success)',
  }
  return map[s || ''] || 'default'
})

const statusLabel = computed(() => {
  const s = caseData.value?.status
  const map: Record<string, string> = {
    screening: '筛查中',
    screen_positive: '筛查阳性',
    pending_review: '待审核',
    confirmed: '已确诊',
    excluded: '已排除',
    pathway_active: '路径执行中',
    completed: '已完成',
  }
  return map[s || ''] || s || '未知'
})

const riskClass = computed(() => {
  const level = caseData.value?.risk_level
  if (level === 'high' || level === 'critical') return 'risk-high'
  if (level === 'medium') return 'risk-medium'
  return 'risk-low'
})

const riskLabel = computed(() => {
  const level = caseData.value?.risk_level
  const map: Record<string, string> = {
    critical: '危急',
    high: '高风险',
    medium: '中风险',
    low: '低风险',
    none: '无风险',
  }
  return map[level || ''] || level || '-'
})

function formatTime(t?: string | null) {
  return t ? new Date(t).toLocaleString('zh-CN') : '-'
}

function goBack() {
  router.push({ name: 'disease-center-cases' })
}

async function loadCase() {
  loading.value = true
  try {
    caseData.value = await getCaseDetail(caseId.value)
  } catch (err: any) {
    message.error('加载病例失败: ' + (err.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function handleConfirm() {
  try {
    await confirmCase(caseId.value, {
      operator_id: 'current_user',
      reason: '病例详情页确认',
    })
    message.success('已确认')
    loadCase()
  } catch (err: any) {
    message.error('确认失败: ' + (err.message || '未知错误'))
  }
}

async function handleExclude() {
  try {
    await excludeCase(caseId.value, {
      operator_id: 'current_user',
      reason: '病例详情页排除',
    })
    message.success('已排除')
    loadCase()
  } catch (err: any) {
    message.error('排除失败: ' + (err.message || '未知错误'))
  }
}

onMounted(() => {
  loadCase()
})
</script>

<style scoped>
.case-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  padding: 16px;
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 12px);
}

.info-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.info-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

.risk-high {
  color: var(--color-error, #D92D20);
  font-weight: 600;
}

.risk-medium {
  color: var(--color-warning, #DC6803);
  font-weight: 500;
}

.risk-low {
  color: var(--color-success, #16845B);
}
</style>
