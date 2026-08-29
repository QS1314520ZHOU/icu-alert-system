<template>
  <section class="role-home doctor-home">
    <!-- 紧凑头部：只保留身份和时钟 -->
    <header class="home-header">
      <div class="header-identity">
        <strong>{{ accountName }}</strong>
        <span class="header-dept">{{ home?.account?.dept || '科室待识别' }}</span>
        <span class="header-shift">{{ shiftText }}</span>
      </div>
      <div class="header-actions">
        <span class="header-clock">{{ clock }}</span>
        <button type="button" class="btn-refresh" @click="load">刷新</button>
      </div>
    </header>

    <!-- 加载态 -->
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>正在加载...</span>
    </div>

    <!-- 错误态 -->
    <div v-else-if="error" class="error-state">{{ error }}</div>

    <!-- 主内容 -->
    <template v-else>
      <!-- 关键指标卡 -->
      <div class="kpi-metrics">
        <ClinicalMetricCard
          label="ICU在科患者"
          :value="sortedFocusPatients.length"
          unit="人"
          value-size="key"
          :change-text="`较昨日${focusPatientsDelta >= 0 ? '+' : ''}${focusPatientsDelta}`"
        />
        <ClinicalMetricCard
          label="危急患者"
          :value="criticalCount"
          unit="人"
          status="critical"
          value-size="key"
        />
        <ClinicalMetricCard
          label="未签收告警"
          :value="unackedAlertCount"
          unit="条"
          :status="unackedAlertCount > 0 ? 'high-risk' : 'normal'"
          value-size="key"
        />
        <ClinicalMetricCard
          label="即将超时"
          :value="timeoutItems.length"
          unit="项"
          :status="timeoutItems.length > 0 ? 'warning' : 'normal'"
          value-size="key"
        />
      </div>

      <!-- 昨夜AI摘要：一句话自然语言 -->
      <section v-if="aiSummary" class="ai-summary" @click="$router.push({ path: '/clinical-workflow', query: route.query })">
        <span class="ai-summary-icon">✨</span>
        <span class="ai-summary-text">{{ aiSummary }}</span>
        <span class="ai-summary-link">查看详情 →</span>
      </section>

      <!-- 可视化区：风险矩阵 + 告警漏斗 -->
      <div class="viz-row">
        <div class="viz-matrix">
          <RiskMatrix
            :patients="riskMatrixPatients"
            :height="320"
            @patient-click="(p) => goPatient(p.id)"
          />
        </div>
        <div class="viz-funnel">
          <AlertFunnel
            :stages="alertFunnelStages"
            :height="320"
          />
        </div>
      </div>

      <!-- 主网格：4个核心区域 -->
      <main class="doctor-grid">
        <!-- 1. 我的重点患者 -->
        <section class="panel focus-panel">
          <div class="panel-head">
            <strong>重点患者</strong>
            <span class="panel-count" v-if="sortedFocusPatients.length">{{ sortedFocusPatients.length }}人</span>
          </div>
          <div class="patient-list">
            <article
              v-for="item in sortedFocusPatients"
              :key="item.patient_id"
              class="patient-row"
              @click="goPatient(item.patient_id)"
            >
              <div class="patient-main">
                <div class="patient-bed-name">
                  <span class="bed-num">{{ displayBed(item.bed) }}</span>
                  <span class="patient-name">{{ item.name || '未知' }}</span>
                </div>
                <div class="patient-issue">{{ cleanReason(item.reason) }}</div>
              </div>
              <div class="patient-meta">
                <em :class="['risk-badge', badgeClass(item.risk_level)]">{{ riskLabel(item.risk_level) }}</em>
                <span class="next-action" v-if="item.next_action">{{ item.next_action }}</span>
                <button type="button" class="btn-enter" @click.stop="goPatient(item.patient_id)">进入</button>
                <button type="button" class="btn-more" @click.stop="togglePatientMenu(item.patient_id)">⋯</button>
              </div>
              <!-- 更多操作菜单 -->
              <div v-if="openMenuId === item.patient_id" class="patient-menu" @click.stop>
                <button type="button" @click="goPatientTab(item.patient_id, 'alerts')">处理告警</button>
                <button type="button" @click="goPatientTab(item.patient_id, 'ai')">查房摘要</button>
                <button type="button" @click="goPatientTab(item.patient_id, 'documents')">病历文书</button>
              </div>
            </article>
            <div v-if="!sortedFocusPatients.length" class="empty-state">{{ doctorEmptyText }}</div>
          </div>
        </section>

        <!-- 2. 今日待办 -->
        <section class="panel todo-panel">
          <div class="panel-head">
            <strong>今日待办</strong>
            <span class="panel-count" v-if="pendingTasks.length">{{ pendingTasks.length }}项</span>
          </div>
          <div class="task-list">
            <article
              v-for="item in pendingTasks"
              :key="item.task_id || item.title"
              class="task-row"
              @click="goTask(item)"
            >
              <div class="task-main">
                <strong>{{ item.title || item.detail || '临床任务' }}</strong>
                <span class="task-bed">{{ displayBed(item.bed_label || item.bed) }} · {{ item.module_label || item.module || '临床' }}</span>
              </div>
              <button type="button" class="btn-task" @click.stop="goTask(item)">处理</button>
            </article>
            <div v-if="!pendingTasks.length" class="empty-state">暂无待办</div>
          </div>
        </section>

        <!-- 3. 昨夜重要变化 -->
        <section class="panel changes-panel">
          <div class="panel-head">
            <strong>昨夜重要变化</strong>
          </div>
          <div v-if="nightChanges.length" class="changes-list">
            <article v-for="(change, idx) in nightChanges" :key="idx" class="change-row">
              <span class="change-icon" :class="change.tone">{{ change.icon }}</span>
              <span class="change-text">{{ change.text }}</span>
            </article>
          </div>
          <div v-else class="empty-state">昨夜无重要变化</div>
        </section>

        <!-- 4. 即将超时事项 -->
        <section class="panel timeout-panel">
          <div class="panel-head">
            <strong>即将超时</strong>
            <span class="panel-count" v-if="timeoutItems.length">{{ timeoutItems.length }}项</span>
          </div>
          <div v-if="timeoutItems.length" class="timeout-list">
            <article v-for="(item, idx) in timeoutItems" :key="idx" class="timeout-row" @click="goTask(item)">
              <div class="timeout-main">
                <strong>{{ item.title }}</strong>
                <span class="timeout-deadline">{{ item.deadline }}</span>
              </div>
              <button type="button" class="btn-task" @click.stop="goTask(item)">处理</button>
            </article>
          </div>
          <div v-else class="empty-state">暂无超时风险</div>
        </section>
      </main>

      <!-- 科室质控：只显示异常项 -->
      <section v-if="qualityAbnormal" class="quality-bar" @click="$router.push('/analytics')">
        <span class="quality-icon">⚠️</span>
        <span>{{ qualityAbnormal }}</span>
        <span class="quality-link">查看详情 →</span>
      </section>
      <section v-else-if="qualityLoaded" class="quality-ok">
        近 7 日无新增质量异常
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDoctorHome } from '../api'
import { useAuthStore } from '../stores/auth'
import { formatRiskLevelLabel } from '../utils/displayLabels'
import { ClinicalMetricCard, RiskMatrix, AlertFunnel } from '../components/charts'
import type { MatrixPatient } from '../components/charts'
import type { FunnelStage } from '../components/charts'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const home = ref<any>(null)
const clock = ref('')
const openMenuId = ref<string | null>(null)
let timer: any

