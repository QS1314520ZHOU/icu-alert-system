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

      <a-card title="规则类型热力图" :bordered="false" class="panel panel-wide panel-heatmap">
        <div v-if="heatmapY.length" class="heatmap-summary">
          <div class="summary-chip">
            <span class="summary-k">规则数</span>
            <b class="summary-v">{{ heatmapSummary.ruleCount }}</b>
          </div>
          <div class="summary-chip">
            <span class="summary-k">时段数</span>
            <b class="summary-v">{{ heatmapSummary.slotCount }}</b>
          </div>
          <div class="summary-chip summary-chip--wide">
            <span class="summary-k">峰值时段</span>
            <b class="summary-v">{{ heatmapSummary.peakText }}</b>
          </div>
        </div>
        <div v-if="heatmapY.length" class="chart-wrap chart-lg chart-heatmap">
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
import {
  icuCategoryAxis,
  icuGrid,
  icuLegend,
  icuTooltip,
  icuValueAxis,
} from '../charts/icuTheme'

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

const deptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
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
    backgroundColor: 'transparent',
    tooltip: icuTooltip({ trigger: 'axis' }),
    legend: icuLegend({ textStyle: { fontSize: 10 } }),
    grid: icuGrid({ left: 42, right: 18, top: 34, bottom: 34 }),
    xAxis: icuCategoryAxis(xs, { axisLabel: { fontSize: 10, margin: 10 } }),
    yAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
    series: [
      {
        name: '总量',
        type: 'bar',
        data: freqSeries.value.map((p: any) => p.total || 0),
        itemStyle: {
          color: '#0ea5b7',
          borderRadius: [6, 6, 0, 0],
          shadowBlur: 10,
          shadowColor: 'rgba(14, 165, 183, 0.18)',
        },
        barMaxWidth: 16,
      },
      {
        name: 'Warning',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fbbf24' },
        itemStyle: { color: '#fbbf24' },
        data: freqSeries.value.map((p: any) => p.warning || 0),
      },
      {
        name: 'High',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb923c' },
        itemStyle: { color: '#fb923c' },
        data: freqSeries.value.map((p: any) => p.high || 0),
      },
      {
        name: 'Critical',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb5a7a' },
        itemStyle: { color: '#fb5a7a' },
        data: freqSeries.value.map((p: any) => p.critical || 0),
      },
    ],
  }
})

const heatmapOption = computed(() => {
  const maxVal = heatmapData.value.reduce((m, cur) => Math.max(m, cur[2] || 0), 0)
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      extraCssText: 'box-shadow: 0 12px 28px rgba(0,0,0,.28); border-radius: 10px;',
      formatter: (params: any) => {
        const x = heatmapX.value[params.value[0]]
        const y = heatmapY.value[params.value[1]]
        return `${y}<br/>时段：${x}<br/>触发：${params.value[2]} 次`
      },
    }),
    grid: icuGrid({ left: 128, right: 22, top: 20, bottom: 62 }),
    xAxis: icuCategoryAxis(heatmapX.value, {
      axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.24)' } },
      axisLabel: { color: '#79d7ea', fontSize: 10, margin: 12 },
      splitArea: { show: false },
      splitLine: { show: true, lineStyle: { color: 'rgba(61, 118, 145, 0.12)' } },
    }),
    yAxis: icuCategoryAxis(heatmapY.value, {
      axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.24)' } },
      axisLabel: { color: '#b7ddec', fontSize: 10, margin: 14 },
      splitArea: { show: false },
      splitLine: { show: true, lineStyle: { color: 'rgba(61, 118, 145, 0.12)' } },
    }),
    visualMap: {
      min: 0,
      max: Math.max(1, maxVal),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 8,
      itemWidth: 140,
      itemHeight: 10,
      text: ['高频', '低频'],
      textGap: 10,
      textStyle: { color: '#7fc7da', fontSize: 10 },
      inRange: {
        color: ['#0a2234', '#0e4c68', '#16b3c9', '#f59e0b', '#fb5a7a'],
      },
    },
    series: [
      {
        name: '触发频次',
        type: 'heatmap',
        data: heatmapData.value,
        label: {
          show: true,
          formatter: ({ value }: any) => (value?.[2] ? value[2] : ''),
          color: '#effcff',
          fontSize: 10,
          fontWeight: 700,
        },
        itemStyle: {
          borderRadius: 8,
          borderColor: 'rgba(112, 226, 255, 0.1)',
          borderWidth: 1,
        },
        emphasis: {
          itemStyle: {
            borderColor: '#dffbff',
            borderWidth: 1,
            shadowBlur: 18,
            shadowColor: 'rgba(34, 211, 238, 0.22)',
          },
        },
      },
    ],
  }
})

