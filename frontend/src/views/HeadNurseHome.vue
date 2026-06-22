<template>
  <section class="head-nurse-home">
    <header class="home-top">
      <div>
        <span>护士长首页</span>
        <strong>{{ accountName }}</strong>
      </div>
      <div class="top-meta">
        <span>{{ home?.account?.dept || '科室待识别' }}</span>
        <span>{{ shiftText }}</span>
        <span>{{ clock }}</span>
        <button type="button" @click="load">刷新</button>
      </div>
    </header>

    <div v-if="loading" class="empty">正在汇总全科床位、护理负荷和质控数据...</div>
    <div v-else-if="error" class="empty danger">{{ error }}</div>
    <template v-else>
      <section class="start-guide">
        <div>
          <span>护士长看板</span>
          <strong>先看全科床位，再看护理负荷，最后追踪评估依从和质控事件。</strong>
        </div>
        <button type="button" @click="showOnboarding = true">查看3步引导</button>
      </section>

      <section class="summary-cards">
        <article v-for="item in summaryCards" :key="item.key" :class="['summary-card', `is-${item.tone}`]">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.hint }}</em>
        </article>
      </section>

      <!-- 依从性看板入口 -->
      <section class="compliance-entry">
        <div class="entry-content">
          <strong>护理依从性看板</strong>
          <span>查看评估/翻身/CAM-ICU/早期活动依从率时间线、逾期TOP床位和班次对比</span>
        </div>
        <button type="button" @click="showCompliance = !showCompliance">
          {{ showCompliance ? '收起看板' : '展开看板' }}
        </button>
      </section>

      <!-- 依从性看板 -->
      <ComplianceDashboard
        v-if="showCompliance"
        :user-id="userId"
        :dept-code="routeDeptCode"
        :dept="routeDept"
      />

      <!-- Bundle 合规核查 -->
      <section class="panel bundle-panel">
        <BundleComplianceChecklist :dept-code="routeDeptCode" :dept="routeDept" />
      </section>

      <main class="head-nurse-grid">
        <!-- 左侧 -->
        <section class="panel">
          <div class="panel-head">
            <strong>全科床位</strong>
            <span>{{ beds.length }} 床</span>
          </div>
          <div class="bed-cloud">
            <span v-for="b in sortedBeds" :key="b.patient_id">
              <b>{{ displayBed(b.bed) }}</b>
              <em>{{ b.name || '未知患者' }}</em>
            </span>
          </div>
          <div v-if="pendingHandover.length" class="pending-handover">
            <strong>待交接床位 ({{ pendingHandover.length }})</strong>
            <div class="handover-list">
              <span v-for="b in pendingHandover" :key="b.patient_id">
                {{ displayBed(b.bed) }} {{ b.name }}
              </span>
            </div>
          </div>
        </section>

        <!-- 右侧 -->
        <section class="panel">
          <div class="panel-head">
            <strong>护理负荷热力图</strong>
            <span>本班护理记录密度</span>
          </div>
          <div class="workload-summary">
            <span>已用 {{ workload.used_minutes || 0 }} / 预计 {{ workload.estimated_minutes || 0 }} 分钟</span>
            <i><b :style="{ width: `${workload.percent || 0}%` }"></b></i>
          </div>
          <div class="heatmap">
            <article v-for="row in heatmap" :key="row.nurse" :class="`density-${row.tone}`">
              <strong>{{ row.nurse }} · {{ row.task_density }}</strong>
              <i>
                <b v-for="bucket in row.buckets || []" :key="`${row.nurse}-${bucket.time}`"
                  :style="{ height: `${Math.min(100, Math.max(12, Number(bucket.count || 0) * 10))}%` }"
                  :title="`${bucket.time} ${bucket.count}条`"></b>
              </i>
            </article>
          </div>
          <div v-if="!heatmap.length" class="empty small">暂无护理记录数据。</div>
        </section>

        <!-- 评估依从 -->
        <section class="panel">
          <div class="panel-head">
            <strong>评估依从率</strong>
            <span>{{ assessmentCompliance.compliance_rate }}%</span>
          </div>
          <div class="compliance-summary">
            <span>总计 {{ assessmentCompliance.total_reminders }} 项</span>
            <span>逾期 {{ assessmentCompliance.active_overdue }} 项</span>
            <span>按时完成 {{ assessmentCompliance.resolved_ontime }} 项</span>
          </div>
          <div class="compliance-list">
            <article v-for="item in assessmentCompliance.by_type || []" :key="item.score_type" class="compliance-item">
              <strong>{{ item.title || item.score_type }}</strong>
              <div class="compliance-bar">
                <i :style="{ width: `${item.compliance_rate}%` }"></i>
              </div>
              <span>{{ item.compliance_rate }}% ({{ item.overdue }}/{{ item.total }} 逾期)</span>
            </article>
          </div>
          <div v-if="!(assessmentCompliance.by_type || []).length" class="empty small">暂无评估提醒数据。</div>
        </section>

        <!-- 告警处置 -->
        <section class="panel">
          <div class="panel-head">
            <strong>告警处置统计</strong>
            <span>近12小时</span>
          </div>
          <div class="alert-stats">
            <div class="stat-item">
              <span>告警总数</span>
              <strong>{{ alertStats.total_alerts || 0 }}</strong>
            </div>
            <div class="stat-item">
              <span>已处置</span>
              <strong>{{ alertStats.handled || 0 }}</strong>
            </div>
            <div class="stat-item">
              <span>待处理</span>
              <strong :class="{ 'text-warning': alertStats.pending > 0 }">{{ alertStats.pending || 0 }}</strong>
            </div>
            <div class="stat-item">
              <span>处置率</span>
              <strong>{{ alertStats.handle_rate || 0 }}%</strong>
            </div>
            <div class="stat-item">
              <span>平均响应</span>
              <strong>{{ alertStats.avg_response_minutes || 0 }}分钟</strong>
            </div>
          </div>
        </section>

        <!-- 质控事件 -->
        <section class="panel">
          <div class="panel-head">
            <strong>未闭环质控事件</strong>
            <span>{{ qualityEvents.length }} 条</span>
          </div>
          <div class="event-list">
            <article v-for="event in qualityEvents" :key="`${event.patient_id}-${event.time}-${event.title}`" class="event-item">
              <strong>{{ displayBed(event.bed) }} {{ event.title }}</strong>
              <span>{{ event.type }} · {{ fmt(event.time) }}</span>
            </article>
          </div>
          <div v-if="!qualityEvents.length" class="empty small">本班暂无未闭环质控事件。</div>
          <div class="quality-row">
            <span>跌倒 {{ qualitySummary.falls || 0 }}</span>
            <span>压疮 {{ qualitySummary.pressure_ulcers || 0 }}</span>
            <span>管路脱出 {{ qualitySummary.line_displacement || 0 }}</span>
            <span>给药差错 {{ qualitySummary.medication_errors || 0 }}</span>
          </div>
        </section>

        <!-- 规则噪音 -->
        <section class="panel">
          <div class="panel-head">
            <strong>规则健康度</strong>
            <span>近7天</span>
          </div>
          <div class="scanner-list">
            <article v-for="row in scannerRows" :key="row.scanner_name" class="scanner-item">
              <strong>{{ row.name || row.scanner_name }}</strong>
              <div class="scanner-stats">
                <span>触发 {{ row.fire_count || 0 }}</span>
                <span>确认率 {{ row.ack_rate || 0 }}%</span>
                <span :class="{ 'text-warning': (row.noise_score || 0) > 30 }">噪音 {{ row.noise_score || 0 }}%</span>
              </div>
            </article>
          </div>
          <div v-if="!scannerRows.length" class="empty small">暂无规则健康数据。</div>
        </section>
      </main>

      <div v-if="showOnboarding" class="onboarding-mask" @click.self="dismissOnboarding">
        <div class="onboarding-card">
          <div class="panel-head">
            <strong>护士长看板3步用法</strong>
            <button type="button" @click="dismissOnboarding">知道了</button>
          </div>
          <ol>
            <li><b>先看全科床位</b><span>确认在科患者和床位分布，关注待交接床位。</span></li>
            <li><b>查看护理负荷</b><span>发现护理记录密度和人力压力，及时调配资源。</span></li>
            <li><b>追踪评估依从和质控</b><span>重点处理逾期评估和未闭环质控事件。</span></li>
          </ol>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getHeadNurseHome } from '../api'
