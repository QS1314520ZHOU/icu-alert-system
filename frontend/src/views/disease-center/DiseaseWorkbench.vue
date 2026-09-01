<template>
  <div class="disease-workbench">
    <a-page-header
      :title="diseaseName || '病种工作台'"
      :sub-title="diseaseCode"
      @back="goBack"
    >
      <template #extra>
        <a-space>
          <a-tag :color="statusColor">{{ statusLabel }}</a-tag>
          <a-tag v-if="disease?.version">v{{ disease.version }}</a-tag>
        </a-space>
      </template>
    </a-page-header>

    <a-spin :spinning="loading">
      <div class="workbench-content">
        <a-tabs v-model:activeKey="activeTab" type="card">
          <!-- 概览 -->
          <a-tab-pane key="overview" tab="概览">
            <div class="overview-grid">
              <div class="overview-card">
                <span class="overview-label">总病例数</span>
                <span class="overview-value">{{ dashData?.total_cases ?? '-' }}</span>
              </div>
              <div class="overview-card">
                <span class="overview-label">今日新增</span>
                <span class="overview-value">{{ dashData?.today_new ?? '-' }}</span>
              </div>
              <div class="overview-card">
                <span class="overview-label">待临床确认</span>
                <span class="overview-value">{{ dashData?.pending_review ?? '-' }}</span>
              </div>
              <div class="overview-card">
                <span class="overview-label">路径超时</span>
                <span class="overview-value" :class="{ 'value-warning': (dashData?.overdue_pathways ?? 0) > 0 }">
                  {{ dashData?.overdue_pathways ?? '-' }}
                </span>
              </div>
            </div>

            <div class="overview-charts">
              <div class="chart-card">
                <div class="chart-title">风险分布</div>
                <v-chart v-if="riskOption" :option="riskOption" :style="{ height: '260px' }" autoresize />
                <a-empty v-else description="暂无数据" />
              </div>
              <div class="chart-card">
                <div class="chart-title">病例趋势</div>
                <v-chart v-if="trendOption" :option="trendOption" :style="{ height: '260px' }" autoresize />
                <a-empty v-else description="暂无数据" />
              </div>
            </div>
          </a-tab-pane>

          <!-- 病例列表 -->
          <a-tab-pane key="cases" tab="病例列表">
            <a-table
              :columns="caseColumns"
              :data-source="caseList"
              :loading="caseLoading"
              :pagination="casePagination"
              row-key="id"
              size="middle"
              @change="handleCaseTableChange"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'patient_id'">
                  <a @click="goCaseDetail(record.id)">{{ record.patient_id }}</a>
                </template>
                <template v-if="column.key === 'status'">
                  <a-tag :color="getCaseStatusColor(record.status)" size="small">
                    {{ getCaseStatusLabel(record.status) }}
                  </a-tag>
                </template>
                <template v-if="column.key === 'risk_level'">
                  <span :class="getRiskClass(record.risk_level)">{{ record.risk_level || '-' }}</span>
                </template>
                <template v-if="column.key === 'actions'">
                  <a-button type="link" size="small" @click="goCaseDetail(record.id)">详情</a-button>
                </template>
              </template>
            </a-table>
          </a-tab-pane>

          <!-- 筛查规则 -->
          <a-tab-pane key="screening" tab="筛查规则">
            <div class="tab-placeholder">
              <a-empty description="筛查规则配置 - 待实现" />
            </div>
          </a-tab-pane>

          <!-- 临床路径 -->
          <a-tab-pane key="pathway" tab="临床路径">
            <div v-if="pathway" class="pathway-info">
              <div class="pathway-header">
                <span class="pathway-name">{{ pathway.name }}</span>
                <a-tag :color="pathway.status === 'published' ? 'var(--color-success)' : 'default'">
                  {{ pathway.status === 'published' ? '已发布' : pathway.status }}
                </a-tag>
              </div>
              <p v-if="pathway.description" class="pathway-desc">{{ pathway.description }}</p>
              <div v-if="pathway.tasks && pathway.tasks.length > 0" class="pathway-tasks">
                <div v-for="(task, idx) in pathway.tasks" :key="idx" class="pathway-task-item">
                  <span class="task-idx">{{ idx + 1 }}</span>
                  <span class="task-name">{{ task.name || task.task_id }}</span>
                  <a-tag v-if="task.time_limit_hours" size="small">
                    {{ task.time_limit_hours }}h 时限
                  </a-tag>
                </div>
              </div>
            </div>
            <a-empty v-else description="暂无临床路径" />
          </a-tab-pane>

          <!-- 证据规则 -->
          <a-tab-pane key="evidence" tab="证据规则">
            <div class="tab-placeholder">
              <a-empty description="证据规则配置 - 待实现" />
            </div>
          </a-tab-pane>

          <!-- 数据分析 -->
          <a-tab-pane key="analytics" tab="数据分析">
            <div class="tab-placeholder">
              <a-empty description="数据分析 - 待实现" />
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import VChart from 'vue-echarts'
import {
  getDiseaseDetail,
  getDiseaseDashboard,
  getDiseaseCases,
  getDiseasePathway,
} from '@/api/diseaseCenter'
import type { Disease, DiseaseDashboardData, DiseaseCase } from '@/api/diseaseCenter'

const route = useRoute()
const router = useRouter()

const diseaseId = computed(() => route.params.id as string)
const disease = ref<Disease | null>(null)
const dashData = ref<DiseaseDashboardData | null>(null)
const pathway = ref<any>(null)
const loading = ref(false)
const activeTab = ref('overview')

