<template>
  <section class="nurse-home">
    <header class="nurse-top">
      <div>
        <strong>{{ accountName }}</strong>
        <span>{{ shiftText }} · 我的床位：{{ bedText }}</span>
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
      <section class="nurse-summary">
        <article v-for="item in nurseSummary" :key="item.key" :class="['summary-card', `is-${item.tone}`]">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.hint }}</em>
        </article>
      </section>
      <div v-if="home?.head_degraded || home?.bundle_degraded" class="empty small">
        {{ home?.head_degraded || home?.bundle_degraded }}
      </div>

      <main v-if="isHeadMode" class="head-layout">
        <section class="panel">
          <div class="panel-head"><strong>全科床位</strong><span>{{ sortedHeadBeds.length }} 床</span></div>
          <div class="bed-cloud">
            <span v-for="b in sortedHeadBeds" :key="b.patient_id">
              <b>{{ displayBed(b.bed) }}</b>
              <em>{{ b.name || '未知患者' }}</em>
            </span>
          </div>
        </section>
        <section class="panel">
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
            <article v-for="event in sortedHeadEvents" :key="`${event.patient_id}-${event.time}-${event.title}`" class="head-event">
              <strong>{{ displayBed(event.bed) }} {{ event.title }}</strong>
              <span>{{ event.type }} · {{ fmt(event.time) }}</span>
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
            <article v-for="bed in sortedBeds" :key="bed.patient_id" class="bed-card">
              <div class="bed-card__main">
                <strong>{{ displayBed(bed.bed) }}</strong>
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
                @click="selectTask(tasksByBed(bed.patient_id)[0])"
              >
                {{ tasksByBed(bed.patient_id).length }} 条风险提醒
              </button>
              <span v-else class="bed-clear">暂无风险提醒</span>
            </article>
            <div v-if="!beds.length" class="empty small">{{ nurseEmptyText }}</div>
          </div>
        </section>

        <aside class="side">
          <section class="panel">
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
          <section class="panel">
            <div class="panel-head"><strong>安全清单</strong><span>闭环状态</span></div>
            <article v-for="item in bundles" :key="item.code" :class="`bundle is-${item.tone}`">
              <strong>{{ displayName(item.name || item.code) }}</strong>
              <span>{{ item.data_state === 'missing' ? '暂无同步' : `${item.completed}/${item.total}` }}</span>
            </article>
            <div v-if="home?.bundle_degraded && !bundles.length" class="empty small">{{ home.bundle_degraded }}</div>
            <div v-else-if="!bundles.length" class="empty small">本班安全清单暂无同步记录。</div>
          </section>
          <section class="panel">
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
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getNurseHome, postNurseHandoffGenerate, postNurseReminderFeedback, postNurseTaskExecute } from '../api'
import { useAuthStore } from '../stores/auth'
import { formatAlertTypeLabel } from '../utils/displayLabels'

const NURSE_HOME_CACHE_TTL_MS = 2 * 60 * 1000
const nurseHomeCache = new Map<string, { ts: number; data: any }>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const home = ref<any>(null)
const selectedTask = ref<any>(null)
const handoffLoading = ref(false)
const handoffError = ref('')
const handoffMode = ref<'isbar' | 'ipass'>('isbar')

const userId = computed(() => String(auth.effectiveUserId || '').trim())
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
})

watch(() => [route.query.user_id, route.query.userId, route.query.userName, route.query.username, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department, route.query.view], () => {
  auth.hydrateFromQuery(route.query)
  void load()
})

function cleanDuplicateIdentityQuery() {
  const query = auth.cleanIdentityQuery(route.query)
  if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ path: route.path, query })
}
</script>

