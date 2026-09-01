<template>
  <div class="disease-overview-page">
    <!-- KPI 统计行 -->
    <div class="kpi-row">
      <div v-for="kpi in kpiCards" :key="kpi.key" class="kpi-card">
        <div class="kpi-content">
          <span class="kpi-value">{{ kpi.value }}</span>
          <span class="kpi-label">{{ kpi.label }}</span>
        </div>
        <span class="kpi-icon" :style="{ background: kpi.iconBg }">{{ kpi.icon }}</span>
      </div>
    </div>

    <!-- 质量指标行 -->
    <div class="kpi-row" v-if="qualityMetrics">
      <div v-for="qm in qualityCards" :key="qm.key" class="kpi-card">
        <div class="kpi-content">
          <span class="kpi-value">{{ qm.value }}</span>
          <span class="kpi-label">{{ qm.label }}</span>
        </div>
        <span class="kpi-icon" :style="{ background: qm.iconBg }">{{ qm.icon }}</span>
      </div>
    </div>

    <!-- 图表行 -->
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-title">
          <span>病例漏斗</span>
          <span class="chart-subtitle">筛查 → 阳性 → 待确认 → 纳入 → 路径 → 完成</span>
        </div>
        <v-chart v-if="funnelOption" :option="funnelOption" :style="{ height: '300px' }" autoresize />
        <a-empty v-else description="暂无漏斗数据" />
      </div>
      <div class="chart-card">
        <div class="chart-title">
          <span>病例趋势</span>
          <span class="chart-subtitle">最近 30 天</span>
        </div>
        <v-chart v-if="trendOption" :option="trendOption" :style="{ height: '300px' }" autoresize />
        <a-empty v-else description="暂无趋势数据" />
      </div>
    </div>

    <!-- 二次图表行 -->
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-title">
          <span>风险等级分布</span>
          <span class="chart-subtitle">当前活跃病例</span>
        </div>
        <v-chart v-if="riskOption" :option="riskOption" :style="{ height: '300px' }" autoresize />
        <a-empty v-else description="暂无风险数据" />
      </div>
      <div class="chart-card">
        <div class="chart-title">
          <span>状态分布</span>
          <span class="chart-subtitle">各状态病例数</span>
        </div>
        <v-chart v-if="statusOption" :option="statusOption" :style="{ height: '300px' }" autoresize />
        <a-empty v-else description="暂无状态数据" />
      </div>
    </div>

    <!-- 待审病例 -->
    <div class="section-card">
      <div class="section-header">
        <span class="section-title">待临床确认病例</span>
        <a-button type="link" @click="goCases">查看全部 →</a-button>
      </div>
      <a-table
        :columns="pendingColumns"
        :data-source="pendingCases"
        :loading="pendingLoading"
        :pagination="false"
        row-key="id"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'patient_id'">
            <a @click="goCaseDetail(record.id)">{{ record.patient_id }}</a>
          </template>
          <template v-if="column.key === 'disease_name'">
            <a-tag color="var(--color-primary-light, #e6f7f5)">
              <span style="color: var(--color-primary)">{{ record.disease_name || record.disease_code }}</span>
            </a-tag>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag color="var(--color-primary-light)">待临床确认</a-tag>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space>
              <a-button type="link" size="small" @click="goCaseDetail(record.id)">详情</a-button>
              <a-button type="link" size="small" @click="handleConfirm(record)">确认</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
      <a-empty v-if="!pendingLoading && pendingCases.length === 0" description="暂无待临床确认病例" />
    </div>

    <!-- 快速确认对话框 -->
    <a-modal
      v-model:open="confirmModalVisible"
      title="确认纳入病例"
      @ok="handleConfirmSubmit"
      @cancel="confirmModalVisible = false"
      :confirm-loading="confirmLoading"
    >
      <a-form layout="vertical">
        <a-form-item label="患者 ID">
          <a-input :value="confirmTarget?.patient_id" disabled />
        </a-form-item>
        <a-form-item label="确认原因" required>
          <a-textarea
            v-model:value="confirmReason"
            placeholder="请输入确认原因（必填）"
            :rows="3"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import VChart from 'vue-echarts'
import {
  getDashboard,
  getGlobalFunnel,
  getAllCases,
  confirmCase,
} from '@/api/diseaseCenter'
import type { DashboardData, DiseaseCase, FunnelData } from '@/api/diseaseCenter'

