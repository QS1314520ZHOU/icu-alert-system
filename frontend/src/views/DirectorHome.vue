<template>
  <section class="director-home">
    <PageHeader title="主任首页" :subtitle="`科主任 · ${home?.account?.dept || '科室待识别'}`">
      <template #actions>
        <span class="top-meta">{{ accountName }}</span>
        <span class="top-meta">{{ shiftText }}</span>
        <span class="top-meta">{{ clock }}</span>
        <a-button size="small" @click="load">刷新</a-button>
      </template>
    </PageHeader>

    <LoadingState v-if="loading" message="正在汇总科室质控、KPI和科研数据..." />
    <ErrorState v-else-if="error" :description="error" />
    <template v-else>
      <WardClinicalBoard class="dr-board" title="科室患者临床概览" default-filter="focus" />

      <MetricStrip
        :metrics="summaryCards.map((c) => ({
          label: c.label,
          value: c.value,
          variant: c.tone === 'red' ? 'danger' : c.tone === 'yellow' ? 'warning' : c.tone === 'green' ? 'success' : 'info',
          trend: 'stable',
          trendValue: c.hint,
        }))"
      />

      <!-- Bundle 合规核查 -->
      <section class="panel bundle-panel">
        <BundleComplianceChecklist :dept-code="routeDeptCode" :dept="routeDept" />
      </section>

      <main class="director-grid">
        <!-- 主任视角：先看告警闭环与质控安全，再看床位人力、规则质量与科研 -->
        <!-- KPI 摘要 -->
        <section class="panel">
          <div class="panel-head">
            <strong>KPI 摘要</strong>
            <span>近24小时</span>
          </div>
          <div class="kpi-grid">
            <div class="kpi-section">
              <strong>告警处置</strong>
              <div class="kpi-items">
                <div class="kpi-item">
                  <span>告警总数</span>
                  <b>{{ nv(alertStats.total_24h) }}</b>
                </div>
                <div class="kpi-item">
                  <span>已处置</span>
                  <b>{{ nv(alertStats.handled_24h) }}</b>
                </div>
                <div class="kpi-item">
                  <span>待处理</span>
                  <b :class="{ 'text-warning': (alertStats.pending_24h || 0) > 0 }">{{ nv(alertStats.pending_24h) }}</b>
                </div>
                <div class="kpi-item">
                  <span>处置率</span>
                  <b>{{ alertStats.total_24h ? pctv(alertStats.handle_rate) : '—' }}</b>
                </div>
              </div>
            </div>
            <div class="kpi-section">
              <strong>AI 推理</strong>
              <div class="kpi-items">
                <div class="kpi-item">
                  <span>综合推理生成</span>
                  <b>{{ nv(aiStats.integrated_reasoning) }}</b>
                </div>
                <div class="kpi-item">
                  <span>临床确认采纳</span>
                  <b title="后端 adopted 字段仅记录前端点击，不能代表临床采纳">未统计</b>
                </div>
              </div>
            </div>
            <div class="kpi-section">
              <strong>护理负荷</strong>
              <div class="kpi-items">
                <div class="kpi-item">
                  <span>平均负荷</span>
                  <b>{{ pctv(workloadStats.avg_nursing_workload_percent) }}</b>
                </div>
                <div class="kpi-item">
                  <span>高负荷床</span>
                  <b :class="{ 'text-warning': (workloadStats.high_workload_beds || 0) > 0 }">{{ nv(workloadStats.high_workload_beds) }}</b>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 质控大屏 -->
        <section class="panel">
          <div class="panel-head">
            <strong>质控安全事件</strong>
            <span>近7天</span>
          </div>
          <div class="quality-section">
            <strong>质控事件</strong>
            <div class="quality-grid">
              <div class="quality-item">
                <span>跌倒</span>
                <b>{{ nv(qualityEvents.falls) }}</b>
              </div>
              <div class="quality-item">
                <span>压疮</span>
                <b>{{ nv(qualityEvents.pressure_ulcers) }}</b>
              </div>
              <div class="quality-item">
                <span>管路脱出</span>
                <b>{{ nv(qualityEvents.line_displacement) }}</b>
              </div>
              <div class="quality-item">
                <span>给药差错</span>
                <b>{{ nv(qualityEvents.medication_errors) }}</b>
              </div>
            </div>
          </div>
          <div class="adoption-section">
            <strong>信号采纳</strong>
            <div class="adoption-stats">
              <span>总信号 {{ nv(adoptionSummary.total_signals) }}</span>
              <span>已采纳 {{ nv(adoptionSummary.adopted) }}</span>
              <span>采纳率 {{ adoptionSummary.total_signals ? pctv(adoptionSummary.adoption_rate) : '—' }}</span>
            </div>
          </div>
        </section>

        <!-- 科室概览 -->
        <section class="panel">
          <div class="panel-head">
            <strong>科室概览</strong>
            <span>{{ overview.total_beds ? `${overview.total_beds} 床` : '床位数未配置' }}</span>
          </div>
          <div class="overview-stats">
            <div class="overview-item">
              <span>床位使用率</span>
              <strong>{{ overview.total_beds ? pctv(overview.occupancy_rate) : '—' }}</strong>
              <em>{{ nv(overview.occupied_beds) }}/{{ nv(overview.total_beds) }}</em>
            </div>
            <div class="overview-item">
              <span>主管医生</span>
              <strong>{{ Array.isArray(overview.doctors) ? overview.doctors.length : '—' }}</strong>
              <em>人</em>
            </div>
            <div class="overview-item">
              <span>责任护士</span>
              <strong>{{ Array.isArray(overview.nurses) ? overview.nurses.length : '—' }}</strong>
              <em>人</em>
            </div>
          </div>
          <div class="doctor-list">
            <strong>医生床位分布</strong>
            <div class="doctor-grid">
              <article v-for="doc in overview.doctors || []" :key="doc.user_id" class="doctor-item">
                <span>{{ doc.name }}</span>
                <b>{{ doc.managed_beds }} 床</b>
              </article>
            </div>
            <EmptyState v-if="!(overview.doctors || []).length" description="暂无医生分管数据。" />
          </div>
        </section>

        <!-- 规则健康度 -->
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
          <a-button class="full-btn" type="primary" @click="$router.push({ path: '/admin/scanner-health', query: route.query })">查看规则健康详情</a-button>
        </section>

        <!-- 科研动态 -->
        <section class="panel">
          <div class="panel-head">
            <strong>科研动态</strong>
            <span>{{ researchSummary.total != null ? `${researchSummary.total} 个任务` : '未接入' }}</span>
          </div>
          <div class="research-stats">
            <div class="research-item">
              <span>待处理</span>
              <b>{{ nv(researchSummary.pending) }}</b>
            </div>
            <div class="research-item">
              <span>已完成</span>
              <b>{{ nv(researchSummary.completed) }}</b>
            </div>
          </div>
          <div class="research-list">
            <article v-for="item in researchSummary.recent_exports || []" :key="item.job_id" class="research-export">
              <strong>{{ item.title || '科研导出' }}</strong>
              <span>{{ item.status }} · {{ fmt(item.created_at) }}</span>
            </article>
          </div>
          <EmptyState v-if="!(researchSummary.recent_exports || []).length" description="暂无科研任务。" />
          <a-button class="full-btn" type="primary" @click="$router.push({ path: '/research-workbench', query: route.query })">进入科研工作台</a-button>
        </section>

        <!-- 角色分布 -->
        <section class="panel">
          <div class="panel-head">
            <strong>角色分布</strong>
            <span>科室人员</span>
          </div>
          <div class="role-grid">
            <div class="role-item">
              <span>医生</span>
              <b>{{ nv(roleDistribution.doctors) }}</b>
            </div>
            <div class="role-item">
              <span>护士</span>
              <b>{{ nv(roleDistribution.nurses) }}</b>
            </div>
            <div class="role-item">
              <span>药师</span>
              <b>{{ nv(roleDistribution.pharmacists) }}</b>
            </div>
            <div class="role-item">
              <span>护士长</span>
              <b>{{ nv(roleDistribution.head_nurses) }}</b>
            </div>
          </div>
        </section>
      </main>

      <div v-if="showOnboarding" class="onboarding-mask" @click.self="dismissOnboarding">
        <div class="onboarding-card">
          <div class="panel-head">
            <strong>主任看板3步用法</strong>
            <a-button size="small" @click="dismissOnboarding">知道了</a-button>
          </div>
          <ol>
            <li><b>先看科室概览</b><span>确认床位使用率和医护人员分布。</span></li>
            <li><b>查看质控大屏</b><span>关注质控事件和信号采纳率。</span></li>
            <li><b>追踪KPI和科研</b><span>重点处理告警处置、AI采纳和科研任务。</span></li>
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
import { getDirectorHome } from '../api'
import { useAuthStore } from '../stores/auth'
import { roleHomeConfig } from '../config/roleHomeConfig'
import BundleComplianceChecklist from './BundleComplianceChecklist.vue'
import { PageHeader, MetricStrip, LoadingState, ErrorState, EmptyState } from '../components/common/design-system'

