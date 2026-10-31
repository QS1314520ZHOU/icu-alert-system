<template>
  <section class="role-home doctor-home">
    <!-- 页面头部：身份、班次、时钟与刷新 -->
    <PageHeader title="医生首页" :subtitle="`${home?.account?.dept || '科室待识别'} · ${shiftText}`">
      <template #actions>
        <span class="header-meta">{{ accountName }}</span>
        <span class="header-clock">{{ clock }}</span>
        <a-button size="small" @click="load">刷新</a-button>
      </template>
    </PageHeader>

    <!-- 加载态 -->
    <LoadingState v-if="loading" message="正在加载..." />

    <!-- 错误态 -->
    <ErrorState v-else-if="error" :description="error" />

    <!-- 主内容 -->
    <template v-else>
      <!-- 床位临床概览：结论先行，数据来自本班统计与实时体征 -->
      <WardClinicalBoard
        :title="managedIds.length ? '我的分管患者' : '科室患者概览'"
        :patient-ids="managedIds"
        :scope-label="managedIds.length ? '分管患者' : '在科患者'"
      />

      <!-- 昨夜AI摘要：一句话自然语言 -->
      <section v-if="aiSummary" class="ai-summary" @click="$router.push({ path: '/clinical-workflow', query: route.query })">
        <span class="ai-summary-text">{{ aiSummary }}</span>
        <span class="ai-summary-link">查看详情 →</span>
      </section>

      <!-- 主网格：4个核心区域 -->
      <main class="doctor-grid">
        <!-- 1. 我的重点患者 -->
        <section v-if="sortedFocusPatients.length" class="panel focus-panel">
          <div class="panel-head">
            <strong>综合风险推理提示</strong>
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
                <a-button size="small" type="primary" @click.stop="goPatient(item.patient_id)">进入</a-button>
                <a-button size="small" class="btn-more" @click.stop="togglePatientMenu(item.patient_id)">⋯</a-button>
              </div>
              <!-- 更多操作菜单 -->
              <div v-if="openMenuId === item.patient_id" class="patient-menu" @click.stop>
                <button type="button" @click="goPatientTab(item.patient_id, 'alerts')">处理告警</button>
                <button type="button" @click="goPatientTab(item.patient_id, 'ai')">查房摘要</button>
                <button type="button" @click="goPatientTab(item.patient_id, 'documents')">病历文书</button>
              </div>
            </article>
            <EmptyState v-if="!sortedFocusPatients.length" :description="doctorEmptyText" />
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
              <a-button size="small" @click.stop="goTask(item)">处理</a-button>
            </article>
            <EmptyState v-if="!pendingTasks.length" description="暂无待办" />
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
          <EmptyState v-else description="昨夜无重要变化" />
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
              <a-button size="small" @click.stop="goTask(item)">处理</a-button>
            </article>
          </div>
          <EmptyState v-else description="暂无超时风险" />
        </section>
      </main>

      <!-- 科室质控：只显示异常项 -->
      <section v-if="qualityAbnormal" class="quality-bar" @click="$router.push('/analytics')">
        <span class="quality-icon">!</span>
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
import { Button as AButton } from 'ant-design-vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDoctorHome } from '../api'
import { useAuthStore } from '../stores/auth'
import { formatRiskLevelLabel } from '../utils/displayLabels'
import { PageHeader, LoadingState, ErrorState, EmptyState } from '../components/common/design-system'
import WardClinicalBoard from '../components/home/WardClinicalBoard.vue'

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
const managedIds = computed<string[]>(() => (home.value?.managed_patient_ids || []).map(String))
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
      icon: '!',
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
/* ─── 布局 ─────────────────────────────────────────────────────────────────── */
.role-home {
  padding: var(--page-padding);
  padding-bottom: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--element-gap-lg);
  min-height: 100vh;
  background: var(--color-bg-page);
}

/* ─── 头部辅助文字 ─────────────────────────────────────────────────────────── */
.header-meta {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}

.header-clock {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

/* ─── 可视化行 ─────────────────────────────────────────────────────────────── */
.viz-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 14px;
}

.viz-matrix,
.viz-funnel {
  min-width: 0;
}

/* ─── AI 摘要条 ─────────────────────────────────────────────────────────────── */
.ai-summary {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--color-ai-light);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  cursor: pointer;
  transition: border-color 0.15s;
}

.ai-summary:hover {
  border-color: var(--color-ai);
}