const router = useRouter()

// --- state ---
const dashboard = ref<DashboardData | null>(null)
const funnelData = ref<FunnelData | null>(null)
const pendingCases = ref<DiseaseCase[]>([])
const pendingLoading = ref(false)
const kpiLoading = ref(false)

// --- KPI ---
const kpiCards = computed(() => {
  const d = dashboard.value
  if (!d) {
    return [
      { key: 'diseases', label: '疾病数', value: '-', icon: '📁', iconBg: 'rgba(29,111,99,0.1)' },
      { key: 'today', label: '今日新增', value: '-', icon: '🆕', iconBg: 'rgba(59,130,246,0.1)' },
      { key: 'pending', label: '待临床确认', value: '-', icon: '⏳', iconBg: 'rgba(217,45,32,0.1)' },
      { key: 'active', label: '路径执行中', value: '-', icon: '🚀', iconBg: 'rgba(22,132,91,0.1)' },
    ]
  }
  return [
    { key: 'diseases', label: '疾病数', value: d.disease_count ?? d.disease_total ?? 0, icon: '📁', iconBg: 'rgba(29,111,99,0.1)' },
    { key: 'today', label: '今日新增', value: d.today_new ?? d.today_new_cases ?? 0, icon: '🆕', iconBg: 'rgba(59,130,246,0.1)' },
    { key: 'pending', label: '待临床确认', value: d.pending_review ?? 0, icon: '⏳', iconBg: 'rgba(217,45,32,0.1)' },
    { key: 'active', label: '路径执行中', value: d.pathway_active ?? d.active_cases ?? 0, icon: '🚀', iconBg: 'rgba(22,132,91,0.1)' },
  ]
})

const qualityMetrics = computed(() => dashboard.value?.quality_metrics ?? null)

const qualityCards = computed(() => {
  const q = qualityMetrics.value
  if (!q) return []
  const pct = (v: number) => `${(v * 100).toFixed(1)}%`
  return [
    { key: 'confirm_rate', label: '纳入确认率', value: pct(q.confirmation_rate), icon: '✅', iconBg: 'rgba(22,132,91,0.1)' },
    { key: 'exclude_rate', label: '排除率', value: pct(q.exclusion_rate), icon: '❌', iconBg: 'rgba(217,45,32,0.1)' },
    { key: 'pathway_start', label: '路径启动率', value: pct(q.pathway_start_rate), icon: '📋', iconBg: 'rgba(59,130,246,0.1)' },
    { key: 'pathway_complete', label: '路径完成率', value: pct(q.pathway_completion_rate), icon: '🏁', iconBg: 'rgba(22,132,91,0.1)' },
  ]
})

// --- Funnel Chart ---
const funnelOption = computed(() => {
  const f = funnelData.value
  if (!f || !f.stages || f.stages.length === 0) return null
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    color: ['#1D6F63', '#2A9D8F', '#3BB5A0', '#5CC4B4', '#7DD3C8', '#9EE2DA'],
    series: [{
      type: 'funnel',
      left: '10%',
      width: '80%',
      sort: 'descending',
      gap: 2,
      label: { show: true, position: 'inside', formatter: '{b}\n{c}' },
      data: f.stages.map((item: any) => ({
        name: item.label,
        value: item.count,
      })),
    }],
  }
})

// --- Trend Chart ---
const trendOption = computed(() => {
  const d = dashboard.value
  const trend = d?.case_trend
  if (!trend || trend.length === 0) return null
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trend.map((t: any) => t._id) },
    yAxis: { type: 'value', name: '病例数' },
    series: [
      {
        name: '总病例',
        type: 'line',
        data: trend.map((t: any) => t.total),
        smooth: true,
        areaStyle: { color: 'rgba(29,111,99,0.1)' },
        lineStyle: { color: '#1D6F63' },
        itemStyle: { color: '#1D6F63' },
      },
      {
        name: '已确诊',
        type: 'line',
        data: trend.map((t: any) => t.confirmed),
        smooth: true,
        lineStyle: { color: '#2A9D8F' },
        itemStyle: { color: '#2A9D8F' },
      },
    ],
  }
})

