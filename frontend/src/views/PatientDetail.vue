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
          <div class="tab-toolbar">
            <a-radio-group v-model:value="trendWindow" size="small">
              <a-radio-button value="24h">24h</a-radio-button>
              <a-radio-button value="48h">48h</a-radio-button>
              <a-radio-button value="7d">7d</a-radio-button>
            </a-radio-group>
            <a-button size="small" @click="loadTrend">刷新</a-button>
          </div>
          <div v-if="trendPoints.length" class="chart-wrap">
            <VChart :option="trendOption" autoresize />
          </div>
          <div v-else class="tab-empty">暂无趋势数据</div>
        </a-tab-pane>

        <a-tab-pane key="labs" tab="检验结果时间线">
          <a-timeline>
            <a-timeline-item v-for="exam in labs" :key="exam.requestId">
              <div class="lab-head">
                <strong>{{ exam.examName || exam.requestName || '检验' }}</strong>
                <span>{{ fmtTime(exam.requestTime) }}</span>
              </div>
              <div class="lab-items">
                <span
                  v-for="item in exam.items || []"
                  :key="item.itemId || item.itemCode || item.itemName"
                  :class="['lab-item', labFlag(item)]"
                >
                  {{ item.itemName || item.itemCnName || '指标' }}:
                  {{ item.result || item.resultValue || item.value }}
                  {{ item.unit || '' }}
                </span>
              </div>
            </a-timeline-item>
          </a-timeline>
          <div v-if="!labs.length" class="tab-empty">暂无检验记录</div>
        </a-tab-pane>

        <a-tab-pane key="drugs" tab="用药记录">
          <a-table
            :columns="drugColumns"
            :data-source="drugs"
            size="small"
            :pagination="{ pageSize: 8 }"
            row-key="_id"
          />
        </a-tab-pane>

        <a-tab-pane key="assess" tab="护理评估">
          <a-table
            :columns="assessmentColumns"
            :data-source="assessments"
            size="small"
            :pagination="{ pageSize: 8 }"
            row-key="time"
          />
        </a-tab-pane>

        <a-tab-pane key="alerts" tab="预警历史">
          <div v-if="alerts.length" class="alert-feed">
            <article
              v-for="(item, idx) in alerts"
              :key="item._id || item.created_at || idx"
              :class="['alert-card', `sev-${normalizeSeverity(item.severity)}`]"
            >
              <div class="alert-rail">
                <span :class="['alert-dot', `sev-${normalizeSeverity(item.severity)}`]"></span>
                <span v-if="idx < alerts.length - 1" class="alert-line"></span>
              </div>

              <div class="alert-body">
                <div class="alert-head">
                  <div class="alert-title-row">
                    <h4 class="alert-title">{{ item.name || item.rule_id || '预警' }}</h4>
                    <span :class="['alert-pill', `sev-${normalizeSeverity(item.severity)}`]">
                      {{ alertSeverityText(item.severity) }}
                    </span>
                  </div>
                  <div class="alert-value">{{ formatAlertValue(item) }}</div>
                </div>

                <div class="alert-meta">
                  <span>{{ fmtTime(item.created_at) || '时间未知' }}</span>
                  <span v-if="item.alert_type">{{ alertTypeText(item.alert_type) }}</span>
                  <span v-if="item.category">{{ alertCategoryText(item.category) }}</span>
                </div>

                <div
                  v-if="item.parameter || item.condition?.operator || item.condition?.threshold"
                  class="alert-rule"
                >
                  {{ item.parameter || '参数' }}
                  {{ item.condition?.operator || '' }}
                  {{ item.condition?.threshold || '' }}
                </div>

                <div v-if="alertDetailFields(item).length" class="alert-detail-grid">
                  <div v-for="f in alertDetailFields(item)" :key="f.label" class="alert-detail-item">
                    <span class="detail-label">{{ f.label }}</span>
                    <span class="detail-value">{{ f.value ?? '—' }}</span>
                  </div>
                </div>
                <pre v-else-if="item.extra" class="alert-extra">{{ formatAlertExtra(item.extra) }}</pre>
              </div>
            </article>
          </div>
          <div v-if="!alerts.length" class="tab-empty">暂无预警记录</div>
        </a-tab-pane>

        <a-tab-pane key="ai" tab="AI辅助">
          <div class="ai-grid">
            <a-card title="检验异常摘要" :bordered="false" class="ai-card">
              <div class="ai-card-head">
                <span class="ai-card-note">进入详情自动生成</span>
                <a-button size="small" type="link" :loading="aiLabLoading" @click="loadAiLab">重新生成</a-button>
              </div>
              <a-spin :spinning="aiLabLoading">
                <div v-if="aiLabSummary" class="ai-rich" v-html="renderAiRichText(aiLabSummary)"></div>
                <div v-else class="ai-empty">暂无内容</div>
              </a-spin>
              <div v-if="aiLabError" class="ai-error">{{ aiLabError }}</div>
            </a-card>
            <a-card title="规则推荐" :bordered="false" class="ai-card">
              <div class="ai-card-head">
                <span class="ai-card-note">进入详情自动生成</span>
                <a-button size="small" type="link" :loading="aiRuleLoading" @click="loadAiRules">重新生成</a-button>
              </div>
              <a-spin :spinning="aiRuleLoading">
                <div v-if="aiRuleRows.length" class="ai-rule-wrap">
                  <a-table
                    size="small"
                    class="ai-rule-table"
                    :columns="aiRuleColumns"
                    :data-source="aiRuleRows"
                    :pagination="{ pageSize: 8, hideOnSinglePage: true }"
                    :scroll="{ x: 920 }"
                    row-key="key"
                  />
                </div>
                <div v-else-if="aiRuleText" class="ai-rich" v-html="renderAiRichText(aiRuleText)"></div>
                <div v-else class="ai-empty">暂无内容</div>
              </a-spin>
              <div v-if="aiRuleError" class="ai-error">{{ aiRuleError }}</div>
            </a-card>
            <a-card title="恶化风险预测" :bordered="false" class="ai-card">
              <div class="ai-card-head">
                <span class="ai-card-note">进入详情自动生成</span>
                <a-button size="small" type="link" :loading="aiRiskLoading" @click="loadAiRisk">重新生成</a-button>
              </div>
              <a-spin :spinning="aiRiskLoading">
                <div v-if="aiRiskText" class="ai-rich" v-html="renderAiRichText(aiRiskText)"></div>
                <div v-else class="ai-empty">暂无内容</div>
              </a-spin>
              <div v-if="aiRiskError" class="ai-error">{{ aiRiskError }}</div>
            </a-card>
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
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
} from '../api'

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

