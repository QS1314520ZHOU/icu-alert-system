<template>
  <section class="role-home doctor-home">
    <header class="home-top">
      <div>
        <span>主管医生首页</span>
        <strong>{{ accountName }}</strong>
      </div>
      <div class="top-meta">
        <span>{{ home?.account?.dept || '科室待识别' }}</span>
        <span>{{ shiftText }}</span>
        <span>{{ clock }}</span>
        <button type="button" @click="load">刷新</button>
      </div>
    </header>

    <div v-if="loading" class="empty">正在汇总我管的床、昨夜 AI 监控和待办...</div>
    <div v-else-if="error" class="empty danger">{{ error }}</div>
    <template v-else>
      <section class="start-guide">
        <div>
          <span>今天从这里开始</span>
          <strong>先看重点患者，再处理待办，最后进入患者详情完成查房和文书。</strong>
        </div>
        <button type="button" @click="showOnboarding = true">查看3步引导</button>
      </section>

      <section class="doctor-summary">
        <article v-for="item in doctorSummary" :key="item.key" :class="['summary-card', `is-${item.tone}`]">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.hint }}</em>
        </article>
      </section>

      <main class="doctor-grid">
        <section class="panel focus-panel">
          <div class="panel-head">
            <strong>我的今日重点</strong>
            <span>按床位数字和综合风险排序</span>
          </div>
          <article v-for="item in sortedFocusPatients" :key="item.patient_id" class="focus-row" @click="goPatient(item.patient_id)">
            <i :class="`tone-${tone(item.risk_level)}`"></i>
            <div>
              <strong>{{ displayBed(item.bed) }} {{ item.name || '未知患者' }}</strong>
              <span>{{ cleanReason(item.reason) }}</span>
              <small>
                <em>{{ riskLabel(item.risk_level) }}</em>
                <em>评分 {{ item.risk_score || 0 }}</em>
              </small>
              <div class="focus-actions">
                <button type="button" @click.stop="goPatient(item.patient_id)">查看详情</button>
                <button type="button" @click.stop="goPatientTab(item.patient_id, 'alerts')">处理告警</button>
                <button type="button" @click.stop="goPatientTab(item.patient_id, 'ai')">查房摘要</button>
                <button type="button" @click.stop="goPatientTab(item.patient_id, 'documents')">病历文书</button>
              </div>
            </div>
          </article>
          <div v-if="!sortedFocusPatients.length" class="empty small">{{ doctorEmptyText }}</div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <strong>AI 昨夜替我做了什么</strong>
            <span>过去 12 小时</span>
          </div>
          <div class="kpi-grid">
            <div v-for="item in aiStats" :key="item.label" class="kpi">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
          <button class="full-btn" type="button" @click="$router.push({ path: '/clinical-workflow', query: route.query })">查看夜班完整工作日志</button>
        </section>

        <section class="panel">
          <div class="panel-head">
            <strong>我的待办</strong>
            <span>未签 / 未关闭 / 未确认</span>
          </div>
          <div class="task-list">
            <article v-for="item in pendingTasks" :key="item.task_id || item.title" class="task-row">
              <strong>{{ item.title || item.detail || '临床任务' }}</strong>
              <span>{{ displayBed(item.bed_label || item.bed) }} · {{ item.module_label || item.module || '临床' }}</span>
              <button type="button" @click="goTask(item)">去处理</button>
            </article>
            <div v-if="!pendingTasks.length" class="empty small">暂无待办，仍建议复核高风险患者详情。</div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <strong>科室质控速览</strong>
            <span>近 7 日质量信号</span>
          </div>
          <div class="lights">
            <button v-for="item in qualityLights" :key="item.key" type="button" :class="`light is-${item.tone}`" @click="$router.push('/analytics')">
              <span>{{ item.label }}</span>
              <b>{{ item.value }}</b>
            </button>
          </div>
        </section>
      </main>

      <div v-if="showOnboarding" class="onboarding-mask" @click.self="dismissOnboarding">
        <div class="onboarding-card">
          <div class="panel-head">
            <strong>医生首页3步用法</strong>
            <button type="button" @click="dismissOnboarding">知道了</button>
          </div>
          <ol>
            <li><b>先看重点患者</b><span>红色/黄色风险优先进入详情复核证据。</span></li>
            <li><b>处理待办和高危预警</b><span>从卡片按钮直接进入告警、AI摘要或病历文书。</span></li>
            <li><b>进入患者详情闭环</b><span>在详情页完成趋势查看、查房摘要和文书生成。</span></li>
          </ol>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDoctorHome } from '../api'
