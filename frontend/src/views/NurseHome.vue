<template>
  <section class="nurse-home">
    <header class="nurse-top ds-card">
      <div class="home-title">
        <strong>{{ isHeadMode ? '护士长首页' : '护士首页' }}</strong>
        <span>{{ isHeadMode ? '护士长' : '责任护士' }} · {{ home?.account?.dept || routeDept || '科室待识别' }}</span>
      </div>
      <div class="top-meta">
        <span>{{ accountName }}</span>
        <span>{{ shiftText }}</span>
        <span>{{ isHeadMode ? `全科床位：${sortedHeadBeds.length} 床` : `我的床位：${bedText}` }}</span>
      </div>
      <div class="workload">
        <span>工作负荷 {{ workload.used_minutes || 0 }} / {{ workload.estimated_minutes || 0 }} 分钟</span>
        <i><b :style="{ width: `${workload.percent || 0}%` }"></b></i>
      </div>
      <button type="button" @click="load">刷新</button>
    </header>

    <div v-if="loading" class="empty">正在读取本班床位和风险提醒...</div>
    <div v-else-if="error" class="empty danger">{{ error }}</div>

    <template v-else>
      <section class="start-guide ds-card">
        <div>
          <span>{{ isHeadMode ? '护士长看板' : '今天从这里开始' }}</span>
          <strong>{{ isHeadMode ? '先看全科床位，再看工作负荷，最后追踪未闭环护理事件。' : '先看我的床位，再处理本班提醒，下班前生成交班单。' }}</strong>
        </div>
        <button type="button" @click="showOnboarding = true">查看3步引导</button>
      </section>

      <section class="nurse-summary">
        <article v-for="item in nurseSummary" :key="item.key" :class="['summary-card', 'ds-card', 'ds-kpi', kpiToneClass(item.tone)]">
          <div class="ds-kpi-icon">
            <TeamOutlined v-if="item.key === 'beds'" />
            <ClockCircleOutlined v-else-if="item.key === 'tasks'" />
            <BellOutlined v-else-if="item.key === 'reminders'" />
            <CheckCircleOutlined v-else-if="item.key === 'quality'" />
          </div>
          <div>
            <span class="ds-kpi-label">{{ item.label }}</span>
            <strong class="ds-kpi-num">{{ item.value }}</strong>
            <em>{{ item.hint }}</em>
          </div>
        </article>
      </section>
      <div v-if="home?.head_degraded || home?.bundle_degraded" class="empty small">
        {{ home?.head_degraded || home?.bundle_degraded }}
      </div>

      <main v-if="isHeadMode" class="head-layout">
        <section class="panel ds-card">
          <div class="panel-head"><strong>全科床位</strong><span>{{ sortedHeadBeds.length }} 床</span></div>
          <div class="bed-cloud">
            <span v-for="b in sortedHeadBeds" :key="b.patient_id" class="ds-list-item">
              <i :class="['ds-dot', bedDotClass(b)]"></i>
              <b>{{ displayBed(b.bed) }}</b>
              <em>{{ b.name || '未知患者' }}</em>
            </span>
          </div>
        </section>
        <section class="panel ds-card">
          <div class="panel-head"><strong>工作负荷热力图</strong><span>本班护理记录密度</span></div>
          <div class="heatmap">
            <article v-for="row in heatmap" :key="row.nurse" :class="`density-${row.tone}`">
              <strong>{{ row.nurse }} · {{ row.task_density }}</strong>
              <i>
                <b v-for="bucket in row.buckets || []" :key="`${row.nurse}-${bucket.time}`" :style="{ height: `${Math.min(100, Math.max(12, Number(bucket.count || 0) * 10))}%` }" :title="`${bucket.time} ${bucket.count}条`"></b>
              </i>
            </article>
          </div>
        </section>
        <section class="panel head-side">
          <div class="panel-head"><strong>异常事件</strong><span>{{ headEvents.length }} 条</span></div>
          <div class="head-event-grid">
            <article v-for="event in sortedHeadEvents" :key="`${event.patient_id}-${event.time}-${event.title}`" class="head-event ds-list-item">
              <i :class="['ds-dot', eventDotClass(event)]"></i>
              <div>
                <strong>{{ displayBed(event.bed) }} {{ event.title }}</strong>
                <span>{{ event.type }} · {{ fmt(event.time) }}</span>
              </div>
            </article>
          </div>
          <div v-if="!headEvents.length" class="empty small">本班暂无未闭环护理异常。</div>
          <div class="quality-row">
            <span>跌倒 {{ headQuality.falls || 0 }}</span>
            <span>压疮 {{ headQuality.pressure_ulcers || 0 }}</span>
            <span>管路脱出 {{ headQuality.line_displacement || 0 }}</span>
            <span>给药差错 {{ headQuality.medication_errors || 0 }}</span>
          </div>
        </section>
      </main>

      <main v-else class="nurse-grid">
        <section class="panel beds-panel">
          <div class="panel-head">
            <strong>我的床位</strong>
            <span>{{ sortedBeds.length }} 床</span>
          </div>
          <div class="bed-board">
            <article v-for="bed in sortedBeds" :key="bed.patient_id" class="bed-card ds-list-item" @click="goPatient(bed.patient_id)">
              <div class="bed-card__main">
                <span class="bed-title"><i :class="['ds-dot', bedDotClass(bed)]"></i><strong>{{ displayBed(bed.bed) }}</strong></span>
                <span>{{ bed.name || '未知患者' }}</span>
              </div>
              <div class="bed-card__meta">
                <span>责任护士 {{ bed.responsible_nurse || accountName }}</span>
                <span>首次记录 {{ fmt(bed.first_record_time) }}</span>
              </div>
              <button
                v-if="tasksByBed(bed.patient_id).length"
                type="button"
                class="bed-risk-button"
                @click.stop="selectTask(tasksByBed(bed.patient_id)[0])"
              >
                {{ tasksByBed(bed.patient_id).length }} 条风险提醒
              </button>
              <span v-else class="bed-clear">暂无风险提醒</span>
            </article>
            <div v-if="!beds.length" class="empty small">{{ nurseEmptyText }}</div>
          </div>
        </section>

        <aside class="side">
          <section class="panel ds-card">
            <div class="panel-head"><strong>本班提醒</strong><span>{{ (home?.timeline || []).length }} 条</span></div>
            <article v-for="task in home?.timeline || []" :key="task.task_id" :class="['notice-card', `is-${task.status}`]" @click="selectTask(task)">
              <div>
                <strong>{{ cleanVisibleText(displayName(task.title)) }}</strong>
                <span>{{ displayBed(task.bed) }} {{ task.patient_name || '未知患者' }} · {{ fmt(task.due_at) }}</span>
              </div>
              <button type="button">处理</button>
            </article>
            <div v-if="!(home?.timeline || []).length" class="empty small">本班暂无需要处理的风险提醒。</div>
          </section>
          <section class="panel ds-card">
            <div class="panel-head"><strong>安全清单</strong><span>闭环状态</span></div>
            <article v-for="item in bundles" :key="item.code" :class="`bundle is-${item.tone}`">
              <strong>{{ displayName(item.name || item.code) }}</strong>
              <span>{{ item.data_state === 'missing' ? '暂无同步' : `${item.completed}/${item.total}` }}</span>
            </article>
            <div v-if="home?.bundle_degraded && !bundles.length" class="empty small">{{ home.bundle_degraded }}</div>
            <div v-else-if="!bundles.length" class="empty small">本班安全清单暂无同步记录。</div>
          </section>
          <section class="panel ds-card">
            <div class="panel-head"><strong>AI 提醒</strong><span>护理相关</span></div>
            <article v-for="item in reminders" :key="item._id || item.created_at" class="reminder">
              <strong>{{ shortText(displayName(item.name || item.alert_type || item.rule_id)) }}</strong>
              <div>
                <button type="button" @click="feedbackReminder(item, 'resolved')">已处理</button>
                <button type="button" @click="feedbackReminder(item, 'escalate')">转给医生</button>
                <button type="button" @click="feedbackReminder(item, 'false_positive')">不是问题</button>
              </div>
            </article>
            <div v-if="!reminders.length" class="empty small">暂无护理执行相关 AI 提醒。</div>
          </section>
          <!-- 生理危急 / 临床风险（P0/P1） -->
          <section v-if="physiologicAlerts.length" class="panel ds-card panel--alert">
            <div class="panel-head"><strong>⚠ 危急/高风险</strong><span class="badge-red">{{ physiologicCount }}</span></div>
            <article v-for="item in physiologicAlerts.slice(0, 6)" :key="item._id || item.created_at" class="alert-item alert-item--p0">
              <div class="alert-item-main">
                <span :class="['dot', priorityDot(item.priority)]"></span>
                <strong>{{ item.bed || '—' }}床 {{ item.patient_name || '—' }}</strong>
                <span class="alert-item-name">{{ item.name || item.rule_id }}</span>
              </div>
              <div class="alert-item-meta">
                <span class="pill pill--domain">{{ formatDomainLabel(item.alert_domain) }}</span>
                <span class="pill pill--priority">{{ formatPriorityLabel(item.priority) }}</span>
                <small>{{ fmtTime(item.created_at) || '—' }}</small>
              </div>
            </article>
          </section>
          <!-- 流程任务（P2/P3） -->
          <section v-if="workflowTasks.length" class="panel ds-card panel--task">
            <div class="panel-head"><strong>📋 流程任务</strong><span class="badge-amber">{{ workflowTaskCount }}</span></div>
            <article v-for="item in sortedWorkflowTasks" :key="item._id || item.created_at" class="alert-item" :class="escalationClass(item)">
              <div class="alert-item-main">
                <span :class="['dot', priorityDot(item.priority)]"></span>
                <strong>{{ item.bed || '—' }}床 {{ item.patient_name || '—' }}</strong>
                <span class="alert-item-name">{{ item.name || item.rule_id }}</span>
              </div>
              <div class="alert-item-meta">
                <span v-if="item.escalation_of" class="pill pill--escalated">已升级</span>
                <span v-if="item.alert_episode_id" class="pill pill--episode">同一事件</span>
                <span class="pill pill--priority">{{ formatPriorityLabel(item.priority) }}</span>
                <small>{{ fmtTime(item.due_at || item.created_at) || '—' }}</small>
              </div>
            </article>
            <div v-if="!workflowTasks.length" class="empty small">暂无流程任务。</div>
          </section>
        </aside>
      </main>

      <section :class="['handoff-bar', { open: handoffShouldOpen }]">
        <div>
          <strong>一键交班</strong>
          <span>{{ handoffError || handoffStatus }}</span>
        </div>
        <button type="button" :disabled="handoffLoading || !sortedBeds.length" @click="generateHandoff">{{ handoffLoading ? '生成中' : '生成本班交班单' }}</button>
      </section>
      <section v-if="handoffItems.length" class="panel handoff-editor">
        <div class="panel-head">
          <strong>本班交班单</strong>
          <div class="handoff-switch">
            <button type="button" :class="{ active: handoffMode === 'isbar' }" @click="handoffMode = 'isbar'">ISBAR</button>
            <button type="button" :class="{ active: handoffMode === 'ipass' }" @click="handoffMode = 'ipass'">I-PASS</button>
          </div>
        </div>
        <article v-for="item in handoffItems" :key="item.patient_id" class="handoff-item">
          <strong>{{ item.bed || '--' }}床 {{ item.name || '未知患者' }}</strong>
          <label v-for="section in activeHandoffSections" :key="`${item.patient_id}-${section.key}`">
            <span>{{ section.label }}</span>
            <textarea v-model="item[handoffMode][section.key]" rows="2"></textarea>
          </label>
        </article>
      </section>

      <div v-if="selectedTask" class="modal-mask" @click.self="selectedTask = null">
        <div class="task-modal">
          <strong>{{ selectedTask.title }}</strong>
          <p>{{ selectedTask.bed }}床 {{ selectedTask.patient_name }} · {{ fmt(selectedTask.due_at) }}</p>
          <div class="modal-actions">
            <button type="button" @click="executeTask('executed')">执行</button>
            <button type="button" @click="executeTask('delay_15m')">推迟15分钟</button>
            <button type="button" @click="executeTask('handover')">转交</button>
            <button type="button" @click="executeTask('not_applicable')">不适用</button>
          </div>
        </div>
      </div>

      <div v-if="showOnboarding" class="onboarding-mask" @click.self="dismissOnboarding">
        <div class="onboarding-card">
          <div class="panel-head">
            <strong>{{ isHeadMode ? '护士长看板3步用法' : '护士首页3步用法' }}</strong>
            <button type="button" @click="dismissOnboarding">知道了</button>
          </div>
          <ol v-if="isHeadMode">
            <li><b>先看全科床位</b><span>确认在科患者和床位分布。</span></li>
            <li><b>查看工作负荷</b><span>发现护理记录密度和人力压力。</span></li>
            <li><b>追踪未闭环事件</b><span>重点处理异常事件和护理质控命中。</span></li>
          </ol>
          <ol v-else>
            <li><b>先看我的床位</b><span>点击床位进入患者详情。</span></li>
            <li><b>处理本班提醒</b><span>对风险提醒执行、推迟、转交或标记不适用。</span></li>
            <li><b>下班前交班</b><span>一键生成本班 ISBAR 交班单。</span></li>
          </ol>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getNurseHome, postNurseHandoffGenerate, postNurseReminderFeedback, postNurseTaskExecute } from '../api'