const route = useRoute()
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

const accountName = computed(() => home.value?.account?.display_name || home.value?.account?.userName || userId.value || '未识别主任')
const overview = computed(() => home.value?.department_overview || {})
const qualityDashboard = computed(() => home.value?.quality_dashboard || {})
const qualityEvents = computed(() => qualityDashboard.value?.quality_events || {})
const adoptionSummary = computed(() => qualityDashboard.value?.adoption_summary || {})
const kpiSummary = computed(() => home.value?.kpi_summary || {})
const alertStats = computed(() => kpiSummary.value?.alert_stats || {})
const aiStats = computed(() => kpiSummary.value?.ai_stats || {})
const workloadStats = computed(() => kpiSummary.value?.workload_stats || {})
const researchSummary = computed(() => home.value?.research_summary || {})
const roleDistribution = computed(() => home.value?.role_distribution || {})
const scannerHealth = computed(() => qualityDashboard.value?.scanner_health || {})
const scannerRows = computed(() => (scannerHealth.value?.rows || []).slice(0, 10))

const shiftText = computed(() => {
  const s = home.value?.shift
  if (!s) return '班次待配置'
  return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
})

const summaryCards = computed(() => {
  const occRate = overview.value?.occupancy_rate || 0
  const handleRate = alertStats.value?.handle_rate || 0
  const researchTotal = nv(researchSummary.value?.total)
  return [
    { key: 'beds', label: '床位使用率', value: overview.value?.total_beds ? `${occRate}%` : '—', hint: overview.value?.total_beds ? `${overview.value?.occupied_beds || 0}/${overview.value?.total_beds}` : '床位数未配置', tone: !overview.value?.total_beds ? 'blue' : occRate > 90 ? 'red' : occRate > 80 ? 'yellow' : 'green' },
    { key: 'alerts', label: '告警处置率', value: alertStats.value?.total_24h ? `${handleRate}%` : '—', hint: alertStats.value?.total_24h ? `${alertStats.value?.pending_24h || 0} 项待处理` : '暂无告警数据', tone: !alertStats.value?.total_24h ? 'blue' : (alertStats.value?.pending_24h || 0) > 0 ? 'yellow' : 'green' },
    { key: 'ai', label: '近24h AI推理', value: nv(aiStats.value?.integrated_reasoning), hint: '生成条数（暂无临床确认采纳数据）', tone: 'blue' },
    { key: 'research', label: '科研任务', value: researchTotal, hint: researchSummary.value?.pending != null ? `${researchSummary.value.pending} 个待处理` : '科研数据未接入', tone: (researchSummary.value?.pending || 0) > 0 ? 'yellow' : 'blue' },
  ]
})

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
    const params: { user_id: string; dept?: string; dept_code?: string } = {
      user_id: userId.value,
    }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDept.value) params.dept = routeDept.value
    const { data } = await getDirectorHome(params)
    home.value = data?.data || {}
    auth.updateAccount(home.value?.account)
  } catch (err: any) {
    error.value = err?.message || '主任首页加载失败'
  } finally {
    loading.value = false
  }
}

