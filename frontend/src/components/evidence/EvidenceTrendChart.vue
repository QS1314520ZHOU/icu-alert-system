<template>
  <div class="evidence-trend">
    <div v-if="!trends.length" class="trend-empty">暂无趋势数据</div>
    <div v-else class="trend-charts">
      <div v-for="trend in trends" :key="trend.code" class="trend-item">
        <div class="trend-header">
          <span class="trend-name">{{ trend.name }}</span>
          <span class="trend-range">{{ trend.reference_range }}</span>
        </div>
        <div ref="chartRefs" class="trend-canvas" :data-code="trend.code"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import type { EvidenceTrend } from '../../api/clinicalEvidence'

const props = defineProps<{
  trends: EvidenceTrend[]
}>()

const chartRefs = ref<HTMLElement[]>([])
const chartInstances: any[] = []

onMounted(() => {
  void nextTick(renderCharts)
})

watch(() => props.trends, () => {
  void nextTick(renderCharts)
}, { deep: true })

onBeforeUnmount(() => {
  chartInstances.forEach(c => c?.dispose?.())
  chartInstances.length = 0
})

async function renderCharts() {
  // 动态导入 echarts 避免首屏加载过大
  let echarts: any
  try {
    echarts = await import('echarts')
  } catch {
    return
  }

  chartInstances.forEach(c => c?.dispose?.())
  chartInstances.length = 0

  const container = document.querySelector('.trend-charts')
  if (!container) return

  const canvases = container.querySelectorAll('.trend-canvas')
  canvases.forEach((canvas, idx) => {
    const trend = props.trends[idx]
    if (!trend || !canvas) return

    const chart = echarts.init(canvas as HTMLElement)
    chartInstances.push(chart)

    const times = trend.points.map(p => {
      const d = new Date(p.time)
      return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
    })
    const values = trend.points.map(p => p.value)

    const option = {
      grid: { top: 10, right: 12, bottom: 24, left: 40 },
      xAxis: { type: 'category', data: times, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: [{
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { width: 2, color: '#2563EB' },
        itemStyle: { color: '#2563EB' },
        areaStyle: { color: 'rgba(37,99,235,0.08)' },
      }],
      tooltip: { trigger: 'axis' },
    }

    chart.setOption(option)
  })
}
</script>

<style scoped>
.trend-charts {
  display: grid;
  gap: 12px;
}
.trend-item {
  border: 1px solid var(--color-border, #E5E7EB);
  border-radius: 6px;
  padding: 8px;
  background: var(--bg-surface, #fff);
}
.trend-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}
.trend-name { font-size: 12px; font-weight: 600; color: var(--text-primary, #182230); }
.trend-range { font-size: 11px; color: var(--text-tertiary, #9CA3AF); }
.trend-canvas { width: 100%; height: 140px; }
.trend-empty {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary, #9CA3AF);
  font-size: 13px;
}
</style>