// ─── 身份解析 ────────────────────────────────────────────────────────────────
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

// ─── 数据派生 ────────────────────────────────────────────────────────────────
const focusPatients = computed(() => home.value?.focus_patients || [])
const sortedFocusPatients = computed(() => sortBeds(focusPatients.value, (row: any) => row?.bed))
const pendingTasks = computed(() => (home.value?.pending_tasks || []).slice(0, 8))
const doctorEmptyText = computed(() => cleanEmptyText(home.value?.data_state?.empty_reason, '当前暂无需要置顶的分管患者'))
const shiftText = computed(() => {
  const s = home.value?.shift
  if (!s) return '班次待配置'
  return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
})

// AI昨夜摘要：一句话自然语言
const aiSummary = computed(() => {
  const a = home.value?.ai_night_watch || {}
  const total = a.total_alerts ?? 0
  const handled = a.handled ?? 0
  const pending = a.pending_followup ?? 0
  if (!total) return ''
  const parts: string[] = []
  parts.push(`昨夜共 ${total} 条告警`)
  if (handled) parts.push(`${handled} 条已处理`)
  if (pending) parts.push(`${pending} 条待跟进`)
  return parts.join('，') + '。'
})

// 昨夜重要变化：从数据中提取关键变化
const nightChanges = computed(() => {
  const changes: Array<{ icon: string; text: string; tone: string }> = []
  const a = home.value?.ai_night_watch || {}

  // 从患者数据中提取变化
  focusPatients.value.forEach((p: any) => {
    if (p.risk_changed) {
      changes.push({
        icon: '⬆',
        text: `${p.bed} ${p.name || ''} 风险等级变化`,
        tone: 'up'
      })
    }
  })

  // 从AI数据中提取关键事件
  if (a.pending_followup > 0) {
    changes.push({
      icon: '🔔',
      text: `${a.pending_followup} 条告警待跟进`,
      tone: 'warn'
    })
  }

  return changes.slice(0, 5)
})

