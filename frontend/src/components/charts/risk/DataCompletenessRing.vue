<template>
  <div class="completeness-ring">
    <div class="completeness-ring__chart" ref="chartRef" :style="{ width: size + 'px', height: size + 'px' }" />
    <div v-if="label" class="completeness-ring__label">{{ label }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, shallowRef, computed } from 'vue'
import * as echarts from 'echarts/core'
import { GaugeChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([GaugeChart, CanvasRenderer])

const props = withDefaults(defineProps<{
  /** 完整度百分比 0-100 */
  value: number
  /** 尺寸（px） */
  size?: number
  /** 标签 */
  label?: string
  /** 颜色 */
  color?: string
}>(), {
  size: 80,
  color: '#1677FF',
})

const chartRef = ref<HTMLElement>()
const chart = shallowRef<echarts.ECharts>()

const statusColor = computed(() => {
  if (props.value >= 80) return '#12A66A'
  if (props.value >= 60) return '#E5B700'
  return '#D92D20'
})

function render() {
  if (!chart.value) return
  chart.value.setOption({
    series: [{
      type: 'gauge',
      startAngle: 90,
      endAngle: -270,
      radius: '90%',
      center: ['50%', '50%'],
      pointer: { show: false },
      progress: {
        show: true,
        overlap: false,
        roundCap: true,
        width: 8,
        itemStyle: { color: statusColor.value },
      },
      axisLine: { lineStyle: { width: 8, color: [[1, '#E8EEF5']] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      detail: {
        valueAnimation: true,
        formatter: '{value}%',
        fontSize: props.size < 60 ? 11 : 14,
        fontWeight: 700,
        fontFamily: '"Rajdhani", sans-serif',
        color: statusColor.value,
        offsetCenter: [0, 0],
      },
      data: [{ value: props.value }],
    }],
  }, true)
}

onMounted(() => {
  if (chartRef.value) {
    chart.value = echarts.init(chartRef.value)
    render()
  }
})

watch(() => props.value, render)

onBeforeUnmount(() => chart.value?.dispose())
</script>

<style scoped>
.completeness-ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.completeness-ring__label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  text-align: center;
}
</style>