import { useAuthStore } from '../stores/auth'
import { formatAlertTypeLabel, formatDomainLabel, formatPriorityLabel } from '../utils/displayLabels'
import { roleHomeConfig } from '../config/roleHomeConfig'
import { BellOutlined, CheckCircleOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons-vue'

const NURSE_HOME_CACHE_TTL_MS = 2 * 60 * 1000
const nurseHomeCache = new Map<string, { ts: number; data: any }>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const home = ref<any>(null)
const selectedTask = ref<any>(null)
const showOnboarding = ref(false)
const handoffLoading = ref(false)
const handoffError = ref('')
const handoffMode = ref<'isbar' | 'ipass'>('isbar')

function firstIdentityQuery(...keys: string[]) {
  for (const key of keys) {
    const value = route.query[key]
    const text = String(Array.isArray(value) ? value[0] : value || '').trim()
    if (text) return text
  }
  return ''
}
const routeIdentity = computed(() => firstIdentityQuery('user_id', 'userId', 'userName', 'useName', 'username'))
const userId = computed(() => String(routeIdentity.value || auth.effectiveUserId || '').trim())
const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim())
const routeDept = computed(() => String(route.query.dept || route.query.department || auth.dept || '').trim())
const homeCacheKey = computed(() => JSON.stringify({
  user_id: userId.value,
  shift_code: 'auto',
  view: String(route.query.view || '') || '',
  dept: routeDept.value,
  dept_code: routeDeptCode.value,
}))
const isHeadMode = computed(() => String(route.query.view || '').toLowerCase() === 'head' || ['head_nurse', 'charge_nurse'].includes(String(home.value?.account?.role || '').toLowerCase()))
const accountName = computed(() => home.value?.account?.display_name || home.value?.account?.userName || userId.value || '未识别护士')
const beds = computed(() => home.value?.beds || [])
const workload = computed(() => home.value?.workload || {})
const bundles = computed(() => home.value?.bundles || [])
const reminders = computed(() => home.value?.ai_reminders || [])