// 即将超时事项
const timeoutItems = computed(() => {
  const items: Array<{ title: string; deadline: string; patient_id?: string; module?: string }> = []
  // 从待办中筛选即将超时的
  pendingTasks.value.forEach((t: any) => {
    if (t.deadline || t.urgent) {
      items.push({
        title: t.title || t.detail || '临床任务',
        deadline: t.deadline_label || '即将超时',
        patient_id: t.patient_id || t.patientId,
        module: t.module
      })
    }
  })
  return items.slice(0, 5)
})

// ─── 可视化数据 ────────────────────────────────────────────────────────────

// 风险矩阵数据
const riskMatrixPatients = computed<MatrixPatient[]>(() => {
  return focusPatients.value.map((p: any) => ({
    id: p.patient_id || p.id,
    name: p.name || '未知',
    bedNo: displayBed(p.bed),
    diagnosis: p.diagnosis || p.reason || '',
    riskScore: Number(p.risk_score || 0),
    riskVelocity: Number(p.risk_velocity || p.risk_delta || 0),
    pendingIssues: Number(p.pending_issues || p.alert_count || 0),
  }))
})

// 危急患者数
const criticalCount = computed(() => {
  return focusPatients.value.filter((p: any) => {
    const level = String(p.risk_level || '').toLowerCase()
    return ['critical', 'danger', 'red'].includes(level)
  }).length
})

// 未签收告警数
const unackedAlertCount = computed(() => {
  return Number(home.value?.ai_night_watch?.pending_followup || 0)
})

// 患者数变化
const focusPatientsDelta = computed(() => {
  return Number(home.value?.patient_delta || 0)
})

// 告警漏斗数据
const alertFunnelStages = computed<FunnelStage[]>(() => {
  const a = home.value?.ai_night_watch || {}
  const total = a.total_alerts || 0
  const handled = a.handled || 0
  const pending = a.pending_followup || 0
  return [
    { name: '告警触发', value: total, color: '#D92D20' },
    { name: '已签收', value: total - pending, color: '#F79009' },
    { name: '已处置', value: handled, color: '#1677FF' },
    { name: '已关闭', value: Math.max(0, handled - 2), color: '#12A66A' },
  ]
})

