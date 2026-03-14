<template>
  <div class="detail-container">
    <a-page-header
      :title="displayName"
      :sub-title="displaySubTitle"
      @back="backToList"
      class="detail-page-header"
    />

    <div class="detail-content">
      <a-card title="基本信息" :bordered="false" class="info-card">
        <p>诊断: {{ displayDiagnosis }}</p>
        <p>入院时间: {{ displayAdmissionTime }}</p>
        <p>HIS编号: {{ displayHisPid }}</p>
      </a-card>
      <a-card title="生命体征" :bordered="false" class="info-card vitals-card">
        <div v-if="vitals?.source" class="vitals-grid">
          <div class="v-item">
            <span class="v-label">来源</span>
            <span class="v-value">{{ vitalsSourceText }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">时间</span>
            <span class="v-value">{{ fmtTime(vitals.time) || '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">HR</span>
            <span class="v-value">{{ vitals.hr ?? '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">SpO₂</span>
            <span class="v-value">{{ vitals.spo2 != null ? vitals.spo2 + '%' : '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">RR</span>
            <span class="v-value">{{ vitals.rr ?? '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">BP</span>
            <span class="v-value">{{ fmtBP(vitals) }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">T</span>
            <span class="v-value">{{ fmtTemp(vitals.temp) }}</span>
          </div>
        </div>
        <div v-else class="vitals-empty">暂无监护数据</div>
      </a-card>
    </div>

    <a-card class="tabs-card" :bordered="false">
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="trend" tab="生命体征趋势">
          <PatientTrendTab
            v-if="activeTab === 'trend'"
            v-model:trend-window="trendWindow"
            :trend-points="trendPoints"
            :trend-option="trendOption"
            :on-refresh="loadTrend"
          />
        </a-tab-pane>

        <a-tab-pane key="labs" tab="检验结果时间线">
          <PatientLabsTab
            v-if="activeTab === 'labs'"
            :labs="labs"
            :fmt-time="fmtTime"
            :lab-flag="labFlag"
          />
        </a-tab-pane>

        <a-tab-pane key="drugs" tab="用药记录">
          <PatientDataTableTab
            v-if="activeTab === 'drugs'"
            :columns="drugColumns"
            :rows="drugs"
            row-key="_id"
          />
        </a-tab-pane>

        <a-tab-pane key="assess" tab="护理评估">
          <PatientDataTableTab
            v-if="activeTab === 'assess'"
            :columns="assessmentColumns"
            :rows="assessments"
            row-key="time"
          />
        </a-tab-pane>

        <a-tab-pane key="alerts" tab="预警历史">
          <PatientAlertsTab
            v-if="activeTab === 'alerts'"
            :latest-composite-alert="latestCompositeAlert"
            :latest-composite-window-hours="latestCompositeWindowHours"
            :latest-composite-modi="latestCompositeModi"
            :latest-composite-organ-count="latestCompositeOrganCount"
            :latest-composite-involved-text="latestCompositeInvolvedText"
            :composite-radar-option="compositeRadarOption"
            :alerts="alerts"
            :fmt-time="fmtTime"
            :normalize-severity="normalizeSeverity"
            :alert-severity-text="alertSeverityText"
            :format-alert-value="formatAlertValue"
            :alert-type-text="alertTypeText"
            :alert-category-text="alertCategoryText"
            :alert-detail-fields="alertDetailFields"
            :is-ai-risk-alert="isAiRiskAlert"
            :ai-confidence-class="aiConfidenceClass"
            :ai-risk-confidence-level="aiRiskConfidenceLevel"
            :ai-risk-level-text="aiRiskLevelText"
            :feedback-outcome-text="feedbackOutcomeText"
            :submit-ai-feedback="submitAiFeedback"
            :ai-risk-organ-rows="aiRiskOrganRows"
            :ai-risk-validation-issues="aiRiskValidationIssues"
            :ai-risk-hallucinations="aiRiskHallucinations"
            :ai-risk-evidence-list="aiRiskEvidenceList"
            :open-evidence="openEvidence"
            :ai-risk-explainability-rows="aiRiskExplainabilityRows"
            :format-alert-extra="formatAlertExtra"
          />
        </a-tab-pane>

        <a-tab-pane key="ai" tab="AI辅助">
          <PatientAiTab
            v-if="activeTab === 'ai'"
            :ai-lab-loading="aiLabLoading"
            :ai-lab-summary="aiLabSummary"
            :load-ai-lab="loadAiLab"
            :render-ai-rich-text="renderAiRichText"
            :ai-lab-error="aiLabError"
            :ai-rule-loading="aiRuleLoading"
            :load-ai-rules="loadAiRules"
            :ai-rule-rows="aiRuleRows"
            :ai-rule-columns="aiRuleColumns"
            :ai-rule-text="aiRuleText"
            :ai-rule-error="aiRuleError"
            :ai-risk-loading="aiRiskLoading"
            :load-ai-risk="loadAiRisk"
            :latest-ai-risk-alert="latestAiRiskAlert"
            :ai-confidence-class="aiConfidenceClass"
            :ai-risk-confidence-level="aiRiskConfidenceLevel"
            :ai-risk-level-text="aiRiskLevelText"
            :ai-risk-evidence-list="aiRiskEvidenceList"
            :open-evidence="openEvidence"
            :ai-risk-hallucinations="aiRiskHallucinations"
            :ai-risk-text="aiRiskText"
            :ai-risk-error="aiRiskError"
            :ai-handoff-loading="aiHandoffLoading"
            :load-ai-handoff="loadAiHandoff"
            :copy-handoff-summary="copyHandoffSummary"
            :ai-handoff="aiHandoff"
            :ai-handoff-confidence="aiHandoffConfidence"
            :normalize-list="normalizeList"
            :ai-handoff-error="aiHandoffError"
            :knowledge-loading="knowledgeLoading"
            :load-knowledge-docs="loadKnowledgeDocs"
            :handle-reload-knowledge="handleReloadKnowledge"
            :knowledge-docs="knowledgeDocs"
            :knowledge-status="knowledgeStatus"
            :selected-knowledge-doc-id="selectedKnowledgeDocId"
            :load-knowledge-document="loadKnowledgeDocument"
            :selected-knowledge-doc="selectedKnowledgeDoc"
            :knowledge-scope-text="knowledgeScopeText"
            :knowledge-error="knowledgeError"
          />
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <PatientEvidenceModal
      v-if="evidenceModalOpen"
      v-model:open="evidenceModalOpen"
      :modal="evidenceModal"
      :open-evidence="openEvidence"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import {
  Card as ACard,
  PageHeader as APageHeader,
  TabPane as ATabPane,
  Tabs as ATabs,
  message,
} from 'ant-design-vue'
import {
  getPatientDetail,
  getPatientVitals,
  getPatientLabs,
  getPatientVitalsTrend,
  getPatientDrugs,
  getPatientAssessments,
  getPatientAlerts,
  getAiLabSummary,
  getAiRuleRecommendations,
  getAiRiskForecast,
  getPatientHandoffSummary,
  getKnowledgeChunk,
  getKnowledgeDocument,
  getKnowledgeDocuments,
  getKnowledgeStatus,
  postAiFeedback,
  reloadKnowledge,
} from '../api'

const PatientTrendTab = defineAsyncComponent(() => import('../components/patient-detail/TrendTab.vue'))
const PatientLabsTab = defineAsyncComponent(() => import('../components/patient-detail/LabsTab.vue'))
const PatientDataTableTab = defineAsyncComponent(() => import('../components/patient-detail/DataTableTab.vue'))
const PatientAlertsTab = defineAsyncComponent(() => import('../components/patient-detail/AlertsTab.vue'))
const PatientAiTab = defineAsyncComponent(() => import('../components/patient-detail/AiTab.vue'))
const PatientEvidenceModal = defineAsyncComponent(() => import('../components/patient-detail/EvidenceModal.vue'))

const route = useRoute()
const router = useRouter()
const patient = ref<any>(null)
const vitals = ref<any>(null)
const activeTab = ref('trend')

const trendWindow = ref('24h')
const trendPoints = ref<any[]>([])
const labs = ref<any[]>([])
const drugs = ref<any[]>([])
const assessments = ref<any[]>([])
const alerts = ref<any[]>([])

const compositeOrganOrder = ['respiratory', 'circulatory', 'renal', 'coagulation', 'hepatic', 'neurologic']
const compositeOrganLabelDefault: Record<string, string> = {
  respiratory: '呼吸',
  circulatory: '循环',
  renal: '肾脏',
  coagulation: '凝血',
  hepatic: '肝脏',
  neurologic: '神经',
}

const aiLabSummary = ref('')
const aiRuleText = ref('')
const aiRiskText = ref('')
const aiHandoff = ref<any>(null)
const aiLabError = ref('')
const aiRuleError = ref('')
const aiRiskError = ref('')
const aiHandoffError = ref('')
const aiLabLoading = ref(false)
const aiRuleLoading = ref(false)
const aiRiskLoading = ref(false)
const aiHandoffLoading = ref(false)
const aiAutoLoaded = ref(false)
const knowledgeDocs = ref<any[]>([])
const selectedKnowledgeDocId = ref<string>('')
const selectedKnowledgeDoc = ref<any>(null)
const knowledgeLoading = ref(false)
const knowledgeError = ref('')
const knowledgeStatus = ref<any>(null)
const evidenceModalOpen = ref(false)
const evidenceModal = ref<any>({
  title: '',
  source: '',
  package_name: '',
  package_version: '',
  category: '',
  owner: '',
  updated_at: '',
  priority: null,
  local_ref: '',
  recommendation: '',
  recommendation_grade: '',
  section_title: '',
  tags: [],
  content: '',
  related_chunks: [],
})

const displayName = computed(() =>
  patient.value?.name || patient.value?.hisName || '加载中...'
)
const displaySubTitle = computed(() => {
  const bed = patient.value?.hisBed || patient.value?.bed || '--'
  const gender = patient.value?.genderText || patient.value?.hisSex || ''
  const age = patient.value?.age || patient.value?.hisAge || ''
  return `${bed}床 | ${gender} ${age}`.trim()
})
const displayDiagnosis = computed(() =>
  patient.value?.clinicalDiagnosis ||
  patient.value?.admissionDiagnosis ||
  patient.value?.hisDiagnose ||
  '暂无'
)
const displayAdmissionTime = computed(() =>
  patient.value?.icuAdmissionTime ||
  patient.value?.admissionTime ||
  '未知'
)
const displayHisPid = computed(() =>
  patient.value?.hisPid || patient.value?.hisPID || '无'
)

const vitalsSourceText = computed(() => {
  if (!vitals.value?.source) return ''
  if (vitals.value.source === 'monitor') return '监护仪'
  if (vitals.value.source === 'nurse_manual') return '护士录入'
  return '未知'
})

const latestCompositeAlert = computed(() =>
  alerts.value.find((a: any) =>
    String(a?.alert_type || '') === 'multi_organ_deterioration_trend' ||
    String(a?.category || '') === 'composite_deterioration')
)
const latestAiRiskAlert = computed(() =>
  alerts.value.find((a: any) => String(a?.alert_type || '') === 'ai_risk')
)

const latestCompositeExtra = computed(() => latestCompositeAlert.value?.extra || {})
const latestCompositeWindowHours = computed(() => latestCompositeExtra.value?.window_hours ?? 4)
const latestCompositeModi = computed(() => latestCompositeExtra.value?.modi ?? latestCompositeAlert.value?.value ?? null)
const latestCompositeOrganCount = computed(() => {
  const count = latestCompositeExtra.value?.organ_count
  if (count != null) return count
  const involved = latestCompositeExtra.value?.involved_organs
  return Array.isArray(involved) ? involved.length : 0
})
const latestCompositeInvolvedText = computed(() => {
  const labels = latestCompositeExtra.value?.organ_labels_cn || {}
  const involved = Array.isArray(latestCompositeExtra.value?.involved_organs)
    ? latestCompositeExtra.value.involved_organs
    : []
  const names = involved
    .map((k: any) => labels?.[String(k)] || compositeOrganLabelDefault[String(k)] || String(k))
    .filter(Boolean)
  return names.length ? `涉及系统: ${names.join(' / ')}` : '涉及系统: 暂无'
})

const compositeRadarOption = computed(() => {
  const extra = latestCompositeExtra.value || {}
  const scoreMap = extra?.organ_scores || {}
  const labels = extra?.organ_labels_cn || {}
  const values = compositeOrganOrder.map((k) => {
    const raw = Number(scoreMap?.[k] ?? 0)
    if (Number.isNaN(raw)) return 0
    return Math.max(0, Math.min(3, raw))
  })
  const indicator = compositeOrganOrder.map((k) => ({
    name: labels?.[k] || compositeOrganLabelDefault[k] || k,
    max: 3,
  }))
  return {
    tooltip: { trigger: 'item', confine: true },
    radar: {
      indicator,
      radius: '63%',
      splitNumber: 3,
      axisName: { color: '#7d93b5', fontSize: 12 },
      axisLine: { lineStyle: { color: '#214368' } },
      splitLine: { lineStyle: { color: ['#183357', '#1f3f67', '#26547c'] } },
      splitArea: { areaStyle: { color: ['rgba(15, 33, 56, 0.28)', 'rgba(17, 37, 63, 0.22)', 'rgba(24, 53, 90, 0.16)'] } },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: values,
            name: '器官严重程度',
            areaStyle: { color: 'rgba(56, 189, 248, 0.24)' },
            lineStyle: { color: '#38bdf8', width: 2 },
            itemStyle: { color: '#0ea5e9' },
          },
        ],
      },
    ],
  }
})

const trendOption = computed(() => {
  const xs = trendPoints.value.map(p => fmtTimeShort(p.time))
  const mapVals = trendPoints.value.map(p => p.ibp_map ?? p.nibp_map ?? null)
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9aa4b2' } },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: xs,
      axisLine: { lineStyle: { color: '#1e2a3a' } },
      axisLabel: { color: '#6b7280', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: '#1e2a3a' } },
      axisLabel: { color: '#6b7280', fontSize: 10 },
      splitLine: { lineStyle: { color: '#132237' } },
    },
    series: [
      { name: 'HR', type: 'line', smooth: true, data: trendPoints.value.map(p => p.hr ?? null) },
      { name: 'SpO₂', type: 'line', smooth: true, data: trendPoints.value.map(p => p.spo2 ?? null) },
      { name: 'RR', type: 'line', smooth: true, data: trendPoints.value.map(p => p.rr ?? null) },
      { name: 'MAP', type: 'line', smooth: true, data: mapVals },
      { name: 'T', type: 'line', smooth: true, data: trendPoints.value.map(p => p.temp ?? null) },
    ],
  }
})

function formatDrugName(record: any) {
  return record?.drugName || record?.orderName || record?.drugSpec || '—'
}
function formatDose(record: any) {
  const dose = record?.dose
  const unit = record?.doseUnit
  if (dose == null || dose === '') return '—'
  return unit ? `${dose}${unit}` : String(dose)
}

const drugColumns = [
  { title: '药品', dataIndex: 'drugName', key: 'drugName', customRender: ({ record }: any) => formatDrugName(record) },
  { title: '剂量', dataIndex: 'dose', key: 'dose', customRender: ({ record }: any) => formatDose(record) },
  { title: '用法', dataIndex: 'route', key: 'route', customRender: ({ text }: any) => text || '—' },
  { title: '频次', dataIndex: 'frequency', key: 'frequency', customRender: ({ text }: any) => text || '—' },
  { title: '执行时间', dataIndex: 'executeTime', key: 'executeTime', customRender: ({ text }: any) => fmtTime(text) || '—' },
]

const assessmentColumns = [
  { title: '时间', dataIndex: 'time', key: 'time', customRender: ({ text }: any) => fmtTime(text) || '—' },
  { title: 'GCS', dataIndex: 'gcs', key: 'gcs', customRender: ({ text }: any) => text ?? '—' },
  { title: 'RASS', dataIndex: 'rass', key: 'rass', customRender: ({ text }: any) => text ?? '—' },
  { title: '疼痛', dataIndex: 'pain', key: 'pain', customRender: ({ text }: any) => text ?? '—' },
  { title: '谵妄', dataIndex: 'delirium', key: 'delirium', customRender: ({ text }: any) => text ?? '—' },
  { title: 'Braden', dataIndex: 'braden', key: 'braden', customRender: ({ text }: any) => text ?? '—' },
]

type AiRuleRow = {
  key: string
  parameter: string
  operator: string
  threshold: string
  severity: string
  reason: string
}

const aiRuleColumns = [
  { title: '指标', dataIndex: 'parameter', key: 'parameter', width: 220, ellipsis: true },
  { title: '方向', dataIndex: 'operator', key: 'operator', width: 76, align: 'center' as const },
  { title: '阈值', dataIndex: 'threshold', key: 'threshold', width: 96, align: 'center' as const },
  { title: '级别', dataIndex: 'severity', key: 'severity', width: 96, align: 'center' as const },
  { title: '依据', dataIndex: 'reason', key: 'reason', width: 320, ellipsis: true },
]

function fmtBP(v: any) {
  const s = v?.nibp_sys, d = v?.nibp_dia
  return s != null || d != null ? `${s ?? '—'}/${d ?? '—'}` : '—'
}
function fmtTemp(v: any) {
  if (v == null) return '—'
  const n = Number(v)
  return isNaN(n) ? '—' : n.toFixed(1)
}
function fmtTime(t: any) {
  if (!t) return ''
  try {
    return dayjs(t).format('YYYY-MM-DD HH:mm')
  } catch { return '' }
}
function fmtTimeShort(t: any) {
  if (!t) return ''
  try { return dayjs(t).format('MM-DD HH:mm') } catch { return '' }
}

function knowledgeScopeText(scope: any) {
  const value = String(scope || '').toLowerCase()
  if (value === 'institutional') return '院内SOP/制度'
  if (value === 'external') return '外部指南'
  if (value === 'local') return '本地资料'
  return value || '未知'
}

function escapeHtml(raw: string) {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function stripMarkdownFence(raw: string) {
  const text = String(raw || '').trim()
  if (!text) return ''
  const fullFence = text.match(/^```(?:json|markdown|md)?\s*([\s\S]*?)\s*```$/i)
  if (fullFence?.[1]) return fullFence[1].trim()
  return text
    .replace(/^```(?:json|markdown|md)?\s*/i, '')
    .replace(/\s*```$/, '')
    .trim()
}

function inlineMarkdownToHtml(raw: string) {
  let out = escapeHtml(raw)
  out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>')
  return out
}

function renderAiRichText(raw: any) {
  const text = stripMarkdownFence(String(raw || ''))
  if (!text) return ''
  return text
    .split(/\r?\n/)
    .map((line) => {
      const t = line.trim()
      if (!t) return '<p class="ai-blank"></p>'
      const h = t.match(/^#{1,4}\s*(.+)$/)
      if (h) return `<h4>${inlineMarkdownToHtml(h[1] || '')}</h4>`
      if (/^\d+\.\s+/.test(t)) return `<p class="ai-li">${inlineMarkdownToHtml(t)}</p>`
      if (/^[-*]\s+/.test(t)) return `<p class="ai-li">${inlineMarkdownToHtml(t.replace(/^[-*]\s+/, '• '))}</p>`
      return `<p>${inlineMarkdownToHtml(t)}</p>`
    })
    .join('')
}

function parseAiRuleRows(raw: any): AiRuleRow[] {
  const text = stripMarkdownFence(String(raw || ''))
  if (!text) return []
  const candidates = [text]
  const arrBlock = text.match(/\[[\s\S]*\]/)
  if (arrBlock?.[0] && arrBlock[0] !== text) {
    candidates.unshift(arrBlock[0])
  }
  let arr: any[] | null = null
  for (const c of candidates) {
    try {
      const parsed = JSON.parse(c)
      if (Array.isArray(parsed)) {
        arr = parsed
        break
      }
    } catch {
      // ignore
    }
  }
  if (!arr?.length) return []
  const sevMap: Record<string, string> = {
    warning: '提醒',
    high: '高风险',
    critical: '危急',
  }
  return arr.map((it: any, idx: number) => {
    const severityRaw = String(it?.severity || '').toLowerCase()
    return {
      key: String(idx + 1),
      parameter: String(it?.parameter || it?.name || '—'),
      operator: String(it?.operator || '—'),
      threshold: it?.threshold != null ? String(it.threshold) : '—',
      severity: sevMap[severityRaw] || String(it?.severity || '—'),
      reason: String(it?.reason || it?.description || '—'),
    }
  })
}

const aiRuleRows = computed(() => parseAiRuleRows(aiRuleText.value))
const aiHandoffConfidence = computed(() => String(aiHandoff.value?.confidence_level || '').toLowerCase())
void aiHandoffConfidence

function aiConfidenceClass(level: string) {
  const v = String(level || '').toLowerCase()
  if (v === 'low') return 'ai-confidence-low'
  if (v === 'medium') return 'ai-confidence-medium'
  return 'ai-confidence-high'
}
void aiConfidenceClass

function normalizeConfidenceLevel(raw: any) {
  const v = String(raw || '').toLowerCase()
  if (v === 'low' || v === 'medium' || v === 'high') return v
  return 'medium'
}

function isAiRiskAlert(item: any) {
  return String(item?.alert_type || '') === 'ai_risk'
}

function aiRiskConfidenceLevel(item: any) {
  return normalizeConfidenceLevel(
    item?.extra?.confidence?.overall ||
    item?.extra?.explainability?.confidence_level ||
    'medium'
  )
}

function aiRiskLevelText(raw: any) {
  let v = String(raw || '').toLowerCase()
  // Strip Coze footnote tags like [^thread://...] before matching
  v = v.replace(/\[\^[^\]]+\]/g, '').trim()
  
  if (v === 'critical' || v === '极高') return '极高'
  if (v === 'high' || v === '高') return '高'
  if (v === 'medium' || v === '中') return '中'
  if (v === 'low' || v === '低') return '低'
  return v || '—'
}

function feedbackOutcomeText(raw: any) {
  const v = String(raw || '').toLowerCase()
  if (v === 'confirmed') return '采纳'
  if (v === 'dismissed') return '忽略'
  if (v === 'inaccurate') return '不准确'
  return String(raw || '—')
}

function aiRiskOrganRows(item: any) {
  const organ = item?.extra?.organ_assessment
  const organLabels: Record<string, string> = {
    respiratory: '呼吸',
    cardiovascular: '循环',
    renal: '肾脏',
    hepatic: '肝脏',
    coagulation: '凝血',
    neurological: '神经',
  }
  const statusLabels: Record<string, string> = {
    normal: '正常',
    impaired: '受损',
    failure: '衰竭',
  }
  if (!organ || typeof organ !== 'object') return []
  return Object.entries(organ)
    .map(([key, val]: [string, any]) => ({
      key,
      label: organLabels[key] || key,
      status_text: statusLabels[String(val?.status || '').toLowerCase()] || String(val?.status || '—'),
      evidence: String(val?.evidence || ''),
      confidence_level: normalizeConfidenceLevel(val?.confidence_level),
    }))
    .filter((x) => x.label)
}

function aiRiskValidationIssues(item: any) {
  const issues = item?.extra?.safety_validation?.issues
  return Array.isArray(issues) ? issues : []
}

function aiRiskHallucinations(item: any) {
  const flags = item?.extra?.hallucination_flags
  return Array.isArray(flags) ? flags : []
}

function aiRiskEvidenceList(item: any) {
  const evidence = item?.extra?.evidence_sources
  return Array.isArray(evidence) ? evidence : []
}

function aiRiskExplainabilityRows(item: any) {
  const rows = item?.extra?.explainability?.top_factors
  return Array.isArray(rows) ? rows : []
}

async function openEvidence(evidence: any) {
  const chunkId = String(evidence?.chunk_id || '').trim()
  if (!chunkId) {
    message.warning('缺少本地证据ID')
    return
  }
  try {
    const res = await getKnowledgeChunk(chunkId)
    const chunk = res.data?.chunk || {}
    evidenceModal.value = {
      title: chunk.title || evidence.title || '离线指南证据',
      source: chunk.source || evidence.source || '',
      package_name: chunk.package_name || '',
      package_version: chunk.package_version || '',
      category: chunk.category || '',
      owner: chunk.owner || '',
      updated_at: chunk.updated_at || '',
      priority: chunk.priority ?? null,
      local_ref: chunk.local_ref || '',
      recommendation: chunk.recommendation || evidence.recommendation || '',
      recommendation_grade: chunk.recommendation_grade || '',
      section_title: chunk.section_title || '',
      tags: Array.isArray(chunk.tags) ? chunk.tags : [],
      content: chunk.content || evidence.quote || '',
      related_chunks: Array.isArray(chunk.related_chunks) ? chunk.related_chunks : [],
    }
    evidenceModalOpen.value = true
  } catch {
    evidenceModal.value = {
      title: evidence.title || '离线指南证据',
      source: evidence.source || '',
      package_name: evidence.package_name || '',
      package_version: evidence.package_version || '',
      category: evidence.category || '',
      owner: evidence.owner || '',
      updated_at: evidence.updated_at || '',
      priority: evidence.priority ?? null,
      local_ref: evidence.local_ref || '',
      recommendation: evidence.recommendation || '',
      recommendation_grade: evidence.recommendation_grade || '',
      section_title: evidence.section_title || '',
      tags: Array.isArray(evidence.tags) ? evidence.tags : [],
      content: evidence.quote || '本地知识片段加载失败',
      related_chunks: [],
    }
    evidenceModalOpen.value = true
  }
}

function normalizeList(raw: any): string[] {
  if (!Array.isArray(raw)) return []
  return raw.map((x) => String(x || '').trim()).filter(Boolean)
}

function handoffPlainText() {
  const s = aiHandoff.value || {}
  const lines: string[] = []
  lines.push(`Illness severity: ${s.illness_severity || 'watcher'}`)
  lines.push(`Patient summary: ${s.patient_summary || ''}`)
  lines.push(`Action list: ${normalizeList(s.action_list).join('；')}`)
  lines.push(`Situation awareness: ${normalizeList(s.situation_awareness).join('；')}`)
  lines.push(`Synthesis by receiver: ${s.synthesis_by_receiver || ''}`)
  lines.push(`Confidence: ${s.confidence_level || 'low'}`)
  if (s?.validation?.status) {
    lines.push(`Validation: ${s.validation.status}`)
  }
  return lines.join('\n')
}

async function copyHandoffSummary() {
  if (!aiHandoff.value) return
  try {
    await navigator.clipboard.writeText(handoffPlainText())
    aiHandoffError.value = '交班摘要已复制'
    setTimeout(() => {
      if (aiHandoffError.value === '交班摘要已复制') aiHandoffError.value = ''
    }, 1500)
  } catch {
    aiHandoffError.value = '复制失败'
  }
}
void copyHandoffSummary

async function submitAiFeedback(item: any, outcome: 'confirmed' | 'dismissed' | 'inaccurate') {
  const predictionId = String(item?._id || '').trim()
  if (!predictionId) {
    message.error('缺少预警ID，无法提交反馈')
    return
  }
  try {
    await postAiFeedback({
      prediction_id: predictionId,
      outcome,
      module: 'ai_risk',
      detail: {
        patient_id: String(item?.patient_id || ''),
        rule_id: String(item?.rule_id || ''),
        alert_type: String(item?.alert_type || ''),
      },
    })
    if (!item.ai_feedback) item.ai_feedback = {}
    item.ai_feedback.outcome = outcome
    item.ai_feedback.updated_at = new Date().toISOString()
    message.success('AI反馈已记录')
  } catch {
    message.error('AI反馈提交失败')
  }
}

async function loadKnowledgeDocs() {
  if (knowledgeLoading.value) return
  knowledgeLoading.value = true
  knowledgeError.value = ''
  try {
    const [res, statusRes] = await Promise.all([getKnowledgeDocuments(), getKnowledgeStatus()])
    const docs = Array.isArray(res.data?.documents) ? res.data.documents : []
    knowledgeDocs.value = docs
    knowledgeStatus.value = statusRes.data?.status || null
    if (!selectedKnowledgeDocId.value && docs.length) {
      selectedKnowledgeDocId.value = String(docs[0].doc_id || '')
      await loadKnowledgeDocument(selectedKnowledgeDocId.value)
    }
  } catch {
    knowledgeError.value = '离线知识包加载失败'
  } finally {
    knowledgeLoading.value = false
  }
}

async function loadKnowledgeDocument(docId?: any) {
  const id = String(docId || selectedKnowledgeDocId.value || '').trim()
  if (!id) return
  knowledgeLoading.value = true
  knowledgeError.value = ''
  try {
    const res = await getKnowledgeDocument(id)
    selectedKnowledgeDoc.value = res.data?.document || null
  } catch {
    knowledgeError.value = '离线文档加载失败'
  } finally {
    knowledgeLoading.value = false
  }
}

async function handleReloadKnowledge() {
  if (knowledgeLoading.value) return
  knowledgeLoading.value = true
  knowledgeError.value = ''
  try {
    const res = await reloadKnowledge()
    const [docsRes, statusRes] = await Promise.all([getKnowledgeDocuments(), getKnowledgeStatus()])
    const docs = Array.isArray(docsRes.data?.documents) ? docsRes.data.documents : []
    knowledgeDocs.value = docs
    knowledgeStatus.value = statusRes.data?.status || res.data?.status || null
    if (selectedKnowledgeDocId.value) {
      const stillExists = docs.some((doc: any) => String(doc?.doc_id || '') === selectedKnowledgeDocId.value)
      if (!stillExists) {
        selectedKnowledgeDocId.value = ''
        selectedKnowledgeDoc.value = null
      }
    }
    if (!selectedKnowledgeDocId.value && docs.length) {
      selectedKnowledgeDocId.value = String(docs[0].doc_id || '')
    }
    if (selectedKnowledgeDocId.value) {
      const detailRes = await getKnowledgeDocument(selectedKnowledgeDocId.value)
      selectedKnowledgeDoc.value = detailRes.data?.document || null
    }
    message.success(res.data?.message || '知识库已热更新')
  } catch {
    knowledgeError.value = '知识库热更新失败'
    message.error('知识库热更新失败')
  } finally {
    knowledgeLoading.value = false
  }
}

function alertDetailFields(item: any) {
  const t = String(item?.alert_type || '')
  const extra = item?.extra || {}
  const fields: { label: string, value: any }[] = []

  if (t === 'sofa' || t === 'septic_shock') {
    const sofa = extra?.sofa || extra
    const comps = sofa?.components || {}
    fields.push(
      { label: 'SOFA', value: sofa?.score ?? item?.value },
      { label: 'ΔSOFA', value: sofa?.delta },
      { label: '呼吸', value: comps?.resp },
      { label: '凝血', value: comps?.coag },
      { label: '肝脏', value: comps?.liver },
      { label: '循环', value: comps?.cardio },
      { label: '神经', value: comps?.neuro },
      { label: '肾脏', value: comps?.renal },
    )
    return fields
  }

  if (t === 'qsofa') {
    fields.push(
      { label: 'qSOFA', value: item?.value },
      { label: 'SBP', value: extra?.sbp },
      { label: 'RR', value: extra?.rr },
      { label: 'GCS', value: extra?.gcs },
    )
    return fields
  }

  if (t === 'ards') {
    fields.push(
      { label: 'P/F', value: item?.value ?? item?.condition?.pf_ratio },
      { label: 'PaO₂', value: extra?.pao2 },
      { label: 'FiO₂', value: extra?.fio2 },
      { label: 'PEEP', value: extra?.peep },
    )
    return fields
  }

  if (t === 'aki') {
    const cond = extra?.condition || {}
    fields.push(
      { label: '分期', value: extra?.stage ?? item?.value },
      { label: '当前Cr', value: extra?.current },
      { label: '基线Cr', value: extra?.baseline },
      { label: 'Δ48h', value: cond?.delta_48h },
      { label: '尿量(6h)', value: cond?.urine_6h_ml_kg_h },
      { label: '尿量(12h)', value: cond?.urine_12h_ml_kg_h },
      { label: '尿量(24h)', value: cond?.urine_24h_ml_kg_h },
    )
    return fields
  }

  if (t === 'dic') {
    const detail = extra?.detail || {}
    fields.push(
      { label: 'ISTH评分', value: extra?.score ?? item?.value },
      { label: 'PLT', value: detail?.plt },
      { label: 'D-Dimer', value: detail?.ddimer },
      { label: 'PT/INR', value: detail?.pt },
      { label: 'Fib', value: detail?.fib },
    )
    return fields
  }

  if (t === 'lab_threshold') {
    const unit = extra?.unit ? ` ${extra.unit}` : ''
    const plan = extra?.correction_plan
    fields.push(
      { label: '指标', value: extra?.raw_name || item?.parameter },
      { label: '结果', value: item?.value != null ? `${item.value}${unit}` : '—' },
      { label: '标志', value: extra?.raw_flag },
    )
    if (plan?.title) {
      fields.push({ label: '纠正建议', value: Array.isArray(plan.actions) ? plan.actions.join('；') : plan.title })
    }
    if (plan?.aki_note) {
      fields.push({ label: 'AKI提示', value: plan.aki_note })
    }
    return fields
  }

  if (t === 'trend_analysis') {
    const trend = extra?.trend || {}
    const recent = Array.isArray(extra?.recent_values) ? extra.recent_values.slice(-5).join(', ') : ''
    fields.push(
      { label: '指标', value: item?.parameter },
      { label: '方向', value: trend?.direction },
      { label: '斜率', value: trend?.slope },
      { label: '近5点', value: recent },
    )
    return fields
  }

  if (t === 'gcs_drop') {
    fields.push(
      { label: 'GCS下降', value: extra?.drop },
      { label: '基线GCS', value: extra?.baseline },
      { label: '当前GCS', value: extra?.current },
    )
    return fields
  }

  if (t === 'icp' || t === 'cpp') {
    fields.push({ label: '当前值', value: item?.value })
    return fields
  }

  if (t === 'pupil') {
    fields.push(
      { label: '左瞳', value: extra?.left },
      { label: '右瞳', value: extra?.right },
      { label: '异常', value: extra?.abnormal ? '是' : '否' },
    )
    return fields
  }

  if (t === 'gi_bleeding') {
    fields.push(
      { label: 'Hb下降', value: item?.condition?.drop },
      { label: 'HR', value: extra?.hr },
      { label: 'SBP', value: extra?.sbp },
    )
    return fields
  }

  if (t === 'weaning') {
    fields.push(
      { label: 'FiO₂', value: extra?.fio2 },
      { label: 'PEEP', value: extra?.peep },
      { label: 'MAP', value: extra?.map },
      { label: 'GCS', value: extra?.gcs },
    )
    return fields
  }

  if (t === 'hit' || t === 'nephrotoxicity') {
    fields.push(
      { label: '当前值', value: item?.value },
      { label: '基线', value: extra?.baseline },
    )
    return fields
  }

  if (t === 'sedation') {
    fields.push({ label: 'RASS', value: extra?.rass })
    return fields
  }

  if (t === 'qt_risk') {
    fields.push({ label: '药物数量', value: item?.value })
    return fields
  }

  if (t === 'af_afl_new_onset') {
    fields.push(
      { label: '峰值HR', value: extra?.hr_peak_in_segment != null ? `${extra.hr_peak_in_segment} bpm` : item?.value },
      { label: '不规则时长', value: extra?.irregular_duration_seconds != null ? `${extra.irregular_duration_seconds}s` : '—' },
      { label: 'AF标签', value: extra?.has_af_tag ? '是' : '否' },
      { label: 'AFL标签', value: extra?.has_afl_tag ? '是' : '否' },
    )
    return fields
  }

  if (t === 'brady_hypotension') {
    fields.push(
      { label: 'HR', value: extra?.latest_hr != null ? `${extra.latest_hr} bpm` : item?.value },
      { label: '当前SBP', value: extra?.latest_sbp != null ? `${extra.latest_sbp} mmHg` : '—' },
      { label: '基线SBP', value: extra?.baseline_sbp != null ? `${extra.baseline_sbp} mmHg` : '—' },
      { label: 'SBP下降', value: extra?.drop_sbp != null ? `${extra.drop_sbp} mmHg` : '—' },
    )
    return fields
  }

  if (t === 'qtc_prolonged') {
    fields.push(
      { label: 'QTc', value: extra?.qtc_ms != null ? `${extra.qtc_ms} ms` : (item?.value != null ? `${item.value} ms` : '—') },
      { label: '阈值', value: extra?.qtc_threshold_ms != null ? `${extra.qtc_threshold_ms} ms` : '—' },
      { label: '来源', value: extra?.source_code || '—' },
    )
    return fields
  }

  if (t === 'opioid_high_dose_resp_risk') {
    fields.push(
      { label: '24h吗啡当量', value: extra?.opioid_med_24h_mg != null ? `${extra.opioid_med_24h_mg} mg` : item?.value },
      { label: '阈值', value: extra?.threshold_mg_per_day != null ? `${extra.threshold_mg_per_day} mg/d` : '—' },
    )
    return fields
  }

  if (t === 'opioid_respiratory_depression') {
    fields.push(
      { label: 'RR', value: extra?.rr != null ? `${extra.rr} 次/分` : '—' },
      { label: 'SpO₂', value: extra?.latest_spo2 != null ? `${extra.latest_spo2}%` : '—' },
      { label: 'SpO₂下降', value: extra?.spo2_drop != null ? `${extra.spo2_drop}%` : '—' },
      { label: '24h吗啡当量', value: extra?.opioid_med_24h_mg != null ? `${extra.opioid_med_24h_mg} mg` : '—' },
    )
    return fields
  }

  if (t === 'opioid_withdrawal_risk') {
    fields.push(
      { label: '持续用药时长', value: extra?.course_duration_hours != null ? `${extra.course_duration_hours} h` : '—' },
      { label: '停药时长', value: extra?.since_last_opioid_hours != null ? `${extra.since_last_opioid_hours} h` : (item?.value != null ? `${item.value} h` : '—') },
      { label: '末次用药', value: fmtTime(extra?.course_last) || '—' },
    )
    return fields
  }

  if (t === 'nurse_reminder') {
    fields.push(
      { label: '提醒类型', value: item?.parameter || item?.rule_id },
      { label: '上次时间', value: fmtTime(item?.source_time) || '—' },
    )
    if (extra?.risk_level) fields.push({ label: '风险等级', value: extra.risk_level === 'high' ? '高' : (extra.risk_level === 'medium' ? '中' : '低') })
    if (extra?.braden != null) fields.push({ label: 'Braden', value: extra.braden })
    if (extra?.rass != null) fields.push({ label: 'RASS', value: extra.rass })
    if (extra?.interval_hours) fields.push({ label: '翻身频率', value: `${extra.interval_hours}h` })
    return fields
  }

  if (t === 'ai_risk') {
    const synd = Array.isArray(extra?.syndromes_detected) ? extra.syndromes_detected.map((s: any) => s?.name).filter(Boolean) : []
    const det = Array.isArray(extra?.deterioration_signals) ? extra.deterioration_signals : []
    const halluc = Array.isArray(extra?.hallucination_flags) ? extra.hallucination_flags : []
    const evid = Array.isArray(extra?.evidence_sources) ? extra.evidence_sources : []
    fields.push(
      { label: '置信度', value: extra?.confidence?.overall || '—' },
      { label: '安全校验', value: extra?.safety_validation?.status || '—' },
      { label: '证据条目', value: evid.length || 0 },
      { label: '幻觉标记', value: halluc.length || 0 },
      { label: '综合征', value: synd.length ? synd.join('、') : '—' },
      { label: '恶化信号', value: det.length ? det.slice(0, 3).join('；') : '—' },
    )
    return fields
  }

  if (t === 'fluid_balance') {
    const win24 = extra?.windows?.['24h'] || {}
    fields.push(
      { label: '体重(kg)', value: extra?.weight_kg },
      { label: '24h入量', value: win24?.intake_ml != null ? `${win24.intake_ml} mL` : '—' },
      { label: '24h出量', value: win24?.output_ml != null ? `${win24.output_ml} mL` : '—' },
      { label: '24h净平衡', value: win24?.net_ml != null ? `${win24.net_ml} mL` : '—' },
      { label: '占体重%', value: win24?.pct_body_weight != null ? `${win24.pct_body_weight}%` : '—' },
    )
    return fields
  }

  if (t === 'delirium_risk') {
    const factors = Array.isArray(extra?.factors) ? extra.factors : []
    const top = factors.slice(0, 3).map((f: any) => `${f.factor}(${f.weight})`).join('；')
    fields.push(
      { label: '风险评分', value: item?.value },
      { label: 'RASS', value: extra?.observations?.latest_rass },
      { label: 'GCS', value: extra?.observations?.latest_gcs },
      { label: '主要因素', value: top || '—' },
    )
    return fields
  }

  if (t === 'sedation_delirium_conversion') {
    fields.push(
      { label: 'RASS', value: extra?.latest_rass ?? item?.value },
      { label: 'GCS', value: extra?.latest_gcs },
      { label: '深镇静时长(h)', value: extra?.deep_sedation_hours },
    )
    return fields
  }

  if (t === 'glucose_variability') {
    fields.push(
      { label: 'CV%', value: extra?.cv_percent ?? item?.value },
      { label: '24h采样数', value: extra?.points_24h },
      { label: '最新血糖', value: extra?.latest_glucose != null ? `${extra.latest_glucose} mmol/L` : '—' },
    )
    return fields
  }

  if (t === 'hypoglycemia') {
    fields.push(
      { label: '当前血糖', value: item?.value != null ? `${item.value} mmol/L` : '—' },
      { label: '阈值', value: item?.condition?.threshold != null ? `${item.condition.threshold} mmol/L` : '—' },
    )
    return fields
  }

  if (t === 'glucose_drop_fast') {
    fields.push(
      { label: '下降速率', value: extra?.drop_rate_mmol_per_h != null ? `${extra.drop_rate_mmol_per_h} mmol/L/h` : item?.value },
      { label: '起点', value: extra?.from?.value != null ? `${extra.from.value} mmol/L` : '—' },
      { label: '终点', value: extra?.to?.value != null ? `${extra.to.value} mmol/L` : '—' },
    )
    return fields
  }

  if (t === 'glucose_recheck_reminder') {
    fields.push(
      { label: '上次血糖时间', value: fmtTime(extra?.last_glucose_time) || '—' },
      { label: '距今(小时)', value: extra?.hours_since_last_check ?? item?.value },
    )
    return fields
  }

  if (t === 'hyperglycemia_no_insulin') {
    fields.push(
      { label: '连续高血糖次数', value: extra?.consecutive_high_count },
      { label: '当前血糖', value: extra?.latest_glucose != null ? `${extra.latest_glucose} mmol/L` : (item?.value != null ? `${item.value} mmol/L` : '—') },
      { label: '阈值', value: extra?.high_threshold_mmol != null ? `${extra.high_threshold_mmol} mmol/L` : '—' },
    )
    return fields
  }

  if (t === 'abx_timeout') {
    fields.push(
      { label: '广谱疗程(h)', value: extra?.broad_duration_hours ?? item?.value },
      { label: '培养结果时间', value: fmtTime(extra?.culture_latest?.time) || '—' },
      { label: '建议', value: extra?.suggestion || '降阶梯评估' },
    )
    return fields
  }

  if (t === 'abx_stop_recommendation') {
    fields.push(
      { label: 'PCT峰值', value: extra?.pct_peak },
      { label: 'PCT当前', value: extra?.pct_latest ?? item?.value },
      { label: '降幅', value: extra?.pct_decline_ratio != null ? `${Math.round(extra.pct_decline_ratio * 100)}%` : '—' },
      { label: '抗生素疗程(h)', value: extra?.antibiotic_duration_hours },
    )
    return fields
  }

  if (t === 'abx_tdm_reminder') {
    fields.push(
      { label: '药物组', value: extra?.drug_group || item?.parameter },
      { label: '疗程(h)', value: extra?.course_duration_hours ?? item?.value },
      { label: '已做TDM', value: extra?.tdm_detected ? '是' : '否' },
    )
    return fields
  }

  if (t === 'abx_duration_exceeded') {
    fields.push(
      { label: '疗程(天)', value: extra?.course_duration_days ?? item?.value },
      { label: '培养阳性依据', value: extra?.culture_positive ? '有' : '无' },
      { label: '培养记录数', value: extra?.culture_records_count },
    )
    return fields
  }

  if (t === 'vte_prophylaxis_omission') {
    fields.push(
      { label: 'Padua', value: extra?.padua_score ?? item?.value },
      { label: 'Caprini', value: extra?.caprini_score },
      { label: '药物预防', value: extra?.has_drug_prophylaxis ? '有' : '无' },
      { label: '机械预防', value: extra?.has_mechanical_prophylaxis ? '有' : '无' },
    )
    return fields
  }

  if (t === 'vte_bleeding_linkage') {
    fields.push(
      { label: 'Padua', value: extra?.padua_score ?? item?.value },
      { label: 'PLT', value: extra?.platelet },
      { label: 'INR', value: extra?.inr },
      { label: '建议', value: extra?.advice || '机械预防优先' },
    )
    return fields
  }

  if (t === 'vte_immobility_no_prophylaxis') {
    fields.push(
      { label: '制动时长(h)', value: extra?.immobility_hours ?? item?.value },
      { label: 'Padua', value: extra?.padua_score },
      { label: 'Caprini', value: extra?.caprini_score },
      { label: '机械预防', value: extra?.has_mechanical_prophylaxis ? '有' : '无' },
    )
    return fields
  }

  if (t === 'nutrition_start_delay') {
    fields.push(
      { label: 'ICU停留(h)', value: extra?.icu_stay_hours ?? item?.value },
      { label: '延迟阈值(h)', value: extra?.start_delay_hours },
      { label: 'EN/PN医嘱', value: extra?.nutrition_order_found ? '有' : '无' },
    )
    return fields
  }

  if (t === 'nutrition_calorie_not_reached') {
    fields.push(
      { label: '覆盖率', value: extra?.coverage_percent != null ? `${extra.coverage_percent}%` : (item?.value != null ? `${item.value}%` : '—') },
      { label: '目标热卡/天', value: extra?.target_kcal_day != null ? `${extra.target_kcal_day} kcal` : '—' },
      { label: '近窗口实际热卡', value: extra?.actual_kcal_window != null ? `${extra.actual_kcal_window} kcal` : '—' },
      { label: '近窗口目标热卡', value: extra?.target_kcal_window != null ? `${extra.target_kcal_window} kcal` : '—' },
    )
    return fields
  }

  if (t === 'nutrition_feeding_intolerance') {
    fields.push(
      { label: '高胃残余次数', value: extra?.high_grv_count ?? 0 },
      { label: '最近GRV', value: extra?.latest_grv_ml != null ? `${extra.latest_grv_ml} mL` : '—' },
      { label: '呕吐次数', value: extra?.vomiting_count ?? 0 },
      { label: '腹胀次数', value: extra?.abdominal_distension_count ?? 0 },
      { label: '喂养中断次数', value: extra?.feeding_interrupt_count ?? 0 },
      { label: '建议', value: extra?.suggestion || '评估喂养方式' },
    )
    return fields
  }

  if (t === 'nutrition_refeeding_risk') {
    fields.push(
      { label: '触发电解质', value: Array.isArray(extra?.triggered_electrolytes) ? extra.triggered_electrolytes.join('/') : '—' },
      { label: 'BMI', value: extra?.malnutrition?.bmi },
      { label: '白蛋白(g/L)', value: extra?.malnutrition?.albumin_g_l },
      { label: 'K下降', value: extra?.k_trend?.drop_ratio != null ? `${Math.round(extra.k_trend.drop_ratio * 100)}%` : '—' },
      { label: 'P下降', value: extra?.phosphate_trend?.drop_ratio != null ? `${Math.round(extra.phosphate_trend.drop_ratio * 100)}%` : '—' },
      { label: 'Mg下降', value: extra?.magnesium_trend?.drop_ratio != null ? `${Math.round(extra.magnesium_trend.drop_ratio * 100)}%` : '—' },
    )
    return fields
  }

  if (t === 'multi_organ_deterioration_trend') {
    const labels = extra?.organ_labels_cn || {}
    const scores = extra?.organ_scores || {}
    const involved = Array.isArray(extra?.involved_organs) ? extra.involved_organs : []
    const involvedText = involved
      .map((k: any) => labels?.[String(k)] || compositeOrganLabelDefault[String(k)] || String(k))
      .join(' / ')

    fields.push(
      { label: 'MODI', value: extra?.modi ?? item?.value },
      { label: '器官系统数', value: extra?.organ_count ?? involved.length },
      { label: '统计窗口', value: extra?.window_hours != null ? `${extra.window_hours}h` : '—' },
      { label: '涉及系统', value: involvedText || '—' },
      { label: '呼吸', value: scores?.respiratory ?? 0 },
      { label: '循环', value: scores?.circulatory ?? 0 },
      { label: '肾脏', value: scores?.renal ?? 0 },
      { label: '凝血', value: scores?.coagulation ?? 0 },
      { label: '肝脏', value: scores?.hepatic ?? 0 },
      { label: '神经', value: scores?.neurologic ?? 0 },
    )
    return fields
  }
  
  if (t === 'liberation_bundle') {
    return [
      { label: '合规度', value: extra?.compliance != null ? `${extra.compliance}/6` : '—' },
      { label: 'A', value: { green: '通过', yellow: '异常', red: '未通过' }[extra?.lights?.['A']] || '—' },
      { label: 'B', value: { green: '通过', yellow: '异常', red: '未通过' }[extra?.lights?.['B']] || '—' },
      { label: 'C', value: { green: '通过', yellow: '异常', red: '未通过' }[extra?.lights?.['C']] || '—' },
      { label: 'D', value: { green: '通过', yellow: '异常', red: '未通过' }[extra?.lights?.['D']] || '—' },
      { label: 'E', value: { green: '通过', yellow: '异常', red: '未通过' }[extra?.lights?.['E']] || '—' },
      { label: 'F', value: { green: '通过', yellow: '异常', red: '未通过' }[extra?.lights?.['F']] || '—' },
    ]
  }

  return []
}

function formatAlertExtra(extra: any) {
  try {
    return JSON.stringify(extra, null, 2)
  } catch {
    return ''
  }
}

function formatAlertValue(a: any) {
  if (!a) return '—'
  const t = String(a.alert_type || '')
  const p = String(a.parameter || '')
  const v = a.value
  const extra = a.extra || {}

  if (t === 'dic') {
    const score = extra?.score ?? v
    return score != null ? `DIC=${score}` : '—'
  }
  if (t === 'ards') {
    const pf = v ?? extra?.pf_ratio
    return pf != null ? `P/F=${Math.round(Number(pf))}` : '—'
  }
  if (t === 'aki') {
    return v != null ? `AKI=${v}期` : '—'
  }
  if (t === 'qsofa') {
    return v != null ? `qSOFA=${v}` : '—'
  }
  if (t === 'sofa' || t === 'septic_shock') {
    return v != null ? `SOFA=${v}` : '—'
  }
  if (t === 'nurse_reminder') {
    return '—'
  }

  if (t === 'fluid_balance') {
    const net = v ?? extra?.windows?.['24h']?.net_ml
    const pct = extra?.max_positive_pct_body_weight
    if (net != null && pct != null) return `净平衡=${net}mL (${pct}%)`
    if (net != null) return `净平衡=${net}mL`
    return '—'
  }

  if (t === 'delirium_risk') {
    return v != null ? `谵妄评分=${v}` : '—'
  }

  if (t === 'sedation_delirium_conversion') {
    const h = extra?.deep_sedation_hours
    return h != null ? `深镇静${h}h` : '—'
  }

  if (t === 'glucose_variability') {
    const cv = extra?.cv_percent ?? v
    return cv != null ? `CV=${cv}%` : '—'
  }

  if (t === 'hypoglycemia') {
    return v != null ? `Glu=${v} mmol/L` : '—'
  }

  if (t === 'glucose_drop_fast') {
    const r = extra?.drop_rate_mmol_per_h ?? v
    return r != null ? `降速=${r} mmol/L/h` : '—'
  }

  if (t === 'glucose_recheck_reminder') {
    const h = extra?.hours_since_last_check ?? v
    return h != null ? `超时${h}h` : '—'
  }

  if (t === 'hyperglycemia_no_insulin') {
    const c = extra?.consecutive_high_count
    const lv = extra?.latest_glucose ?? v
    if (c != null && lv != null) return `${c}次>10, Glu=${lv}`
    return lv != null ? `Glu=${lv}` : '—'
  }

  if (t === 'abx_timeout') {
    const h = extra?.broad_duration_hours ?? v
    return h != null ? `广谱${h}h` : '—'
  }

  if (t === 'abx_stop_recommendation') {
    const pct = extra?.pct_latest ?? v
    const ratio = extra?.pct_decline_ratio
    if (pct != null && ratio != null) return `PCT=${pct}, ↓${Math.round(ratio * 100)}%`
    return pct != null ? `PCT=${pct}` : '—'
  }

  if (t === 'abx_tdm_reminder') {
    const g = extra?.drug_group || p
    return g ? `${g} TDM缺失` : 'TDM缺失'
  }

  if (t === 'abx_duration_exceeded') {
    const d = extra?.course_duration_days ?? v
    return d != null ? `疗程${d}天` : '—'
  }

  if (t === 'af_afl_new_onset') {
    const hr = extra?.hr_peak_in_segment ?? v
    return hr != null ? `AF/AFL HR峰值=${hr}` : '新发AF/AFL'
  }

  if (t === 'brady_hypotension') {
    const hr = extra?.latest_hr ?? v
    const drop = extra?.drop_sbp
    if (hr != null && drop != null) return `HR=${hr}, SBP↓${drop}`
    return hr != null ? `HR=${hr}` : '心动过缓+低压'
  }

  if (t === 'qtc_prolonged') {
    const qtc = extra?.qtc_ms ?? v
    return qtc != null ? `QTc=${qtc}ms` : 'QTc延长'
  }

  if (t === 'opioid_high_dose_resp_risk') {
    const med = extra?.opioid_med_24h_mg ?? v
    return med != null ? `MED24h=${med}mg` : '阿片高剂量'
  }

  if (t === 'opioid_respiratory_depression') {
    const rr = extra?.rr
    const spo2 = extra?.latest_spo2
    if (rr != null && spo2 != null) return `RR=${rr}, SpO₂=${spo2}%`
    if (rr != null) return `RR=${rr}`
    if (spo2 != null) return `SpO₂=${spo2}%`
    return '呼吸抑制风险'
  }

  if (t === 'opioid_withdrawal_risk') {
    const h = extra?.since_last_opioid_hours ?? v
    return h != null ? `停药${h}h` : '戒断风险'
  }

  if (t === 'vte_prophylaxis_omission') {
    const p = extra?.padua_score ?? v
    return p != null ? `Padua=${p}` : '—'
  }

  if (t === 'vte_bleeding_linkage') {
    const p = extra?.padua_score ?? v
    return p != null ? `Padua=${p}, 机械优先` : '机械优先'
  }

  if (t === 'vte_immobility_no_prophylaxis') {
    const h = extra?.immobility_hours ?? v
    return h != null ? `制动${h}h` : '—'
  }

  if (t === 'nutrition_start_delay') {
    const h = extra?.icu_stay_hours ?? v
    return h != null ? `ICU停留${h}h未见EN/PN` : '未见EN/PN'
  }

  if (t === 'nutrition_calorie_not_reached') {
    const pct = extra?.coverage_percent ?? v
    return pct != null ? `热卡达标${pct}%` : '热卡不足'
  }

  if (t === 'nutrition_feeding_intolerance') {
    const grv = extra?.latest_grv_ml ?? v
    if (grv != null) return `GRV=${grv}mL + 喂养中断`
    return '喂养不耐受'
  }

  if (t === 'nutrition_refeeding_risk') {
    const items = extra?.triggered_electrolytes
    if (Array.isArray(items) && items.length > 0) return `电解质下降:${items.join('/')}`
    return v != null ? `最大降幅${v}%` : '再喂养风险'
  }

  if (t === 'multi_organ_deterioration_trend') {
    const modi = extra?.modi ?? v
    const n = extra?.organ_count
    if (modi != null && n != null) return `MODI=${modi} (${n}系统)`
    if (modi != null) return `MODI=${modi}`
    return '多器官恶化趋势'
  }

  if (t === 'lab_threshold') {
    const unit = extra?.unit || ''
    const labelMap: Record<string, string> = {
      k: 'K⁺',
      na: 'Na⁺',
      ica: 'iCa',
      ca: 'Ca',
      lac: 'Lac',
      glu: 'Glu',
      hb: 'Hb',
      plt: 'PLT',
      cr: 'Cr',
      pct: 'PCT',
      inr: 'INR',
      pt: 'PT',
      fib: 'Fib',
      ddimer: 'D-Dimer',
      trop: 'TnI/TnT',
      bnp: 'BNP',
      bil: 'TBil',
      pao2: 'PaO₂',
    }
    const label = labelMap[p] || extra?.raw_name || ''
    if (v == null) return '—'
    return label ? `${label}=${v}${unit}` : `${v}${unit}`
  }

  const unitMap: Record<string, string> = {
    param_HR: ' bpm',
    param_PR: ' bpm',
    param_resp: ' 次/分',
    param_spo2: ' %',
    param_T: ' ℃',
    param_nibp_s: ' mmHg',
    param_nibp_d: ' mmHg',
    param_nibp_m: ' mmHg',
    param_ibp_s: ' mmHg',
    param_ibp_d: ' mmHg',
    param_ibp_m: ' mmHg',
    param_cvp: ' cmH2O',
    param_ETCO2: ' mmHg',
    icp: ' mmHg',
    cpp: ' mmHg',
  }
  if (p && unitMap[p]) {
    return v != null ? `${v}${unitMap[p]}` : '—'
  }

  return v ?? '—'
}

function formatAiError(raw: any) {
  const s = String(raw || '')
  if (!s) return ''
  if (s.includes('503') || s.toLowerCase().includes('service unavailable')) {
    return 'AI服务暂不可用(503)，请稍后重试或检查API Key/额度'
  }
  if (s.toLowerCase().includes('401') || s.toLowerCase().includes('unauthorized')) {
    return 'AI鉴权失败(401)，请检查 LLM_API_KEY'
  }
  if (s.toLowerCase().includes('403')) {
    return 'AI权限不足(403)，请检查账号权限或额度'
  }
  return s
}

function normalizeSeverity(raw: any) {
  const s = String(raw || '').toLowerCase()
  if (s === 'critical' || s.includes('crit')) return 'critical'
  if (s === 'high' || s.includes('high')) return 'high'
  return 'warning'
}

function alertSeverityText(raw: any) {
  const sev = normalizeSeverity(raw)
  if (sev === 'critical') return '危急'
  if (sev === 'high') return '高风险'
  return '预警'
}

function alertTypeText(raw: any) {
  const t = String(raw || '')
  if (!t) return ''
  const map: Record<string, string> = {
    lab_threshold: '检验阈值',
    trend_analysis: '趋势恶化',
    sofa: 'SOFA',
    qsofa: 'qSOFA',
    septic_shock: '脓毒性休克',
    ards: 'ARDS',
    aki: 'AKI',
    dic: 'DIC',
    gi_bleeding: '消化道出血',
    gcs_drop: 'GCS下降',
    hit: 'HIT',
    nephrotoxicity: '肾毒性',
    sedation: '镇静风险',
    qt_risk: 'QT风险',
    af_afl_new_onset: '新发房颤/房扑',
    brady_hypotension: '心动过缓合并低压',
    qtc_prolonged: 'QTc明显延长',
    opioid_high_dose_resp_risk: '阿片高剂量呼吸抑制风险',
    opioid_respiratory_depression: '阿片呼吸抑制',
    opioid_withdrawal_risk: '阿片戒断风险',
    weaning: '撤机评估',
    nurse_reminder: '护理提醒',
    ai_risk: 'AI风险',
    fluid_balance: '液体平衡',
    delirium_risk: '谵妄风险',
    sedation_delirium_conversion: '镇静转谵妄',
    glucose_variability: '血糖波动',
    hypoglycemia: '低血糖',
    glucose_drop_fast: '血糖快速下降',
    glucose_recheck_reminder: '血糖复查提醒',
    hyperglycemia_no_insulin: '高血糖未启胰岛素',
    abx_timeout: '抗生素time-out',
    abx_stop_recommendation: 'PCT停药评估',
    abx_tdm_reminder: '抗生素TDM提醒',
    abx_duration_exceeded: '抗生素疗程超限',
    vte_prophylaxis_omission: 'VTE预防遗漏',
    vte_bleeding_linkage: 'VTE出血风险联动',
    vte_immobility_no_prophylaxis: '制动无VTE预防',
    nutrition_start_delay: '营养启动延迟',
    nutrition_calorie_not_reached: '热卡未达标',
    nutrition_feeding_intolerance: '喂养不耐受',
    nutrition_refeeding_risk: '再喂养风险',
    multi_organ_deterioration_trend: '多器官恶化趋势',
    cvc_review: 'CVC评估',
    foley_review: '导尿管评估',
    ett_extubation_delay: '拔管延迟',
    liberation_bundle: 'ABCDEF Bundle',
    fluid_responsiveness: '容量反应性',
    crrt_filter_clotting: '滤器凝堵',
    crrt_citrate_ica: '枸橼酸 iCa',
    crrt_heparin_act: '肝素 ACT',
    crrt_dose_low: 'CRRT剂量不足',
    renal_dose_adjustment: '肾功能剂量调整',
    driving_pressure: '驱动压升高',
    pplat_high: '平台压升高',
    lung_protective_ventilation: '肺保护通气未达标',
    mechanical_power: '机械功率升高',
    steroid_taper_after_vaso: '激素减停提醒',
    steroid_long_term_taper: '长程激素减停',
    steroid_hyperglycemia: '激素相关高血糖',
  }
  return map[t] || t.split('_').join(' ')
}

function alertCategoryText(raw: any) {
  const t = String(raw || '')
  if (!t) return ''
  const map: Record<string, string> = {
    vital_signs: '生命体征',
    syndrome: '综合征',
    lab_results: '检验',
    trend: '趋势',
    nurse: '护理',
    ai: 'AI',
    ventilator: '呼吸机',
    drug_safety: '用药安全',
    fluid_balance: '液体平衡',
    glycemic_control: '血糖管理',
    antibiotic_stewardship: '抗菌药管理',
    vte_prophylaxis: 'VTE预防',
    nutrition_monitor: '营养监测',
    composite_deterioration: '复合恶化',
    device_management: '装置管理',
    bundle: 'Bundle',
    hemodynamic: '血流动力学',
    crrt: 'CRRT',
    dose_adjustment: '剂量调整',
  }
  return map[t] || t.split('_').join(' ')
}

function labFlag(item: any) {
  const flag = item.resultFlag || item.abnormalFlag || item.flag
  if (!flag) return ''
  const f = String(flag)
  if (f.includes('H') || f.includes('↑')) return 'lab-high'
  if (f.includes('L') || f.includes('↓')) return 'lab-low'
  return ''
}

function backToList() {
  router.push({ path: '/', query: route.query })
}

async function loadTrend() {
  const patientId = route.params.id as string
  if (!patientId) return
  try {
    const res = await getPatientVitalsTrend(patientId, trendWindow.value)
    trendPoints.value = res.data.points || []
  } catch (e) {
    console.error('加载趋势失败', e)
  }
}

async function loadLabs() {
  const patientId = route.params.id as string
  if (!patientId) return
  try {
    const res = await getPatientLabs(patientId)
    labs.value = res.data.exams || []
  } catch (e) {
    console.error('加载检验失败', e)
  }
}

async function loadDrugs() {
  const patientId = route.params.id as string
  if (!patientId) return
  try {
    const res = await getPatientDrugs(patientId)
    drugs.value = res.data.records || []
  } catch (e) {
    console.error('加载用药失败', e)
  }
}

async function loadAssessments() {
  const patientId = route.params.id as string
  if (!patientId) return
  try {
    const res = await getPatientAssessments(patientId)
    assessments.value = res.data.records || []
  } catch (e) {
    console.error('加载评估失败', e)
  }
}

async function loadAlerts() {
  const patientId = route.params.id as string
  if (!patientId) return
  try {
    const res = await getPatientAlerts(patientId)
    alerts.value = res.data.records || []
  } catch (e) {
    console.error('加载预警失败', e)
  }
}

async function loadAiLab() {
  if (aiLabLoading.value) return
  const patientId = route.params.id as string
  if (!patientId) return
  aiLabError.value = ''
  aiLabLoading.value = true
  try {
    const res = await getAiLabSummary(patientId)
    aiLabSummary.value = res.data.summary || ''
    aiLabError.value = formatAiError(res.data.error || '')
  } catch (e) {
    aiLabError.value = 'AI服务不可用'
  } finally {
    aiLabLoading.value = false
  }
}

async function loadAiRules() {
  if (aiRuleLoading.value) return
  const patientId = route.params.id as string
  if (!patientId) return
  aiRuleError.value = ''
  aiRuleLoading.value = true
  try {
    const res = await getAiRuleRecommendations(patientId)
    aiRuleText.value = res.data.recommendations || ''
    aiRuleError.value = formatAiError(res.data.error || '')
  } catch (e) {
    aiRuleError.value = 'AI服务不可用'
  } finally {
    aiRuleLoading.value = false
  }
}

async function loadAiRisk() {
  if (aiRiskLoading.value) return
  const patientId = route.params.id as string
  if (!patientId) return
  aiRiskError.value = ''
  aiRiskLoading.value = true
  try {
    const res = await getAiRiskForecast(patientId)
    aiRiskText.value = res.data.risk_summary || ''
    aiRiskError.value = formatAiError(res.data.error || '')
  } catch (e) {
    aiRiskError.value = 'AI服务不可用'
  } finally {
    aiRiskLoading.value = false
  }
}

async function loadAiHandoff() {
  if (aiHandoffLoading.value) return
  const patientId = route.params.id as string
  if (!patientId) return
  aiHandoffError.value = ''
  aiHandoffLoading.value = true
  try {
    const res = await getPatientHandoffSummary(patientId)
    aiHandoff.value = res.data.summary || null
    aiHandoffError.value = formatAiError(res.data.error || '')
  } catch (e) {
    aiHandoffError.value = 'AI服务不可用'
  } finally {
    aiHandoffLoading.value = false
  }
}

async function loadAiAll() {
  if (aiAutoLoaded.value) return
  aiAutoLoaded.value = true
  await Promise.allSettled([loadAiLab(), loadAiRules(), loadAiRisk(), loadAiHandoff(), loadKnowledgeDocs()])
}

function resetDetailState() {
  patient.value = null
  vitals.value = null
  trendPoints.value = []
  labs.value = []
  drugs.value = []
  assessments.value = []
  alerts.value = []
  aiLabSummary.value = ''
  aiRuleText.value = ''
  aiRiskText.value = ''
  aiHandoff.value = null
  knowledgeDocs.value = []
  selectedKnowledgeDocId.value = ''
  selectedKnowledgeDoc.value = null
  aiLabError.value = ''
  aiRuleError.value = ''
  aiRiskError.value = ''
  aiHandoffError.value = ''
  knowledgeError.value = ''
  aiAutoLoaded.value = false
}

async function loadDetailPage() {
  const patientId = route.params.id as string
  if (!patientId) return
  await Promise.allSettled([
    (async () => {
      try {
        const res = await getPatientDetail(patientId)
        patient.value = res.data.patient || null
      } catch (e) {
        console.error('加载患者失败', e)
      }
    })(),
    (async () => {
      try {
        const vRes = await getPatientVitals(patientId)
        vitals.value = vRes.data.vitals || null
      } catch (e) {
        console.error('加载生命体征失败', e)
      }
    })(),
    loadTrend(),
    loadLabs(),
    loadDrugs(),
    loadAssessments(),
    loadAlerts(),
    loadAiAll(),
  ])
}

watch(trendWindow, () => {
  if (activeTab.value === 'trend') loadTrend()
})

watch(
  () => route.params.id,
  (next, prev) => {
    if (next && next !== prev) {
      resetDetailState()
      void loadDetailPage()
    }
  }
)

onMounted(() => {
  void loadDetailPage()
})
</script>

<style scoped>
.detail-container {
  max-width: 1680px;
  margin: 0 auto;
  padding: 0 12px 16px;
}
.detail-page-header {
  background: #112240;
  border-radius: 8px;
  margin-bottom: 16px;
  border: 1px solid #1e3a5f;
}
.detail-content {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(420px, 2fr);
  gap: 12px;
  margin-bottom: 16px;
}
.info-card {
  background: #112240;
  border: 1px solid #1e3a5f;
  border-radius: 8px;
}
.vitals-card :deep(.ant-card-body) {
  padding-top: 8px;
}
.vitals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}
.acid-base-card {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #214368;
  background: rgba(15, 33, 56, 0.72);
}
.acid-base-head,
.acid-base-summary,
.acid-base-metrics,
.acid-base-components {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.acid-base-head {
  justify-content: space-between;
  margin-bottom: 6px;
  color: #cbd5f5;
}
.acid-base-summary {
  margin-bottom: 6px;
}
.acid-pill,
.acid-comp {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}
.acid-primary { background: rgba(59, 130, 246, 0.16); color: #93c5fd; }
.acid-secondary { background: rgba(245, 158, 11, 0.16); color: #fbbf24; }
.acid-tertiary { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
.acid-base-metrics { color: #9fb3d1; font-size: 12px; margin-bottom: 6px; }
.acid-comp { background: rgba(148, 163, 184, 0.14); color: #cbd5f5; }
.acid-comp.abnormal { background: rgba(239, 68, 68, 0.18); color: #fca5a5; }
.v-item {
  background: #0d1f3a;
  border: 1px solid #1b2d4d;
  border-radius: 6px;
  padding: 10px 12px;
}
.v-label {
  display: block;
  font-size: 11px;
  color: #7aa2d6;
  margin-bottom: 4px;
}
.v-value {
  font-size: 16px;
  font-weight: 700;
  color: #e6f0ff;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.vitals-empty {
  color: #6b7280;
  font-size: 12px;
  padding: 10px 0;
}
.tabs-card {
  background: #0c1626;
  border: 1px solid #15243a;
}
.tabs-card :deep(.ant-card-body) {
  padding: 14px 16px 18px;
  overflow: visible;
}
.tabs-card :deep(.ant-tabs-nav) {
  margin-bottom: 14px;
}
.tabs-card :deep(.ant-tabs-nav-list) {
  flex-wrap: wrap;
  gap: 4px;
}
.tabs-card :deep(.ant-tabs-tab) {
  margin: 0 !important;
  padding: 8px 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.chart-wrap {
  height: 360px;
}
.tab-empty {
  color: #6b7280;
  font-size: 12px;
  padding: 12px;
}
.lab-head {
  display: flex;
  justify-content: space-between;
  color: #d1d5db;
  margin-bottom: 6px;
}
.lab-items {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.lab-item {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #111827;
  color: #9ca3af;
}
.lab-item.lab-high { color: #fca5a5; background: #3f1d1d; }
.lab-item.lab-low { color: #93c5fd; background: #172554; }
.modi-panel {
  margin-bottom: 12px;
  border: 1px solid #1a385d;
  border-radius: 12px;
  padding: 12px;
  background: linear-gradient(180deg, rgba(13, 34, 58, 0.95) 0%, rgba(10, 25, 45, 0.95) 100%);
}
.modi-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.modi-title {
  color: #eaf2ff;
  font-size: 15px;
  font-weight: 800;
}
.modi-sub {
  margin-top: 4px;
  color: #8da4c7;
  font-size: 12px;
}
.modi-kpi-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(100px, 1fr));
  gap: 8px;
}
.modi-kpi {
  border: 1px solid #274970;
  border-radius: 8px;
  padding: 8px 10px;
  background: rgba(9, 22, 40, 0.75);
  text-align: right;
}
.modi-kpi > span {
  display: block;
  color: #8da4c7;
  font-size: 11px;
}
.modi-kpi > strong {
  color: #f1f6ff;
  font-size: 18px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.modi-organs {
  margin-top: 8px;
  color: #a4b8d5;
  font-size: 12px;
}
.modi-chart {
  height: 300px;
  margin-top: 6px;
}
.alert-feed {
  display: grid;
  gap: 12px;
  padding-right: 2px;
}
.alert-card {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 12px;
}
.alert-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 9px;
}
.alert-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  flex: 0 0 auto;
}
.alert-line {
  width: 2px;
  flex: 1 1 auto;
  margin-top: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #1f3c67 0%, #0f233f 100%);
}
.alert-body {
  border: 1px solid #173153;
  border-left: 4px solid #f59e0b;
  border-radius: 10px;
  padding: 12px 14px;
  background:
    linear-gradient(180deg, rgba(19, 35, 58, 0.96) 0%, rgba(12, 25, 43, 0.96) 100%);
}
.alert-card.sev-high .alert-body { border-left-color: #f97316; }
.alert-card.sev-critical .alert-body { border-left-color: #f43f5e; }
.alert-dot.sev-warning { background: #f59e0b; box-shadow: 0 0 8px #f59e0b99; }
.alert-dot.sev-high { background: #f97316; box-shadow: 0 0 8px #f9731699; }
.alert-dot.sev-critical { background: #f43f5e; box-shadow: 0 0 10px #f43f5e99; }

.alert-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.alert-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
}
.alert-title {
  margin: 0;
  color: #eaf2ff;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.25;
}
.alert-pill {
  display: inline-flex;
  align-items: center;
  height: 20px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2px;
  border: 1px solid transparent;
}
.alert-pill.sev-warning {
  color: #fcd34d;
  background: #3f2d07;
  border-color: #6a4b0d;
}
.alert-pill.sev-high {
  color: #fdba74;
  background: #41210b;
  border-color: #7c3816;
}
.alert-pill.sev-critical {
  color: #fda4af;
  background: #47131d;
  border-color: #7f1d32;
}
.alert-value {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 18px;
  line-height: 1.2;
  color: #f1f6ff;
  font-weight: 800;
  text-align: right;
  white-space: nowrap;
}
.alert-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.alert-meta > span {
  font-size: 11px;
  color: #8da4c7;
  padding: 2px 8px;
  border-radius: 999px;
  background: #10233d;
  border: 1px solid #1b3a60;
}
.alert-rule {
  margin-top: 8px;
  font-size: 12px;
  color: #d7e6ff;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.alert-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px 10px;
  margin-top: 10px;
}
.alert-detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: #9ca3af;
  background: #0f2038;
  border: 1px solid #1c3d64;
  border-radius: 6px;
  padding: 6px 8px;
}
.detail-label { color: #7aa2d6; }
.detail-value { color: #e5e7eb; font-weight: 600; }
.alert-extra {
  margin-top: 10px;
  white-space: pre-wrap;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
  background: #0b1626;
  border: 1px solid #19304d;
  border-radius: 6px;
  padding: 8px;
}
.ai-risk-panel {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}
.ai-risk-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.ai-risk-summary,
.ai-risk-card {
  border: 1px solid #214064;
  border-radius: 8px;
  background: #0d2036;
  padding: 10px 12px;
}
.ai-risk-summary {
  display: grid;
  gap: 4px;
  min-width: 240px;
}
.ai-risk-summary strong,
.ai-risk-card strong {
  color: #eef4ff;
}
.ai-risk-summary span,
.ai-risk-card p {
  color: #b9cae8;
  font-size: 12px;
  margin: 0;
}
.ai-risk-feedback {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.ai-risk-organ-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}
.ai-risk-organ {
  border: 1px solid #1c3a5b;
  border-radius: 8px;
  background: #0c1d31;
  padding: 8px 10px;
  transition: opacity .2s ease;
}
.ai-risk-organ-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.ai-risk-organ-name {
  color: #d9e8ff;
  font-weight: 700;
}
.ai-risk-organ-status {
  color: #93c5fd;
  font-size: 11px;
}
.ai-risk-organ-evidence {
  margin-top: 6px;
  color: #a9bbda;
  font-size: 11px;
  line-height: 1.5;
}
.ai-risk-organ-conf {
  margin-top: 6px;
  color: #7fa0d0;
  font-size: 11px;
}
.ai-risk-section {
  border: 1px solid #1d3554;
  border-radius: 8px;
  background: #0a1829;
  padding: 10px 12px;
}
.ai-risk-section-title {
  color: #dbe9ff;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}
.ai-risk-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  color: #bfd0ec;
  font-size: 12px;
}
.ai-risk-list-warning {
  color: #fecaca;
}
.ai-risk-list-hallucination {
  list-style: none;
  padding-left: 0;
}
.hallucination-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 999px;
  width: fit-content;
  max-width: 100%;
  border: 1px solid transparent;
}
.hallucination-warning {
  color: #fde68a;
  background: #3c2d06;
  border-color: #6b4f11;
}
.hallucination-high {
  color: #fecaca;
  background: #47131d;
  border-color: #7f1d32;
}
.ai-risk-evidence-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}
.ai-evidence-link {
  color: #93c5fd;
  cursor: pointer;
}
.ai-evidence-link:hover {
  color: #bfdbfe;
}
.ai-evidence-inline {
  margin-left: 4px;
}
.ai-evidence-popover {
  max-width: 420px;
  display: grid;
  gap: 6px;
  color: #334155;
}
.ai-evidence-quote {
  max-width: 420px;
  white-space: pre-wrap;
  line-height: 1.6;
}
.ai-risk-card {
  display: grid;
  gap: 8px;
}
.ai-confidence-low {
  opacity: 0.58;
}
.ai-confidence-medium {
  opacity: 0.82;
}
.ai-confidence-high {
  opacity: 1;
}
.ai-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 12px;
}
.ai-card {
  background: #0f1a2b;
  border: 1px solid #1a2c46;
  min-height: 520px;
}
.ai-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ai-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 8px;
  flex-wrap: wrap;
}
.ai-card-note {
  font-size: 11px;
  color: #7f97bd;
}
.ai-empty {
  color: #8898b5;
  font-size: 12px;
  padding: 8px 2px;
}
.ai-rich {
  margin-top: 2px;
  color: #d7e3fa;
  font-size: 12px;
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-height: 62vh;
  overflow: auto;
  padding-right: 4px;
}
.ai-rich :deep(h4) {
  margin: 10px 0 4px;
  font-size: 14px;
  color: #f1f5ff;
}
.ai-rich :deep(p) {
  margin: 0;
}
.ai-rich :deep(.ai-li) {
  padding-left: 4px;
}
.ai-rich :deep(.ai-blank) {
  height: 8px;
}
.ai-rich :deep(code) {
  background: #0b1425;
  border: 1px solid #1c2d4a;
  border-radius: 3px;
  padding: 1px 4px;
  color: #b8c9eb;
}
.kb-browser {
  display: grid;
  gap: 8px;
}
.kb-doc-meta {
  border: 1px solid #1d3554;
  border-radius: 8px;
  background: #0a1829;
  padding: 10px 12px;
}
.kb-doc-meta p {
  margin: 0 0 4px;
  color: #c3d3ec;
  font-size: 12px;
}
.kb-chunk-list {
  display: grid;
  gap: 8px;
  max-height: 52vh;
  overflow: auto;
}
.kb-chunk-item {
  border: 1px solid #1c3a5b;
  border-radius: 8px;
  background: #0c1d31;
  padding: 10px 12px;
}
.kb-chunk-title {
  color: #dce8fb;
  font-weight: 700;
  margin-bottom: 6px;
  font-size: 12px;
}
.kb-chunk-content {
  white-space: pre-wrap;
  color: #b6c8e4;
  line-height: 1.65;
  font-size: 12px;
}
.ai-rule-table {
  margin-top: 2px;
  width: 100%;
}
.ai-rule-wrap {
  max-height: 62vh;
  overflow: auto;
  border: 1px solid #1b2f4d;
  border-radius: 8px;
}
.ai-rule-table :deep(.ant-table) {
  background: #0f1a2b;
}
.ai-rule-table :deep(.ant-table-content) {
  overflow-x: auto !important;
}
.ai-rule-table :deep(table) {
  min-width: 920px;
}
.ai-rule-table :deep(.ant-table-thead > tr > th) {
  background: #11213a;
  color: #c9d8f3;
  border-bottom-color: #213a5d;
  white-space: nowrap;
}
.ai-rule-table :deep(.ant-table-tbody > tr > td) {
  background: #0f1a2b;
  color: #d7e3fa;
  border-bottom-color: #1d3352;
  white-space: nowrap;
}
.ai-rule-table :deep(.ant-table-tbody > tr > td:nth-child(1)),
.ai-rule-table :deep(.ant-table-tbody > tr > td:nth-child(5)) {
  white-space: normal;
  word-break: break-word;
}
.ai-error {
  color: #f87171;
  font-size: 11px;
  margin-top: 6px;
}

/* ===== Light Theme ===== */
:global(html[data-theme='light']) .detail-container {
  background: #f4f7fb;
}
:global(html[data-theme='light']) .detail-page-header {
  background: #ffffff;
  border: 1px solid #d9e2f1;
}
:global(html[data-theme='light']) .detail-page-header :deep(.ant-page-header-heading-title) {
  color: #0f172a;
}
:global(html[data-theme='light']) .detail-page-header :deep(.ant-page-header-heading-sub-title) {
  color: #64748b;
}
:global(html[data-theme='light']) .info-card {
  background: #ffffff;
  border-color: #d9e2f1;
}
:global(html[data-theme='light']) .info-card :deep(.ant-card-head) {
  border-bottom-color: #e2eaf5;
}
:global(html[data-theme='light']) .info-card :deep(.ant-card-head-title) {
  color: #0f172a;
}
:global(html[data-theme='light']) .info-card :deep(.ant-card-body),
:global(html[data-theme='light']) .info-card p {
  color: #334155;
}
:global(html[data-theme='light']) .v-item {
  background: #f5f8fe;
  border-color: #d9e2f1;
}
:global(html[data-theme='light']) .v-label { color: #60759a; }
:global(html[data-theme='light']) .v-value { color: #1f2937; }
:global(html[data-theme='light']) .tabs-card {
  background: #ffffff;
  border-color: #d9e2f1;
}
:global(html[data-theme='light']) .tab-empty { color: #64748b; }
:global(html[data-theme='light']) .lab-head { color: #334155; }
:global(html[data-theme='light']) .lab-item {
  background: #f5f8fe;
  color: #51627f;
  border: 1px solid #dce5f2;
}
:global(html[data-theme='light']) .lab-item.lab-high {
  color: #be123c;
  background: #fff1f2;
  border-color: #fecdd3;
}
:global(html[data-theme='light']) .lab-item.lab-low {
  color: #1d4ed8;
  background: #eff6ff;
  border-color: #bfdbfe;
}
:global(html[data-theme='light']) .modi-panel {
  background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
  border-color: #d9e2f1;
}
:global(html[data-theme='light']) .modi-title { color: #0f172a; }
:global(html[data-theme='light']) .modi-sub { color: #64748b; }
:global(html[data-theme='light']) .modi-kpi {
  background: #f5f8fe;
  border-color: #dce5f3;
}
:global(html[data-theme='light']) .modi-kpi > span { color: #5e7395; }
:global(html[data-theme='light']) .modi-kpi > strong { color: #1f2937; }
:global(html[data-theme='light']) .modi-organs { color: #475569; }
:global(html[data-theme='light']) .alert-line {
  background: linear-gradient(180deg, #b3c3dc 0%, #d4deee 100%);
}
:global(html[data-theme='light']) .alert-body {
  background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
  border-color: #dce5f3;
}
:global(html[data-theme='light']) .alert-title { color: #0f172a; }
:global(html[data-theme='light']) .alert-value { color: #1f2937; }
:global(html[data-theme='light']) .alert-meta > span {
  background: #f2f6fc;
  border-color: #d9e2f1;
  color: #5e7395;
}
:global(html[data-theme='light']) .alert-rule { color: #334155; }
:global(html[data-theme='light']) .alert-detail-item {
  background: #f6f9ff;
  border-color: #dce5f3;
  color: #51627f;
}
:global(html[data-theme='light']) .detail-label { color: #5e7395; }
:global(html[data-theme='light']) .detail-value { color: #1f2937; }
:global(html[data-theme='light']) .alert-extra {
  background: #f8fbff;
  border-color: #dce6f3;
  color: #60759a;
}
:global(html[data-theme='light']) .ai-risk-summary,
:global(html[data-theme='light']) .ai-risk-card {
  background: #f7fbff;
  border-color: #d7e6f5;
}
:global(html[data-theme='light']) .ai-risk-summary strong,
:global(html[data-theme='light']) .ai-risk-card strong {
  color: #0f172a;
}
:global(html[data-theme='light']) .ai-risk-summary span,
:global(html[data-theme='light']) .ai-risk-card p {
  color: #475569;
}
:global(html[data-theme='light']) .ai-risk-organ {
  background: #f8fbff;
  border-color: #dbe7f5;
}
:global(html[data-theme='light']) .ai-risk-organ-name {
  color: #0f172a;
}
:global(html[data-theme='light']) .ai-risk-organ-status {
  color: #2563eb;
}
:global(html[data-theme='light']) .ai-risk-organ-evidence,
:global(html[data-theme='light']) .ai-risk-organ-conf {
  color: #475569;
}
:global(html[data-theme='light']) .ai-risk-section {
  background: #f8fbff;
  border-color: #dce7f5;
}
:global(html[data-theme='light']) .ai-risk-section-title {
  color: #0f172a;
}
:global(html[data-theme='light']) .ai-risk-list {
  color: #475569;
}
:global(html[data-theme='light']) .ai-risk-list-warning {
  color: #b91c1c;
}
:global(html[data-theme='light']) .hallucination-warning {
  color: #92400e;
  background: #fffbeb;
  border-color: #fcd34d;
}
:global(html[data-theme='light']) .hallucination-high {
  color: #b91c1c;
  background: #fff1f2;
  border-color: #fecdd3;
}
:global(html[data-theme='light']) .ai-evidence-link {
  color: #2563eb;
}
:global(html[data-theme='light']) .ai-card {
  background: #ffffff;
  border-color: #d9e2f1;
}
:global(html[data-theme='light']) .ai-card-note { color: #64748b; }
:global(html[data-theme='light']) .ai-empty { color: #64748b; }
:global(html[data-theme='light']) .ai-rich { color: #334155; }
:global(html[data-theme='light']) .ai-rich :deep(h4) { color: #0f172a; }
:global(html[data-theme='light']) .ai-rich :deep(code) {
  background: #f2f6fc;
  border-color: #dce6f3;
  color: #3b4e6d;
}
:global(html[data-theme='light']) .kb-doc-meta {
  background: #f8fbff;
  border-color: #dce7f5;
}
:global(html[data-theme='light']) .kb-doc-meta p {
  color: #475569;
}
:global(html[data-theme='light']) .kb-chunk-item {
  background: #f8fbff;
  border-color: #dbe7f5;
}
:global(html[data-theme='light']) .kb-chunk-title {
  color: #0f172a;
}
:global(html[data-theme='light']) .kb-chunk-content {
  color: #475569;
}
:global(html[data-theme='light']) .ai-rule-wrap {
  border-color: #dce5f3;
}
:global(html[data-theme='light']) .ai-rule-table :deep(.ant-table) {
  background: #ffffff;
}
:global(html[data-theme='light']) .ai-rule-table :deep(.ant-table-thead > tr > th) {
  background: #f1f6ff;
  color: #334155;
  border-bottom-color: #dce5f3;
}
:global(html[data-theme='light']) .ai-rule-table :deep(.ant-table-tbody > tr > td) {
  background: #ffffff;
  color: #334155;
  border-bottom-color: #e6edf8;
}
:global(html[data-theme='light']) .ai-error {
  color: #dc2626;
}

@media (max-width: 1500px) {
  .ai-grid {
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  }
}

@media (max-width: 980px) {
  .detail-container {
    padding: 0 8px 14px;
  }
  .detail-content {
    grid-template-columns: 1fr;
  }
  .tabs-card :deep(.ant-card-body) {
    padding: 10px 10px 14px;
  }
  .ai-grid {
    grid-template-columns: 1fr;
  }
  .ai-card {
    min-height: 0;
  }
  .ai-rule-wrap,
  .ai-rich {
    max-height: 56vh;
  }
  .alert-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .alert-value {
    text-align: left;
    font-size: 16px;
  }
  .modi-chart {
    height: 260px;
  }
}

@media (max-width: 640px) {
  .detail-page-header {
    margin-bottom: 10px;
  }
  .tabs-card :deep(.ant-tabs-nav) {
    overflow-x: auto;
  }
  .tabs-card :deep(.ant-tabs-nav-list) {
    flex-wrap: nowrap;
    width: max-content;
  }
  .tab-toolbar {
    flex-wrap: wrap;
    gap: 8px;
  }
  .modi-kpi-group {
    width: 100%;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .modi-kpi {
    text-align: left;
  }
  .modi-chart {
    height: 240px;
  }
  .lab-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
  .alert-card {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .alert-rail {
    display: none;
  }
  .alert-body {
    padding: 10px 10px;
  }
}
</style>
