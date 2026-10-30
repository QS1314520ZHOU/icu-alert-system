<template>
  <div class="saki-charts">
    <a-tabs v-model:activeKey="activeChart">
      <a-tab-pane key="trajectory" tab="肌酐轨迹">
        <a-button type="primary" @click="loadTrajectory" :loading="loading" style="margin-bottom:12px">加载轨迹</a-button>
        <div v-if="trajectoryData && trajectoryData.trajectories?.length" class="chart-container">
          <v-chart :option="trajectoryOption" style="height:400px" autoresize />
        </div>
        <div v-else class="empty-wrap"><EmptyState description="暂无肌酐轨迹数据" /></div>
      </a-tab-pane>

      <a-tab-pane key="forest" tab="森林图">
        <a-button type="primary" @click="loadForest" :loading="loading" style="margin-bottom:12px">加载森林图</a-button>
        <div v-if="forestData?.forest_data?.length" class="chart-container">
          <v-chart :option="forestOption" style="height:400px" autoresize />
        </div>
        <div v-else class="empty-wrap"><EmptyState description="暂无森林图数据" /></div>
      </a-tab-pane>

      <a-tab-pane key="outcomes" tab="结局分布">
        <a-button type="primary" @click="loadOutcomes" :loading="loading" style="margin-bottom:12px">加载结局</a-button>
        <div v-if="outcomesData" class="chart-container">
          <v-chart :option="outcomesOption" style="height:300px" autoresize />
        </div>
        <div v-else class="empty-wrap"><EmptyState description="暂无结局数据" /></div>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { Button as AButton, TabPane as ATabPane, Tabs as ATabs } from 'ant-design-vue'
import { ref, computed } from 'vue'
import { use } from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { runCreatinineTrajectory, runForest, runOutcomes } from '../../api/saki'
import { EmptyState } from '../../components/common/design-system'

use([CanvasRenderer, LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, MarkLineComponent])

const activeChart = ref('trajectory')
const loading = ref(false)
const trajectoryData = ref<any>(null)
const forestData = ref<any>(null)
const outcomesData = ref<any>(null)

const trajectoryOption = computed(() => {
  if (!trajectoryData.value?.trajectories?.length) return undefined
  const series = trajectoryData.value.trajectories.slice(0, 10).map((t: any, i: number) => ({
    name: `Patient ${i + 1}`,
    type: 'line' as const,
    data: t.points.map((p: any) => [p.time, p.value]),
    smooth: true,
    lineStyle: { width: 1.5 },
  }))
  return {
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', bottom: 0 },
    xAxis: { type: 'category', name: '时间' },
    yAxis: { type: 'value', name: '肌酐 (umol/L)' },
    series,
  }
})

const FOREST_LABELS: Record<string, string> = { age: '年龄', sofa_admission: '入科 SOFA', apache2: 'APACHE II', lactate_admission: '入科乳酸', creatinine_admission: '入科肌酐', mechanical_ventilation: '机械通气', vasopressor: '血管活性药' }
const forestOption = computed(() => {
  if (!forestData.value?.forest_data?.length) return undefined
  const data = forestData.value.forest_data
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => Number(v).toFixed(2) },
    grid: { left: 110, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'log', name: 'OR', min: 0.1 },
    yAxis: { type: 'category', data: data.map((d: any) => FOREST_LABELS[d.variable] || d.variable || d.name || '') },
    series: [{
      type: 'bar',
      data: data.map((d: any) => ({ value: d.estimate ?? d.coef ?? d.or ?? 1, itemStyle: { color: (d.p ?? 1) < 0.05 ? ((d.estimate ?? 1) > 1 ? '#B91C1C' : '#2F7D55') : '#94A3B8' } })),
      markLine: { silent: true, symbol: 'none', lineStyle: { type: 'dashed', color: '#5392FF' }, data: [{ xAxis: 1 }], label: { show: false } },
    }],
  }
})

const outcomesOption = computed(() => {
  if (!outcomesData.value) return undefined
  const dist = outcomesData.value.stage_distribution || {}
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      data: Object.entries(dist).map(([k, v]) => ({ name: k === '0' ? '无 AKI' : `${k} 期`, value: v })),
    }],
  }
})

const loadTrajectory = async () => {
  loading.value = true
  try { const r = await runCreatinineTrajectory({}); trajectoryData.value = r.data } catch {} finally { loading.value = false }
}
const loadForest = async () => {
  loading.value = true
  try { const r = await runForest({}); forestData.value = r.data } catch {} finally { loading.value = false }
}
const loadOutcomes = async () => {
  loading.value = true
  try { const r = await runOutcomes({}); outcomesData.value = r.data } catch {} finally { loading.value = false }
}
</script>

<style scoped>
.saki-charts { display: flex; flex-direction: column; gap: 16px; }
.chart-container { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 16px 18px; }
.empty-wrap { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
</style>