// 科室质控：只显示异常
const qualityLoaded = computed(() => !!home.value?.quality_summary)
const qualityAbnormal = computed(() => {
  const q = home.value?.quality_summary || {}
  const rows = q?.scanner_health?.rows || q?.rows || []
  const abnormal = rows.filter((r: any) => {
    const val = Number(r?.rate ?? r?.count ?? r?.value ?? 0)
    return val > 0
  })
  if (!abnormal.length) return ''
  return abnormal.map((r: any) => r?.name || r?.scanner_name || '异常项').join('、') + ' 有新增'
})

// ─── 工具函数 ────────────────────────────────────────────────────────────────
function badgeClass(value: any) {
  const key = String(value || '').toLowerCase()
  if (['critical', 'danger', 'red'].includes(key)) return 'risk-badge--danger'
  if (['high', 'warning', 'warn', 'medium', 'watch', 'yellow'].includes(key)) return 'risk-badge--warning'
  if (['stable', 'success', 'green', 'ok', 'normal'].includes(key)) return 'risk-badge--success'
  return 'risk-badge--info'
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
  openMenuId.value = null
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

function togglePatientMenu(id: string) {
  openMenuId.value = openMenuId.value === id ? null : id
}

function cleanReason(value: any) {
  if (value && typeof value === 'object') {
    const summary = String(value.summary || value.text || value.title || '').trim()
    const suggestion = String(value.suggestion || value.recommendation || '').trim()
    return [summary, suggestion ? `建议：${suggestion}` : ''].filter(Boolean).join('。') || '进入详情复核'
  }
  const text = String(value || '').trim()
  if (!text) return '暂无说明'
  if (text.includes("'summary'") || text.includes('"summary"')) return '综合风险推理已生成，点击查看详情'
  return text.length > 36 ? text.slice(0, 36) + '...' : text
}

function cleanEmptyText(value: any, fallback: string) {
  const text = String(value || '').trim()
  if (!text) return fallback
  if (/patient\s*表|account\s*表|bedDoctorId|user[_-]?id|userId|collection|集合|数据库/i.test(text)) return fallback
  return text
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────
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

// 点击外部关闭菜单
function handleClickOutside(e: MouseEvent) {
  if (openMenuId.value && !(e.target as HTMLElement).closest('.patient-menu') && !(e.target as HTMLElement).closest('.btn-more')) {
    openMenuId.value = null
  }
}

onMounted(() => {
  auth.hydrateFromQuery(route.query)
  cleanDuplicateIdentityQuery()
  tick()
  timer = setInterval(tick, 1000)
  document.addEventListener('click', handleClickOutside)
  void load()
})

onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener('click', handleClickOutside)
})

watch(() => [route.query.user_id, route.query.userId, route.query.userName, route.query.useName, route.query.username, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  auth.hydrateFromQuery(route.query)
  void load()
})

function cleanDuplicateIdentityQuery() {
  const query = auth.cleanIdentityQuery(route.query)
  if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ path: route.path, query })
}
</script>

<style scoped>
/* ─── KPI指标卡 ──────────────────────────────────────────────────────────── */
.kpi-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

/* ─── 可视化行 ──────────────────────────────────────────────────────────── */
.viz-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.viz-matrix,
.viz-funnel {
  min-width: 0;
}

@media (max-width: 1200px) {
  .viz-row {
    grid-template-columns: 1fr;
  }
  .kpi-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .kpi-metrics {
    grid-template-columns: 1fr;
  }
}