import { useAuthStore } from '../stores/auth'
import { roleHomeConfig } from '../config/roleHomeConfig'
import ComplianceDashboard from './ComplianceDashboard.vue'
import BundleComplianceChecklist from './BundleComplianceChecklist.vue'

const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const home = ref<any>(null)
const clock = ref('')
const showOnboarding = ref(false)
const showCompliance = ref(false)
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

const accountName = computed(() => home.value?.account?.display_name || home.value?.account?.userName || userId.value || '未识别护士长')
const beds = computed(() => home.value?.beds || [])
const pendingHandover = computed(() => home.value?.pending_handover || [])
const workload = computed(() => home.value?.workload || {})
const heatmap = computed(() => workload.value?.heatmap || [])
const assessmentCompliance = computed(() => home.value?.assessment_compliance || {})
const alertStats = computed(() => home.value?.alert_stats || {})
const qualityEvents = computed(() => home.value?.quality_events || [])
const qualitySummary = computed(() => home.value?.quality_summary || {})
const scannerHealth = computed(() => home.value?.scanner_health || {})
const scannerRows = computed(() => (scannerHealth.value?.rows || []).slice(0, 10))

const shiftText = computed(() => {
  const s = home.value?.shift
  if (!s) return '班次待配置'
  return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
})

const summaryCards = computed(() => {
  const compliance = assessmentCompliance.value
  const alerts = alertStats.value
  return [
    { key: 'beds', label: '全科床位', value: beds.value.length, hint: `${pendingHandover.value.length} 床待交接`, tone: 'blue' },
    { key: 'handover', label: '待交接', value: pendingHandover.value.length, hint: '需关注', tone: pendingHandover.value.length ? 'yellow' : 'green' },
    { key: 'compliance', label: '评估依从率', value: `${compliance.compliance_rate || 0}%`, hint: `${compliance.active_overdue || 0} 项逾期`, tone: (compliance.active_overdue || 0) > 0 ? 'red' : 'green' },
    { key: 'alerts', label: '告警处置率', value: `${alerts.handle_rate || 0}%`, hint: `${alerts.pending || 0} 项待处理`, tone: (alerts.pending || 0) > 0 ? 'yellow' : 'green' },
  ]
})

