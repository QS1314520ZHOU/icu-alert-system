<template>
  <section class="head-nurse-home">
    <PageHeader title="护士长质控" :subtitle="`护士长 · ${home?.account?.dept || '科室待识别'}`">
      <template #actions>
        <span class="top-meta">{{ accountName }}</span>
        <span class="top-meta">{{ shiftText }}</span>
        <span class="top-meta">{{ clock }}</span>
        <a-button size="small" @click="load">刷新</a-button>
      </template>
    </PageHeader>

    <LoadingState v-if="loading" message="正在汇总全科床位、护理负荷与质控数据..." />
    <ErrorState v-else-if="error" :description="error" />
    <template v-else>
      <WardClinicalBoard class="hn-board" title="全科床位临床概览" />

      <MetricStrip
        :metrics="summaryCards.map((c) => ({
          label: c.label,
          value: c.value,
          variant: c.tone === 'red' ? 'danger' : c.tone === 'yellow' ? 'warning' : c.tone === 'green' ? 'success' : 'info',
          trend: 'stable',
          trendValue: c.hint,
        }))"
      />

      <!-- 依从性看板入口 -->
      <section class="compliance-entry" @click="showCompliance = !showCompliance">
        <div class="entry-content">
          <strong>护理依从性看板</strong>
          <span>查看评估/翻身/CAM-ICU/早期活动依从率时间线、逾期TOP床位和班次对比</span>
        </div>
        <a-button size="small">
          {{ showCompliance ? '收起看板' : '展开看板' }}
        </a-button>
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
        <!-- 右侧 -->
        <section class="panel">
          <div class="panel-head">
            <strong>护理负荷热力图</strong>
            <span>本班护理记录密度</span>
          </div>
          <div class="workload-summary">
            <span>{{ workload.estimated_minutes ? `已用 ${workload.used_minutes ?? '—'} / 预计 ${workload.estimated_minutes} 分钟` : '护理工时未配置，无法计算负荷' }}</span>
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
          <EmptyState v-if="!heatmap.length" description="暂无护理记录数据。" />
        </section>

        <!-- 评估依从 -->
        <section class="panel">
          <div class="panel-head">
            <strong>评估依从率</strong>
            <span>{{ pctv(assessmentCompliance.compliance_rate) }}</span>
          </div>
          <div class="compliance-summary">
            <span>总计 {{ nv(assessmentCompliance.total_reminders) }} 项</span>
            <span>逾期 {{ nv(assessmentCompliance.active_overdue) }} 项</span>
            <span>按时完成 {{ nv(assessmentCompliance.resolved_ontime) }} 项</span>
          </div>
          <div class="compliance-list">
            <article v-for="item in assessmentCompliance.by_type || []" :key="item.score_type" class="compliance-item">
              <strong>{{ item.title || item.score_type }}</strong>
              <div class="compliance-bar">
                <i :style="{ width: `${item.compliance_rate}%` }"></i>
              </div>
              <span>{{ pctv(item.compliance_rate) }} ({{ item.overdue }}/{{ item.total }} 逾期)</span>
            </article>
          </div>
          <EmptyState v-if="!(assessmentCompliance.by_type || []).length" description="暂无评估提醒数据。" />
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
              <strong>{{ nv(alertStats.total_alerts) }}</strong>
            </div>
            <div class="stat-item">
              <span>已处置</span>
              <strong>{{ nv(alertStats.handled) }}</strong>
            </div>
            <div class="stat-item">
              <span>待处理</span>
              <strong :class="{ 'text-warning': alertStats.pending > 0 }">{{ nv(alertStats.pending) }}</strong>
            </div>
            <div class="stat-item">
              <span>处置率</span>
              <strong>{{ alertStats.total_alerts ? pctv(alertStats.handle_rate) : '—' }}</strong>
            </div>
            <div class="stat-item">
              <span>平均响应</span>
              <strong>{{ nv(alertStats.avg_response_minutes) === '—' ? '—' : `${alertStats.avg_response_minutes} 分钟` }}</strong>
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
            <article v-for="event in qualityEvents" :key="`${event.patient_id}-${event.time}-${event.title}`" class="event-item ds-list-item">
              <i :class="['ds-dot', eventDotClass(event)]"></i>
              <div>
                <strong>{{ displayBed(event.bed) }} {{ event.title }}</strong>
                <span>{{ event.type }} · {{ fmt(event.time) }}</span>
              </div>
            </article>
          </div>
          <EmptyState v-if="!qualityEvents.length" description="本班暂无未闭环质控事件。" />
          <div class="quality-row">
            <span>跌倒 {{ nv(qualitySummary.falls) }}</span>
            <span>压疮 {{ nv(qualitySummary.pressure_ulcers) }}</span>
            <span>管路脱出 {{ nv(qualitySummary.line_displacement) }}</span>
            <span>给药差错 {{ nv(qualitySummary.medication_errors) }}</span>
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
                <span>触发 {{ nv(row.fire_count) }}</span>
                <span>确认率 {{ pctv(row.ack_rate) }}</span>
                <span :class="{ 'text-warning': (row.noise_score || 0) > 30 }">噪音 {{ pctv(row.noise_score) }}</span>
              </div>
            </article>
          </div>
          <EmptyState v-if="!scannerRows.length" description="暂无规则健康数据。" />
        </section>

        <!-- 流程任务逾期TOP床位 -->
        <section v-if="overdueByBed.length" class="panel">
          <div class="panel-head">
            <strong>流程逾期 TOP 床位</strong>
            <span>{{ workflowOverdue.length }} 条逾期</span>
          </div>
          <div class="top-bed-list">
            <article v-for="(entry, idx) in overdueByBed.slice(0, 10)" :key="entry[0]" class="top-bed-item">
              <span class="top-bed-rank">{{ idx + 1 }}</span>
              <strong>{{ entry[0] }}床</strong>
              <span>{{ entry[1] }} 条逾期</span>
            </article>
          </div>
        </section>

        <!-- P2→P1 升级列表 -->
        <section v-if="escalationP2toP1.length" class="panel">
          <div class="panel-head">
            <strong>P2→P1 升级记录</strong>
            <span>{{ escalationP2toP1.length }} 条</span>
          </div>
          <div class="event-list">
            <article v-for="item in escalationP2toP1.slice(0, 10)" :key="item._id || item.created_at" class="event-item ds-list-item">
              <i class="ds-dot event-dot--escalation"></i>
              <div>
                <strong>{{ item.bed || '--' }}床 {{ item.patient_name || '--' }}</strong>
                <span>{{ item.name || item.rule_id }} · {{ fmt(item.created_at) }}</span>
              </div>
            </article>
          </div>
        </section>

        <!-- 质控缺项 -->
        <section v-if="qualityGaps.length" class="panel">
          <div class="panel-head">
            <strong>质控缺项</strong>
            <span>{{ qualityGaps.length }} 项</span>
          </div>
          <div class="event-list">
            <article v-for="item in qualityGaps.slice(0, 10)" :key="item._id || item.created_at" class="event-item ds-list-item">
              <i class="ds-dot event-dot--gap"></i>
              <div>
                <strong>{{ item.bed || '--' }}床 {{ item.patient_name || '--' }}</strong>
                <span>{{ item.name || item.rule_id }} · {{ item.alert_type ? formatAlertTypeLabel(item.alert_type) : '' }}</span>
              </div>
            </article>
          </div>
        </section>

        <!-- 已升级告警 -->
        <section v-if="workflowEscalated.length" class="panel">
          <div class="panel-head">
            <strong>已升级告警</strong>
            <span>{{ workflowEscalated.length }} 条</span>
          </div>
          <div class="event-list">
            <article v-for="item in workflowEscalated.slice(0, 10)" :key="item._id || item.created_at" class="event-item ds-list-item">
              <i class="ds-dot event-dot--escalated"></i>
              <div>
                <strong>{{ item.bed || '--' }}床 {{ item.patient_name || '--' }}</strong>
                <span>{{ item.name || item.rule_id }} · {{ item.priority }} · {{ fmt(item.created_at) }}</span>
              </div>
            </article>
          </div>
        </section>
      </main>

      <div v-if="showOnboarding" class="onboarding-mask" @click.self="dismissOnboarding">
        <div class="onboarding-card">
          <div class="panel-head">
            <strong>护士长看板3步用法</strong>
            <a-button size="small" @click="dismissOnboarding">知道了</a-button>
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
import WardClinicalBoard from '../components/home/WardClinicalBoard.vue'
import { Button as AButton } from 'ant-design-vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getHeadNurseHome } from '../api'
import { useAuthStore } from '../stores/auth'
import { roleHomeConfig } from '../config/roleHomeConfig'
import ComplianceDashboard from './ComplianceDashboard.vue'
import BundleComplianceChecklist from './BundleComplianceChecklist.vue'
import { formatAlertTypeLabel } from '../utils/displayLabels'
import { PageHeader, MetricStrip, LoadingState, ErrorState, EmptyState } from '../components/common/design-system'

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
    // 后端未返回 pending_handover 时为“未统计”，不能显示为 0（会被误读为全部交接完成）
    Array.isArray(home.value?.pending_handover)
      ? { key: 'handover', label: '待交接床位', value: pendingHandover.value.length, hint: pendingHandover.value.length ? '下班前需完成' : '本班已全部交接', tone: pendingHandover.value.length ? 'yellow' : 'green' }
      : { key: 'handover', label: '待交接床位', value: '—', hint: '交班状态未统计，请到智能交接班查看', tone: 'blue' },
    { key: 'compliance', label: '评估依从率', value: compliance.total_reminders ? `${compliance.compliance_rate || 0}%` : '—', hint: compliance.total_reminders ? `${compliance.active_overdue || 0} 项逾期` : '暂无评估提醒数据', tone: !compliance.total_reminders ? 'blue' : (compliance.active_overdue || 0) > 0 ? 'red' : 'green' },
    { key: 'alerts', label: '告警处置率', value: alerts.total_alerts ? `${alerts.handle_rate || 0}%` : '—', hint: alerts.total_alerts ? `${alerts.pending || 0} 项待处理` : '近12小时无告警数据', tone: !alerts.total_alerts ? 'blue' : (alerts.pending || 0) > 0 ? 'yellow' : 'green' },
  ]
})