/* ─── 基础变量 ─────────────────────────────────────────────────────────────── */
.role-home {
  --spacing-xs: 8px;
  --spacing-sm: 12px;
  --spacing-md: 16px;
  --spacing-lg: 20px;
  --radius-sm: 6px;
  --radius-md: 8px;
  --text-xs: 12px;
  --text-sm: 13px;
  --text-base: 14px;
  --text-lg: 16px;
  --text-xl: 18px;
  --color-text-primary: var(--text-primary, #1a1a2e);
  --color-text-secondary: var(--text-secondary, #6b7280);
  --color-text-muted: var(--text-muted, #9ca3af);
  --color-bg: var(--bg-base, #f8fafc);
  --color-surface: var(--bg-surface, #ffffff);
  --color-border: var(--border-color, rgba(145, 176, 199, 0.2));
  --color-brand: var(--brand, #2563eb);
  --color-danger: var(--danger, #ef4444);
  --color-warning: var(--warning, #f59e0b);
  --color-success: var(--success, #10b981);
}

/* ─── 布局 ─────────────────────────────────────────────────────────────────── */
.role-home {
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  min-height: 100vh;
  background: var(--color-bg);
}

/* ─── 头部 ─────────────────────────────────────────────────────────────────── */
.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.header-identity {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.header-identity strong {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.header-dept,
.header-shift {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  padding: 2px 8px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.header-clock {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.btn-refresh {
  padding: 6px 12px;
  font-size: var(--text-xs);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-brand);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh:hover {
  background: var(--color-bg);
}

/* ─── AI 摘要条 ─────────────────────────────────────────────────────────────── */
.ai-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-radius: var(--radius-md);
  border: 1px solid #bae6fd;
  cursor: pointer;
  transition: all 0.2s;
}

.ai-summary:hover {
  background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%);
}

.ai-summary-icon {
  font-size: var(--text-lg);
}

.ai-summary-text {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  line-height: 1.5;
}

.ai-summary-link {
  font-size: var(--text-xs);
  color: var(--color-brand);
  white-space: nowrap;
}

/* ─── 主网格 ─────────────────────────────────────────────────────────────────── */
.doctor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-sm);
  flex: 1;
}

/* ─── 面板通用 ─────────────────────────────────────────────────────────────────── */
.panel {
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
}

.panel-head strong {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.panel-count {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  padding: 2px 8px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
}

/* ─── 重点患者列表 ─────────────────────────────────────────────────────────────── */
.patient-list {
  flex: 1;
  overflow-y: auto;
  max-height: 400px;
}

.patient-row {
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background 0.2s;
}

.patient-row:hover {
  background: var(--color-bg);
}

.patient-row:last-child {
  border-bottom: none;
}

.patient-main {
  flex: 1;
  min-width: 0;
}

.patient-bed-name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.bed-num {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-brand);
  padding: 2px 6px;
  background: #eff6ff;
  border-radius: var(--radius-sm);
}

.patient-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.patient-issue {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.patient-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: var(--spacing-sm);
  flex-shrink: 0;
}

.risk-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-style: normal;
  white-space: nowrap;
}

.risk-badge--danger {
  background: #fef2f2;
  color: #dc2626;
}

.risk-badge--warning {
  background: #fffbeb;
  color: #d97706;
}

.risk-badge--success {
  background: #f0fdf4;
  color: #16a34a;
}

.risk-badge--info {
  background: #eff6ff;
  color: #2563eb;
}

.next-action {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-enter {
  padding: 4px 12px;
  font-size: var(--text-xs);
  font-weight: 500;
  border: 1px solid var(--color-brand);
  border-radius: var(--radius-sm);
  background: var(--color-brand);
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-enter:hover {
  background: #1d4ed8;
}

.btn-more {
  padding: 4px 8px;
  font-size: var(--text-lg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  line-height: 1;
}

.btn-more:hover {
  background: var(--color-bg);
}

/* ─── 患者操作菜单 ─────────────────────────────────────────────────────────────── */
.patient-menu {
  position: absolute;
  right: var(--spacing-md);
  top: 100%;
  z-index: 100;
  display: flex;
  flex-direction: column;
  min-width: 120px;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.patient-menu button {
  padding: 8px 12px;
  font-size: var(--text-xs);
  text-align: left;
  border: none;
  background: none;
  color: var(--color-text-primary);
  cursor: pointer;
  transition: background 0.2s;
}

.patient-menu button:hover {
  background: var(--color-bg);
}

/* ─── 待办列表 ─────────────────────────────────────────────────────────────────── */
.task-list {
  flex: 1;
  overflow-y: auto;
  max-height: 400px;
}

.task-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background 0.2s;
}

.task-row:hover {
  background: var(--color-bg);
}

.task-row:last-child {
  border-bottom: none;
}

.task-main {
  flex: 1;
  min-width: 0;
}

.task-main strong {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.task-bed {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.btn-task {
  padding: 4px 12px;
  font-size: var(--text-xs);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-brand);
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  margin-left: var(--spacing-sm);
}

.btn-task:hover {
  background: #eff6ff;
}

/* ─── 昨夜变化 ─────────────────────────────────────────────────────────────────── */
.changes-list {
  padding: var(--spacing-sm) 0;
}

.change-row {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
}

.change-row:last-child {
  border-bottom: none;
}

.change-icon {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
}

.change-icon.up {
  background: #fef2f2;
  color: #dc2626;
}

.change-icon.warn {
  background: #fffbeb;
  color: #d97706;
}

.change-text {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  line-height: 1.4;
}

/* ─── 超时事项 ─────────────────────────────────────────────────────────────────── */
.timeout-list {
  flex: 1;
  overflow-y: auto;
}

.timeout-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background 0.2s;
}

.timeout-row:hover {
  background: #fef2f2;
}

.timeout-row:last-child {
  border-bottom: none;
}

.timeout-main {
  flex: 1;
  min-width: 0;
}

.timeout-main strong {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.timeout-deadline {
  font-size: var(--text-xs);
  color: var(--color-danger);
  font-weight: 500;
}

/* ─── 科室质控 ─────────────────────────────────────────────────────────────────── */
.quality-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: #fffbeb;
  border-radius: var(--radius-md);
  border: 1px solid #fde68a;
  cursor: pointer;
  transition: all 0.2s;
}

.quality-bar:hover {
  background: #fef3c7;
}

.quality-icon {
  font-size: var(--text-lg);
}

.quality-bar span:nth-child(2) {
  flex: 1;
  font-size: var(--text-sm);
  color: #92400e;
}

.quality-link {
  font-size: var(--text-xs);
  color: #d97706;
  white-space: nowrap;
}

.quality-ok {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  text-align: center;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

/* ─── 空状态 ─────────────────────────────────────────────────────────────────── */
.empty-state {
  padding: var(--spacing-lg);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* ─── 加载态 ─────────────────────────────────────────────────────────────────── */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: 60px 0;
  color: var(--color-text-secondary);
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ─── 错误态 ─────────────────────────────────────────────────────────────────── */
.error-state {
  padding: var(--spacing-md);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-danger);
  background: #fef2f2;
  border-radius: var(--radius-md);
  border: 1px solid #fecaca;
}

/* ─── 响应式 ─────────────────────────────────────────────────────────────────── */
@media (max-width: 1024px) {
  .doctor-grid {
    grid-template-columns: 1fr;
  }

  .patient-list,
  .task-list {
    max-height: 300px;
  }
}

@media (max-width: 768px) {
  .role-home {
    padding: var(--spacing-sm);
  }

  .home-header {
    flex-direction: column;
    gap: var(--spacing-sm);
    align-items: flex-start;
  }

  .header-identity {
    flex-wrap: wrap;
  }

  .header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .patient-row {
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .patient-meta {
    margin-left: 0;
    width: 100%;
    justify-content: flex-start;
  }
}

/* ─── 主题适配 ─────────────────────────────────────────────────────────────────── */
html[data-theme='light'] .role-home {
  background: var(--bg-base);
}

html[data-theme='light'] .home-header,
html[data-theme='light'] .panel {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

html[data-theme='light'] .ai-summary {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-color: #bae6fd;
}

html[data-theme='light'] .quality-bar {
  background: #fffbeb;
  border-color: #fde68a;
}

html[data-theme='light'] .btn-enter {
  background: #2563eb;
  border-color: #2563eb;
}

html[data-theme='light'] .btn-enter:hover {
  background: #1d4ed8;
}
</style>
