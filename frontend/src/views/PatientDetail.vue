<template>
  <div class="detail-container">
    <a-page-header
      :title="displayName"
      :sub-title="displaySubTitle"
      @back="backToList"
      style="background: #112240; border-radius: 8px; margin-bottom: 16px;"
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
          <a-list :data-source="alerts" :split="false">
            <template #renderItem="{ item }">
              <a-list-item class="alert-item">
                <div class="alert-left">
                  <span :class="['alert-dot', `sev-${item.severity || 'warning'}`]"></span>
                  <div>
                    <div class="alert-title">{{ item.name || item.rule_id || '预警' }}</div>
                    <div class="alert-sub">
                      {{ fmtTime(item.created_at) }} · {{ item.parameter || '' }}
                      {{ item.condition?.operator || '' }} {{ item.condition?.threshold || '' }}
                    </div>
                  </div>
                </div>
                <div class="alert-value">{{ item.value ?? '—' }}</div>
              </a-list-item>
            </template>
          </a-list>
          <div v-if="!alerts.length" class="tab-empty">暂无预警记录</div>
        </a-tab-pane>

        <a-tab-pane key="ai" tab="AI辅助">
          <div class="ai-grid">
            <a-card title="检验异常摘要" :bordered="false" class="ai-card">
              <a-button size="small" @click="loadAiLab">生成摘要</a-button>
              <pre class="ai-text">{{ aiLabSummary || '—' }}</pre>
              <div v-if="aiLabError" class="ai-error">{{ aiLabError }}</div>
            </a-card>
            <a-card title="规则推荐" :bordered="false" class="ai-card">
              <a-button size="small" @click="loadAiRules">生成推荐</a-button>
              <pre class="ai-text">{{ aiRuleText || '—' }}</pre>
              <div v-if="aiRuleError" class="ai-error">{{ aiRuleError }}</div>
            </a-card>
            <a-card title="恶化风险预测" :bordered="false" class="ai-card">
              <a-button size="small" @click="loadAiRisk">生成预测</a-button>
              <pre class="ai-text">{{ aiRiskText || '—' }}</pre>
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

const drugColumns = [
  { title: '药品', dataIndex: 'drugName', key: 'drugName' },
  { title: '剂量', dataIndex: 'dose', key: 'dose' },
  { title: '用法', dataIndex: 'route', key: 'route' },
  { title: '频次', dataIndex: 'frequency', key: 'frequency' },
  { title: '执行时间', dataIndex: 'executeTime', key: 'executeTime' },
]

const assessmentColumns = [
  { title: '时间', dataIndex: 'time', key: 'time' },
  { title: 'GCS', dataIndex: 'gcs', key: 'gcs' },
  { title: 'RASS', dataIndex: 'rass', key: 'rass' },
  { title: '疼痛', dataIndex: 'pain', key: 'pain' },
  { title: '谵妄', dataIndex: 'delirium', key: 'delirium' },
  { title: 'Braden', dataIndex: 'braden', key: 'braden' },
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
  try {
    const res = await getPatientVitalsTrend(patientId, trendWindow.value)
    trendPoints.value = res.data.points || []
  } catch (e) {
    console.error('加载趋势失败', e)
  }
}

async function loadLabs() {
  const patientId = route.params.id as string
  try {
    const res = await getPatientLabs(patientId)
    labs.value = res.data.exams || []
  } catch (e) {
    console.error('加载检验失败', e)
  }
}

async function loadDrugs() {
  const patientId = route.params.id as string
  try {
    const res = await getPatientDrugs(patientId)
    drugs.value = res.data.records || []
  } catch (e) {
    console.error('加载用药失败', e)
  }
}

async function loadAssessments() {
  const patientId = route.params.id as string
  try {
    const res = await getPatientAssessments(patientId)
    assessments.value = res.data.records || []
  } catch (e) {
    console.error('加载评估失败', e)
  }
}

async function loadAlerts() {
  const patientId = route.params.id as string
  try {
    const res = await getPatientAlerts(patientId)
    alerts.value = res.data.records || []
  } catch (e) {
    console.error('加载预警失败', e)
  }
}

async function loadAiLab() {
  const patientId = route.params.id as string
  aiLabError.value = ''
  try {
    const res = await getAiLabSummary(patientId)
    aiLabSummary.value = res.data.summary || ''
    aiLabError.value = res.data.error || ''
  } catch (e) {
    aiLabError.value = 'AI服务不可用'
  }
}

async function loadAiRules() {
  const patientId = route.params.id as string
  aiRuleError.value = ''
  try {
    const res = await getAiRuleRecommendations(patientId)
    aiRuleText.value = res.data.recommendations || ''
    aiRuleError.value = res.data.error || ''
  } catch (e) {
    aiRuleError.value = 'AI服务不可用'
  }
}

async function loadAiRisk() {
  const patientId = route.params.id as string
  aiRiskError.value = ''
  try {
    const res = await getAiRiskForecast(patientId)
    aiRiskText.value = res.data.risk_summary || ''
    aiRiskError.value = res.data.error || ''
  } catch (e) {
    aiRiskError.value = 'AI服务不可用'
  }
}

watch(activeTab, key => {
  if (key === 'labs' && !labs.value.length) loadLabs()
  if (key === 'drugs' && !drugs.value.length) loadDrugs()
  if (key === 'assess' && !assessments.value.length) loadAssessments()
  if (key === 'alerts' && !alerts.value.length) loadAlerts()
})

watch(trendWindow, () => {
  if (activeTab.value === 'trend') loadTrend()
})

onMounted(async () => {
  const patientId = route.params.id as string
  try {
    const res = await getPatientDetail(patientId)
    patient.value = res.data.patient || null
  } catch (e) {
    console.error('加载患者失败', e)
  }

  try {
    const vRes = await getPatientVitals(patientId)
    vitals.value = vRes.data.vitals || null
  } catch (e) {
    console.error('加载生命体征失败', e)
  }

  loadTrend()
})
</script>

<style scoped>
.detail-container {
  max-width: 1400px;
  margin: 0 auto;
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
.alert-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.alert-left {
  display: flex;
  gap: 10px;
  align-items: center;
}
.alert-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.alert-dot.sev-warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b88; }
.alert-dot.sev-high { background: #ef4444; box-shadow: 0 0 6px #ef444488; }
.alert-dot.sev-critical { background: #d946ef; box-shadow: 0 0 6px #d946ef88; }
.alert-title {
  color: #e5e7eb;
  font-size: 13px;
}
.alert-sub {
  color: #6b7280;
  font-size: 11px;
}
.alert-value {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  color: #e5e7eb;
  font-weight: 700;
}
.ai-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}
.ai-card {
  background: #0f1a2b;
  border: 1px solid #1a2c46;
}
.ai-text {
  margin-top: 8px;
  white-space: pre-wrap;
  color: #cbd5f5;
  font-size: 12px;
  line-height: 1.5;
}
.ai-error {
  color: #f87171;
  font-size: 11px;
  margin-top: 6px;
}

@media (max-width: 980px) {
  .detail-content {
    grid-template-columns: 1fr;
  }
}
</style>
