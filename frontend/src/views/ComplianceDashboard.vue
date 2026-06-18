<template>
  <section class="compliance-dashboard">
    <div class="dashboard-header">
      <strong>护理依从性看板</strong>
      <div class="header-actions">
        <select v-model="selectedShift" @change="load">
          <option value="auto">当前班次</option>
          <option value="morning">早班</option>
          <option value="afternoon">中班</option>
          <option value="night">晚班</option>
        </select>
        <button type="button" @click="load" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div v-if="loading && !dashboard" class="loading">正在加载依从性数据...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="dashboard">
      <!-- 概览卡片 -->
      <div class="overview-cards">
        <div class="overview-card" :class="complianceTone">
          <span>当前班次依从率</span>
          <strong>{{ current.compliance_rate }}%</strong>
          <em>{{ dashboard.compliance_overview?.trend || '0%' }} 较上班</em>
        </div>
        <div class="overview-card" :class="overdueTone">
          <span>当前逾期</span>
          <strong>{{ current.total_overdue }} 项</strong>
          <em>逾期率 {{ current.overdue_rate }}%</em>
        </div>
        <div class="overview-card">
          <span>已完成</span>
          <strong>{{ current.total_completed }}/{{ current.total_expected }}</strong>
          <em>本班应评估</em>
        </div>
        <div class="overview-card">
          <span>平均响应</span>
          <strong>{{ current.avg_response_minutes }} 分钟</strong>
          <em>从逾期到完成</em>
        </div>
      </div>

      <!-- 时间线热力图 -->
      <div class="section">
        <div class="section-header">
          <strong>依从率时间线</strong>
          <span class="legend">
            <span class="legend-item good">≥80%</span>
            <span class="legend-item warn">60-80%</span>
            <span class="legend-item bad">&lt;60%</span>
            <span class="legend-item empty">无数据</span>
          </span>
        </div>
        <div class="heatmap-container">
          <div v-if="!heatmap.length" class="empty">暂无时间线数据</div>
          <div v-else class="heatmap">
            <div class="heatmap-header">
              <div class="heatmap-label">时间</div>
              <div v-for="type in heatmapTypes" :key="type" class="heatmap-type-label">
                {{ type }}
              </div>
            </div>
            <div v-for="row in heatmap" :key="row.hour" class="heatmap-row">
              <div class="heatmap-hour">{{ row.hour }}</div>
              <div
                v-for="type in heatmapTypes"
                :key="`${row.hour}-${type}`"
                class="heatmap-cell"
                :class="getCellClass(row.by_type, type)"
                :title="getCellTooltip(row.by_type, type, row.hour)"
              >
                {{ getCellRate(row.by_type, type) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 逾期 TOP 床位 -->
      <div class="section">
        <div class="section-header">
          <strong>逾期 TOP 床位</strong>
          <span>当前逾期最多的患者</span>
        </div>
        <div v-if="!overdueTopBeds.length" class="empty">暂无逾期患者</div>
        <div v-else class="overdue-list">
          <div
            v-for="bed in overdueTopBeds"
            :key="bed.patient_id"
            class="overdue-item"
            :class="severityClass(bed.worst_severity)"
            @click="goPatient(bed.patient_id)"
          >
            <div class="overdue-bed">
              <strong>{{ displayBed(bed.bed) }}</strong>
              <span>{{ bed.name || '未知患者' }}</span>
            </div>
            <div class="overdue-detail">
              <span class="overdue-count">{{ bed.overdue_count }} 项逾期</span>
              <div class="overdue-types">
                <span
                  v-for="t in bed.overdue_types"
                  :key="t"
                  class="type-tag"
                >
                  {{ scoreTypeLabel(t) }}
                </span>
              </div>
            </div>
            <div class="overdue-time">
              最早逾期: {{ fmt(bed.latest_due_at) }}
            </div>
          </div>
        </div>
      </div>

      <!-- 班次对比 -->
      <div class="section">
        <div class="section-header">
          <strong>班次对比</strong>
          <span>当前班 vs 上班</span>
        </div>
        <div v-if="!byTypeComparison.length" class="empty">暂无对比数据</div>
        <div v-else class="comparison-list">
          <div v-for="item in byTypeComparison" :key="item.score_type" class="comparison-item">
            <div class="comparison-header">
              <strong>{{ item.label }}</strong>
              <span class="interval">每{{ item.interval_hours }}h</span>
            </div>
            <div class="comparison-bars">
              <div class="bar-row">
                <span class="bar-label">当前班</span>
                <div class="bar-track">
                  <div
                    class="bar-fill current"
                    :style="{ width: `${item.current?.compliance_rate || 0}%` }"
                  ></div>
                </div>
                <span class="bar-value">{{ item.current?.compliance_rate || 0 }}%</span>
              </div>
              <div class="bar-row">
                <span class="bar-label">上班</span>
                <div class="bar-track">
                  <div
                    class="bar-fill previous"
                    :style="{ width: `${item.previous?.compliance_rate || 0}%` }"
                  ></div>
                </div>
                <span class="bar-value">{{ item.previous?.compliance_rate || 0 }}%</span>
              </div>
            </div>
            <div class="comparison-stats">
              <span>当前: {{ item.current?.completed || 0 }}/{{ item.current?.expected || 0 }}</span>
              <span>逾期: {{ item.current?.overdue || 0 }}</span>
              <span :class="trendClass(item.trend)">{{ item.trend }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getComplianceDashboard } from '../api'

const props = defineProps<{
  userId: string
  deptCode?: string
  dept?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const dashboard = ref<any>(null)
const selectedShift = ref('auto')

const current = computed(() => dashboard.value?.compliance_overview?.current_shift || {})
const heatmap = computed(() => dashboard.value?.heatmap || [])
const overdueTopBeds = computed(() => dashboard.value?.overdue_top_beds || [])
const byTypeComparison = computed(() => dashboard.value?.by_type_comparison || [])

const heatmapTypes = computed(() => {
  const types = new Set<string>()
  for (const row of heatmap.value) {
    for (const item of row.by_type || []) {
      types.add(item.label)
    }
  }
  return Array.from(types)
})

const complianceTone = computed(() => {
  const rate = current.value?.compliance_rate || 0
  if (rate >= 80) return 'good'
  if (rate >= 60) return 'warn'
  return 'bad'
})

const overdueTone = computed(() => {
  const count = current.value?.total_overdue || 0
  if (count === 0) return 'good'
  if (count <= 3) return 'warn'
  return 'bad'
})

function getCellClass(byType: any[], type: string) {
  const item = byType?.find(t => t.label === type)
  if (!item) return 'empty'
  const rate = item.compliance_rate
  if (rate >= 80) return 'good'
  if (rate >= 60) return 'warn'
  return 'bad'
}

function getCellRate(byType: any[], type: string) {
  const item = byType?.find(t => t.label === type)
  return item ? `${item.compliance_rate}%` : '-'
}

function getCellTooltip(byType: any[], type: string, hour: string) {
  const item = byType?.find(t => t.label === type)
  if (!item) return `${hour} ${type}: 无数据`
  return `${hour} ${type}\n依从率: ${item.compliance_rate}%\n完成: ${item.completed}/${item.total}\n逾期: ${item.overdue}`
}

function scoreTypeLabel(type: string) {
  const labels: Record<string, string> = {
    assessment: '评估',
    turning: '翻身',
    cam_icu: 'CAM-ICU',
    early_mobility: '早期活动',
    gcs: 'GCS',
    rass: 'RASS',
    pain: '疼痛',
    cpot: 'CPOT',
    bps: 'BPS',
    delirium: '谵妄',
    braden: 'Braden',
  }
  return labels[type] || type
}

function severityClass(severity: string) {
  if (severity === 'critical') return 'severity-critical'
  if (severity === 'high') return 'severity-high'
  return 'severity-warning'
}

function trendClass(trend: string) {
  if (trend.startsWith('+')) return 'trend-up'
  if (trend.startsWith('-')) return 'trend-down'
  return ''
}

function displayBed(value: any) {
  const text = String(value || '').trim()
  if (!text || text === '--') return '--床'
  return text.includes('床') ? text : `${text}床`
}

function fmt(value: any) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function goPatient(patientId: string) {
  if (patientId) {
    router.push({ path: `/patient/${patientId}`, query: route.query })
  }
}

async function load() {
  if (!props.userId) {
    error.value = '未识别当前账号。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const params: any = {
      user_id: props.userId,
      shift_code: selectedShift.value,
    }
    if (props.deptCode) params.dept_code = props.deptCode
    else if (props.dept) params.dept = props.dept
    const { data } = await getComplianceDashboard(params)
    dashboard.value = data?.data || {}
  } catch (err: any) {
    error.value = err?.message || '依从性看板加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

watch(() => [props.userId, props.deptCode, props.dept], () => {
  void load()
})
</script>

<style scoped>
.compliance-dashboard {
  display: grid;
  gap: 16px;
  padding: 16px;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dashboard-header strong {
  color: #1D2129;
  font-size: 18px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.header-actions select {
  min-height: 36px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid rgba(125, 211, 252, .2);
  background: #15558D;
  color: #1D2129;
}

.header-actions button {
  min-height: 36px;
  padding: 0 12px;
  border-radius: 6px;
  border: 1px solid rgba(125, 211, 252, .2);
  background: #15558D;
  color: #1D2129;
  cursor: pointer;
}

.header-actions button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading, .error, .empty {
  padding: 20px;
  text-align: center;
  border-radius: 4px;
  background: #FFFFFF;
  color: #4E5969;
}

.error {
  color: #D9342B;
}

.overview-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.overview-card {
  padding: 16px;
  border-radius: 4px;
  background: #FFFFFF;
  border: 1px solid rgba(125, 211, 252, .14);
}

.overview-card span {
  color: #4E5969;
  font-size: 12px;
  display: block;
}

.overview-card strong {
  color: #1D2129;
  font-size: 28px;
  display: block;
  margin: 8px 0 4px;
}

.overview-card em {
  color: #4E5969;
  font-size: 11px;
  font-style: normal;
}

.overview-card.good {
  border-color: rgba(52, 211, 153, .34);
}

.overview-card.warn {
  border-color: rgba(245, 158, 11, .42);
}

.overview-card.bad {
  border-color: rgba(239, 68, 68, .42);
}

.section {
  background: #FFFFFF;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: 4px;
  padding: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header strong {
  color: #1D2129;
  font-size: 15px;
}

.section-header span {
  color: #4E5969;
  font-size: 12px;
}

.legend {
  display: flex;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}

.legend-item::before {
  content: '';
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.legend-item.good::before {
  background: #34d399;
}

.legend-item.warn::before {
  background: #fbbf24;
}

.legend-item.bad::before {
  background: #ef4444;
}

.legend-item.empty::before {
  background: rgba(148, 163, 184, .25);
}

.heatmap-container {
  overflow-x: auto;
}

.heatmap {
  min-width: 500px;
}

.heatmap-header {
  display: grid;
  grid-template-columns: 80px repeat(auto-fit, minmax(80px, 1fr));
  gap: 4px;
  margin-bottom: 4px;
}

.heatmap-label {
  color: #4E5969;
  font-size: 11px;
  display: flex;
  align-items: center;
}

.heatmap-type-label {
  color: #4E5969;
  font-size: 11px;
  text-align: center;
  padding: 4px;
}

.heatmap-row {
  display: grid;
  grid-template-columns: 80px repeat(auto-fit, minmax(80px, 1fr));
  gap: 4px;
  margin-bottom: 4px;
}

.heatmap-hour {
  color: #4E5969;
  font-size: 12px;
  display: flex;
  align-items: center;
}

.heatmap-cell {
  padding: 8px;
  border-radius: 4px;
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  cursor: default;
  transition: transform 0.1s;
}

.heatmap-cell:hover {
  transform: scale(1.05);
}

.heatmap-cell.good {
  background: rgba(52, 211, 153, .3);
  color: #34d399;
}

.heatmap-cell.warn {
  background: rgba(251, 191, 36, .3);
  color: #fbbf24;
}

.heatmap-cell.bad {
  background: rgba(239, 68, 68, .3);
  color: #ef4444;
}

.heatmap-cell.empty {
  background: rgba(148, 163, 184, .1);
  color: rgba(148, 163, 184, .5);
}

.overdue-list {
  display: grid;
  gap: 8px;
}

.overdue-item {
  display: grid;
  grid-template-columns: 150px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border-radius: 4px;
  background: #FFFFFF;
  cursor: pointer;
  transition: background 0.2s;
}

.overdue-item:hover {
  background: rgba(11, 33, 50, .9);
}

.overdue-item.severity-critical {
  border-left: 3px solid #ef4444;
}

.overdue-item.severity-high {
  border-left: 3px solid #f97316;
}

.overdue-item.severity-warning {
  border-left: 3px solid #eab308;
}

.overdue-bed strong {
  color: #1D2129;
  font-size: 16px;
  display: block;
}

.overdue-bed span {
  color: #4E5969;
  font-size: 12px;
}

.overdue-detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.overdue-count {
  color: #1D2129;
  font-size: 13px;
}

.overdue-types {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.type-tag {
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(125, 211, 252, .15);
  color: #4E5969;
  font-size: 11px;
}

.overdue-time {
  color: #4E5969;
  font-size: 11px;
  text-align: right;
}

.comparison-list {
  display: grid;
  gap: 12px;
}

.comparison-item {
  padding: 12px;
  border-radius: 4px;
  background: #FFFFFF;
}

.comparison-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.comparison-header strong {
  color: #1D2129;
  font-size: 14px;
}

.interval {
  color: #4E5969;
  font-size: 11px;
}

.comparison-bars {
  display: grid;
  gap: 6px;
  margin-bottom: 8px;
}

.bar-row {
  display: grid;
  grid-template-columns: 50px 1fr 50px;
  gap: 8px;
  align-items: center;
}

.bar-label {
  color: #4E5969;
  font-size: 11px;
}

.bar-track {
  height: 20px;
  border-radius: 4px;
  background: rgba(148, 163, 184, .15);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.bar-fill.current {
  background: #FFFFFF;
}

.bar-fill.previous {
  background: rgba(148, 163, 184, .4);
}

.bar-value {
  color: #1D2129;
  font-size: 12px;
  text-align: right;
}

.comparison-stats {
  display: flex;
  gap: 12px;
}

.comparison-stats span {
  color: #4E5969;
  font-size: 11px;
}

.trend-up {
  color: #34d399 !important;
}

.trend-down {
  color: #ef4444 !important;
}

@media (max-width: 768px) {
  .overview-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .overdue-item {
    grid-template-columns: 1fr;
  }

  .overdue-time {
    text-align: left;
  }
}

/* Light theme */
html[data-theme='light'] .compliance-dashboard {
  background: transparent;
}

html[data-theme='light'] .dashboard-header strong,
html[data-theme='light'] .section-header strong,
html[data-theme='light'] .overview-card strong,
html[data-theme='light'] .comparison-header strong,
html[data-theme='light'] .overdue-bed strong,
html[data-theme='light'] .overdue-count,
html[data-theme='light'] .bar-value {
  color: #1D2129;
}

html[data-theme='light'] .overview-card,
html[data-theme='light'] .section {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
}

html[data-theme='light'] .overdue-item,
html[data-theme='light'] .comparison-item {
  background: #f8fafc;
}

html[data-theme='light'] .header-actions select,
html[data-theme='light'] .header-actions button {
  background: #eff6ff;
  border-color: rgba(37, 99, 235, 0.18);
  color: #15558D;
}

html[data-theme='light'] .heatmap-cell.good {
  background: rgba(52, 211, 153, .2);
  color: #059669;
}

html[data-theme='light'] .heatmap-cell.warn {
  background: rgba(251, 191, 36, .2);
  color: #d97706;
}

html[data-theme='light'] .heatmap-cell.bad {
  background: rgba(239, 68, 68, .2);
  color: #dc2626;
}

html[data-theme='light'] .bar-fill.current {
  background: #FFFFFF;
}

html[data-theme='light'] .bar-fill.previous {
  background: rgba(148, 163, 184, .3);
}

html[data-theme='light'] .loading,
html[data-theme='light'] .error,
html[data-theme='light'] .empty {
  background: #f8fafc;
  color: #4E5969;
}

html[data-theme='light'] .error {
  color: #dc2626;
}
</style>
