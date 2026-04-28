<template>
  <div class="rounding-page">
    <section class="rounding-hero">
      <div class="hero-copy">
        <div class="eyebrow">ICU Daily Rounds</div>
        <h1>Rounding Sheet / 智能查房报告</h1>
        <p>
          当前范围：<strong>{{ scopeLabel }}</strong>，聚合过去 {{ hours }} 小时的预警、趋势、检验、用药、护理与 AI 关注点。
        </p>
      </div>
      <div class="hero-actions">
        <a-select v-model:value="hours" :options="hourOptions" class="hour-select" />
        <a-button :loading="loading" @click="loadPatients">刷新</a-button>
        <a-button type="primary" :loading="exporting" :disabled="!selectedPatientIds.length" @click="exportSelected">
          导出 {{ selectedPatientIds.length || '' }} 份 Markdown
        </a-button>
      </div>
    </section>

    <section class="metric-grid">
      <article class="metric-card metric-card--cyan">
        <span>查房患者</span>
        <strong>{{ patients.length }}</strong>
        <small>{{ scope?.dept_code || routeDeptCode || '全部在科' }}</small>
      </article>
      <article class="metric-card metric-card--red">
        <span>危急风险</span>
        <strong>{{ riskStats.critical }}</strong>
        <small>需优先床旁确认</small>
      </article>
      <article class="metric-card metric-card--orange">
        <span>高风险</span>
        <strong>{{ riskStats.high }}</strong>
        <small>建议晨会重点讨论</small>
      </article>
      <article class="metric-card">
        <span>已勾选导出</span>
        <strong>{{ selectedPatientIds.length }}</strong>
        <small>支持 Markdown 交班留痕</small>
      </article>
    </section>

    <a-alert v-if="error" type="error" :message="error" show-icon class="mb" />

    <section class="rounding-layout">
      <aside class="census-panel">
        <div class="panel-head">
          <div>
            <h2>今日查房患者</h2>
            <p>{{ filteredPatients.length }} / {{ patients.length }} 人</p>
          </div>
          <button type="button" class="ghost-link" @click="toggleSelectAll">
            {{ allFilteredSelected ? '取消全选' : '全选当前' }}
          </button>
        </div>

        <div class="filters">
          <a-input v-model:value="keyword" allow-clear placeholder="搜索床号 / 姓名 / 诊断" />
          <a-select v-model:value="riskFilter" :options="riskOptions" />
        </div>

        <a-spin :spinning="loading">
          <a-empty v-if="!filteredPatients.length" description="当前科室暂无在科查房患者" />
          <div v-else class="patient-list">
            <article
              v-for="patient in filteredPatients"
              :key="patient.patient_id"
              :class="['patient-card', { active: activePatient?.patient_id === patient.patient_id }]"
              @click="selectPatient(patient)"
            >
              <label class="select-dot" @click.stop>
                <input
                  type="checkbox"
                  :checked="selectedPatientIds.includes(patient.patient_id)"
                  @change="togglePatient(patient.patient_id)"
                />
                <span></span>
              </label>
              <div class="bed-pill">{{ patient.bed_no || '--' }}床</div>
              <div class="patient-main">
                <div class="patient-title">
                  <strong>{{ patient.name || '未命名' }}</strong>
                  <a-tag :color="riskColor(patient.risk_level)">{{ riskText(patient.risk_level) }}</a-tag>
                </div>
                <p>{{ patient.diagnosis || '暂无诊断' }}</p>
                <small>{{ patient.age || '年龄未知' }} · {{ patient.department || scopeLabel }}</small>
              </div>
            </article>
          </div>
        </a-spin>
      </aside>

      <main class="summary-panel">
        <a-empty v-if="!activePatient" description="请选择一名患者查看查房摘要" />
        <template v-else>
          <div class="summary-head">
            <div>
              <div class="bed-large">{{ activePatient.bed_no || '--' }}床</div>
              <h2>{{ activePatient.name }} <span>{{ activePatient.age || '' }}</span></h2>
              <p>{{ activePatient.diagnosis || '暂无诊断' }}</p>
            </div>
            <a-space wrap>
              <a-tag :color="riskColor(activePatient.risk_level)">{{ riskText(activePatient.risk_level) }}</a-tag>
              <a-button size="small" :loading="summaryLoading" @click="loadSummary">刷新摘要</a-button>
              <a-button size="small" type="primary" :loading="aiLoading" @click="loadAi">生成 AI 关注点</a-button>
            </a-space>
          </div>

          <a-spin :spinning="summaryLoading">
            <div v-if="summary" class="summary-content">
              <div class="quick-strip">
                <article>
                  <span>关键事件</span>
                  <strong>{{ summary.key_events?.length || 0 }}</strong>
                </article>
                <article>
                  <span>趋势指标</span>
                  <strong>{{ summary.trend_highlights?.length || 0 }}</strong>
                </article>
                <article>
                  <span>用药调整</span>
                  <strong>{{ summary.medication_changes?.length || 0 }}</strong>
                </article>
                <article>
                  <span>数据缺口</span>
                  <strong>{{ summary.data_quality?.data_gaps?.length || 0 }}</strong>
                </article>
              </div>

              <section class="briefing-section">
                <div class="briefing-main">
                  <div class="section-title">晨会 Briefing / 过夜摘要</div>
                  <p class="digest-headline">{{ summary.overnight_digest?.headline || '暂无可汇总的过夜变化，请结合床旁记录复核。' }}</p>
                  <div class="digest-grid">
                    <article>
                      <span>预警记录</span>
                      <strong>{{ summary.overnight_digest?.alerts?.length || 0 }}</strong>
                      <small>{{ firstText(summary.overnight_digest?.alerts, '暂无新增预警') }}</small>
                    </article>
                    <article>
                      <span>检验变化</span>
                      <strong>{{ summary.overnight_digest?.labs?.length || 0 }}</strong>
                      <small>{{ firstText(summary.overnight_digest?.labs, '暂无检验变化') }}</small>
                    </article>
                    <article>
                      <span>医嘱/用药</span>
                      <strong>{{ summary.overnight_digest?.medications?.length || 0 }}</strong>
                      <small>{{ firstText(summary.overnight_digest?.medications, '暂无医嘱调整') }}</small>
                    </article>
                    <article>
                      <span>护理处置</span>
                      <strong>{{ summary.overnight_digest?.nursing?.length || 0 }}</strong>
                      <small>{{ firstText(summary.overnight_digest?.nursing, '暂无护理处置') }}</small>
                    </article>
                  </div>
                </div>
                <div class="briefing-side">
                  <div class="section-title">查房待确认清单</div>
                  <div class="checklist">
                    <article v-for="item in summary.rounding_checklist || []" :key="`${item.label}-${item.source}`" class="check-item">
                      <span :class="['check-dot', `check-${item.status}`]"></span>
                      <div>
                        <strong>{{ item.label }}</strong>
                        <small>{{ item.source }}</small>
                      </div>
                    </article>
                  </div>
                </div>
              </section>

              <section class="priority-section">
                <div class="section-title">今日优先关注问题</div>
                <div v-if="summary.clinical_priorities?.length" class="priority-grid">
                  <article v-for="item in summary.clinical_priorities" :key="item.title" class="priority-card">
                    <div class="priority-head">
                      <a-tag :color="focusColor(item.risk_level)">{{ riskText(item.risk_level) }}</a-tag>
                      <strong>{{ item.title }}</strong>
                    </div>
                    <p>{{ item.why_it_matters }}</p>
                    <div class="evidence-list">
                      <span v-for="evidence in (item.evidence || []).slice(0, 3)" :key="evidence">{{ evidence }}</span>
                    </div>
                    <div class="question-list">
                      <em v-for="question in (item.rounding_questions || []).slice(0, 2)" :key="question">{{ question }}</em>
                    </div>
                  </article>
                </div>
                <div v-else class="soft-empty">暂无系统生成的优先问题。</div>
              </section>

              <section class="bodymap-section">
                <div class="bodymap-visual">
                  <OrganHeatmapFigure
                    show-legend
                    :organ-states="roundingOrganStates"
                    :organ-tooltips="roundingOrganTooltips"
                    :selected-organ="selectedOrgan"
                    silhouette="female"
                    @organ-click="handleOrganClick"
                  />
                </div>
                <div class="bodymap-side">
                  <div class="section-title">人体图 / 器官系统查房定位</div>
                  <p>按过去 {{ hours }} 小时的器官系统事件数和严重度点亮人体图，点击器官可跳转到对应系统。</p>
                  <div class="organ-chip-grid">
                    <button
                      v-for="item in organFocusRows"
                      :key="item.key"
                      type="button"
                      :class="['organ-chip', `sev-${item.severity}`, { active: activeSystemTab === item.systemKey }]"
                      @click="activeSystemTab = item.systemKey"
                    >
                      <strong>{{ item.label }}</strong>
                      <span>{{ item.count }} 条 · {{ severityText(item.severity) }}</span>
                    </button>
                  </div>
                  <div class="bodymap-note">人体图为查房导航与风险提示，不替代医生判断。</div>
                </div>
              </section>

              <section class="trend-section">
                <div class="section-title">生命体征趋势 Highlights</div>
                <div v-if="summary.trend_highlights?.length" class="trend-grid">
                  <article v-for="item in summary.trend_highlights" :key="item.code || item.label" class="trend-card">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.latest ?? '—' }}</strong>
                    <small>范围 {{ item.min ?? '—' }} - {{ item.max ?? '—' }}，{{ item.points || 0 }} 点</small>
                  </article>
                </div>
                <div v-else class="soft-empty">暂无床旁生命体征趋势，建议确认监护数据同步。</div>
              </section>

              <a-tabs v-model:activeKey="activeSystemTab" class="system-tabs">
                <a-tab-pane v-for="system in systemTabs" :key="system.key" :tab="`${system.label} ${systemCount(system.key)}`">
                  <article v-if="systemAssessment(system.key)" class="assessment-card">
                    <div>
                      <a-tag :color="assessmentColor(systemAssessment(system.key)?.status)">
                        {{ assessmentText(systemAssessment(system.key)?.status) }}
                      </a-tag>
                      <strong>{{ systemAssessment(system.key)?.headline }}</strong>
                    </div>
                    <p>{{ systemAssessment(system.key)?.action_hint }}</p>
                    <span v-for="evidence in (systemAssessment(system.key)?.evidence || []).slice(0, 3)" :key="evidence">
                      {{ evidence }}
                    </span>
                  </article>
                  <a-empty v-if="!systemCount(system.key)" description="暂无重点事件" />
                  <a-timeline v-else>
                    <a-timeline-item v-for="(item, idx) in (summary.systems?.[system.key] || []).slice(0, 18)" :key="idx">
                      <div class="event-row">
                        <strong>{{ item.title || item.type }}</strong>
                        <a-tag :color="eventColor(item.type)">{{ eventLabel(item.type) }}</a-tag>
                      </div>
                      <div class="muted">{{ fmt(item.time) }}</div>
                    </a-timeline-item>
                  </a-timeline>
                </a-tab-pane>
              </a-tabs>

              <section class="ai-box">
                <div class="section-title">AI 关注点提示</div>
                <a-empty v-if="!aiPoints.length" description="点击“生成 AI 关注点”获取 3-5 条查房提示" />
                <article v-for="(point, idx) in aiPoints" :key="idx" class="focus-card">
                  <div class="focus-head">
                    <a-tag :color="focusColor(point.risk_level)">{{ riskText(point.risk_level) || point.risk_level }}</a-tag>
                    <strong>{{ point.title }}</strong>
                  </div>
                  <p>{{ point.suggested_attention }}</p>
                  <small>{{ (point.evidence || []).join('；') }}</small>
                </article>
                <div class="disclaimer">仅供临床决策支持，不替代医生判断。</div>
              </section>
            </div>
          </a-spin>
        </template>
      </main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Alert as AAlert,
  Button as AButton,
  Empty as AEmpty,
  Input as AInput,
  Select as ASelect,
  Space as ASpace,
  Spin as ASpin,
  Tabs as ATabs,
  TabPane as ATabPane,
  Tag as ATag,
  Timeline as ATimeline,
  TimelineItem as ATimelineItem,
  message,
} from 'ant-design-vue'
import OrganHeatmapFigure from '../components/common/OrganHeatmapFigure.vue'
import { getDepartments } from '../api'
import { getRoundingPatients, getRoundingSummary, postRoundingAiInsights, postRoundingExport } from '../api/rounding'
import { BODY_MAP_ORGAN_LABELS, bodyMapSeverityText, type BodyMapOrganKey, type BodyMapSeverity } from '../utils/bodyMap'