// ── 护理流程任务（workflow_reminder + quality_gap） ──
const workflowTasks = computed(() => {
  const all = home.value?.active_alerts || []
  return all.filter((a: any) => {
    const domain = String(a?.alert_domain || '').toLowerCase()
    return domain === 'workflow_reminder' || domain === 'quality_gap'
  })
})
const workflowTaskCount = computed(() => workflowTasks.value.length)

const physiologicAlerts = computed(() => {
  const all = home.value?.active_alerts || []
  return all.filter((a: any) => {
    const domain = String(a?.alert_domain || '').toLowerCase()
    const priority = String(a?.priority || '').toLowerCase()
    return domain === 'physiologic_alarm' || (domain === 'clinical_risk' && (priority === 'p0' || priority === 'p1'))
  })
})
const physiologicCount = computed(() => physiologicAlerts.value.length)

const PRIORITY_SORT: Record<string, number> = { p0: 0, p1: 1, p2: 2, p3: 3 }
const sortedWorkflowTasks = computed(() =>
  [...workflowTasks.value].sort((a: any, b: any) => {
    const pa = PRIORITY_SORT[String(a.priority || 'p3').toLowerCase()] ?? 3
    const pb = PRIORITY_SORT[String(b.priority || 'p3').toLowerCase()] ?? 3
    if (pa !== pb) return pa - pb
    const da = new Date(a.due_at || a.created_at || 0).getTime()
    const db = new Date(b.due_at || b.created_at || 0).getTime()
    return da - db
  })
)