const heatmapSummary = computed(() => {
  let peak = { val: 0, x: '', y: '' }
  for (const item of heatmapData.value) {
    const xi = Number(item?.[0])
    const yi = Number(item?.[1])
    const v = item?.[2] || 0
    if (v >= peak.val) {
      peak = {
        val: v,
        x: heatmapX.value[xi] || '',
        y: heatmapY.value[yi] || '',
      }
    }
  }
  return {
    ruleCount: heatmapY.value.length,
    slotCount: heatmapX.value.length,
    peakText: peak.val ? `${peak.y} · ${peak.x} · ${peak.val}次` : '暂无峰值',
  }
})

const deptRankOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({ trigger: 'axis', axisPointer: { type: 'shadow' } }),
  grid: icuGrid({ left: 84, right: 18, top: 16, bottom: 24 }),
  xAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
  yAxis: icuCategoryAxis(deptRankings.value.map((d: any) => d.dept), {
    axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.18)' } },
    axisLabel: { color: '#b7ddec', fontSize: 10 },
  }),
  series: [
    {
      type: 'bar',
      data: deptRankings.value.map((d: any) => d.count || 0),
      itemStyle: {
        color: (params: any) => {
          const colors = ['#16b3c9', '#0ea5b7', '#0891b2', '#0369a1']
          return colors[params.dataIndex % colors.length]
        },
        borderRadius: [0, 8, 8, 0],
      },
      barMaxWidth: 18,
      label: {
        show: true,
        position: 'right',
        color: '#dffbff',
        fontSize: 10,
      },
    },
  ],
}))

const bedRankOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({ trigger: 'axis', axisPointer: { type: 'shadow' } }),
  grid: icuGrid({ left: 102, right: 18, top: 16, bottom: 24 }),
  xAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
  yAxis: icuCategoryAxis(bedRankings.value.map((d: any) => `${d.dept}-${d.bed}`), {
    axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.18)' } },
    axisLabel: { color: '#b7ddec', fontSize: 10 },
  }),
  series: [
    {
      type: 'bar',
      data: bedRankings.value.map((d: any) => d.count || 0),
      itemStyle: {
        color: (params: any) => {
          const colors = ['#f59e0b', '#fb923c', '#fb7185', '#f43f5e']
          return colors[params.dataIndex % colors.length]
        },
        borderRadius: [0, 8, 8, 0],
      },
      barMaxWidth: 18,
      label: {
        show: true,
        position: 'right',
        color: '#dffbff',
        fontSize: 10,
      },
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
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&display=swap');

.analytics-page {
  position: relative;
  isolation: isolate;
  padding: 16px 22px 24px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.1), rgba(34, 211, 238, 0) 28%),
    linear-gradient(180deg, #06111d 0%, #040b14 100%);
  min-height: 100%;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
}

.analytics-page::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(73, 196, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(73, 196, 255, 0.04) 1px, transparent 1px);
  background-size: 28px 28px;
  opacity: 0.26;
  z-index: -1;
}