import { useAuthStore } from '../stores/auth'
import { formatRiskLevelLabel } from '../utils/displayLabels'
import { roleHomeConfig } from '../config/roleHomeConfig'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const home = ref<any>(null)
const clock = ref('')
const showOnboarding = ref(false)
let timer: any

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
const accountName = computed(() => home.value?.account?.display_name || home.value?.account?.userName || userId.value || '未识别医生')
const focusPatients = computed(() => home.value?.focus_patients || [])
const sortedFocusPatients = computed(() => sortBeds(focusPatients.value, (row: any) => row?.bed))
const pendingTasks = computed(() => (home.value?.pending_tasks || []).slice(0, 8))
const doctorEmptyText = computed(() => cleanEmptyText(home.value?.data_state?.empty_reason, '当前暂无需要置顶的分管患者，请确认患者主管医生信息已维护。'))
const shiftText = computed(() => {
  const s = home.value?.shift
  if (!s) return '班次待配置'
  return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
})
const aiStats = computed(() => {
  const a = home.value?.ai_night_watch || {}
  return [
    { label: '告警总数', value: a.total_alerts ?? 0 },
    { label: '自动抑制', value: a.auto_suppressed ?? 0 },
    { label: '已推送', value: a.pushed ?? 0 },
    { label: '已处理', value: a.handled ?? 0 },
    { label: '待跟进', value: a.pending_followup ?? 0 },
    { label: '综合判断', value: a.integrated_reasoning ?? 0 },
    { label: '判断采纳', value: a.integrated_adopted ?? 0 },
    { label: '主动提醒点击', value: `${a.pulse_clicks ?? 0}/${a.pulse_pushes ?? 0}` },
  ]
})
const doctorSummary = computed(() => {
  const a = home.value?.ai_night_watch || {}
  const managed = Number(home.value?.managed_beds ?? home.value?.data_state?.managed_beds ?? 0)
  const highRisk = focusPatients.value.filter((item: any) => ['critical', 'high', 'warning'].includes(String(item?.risk_level || '').toLowerCase())).length
  const pending = Number(a.pending_followup ?? 0)
  return [
    { key: 'beds', label: '分管床位', value: managed, hint: '当前账号匹配', tone: managed ? 'blue' : 'muted' },
    { key: 'risk', label: '重点风险', value: highRisk, hint: '需优先复核', tone: highRisk ? 'red' : 'green' },
    { key: 'pending', label: '待跟进告警', value: pending, hint: '过去 12 小时', tone: pending ? 'yellow' : 'green' },
    { key: 'tasks', label: '临床待办', value: pendingTasks.value.length, hint: '未签未确认', tone: pendingTasks.value.length ? 'yellow' : 'green' },
  ]
})
const qualityLights = computed(() => {
  const q = home.value?.quality_summary || {}
  const rows = q?.scanner_health?.rows || q?.rows || []
  const labels = ['VAP', 'CRBSI', 'CAUTI', '拔管失败', '镇静过度', '谵妄发生率']
  return labels.map((label) => {
    const row = rows.find((r: any) => String(r?.name || r?.scanner_name || '').toLowerCase().includes(label.toLowerCase()))
    const value = row?.rate ?? row?.count ?? row?.value ?? '--'
    const num = Number(value)
    return { key: label, label, value, tone: Number.isFinite(num) && num > 0 ? 'yellow' : 'green' }
  })
})