function dismissOnboarding() {
  showOnboarding.value = false
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(roleHomeConfig.director?.onboardingKey || 'director_onboarding', '1')
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
.dr-board { margin-bottom: 12px; }
.director-home {
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

.full-btn {
  width: 100%;
}

.bundle-panel {
  padding: var(--card-padding);
}

.director-grid {
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

.overview-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.overview-item {
  padding: 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
  text-align: center;
}

.overview-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  display: block;
}

.overview-item strong {
  color: var(--color-text-primary);
  font-size: var(--text-metric-key);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
  display: block;
  margin-top: 4px;
}

.overview-item em {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  font-style: normal;
  font-variant-numeric: tabular-nums;
}

.doctor-list {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-divider);
}

.doctor-list strong {
  color: var(--color-text-primary);
  font-size: var(--text-body);
  font-weight: var(--weight-semibold);
  display: block;
  margin-bottom: var(--space-2);
}

.doctor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 6px;
}

.doctor-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
}

.doctor-item span {
  color: var(--color-text-primary);
  font-size: var(--text-caption);
}

.doctor-item b {
  color: var(--chart-color-1);
  font-size: var(--text-caption);
  font-variant-numeric: tabular-nums;
}

.quality-section,
.adoption-section {
  margin-bottom: var(--space-2);
}

