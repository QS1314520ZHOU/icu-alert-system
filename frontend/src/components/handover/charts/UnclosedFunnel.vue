<template>
  <div class="unclosed-funnel">
    <div class="funnel-header">
      <h3 class="funnel-title">未闭环事项漏斗</h3>
    </div>
    <div ref="chartRef" class="funnel-chart"></div>
    <div class="funnel-caption">
      展示危急值从发现到闭环的各阶段数量。每一级可点击查看明细。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

interface FunnelData {
  critical_total: number
  notified: number
  confirmed: number
  handled: number
  reassessed: number
  closed: number
}

const props = defineProps<{ data: FunnelData }>()
const emit = defineEmits<{ select: [stage: string, count: number] }>()
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

const stages = [
  { key: 'critical_total', label: '危急值', color: '#D92D20' },
  { key: 'notified', label: '已通知', color: '#F79009' },
  { key: 'confirmed', label: '已确认', color: '#E5B700' },
  { key: 'handled', label: '已处理', color: '#2E90FA' },
  { key: 'reassessed', label: '已复评', color: '#7A5AF8' },
  { key: 'closed', label: '已闭环', color: '#12A66A' },
]

function buildOption() {
  const d = props.data || {} as FunnelData
  const funnelData = stages.map(s => ({
    name: s.label,
    value: (d as any)[s.key] || 0,
    itemStyle: { color: s.color },
    stageKey: s.key,
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c}条',
    },
    series: [{
      type: 'funnel',
      left: '10%',
      width: '80%',
      top: 10,
      bottom: 10,
      min: 0,
      sort: 'descending',
      gap: 2,
      label: {
        show: true,
        position: 'inside',
        formatter: '{b}\n{c}',
        fontSize: 12,
        color: '#fff',
      },
      data: funnelData,
    }],
  }
}

function render() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params: any) => {
      if (params.data?.stageKey) emit('select', params.data.stageKey, params.data.value)
    })
  }
  chart.setOption(buildOption(), true)
}

onMounted(() => { nextTick(render) })
watch(() => props.data, () => nextTick(render), { deep: true })
</script>

<style scoped>
.unclosed-funnel { background: #fff; border-radius: 8px; border: 1px solid #DCE5EF; padding: 16px; }
.funnel-header { margin-bottom: 8px; }
.funnel-title { font-size: 14px; font-weight: 600; color: #17233D; margin: 0; }
.funnel-chart { width: 100%; height: 240px; }
.funnel-caption { font-size: 12px; color: #8A94A6; margin-top: 8px; border-top: 1px solid #F0F3F7; padding-top: 8px; }
</style>
