<template>
  <div class="saki-overview">
    <div class="metrics-row">
      <div class="metric-card" v-for="m in metrics" :key="m.label">
        <div class="metric-label">{{ m.label }}</div>
        <div class="metric-value" :style="{ color: m.color }">{{ m.value }}</div>
      </div>
    </div>

    <div class="charts-row">
      <div class="chart-panel">
        <h3>AKI 分期分布</h3>
        <v-chart v-if="stageOption" :option="stageOption" style="height:280px" autoresize />
        <EmptyState v-else description="暂无数据" />
      </div>
      <div class="chart-panel">
        <h3>科室分布</h3>
        <v-chart v-if="deptOption" :option="deptOption" style="height:280px" autoresize />
        <EmptyState v-else description="暂无数据" />
      </div>
    </div>

    <div class="chart-panel full-width">
      <h3>最近病例</h3>
      <a-table :dataSource="recentCases" :columns="caseColumns" :pagination="false" size="small" rowKey="patient_id">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'aki_stage'">
            <a-tag :color="stageColor(record.aki_stage)">Stage {{ record.aki_stage }}</a-tag>
          </template>
          <template v-if="column.key === 'is_saki'">
            <a-tag :color="record.is_saki ? 'red' : 'green'">{{ record.is_saki ? 'S-AKI' : '非S-AKI' }}</a-tag>
          </template>
          <template v-if="column.key === 'review_status'">
            <a-tag>{{ reviewLabel(record.review_status) }}</a-tag>
          </template>
        </template>
      </a-table>
    </div>

  </div>
</template>

<script setup lang="ts">
import { Table as ATable, Tag as ATag } from 'ant-design-vue'
import { ref, onMounted } from 'vue'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { getSakiCaseStatistics, getSakiCases } from '../../api/saki'
import { EmptyState } from '../../components/common/design-system'

use([CanvasRenderer, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const metrics = ref([
  { label: '总病例', value: 0, color: '#1890ff' },
  { label: 'S-AKI 阳性', value: 0, color: '#ff4d4f' },
  { label: '待复核', value: 0, color: '#faad14' },
  { label: '已确认', value: 0, color: '#52c41a' },
])

const stageOption = ref<any>(null)
const deptOption = ref<any>(null)
const recentCases = ref<any[]>([])

const caseColumns = [
  { title: '患者ID', dataIndex: 'patient_id', key: 'patient_id', width: 120 },
  { title: '科室', dataIndex: 'department', key: 'department' },
  { title: 'AKI分期', key: 'aki_stage', width: 100 },
  { title: 'S-AKI', key: 'is_saki', width: 90 },
  { title: '审核', key: 'review_status', width: 90 },
]

const stageColor = (s: number) => ['green', 'orange', 'red', 'volcano'][s] || 'default'
const reviewLabel = (s: string) => ({ pending: '待审', confirmed: '已确认', rejected: '已驳回', modified: '已修改' }[s] || s)

onMounted(async () => {
  try {
    const [statsRes, casesRes] = await Promise.all([
      getSakiCaseStatistics(),
      getSakiCases({ page: 1, page_size: 10 }),
    ])
    const stats = statsRes.data
    metrics.value[0]!.value = stats.total_cases || 0
    metrics.value[1]!.value = stats.saki_positive || 0
    metrics.value[2]!.value = (stats.by_review_status?.pending) || 0
    metrics.value[3]!.value = (stats.by_review_status?.confirmed) || 0

    const byStage = stats.by_stage || {}
    const stageData = Object.entries(byStage).map(([k, v]) => ({ name: `Stage ${k}`, value: v as number }))
    if (stageData.length > 0) {
      stageOption.value = {
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        series: [{ type: 'pie', radius: ['40%', '70%'], data: stageData }],
      }
    }

    const cases = casesRes.data?.cases || []
    recentCases.value = cases
  } catch (e) {
    console.warn('S-AKI overview load failed', e)
  }
})
</script>

<style scoped>
.saki-overview { display: flex; flex-direction: column; gap: 20px; }
.metrics-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.metric-card { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 14px 16px; text-align: left; }
.metric-label { font-size: var(--text-caption); font-weight: var(--weight-medium); color: var(--color-text-secondary); }
.metric-value { font-size: var(--text-metric-key); font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; }
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.chart-panel { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 16px 18px; }
.chart-panel h3 { margin: 0 0 12px; font-size: var(--text-section-title); font-weight: var(--weight-semibold); color: var(--color-text-primary); }
.full-width { grid-column: 1 / -1; }
.disclaimer-banner { text-align: center; padding: 10px; background: var(--color-warning-soft-bg); border: 1px solid var(--color-warning-soft-border); border-radius: var(--radius-md); font-size: var(--text-caption); color: var(--color-warning); }
</style>
