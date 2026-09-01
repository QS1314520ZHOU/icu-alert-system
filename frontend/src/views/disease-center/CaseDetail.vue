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
            @click="showConfirmModal"
          >
            确认纳入
          </a-button>
          <a-button
            v-if="caseData?.status === 'pending_review'"
            size="small"
            danger
            @click="showExcludeModal"
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
            <a-space>
              <a-button
                size="small"
                :loading="aiLoading"
                @click="generateAiSummary"
              >
                {{ aiSummary ? '重新分析' : '生成分析' }}
              </a-button>
            </a-space>
          </div>
          <div v-if="aiSummary" class="ai-summary-content">
            <div class="ai-summary-text">{{ aiSummary.summary || '暂无摘要' }}</div>

            <div v-if="aiSummary.risk_level && aiSummary.risk_level !== 'unknown'" class="ai-section">
              <div class="ai-section-title">风险等级</div>
              <a-tag :color="getRiskColor(aiSummary.risk_level)">{{ getRiskLabel(aiSummary.risk_level) }}</a-tag>
              <span v-if="aiSummary.uncertainty" class="ai-uncertainty">
                不确定性: {{ getUncertaintyLabel(aiSummary.uncertainty) }}
              </span>
            </div>

            <div v-if="aiSummary.core_problems?.length" class="ai-section">
              <div class="ai-section-title">核心问题</div>
              <ul>
                <li v-for="(problem, idx) in aiSummary.core_problems" :key="idx">
                  <span>{{ problem.claim }}</span>
                  <a-tag v-if="problem.confidence_level" size="small" :color="getConfidenceColor(problem.confidence_level)">
                    {{ problem.confidence_level }}
                  </a-tag>
                </li>
              </ul>
            </div>

            <div v-if="aiSummary.supporting_evidence?.length" class="ai-section">
              <div class="ai-section-title">支持证据</div>
              <ul>
                <li v-for="(ev, idx) in aiSummary.supporting_evidence" :key="idx">{{ ev.claim }}</li>
              </ul>
            </div>

            <div v-if="aiSummary.contradicting_evidence?.length" class="ai-section">
              <div class="ai-section-title">矛盾证据</div>
              <ul>
                <li v-for="(ev, idx) in aiSummary.contradicting_evidence" :key="idx">{{ ev.claim }}</li>
              </ul>
            </div>

            <div v-if="aiSummary.missing_information?.length" class="ai-section">
              <div class="ai-section-title">缺失信息</div>
              <ul>
                <li v-for="(item, idx) in aiSummary.missing_information" :key="idx">
                  <span>{{ item.description }}</span>
                  <a-tag v-if="item.priority" size="small" :color="getPriorityColor(item.priority)">
                    {{ item.priority }}
                  </a-tag>
                  <span v-if="item.suggested_action" class="ai-suggested-action">建议: {{ item.suggested_action }}</span>
                </li>
              </ul>
            </div>

            <div v-if="aiSummary.suggested_assessments?.length" class="ai-section">
              <div class="ai-section-title">建议评估</div>
              <ul>
                <li v-for="(item, idx) in aiSummary.suggested_assessments" :key="idx">
                  <span>{{ item.assessment }}</span>
                  <span v-if="item.rationale" class="ai-rationale">（{{ item.rationale }}）</span>
                </li>
              </ul>
            </div>

            <div class="ai-meta">
              <a-tag v-if="aiSummary.generation_mode" size="small">
                {{ aiSummary.generation_mode === 'llm' ? 'LLM生成' : '规则回退' }}
              </a-tag>
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

    <!-- 确认纳入对话框 -->
    <a-modal
      v-model:open="confirmModalVisible"
      title="确认纳入病例"
      @ok="handleConfirm"
      @cancel="confirmModalVisible = false"
      :confirm-loading="confirmLoading"
    >
      <a-form :model="confirmForm" layout="vertical">
        <a-form-item label="确认操作" required>
          <a-radio-group v-model:value="confirmForm.action">
            <a-radio value="confirm">确认纳入</a-radio>
            <a-radio value="reject">驳回</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="确认原因" required>
          <a-textarea
            v-model:value="confirmForm.reason"
            placeholder="请输入确认原因（必填）"
            :rows="3"
          />
        </a-form-item>
        <a-form-item label="临床备注">
          <a-textarea
            v-model:value="confirmForm.clinical_note"
            placeholder="可选：补充临床观察或备注"
            :rows="2"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 排除病例对话框 -->
    <a-modal
      v-model:open="excludeModalVisible"
      title="排除病例"
      @ok="handleExclude"
      @cancel="excludeModalVisible = false"
      :confirm-loading="excludeLoading"
      ok-text="确认排除"
      ok-type="danger"
    >
      <a-form :model="excludeForm" layout="vertical">
        <a-form-item label="排除类型" required>
          <a-select v-model:value="excludeForm.exclude_type" placeholder="请选择排除类型">
            <a-select-option value="clinical_judgment">临床判断排除</a-select-option>
            <a-select-option value="data_error">数据错误</a-select-option>
            <a-select-option value="self_discharge">自动出院</a-select-option>
            <a-select-option value="death">死亡</a-select-option>
            <a-select-option value="transfer">转院</a-select-option>
            <a-select-option value="other">其他</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="排除原因" required>
          <a-textarea
            v-model:value="excludeForm.reason"
            placeholder="请输入排除原因（必填）"
            :rows="3"
          />
        </a-form-item>
        <a-form-item label="临床备注">
          <a-textarea
            v-model:value="excludeForm.clinical_note"
            placeholder="可选：补充临床观察或备注"
            :rows="2"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getCaseDetail,
  confirmCase,
  excludeCase,
  getCaseAiSummary,
  generateCaseAiSummary,
} from '@/api/diseaseCenter'
import type { DiseaseCase, AICaseInsight } from '@/api/diseaseCenter'
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
const aiSummary = ref<AICaseInsight | null>(null)
const aiModel = ref<string>('')
const aiError = ref<string>('')

