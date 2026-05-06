<template>
  <div class="rounding-page">
    <section class="rounding-hero">
      <div class="hero-copy">
        <div class="eyebrow">ICU 查房</div>
        <h1>患者查房单</h1>
        <p>
          <strong>{{ scopeLabel }}</strong> · 过去 {{ hours }} 小时
        </p>
      </div>
      <div class="hero-actions">
        <a-select v-model:value="hours" :options="hourOptions" class="hour-select" />
        <a-button :loading="loading" @click="loadPatients">刷新</a-button>
        <a-button type="primary" :loading="exporting" :disabled="!selectedPatientIds.length" @click="exportSelected">
          导出 {{ selectedPatientIds.length || '' }} 份
        </a-button>
      </div>
    </section>

    <section class="metric-grid">
      <article class="metric-card metric-card--cyan">
        <span>查房患者</span>
        <strong>{{ patients.length }}</strong>
        <small>{{ scopeLabel }}</small>
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
        <small>查房留痕</small>
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
              <a-button size="small" type="primary" :loading="aiLoading" @click="loadAi">生成关注点</a-button>
            </a-space>
          </div>

          <a-spin :spinning="summaryLoading">
            <div v-if="summary" class="summary-content">
              <div class="quick-strip">
                <article class="completion-card">
                  <span>查房闭环</span>
                  <strong>{{ summary.completion?.percent ?? 0 }}%</strong>
                  <i><b :style="{ width: `${summary.completion?.percent ?? 0}%` }"></b></i>
                </article>
                <article v-for="chip in summary.completion?.chips || []" :key="chip.label">
                  <span>{{ chip.label }}</span>
                  <strong>{{ chip.value }}</strong>
                </article>
              </div>

              <section class="briefing-section">
                <div class="briefing-main">
                  <div class="section-title">今日动作</div>
                  <div class="action-grid">
                    <button
                      v-for="item in summary.completion?.tasks || []"
                      :key="`${item.title}-${item.source}`"
                      type="button"
                      :class="['action-card', `prio-${item.priority}`]"
                      @click="markRoundAction(item)"
                    >
                      <strong>{{ shortText(item.title, 18) }}</strong>
                      <span>{{ item.action }}</span>
                    </button>
                    <div v-if="!(summary.completion?.tasks || []).length" class="soft-empty">今日查房动作已清空。</div>
                  </div>
                </div>
                <div class="briefing-side">
                  <div class="section-title">数据质量 {{ summary.completion?.data_quality?.percent ?? 0 }}%</div>
                  <div class="checklist">
                    <article v-for="item in summary.rounding_checklist || []" :key="`${item.label}-${item.source}`" class="check-item">
                      <span :class="['check-dot', `check-${item.status}`]"></span>
                      <div>
                        <strong>{{ item.label }}</strong>
                        <small>{{ sourceText(item.source) }}</small>
                      </div>
                    </article>
                  </div>
                </div>
              </section>

              <section class="priority-section">
                <div class="section-title">优先问题</div>
                <div v-if="summary.clinical_priorities?.length" class="priority-grid">
                  <article v-for="item in summary.clinical_priorities" :key="item.title" class="priority-card">
                    <div class="priority-head">
                      <a-tag :color="focusColor(item.risk_level)">{{ riskText(item.risk_level) }}</a-tag>
                      <strong>{{ shortText(item.title, 18) }}</strong>
                    </div>
                    <div class="evidence-list">
                      <span v-for="evidence in (item.evidence || []).slice(0, 2)" :key="evidence">{{ shortText(evidenceText(evidence), 30) }}</span>
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
                  <div class="section-title">器官定位</div>
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
                </div>
              </section>

              <section class="trend-section">
                <div class="section-title">生命体征</div>
                <div v-if="summary.trend_highlights?.length" class="trend-grid">
                  <article v-for="item in summary.trend_highlights" :key="item.code || item.label" class="trend-card">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.latest ?? '—' }}</strong>
                    <small>{{ item.min ?? '—' }} - {{ item.max ?? '—' }} · {{ item.points || 0 }}点</small>
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
                    <span v-for="evidence in (systemAssessment(system.key)?.evidence || []).slice(0, 2)" :key="evidence">
                      {{ evidenceText(evidence) }}
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
                <div class="section-title">智能关注点</div>
                <a-empty v-if="!aiPoints.length" description="点击“生成关注点”获取查房提示" />
                <article v-for="(point, idx) in aiPoints" :key="idx" class="focus-card">
                  <div class="focus-head">
                    <a-tag :color="focusColor(point.risk_level)">{{ riskText(point.risk_level) || point.risk_level }}</a-tag>
                    <strong>{{ point.title }}</strong>
                  </div>
                  <p>{{ shortText(point.suggested_attention, 36) }}</p>
                  <small>{{ (point.evidence || []).slice(0, 2).map((x: any) => shortText(x, 20)).join('；') }}</small>
                </article>
                <div class="disclaimer">仅供临床决策支持，不替代医生判断。</div>
              </section>
              <section class="editable-rounding">
                <div class="section-title">查房记录确认</div>
                <textarea v-model="editableDraft" rows="8" placeholder="AI 初稿和系统分类会自动汇总到这里，医生可编辑后确认。" />
                <div class="version-row">
                  <span v-for="item in versionHistory" :key="item.id">{{ item.label }}</span>
                </div>
                <div class="confirm-row">
                  <a-button size="small" @click="buildEditableDraft">生成系统分类初稿</a-button>
                  <a-button size="small" type="primary" @click="confirmRoundingDraft">医生确认</a-button>
                </div>
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
import { getDepartments, postClinicalTask } from '../api'
import {
  getRoundingPatients,
  getRoundingSummary,
  getRoundingVersions,
  postRoundingAiInsights,
  postRoundingExport,
  postRoundingVersion,
  postRoundingVersionConfirm,
} from '../api/rounding'
import { BODY_MAP_ORGAN_LABELS, bodyMapSeverityText, type BodyMapOrganKey, type BodyMapSeverity } from '../utils/bodyMap'
import { formatBeijingTime } from '../utils/time'

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
const editableDraft = ref('')
const versionHistory = ref<any[]>([])
const latestVersionId = ref('')
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
function shortText(value: any, max = 30) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}...` : text
}
function evidenceText(value: any) {
  let text = String(value || '').replace(/\s+/g, ' ').trim()
  text = text.replace(/[（(]([^()（）]*\d{4}-\d{2}-\d{2}T[^()（）]*)[）)]/g, (_match, raw) => ` ${formatBeijingTime(raw, '')}`)
  text = text.replace(/(\d{4}-\d{2}-\d{2}T[^\s)）]+)/g, (_match, raw) => formatBeijingTime(raw, ''))
  text = text.replace(/\s+/g, ' ').replace(/[（(]\s*[）)]/g, '').trim()
  return text
}
function sourceText(value: any) {
  return ({
    alert_records: '预警',
    order_records: '医嘱',
    bedside: '床旁',
    lis: '检验',
  } as Record<string, string>)[String(value || '')] || '核对'
}
function assessmentColor(v: string) {
  return v === 'critical' ? 'red' : v === 'high' ? 'volcano' : v === 'watch' ? 'gold' : 'green'
}
function assessmentText(v: string) {
  return ({ critical: '危急', high: '高危', watch: '关注', stable: '平稳' } as any)[v] || '关注'
}
function fmt(v: any) {
  return formatBeijingTime(v, '—')
}
function systemCount(key: string) {
  return summary.value?.systems?.[key]?.length || 0
}
function systemAssessment(key: string) {
  return (summary.value?.system_assessments || []).find((item: any) => item.system === key)
}
async function markRoundAction(item: any) {
  if (!activePatient.value?.patient_id) return
  const { data } = await postClinicalTask({
    patient_id: activePatient.value.patient_id,
    bed: activePatient.value.bed_no,
    name: activePatient.value.name,
    module: 'rounding',
    task_type: 'rounding_action',
    title: item?.title || '查房动作',
    detail: item?.action || '',
    priority: item?.priority || 'medium',
    source: '查房动作板',
  })
  message.success(data?.deduped ? '查房任务已存在' : '已创建查房任务')
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
    const queryPatientId = String(route.query.patientId || route.query.patient_id || '').trim()
    const queryPatient = queryPatientId
      ? patients.value.find((patient) => String(patient.patient_id || patient.id || patient.hisPid || '') === queryPatientId)
      : null
    if (queryPatient && activePatient.value?.patient_id !== queryPatient.patient_id) {
      await selectPatient(queryPatient)
      return
    }
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
  editableDraft.value = ''
  latestVersionId.value = ''
  await loadSummary()
  await loadVersionHistory()
}
async function loadSummary() {
  if (!activePatient.value) return
  summaryLoading.value = true
  try {
    const res = await getRoundingSummary(activePatient.value.patient_id, hours.value)
    summary.value = res.data?.summary || null
    activeSystemTab.value = pickInitialSystemTab()
    buildEditableDraft()
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
    buildEditableDraft()
  } finally {
    aiLoading.value = false
  }
}

function buildEditableDraft() {
  if (!summary.value) return
  const rows: string[] = []
  rows.push(`查房患者：${activePatient.value?.bed_no || '--'}床 ${activePatient.value?.name || ''}`)
  rows.push(`夜间/近${hours.value}小时事件：`)
  ;(summary.value.night_events || summary.value.recent_events || []).slice(0, 6).forEach((item: any) => rows.push(`- ${fmt(item.time)} ${item.title || item.event || item.name || '事件'}`))
  rows.push('未处理预警：')
  ;(summary.value.unhandled_alerts || summary.value.completion?.tasks || []).slice(0, 6).forEach((item: any) => rows.push(`- ${item.title || item.action || '待处理事项'}`))
  rows.push('今日问题清单：')
  ;(summary.value.clinical_priorities || []).slice(0, 6).forEach((item: any, idx: number) => rows.push(`${idx + 1}. ${item.title || '临床问题'}`))
  rows.push('按系统分类：')
  systemTabs.forEach((system) => {
    const assess = systemAssessment(system.key)
    const events = summary.value?.systems?.[system.key] || []
    rows.push(`${system.label}：${assess?.headline || events[0]?.title || '暂无明确问题'}；待复评：${events.length ? `${events.length}项事件` : '常规复评'}`)
  })
  editableDraft.value = rows.join('\n')
  versionHistory.value = [{ id: 'ai', label: `版本1：AI/系统初稿 ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}` }]
}

async function loadVersionHistory() {
  if (!activePatient.value?.patient_id) return
  const res = await getRoundingVersions(activePatient.value.patient_id)
  const rows = res.data?.versions || []
  versionHistory.value = rows.map((item: any) => ({
    id: item.version_id,
    label: `版本${item.version_no}：${item.status === 'confirmed' ? '医生确认' : item.source || '草稿'} ${fmt(item.created_at)}`,
  }))
  latestVersionId.value = rows[0]?.version_id || ''
}

async function confirmRoundingDraft() {
  if (!activePatient.value?.patient_id || !editableDraft.value.trim()) return
  const saved = await postRoundingVersion(activePatient.value.patient_id, {
    content: editableDraft.value,
    status: 'draft',
    source: 'doctor_edit',
    summary_snapshot: summary.value || {},
  })
  const versionId = saved.data?.version?.version_id
  if (versionId) {
    await postRoundingVersionConfirm(activePatient.value.patient_id, versionId, { status: 'confirmed' })
  }
  await loadVersionHistory()
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
watch(() => [route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department, route.query.patientId, route.query.patient_id], () => {
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
  grid-template-columns: 1.25fr repeat(4, minmax(0, 1fr));
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
.completion-card i {
  display: block;
  height: 8px;
  margin-top: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255,255,255,.08);
}
.completion-card b {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #22c55e, #67e8f9);
}
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
.action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.action-card {
  min-height: 76px;
  padding: 12px;
  border: 1px solid rgba(125,211,252,.16);
  border-radius: 14px;
  color: inherit;
  background: rgba(2, 8, 20, .28);
  text-align: left;
  cursor: pointer;
  transition: transform .16s ease, border-color .16s ease;
}
.action-card:hover {
  transform: translateY(-1px);
  border-color: rgba(103,232,249,.42);
}
.action-card.prio-high {
  border-color: rgba(251,113,133,.28);
}
.action-card strong,
.action-card span {
  display: block;
}
.action-card strong {
  color: #e6f7ff;
}
.action-card span {
  margin-top: 8px;
  color: #8bdcf1;
  font-size: 12px;
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
  align-items: stretch;
}
.priority-card {
  display: grid;
  gap: 10px;
  align-content: start;
  min-height: 118px;
}
.priority-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.priority-head strong {
  color: #e6f7ff;
  line-height: 1.35;
}
.priority-card p {
  color: #c9d9e6;
  line-height: 1.6;
}
.evidence-list, .question-list {
  display: grid;
  gap: 8px;
}
.evidence-list span {
  min-height: 30px;
  padding: 8px 10px;
  border-radius: 12px;
  color: #bfefff;
  background: rgba(14, 116, 144, .18);
  line-height: 1.45;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.question-list em {
  display: block;
  padding: 8px 10px;
  border-radius: 12px;
  color: #fef3c7;
  background: rgba(113, 63, 18, .22);
  font-style: normal;
  font-size: 12px;
  line-height: 1.45;
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
.editable-rounding {
  display: grid;
  gap: 10px;
  border: 1px solid rgba(125,167,214,.16);
  border-radius: 14px;
  padding: 12px;
  background: rgba(10,25,42,.72);
}
.editable-rounding textarea {
  width: 100%;
  resize: vertical;
  border-radius: 10px;
  border: 1px solid rgba(125,211,252,.16);
  background: rgba(8,20,34,.94);
  color: #e6f7ff;
  padding: 10px 12px;
  line-height: 1.7;
}
.version-row,
.confirm-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.version-row span {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(8,47,73,.5);
  color: #bfefff;
  font-size: 12px;
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

html[data-theme='light'] .rounding-page {
  color: #10243d;
  background:
    radial-gradient(circle at 10% 0%, rgba(14, 165, 233, .14), transparent 32%),
    radial-gradient(circle at 88% 8%, rgba(20, 184, 166, .10), transparent 30%),
    linear-gradient(180deg, rgba(236, 252, 255, .96), rgba(247, 250, 252, .98));
}
html[data-theme='light'] .rounding-hero,
html[data-theme='light'] .census-panel,
html[data-theme='light'] .summary-panel {
  border-color: rgba(203, 213, 225, .88);
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, .12), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(244, 249, 253, .98));
  box-shadow: 0 14px 34px rgba(15, 23, 42, .08);
}
html[data-theme='light'] .eyebrow,
html[data-theme='light'] .ghost-link,
html[data-theme='light'] .bed-large {
  color: #0369a1;
}
html[data-theme='light'] h1,
html[data-theme='light'] .hero-copy strong,
html[data-theme='light'] .panel-head h2,
html[data-theme='light'] .summary-head h2,
html[data-theme='light'] .section-title,
html[data-theme='light'] .patient-title strong,
html[data-theme='light'] .quick-strip strong,
html[data-theme='light'] .trend-card strong,
html[data-theme='light'] .digest-grid strong,
html[data-theme='light'] .check-item strong,
html[data-theme='light'] .priority-head strong,
html[data-theme='light'] .assessment-card strong,
html[data-theme='light'] .focus-head strong,
html[data-theme='light'] .event-row strong,
html[data-theme='light'] .organ-chip strong {
  color: #12314f;
}
html[data-theme='light'] .hero-copy p,
html[data-theme='light'] .panel-head p,
html[data-theme='light'] .summary-head p,
html[data-theme='light'] .summary-head h2 span,
html[data-theme='light'] .patient-main p,
html[data-theme='light'] .patient-main small,
html[data-theme='light'] .muted,
html[data-theme='light'] .disclaimer,
html[data-theme='light'] .soft-empty,
html[data-theme='light'] .quick-strip span,
html[data-theme='light'] .trend-card span,
html[data-theme='light'] .digest-grid span,
html[data-theme='light'] .digest-grid small,
html[data-theme='light'] .check-item small,
html[data-theme='light'] .priority-card p,
html[data-theme='light'] .bodymap-side p,
html[data-theme='light'] .organ-chip span,
html[data-theme='light'] .bodymap-note,
html[data-theme='light'] .assessment-card p,
html[data-theme='light'] .assessment-card span,
html[data-theme='light'] .focus-card p,
html[data-theme='light'] .focus-card small {
  color: #64748b;
}
html[data-theme='light'] .metric-card,
html[data-theme='light'] .quick-strip article,
html[data-theme='light'] .trend-card,
html[data-theme='light'] .focus-card,
html[data-theme='light'] .digest-grid article,
html[data-theme='light'] .priority-card,
html[data-theme='light'] .assessment-card,
html[data-theme='light'] .patient-card,
html[data-theme='light'] .briefing-side,
html[data-theme='light'] .bodymap-visual,
html[data-theme='light'] .organ-chip,
html[data-theme='light'] .bodymap-note {
  border-color: rgba(203, 213, 225, .82);
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, .08), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(244, 249, 253, .98));
  box-shadow: 0 8px 22px rgba(15, 23, 42, .05);
}
html[data-theme='light'] .metric-card--cyan {
  border-color: rgba(14, 165, 233, .22);
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, .14), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(235, 248, 252, .98));
}
html[data-theme='light'] .metric-card--red {
  border-color: rgba(251, 113, 133, .24);
  background:
    radial-gradient(circle at top right, rgba(251, 113, 133, .12), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(255, 241, 242, .96));
}
html[data-theme='light'] .metric-card--orange {
  border-color: rgba(245, 158, 11, .26);
  background:
    radial-gradient(circle at top right, rgba(245, 158, 11, .13), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(255, 251, 235, .96));
}
html[data-theme='light'] .metric-card span,
html[data-theme='light'] .metric-card small {
  color: #64748b;
}
html[data-theme='light'] .metric-card strong {
  color: #12314f;
}
html[data-theme='light'] .patient-card:hover,
html[data-theme='light'] .patient-card.active,
html[data-theme='light'] .organ-chip:hover,
html[data-theme='light'] .organ-chip.active {
  border-color: rgba(14, 165, 233, .38);
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, .14), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(232, 247, 252, .98));
  box-shadow: inset 3px 0 0 rgba(14, 165, 233, .68), 0 8px 20px rgba(14, 165, 233, .08);
}
html[data-theme='light'] .select-dot span {
  border-color: rgba(14, 165, 233, .34);
  background: rgba(248, 250, 252, .98);
}
html[data-theme='light'] .bed-pill,
html[data-theme='light'] .bed-large {
  border-color: rgba(14, 165, 233, .24);
  background: rgba(240, 249, 255, .98);
  color: #0369a1;
}
html[data-theme='light'] .summary-head {
  border-bottom-color: rgba(203, 213, 225, .82);
}
html[data-theme='light'] .briefing-section,
html[data-theme='light'] .bodymap-section,
html[data-theme='light'] .priority-section,
html[data-theme='light'] .trend-section,
html[data-theme='light'] .ai-box,
html[data-theme='light'] .system-tabs {
  border: 1px solid rgba(203, 213, 225, .82);
  background:
    radial-gradient(circle at top right, rgba(20, 184, 166, .08), transparent 40%),
    linear-gradient(180deg, rgba(255, 255, 255, .98), rgba(241, 248, 253, .96));
  box-shadow: 0 8px 22px rgba(15, 23, 42, .04);
}
html[data-theme='light'] .digest-headline {
  color: #1e3a5f;
}
html[data-theme='light'] .evidence-list span {
  color: #0369a1;
  background: rgba(240, 249, 255, .98);
  border: 1px solid rgba(186, 230, 253, .88);
}
html[data-theme='light'] .question-list em {
  color: #92400e;
  background: rgba(255, 251, 235, .9);
  border-radius: 10px;
  padding: 6px 8px;
}
html[data-theme='light'] .organ-chip.sev-critical {
  border-color: rgba(251, 113, 133, .34);
  background:
    radial-gradient(circle at top right, rgba(251, 113, 133, .12), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(255, 241, 242, .96));
}
html[data-theme='light'] .assessment-card {
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, .10), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(244, 249, 253, .98));
}
html[data-theme='light'] .rounding-page :deep(.ant-input),
html[data-theme='light'] .rounding-page :deep(.ant-select-selector) {
  border-color: rgba(203, 213, 225, .92) !important;
  background: rgba(248, 250, 252, .98) !important;
  color: #0f172a !important;
}
html[data-theme='light'] .rounding-page :deep(.ant-input::placeholder) {
  color: #94a3b8;
}
html[data-theme='light'] .rounding-page :deep(.ant-select-selection-item),
html[data-theme='light'] .rounding-page :deep(.ant-select-selection-placeholder) {
  color: #334155 !important;
}
html[data-theme='light'] .rounding-page :deep(.ant-tabs-tab) {
  color: #64748b;
}
html[data-theme='light'] .rounding-page :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: #0369a1 !important;
}
html[data-theme='light'] .rounding-page :deep(.ant-tabs-ink-bar) {
  background: #0ea5e9;
}
html[data-theme='light'] .rounding-page :deep(.ant-timeline-item-tail) {
  border-inline-start-color: rgba(203, 213, 225, .9);
}
html[data-theme='light'] .rounding-page :deep(.ant-empty-description) {
  color: #64748b;
}
@media (max-width: 1280px) {
  .metric-grid, .quick-strip, .trend-grid, .digest-grid, .priority-grid, .action-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .rounding-layout { grid-template-columns: 1fr; }
  .patient-list { max-height: 420px; }
}
@media (max-width: 760px) {
  .rounding-page { padding: 12px; }
  .rounding-hero, .summary-head { flex-direction: column; align-items: stretch; }
  .metric-grid, .quick-strip, .trend-grid, .filters, .bodymap-section, .organ-chip-grid, .briefing-section, .digest-grid, .priority-grid, .action-grid { grid-template-columns: 1fr; }
  .patient-card { grid-template-columns: 24px 50px minmax(0, 1fr); }
}
</style>
