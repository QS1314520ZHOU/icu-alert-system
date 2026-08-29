<template>
  <div class="sparkline-container" ref="chartRef" :style="{ height: height + 'px' }" />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getChartColor, icuTooltip } from '../../../charts/icuTheme'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{
  /** 数据值数组 */
  data: number[]
  /** 颜色 */
  color?: string
  /** 高度 */
  height?: number
  /** 正常范围 [min, max] */
  normalRange?: [number, number]
}>(), {
  height: 32,
  color: getChartColor(0),
})

const chartRef = ref<HTMLElement>()
const chart = shallowRef<echarts.ECharts>()

function render() {
  if (!chart.value || !props.data.length) return

  const seriesData: any[] = [{ type: 'line', data: props.data, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: props.color }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: props.color + '30' }, { offset: 1, color: props.color + '05' }]) } }]

  if (props.normalRange) {
    seriesData[0].markArea = {
      silent: true,
      data: [[{ yAxis: props.normalRange[0], itemStyle: { color: 'rgba(18,166,106,0.06)' } }, { yAxis: props.normalRange[1] }]],
    }
  }

  chart.value.setOption({
    grid: { left: 0, right: 0, top: 0, bottom: 0 },
    tooltip: { ...icuTooltip({ trigger: 'axis' }), formatter: (p: any) => p[0]?.value ?? '--' },
    xAxis: { type: 'category', show: false, data: props.data.map((_, i) => i) },
    yAxis: { type: 'value', show: false },
    series: seriesData,
  }, true)
}

onMounted(() => {
  if (chartRef.value) {
    chart.value = echarts.init(chartRef.value)
    render()
  }
})

watch(() => props.data, render, { deep: true })
watch(() => props.color, render)

onBeforeUnmount(() => {
  chart.value?.dispose()
})
</script>

<style scoped>
.sparkline-container {
  width: 100%;
  min-width: 60px;
}
</style>