<style scoped>
.nurse-home { padding: 12px; display: grid; gap: 12px; }
.nurse-top { min-height: 80px; display: grid; grid-template-columns: minmax(0,1fr) 320px auto; align-items: center; gap: 12px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(7,20,34,.82); }
.nurse-top strong { color: #f8fbff; font-size: 20px; }
.nurse-top span, .panel-head span, .empty, .bundle span, .task-modal p, .summary-card span, .summary-card em { color: #91adbd; font-size: 12px; }
.workload { display: grid; gap: 6px; }
.workload i { height: 8px; border-radius: 999px; background: rgba(148,163,184,.25); overflow: hidden; }
.workload b { display: block; height: 100%; background: #38bdf8; }
button { min-height: 44px; border: 1px solid rgba(125,211,252,.22); border-radius: 8px; background: rgba(13,44,66,.78); color: #eafcff; padding: 0 10px; cursor: pointer; }
.nurse-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.summary-card { min-height: 82px; display: grid; align-content: center; gap: 4px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); }
.summary-card strong { color: #f8fbff; font-size: 25px; line-height: 1; }
.summary-card em { font-style: normal; }
.summary-card.is-red { border-color: rgba(239,68,68,.48); }
.summary-card.is-yellow { border-color: rgba(245,158,11,.42); }
.summary-card.is-green { border-color: rgba(52,211,153,.34); }
.summary-card.is-blue { border-color: rgba(56,189,248,.34); }
.nurse-grid { min-height: 560px; display: grid; grid-template-columns: minmax(0, 3fr) minmax(340px, 2fr); gap: 12px; }
.side, .head-layout { display: grid; gap: 12px; }
.head-layout { grid-template-columns: 1fr 1fr; }
.panel { min-width: 0; display: grid; align-content: start; gap: 10px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); }
.panel-head { display: flex; justify-content: space-between; gap: 10px; }
.panel-head strong { color: #f4fbff; }
.task-legend { display: flex; flex-wrap: wrap; gap: 8px; }
.task-legend span { padding: 5px 9px; border-radius: 999px; background: rgba(11,33,50,.72); color: #91adbd; font-size: 12px; }
.task-legend .is-overdue { color: #fecaca; border: 1px solid rgba(239,68,68,.4); }
.task-legend .is-due { color: #fde68a; border: 1px solid rgba(245,158,11,.4); }
.task-legend .is-soon { color: #bae6fd; border: 1px solid rgba(56,189,248,.36); }
.task-legend .is-done { color: #bbf7d0; border: 1px solid rgba(52,211,153,.36); }
.timeline { overflow: auto; display: grid; gap: 8px; }
.time-head { min-width: 760px; display: grid; grid-template-columns: 84px repeat(7, 1fr); color: #8caabd; font-size: 12px; }
.bed-line { min-width: 760px; display: grid; grid-template-columns: 84px minmax(0,1fr); align-items: stretch; gap: 8px; }
.bed-line > strong { display: grid; place-items: center; color: #f8fbff; border-radius: 8px; background: rgba(11,33,50,.72); }
.task-strip { min-height: 58px; position: relative; display: flex; align-items: center; gap: 8px; padding: 7px; border-radius: 8px; background: repeating-linear-gradient(90deg, rgba(125,211,252,.08) 0, rgba(125,211,252,.08) 1px, rgba(11,33,50,.48) 1px, rgba(11,33,50,.48) 10.416%); overflow-x: auto; }
.task-card { flex: 0 0 132px; font-size: 12px; }
.is-future { opacity: .7; }
.is-soon { border-color: rgba(56,189,248,.55); }
.is-due { border-color: rgba(245,158,11,.65); }
.is-overdue { border-color: rgba(239,68,68,.7); color: #fecaca; }
.is-done { border-color: rgba(52,211,153,.55); color: #bbf7d0; }
.bundle, .reminder { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px; border-radius: 8px; background: rgba(11,33,50,.72); }
.bundle strong, .reminder strong { color: #edf8ff; font-size: 13px; }
.bundle.is-green { border-left: 3px solid #34d399; }
.bundle.is-yellow { border-left: 3px solid #f59e0b; }
.bundle.is-red { border-left: 3px solid #ef4444; }
.reminder { display: grid; }
.reminder div { display: flex; gap: 8px; flex-wrap: wrap; }
.reminder button { min-height: 36px; }
.handoff-bar { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); opacity: .82; }
.handoff-bar.open { border-color: rgba(245,158,11,.42); opacity: 1; }
.handoff-bar strong { color: #f8fbff; display: block; }
.handoff-bar span { color: #91adbd; font-size: 12px; }
.empty { padding: 14px; border-radius: 8px; background: rgba(11,33,50,.58); }
.empty.small { padding: 10px; }
.danger { color: #fecaca; }
.modal-mask { position: fixed; inset: 0; z-index: 200; display: grid; place-items: center; background: rgba(0,0,0,.52); }
.task-modal { width: min(520px, calc(100vw - 24px)); display: grid; gap: 12px; padding: 16px; border-radius: 8px; border: 1px solid rgba(125,211,252,.22); background: #081827; }
.task-modal strong { color: #fff; font-size: 18px; }
.modal-actions { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; }
.bed-cloud { display: grid; grid-template-columns: repeat(auto-fill, minmax(116px, 1fr)); gap: 8px; }
.heatmap { display: flex; flex-wrap: wrap; gap: 8px; }
.bed-cloud span {
  min-width: 0;
  min-height: 54px;
  display: grid;
  align-content: center;
  gap: 3px;
  padding: 8px 10px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(13,44,66,.82), rgba(8,28,44,.72));
  color: #eafcff;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
}
.bed-cloud span b {
  color: #f8fbff;
  font-size: 15px;
  line-height: 1.1;
  font-weight: 800;
}
.bed-cloud span em {
  min-width: 0;
  color: #91adbd;
  font-size: 12px;
  line-height: 1.2;
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.heatmap article { padding: 8px 10px; border-radius: 8px; background: rgba(11,33,50,.72); color: #eafcff; }
.heatmap article { min-width: 150px; display: grid; gap: 8px; }
.heatmap i { height: 42px; display: flex; align-items: end; gap: 3px; }
.heatmap b { width: 10px; min-height: 8px; border-radius: 3px 3px 0 0; background: #38bdf8; }
.density-high { border: 1px solid rgba(239,68,68,.6); }
.density-medium { border: 1px solid rgba(245,158,11,.55); }
.density-low { border: 1px solid rgba(52,211,153,.45); }
.head-side { grid-column: 1 / -1; }
.head-event-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.head-event { display: grid; gap: 4px; padding: 10px; border-radius: 8px; background: rgba(11,33,50,.72); }
.head-event strong { color: #fff; font-size: 13px; }
.head-event span, .quality-row span { color: #91adbd; font-size: 12px; }
.quality-row { display: flex; flex-wrap: wrap; gap: 8px; }
.quality-row span { padding: 8px 10px; border-radius: 8px; background: rgba(11,33,50,.72); }
.handoff-editor { margin-top: -4px; }
.handoff-switch { display: flex; gap: 6px; }
.handoff-switch button { min-height: 34px; padding: 0 10px; }
.handoff-switch button.active { border-color: rgba(52,211,153,.55); color: #bbf7d0; background: rgba(13,74,55,.72); }
.handoff-item { display: grid; gap: 8px; padding: 10px; border-radius: 8px; background: rgba(11,33,50,.58); }
.handoff-item > strong { color: #fff; }
.handoff-item label { display: grid; gap: 4px; }
.handoff-item label span { color: #91adbd; font-size: 12px; }
.handoff-item textarea { resize: vertical; min-height: 58px; border-radius: 8px; border: 1px solid rgba(125,211,252,.18); background: rgba(5,18,30,.9); color: #eafcff; padding: 8px; }
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
  min-height: 142px;
  display: grid;
  align-content: space-between;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(125, 211, 252, .16);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(10, 32, 50, .92), rgba(7, 22, 36, .86));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .04);
}
.bed-card__main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}
.bed-card__main strong {
  color: #f8fbff;
  font-size: 24px;
  line-height: 1;
}
.bed-card__main span {
  min-width: 0;
  color: #d7eefc;
  font-size: 15px;
  font-weight: 700;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bed-card__meta {
  display: grid;
  gap: 4px;
}
.bed-card__meta span,
.bed-clear {
  color: #91adbd;
  font-size: 12px;
}
.bed-risk-button {
  width: 100%;
  min-height: 38px;
  border-color: rgba(245, 158, 11, .48);
  background: rgba(80, 45, 13, .55);
  color: #fde68a;
}
.bed-clear {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  color: #bbf7d0;
}
.notice-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: 8px;
  background: rgba(11, 33, 50, .72);
  cursor: pointer;
}
.notice-card div {
  min-width: 0;
  display: grid;
  gap: 4px;
}
.notice-card strong {
  min-width: 0;
  color: #edf8ff;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notice-card span {
  color: #91adbd;
  font-size: 12px;
}
.notice-card button {
  min-height: 34px;
  flex: 0 0 auto;
}
.notice-card.is-overdue {
  border-color: rgba(239, 68, 68, .42);
  background: rgba(69, 20, 28, .46);
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
@media (max-width: 1024px) { .nurse-top, .nurse-summary, .nurse-grid, .head-layout { grid-template-columns: 1fr; } .side { grid-template-columns: 1fr 1fr; } }
@media (max-width: 760px) { .side, .handoff-bar, .head-event-grid { grid-template-columns: 1fr; flex-direction: column; align-items: stretch; } }

html[data-theme='light'] .nurse-home {
  background:
    radial-gradient(circle at 12% 0%, rgba(37, 99, 235, 0.08), transparent 28%),
    radial-gradient(circle at 88% 12%, rgba(16, 185, 129, 0.07), transparent 30%);
}
html[data-theme='light'] .nurse-top,
html[data-theme='light'] .panel,
html[data-theme='light'] .handoff-bar,
html[data-theme='light'] .task-modal,
html[data-theme='light'] .summary-card {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.07), 0 1px 3px rgba(15, 23, 42, 0.04);
}
html[data-theme='light'] .nurse-top strong,
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
  color: #0f172a;
}
html[data-theme='light'] .bed-cloud span b {
  color: #0f172a;
}
html[data-theme='light'] .bed-cloud span em {
  color: #64748b;
}
html[data-theme='light'] .nurse-top span,
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
  color: #64748b;
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
  background: #f8fafc;
  border-color: rgba(145, 176, 199, 0.26);
}
html[data-theme='light'] .task-legend span {
  background: #f8fafc;
}
html[data-theme='light'] .bed-cloud span {
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
html[data-theme='light'] .bed-card,
html[data-theme='light'] .notice-card {
  background: #ffffff;
  border-color: rgba(145, 176, 199, 0.3);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
html[data-theme='light'] .bed-card__main strong,
html[data-theme='light'] .bed-card__main span,
html[data-theme='light'] .notice-card strong {
  color: #0f172a;
}
html[data-theme='light'] .bed-card__meta span,
html[data-theme='light'] .bed-clear,
html[data-theme='light'] .notice-card span {
  color: #64748b;
}
html[data-theme='light'] .bed-risk-button {
  background: #fffbeb;
  border-color: rgba(245, 158, 11, 0.34);
  color: #92400e;
}
html[data-theme='light'] .notice-card.is-overdue {
  background: #fef2f2;
  border-color: rgba(220, 38, 38, 0.26);
}
html[data-theme='light'] .task-strip {
  background: repeating-linear-gradient(90deg, rgba(37, 99, 235, 0.08) 0, rgba(37, 99, 235, 0.08) 1px, #f8fafc 1px, #f8fafc 10.416%);
}
html[data-theme='light'] button {
  background: #eff6ff;
  border-color: rgba(37, 99, 235, 0.18);
  color: #1d4ed8;
}
html[data-theme='light'] button:hover {
  background: #dbeafe;
  border-color: rgba(37, 99, 235, 0.3);
}
html[data-theme='light'] .handoff-switch button.active {
  background: #dcfce7;
  border-color: rgba(22, 163, 74, 0.28);
  color: #15803d;
}
html[data-theme='light'] .handoff-item textarea {
  background: #ffffff;
  border-color: rgba(145, 176, 199, 0.36);
  color: #0f172a;
}
html[data-theme='light'] .workload i {
  background: #e2e8f0;
}
html[data-theme='light'] .danger,
html[data-theme='light'] .is-overdue {
  color: #b91c1c;
}
</style>