// ── 流程/质控聚合统计 ──
const allActiveAlerts = computed(() => home.value?.active_alerts || [])
const workflowAlerts = computed(() => allActiveAlerts.value.filter((a: any) => {
  const d = String(a?.alert_domain || '').toLowerCase()
  return d === 'workflow_reminder' || d === 'quality_gap'
}))
const workflowOverdue = computed(() => workflowAlerts.value.filter((a: any) => {
  const now = Date.now(); const due = new Date(a?.due_at || 0).getTime()
  return due > 0 && due < now
}))
const workflowEscalated = computed(() => workflowAlerts.value.filter((a: any) => a?.escalation_of))
const escalationP2toP1 = computed(() => workflowAlerts.value.filter((a: any) => {
  const hist = a?.priority_history
  return Array.isArray(hist) && hist.some((h: any) => h?.from === 'p2' && h?.to === 'p1')
}))
const overdueByBed = computed(() => {
  const map = new Map<string, number>()
  for (const a of workflowOverdue.value) {
    const bed = String(a?.bed || '--')
    map.set(bed, (map.get(bed) || 0) + 1)
  }
  return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10)
})
const qualityGaps = computed(() => allActiveAlerts.value.filter((a: any) =>
  String(a?.alert_domain || '').toLowerCase() === 'quality_gap'
))