// 确认对话框
const confirmModalVisible = ref(false)
const confirmLoading = ref(false)
const confirmForm = ref({
  action: 'confirm' as 'confirm' | 'reject',
  reason: '',
  clinical_note: '',
})

// 排除对话框
const excludeModalVisible = ref(false)
const excludeLoading = ref(false)
const excludeForm = ref({
  exclude_type: undefined as string | undefined,
  reason: '',
  clinical_note: '',
})

const statusColor = computed(() => {
  const s = caseData.value?.status
  const map: Record<string, string> = {
    screening: 'default',
    screen_positive: 'orange',
    pending_review: 'blue',
    confirmed: 'green',
    excluded: 'default',
    pathway_active: 'purple',
    completed: 'cyan',
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

// ---- 确认纳入 ----

function showConfirmModal() {
  confirmForm.value = {
    action: 'confirm',
    reason: '',
    clinical_note: '',
  }
  confirmModalVisible.value = true
}

async function handleConfirm() {
  if (!confirmForm.value.reason.trim()) {
    message.warning('请输入确认原因')
    return
  }
  confirmLoading.value = true
  try {
    await confirmCase(caseId.value, {
      action: confirmForm.value.action,
      reason: confirmForm.value.reason.trim(),
      clinical_note: confirmForm.value.clinical_note.trim() || undefined,
    })
    message.success(confirmForm.value.action === 'confirm' ? '已确认纳入' : '已驳回')
    confirmModalVisible.value = false
    loadCase()
  } catch (err: any) {
    message.error('操作失败: ' + (err.message || '未知错误'))
  } finally {
    confirmLoading.value = false
  }
}

// ---- 排除 ----

function showExcludeModal() {
  excludeForm.value = {
    exclude_type: undefined,
    reason: '',
    clinical_note: '',
  }
  excludeModalVisible.value = true
}

async function handleExclude() {
  if (!excludeForm.value.exclude_type) {
    message.warning('请选择排除类型')
    return
  }
  if (!excludeForm.value.reason.trim()) {
    message.warning('请输入排除原因')
    return
  }
  excludeLoading.value = true
  try {
    await excludeCase(caseId.value, {
      exclude_type: excludeForm.value.exclude_type as any,
      reason: excludeForm.value.reason.trim(),
      clinical_note: excludeForm.value.clinical_note.trim() || undefined,
    })
    message.success('已排除')
    excludeModalVisible.value = false
    loadCase()
  } catch (err: any) {
    message.error('排除失败: ' + (err.message || '未知错误'))
  } finally {
    excludeLoading.value = false
  }
}

// ---- AI 摘要 ----

async function generateAiSummary() {
  aiLoading.value = true
  aiError.value = ''
  try {
    const result = await generateCaseAiSummary(caseId.value)
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

async function loadExistingAiSummary() {
  try {
    const result = await getCaseAiSummary(caseId.value)
    if (result.success && result.data) {
      aiSummary.value = result.data
      aiModel.value = result.model || ''
    }
  } catch {
    // 没有已保存的摘要，忽略
  }
}

function getRiskColor(risk: string) {
  const map: Record<string, string> = {
    critical: 'red',
    high: 'orange',
    medium: 'yellow',
    low: 'green',
    unknown: 'default',
  }
  return map[risk] || 'default'
}

function getRiskLabel(risk: string) {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高风险',
    medium: '中风险',
    low: '低风险',
    unknown: '未知',
  }
  return map[risk] || risk
}

function getUncertaintyLabel(uncertainty: string) {
  const map: Record<string, string> = {
    low: '低',
    moderate: '中等',
    high: '高',
  }
  return map[uncertainty] || uncertainty
}

function getConfidenceColor(level: string) {
  const map: Record<string, string> = {
    high: 'green',
    moderate: 'blue',
    low: 'orange',
  }
  return map[level] || 'default'
}

function getPriorityColor(priority: string) {
  const map: Record<string, string> = {
    high: 'red',
    medium: 'orange',
    low: 'blue',
  }
  return map[priority] || 'default'
}

onMounted(() => {
  loadCase()
  loadExistingAiSummary()
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
  align-items: center;
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  padding-top: 8px;
  border-top: 1px solid var(--color-border, #E3E7EC);
}

.ai-uncertainty {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  margin-left: 8px;
}

.ai-suggested-action {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  display: block;
  margin-top: 2px;
}

.ai-rationale {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.ai-error {
  color: var(--color-error, #D92D20);
  font-size: 14px;
  padding: 8px;
}

.ai-placeholder {
  color: var(--color-text-secondary, #667085);
  font-size: 14px;
  text-align: center;
  padding: 16px;
}
</style>