.quality-section strong,
.adoption-section strong {
  color: var(--color-text-primary);
  font-size: var(--text-body);
  font-weight: var(--weight-semibold);
  display: block;
  margin-bottom: var(--space-2);
}

.quality-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}

.quality-item {
  padding: 8px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
  text-align: center;
}

.quality-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  display: block;
}

.quality-item b {
  color: var(--color-text-primary);
  font-size: var(--text-metric-normal);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
  display: block;
  margin-top: 4px;
}

.adoption-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.adoption-stats span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  font-variant-numeric: tabular-nums;
}

.kpi-grid {
  display: grid;
  gap: 12px;
}

.kpi-section strong {
  color: var(--color-text-primary);
  font-size: var(--text-body);
  font-weight: var(--weight-semibold);
  display: block;
  margin-bottom: var(--space-2);
}

.kpi-items {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 6px;
}

.kpi-item {
  padding: 8px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
  text-align: center;
}

.kpi-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  display: block;
}

.kpi-item b {
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


.research-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.research-item {
  padding: 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
  text-align: center;
}

.research-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  display: block;
}

.research-item b {
  color: var(--color-text-primary);
  font-size: var(--text-metric-normal);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
  display: block;
  margin-top: 4px;
}

.research-list {
  display: grid;
  gap: 6px;
}

.research-export {
  display: grid;
  gap: 2px;
  padding: 8px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
}

.research-export strong {
  color: var(--color-text-primary);
  font-size: var(--text-caption);
  font-weight: var(--weight-semibold);
}

.research-export span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  font-variant-numeric: tabular-nums;
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.role-item {
  padding: 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-bg-surface);
  text-align: center;
}

.role-item span {
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  display: block;
}

.role-item b {
  color: var(--color-text-primary);
  font-size: var(--text-metric-normal);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
  display: block;
  margin-top: 4px;
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
  .director-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .overview-stats,
  .quality-grid,
  .role-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