const route = useRoute()

const loading = ref(false)
const summaryLoading = ref(false)
const aiLoading = ref(false)
const exporting = ref(false)
const error = ref('')
const hours = ref(24)
const keyword = ref('')
const riskFilter = ref('all')
const patients = ref<any[]>([])
const departments = ref<any[]>([])
const scope = ref<any>(null)
const activePatient = ref<any>(null)
const summary = ref<any>(null)
const selectedPatientIds = ref<string[]>([])
const aiPoints = ref<any[]>([])
const activeSystemTab = ref('respiratory')
const selectedOrgan = ref('')

const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
const matchedDept = computed(() => departments.value.find((item) => String(item?.deptCode || item?.code || '').trim() === routeDeptCode.value))
const scopeLabel = computed(() => matchedDept.value?.dept || matchedDept.value?.department || routeDeptName.value || routeDeptCode.value || '全部 ICU 在科患者')

const hourOptions = [8, 12, 24, 48].map((value) => ({ value, label: `${value}小时` }))
const riskOptions = [
  { value: 'all', label: '全部风险' },
  { value: 'critical', label: '危急' },
  { value: 'high', label: '高风险' },
  { value: 'medium', label: '中风险' },
  { value: 'low', label: '低风险' },
]
const systemTabs = [
  { key: 'neuro', label: '神经' },
  { key: 'respiratory', label: '呼吸' },
  { key: 'circulation', label: '循环' },
  { key: 'renal', label: '肾脏/液体' },
  { key: 'infection', label: '感染' },
  { key: 'nutrition', label: '营养/代谢' },
  { key: 'coagulation', label: '凝血/血液' },
  { key: 'others', label: '其他' },
]

