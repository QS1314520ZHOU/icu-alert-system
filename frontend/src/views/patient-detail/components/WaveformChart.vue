<template>
  <div class="waveform-chart">
    <ClinicalChart
      :option="chartOption"
      :loading="false"
      :height="200"
      :updated-at="updatedAt"
      aria-label="波形数据图表"
    />
    <div class="waveform-chart__info">
      <span class="waveform-chart__source">数据来源：床旁监护设备</span>
      <span class="waveform-chart__freq">采样周期：{{ sampleInterval }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ClinicalChart from '../../../components/charts/base/ClinicalChart.vue'

const props = defineProps<{
  points: Array<{ time: string; value: number; [key: string]: any }>
  channel: string
  hours: number
}>()

const channelLabels: Record<string, string> = {
  hr: '心率 (bpm)',
  map: '平均动脉压 (mmHg)',
  spo2: '血氧饱和度 (%)',
  rr: '呼吸频率 (次/min)',
  temp: '体温 (°C)',
  sbp: '收缩压 (mmHg)',
  dbp: '舒张压 (mmHg)',
}

const channelUnits: Record<string, string> = {
  hr: 'bpm',
  map: 'mmHg',
  spo2: '%',
  rr: '次/min',
  temp: '°C',
  sbp: 'mmHg',
  dbp: 'mmHg',
}

const sampleInterval = computed(() => {
  if (!props.points.length) return '—'
  if (props.points.length < 2) return '—'
  const t0 = new Date(props.points[0].time).getTime()
  const t1 = new Date(props.points[1].time).getTime()
  const diffSec = Math.abs(t1 - t0) / 1000
  if (diffSec < 60) return `${Math.round(diffSec)}秒`
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}分钟`
  return `${Math.round(diffSec / 3600)}小时`
})

const updatedAt = computed(() => {
  if (!props.points.length) return ''
  const last = props.points[props.points.length - 1]
  try {
    return new Date(last.time).toLocaleString('zh-CN')
  } catch {
    return ''
  }
})

const chartOption = computed(() => {
  if (!props.points.length) return null

  const xData = props.points.map(p => {
    try {
      return new Date(p.time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } catch {
      return p.time
    }
  })
  const yData = props.points.map(p => p.value)
  const label = channelLabels[props.channel] || props.channel
  const unit = channelUnits[props.channel] || ''

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0]
        return `${p.axisValue}<br/>${label}: ${p.value} ${unit}`
      },
    },
    grid: { left: 50, right: 16, top: 16, bottom: 30 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { fontSize: 10 },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      name: unit,
      nameTextStyle: { fontSize: 10 },
      axisLabel: { fontSize: 10 },
    },
    series: [{
      name: label,
      type: 'line',
      data: yData,
      smooth: false,
      symbol: 'none',
      lineStyle: { width: 1.5, color: '#2563EB' },
      areaStyle: { color: 'rgba(37,99,235,0.06)' },
    }],
  }
})
</script>

<style scoped>
.waveform-chart {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.waveform-chart__info {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-tertiary, #94A3B8);
}
</style>
