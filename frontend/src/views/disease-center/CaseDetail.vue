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
            确认纳入
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
            <span class="info-label">临床确认时间</span>
            <span class="info-value">{{ formatTime(caseData.confirmed_at) }}</span>
          </div>
        </div>

        <!-- AI 摘要 -->
        <div class="ai-summary-section">
          <div class="ai-summary-header">
            <span class="ai-summary-title">AI 病例分析</span>
            <a-button
              size="small"
              :loading="aiLoading"
              @click="generateAiSummary"
            >
              {{ aiSummary ? '重新分析' : '生成分析' }}
            </a-button>
          </div>
          <div v-if="aiSummary" class="ai-summary-content">
            <div class="ai-summary-text">{{ aiSummary.summary }}</div>
            <div v-if="aiSummary.core_problems?.length" class="ai-section">
              <div class="ai-section-title">核心问题</div>
              <ul>
                <li v-for="(problem, idx) in aiSummary.core_problems" :key="idx">{{ problem }}</li>
              </ul>
            </div>
            <div v-if="aiSummary.risk_assessment" class="ai-section">
              <div class="ai-section-title">风险评估</div>
              <a-tag :color="getRiskColor(aiSummary.risk_assessment)">{{ aiSummary.risk_assessment }}</a-tag>
            </div>
            <div v-if="aiSummary.key_evidence?.length" class="ai-section">
              <div class="ai-section-title">关键证据</div>
              <ul>
                <li v-for="(ev, idx) in aiSummary.key_evidence" :key="idx">{{ ev }}</li>
              </ul>
            </div>
            <div v-if="aiSummary.recommendations?.length" class="ai-section">
              <div class="ai-section-title">建议</div>
              <ul>
                <li v-for="(rec, idx) in aiSummary.recommendations" :key="idx">{{ rec }}</li>
              </ul>
            </div>
            <div class="ai-meta">
              <span>置信度: {{ (aiSummary.confidence * 100).toFixed(0) }}%</span>
              <span v-if="aiModel">模型: {{ aiModel }}</span>
            </div>
          </div>
          <div v-else-if="aiError" class="ai-error">{{ aiError }}</div>
          <div v-else-if="!aiLoading" class="ai-placeholder">点击"生成分析"获取AI辅助诊断建议</div>
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
import { getCaseDetail, confirmCase, excludeCase, getCaseAiSummary } from '@/api/diseaseCenter'
import type { DiseaseCase, CaseAiSummary } from '@/api/diseaseCenter'
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

// AI 摘要状态
const aiLoading = ref(false)
const aiSummary = ref<CaseAiSummary['data'] | null>(null)
const aiModel = ref<string>('')
const aiError = ref<string>('')

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
    reconsideration_pending: 'orange',
    reopened: 'orange',
  }
  return map[s || ''] || 'default'
})

const statusLabel = computed(() => {
  const s = caseData.value?.status
  const map: Record<string, string> = {
    screening: '筛查中',
    screen_positive: '筛查阳性',
    pending_review: '待临床确认',
    confirmed: '已纳入确认',
    excluded: '已排除',
    pathway_active: '路径执行中',
    completed: '已完成',
    reconsideration_pending: '待复核',
    reopened: '已重新打开',
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
      reason: '病例详情页确认纳入',
    })
    message.success('已确认纳入')
    loadCase()
  } catch (err: any) {
    message.error('确认失败: ' + (err.message || '未知错误'))
  }
}

async function handleExclude() {
  try {
    await excludeCase(caseId.value, {
      reason: '病例详情页排除',
    })
    message.success('已排除')
    loadCase()
  } catch (err: any) {
    message.error('排除失败: ' + (err.message || '未知错误'))
  }
}

async function generateAiSummary() {
  aiLoading.value = true
  aiError.value = ''
  try {
    const result = await getCaseAiSummary(caseId.value)
    if (result.success && result.data) {
      aiSummary.value = result.data
      aiModel.value = result.model || ''
    } else {
      aiError.value = result.error || 'AI分析失败'
    }
  } catch (err: any) {
    aiError.value = 'AI分析请求失败: ' + (err.message || '未知错误')
  } finally {
    aiLoading.value = false
  }
}

function getRiskColor(risk: string) {
  const map: Record<string, string> = {
    critical: 'red',
    high: 'orange',
    medium: 'yellow',
    low: 'green',
  }
  return map[risk] || 'default'
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

/* AI 摘要样式 */
.ai-summary-section {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 12px);
  padding: 16px;
}

.ai-summary-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.ai-summary-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.ai-summary-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ai-summary-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-primary, #18212B);
  padding: 12px;
  background: var(--color-bg-subtle, #F9FAFB);
  border-radius: 8px;
}

.ai-section {
  padding: 8px 0;
}

.ai-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary, #667085);
  margin-bottom: 6px;
}

.ai-section ul {
  margin: 0;
  padding-left: 20px;
}

.ai-section li {
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-primary, #18212B);
}

.ai-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  padding-top: 8px;
  border-top: 1px solid var(--color-border, #E3E7EC);
}

.ai-error {
  color: var(--color-error, #D92D20);
  font-size: 13px;
  padding: 8px;
  background: var(--color-error-light, #FEF3F2);
  border-radius: 6px;
}

.ai-placeholder {
  color: var(--color-text-secondary, #667085);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}
</style>