const sortedBeds = computed(() => sortBeds(beds.value))

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

function sortBeds(rows: any[]) {
  return [...(rows || [])].sort((a: any, b: any) => {
    const left = bedSortParts(a?.bed)
    const right = bedSortParts(b?.bed)
    if (left.hasNumber !== right.hasNumber) return left.hasNumber - right.hasNumber
    if (left.number !== right.number) return left.number - right.number
    return left.suffix.localeCompare(right.suffix, 'zh-CN', { numeric: true, sensitivity: 'base' })
  })
}

function fmt(value: any) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--'
}

function tick() {
  clock.value = new Date().toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function load() {
  if (!userId.value) {
    error.value = '未识别当前账号。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const params: { user_id: string; shift_code?: string; dept?: string; dept_code?: string } = {
      user_id: userId.value,
      shift_code: 'auto',
    }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDept.value) params.dept = routeDept.value
    const { data } = await getHeadNurseHome(params)
    home.value = data?.data || {}
    auth.updateAccount(home.value?.account)
  } catch (err: any) {
    error.value = err?.message || '护士长首页加载失败'
  } finally {
    loading.value = false
  }
}

function dismissOnboarding() {
  showOnboarding.value = false
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(roleHomeConfig.headNurse?.onboardingKey || 'head_nurse_onboarding', '1')
  }
}

onMounted(() => {
  auth.hydrateFromQuery(route.query)
  tick()
  timer = setInterval(tick, 1000)
  void load()
  if (typeof window !== 'undefined') {
    const key = roleHomeConfig.headNurse?.onboardingKey || 'head_nurse_onboarding'
    if (!window.localStorage.getItem(key)) showOnboarding.value = true
  }
})

onUnmounted(() => clearInterval(timer))

watch(() => [route.query.user_id, route.query.userId, route.query.userName, route.query.useName, route.query.username, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  auth.hydrateFromQuery(route.query)
  void load()
})
</script>

<style scoped>
.head-nurse-home {
  padding: 14px;
  display: grid;
  gap: 12px;
}

.start-guide {
  min-height: 66px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(34, 211, 238, .22);
  border-radius: var(--card-radius);
  background: var(--bg-surface), var(--bg-surface));
}

.start-guide div {
  display: grid;
  gap: 4px;
}

.start-guide span {
  color: var(--accent);
  font-size: 12px;
}