.filter-card {
  background:
    linear-gradient(180deg, rgba(9, 22, 36, 0.94) 0%, rgba(6, 15, 27, 0.92) 100%);
  border: 1px solid rgba(80, 199, 255, 0.16);
  margin-bottom: 16px;
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.06), 0 12px 28px rgba(0, 0, 0, 0.2);
}

.filter-card :deep(.ant-card-body) {
  padding: 12px 14px;
}

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.left-tools .label {
  font-size: 12px;
  color: #7ccfe4;
  margin-right: 4px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.filter-card :deep(.ant-segmented) {
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(80, 199, 255, 0.14);
}

.filter-card :deep(.ant-segmented-item) {
  color: #8bcfe1;
  font-weight: 600;
}

.filter-card :deep(.ant-segmented-item-selected) {
  background: linear-gradient(180deg, rgba(11, 107, 137, 0.96) 0%, rgba(7, 63, 86, 0.98) 100%);
  color: #effcff;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.08);
}

.filter-card :deep(.ant-input-number) {
  background: rgba(8, 28, 44, 0.78);
  border-color: rgba(80, 199, 255, 0.14);
}

.filter-card :deep(.ant-input-number input) {
  color: #e8fbff;
}

.filter-card :deep(.ant-btn) {
  background: linear-gradient(180deg, rgba(11, 107, 137, 0.96) 0%, rgba(7, 63, 86, 0.98) 100%);
  border-color: rgba(110, 231, 249, 0.28);
  color: #effcff;
  font-weight: 600;
}

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel {
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.07), rgba(34, 211, 238, 0) 30%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  border: 1px solid rgba(80, 199, 255, 0.14);
  min-height: 420px;
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.04), 0 12px 28px rgba(0, 0, 0, 0.2);
}

.panel :deep(.ant-card-head) {
  min-height: 50px;
  border-bottom: 1px solid rgba(80, 199, 255, 0.1);
  background: linear-gradient(90deg, rgba(9, 31, 48, 0.5), rgba(9, 31, 48, 0));
}

.panel :deep(.ant-card-head-title) {
  color: #67e8f9;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.panel :deep(.ant-card-body) {
  padding: 12px 14px 14px;
}

.panel-wide {
  grid-column: span 2;
}

.chart-wrap {
  width: 100%;
  position: relative;
  border-radius: 12px;
}

.chart-lg {
  height: 360px;
}

.chart-heatmap {
  padding-top: 4px;
}

.chart-md {
  height: 280px;
}

.panel-heatmap {
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 35%),
    var(--card-bg);
}

.heatmap-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(79, 182, 219, 0.18);
}

.summary-chip--wide {
  max-width: 100%;
}

.summary-k {
  font-size: 11px;
  color: #77c9de;
  letter-spacing: 0.08em;
}

.summary-v {
  font-size: 12px;
  color: #e8fbff;
  font-weight: 700;
}

.rank-table {
  margin-top: 12px;
}

.empty {
  color: #7ccfe4;
  font-size: 12px;
  padding: 16px 8px;
}

.rank-table :deep(.ant-table) {
  background: transparent;
  color: #dff8ff;
}

.rank-table :deep(.ant-table-container) {
  border: 1px solid rgba(80, 199, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
}

.rank-table :deep(.ant-table-thead > tr > th) {
  background: rgba(8, 28, 44, 0.82);
  color: #7ccfe4;
  border-bottom-color: rgba(80, 199, 255, 0.1);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.rank-table :deep(.ant-table-tbody > tr > td) {
  background: transparent;
  color: #e3fbff;
  border-bottom-color: rgba(80, 199, 255, 0.08);
  font-size: 12px;
}

.rank-table :deep(.ant-table-tbody > tr:hover > td) {
  background: rgba(11, 42, 63, 0.42) !important;
}

.rank-table :deep(.ant-table-placeholder) {
  background: transparent;
}

.rank-table :deep(.ant-empty-description) {
  color: #7ccfe4;
}

@media (max-width: 980px) {
  .analytics-page {
    padding: 10px;
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
```