const aiLabSummary = ref('')
const aiRuleText = ref('')
const aiRiskText = ref('')
const aiLabError = ref('')
const aiRuleError = ref('')
const aiRiskError = ref('')
const aiLabLoading = ref(false)
const aiRuleLoading = ref(false)
const aiRiskLoading = ref(false)
const aiAutoLoaded = ref(false)

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
    fields.push(
      { label: '指标', value: extra?.raw_name || item?.parameter },
      { label: '结果', value: item?.value != null ? `${item.value}${unit}` : '—' },
      { label: '标志', value: extra?.raw_flag },
    )
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

  if (t === 'nurse_reminder') {
    fields.push(
      { label: '评估项', value: item?.parameter || item?.rule_id },
      { label: '上次时间', value: fmtTime(item?.source_time) || '—' },
    )
    return fields
  }

  if (t === 'ai_risk') {
    const synd = Array.isArray(extra?.syndromes_detected) ? extra.syndromes_detected.map((s: any) => s?.name).filter(Boolean) : []
    const det = Array.isArray(extra?.deterioration_signals) ? extra.deterioration_signals : []
    fields.push(
      { label: '综合征', value: synd.length ? synd.join('、') : '—' },
      { label: '恶化信号', value: det.length ? det.slice(0, 3).join('；') : '—' },
    )
    return fields
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
    weaning: '撤机评估',
    nurse_reminder: '护理提醒',
    ai_risk: 'AI风险',
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

async function loadAiAll() {
  if (aiAutoLoaded.value) return
  aiAutoLoaded.value = true
  await Promise.allSettled([loadAiLab(), loadAiRules(), loadAiRisk()])
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
  aiLabError.value = ''
  aiRuleError.value = ''
  aiRiskError.value = ''
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
}
</style>