const systemToOrganMap: Record<string, BodyMapOrganKey | ''> = {
  neuro: 'neurologic',
  respiratory: 'respiratory',
  circulation: 'circulatory',
  renal: 'renal',
  infection: 'circulatory',
  nutrition: 'hepatic',
  coagulation: 'coagulation',
  others: '',
}
const organToSystemMap: Record<string, string> = {
  neurologic: 'neuro',
  respiratory: 'respiratory',
  circulatory: 'circulation',
  renal: 'renal',
  hepatic: 'nutrition',
  coagulation: 'coagulation',
}

const filteredPatients = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return patients.value.filter((patient) => {
    if (riskFilter.value !== 'all' && patient.risk_level !== riskFilter.value) return false
    if (!q) return true
    return [patient.bed_no, patient.name, patient.diagnosis, patient.department]
      .some((item) => String(item || '').toLowerCase().includes(q))
  })
})

const riskStats = computed(() => patients.value.reduce((acc, patient) => {
  const key = patient.risk_level || 'low'
  acc[key] = (acc[key] || 0) + 1
  return acc
}, { critical: 0, high: 0, medium: 0, low: 0 } as Record<string, number>))

const allFilteredSelected = computed(() => {
  const ids = filteredPatients.value.map((patient) => patient.patient_id)
  return Boolean(ids.length && ids.every((id) => selectedPatientIds.value.includes(id)))
})