.start-guide strong {
  color: var(--text-primary);
  font-size: 15px;
}

.home-top {
  min-height: 72px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 14px;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: var(--card-radius);
  background: var(--bg-surface), .82);
}

.home-top div {
  display: grid;
  gap: 4px;
}

.home-top span,
.panel-head span,
.empty,
.summary-card span,
.summary-card em {
  color: var(--text-secondary);
  font-size: 12px;
}

.home-top strong {
  color: var(--text-primary);
  font-size: 20px;
}

.top-meta {
  display: flex !important;
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

button {
  min-height: 44px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(125, 211, 252, .2);
  background: var(--bg-surface), .78);
  color: var(--text-primary);
  padding: 0 12px;
  cursor: pointer;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.compliance-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 14px;
  border: 1px solid rgba(34, 211, 238, .22);
  border-radius: var(--card-radius);
  background: var(--bg-surface), var(--bg-surface));
  cursor: pointer;
}

.entry-content {
  display: grid;
  gap: 4px;
}

.entry-content strong {
  color: var(--text-primary);
  font-size: 15px;
}

.entry-content span {
  color: var(--accent);
  font-size: 12px;
}

.compliance-entry button {
  min-height: 36px;
  padding: 0 12px;
  white-space: nowrap;
}

.summary-card {
  min-height: 86px;
  display: grid;
  align-content: center;
  gap: 4px;
  padding: 12px;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: var(--card-radius);
  background: var(--bg-surface), .74);
}

.summary-card strong {
  color: var(--text-primary);
  font-size: 26px;
  line-height: 1;
}

.summary-card.is-red {
  border-color: rgba(239, 68, 68, .42);
}

.summary-card.is-yellow {
  border-color: rgba(245, 158, 11, .42);
}

.summary-card.is-green {
  border-color: rgba(52, 211, 153, .34);
}

.summary-card.is-blue {
  border-color: rgba(56, 189, 248, .34);
}

.bundle-panel {
  padding: 16px;
}

.head-nurse-grid {
  min-height: 560px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.panel {
  min-width: 0;
  overflow: auto;
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: var(--card-radius);
  background: var(--bg-surface), .74);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: baseline;
}

.panel-head strong {
  color: var(--text-primary);
  font-size: 15px;
}

.bed-cloud {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(116px, 1fr));
  gap: 8px;
}

.bed-cloud span {
  min-width: 0;
  min-height: 54px;
  display: grid;
  align-content: center;
  gap: 3px;
  padding: 8px 10px;
  border: 1px solid rgba(125, 211, 252, .12);
  border-radius: var(--card-radius);
  background: var(--bg-surface), var(--bg-surface));
  color: var(--text-primary);
}

.bed-cloud span b {
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.1;
  font-weight: 800;
}

.bed-cloud span em {
  min-width: 0;
  color: var(--text-secondary);
  font-size: 12px;
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-handover {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(125, 211, 252, .14);
}

.pending-handover strong {
  color: var(--warning-soft);
  font-size: 13px;
  display: block;
  margin-bottom: 6px;
}

.handover-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.handover-list span {
  padding: 4px 8px;
  border-radius: var(--card-radius);
  background: rgba(245, 158, 11, .15);
  color: var(--warning-soft);
  font-size: 12px;
}

.workload-summary {
  display: grid;
  gap: 6px;
}

.workload-summary span {
  color: var(--text-secondary);
  font-size: 12px;
}

.workload-summary i {
  height: 8px;
  border-radius: var(--card-radius);
  background: rgba(148, 163, 184, .25);
  overflow: hidden;
}

.workload-summary b {
  display: block;
  height: 100%;
  background: var(--chart-1);
}

.heatmap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.heatmap article {
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .72);
  color: var(--text-primary);
  min-width: 150px;
  display: grid;
  gap: 8px;
}

.heatmap i {
  height: 42px;
  display: flex;
  align-items: end;
  gap: 3px;
}

.heatmap b {
  width: 10px;
  min-height: 8px;
  border-radius: 3px 3px 0 0;
  background: var(--chart-1);
}

.density-high {
  border: 1px solid rgba(239, 68, 68, .6);
}

.density-medium {
  border: 1px solid rgba(245, 158, 11, .55);
}

.density-low {
  border: 1px solid rgba(52, 211, 153, .45);
}

.compliance-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.compliance-summary span {
  color: var(--text-secondary);
  font-size: 12px;
}