// Case list
const caseList = ref<DiseaseCase[]>([])
const caseLoading = ref(false)
const caseTotal = ref(0)
const casePage = ref(1)
const casePageSize = ref(20)

const diseaseName = computed(() => disease.value?.name || '')
const diseaseCode = computed(() => disease.value?.code || '')

const statusColor = computed(() => {
  const s = disease.value?.status
  if (s === 'published') return 'var(--color-success)'
  if (s === 'draft') return 'default'
  return 'var(--color-primary)'
})

const statusLabel = computed(() => {
  const s = disease.value?.status
  if (s === 'published') return '已发布'
  if (s === 'draft') return '草稿'
  return s || '未知'
})

const caseColumns = [
  { title: '患者 ID', key: 'patient_id', dataIndex: 'patient_id', width: 140 },
  { title: '状态', key: 'status', dataIndex: 'status', width: 110 },
  { title: '风险', key: 'risk_level', dataIndex: 'risk_level', width: 90 },
  { title: '筛查时间', dataIndex: 'first_detected_at', width: 170,
    customRender: ({ text }: { text: string }) => text ? new Date(text).toLocaleString('zh-CN') : '-' },
  { title: '操作', key: 'actions', width: 80 },
]

const casePagination = computed(() => ({
  current: casePage.value,
  pageSize: casePageSize.value,
  total: caseTotal.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
}))

// --- Charts ---
const riskOption = computed(() => {
  const dist = dashData.value?.risk_distribution
  if (!dist || dist.length === 0) return null
  const colorMap: Record<string, string> = {
    critical: '#D92D20', high: '#F04438', medium: '#DC6803', low: '#16845B', none: '#98A2B3',
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

const trendOption = computed(() => {
  const trend = dashData.value?.trend
  if (!trend || trend.length === 0) return null
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trend.map((t: any) => t._id) },
    yAxis: { type: 'value', name: '病例数' },
    series: [{
      type: 'bar',
      data: trend.map((t: any) => t.total),
      itemStyle: { color: '#1D6F63', borderRadius: [4, 4, 0, 0] },
    }],
  }
})

// --- Helpers ---
function getCaseStatusColor(status: string) {
  const map: Record<string, string> = {
    screening: 'default', screen_positive: 'orange', pending_review: 'var(--color-primary-light)',
    confirmed: 'var(--color-success-light)', excluded: 'default',
    pathway_active: 'var(--color-primary)', completed: 'var(--color-success)',
  }
  return map[status] || 'default'
}

function getCaseStatusLabel(status: string) {
  const map: Record<string, string> = {
    screening: '筛查中', screen_positive: '筛查阳性', pending_review: '待临床确认',
    confirmed: '已纳入确认', excluded: '已排除', pathway_active: '路径执行中', completed: '已完成',
    reconsideration_pending: '待复核', reopened: '已重新打开',
  }
  return map[status] || status
}

function getRiskClass(level: string) {
  if (level === 'high' || level === 'critical') return 'risk-high'
  if (level === 'medium') return 'risk-medium'
  return 'risk-low'
}

function goBack() {
  router.push({ name: 'disease-center-diseases' })
}

function goCaseDetail(caseId: string) {
  router.push({ name: 'disease-center-case-detail', params: { caseId } })
}

function handleCaseTableChange(pag: any) {
  casePage.value = pag.current || 1
  casePageSize.value = pag.pageSize || 20
  loadCases()
}

// --- Data loading ---
async function loadDisease() {
  try {
    disease.value = await getDiseaseDetail(diseaseId.value)
  } catch {
    // disease not found
  }
}

async function loadDashboard() {
  try {
    dashData.value = await getDiseaseDashboard(diseaseId.value)
  } catch {
    // dashboard may not be available
  }
}

async function loadCases() {
  caseLoading.value = true
  try {
    const res = await getDiseaseCases(diseaseId.value, {
      page: casePage.value,
      page_size: casePageSize.value,
    })
    caseList.value = res.items || []
    caseTotal.value = res.total || 0
  } catch {
    caseList.value = []
  } finally {
    caseLoading.value = false
  }
}

async function loadPathway() {
  try {
    pathway.value = await getDiseasePathway(diseaseId.value)
  } catch {
    pathway.value = null
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      loadDisease(),
      loadDashboard(),
      loadCases(),
      loadPathway(),
    ])
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.disease-workbench {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workbench-content {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 12px);
  padding: 16px;
}

.tab-placeholder {
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Overview */
.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.overview-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: var(--radius-md, 8px);
}

.overview-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.overview-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}

.value-warning {
  color: var(--color-error, #D92D20);
}

.overview-charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.chart-card {
  padding: 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 8px);
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin-bottom: 8px;
}

/* Risk classes */
.risk-high {
  color: var(--color-error, #D92D20);
  font-weight: 600;
}

.risk-medium {
  color: var(--color-warning, #DC6803);
  font-weight: 500;
}

.risk-low {
  color: var(--color-success, #16845B);
}

/* Pathway */
.pathway-info {
  padding: 12px;
}

.pathway-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.pathway-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.pathway-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
  margin-bottom: 12px;
}

.pathway-tasks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pathway-task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: var(--radius-sm, 6px);
}

.task-idx {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary, #1D6F63);
  color: #fff;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.task-name {
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
}

@media (max-width: 768px) {
  .overview-charts {
    grid-template-columns: 1fr;
  }
}
</style>