function tone(value: string) {
  const key = String(value || '').toLowerCase()
  if (['critical', 'high'].includes(key)) return 'critical'
  if (key === 'warning') return 'warning'
  if (key === 'info') return 'info'
  return 'unknown'
}
function riskLabel(value: any) {
  return formatRiskLevelLabel(value, '待评估')
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
    const scoreDiff = Number(b?.risk_score || 0) - Number(a?.risk_score || 0)
    if (scoreDiff) return scoreDiff
    const left = bedSortParts(getBed(a))
    const right = bedSortParts(getBed(b))
    if (left.hasNumber !== right.hasNumber) return left.hasNumber - right.hasNumber
    if (left.number !== right.number) return left.number - right.number
    const suffixCompare = left.suffix.localeCompare(right.suffix, 'zh-CN', { numeric: true, sensitivity: 'base' })
    if (suffixCompare) return suffixCompare
    return left.raw.localeCompare(right.raw, 'zh-CN', { numeric: true, sensitivity: 'base' })
  })
}
function goPatient(id: string) {
  if (id) router.push({ path: `/patient/${id}`, query: route.query })
}
function goPatientTab(id: string, tab: string) {
  if (id) router.push({ path: `/patient/${id}`, query: { ...route.query, tab } })
}
function goTask(item: any) {
  const patientId = String(item?.patient_id || item?.patientId || item?.pid || '').trim()
  const module = String(item?.module || item?.module_label || '').toLowerCase()
  const tab = module.includes('文书') || module.includes('document') ? 'documents'
    : module.includes('告警') || module.includes('alert') ? 'alerts'
      : 'ai'
  if (patientId) goPatientTab(patientId, tab)
  else router.push({ path: '/clinical-workflow', query: route.query })
}
function cleanReason(value: any) {
  if (value && typeof value === 'object') {
    const summary = String(value.summary || value.text || value.title || '').trim()
    const suggestion = String(value.suggestion || value.recommendation || '').trim()
    return [summary, suggestion ? `建议：${suggestion}` : ''].filter(Boolean).join('。') || '进入患者详情复核。'
  }
  const text = String(value || '').trim()
  if (!text) return '暂无一句话理由'
  if (text.includes("'summary'") || text.includes('"summary"')) return '综合风险推理已生成结论，点击进入患者详情查看证据和建议。'
  return text
}
function cleanEmptyText(value: any, fallback: string) {
  const text = String(value || '').trim()
  if (!text) return fallback
  if (/patient\s*表|account\s*表|bedDoctorId|user[_-]?id|userId|collection|集合|数据库/i.test(text)) return fallback
  return text
}
async function load() {
  if (!userId.value) {
    error.value = '未识别当前账号。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const params: { user_id: string; dept?: string; dept_code?: string } = { user_id: userId.value }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDept.value) params.dept = routeDept.value
    const { data } = await getDoctorHome(params)
    home.value = data?.data || {}
    auth.updateAccount(home.value?.account)
  } catch (err: any) {
    error.value = err?.message || '医生首页加载失败'
  } finally {
    loading.value = false
  }
}
function tick() {
  clock.value = new Date().toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
onMounted(() => {
  auth.hydrateFromQuery(route.query)
  cleanDuplicateIdentityQuery()
  tick()
  timer = setInterval(tick, 1000)
  void load()
  if (typeof window !== 'undefined' && !window.localStorage.getItem(roleHomeConfig.doctor.onboardingKey)) {
    showOnboarding.value = true
  }
})
onUnmounted(() => clearInterval(timer))

watch(() => [route.query.user_id, route.query.userId, route.query.userName, route.query.useName, route.query.username, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  auth.hydrateFromQuery(route.query)
  void load()
})

function cleanDuplicateIdentityQuery() {
  const query = auth.cleanIdentityQuery(route.query)
  if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ path: route.path, query })
}
function dismissOnboarding() {
  showOnboarding.value = false
  if (typeof window !== 'undefined') window.localStorage.setItem(roleHomeConfig.doctor.onboardingKey, '1')
}
</script>