.compliance-list {
  display: grid;
  gap: 8px;
}

.compliance-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .72);
}

.compliance-item strong {
  color: var(--text-primary);
  font-size: 13px;
}

.compliance-item span {
  color: var(--text-secondary);
  font-size: 12px;
  text-align: right;
}

.compliance-bar {
  height: 6px;
  border-radius: var(--card-radius);
  background: rgba(148, 163, 184, .25);
  overflow: hidden;
}

.compliance-bar i {
  display: block;
  height: 100%;
  background: var(--chart-2);
  border-radius: var(--card-radius);
}

.alert-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.stat-item {
  padding: 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .72);
}

.stat-item span {
  color: var(--text-secondary);
  font-size: 12px;
  display: block;
}

.stat-item strong {
  color: var(--text-primary);
  font-size: 20px;
  display: block;
  margin-top: 4px;
}

.text-warning {
  color: var(--warning-soft) !important;
}

.event-list {
  display: grid;
  gap: 8px;
}

.event-item {
  display: grid;
  gap: 4px;
  padding: 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .72);
}

.event-item strong {
  color: var(--text-primary);
  font-size: 13px;
}

.event-item span {
  color: var(--text-secondary);
  font-size: 12px;
}

.quality-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.quality-row span {
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .72);
  color: var(--text-secondary);
  font-size: 12px;
}

.scanner-list {
  display: grid;
  gap: 8px;
}

.scanner-item {
  display: grid;
  gap: 4px;
  padding: 8px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .72);
}

.scanner-item strong {
  color: var(--text-primary);
  font-size: 13px;
}

.scanner-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.scanner-stats span {
  color: var(--text-secondary);
  font-size: 12px;
}

.empty {
  padding: 14px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .58);
}

.empty.small {
  padding: 10px;
}

.empty.danger {
  color: var(--danger-soft);
}

.onboarding-mask {
  position: fixed;
  inset: 0;
  z-index: 400;
  display: grid;
  place-items: center;
  background: var(--bg-surface), .48);
  padding: 16px;
}

.onboarding-card {
  width: min(560px, 100%);
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid rgba(125, 211, 252, .24);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  box-shadow: var(--card-shadow);
}

.onboarding-card ol {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 10px;
}

.onboarding-card li {
  color: var(--text-primary);
}

.onboarding-card li b {
  display: block;
}

.onboarding-card li span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 4px;
}

@media (max-width: 1024px) {
  .summary-cards,
  .head-nurse-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .alert-stats {
    grid-template-columns: 1fr;
  }
}

/* Light theme */
html[data-theme='light'] .head-nurse-home {
  background:
    var(--bg-surface), transparent 28%),
    var(--bg-surface), transparent 32%);
}

html[data-theme='light'] .home-top,
html[data-theme='light'] .start-guide,
html[data-theme='light'] .panel,
html[data-theme='light'] .summary-card {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: var(--card-shadow);
}

html[data-theme='light'] .home-top strong,
html[data-theme='light'] .start-guide strong,
html[data-theme='light'] .panel-head strong,
html[data-theme='light'] .summary-card strong {
  color: var(--text-primary);
}

html[data-theme='light'] .home-top span,
html[data-theme='light'] .start-guide span,
html[data-theme='light'] .panel-head span,
html[data-theme='light'] .empty,
html[data-theme='light'] .summary-card span,
html[data-theme='light'] .summary-card em {
  color: var(--text-secondary);
}

html[data-theme='light'] .bed-cloud span {
  background: var(--bg-surface);
  box-shadow: var(--card-shadow);
}

html[data-theme='light'] .bed-cloud span b {
  color: var(--text-primary);
}

html[data-theme='light'] .bed-cloud span em {
  color: var(--text-secondary);
}

html[data-theme='light'] .heatmap article,
html[data-theme='light'] .compliance-item,
html[data-theme='light'] .stat-item,
html[data-theme='light'] .event-item,
html[data-theme='light'] .scanner-item,
html[data-theme='light'] .quality-row span,
html[data-theme='light'] .handover-list span {
  background: var(--bg-surface);
  border-color: rgba(145, 176, 199, 0.26);
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

html[data-theme='light'] .empty.danger {
  color: var(--danger);
  background: var(--danger-bg);
  border-color: rgba(239, 68, 68, 0.18);
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
</style>
