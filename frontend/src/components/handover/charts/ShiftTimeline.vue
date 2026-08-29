<template>
  <div class="shift-timeline">
    <div class="timeline-header">
      <h3 class="timeline-title">本班关键变化时间线</h3>
    </div>
    <div ref="chartRef" class="timeline-chart"></div>
    <div class="timeline-caption">
      展示本班次内发生的临床关键事件。点击事件可查看患者详情。
      数据范围：{{ timeRange }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

interface TimelineEvent {
  time: string
  event: string
  patient_id?: string
  bed?: string
  severity?: string
}

const props = defineProps<{
  events: TimelineEvent[]
  timeRange?: string
}>()

const emit = defineEmits<{ select: [event: TimelineEvent] }>()
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

const severityColor: Record<string, string> = {
  critical: '#D92D20',
  high: '#F79009',
  medium: '#E5B700',
  info: '#2E90FA',
  stable: '#12A66A',
}

function buildOption() {
  const events = props.events || []
  const data = events.map((e, i) => ({
    value: [e.time, i],
    itemStyle: { color: severityColor[e.severity || 'info'] || '#2E90FA' },
    eventData: e,
  }))

  return {
    grid: { left: 80, right: 24, top: 16, bottom: 32 },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#DCE5EF' } },
      axisLabel: { color: '#5F6B7A', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      show: false,
      min: -1,
      max: events.length,
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const d = params.data?.eventData
        if (!d) return ''
        return `<b>${d.bed || ''}床</b><br/>${d.event}<br/>${d.time}`
      },
    },
    series: [{
      type: 'scatter',
      data,
      symbolSize: 12,
      label: {
        show: true,
        position: 'right',
        formatter: (params: any) => {
          const d = params.data?.eventData
          return d ? `${d.bed || ''} ${d.event}` : ''
        },
        fontSize: 11,
        color: '#17233D',
      },
    }],
  }
}

function render() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params: any) => {
      if (params.data?.eventData) emit('select', params.data.eventData)
    })
  }
  chart.setOption(buildOption(), true)
}

onMounted(() => { nextTick(render) })
watch(() => props.events, () => nextTick(render), { deep: true })
</script>

<style scoped>
.shift-timeline { background: #fff; border-radius: 8px; border: 1px solid #DCE5EF; padding: 16px; }
.timeline-header { margin-bottom: 8px; }
.timeline-title { font-size: 14px; font-weight: 600; color: #17233D; margin: 0; }
.timeline-chart { width: 100%; height: 240px; }
.timeline-caption { font-size: 12px; color: #8A94A6; margin-top: 8px; border-top: 1px solid #F0F3F7; padding-top: 8px; }
</style>
