<template>
  <div class="analytics-page">
    <a-card :bordered="false" class="filter-card">
      <div class="filter-row">
        <div class="left-tools">
          <a-space wrap>
            <span class="label">时间窗口</span>
            <a-segmented
              v-model:value="windowRange"
              :options="windowOptions"
              size="small"
            />
            <span class="label">粒度</span>
            <a-segmented
              v-model:value="bucket"
              :options="bucketOptions"
              size="small"
            />
            <span class="label">TopN</span>
            <a-input-number v-model:value="topN" :min="5" :max="30" size="small" />
          </a-space>
        </div>
        <div class="right-tools">
          <a-button size="small" :loading="loading" @click="loadAll">刷新统计</a-button>
        </div>
      </div>
    </a-card>

    <section class="analytics-grid">
      <a-card title="预警触发频率" :bordered="false" class="panel panel-wide">
        <div v-if="freqSeries.length" class="chart-wrap chart-lg">
          <AnalyticsChart :option="frequencyOption" autoresize />
        </div>
        <div v-else class="empty">暂无频率数据</div>
      </a-card>

      <a-card title="规则类型热力图" :bordered="false" class="panel panel-wide">
        <div v-if="heatmapY.length" class="chart-wrap chart-lg">
          <AnalyticsChart :option="heatmapOption" autoresize />
        </div>
        <div v-else class="empty">暂无规则热力图数据</div>
      </a-card>

      <a-card title="科室预警排名" :bordered="false" class="panel">
        <div v-if="deptRankings.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="deptRankOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="deptColumns"
          :data-source="deptRankings"
          :pagination="false"
          row-key="dept"
        />
      </a-card>

      <a-card title="床位预警排名" :bordered="false" class="panel">
        <div v-if="bedRankings.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="bedRankOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="bedColumns"
          :data-source="bedRankings"
          :pagination="false"
          :scroll="{ x: 560 }"
          row-key="bedKey"
        />
      </a-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Button as AButton,
  Card as ACard,
  InputNumber as AInputNumber,
  Segmented as ASegmented,
  Space as ASpace,
  Table as ATable,
} from 'ant-design-vue'
import {
  getAlertAnalyticsFrequency,
  getAlertAnalyticsHeatmap,
  getAlertAnalyticsRankings,
} from '../api'

const AnalyticsChart = defineAsyncComponent(async () => {
  await import('../charts/analytics')
  const mod = await import('vue-echarts')
  return mod.default
})

const route = useRoute()
const loading = ref(false)
const windowRange = ref('7d')
const bucket = ref<'hour' | 'day'>('hour')
const topN = ref(10)

const windowOptions = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '14d', value: '14d' },
  { label: '30d', value: '30d' },
]
const bucketOptions = [
  { label: '小时', value: 'hour' },
  { label: '天', value: 'day' },
]

const freqSeries = ref<any[]>([])
const heatmapX = ref<string[]>([])
const heatmapY = ref<string[]>([])
const heatmapData = ref<number[][]>([])
const deptRankings = ref<any[]>([])
const bedRankings = ref<any[]>([])

const deptCode = computed(() => String(route.query.dept_code || '').trim())
const deptName = computed(() => String(route.query.dept || '').trim())

function commonParams() {
  const params: Record<string, any> = { window: windowRange.value }
  if (deptCode.value) params.dept_code = deptCode.value
  else if (deptName.value) params.dept = deptName.value
  return params
}

function toShortTime(v: string) {
  const s = String(v || '')
  if (bucket.value === 'day') return s.slice(5)
  return s.slice(5, 16)
}

const frequencyOption = computed(() => {
  const xs = freqSeries.value.map((p: any) => toShortTime(p.time || ''))
  return {
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9aa4b2' } },
    grid: { left: 36, right: 16, top: 28, bottom: 36 },
    xAxis: {
      type: 'category',
      data: xs,
      axisLabel: { color: '#6b7280', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#6b7280', fontSize: 10 },
      splitLine: { lineStyle: { color: '#16263e' } },
    },
    series: [
      {
        name: '总量',
        type: 'bar',
        data: freqSeries.value.map((p: any) => p.total || 0),
        itemStyle: { color: '#3b82f6aa' },
        barMaxWidth: 16,
      },
      {
        name: 'Warning',
        type: 'line',
        smooth: true,
        data: freqSeries.value.map((p: any) => p.warning || 0),
      },
      {
        name: 'High',
        type: 'line',
        smooth: true,
        data: freqSeries.value.map((p: any) => p.high || 0),
      },
      {
        name: 'Critical',
        type: 'line',
        smooth: true,
        data: freqSeries.value.map((p: any) => p.critical || 0),
      },
    ],
  }
})

const heatmapOption = computed(() => {
  const maxVal = heatmapData.value.reduce((m, cur) => Math.max(m, cur[2] || 0), 0)
  return {
    tooltip: {
      formatter: (params: any) => {
        const x = heatmapX.value[params.value[0]]
        const y = heatmapY.value[params.value[1]]
        return `${y}<br/>${x}时: ${params.value[2]}`
      },
    },
    grid: { left: 110, right: 14, top: 24, bottom: 32 },
    xAxis: {
      type: 'category',
      data: heatmapX.value,
      axisLabel: { color: '#72809a', fontSize: 10 },
      splitArea: { show: true },
    },
    yAxis: {
      type: 'category',
      data: heatmapY.value,
      axisLabel: { color: '#72809a', fontSize: 10 },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: Math.max(1, maxVal),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: '#72809a' },
      inRange: {
        color: ['#10213b', '#245ea8', '#3b82f6', '#f59e0b', '#ef4444'],
      },
    },
    series: [
      {
        name: '触发频次',
        type: 'heatmap',
        data: heatmapData.value,
        emphasis: {
          itemStyle: {
            borderColor: '#fff',
            borderWidth: 1,
          },
        },
      },
    ],
  }
})

const deptRankOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 70, right: 16, top: 12, bottom: 20 },
  xAxis: {
    type: 'value',
    axisLabel: { color: '#6b7280', fontSize: 10 },
    splitLine: { lineStyle: { color: '#16263e' } },
  },
  yAxis: {
    type: 'category',
    data: deptRankings.value.map((d: any) => d.dept),
    axisLabel: { color: '#6b7280', fontSize: 10 },
  },
  series: [
    {
      type: 'bar',
      data: deptRankings.value.map((d: any) => d.count || 0),
      itemStyle: { color: '#06b6d4' },
      barMaxWidth: 18,
    },
  ],
}))

const bedRankOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 90, right: 16, top: 12, bottom: 20 },
  xAxis: {
    type: 'value',
    axisLabel: { color: '#6b7280', fontSize: 10 },
    splitLine: { lineStyle: { color: '#16263e' } },
  },
  yAxis: {
    type: 'category',
    data: bedRankings.value.map((d: any) => `${d.dept}-${d.bed}`),
    axisLabel: { color: '#6b7280', fontSize: 10 },
  },
  series: [
    {
      type: 'bar',
      data: bedRankings.value.map((d: any) => d.count || 0),
      itemStyle: { color: '#f59e0b' },
      barMaxWidth: 18,
    },
  ],
}))

const deptColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept' },
  { title: '总量', dataIndex: 'count', key: 'count', width: 72 },
  { title: 'Critical', dataIndex: 'critical', key: 'critical', width: 80 },
  { title: 'High', dataIndex: 'high', key: 'high', width: 70 },
  { title: 'Warn', dataIndex: 'warning', key: 'warning', width: 70 },
]

const bedColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept', width: 120 },
  { title: '床位', dataIndex: 'bed', key: 'bed', width: 90 },
  { title: '总量', dataIndex: 'count', key: 'count', width: 72 },
  { title: 'Critical', dataIndex: 'critical', key: 'critical', width: 80 },
  { title: 'High', dataIndex: 'high', key: 'high', width: 70 },
  { title: 'Warn', dataIndex: 'warning', key: 'warning', width: 70 },
]

async function loadFrequency() {
  const res = await getAlertAnalyticsFrequency({
    ...commonParams(),
    bucket: bucket.value,
  })
  freqSeries.value = res.data.series || []
}

async function loadHeatmap() {
  const res = await getAlertAnalyticsHeatmap({
    ...commonParams(),
    top_n: topN.value,
  })
  heatmapX.value = res.data.x_labels || []
  heatmapY.value = res.data.y_labels || []
  heatmapData.value = res.data.data || []
}

async function loadRankings() {
  const res = await getAlertAnalyticsRankings({
    ...commonParams(),
    top_n: topN.value,
  })
  deptRankings.value = res.data.dept_rankings || []
  bedRankings.value = (res.data.bed_rankings || []).map((r: any, idx: number) => ({
    ...r,
    bedKey: `${r.dept || ''}-${r.bed || ''}-${idx}`,
  }))
}

async function loadAll() {
  if (loading.value) return
  loading.value = true
  try {
    await Promise.all([loadFrequency(), loadHeatmap(), loadRankings()])
  } catch (e) {
    console.error('加载Analytics失败', e)
  } finally {
    loading.value = false
  }
}

watch([windowRange, bucket, topN], () => {
  void loadAll()
})

watch(
  () => route.query,
  () => {
    void loadAll()
  },
  { deep: true }
)

onMounted(() => {
  void loadAll()
})
</script>

<style scoped>
.analytics-page {
  padding: 12px;
}

.filter-card {
  background: #0e1728;
  border: 1px solid #192d4a;
  margin-bottom: 12px;
}

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.left-tools .label {
  font-size: 12px;
  color: #8fa3c1;
  margin-right: 2px;
}

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.panel {
  background: #0d1728;
  border: 1px solid #192d4a;
  min-height: 440px;
}

.panel-wide {
  grid-column: span 2;
}

.chart-wrap {
  width: 100%;
}

.chart-lg {
  height: 360px;
}

.chart-md {
  height: 280px;
}

.rank-table {
  margin-top: 10px;
}

.empty {
  color: #7b8ba3;
  font-size: 12px;
  padding: 14px 4px;
}

:global(html[data-theme='light']) .analytics-page {
  background: #f4f7fb;
}

:global(html[data-theme='light']) .filter-card,
:global(html[data-theme='light']) .panel {
  background: #ffffff;
  border-color: #d9e2f1;
}

:global(html[data-theme='light']) .left-tools .label,
:global(html[data-theme='light']) .empty {
  color: #64748b;
}

:global(html[data-theme='light']) .rank-table :deep(.ant-table) {
  background: #ffffff;
}

:global(html[data-theme='light']) .rank-table :deep(.ant-table-thead > tr > th) {
  background: #f1f6ff;
  color: #334155;
  border-bottom-color: #dce5f3;
}

:global(html[data-theme='light']) .rank-table :deep(.ant-table-tbody > tr > td) {
  background: #ffffff;
  color: #334155;
  border-bottom-color: #e6edf8;
}

@media (max-width: 980px) {
  .analytics-page {
    padding: 8px;
  }

  .analytics-grid {
    grid-template-columns: 1fr;
  }

  .panel,
  .panel-wide {
    grid-column: auto;
    min-height: 0;
  }

  .chart-lg,
  .chart-md {
    height: 300px;
  }
}
</style>