// --- Risk Distribution ---
const riskOption = computed(() => {
  const d = dashboard.value
  const dist = d?.risk_distribution
  if (!dist || dist.length === 0) return null
  const colorMap: Record<string, string> = {
    critical: '#D92D20',
    high: '#F04438',
    medium: '#DC6803',
    low: '#16845B',
    none: '#98A2B3',
  }
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      label: { formatter: '{b}: {c}' },
      data: dist.map((r: any) => ({
        name: r._id || '未知',
        value: r.count,
        itemStyle: { color: colorMap[r._id] || '#98A2B3' },
      })),
    }],
  }
})

// --- Status Distribution ---
const statusOption = computed(() => {
  const d = dashboard.value
  const sc = d?.status_counts
  if (!sc || Object.keys(sc).length === 0) return null
  const labelMap: Record<string, string> = {
    screening: '筛查中',
    screen_positive: '筛查阳性',
    pending_review: '待临床确认',
    confirmed: '已纳入确认',
    excluded: '已排除',
    pathway_active: '路径执行中',
    completed: '已完成',
    reconsideration_pending: '待复核',
    reopened: '已重新打开',
  }
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      label: { formatter: '{b}: {c}' },
      data: Object.entries(sc).map(([k, v]) => ({
        name: labelMap[k] || k,
        value: v,
      })),
    }],
  }
})

// --- Pending Table ---
const pendingColumns = [
  { title: '患者 ID', key: 'patient_id', dataIndex: 'patient_id' },
  { title: '病种', key: 'disease_name', dataIndex: 'disease_name' },
  { title: '状态', key: 'status' },
  { title: '筛查时间', dataIndex: 'first_detected_at',
    customRender: ({ text }: { text: string }) => text ? new Date(text).toLocaleString('zh-CN') : '-' },
  { title: '操作', key: 'actions', width: 120 },
]

// --- actions ---
function goCases() {
  router.push({ name: 'disease-center-cases' })
}

function goCaseDetail(caseId: string) {
  router.push({ name: 'disease-center-case-detail', params: { caseId } })
}

// 确认对话框状态
const confirmModalVisible = ref(false)
const confirmLoading = ref(false)
const confirmTarget = ref<DiseaseCase | null>(null)
const confirmReason = ref('')

function handleConfirm(record: DiseaseCase) {
  confirmTarget.value = record
  confirmReason.value = ''
  confirmModalVisible.value = true
}

async function handleConfirmSubmit() {
  if (!confirmReason.value.trim()) {
    message.warning('请输入确认原因')
    return
  }
  if (!confirmTarget.value) return
  confirmLoading.value = true
  try {
    await confirmCase(confirmTarget.value.id, {
      action: 'confirm',
      reason: confirmReason.value.trim(),
    })
    message.success('已确认纳入')
    confirmModalVisible.value = false
    loadPendingCases()
  } catch (err: any) {
    message.error('确认失败: ' + (err.message || '未知错误'))
  } finally {
    confirmLoading.value = false
  }
}

// --- load data ---
async function loadDashboard() {
  kpiLoading.value = true
  try {
    dashboard.value = (await getDashboard()).data
  } catch {
    // dashboard may not be fully implemented yet
  } finally {
    kpiLoading.value = false
  }
}

async function loadFunnel() {
  try {
    funnelData.value = (await getGlobalFunnel()).data
  } catch {
    // funnel optional
  }
}

async function loadPendingCases() {
  pendingLoading.value = true
  try {
    const res = await getAllCases({
      status: 'pending_review',
      page: 1,
      page_size: 5,
    })
    pendingCases.value = res.data.items || []
  } catch {
    pendingCases.value = []
  } finally {
    pendingLoading.value = false
  }
}

onMounted(() => {
  loadDashboard()
  loadFunnel()
  loadPendingCases()
})
</script>

<style scoped>
.disease-overview-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* KPI */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.kpi-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 12px);
  transition: box-shadow 0.2s;
}

.kpi-card:hover {
  box-shadow: var(--shadow-md);
}

.kpi-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  line-height: 1.2;
}

.kpi-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.kpi-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg, 12px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

/* Charts */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.chart-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 12px);
  padding: 16px;
}

.chart-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin-bottom: 12px;
}

.chart-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: var(--color-text-secondary, #667085);
}

/* Section */
.section-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 12px);
  padding: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

@media (max-width: 768px) {
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .chart-row {
    grid-template-columns: 1fr;
  }
}
</style>