function displayBed(value: any) {
  const text = String(value || '').trim()
  if (!text || text === '--') return '--床'
  return text.includes('床') ? text : `${text}床`
}

/** 缺失即未知：后端未返回时显示“—”，不把缺失当作 0 */
function nv(value: any) {
  if (value == null || value === '') return '—'
  const n = Number(value)
  return Number.isFinite(n) ? n : '—'
}
function pctv(value: any) {
  const v = nv(value)
  return v === '—' ? '—' : `${v}%`
}
function fmt(value: any) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--'
}

function eventDotClass(row: any) {
  const key = String(row?.severity || row?.level || row?.risk_level || row?.type || row?.title || '').toLowerCase()
  if (/critical|danger|red|危急|跌倒|压疮|脱出|差错/.test(key)) return 'is-critical'
  if (/high|warning|warn|yellow|高危|关注|逾期/.test(key)) return 'is-warn'
  return 'is-muted'
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
})

onUnmounted(() => clearInterval(timer))

watch(() => [route.query.user_id, route.query.userId, route.query.userName, route.query.useName, route.query.username, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  auth.hydrateFromQuery(route.query)
  void load()
})
</script>

<style scoped>
.hn-board { margin-bottom: 12px; }
.head-nurse-home {
  padding: var(--page-padding);
  padding-bottom: 80px;
  display: grid;
  gap: var(--section-gap);
}

/* ── 头部辅助信息 ── */
.top-meta {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

/* ── 引导横幅 ── */
.start-guide {
  min-height: 66px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--element-gap-lg);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
}

.start-guide div {
  display: grid;
  gap: 4px;
}

.start-guide span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
}

.start-guide strong {
  color: var(--color-text-primary);
  font-size: var(--text-section-title);
  font-weight: var(--text-section-title-weight);
}

/* ── 依从性看板入口 ── */
.compliance-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  cursor: pointer;
  transition: border-color 0.15s;
}

.compliance-entry:hover {
  border-color: var(--color-border-strong);
}

.entry-content {
  display: grid;
  gap: 4px;
}

.entry-content strong {
  color: var(--color-text-primary);
  font-size: var(--text-section-title);
  font-weight: var(--text-section-title-weight);
}

.entry-content span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  line-height: var(--text-caption-line-height);
}

.bundle-panel {
  padding: var(--card-padding);
}