function priorityDot(priority: string) {
  const p = String(priority || '').toLowerCase()
  if (p === 'p0') return 'dot-p0'
  if (p === 'p1') return 'dot-p1'
  return 'dot-p2'
}
function escalationClass(item: any) {
  return item.escalation_of ? 'is-escalated' : ''
}
const headBeds = computed(() => home.value?.head_view?.beds || [])
const sortedBeds = computed(() => sortBeds(beds.value))
const sortedHeadBeds = computed(() => sortBeds(headBeds.value))
const heatmap = computed(() => home.value?.head_view?.workload_heatmap || [])
const headEvents = computed(() => home.value?.head_view?.events || [])
const sortedHeadEvents = computed(() => sortBeds(headEvents.value, (row: any) => row?.bed))
const headQuality = computed(() => home.value?.head_view?.quality || {})
const nurseEmptyText = computed(() => cleanEmptyText(home.value?.data_state?.empty_reason, '本班暂未识别到分管床位，请完成接班护理记录后刷新。'))
const handoff = ref<any>(null)
const handoffItems = computed(() => handoff.value?.items || [])
const handoffStatus = computed(() => handoff.value?.handoff_id ? `已生成 ${handoffItems.value.length} 床 ISBAR 交班单，可在下方编辑确认。` : '下班前 1 小时自动展开，按 ISBAR 结构生成本班交班单。')
const isbarSections = [
  { key: 'identify', label: 'I 识别' },
  { key: 'situation', label: 'S 现状' },
  { key: 'background', label: 'B 背景' },
  { key: 'assessment', label: 'A 评估' },
  { key: 'recommendation', label: 'R 建议' },
]
const ipassSections = [
  { key: 'illness_severity', label: '病情严重度' },
  { key: 'patient_summary', label: '患者摘要' },
  { key: 'action_list', label: '行动清单' },
  { key: 'situation_awareness', label: '风险预判' },
  { key: 'synthesis_by_receiver', label: '接班确认' },
]
const activeHandoffSections = computed(() => handoffMode.value === 'isbar' ? isbarSections : ipassSections)
const shiftText = computed(() => {
  const s = home.value?.shift
  if (!s) return '班次待配置'
  return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
})
const bedText = computed(() => sortedBeds.value.length ? sortedBeds.value.map((b: any) => displayBed(b.bed)).join(' / ') : '待接班')
const handoffShouldOpen = computed(() => {
  const end = new Date(home.value?.shift?.end || 0).getTime()
  return end > 0 && end - Date.now() <= 60 * 60 * 1000
})
const taskStatusStats = computed(() => {
  const rows = home.value?.timeline || []
  const counts = rows.reduce((acc: Record<string, number>, task: any) => {
    const key = String(task?.status || 'future').trim() || 'future'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
  return [
    { key: 'overdue', label: '逾期', value: counts.overdue || 0 },
    { key: 'due', label: '到点', value: counts.due || 0 },
    { key: 'soon', label: '临近', value: counts.soon || 0 },
    { key: 'future', label: '待执行', value: counts.future || 0 },
    { key: 'done', label: '已完成', value: counts.done || 0 },
  ]
})
const nurseSummary = computed(() => {
  const qualityTotal = Object.values(headQuality.value || {}).reduce((sum: number, value: any) => sum + Number(value || 0), 0)
  const overdue = taskStatusStats.value.find((item) => item.key === 'overdue')?.value || 0
  return [
    { key: 'beds', label: isHeadMode.value ? '全科床位' : '我的床位', value: isHeadMode.value ? sortedHeadBeds.value.length : sortedBeds.value.length, hint: isHeadMode.value ? '当前科室在科' : '本班归属', tone: 'blue' },
    { key: 'tasks', label: '本班任务', value: (home.value?.timeline || []).length, hint: overdue ? `${overdue} 项逾期` : '按时间轴执行', tone: overdue ? 'red' : 'green' },
    { key: 'reminders', label: 'AI 提醒', value: reminders.value.length + headEvents.value.length, hint: isHeadMode.value ? '含未闭环事件' : '护理执行相关', tone: reminders.value.length || headEvents.value.length ? 'yellow' : 'green' },
    { key: 'quality', label: '护理质控', value: qualityTotal, hint: isHeadMode.value ? '本班事件命中' : `${bundles.value.length} 项安全清单`, tone: qualityTotal ? 'yellow' : 'green' },
  ]
})

function tasksByBed(pid: string) {
  return (home.value?.timeline || []).filter((task: any) => task.patient_id === pid)
}
function fmt(value: any) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--'
}
const fmtTime = fmt
function shortText(value: any) {
  const text = String(value || 'AI提醒')
  return text.length > 20 ? `${text.slice(0, 20)}...` : text
}
function displayName(value: any) {
  return formatAlertTypeLabel(value).replace(/\bBundle\b/gi, '防控清单')
}
function cleanVisibleText(value: any) {
  return String(value || '')
    .replace(/PRE-DELIRIC近似/g, '谵妄风险')
    .replace(/[()（）]/g, '')
    .trim()
}
function displayBed(value: any) {
  const text = String(value || '').trim()
  if (!text || text === '--') return '--床'
  return text.includes('床') ? text : `${text}床`
}
function kpiToneClass(tone: any) {
  const key = String(tone || '').toLowerCase()
  if (key === 'red' || key === 'danger') return 'is-danger'
  if (key === 'yellow' || key === 'warning') return 'is-warning'
  if (key === 'green' || key === 'success') return 'is-success'
  return 'is-brand'
}
function bedDotClass(row: any) {
  const key = String(row?.risk_level || row?.severity || row?.status || '').toLowerCase()
  if (['critical', 'danger', 'red', '危急'].includes(key)) return 'is-critical'
  if (['high', 'warning', 'warn', 'yellow', '关注', '高危'].includes(key)) return 'is-warn'
  return 'is-muted'
}
function eventDotClass(row: any) {
  const key = String(row?.severity || row?.level || row?.risk_level || row?.type || row?.title || '').toLowerCase()
  if (/critical|danger|red|危急|跌倒|压疮|脱出|差错/.test(key)) return 'is-critical'
  if (/high|warning|warn|yellow|高危|关注|逾期/.test(key)) return 'is-warn'
  return 'is-muted'
}
function bedSortParts(value: any) {
  const raw = String(value || '').trim()
  const normalized = raw
    .replace(/[０-９]/g, (char) => String.fromCharCode(char.charCodeAt(0) - 0xfee0))
    .replace(/[\s_-]+/g, '')
  const numberHit = normalized.match(/\d+/)
  return {
    hasNumber: numberHit ? 0 : 1,
    number: numberHit ? Number(numberHit[0]) : Number.MAX_SAFE_INTEGER,
    suffix: numberHit ? normalized.slice((numberHit.index || 0) + numberHit[0].length) : normalized,
    raw: normalized,
  }
}
function sortBeds(rows: any[], getBed: (row: any) => any = (row) => row?.bed) {
  return [...(rows || [])].sort((a: any, b: any) => {
    const left = bedSortParts(getBed(a))
    const right = bedSortParts(getBed(b))
    if (left.hasNumber !== right.hasNumber) return left.hasNumber - right.hasNumber
    if (left.number !== right.number) return left.number - right.number
    const suffixCompare = left.suffix.localeCompare(right.suffix, 'zh-CN', { numeric: true, sensitivity: 'base' })
    if (suffixCompare) return suffixCompare
    return left.raw.localeCompare(right.raw, 'zh-CN', { numeric: true, sensitivity: 'base' })
  })
}
function cleanEmptyText(value: any, fallback: string) {
  const text = String(value || '').trim()
  if (!text) return fallback
  if (/patient\s*表|account\s*表|nurseRecords|bedDoctorId|user[_-]?id|userId|collection|集合|数据库/i.test(text)) return fallback
  return text
}
function selectTask(task: any) {
  selectedTask.value = task
}
function goPatient(id: string) {
  if (id) router.push({ path: `/patient/${id}`, query: route.query })
}
async function executeTask(action: string) {
  if (!selectedTask.value) return
  await postNurseTaskExecute(selectedTask.value.task_id, {
    action,
    patient_id: selectedTask.value.patient_id,
    actor: userId.value,
  })
  selectedTask.value = null
  await load()
}
async function feedbackReminder(item: any, disposition: string) {
  const alertId = String(item?._id || item?.alert_id || '').trim()
  if (!alertId) return
  await postNurseReminderFeedback(alertId, {
    actor: userId.value,
    disposition,
    note: disposition === 'escalate' ? '护士首页转给医生' : disposition === 'false_positive' ? '护士首页反馈不是问题' : '护士首页标记已处理',
    override_reason_code: disposition === 'false_positive' ? 'not_nursing_issue' : undefined,
  })
  await load()
}
async function generateHandoff() {
  handoffLoading.value = true
  handoffError.value = ''
  try {
    const payload: { user_id: string; patient_ids: string[]; shift_code: string; dept?: string; dept_code?: string } = {
      user_id: userId.value,
      patient_ids: sortedBeds.value.map((b: any) => b.patient_id),
      shift_code: home.value?.shift?.code || 'auto',
    }
    if (routeDeptCode.value) payload.dept_code = routeDeptCode.value
    else if (routeDept.value) payload.dept = routeDept.value
    const { data } = await postNurseHandoffGenerate(payload)
    handoff.value = normalizeHandoff(data?.data || {})
  } catch (err: any) {
    handoffError.value = err?.message || '交班单生成失败，请稍后重试。'
  } finally {
    handoffLoading.value = false
  }
}
function normalizeHandoff(doc: any) {
  const items = Array.isArray(doc?.items) ? doc.items : []
  return {
    ...doc,
    items: items.map((item: any) => ({
      ...item,
      ipass: normalizeIpass(item?.ipass),
      isbar: normalizeIsbar(item?.isbar, item?.ipass, item),
    })),
  }
}
function normalizeIpass(value: any) {
  const source = value && typeof value === 'object' ? value : {}
  return {
    illness_severity: stringifySection(source.illness_severity || source.severity),
    patient_summary: stringifySection(source.patient_summary || source.summary),
    action_list: stringifySection(source.action_list || source.actions),
    situation_awareness: stringifySection(source.situation_awareness || source.awareness),
    synthesis_by_receiver: stringifySection(source.synthesis_by_receiver || source.receiver),
  }
}
function normalizeIsbar(value: any, ipassValue: any, item: any) {
  const source = value && typeof value === 'object' ? value : {}
  const ipass = normalizeIpass(ipassValue)
  return {
    identify: stringifySection(source.identify || source.identification || `${item?.bed || '--'}床 ${item?.name || '未知患者'}`),
    situation: stringifySection(source.situation || ipass.patient_summary),
    background: stringifySection(source.background || ipass.situation_awareness),
    assessment: stringifySection(source.assessment || ipass.synthesis_by_receiver),
    recommendation: stringifySection(source.recommendation || ipass.action_list),
  }
}
function stringifySection(value: any) {
  if (Array.isArray(value)) return value.map((item) => String(item || '').trim()).filter(Boolean).join('\n')
  return String(value || '').trim()
}
async function load() {
  if (!userId.value) {
    error.value = '未识别当前账号。'
    return
  }
  const cached = nurseHomeCache.get(homeCacheKey.value)
  const canUseCache = cached && Date.now() - cached.ts < NURSE_HOME_CACHE_TTL_MS
  if (canUseCache) {
    home.value = cached.data
    loading.value = false
  } else {
    loading.value = true
  }
  error.value = ''
  try {
    const params: { user_id: string; shift_code: string; view?: string; dept?: string; dept_code?: string } = {
      user_id: userId.value,
      shift_code: 'auto',
      view: String(route.query.view || '') || undefined,
    }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDept.value) params.dept = routeDept.value
    const { data } = await getNurseHome(params)
    home.value = data?.data || {}
    nurseHomeCache.set(homeCacheKey.value, { ts: Date.now(), data: home.value })
    auth.updateAccount(home.value?.account)
  } catch (err: any) {
    if (!canUseCache) error.value = err?.message || '护士首页加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  auth.hydrateFromQuery(route.query)
  cleanDuplicateIdentityQuery()
  void load()
  if (typeof window !== 'undefined') {
    const key = isHeadMode.value ? roleHomeConfig.headNurse.onboardingKey : roleHomeConfig.nurse.onboardingKey
    if (!window.localStorage.getItem(key)) showOnboarding.value = true
  }
})