.ai-summary-icon {
  font-size: var(--text-section-title);
}

.ai-summary-text {
  flex: 1;
  font-size: var(--text-body);
  color: var(--color-text-primary);
  line-height: var(--text-body-line-height);
}

.ai-summary-link {
  font-size: var(--text-caption);
  color: var(--color-ai);
  white-space: nowrap;
}

/* ─── 主网格 ─────────────────────────────────────────────────────────────────── */
.doctor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  flex: 1;
}

/* ─── 面板通用 ─────────────────────────────────────────────────────────────────── */
.panel {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-divider);
}

.panel-head strong {
  font-size: var(--text-card-title);
  font-weight: var(--text-card-title-weight);
  color: var(--color-text-primary);
}

.panel-count {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  padding: 2px 8px;
  background: var(--color-bg-surface-secondary);
  border-radius: 999px;
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
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-divider);
  cursor: pointer;
  transition: background 0.15s;
}

.patient-row:hover {
  background: var(--color-bg-inset);
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
  gap: var(--space-2);
  margin-bottom: 4px;
}

.bed-num {
  font-size: var(--text-body);
  font-weight: var(--weight-semibold);
  color: var(--color-primary);
  padding: 2px 6px;
  background: var(--color-primary-bg);
  border-radius: var(--radius-tag);
}

.patient-name {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--color-text-primary);
}

.patient-issue {
  font-size: var(--text-caption);
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
  gap: var(--space-2);
  margin-left: var(--space-3);
  flex-shrink: 0;
}

.risk-badge {
  font-size: var(--text-caption);
  font-weight: var(--weight-medium);
  padding: 2px 8px;
  border-radius: 999px;
  font-style: normal;
  white-space: nowrap;
}

.risk-badge--danger {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.risk-badge--warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.risk-badge--success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.risk-badge--info {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.next-action {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ─── 患者操作菜单 ─────────────────────────────────────────────────────────────── */
.patient-menu {
  position: absolute;
  right: var(--space-4);
  top: 100%;
  z-index: 100;
  display: flex;
  flex-direction: column;
  min-width: 120px;
  background: var(--color-bg-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.patient-menu button {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-caption);
  text-align: left;
  border: none;
  background: none;
  color: var(--color-text-primary);
  cursor: pointer;
  transition: background 0.15s;
}

.patient-menu button:hover {
  background: var(--color-bg-inset);
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
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-divider);
  cursor: pointer;
  transition: background 0.15s;
}

.task-row:hover {
  background: var(--color-bg-inset);
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
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.task-bed {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}

.task-row :deep(.ant-btn),
.timeout-row :deep(.ant-btn) {
  flex-shrink: 0;
}

/* ─── 昨夜变化 ─────────────────────────────────────────────────────────────────── */
.changes-list {
  padding: var(--space-3) 0;
}

.change-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-divider);
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
  font-size: var(--text-caption);
}

.change-icon.up {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.change-icon.warn {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.change-text {
  font-size: var(--text-body);
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
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-divider);
  cursor: pointer;
  transition: background 0.15s;
}

.timeout-row:hover {
  background: var(--color-danger-bg);
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
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.timeout-deadline {
  font-size: var(--text-caption);
  color: var(--color-danger);
  font-weight: 500;
}

/* ─── 科室质控 ─────────────────────────────────────────────────────────────────── */
.quality-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-warning-soft-bg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-warning-soft-border);
  cursor: pointer;
  transition: border-color 0.15s;
}

.quality-bar:hover {
  border-color: var(--color-warning);
}

.quality-icon {
  font-size: var(--text-section-title);
}

.quality-bar span:nth-child(2) {
  flex: 1;
  font-size: var(--text-body);
  color: var(--color-warning);
}

.quality-link {
  font-size: var(--text-caption);
  color: var(--color-warning);
  white-space: nowrap;
}

.quality-ok {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-body);
  color: var(--color-text-secondary);
  text-align: center;
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
}

/* ─── 面板内空态保持紧凑 ───────────────────────────────────────────────────────── */
.panel :deep(.empty-state) {
  padding: 24px 16px;
}

/* ─── 响应式 ─────────────────────────────────────────────────────────────────── */
@media (max-width: 1200px) {
  .viz-row {
    grid-template-columns: 1fr;
  }
}

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
    padding: var(--space-3);
  }

  .patient-row {
    flex-direction: column;
    gap: var(--space-3);
  }

  .patient-meta {
    margin-left: 0;
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