.head-nurse-grid {
  min-height: 560px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.panel {
  min-width: 0;
  overflow: auto;
  display: grid;
  align-content: start;
  gap: 10px;
  padding: var(--card-padding);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: baseline;
}

.panel-head strong {
  color: var(--color-text-primary);
  font-size: var(--text-section-title);
  font-weight: var(--text-section-title-weight);
}

.panel-head span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
}

.bed-cloud {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 10px;
}

.bed-cloud span {
  position: relative;
  min-width: 0;
  min-height: 58px;
  display: grid;
  align-content: center;
  gap: 3px;
  padding: 9px 12px 9px 30px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  transition: background 0.15s ease, border-color 0.15s ease;
}

.bed-cloud span::before {
  content: '';
  position: absolute;
  left: 0;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--color-border-strong);
}

.bed-cloud span:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.bed-cloud .ds-dot {
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-50%);
  width: 9px;
  height: 9px;
  border: 2px solid var(--color-bg-surface);
}

.bed-cloud span b {
  color: var(--color-text-primary);
  font-size: var(--text-section-title);
  line-height: 1.1;
  font-weight: var(--weight-bold);
}

.bed-cloud span em {
  min-width: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-body);
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-handover {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-divider);
}

.pending-handover strong {
  color: var(--color-warning);
  font-size: var(--text-body);
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
  border-radius: 999px;
  background: var(--color-warning-soft-bg);
  color: var(--color-warning);
  font-size: var(--text-caption);
}

.workload-summary {
  display: grid;
  gap: 6px;
}

.workload-summary span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
}

.workload-summary i {
  height: 8px;
  border-radius: 999px;
  background: var(--color-bg-inset);
  overflow: hidden;
}

.workload-summary b {
  display: block;
  height: 100%;
  background: var(--chart-color-1);
}

.heatmap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.heatmap article {
  padding: 8px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  min-width: 150px;
  display: grid;
  gap: 8px;
}

.heatmap article strong {
  font-size: var(--text-body);
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
  background: var(--chart-color-1);
}

.density-high {
  border: 1px solid var(--color-critical-border);
}

.density-medium {
  border: 1px solid var(--color-high-risk-border);
}

.density-low {
  border: 1px solid var(--color-normal-border);
}

.compliance-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.compliance-summary span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
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
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
}

.compliance-item strong {
  color: var(--color-text-primary);
  font-size: var(--text-body);
}

.compliance-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  text-align: right;
}

.compliance-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--color-bg-inset);
  overflow: hidden;
}

.compliance-bar i {
  display: block;
  height: 100%;
  background: var(--chart-color-2);
  border-radius: 999px;
}

.alert-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.stat-item {
  padding: 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
}

.stat-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  display: block;
}

.stat-item strong {
  color: var(--color-text-primary);
  font-size: var(--text-metric-normal);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
  display: block;
  margin-top: 4px;
}

.text-warning {
  color: var(--color-warning) !important;
}

.event-list {
  display: grid;
  gap: 8px;
}

.event-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  padding: 10px;
  border-radius: var(--radius-md);
  background: transparent;
}

.event-item:hover {
  background: var(--color-bg-surface-secondary);
}

.event-item strong {
  color: var(--color-text-primary);
  font-size: var(--text-body);
}

.event-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
}

.event-item .ds-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-top: 5px;
}

.event-dot--escalation {
  background: var(--color-warning);
}

.event-dot--gap {
  background: var(--color-warning-soft);
}

.event-dot--escalated {
  background: var(--color-danger);
}

:global(.ai-pulse-root) {
  z-index: 120;
}

.quality-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.quality-row span {
  padding: 8px 10px;
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  font-variant-numeric: tabular-nums;
}

.scanner-list {
  display: grid;
  gap: 8px;
}

.scanner-item {
  display: grid;
  gap: 4px;
  padding: 8px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
}

.scanner-item strong {
  color: var(--color-text-primary);
  font-size: var(--text-body);
}

.scanner-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.scanner-stats span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  font-variant-numeric: tabular-nums;
}

.onboarding-mask {
  position: fixed;
  inset: 0;
  z-index: 400;
  display: grid;
  place-items: center;
  background: rgba(17, 24, 39, 0.4);
  padding: 16px;
}

.onboarding-card {
  width: min(560px, 100%);
  display: grid;
  gap: 12px;
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-lg);
}

.onboarding-card ol {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 10px;
}

.onboarding-card li {
  color: var(--color-text-primary);
}

.onboarding-card li b {
  display: block;
}

.onboarding-card li span {
  display: block;
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  margin-top: 4px;
}

/* 面板内空态保持紧凑 */
.panel :deep(.empty-state) {
  padding: 24px 16px;
}

@media (max-width: 1024px) {
  .head-nurse-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .alert-stats {
    grid-template-columns: 1fr;
  }
}
</style>
