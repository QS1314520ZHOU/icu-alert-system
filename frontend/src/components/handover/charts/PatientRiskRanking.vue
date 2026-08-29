<template>
  <div class="patient-risk-ranking">
    <div class="ranking-header">
      <h3 class="ranking-title">患者风险排序</h3>
    </div>
    <div ref="chartRef" class="ranking-chart"></div>
    <div class="ranking-caption">
      根据危急告警、生命支持、未闭环任务等因素排序。排序依据显示在条形右侧。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

interface PatientRisk {
  patient_id: string
  bed: string
  name: string
  risk_score: number
  risk_factors: string[]
}

const props = defineProps<{ patients: PatientRisk[] }>()
const emit = defineEmits<{ select: [patientId: string] }>()
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function scoreColor(score: number) {
  if (score >= 80) return '#D92D20'
  if (score >= 60) return '#F79009'
  if (score >= 40) return '#E5B700'
  return '#12A66A'
}

function buildOption() {
  const sorted = [...(props.patients || [])].sort((a, b) => a.risk_score - b.risk_score)
  const top10 = sorted.slice(0, 10)

  return {
    grid: { left: 80, right: 100, top: 8, bottom: 8 },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: '#5F6B7A', fontSize: 11 },
      splitLine: { lineStyle: { color: '#F0F3F7' } },
    },
    yAxis: {
      type: 'category',
      data: top10.map(p => `${p.bed}床 ${p.name}`),
      axisLabel: { color: '#17233D', fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const p = top10[params.dataIndex]
        if (!p) return ''
        return `<b>${p.bed}床 ${p.name}</b><br/>风险分：${p.risk_score}<br/>因素：${p.risk_factors.join('、')}`
      },
    },
    series: [{
      type: 'bar',
      data: top10.map(p => ({
        value: p.risk_score,
        itemStyle: { color: scoreColor(p.risk_score), borderRadius: [0, 4, 4, 0] },
        patientId: p.patient_id,
      })),
      barWidth: 20,
      label: {
        show: true,
        position: 'right',
        formatter: (params: any) => {
          const p = top10[params.dataIndex]
          return p ? p.risk_factors.slice(0, 2).join(' ') : ''
        },
        fontSize: 11,
        color: '#5F6B7A',
      },
    }],
  }
}

function render() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params: any) => {
      if (params.data?.patientId) emit('select', params.data.patientId)
    })
  }
  chart.setOption(buildOption(), true)
}

onMounted(() => { nextTick(render) })
watch(() => props.patients, () => nextTick(render), { deep: true })
</script>

<style scoped>
.patient-risk-ranking { background: #fff; border-radius: 8px; border: 1px solid #DCE5EF; padding: 16px; }
.ranking-header { margin-bottom: 8px; }
.ranking-title { font-size: 14px; font-weight: 600; color: #17233D; margin: 0; }
.ranking-chart { width: 100%; height: 280px; }
.ranking-caption { font-size: 12px; color: #8A94A6; margin-top: 8px; border-top: 1px solid #F0F3F7; padding-top: 8px; }
</style>