const organFocusRows = computed(() => systemTabs.map((system) => {
  const count = systemCount(system.key)
  const severity = systemSeverity(system.key)
  return { ...system, systemKey: system.key, organKey: systemToOrganMap[system.key], count, severity }
}))

const roundingOrganStates = computed(() => {
  const states: Record<string, BodyMapSeverity> = {
    neurologic: 'normal',
    respiratory: 'normal',
    circulatory: 'normal',
    hepatic: 'normal',
    coagulation: 'normal',
    renal: 'normal',
  }
  for (const row of organFocusRows.value) {
    if (!row.organKey) continue
    const current = states[row.organKey] || 'normal'
    const next = row.severity || 'normal'
    states[row.organKey] = severityRank(next) > severityRank(current) ? next : current
  }
  return states
})

const roundingOrganTooltips = computed(() => Object.fromEntries(Object.entries(roundingOrganStates.value).map(([key, severity]) => {
  const systemKey = organToSystemMap[key] || ''
  const count = systemKey ? systemCount(systemKey) : 0
  return [key, {
    label: BODY_MAP_ORGAN_LABELS[key as BodyMapOrganKey] || key,
    statusText: severityText(severity),
    detail: `${count} 条查房相关事件`,
    severity,
  }]
})))

function riskColor(v: string) {
  return v === 'critical' ? 'red' : v === 'high' ? 'volcano' : v === 'medium' ? 'gold' : 'cyan'
}
function severityRank(v: string) {
  return ({ normal: 0, warning: 1, high: 2, critical: 3 } as Record<string, number>)[v] || 0
}
function severityText(v: string) {
  return bodyMapSeverityText(v)
}
function severityFromEvent(item: any): BodyMapSeverity {
  const severity = String(item?.severity || item?.evidence?.severity || '').toLowerCase()
  if (severity === 'critical') return 'critical'
  if (severity === 'high') return 'high'
  if (severity === 'medium' || severity === 'warning') return 'warning'
  return 'warning'
}
function systemSeverity(systemKey: string): BodyMapSeverity {
  const rows = summary.value?.systems?.[systemKey] || []
  if (!rows.length) return 'normal'
  let severity: BodyMapSeverity = rows.length >= 6 ? 'high' : 'warning'
  for (const row of rows) {
    const next = severityFromEvent(row)
    if (severityRank(next) > severityRank(severity)) severity = next
  }
  return severity
}
function focusColor(v: string) {
  return v === 'high' ? 'red' : v === 'medium' ? 'gold' : 'blue'
}
function riskText(v: string) {
  return ({ critical: '危急', high: '高', medium: '中', low: '低' } as any)[v] || v || '—'
}
function eventLabel(type: string) {
  return ({ alert: '预警', lab: '检验', medication: '用药', nursing_event: '护理' } as any)[type] || type || '事件'
}
function eventColor(type: string) {
  return ({ alert: 'volcano', lab: 'geekblue', medication: 'purple', nursing_event: 'green' } as any)[type] || 'cyan'
}
function firstText(rows: any[], fallback: string) {
  return Array.isArray(rows) && rows.length ? String(rows[0] || fallback) : fallback
}
function assessmentColor(v: string) {
  return v === 'critical' ? 'red' : v === 'high' ? 'volcano' : v === 'watch' ? 'gold' : 'green'
}
function assessmentText(v: string) {
  return ({ critical: '危急', high: '高危', watch: '关注', stable: '平稳' } as any)[v] || '关注'
}
function fmt(v: any) {
  return v ? new Date(v).toLocaleString('zh-CN') : '—'
}
function systemCount(key: string) {
  return summary.value?.systems?.[key]?.length || 0
}
function systemAssessment(key: string) {
  return (summary.value?.system_assessments || []).find((item: any) => item.system === key)
}
function handleOrganClick(organKey: string) {
  selectedOrgan.value = organKey
  const systemKey = organToSystemMap[organKey]
  if (systemKey) activeSystemTab.value = systemKey
}
function requestParams() {
  const params: { dept?: string; dept_code?: string; limit: number } = { limit: 300 }
  if (routeDeptCode.value) params.dept_code = routeDeptCode.value
  if (!routeDeptCode.value && routeDeptName.value) params.dept = routeDeptName.value
  return params
}
function togglePatient(patientId: string) {
  selectedPatientIds.value = selectedPatientIds.value.includes(patientId)
    ? selectedPatientIds.value.filter((id) => id !== patientId)
    : [...selectedPatientIds.value, patientId]
}
function toggleSelectAll() {
  const ids = filteredPatients.value.map((patient) => patient.patient_id)
  if (allFilteredSelected.value) {
    selectedPatientIds.value = selectedPatientIds.value.filter((id) => !ids.includes(id))
  } else {
    selectedPatientIds.value = Array.from(new Set([...selectedPatientIds.value, ...ids]))
  }
}