<style scoped>
.role-home { padding: 14px; display: grid; gap: 12px; }
.start-guide { min-height: 66px; display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid rgba(34,211,238,.22); border-radius: 8px; background: linear-gradient(135deg, rgba(8,82,112,.62), rgba(6,18,31,.74)); }
.start-guide div { display: grid; gap: 4px; }
.start-guide span { color: #8fd3e8; font-size: 12px; }
.start-guide strong { color: #f8fbff; font-size: 15px; }
.home-top { min-height: 72px; display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 14px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(7,20,34,.82); }
.home-top div { display: grid; gap: 4px; }
.home-top span, .panel-head span, .focus-row span, .task-row span, .empty, .summary-card span, .summary-card em { color: #8eaabd; font-size: 12px; }
.home-top strong { color: #f8fbff; font-size: 20px; }
.top-meta { display: flex !important; flex-direction: row; align-items: center; flex-wrap: wrap; }
button { min-height: 44px; border-radius: 8px; border: 1px solid rgba(125,211,252,.2); background: rgba(13,44,66,.78); color: #eafcff; padding: 0 12px; cursor: pointer; }
.doctor-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.summary-card { min-height: 86px; display: grid; align-content: center; gap: 4px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); }
.summary-card strong { color: #f8fbff; font-size: 26px; line-height: 1; }
.summary-card.is-red { border-color: rgba(239,68,68,.42); }
.summary-card.is-yellow { border-color: rgba(245,158,11,.42); }
.summary-card.is-green { border-color: rgba(52,211,153,.34); }
.summary-card.is-blue { border-color: rgba(56,189,248,.34); }
.doctor-grid { min-height: 560px; display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, .95fr); grid-template-rows: auto auto; gap: 12px; }
.panel { min-width: 0; overflow: auto; display: grid; align-content: start; gap: 10px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); }
.panel-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
.panel-head strong { color: #f4fbff; font-size: 15px; }
.focus-row, .task-row { display: grid; grid-template-columns: 4px minmax(0,1fr); gap: 10px; align-items: center; padding: 10px; border-radius: 8px; background: rgba(11,33,50,.72); cursor: pointer; }
.focus-row i { width: 4px; height: 100%; min-height: 42px; border-radius: 999px; background: #94a3b8; }
.focus-row strong, .task-row strong { color: #eef8ff; font-size: 13px; }
.focus-row small { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.focus-row small em { padding: 2px 7px; border-radius: 999px; background: rgba(125,211,252,.1); color: #bfefff; font-size: 11px; font-style: normal; }
.focus-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.focus-actions button, .task-row button { min-height: 32px; padding: 0 10px; }
.tone-critical { background: #ef4444 !important; }
.tone-warning { background: #f59e0b !important; }
.tone-info { background: #38bdf8 !important; }
.kpi-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 8px; }
.kpi { padding: 10px; border-radius: 8px; background: rgba(11,33,50,.72); }
.kpi span { color: #91adbd; font-size: 12px; }
.kpi strong { display: block; color: #f8fbff; font-size: 24px; margin-top: 4px; }
.full-btn { width: 100%; }
.task-list { display: grid; gap: 8px; }
.task-row { grid-template-columns: minmax(0,1fr) auto; cursor: default; }
.task-row span { grid-column: 1; }
.task-row button { grid-row: 1 / span 2; grid-column: 2; }
.lights { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
.light { display: grid; justify-items: start; align-content: center; gap: 4px; background: rgba(11,33,50,.72); }
.light b { font-size: 18px; }
.is-green { border-color: rgba(52,211,153,.35); }
.is-yellow { border-color: rgba(245,158,11,.42); }
.empty { padding: 14px; border-radius: 8px; background: rgba(11,33,50,.58); }
.empty.small { padding: 10px; }
.empty.danger { color: #fecaca; }
.onboarding-mask { position: fixed; inset: 0; z-index: 400; display: grid; place-items: center; background: rgba(0,0,0,.48); padding: 16px; }
.onboarding-card { width: min(560px, 100%); display: grid; gap: 12px; padding: 16px; border: 1px solid rgba(125,211,252,.24); border-radius: 8px; background: #081827; box-shadow: 0 20px 50px rgba(0,0,0,.32); }
.onboarding-card ol { margin: 0; padding-left: 20px; display: grid; gap: 10px; }
.onboarding-card li { color: #eafcff; }
.onboarding-card li b { display: block; }
.onboarding-card li span { display: block; color: #91adbd; font-size: 12px; margin-top: 4px; }
@media (max-width: 1024px) { .doctor-summary, .doctor-grid { grid-template-columns: 1fr; grid-template-rows: none; } .kpi-grid, .lights { grid-template-columns: repeat(2,minmax(0,1fr)); } }

html[data-theme='light'] .role-home {
  background:
    radial-gradient(circle at 12% 0%, rgba(37, 99, 235, 0.08), transparent 28%),
    radial-gradient(circle at 90% 10%, rgba(14, 165, 233, 0.06), transparent 32%);
}
html[data-theme='light'] .home-top,
html[data-theme='light'] .start-guide,
html[data-theme='light'] .panel,
html[data-theme='light'] .summary-card {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.07), 0 1px 3px rgba(15, 23, 42, 0.04);
}
html[data-theme='light'] .home-top strong,
html[data-theme='light'] .start-guide strong,
html[data-theme='light'] .panel-head strong,
html[data-theme='light'] .focus-row strong,
html[data-theme='light'] .task-row strong,
html[data-theme='light'] .kpi strong,
html[data-theme='light'] .light b,
html[data-theme='light'] .summary-card strong {
  color: #0f172a;
}
html[data-theme='light'] .home-top span,
html[data-theme='light'] .start-guide span,
html[data-theme='light'] .panel-head span,
html[data-theme='light'] .focus-row span,
html[data-theme='light'] .task-row span,
html[data-theme='light'] .kpi span,
html[data-theme='light'] .empty,
html[data-theme='light'] .summary-card span,
html[data-theme='light'] .summary-card em {
  color: #64748b;
}
html[data-theme='light'] .focus-row small em {
  background: #eff6ff;
  color: #2563eb;
}
html[data-theme='light'] .focus-row,
html[data-theme='light'] .task-row,
html[data-theme='light'] .kpi,
html[data-theme='light'] .light,
html[data-theme='light'] .empty {
  background: #f8fafc;
  border: 1px solid rgba(145, 176, 199, 0.26);
}
html[data-theme='light'] .onboarding-card {
  background: #ffffff;
  border-color: rgba(145, 176, 199, 0.32);
}
html[data-theme='light'] .onboarding-card li {
  color: #0f172a;
}
html[data-theme='light'] .onboarding-card li span {
  color: #64748b;
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
html[data-theme='light'] .empty.danger {
  color: #b91c1c;
  background: #fef2f2;
  border-color: rgba(239, 68, 68, 0.18);
}
</style>