watch(() => [route.query.user_id, route.query.userId, route.query.userName, route.query.useName, route.query.username, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department, route.query.view], () => {
  auth.hydrateFromQuery(route.query)
  void load()
})

function cleanDuplicateIdentityQuery() {
  const query = auth.cleanIdentityQuery(route.query)
  if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ path: route.path, query })
}
function dismissOnboarding() {
  showOnboarding.value = false
  if (typeof window !== 'undefined') {
    const key = isHeadMode.value ? roleHomeConfig.headNurse.onboardingKey : roleHomeConfig.nurse.onboardingKey
    window.localStorage.setItem(key, '1')
  }
}
</script>

<style scoped>
.nurse-home { padding: 12px 12px 80px; display: grid; gap: 12px; }
.start-guide { min-height: 66px; display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid rgba(34,211,238,.22); border-radius: var(--card-radius); background: var(--bg-surface); }
.start-guide div { display: grid; gap: 4px; }
.start-guide span { color: var(--text-muted); font-size: 12px; }
.start-guide strong { color: var(--text-primary); font-size: 15px; }
.nurse-top { min-height: 80px; display: grid; grid-template-columns: minmax(0,1fr) minmax(220px, auto) 320px auto; align-items: center; gap: 12px; padding: 14px; border: 1px solid rgba(125,211,252,.14); border-radius: var(--card-radius); background: var(--bg-surface); }
.nurse-top strong { color: var(--text-primary); font-size: 20px; }
.nurse-top span { color: var(--text-muted); font-size: 12px; }
.home-title { display: grid; gap: 4px; }
.top-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; text-align: right; }
.panel-head span, .empty, .bundle span, .task-modal p, .summary-card span, .summary-card em { color: var(--text-secondary); font-size: 12px; }
.workload { display: grid; gap: 6px; }
.workload i { height: 8px; border-radius: var(--card-radius); background: rgba(148,163,184,.25); overflow: hidden; }
.workload b { display: block; height: 100%; background: var(--chart-1); }
button { min-height: 44px; border: 1px solid rgba(125,211,252,.22); border-radius: var(--card-radius); background: var(--bg-surface); color: var(--text-primary); padding: 0 10px; cursor: pointer; }
.nurse-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--card-gap); }
.summary-card { min-height: 82px; padding: 14px; border: 1px solid rgba(125,211,252,.14); border-radius: var(--card-radius); background: var(--bg-surface); }
.summary-card .ds-kpi-icon { width: 40px; height: 40px; border-radius: 8px; }
.summary-card .ds-kpi-num { font-size: 25px; line-height: 1; }
.summary-card em { font-style: normal; }
.nurse-grid { min-height: 560px; display: grid; grid-template-columns: minmax(0, 3fr) minmax(340px, 2fr); gap: 12px; }
.side, .head-layout { display: grid; gap: 12px; }
.head-layout { grid-template-columns: 1fr 1fr; }
.panel { min-width: 0; display: grid; align-content: start; gap: 10px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: var(--card-radius); background: var(--bg-surface); }
.panel-head { display: flex; justify-content: space-between; gap: 10px; }
.panel-head strong { color: var(--text-primary); }
.task-legend { display: flex; flex-wrap: wrap; gap: 8px; }
.task-legend span { padding: 5px 9px; border-radius: var(--card-radius); background: var(--bg-surface); color: var(--text-secondary); font-size: 12px; }
.task-legend .is-overdue { color: var(--danger-soft); border: 1px solid rgba(239,68,68,.4); }
.task-legend .is-due { color: var(--warning-soft); border: 1px solid rgba(245,158,11,.4); }
.task-legend .is-soon { color: var(--chart-1); border: 1px solid rgba(56,189,248,.36); }
.task-legend .is-done { color: var(--success); border: 1px solid rgba(52,211,153,.36); }
.timeline { overflow: auto; display: grid; gap: 8px; }
.time-head { min-width: 760px; display: grid; grid-template-columns: 84px repeat(7, 1fr); color: #8caabd; font-size: 12px; }
.bed-line { min-width: 760px; display: grid; grid-template-columns: 84px minmax(0,1fr); align-items: stretch; gap: 8px; }
.bed-line > strong { display: grid; place-items: center; color: var(--text-primary); border-radius: var(--card-radius); background: var(--bg-surface); }
.task-strip { min-height: 58px; position: relative; display: flex; align-items: center; gap: 8px; padding: 7px; border-radius: var(--card-radius); background: repeating-linear-gradient(90deg, rgba(125,211,252,.08) 0, rgba(125,211,252,.08) 1px, transparent 1px, transparent 10.416%); overflow-x: auto; }
.task-card { flex: 0 0 132px; font-size: 12px; }
.is-future { opacity: .7; }
.is-soon { border-color: rgba(56,189,248,.55); }
.is-due { border-color: rgba(245,158,11,.65); }
.is-overdue { border-color: rgba(239,68,68,.7); color: var(--danger-soft); }
.is-done { border-color: rgba(52,211,153,.55); color: var(--success); }
.bundle, .reminder { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px; border-radius: var(--card-radius); background: var(--bg-surface); }
.bundle strong, .reminder strong { color: var(--text-primary); font-size: 13px; }
.bundle.is-green { border-left: 3px solid #1A9C5B; }
.bundle.is-yellow { border-left: 3px solid #E8901C; }
.bundle.is-red { border-left: 3px solid #D9342B; }
.reminder { display: grid; }
.reminder div { display: flex; gap: 8px; flex-wrap: wrap; }
.reminder button { min-height: 36px; }
.handoff-bar { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: var(--card-radius); background: var(--bg-surface); opacity: .82; }
.handoff-bar.open { border-color: rgba(245,158,11,.42); opacity: 1; }
.handoff-bar strong { color: var(--text-primary); display: block; }
.handoff-bar span { color: var(--text-secondary); font-size: 12px; }
.empty { padding: 14px; border-radius: var(--card-radius); background: var(--bg-surface); }
.empty.small { padding: 10px; }
.danger { color: var(--danger-soft); }
.modal-mask { position: fixed; inset: 0; z-index: 200; display: grid; place-items: center; background: var(--bg-surface); }
.task-modal { width: min(520px, calc(100vw - 24px)); display: grid; gap: 12px; padding: 16px; border-radius: var(--card-radius); border: 1px solid rgba(125,211,252,.22); background: var(--bg-surface); }
.task-modal strong { color: var(--text-primary); font-size: 18px; }
.modal-actions { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; }
.bed-cloud { display: grid; grid-template-columns: repeat(auto-fill, minmax(116px, 1fr)); gap: 8px; }
.heatmap { display: flex; flex-wrap: wrap; gap: 8px; }
.bed-cloud span {
  position: relative;
  min-width: 0;
  min-height: 54px;
  display: grid;
  align-content: center;
  gap: 3px;
  padding: 8px 10px 8px 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  box-shadow: none;
  transition: background .18s ease;
}
.bed-cloud span:hover {
  background: var(--bg-surface-2);
}
.bed-cloud .ds-dot {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
}
.bed-cloud span b {
  color: #1D2129;
  font-size: 14px;
  line-height: 1.1;
  font-weight: 800;
}
.bed-cloud span em {
  min-width: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.2;
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.heatmap article { padding: 8px 10px; border-radius: var(--card-radius); background: var(--bg-surface); color: var(--text-primary); }
.heatmap article { min-width: 150px; display: grid; gap: 8px; }
.heatmap i { height: 42px; display: flex; align-items: end; gap: 3px; }
.heatmap b { width: 10px; min-height: 8px; border-radius: 3px 3px 0 0; background: var(--chart-1); }
.density-high { border: 1px solid rgba(239,68,68,.6); }
.density-medium { border: 1px solid rgba(245,158,11,.55); }
.density-low { border: 1px solid rgba(52,211,153,.45); }
.head-side { grid-column: 1 / -1; }
.head-event-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.head-event { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 8px; padding: 10px; border-radius: 6px; background: transparent; }
.head-event:hover { background: var(--bg-surface-2); }
.head-event strong { color: var(--text-primary); font-size: 13px; }
.head-event span, .quality-row span { color: var(--text-secondary); font-size: 12px; }
.quality-row { display: flex; flex-wrap: wrap; gap: 8px; }
.quality-row span { padding: 8px 10px; border-radius: var(--card-radius); background: var(--bg-surface); }
.handoff-editor { margin-top: -4px; }
.handoff-switch { display: flex; gap: 6px; }
.handoff-switch button { min-height: 34px; padding: 0 10px; }
.handoff-switch button.active { border-color: rgba(52,211,153,.55); color: var(--success); background: var(--bg-surface); }
.handoff-item { display: grid; gap: 8px; padding: 10px; border-radius: var(--card-radius); background: var(--bg-surface); }
.handoff-item > strong { color: var(--text-primary); }
.handoff-item label { display: grid; gap: 4px; }
.handoff-item label span { color: var(--text-secondary); font-size: 12px; }
.handoff-item textarea { resize: vertical; min-height: 58px; border-radius: var(--card-radius); border: 1px solid rgba(125,211,252,.18); background: var(--bg-surface); color: var(--text-primary); padding: 8px; }
.beds-panel {
  min-height: 420px;
}
.bed-board {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.bed-card {
  min-width: 0;
  min-height: 126px;
  display: grid;
  align-content: space-between;
  gap: 12px;
  padding: 14px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  box-shadow: none;
  cursor: pointer;
  transition: background .18s ease;
}
.bed-card:hover {
  background: var(--bg-surface-2);
}
.bed-card__main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}
.bed-card__main strong {
  color: #1D2129;
  font-size: 14px;
  line-height: 1;
}
.bed-card__main span {
  min-width: 0;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bed-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: inherit;
}
.bed-card__meta {
  display: grid;
  gap: 4px;
}
.bed-card__meta span,
.bed-clear {
  color: var(--text-secondary);
  font-size: 12px;
}
.bed-risk-button {
  width: 100%;
  min-height: 38px;
  border-color: rgba(245, 158, 11, .48);
  background: var(--bg-surface);
  color: var(--warning-soft);
}
.bed-clear {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  color: var(--success);
}
.notice-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  cursor: pointer;
}
.notice-card div {
  min-width: 0;
  display: grid;
  gap: 4px;
}
.notice-card strong {
  min-width: 0;
  color: var(--text-primary);
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notice-card span {
  color: var(--text-secondary);
  font-size: 12px;
}
.notice-card button {
  min-height: 34px;
  flex: 0 0 auto;
}
.notice-card.is-overdue {
  border-color: rgba(239, 68, 68, .42);
  background: var(--bg-surface);
}
.notice-card.is-due {
  border-color: rgba(245, 158, 11, .42);
}
.notice-card.is-soon {
  border-color: rgba(56, 189, 248, .38);
}
.notice-card.is-done {
  opacity: .72;
}
.ds-badge {
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  line-height: 18px;
  border: 0;
}
.ds-badge--danger { background: #FFECE8; color: #D9342B; }
.ds-badge--warning { background: #FFF7E8; color: #A65A0C; }
.ds-badge--success { background: #E8FFEA; color: #1A9C5B; }
.ds-badge--info { background: #E8F3FF; color: #15558D; }
:global(.ai-pulse-root) { z-index: 120; }
.onboarding-mask { position: fixed; inset: 0; z-index: 400; display: grid; place-items: center; background: var(--bg-surface); padding: 16px; }
.onboarding-card { width: min(560px, 100%); display: grid; gap: 12px; padding: 16px; border: 1px solid rgba(125,211,252,.24); border-radius: var(--card-radius); background: var(--bg-surface); box-shadow: var(--card-shadow); }
.onboarding-card ol { margin: 0; padding-left: 20px; display: grid; gap: 10px; }
.onboarding-card li { color: var(--text-primary); }
.onboarding-card li b { display: block; }
.onboarding-card li span { display: block; color: var(--text-secondary); font-size: 12px; margin-top: 4px; }
@media (max-width: 1024px) { .nurse-top, .nurse-summary, .nurse-grid, .head-layout { grid-template-columns: 1fr; } .side { grid-template-columns: 1fr 1fr; } .top-meta { justify-content: flex-start; text-align: left; } }
@media (max-width: 760px) { .side, .handoff-bar, .head-event-grid { grid-template-columns: 1fr; flex-direction: column; align-items: stretch; } }

html[data-theme='light'] .nurse-home {
  background: var(--bg-base);
}
html[data-theme='light'] .nurse-top,
html[data-theme='light'] .start-guide,
html[data-theme='light'] .panel,
html[data-theme='light'] .handoff-bar,
html[data-theme='light'] .task-modal,
html[data-theme='light'] .summary-card {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .nurse-top strong,
html[data-theme='light'] .start-guide strong,
html[data-theme='light'] .panel-head strong,
html[data-theme='light'] .bed-line > strong,
html[data-theme='light'] .bundle strong,
html[data-theme='light'] .reminder strong,
html[data-theme='light'] .handoff-bar strong,
html[data-theme='light'] .task-modal strong,
html[data-theme='light'] .head-event strong,
html[data-theme='light'] .handoff-item > strong,
html[data-theme='light'] .heatmap article,
html[data-theme='light'] .summary-card strong {
  color: var(--text-primary);
}
html[data-theme='light'] .bed-cloud span b {
  color: var(--text-primary);
}
html[data-theme='light'] .bed-cloud span em {
  color: var(--text-secondary);
}
html[data-theme='light'] .nurse-top span,
html[data-theme='light'] .start-guide span,
html[data-theme='light'] .panel-head span,
html[data-theme='light'] .empty,
html[data-theme='light'] .bundle span,
html[data-theme='light'] .task-modal p,
html[data-theme='light'] .handoff-bar span,
html[data-theme='light'] .head-event span,
html[data-theme='light'] .quality-row span,
html[data-theme='light'] .handoff-item label span,
html[data-theme='light'] .summary-card span,
html[data-theme='light'] .summary-card em {
  color: var(--text-secondary);
}
html[data-theme='light'] .bed-line > strong,
html[data-theme='light'] .task-strip,
html[data-theme='light'] .bundle,
html[data-theme='light'] .reminder,
html[data-theme='light'] .empty,
html[data-theme='light'] .bed-cloud span,
html[data-theme='light'] .heatmap article,
html[data-theme='light'] .head-event,
html[data-theme='light'] .quality-row span,
html[data-theme='light'] .handoff-item {
  background: var(--bg-surface);
  border-color: rgba(145, 176, 199, 0.26);
}
html[data-theme='light'] .task-legend span {
  background: var(--bg-surface);
}
html[data-theme='light'] .bed-cloud span {
  background: transparent;
  box-shadow: none;
}
html[data-theme='light'] .bed-cloud span:hover {
  background: var(--bg-surface-2);
}
html[data-theme='light'] .bed-card,
html[data-theme='light'] .notice-card {
  background: var(--bg-surface);
  border-color: rgba(145, 176, 199, 0.3);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .bed-card {
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}
html[data-theme='light'] .bed-card:hover {
  background: var(--bg-surface-2);
}
html[data-theme='light'] .bed-card__main strong,
html[data-theme='light'] .bed-card__main span,
html[data-theme='light'] .notice-card strong {
  color: var(--text-primary);
}
html[data-theme='light'] .bed-card__meta span,
html[data-theme='light'] .bed-clear,
html[data-theme='light'] .notice-card span {
  color: var(--text-secondary);
}
html[data-theme='light'] .bed-risk-button {
  background: var(--warning-bg);
  border-color: rgba(245, 158, 11, 0.34);
  color: var(--warning);
}
html[data-theme='light'] .notice-card.is-overdue {
  background: var(--danger-bg);
  border-color: rgba(220, 38, 38, 0.26);
}
html[data-theme='light'] .task-strip {
  background: repeating-var(--bg-surface) 0, rgba(37, 99, 235, 0.08) 1px, #f8fafc 1px, #f8fafc 10.416%);
}
html[data-theme='light'] button {
  background: var(--bg-surface);
  border-color: rgba(37, 99, 235, 0.18);
  color: var(--brand);
}
html[data-theme='light'] button:hover {
  background: var(--bg-surface);
  border-color: rgba(37, 99, 235, 0.3);
}
html[data-theme='light'] .handoff-switch button.active {
  background: var(--bg-surface);
  border-color: rgba(22, 163, 74, 0.28);
  color: var(--success);
}
html[data-theme='light'] .handoff-item textarea {
  background: var(--bg-surface);
  border-color: rgba(145, 176, 199, 0.36);
  color: var(--text-primary);
}
html[data-theme='light'] .workload i {
  background: var(--border-color);
}
html[data-theme='light'] .onboarding-card {
  background: var(--bg-surface);
  border-color: rgba(145, 176, 199, 0.32);
}
html[data-theme='light'] .onboarding-card li {
  color: var(--text-primary);
}
html[data-theme='light'] .onboarding-card li span {
  color: var(--text-secondary);
}
html[data-theme='light'] .danger,
html[data-theme='light'] .is-overdue {
  color: var(--danger);
}
/* ── 告警/流程任务卡片 ── */
.panel--alert { border-color: rgba(251,90,122,.22); }
.panel--task { border-color: rgba(245,158,11,.18); }
.badge-red { display:inline-flex;align-items:center;min-width:24px;height:22px;padding:0 7px;border-radius:99px;background:rgba(251,90,122,.18);color:#fb5a7a;font-size:11px;font-weight:700;justify-content:center; }
.badge-amber { display:inline-flex;align-items:center;min-width:24px;height:22px;padding:0 7px;border-radius:99px;background:rgba(232,144,28,.18);color:#E8901C;font-size:11px;font-weight:700;justify-content:center; }
.alert-item { display:grid;gap:4px;padding:8px 10px;border-radius:6px;border:1px solid rgba(125,211,252,.08);background:rgba(8,23,38,.6);margin-bottom:6px; }
.alert-item.is-escalated { border-color:rgba(249,115,22,.18);background:rgba(40,20,8,.6); }
.alert-item--p0 { border-left:3px solid #fb5a7a; }
.alert-item-main { display:flex;align-items:center;gap:8px;min-width:0; }
.alert-item-main strong { color:var(--text-primary);font-size:12px;white-space:nowrap; }
.alert-item-name { color:var(--text-secondary);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.alert-item-meta { display:flex;align-items:center;gap:6px;padding-left:18px; }
.alert-item-meta small { color:#7da7c4;font-size:10px; }
.dot { width:8px;height:8px;border-radius:50%;flex-shrink:0; }
.dot-p0 { background:#fb5a7a;box-shadow:0 0 6px rgba(251,90,122,.6); }
.dot-p1 { background:#f97316;box-shadow:0 0 4px rgba(249,115,22,.5); }
.dot-p2 { background:#E8901C; }
.pill { display:inline-flex;align-items:center;min-height:18px;padding:0 6px;border-radius:99px;font-size:9px;font-weight:600; }
.pill--domain { background:rgba(56,189,248,.12);color:#38bdf8; }
.pill--priority { background:rgba(125,211,252,.1);color:#7dd3fc; }
.pill--escalated { background:rgba(249,115,22,.15);color:#f97316; }
.pill--episode { background:rgba(232,144,28,.12);color:#E8901C; }
</style>