async function loadDepartments() {
  try {
    const res = await getDepartments()
    departments.value = Array.isArray(res.data?.departments) ? res.data.departments : []
  } catch {
    departments.value = []
  }
}
async function loadPatients() {
  loading.value = true
  error.value = ''
  try {
    const res = await getRoundingPatients(requestParams())
    patients.value = res.data?.patients || []
    scope.value = res.data?.scope || null
    selectedPatientIds.value = selectedPatientIds.value.filter((id) => patients.value.some((patient) => patient.patient_id === id))
    if (!patients.value.some((patient) => patient.patient_id === activePatient.value?.patient_id)) {
      activePatient.value = null
      summary.value = null
      aiPoints.value = []
      if (patients.value.length) await selectPatient(patients.value[0])
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '查房患者加载失败'
  } finally {
    loading.value = false
  }
}
async function selectPatient(row: any) {
  activePatient.value = row
  aiPoints.value = []
  selectedOrgan.value = ''
  await loadSummary()
}
async function loadSummary() {
  if (!activePatient.value) return
  summaryLoading.value = true
  try {
    const res = await getRoundingSummary(activePatient.value.patient_id, hours.value)
    summary.value = res.data?.summary || null
    activeSystemTab.value = pickInitialSystemTab()
  } finally {
    summaryLoading.value = false
  }
}
function pickInitialSystemTab() {
  const rows = systemTabs
    .map((system) => ({ key: system.key, count: summary.value?.systems?.[system.key]?.length || 0, severity: systemSeverity(system.key) }))
    .sort((a, b) => severityRank(b.severity) - severityRank(a.severity) || b.count - a.count)
  return rows[0]?.count ? rows[0].key : 'respiratory'
}
async function loadAi() {
  if (!activePatient.value) return
  aiLoading.value = true
  try {
    const res = await postRoundingAiInsights(activePatient.value.patient_id, hours.value)
    aiPoints.value = res.data?.insights?.focus_points || []
    if (summary.value) summary.value.ai_focus_points = aiPoints.value
  } finally {
    aiLoading.value = false
  }
}
async function exportSelected() {
  exporting.value = true
  try {
    const res = await postRoundingExport({ patient_ids: selectedPatientIds.value.map(String), hours: hours.value, format: 'markdown' })
    message.success(`导出完成：${res.data?.task?.task_id || ''}`)
  } finally {
    exporting.value = false
  }
}

watch(hours, () => {
  if (activePatient.value) loadSummary()
})
watch(() => [route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  loadPatients()
})

onMounted(async () => {
  await loadDepartments()
  await loadPatients()
})
</script>

<style scoped>
.rounding-page {
  min-height: calc(100vh - 76px);
  padding: 20px;
  color: var(--text-main);
  background:
    radial-gradient(circle at 10% 0%, rgba(34, 211, 238, .12), transparent 32%),
    radial-gradient(circle at 84% 8%, rgba(14, 165, 233, .1), transparent 30%);
}
.rounding-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  border: 1px solid rgba(80,199,255,.16);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(7, 25, 42, .95), rgba(5, 13, 25, .9));
  box-shadow: 0 18px 42px rgba(0,0,0,.22);
}
.eyebrow {
  color: #67e8f9;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
  font-size: 12px;
}
h1, h2, p { margin: 0; }
h1 { margin-top: 4px; font-size: 26px; color: #f0fbff; }
.hero-copy p { margin-top: 8px; color: #9fc4d7; }
.hero-copy strong { color: #e6fbff; }
.hero-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; }
.hour-select { width: 132px; }
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0;
}
.metric-card {
  padding: 14px;
  border: 1px solid rgba(125,167,214,.14);
  border-radius: 16px;
  background: rgba(7, 20, 34, .76);
}
.metric-card span, .metric-card small { display: block; color: #8aa4b8; }
.metric-card strong { display: block; margin: 4px 0; color: #f2fbff; font-size: 30px; line-height: 1; }
.metric-card--cyan { background: linear-gradient(135deg, rgba(8, 64, 84, .78), rgba(7, 20, 34, .78)); }
.metric-card--red { background: linear-gradient(135deg, rgba(90, 20, 33, .7), rgba(7, 20, 34, .78)); }
.metric-card--orange { background: linear-gradient(135deg, rgba(91, 55, 15, .7), rgba(7, 20, 34, .78)); }
.rounding-layout {
  display: grid;
  grid-template-columns: minmax(360px, .78fr) minmax(0, 1.45fr);
  gap: 14px;
}
.census-panel, .summary-panel {
  border: 1px solid rgba(80,199,255,.14);
  border-radius: 18px;
  background: rgba(6, 18, 31, .9);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.census-panel { padding: 14px; }
.summary-panel { min-height: 680px; padding: 16px; }
.panel-head, .summary-head, .patient-title, .event-row, .focus-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.panel-head h2, .summary-head h2 { color: #f0fbff; font-size: 18px; }
.panel-head p, .summary-head p { color: #8aa4b8; margin-top: 3px; }
.ghost-link {
  border: 0;
  background: transparent;
  color: #67e8f9;
  cursor: pointer;
  font-weight: 700;
}
.filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 128px;
  gap: 10px;
  margin: 12px 0;
}
.patient-list {
  display: grid;
  gap: 10px;
  max-height: 620px;
  overflow: auto;
  padding-right: 4px;
}
.patient-card {
  display: grid;
  grid-template-columns: 24px 58px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 12px;
  border: 1px solid rgba(125,167,214,.12);
  border-radius: 14px;
  background: rgba(8, 28, 44, .58);
  cursor: pointer;
  transition: transform .15s ease, border-color .15s ease, background .15s ease;
}
.patient-card:hover, .patient-card.active {
  transform: translateY(-1px);
  border-color: rgba(103,232,249,.42);
  background: linear-gradient(135deg, rgba(8, 57, 77, .72), rgba(8, 28, 44, .62));
}
.select-dot input { display: none; }
.select-dot span {
  display: block;
  width: 16px;
  height: 16px;
  border: 1px solid rgba(103,232,249,.28);
  border-radius: 6px;
  background: rgba(3, 12, 24, .8);
}
.select-dot input:checked + span {
  background: #22d3ee;
  box-shadow: 0 0 0 3px rgba(34,211,238,.12);
}
.bed-pill {
  display: grid;
  place-items: center;
  height: 42px;
  border-radius: 12px;
  color: #ecfeff;
  font-weight: 900;
  background: rgba(14, 116, 144, .35);
  border: 1px solid rgba(103,232,249,.18);
}
.patient-main { min-width: 0; }
.patient-main p {
  margin-top: 4px;
  color: #c9d9e6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.patient-main small, .muted, .disclaimer, .soft-empty { color: #88a2b4; }
.bed-large {
  display: inline-flex;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(34,211,238,.12);
  color: #67e8f9;
  font-weight: 900;
}
.summary-head {
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(80,199,255,.12);
}
.summary-head h2 { margin-top: 8px; font-size: 24px; }
.summary-head h2 span { color: #9fc4d7; font-size: 14px; }
.summary-content { display: grid; gap: 14px; margin-top: 14px; }
.quick-strip, .trend-grid, .digest-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.quick-strip article, .trend-card, .focus-card, .digest-grid article, .priority-card, .assessment-card {
  padding: 12px;
  border: 1px solid rgba(125,167,214,.14);
  border-radius: 14px;
  background: rgba(2, 8, 20, .26);
}
.quick-strip span, .trend-card span, .digest-grid span { display: block; color: #8aa4b8; }
.quick-strip strong, .trend-card strong, .digest-grid strong { display: block; margin-top: 4px; color: #e6f7ff; font-size: 24px; }
.digest-grid small {
  display: block;
  margin-top: 6px;
  color: #9fc4d7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.section-title { margin-bottom: 10px; color: #e6f7ff; font-weight: 900; letter-spacing: .02em; }
.briefing-section {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr);
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(103,232,249,.14);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(12, 54, 72, .52), rgba(2, 8, 20, .2)),
    radial-gradient(circle at 90% 16%, rgba(34,211,238,.12), transparent 34%);
}
.digest-headline {
  margin-bottom: 12px;
  color: #dff7ff;
  line-height: 1.7;
  font-size: 15px;
}
.briefing-side {
  padding: 12px;
  border-radius: 16px;
  background: rgba(2, 8, 20, .24);
}
.checklist {
  display: grid;
  gap: 10px;
}
.check-item {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
}
.check-item strong {
  display: block;
  color: #e6f7ff;
}
.check-item small {
  display: block;
  margin-top: 2px;
  color: #88a2b4;
}
.check-dot {
  width: 10px;
  height: 10px;
  margin-top: 5px;
  border-radius: 999px;
  background: #22d3ee;
  box-shadow: 0 0 0 4px rgba(34,211,238,.12);
}
.check-ok { background: #34d399; box-shadow: 0 0 0 4px rgba(52,211,153,.12); }
.check-missing { background: #fbbf24; box-shadow: 0 0 0 4px rgba(251,191,36,.12); }
.check-todo { background: #38bdf8; box-shadow: 0 0 0 4px rgba(56,189,248,.12); }
.priority-section {
  padding: 12px;
  border-radius: 16px;
  background: rgba(8, 28, 44, .42);
}
.priority-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.priority-card {
  display: grid;
  gap: 9px;
}
.priority-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.priority-head strong {
  color: #e6f7ff;
}
.priority-card p {
  color: #c9d9e6;
  line-height: 1.6;
}
.evidence-list, .question-list {
  display: grid;
  gap: 6px;
}
.evidence-list span {
  padding: 7px 9px;
  border-radius: 10px;
  color: #bfefff;
  background: rgba(14, 116, 144, .18);
}
.question-list em {
  color: #fef3c7;
  font-style: normal;
  font-size: 12px;
}
.bodymap-section {
  display: grid;
  grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
  gap: 14px;
  padding: 14px;
  border: 1px solid rgba(103,232,249,.14);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(8, 42, 62, .54), rgba(2, 8, 20, .24)),
    radial-gradient(circle at 26% 18%, rgba(34,211,238,.12), transparent 36%);
}
.bodymap-visual {
  display: grid;
  place-items: center;
  min-height: 360px;
  border-radius: 16px;
  background: rgba(2, 8, 20, .2);
  overflow: hidden;
}
.bodymap-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  justify-content: center;
}
.bodymap-side p {
  color: #9fc4d7;
  line-height: 1.7;
}
.organ-chip-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.organ-chip {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(125,167,214,.14);
  background: rgba(2, 8, 20, .28);
  color: #dff7ff;
  text-align: left;
  cursor: pointer;
  transition: transform .15s ease, border-color .15s ease, background .15s ease;
}
.organ-chip:hover,
.organ-chip.active {
  transform: translateY(-1px);
  border-color: rgba(103,232,249,.42);
  background: rgba(8, 57, 77, .55);
}
.organ-chip span {
  color: #8aa4b8;
  font-size: 12px;
}
.organ-chip.sev-warning { border-color: rgba(251,191,36,.24); }
.organ-chip.sev-high { border-color: rgba(251,146,60,.34); }
.organ-chip.sev-critical { border-color: rgba(244,63,94,.42); background: rgba(90, 20, 33, .34); }
.bodymap-note {
  padding: 10px 12px;
  border-radius: 12px;
  color: #88a2b4;
  background: rgba(2, 8, 20, .26);
}
.trend-section, .ai-box {
  padding: 12px;
  border-radius: 16px;
  background: rgba(8, 28, 44, .42);
}
.system-tabs {
  padding: 4px 10px 10px;
  border-radius: 16px;
  background: rgba(2, 8, 20, .18);
}
.assessment-card {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  background: linear-gradient(135deg, rgba(8, 42, 62, .52), rgba(2, 8, 20, .18));
}
.assessment-card div {
  display: flex;
  align-items: center;
  gap: 8px;
}
.assessment-card strong {
  color: #e6f7ff;
}
.assessment-card p {
  color: #c9d9e6;
}
.assessment-card span {
  color: #9fc4d7;
}
.focus-card { display: grid; gap: 8px; margin-top: 10px; }
.focus-card p { color: #c9d9e6; }
.mb { margin-bottom: 12px; }
@media (max-width: 1280px) {
  .metric-grid, .quick-strip, .trend-grid, .digest-grid, .priority-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .rounding-layout { grid-template-columns: 1fr; }
  .patient-list { max-height: 420px; }
}
@media (max-width: 760px) {
  .rounding-page { padding: 12px; }
  .rounding-hero, .summary-head { flex-direction: column; align-items: stretch; }
  .metric-grid, .quick-strip, .trend-grid, .filters, .bodymap-section, .organ-chip-grid, .briefing-section, .digest-grid, .priority-grid { grid-template-columns: 1fr; }
  .patient-card { grid-template-columns: 24px 50px minmax(0, 1fr); }
}
</style>
