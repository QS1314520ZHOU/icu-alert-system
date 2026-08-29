<template>
  <div class="risk-matrix">
    <div class="risk-matrix__header">
      <span class="risk-matrix__title">{{ title ?? '患者风险矩阵' }}</span>
      <span class="risk-matrix__legend">
        <span class="risk-matrix__legend-item" v-for="l in legendItems" :key="l.label">
          <span class="risk-matrix__legend-dot" :style="{ background: l.color, width: l.size + 'px', height: l.size + 'px' }" />
          {{ l.label }}
        </span>
      </span>
    </div>

    <div class="risk-matrix__body" ref="chartRef" :style="{ height: height + 'px' }" />

    <ClinicalEmptyState
      v-if="loading"
      type="loading"
      message="患者数据加载中"
      size="small"
    />
    <ClinicalEmptyState
      v-else-if="!patients.length"
      type="no-data"
      message="暂无在科患者"
      size="small"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, shallowRef, computed } from 'vue'
import * as echarts from 'echarts/core'
import { ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { RISK_MAP, type RiskLevel, getRiskLevel } from '../../../styles/tokens/risk'
import { FONT_FAMILY } from '../../../styles/tokens/typography'
import ClinicalEmptyState from '../base/ClinicalEmptyState.vue'

echarts.use([ScatterChart, GridComponent, TooltipComponent, CanvasRenderer])

export interface MatrixPatient {
  id: string
  name: string
  bedNo: string
  diagnosis: string
  /** 当前风险分数 0-100 */
  riskScore: number
  /** 风险变化速度（正数上升，负数下降） */
  riskVelocity: number
  /** 未处理问题数量 */
  pendingIssues: number
  riskLevel?: RiskLevel
}

const props = withDefaults(defineProps<{
  title?: string
  patients: MatrixPatient[]
  height?: number
  loading?: boolean
}>(), {
  height: 360,
})

const emit = defineEmits<{ patientClick: [MatrixPatient] }>()

const chartRef = ref<HTMLElement>()
const chart = shallowRef<echarts.ECharts>()

const legendItems = computed(() => [
  { color: RISK_MAP.critical.color, label: '危急', size: 8 },
  { color: RISK_MAP.high.color, label: '高风险', size: 8 },
  { color: RISK_MAP.medium.color, label: '中风险', size: 8 },
  { color: RISK_MAP.low.color, label: '低/稳定', size: 8 },
])

function render() {
  if (!chart.value || !props.patients.length) return

  // 按风险等级分组
  const groups = new Map<string, MatrixPatient[]>()
  props.patients.forEach(p => {
    const level = p.riskLevel ?? getRiskLevel(p.riskScore)
    if (!groups.has(level)) groups.set(level, [])
    groups.get(level)!.push(p)
  })

  const series: any[] = []
  groups.forEach((patients, level) => {
    const visual = RISK_MAP[level as RiskLevel] ?? RISK_MAP.unknown
    series.push({
      name: visual.label,
      type: 'scatter',
      data: patients.map(p => ({
        value: [p.riskScore, p.riskVelocity, p.pendingIssues ?? 0],
        patient: p,
      })),
      symbolSize: (val: number[]) => Math.max(8, Math.min(30, 8 + (val[2] ?? 0) * 3)),
      itemStyle: { color: visual.color, opacity: 0.8 },
      emphasis: { itemStyle: { opacity: 1, borderColor: '#fff', borderWidth: 2 } },
    })
  })

  chart.value.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#DCE5EF',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: '#17233D', fontSize: 12, fontFamily: FONT_FAMILY.primary },
      extraCssText: 'box-shadow: 0 4px 12px rgba(16,24,40,0.08); border-radius: 8px;',
      formatter: (params: any) => {
        const p = params.data.patient as MatrixPatient
        const level = p.riskLevel ?? getRiskLevel(p.riskScore)
        const visual = RISK_MAP[level as RiskLevel] ?? RISK_MAP.unknown
        return `<div style="font-weight:600">${p.bedNo} ${p.name}</div>
          <div style="font-size:12px;color:#5F6B7A">${p.diagnosis}</div>
          <div style="margin-top:4px">风险: <b style="color:${visual.color}">${p.riskScore}分</b></div>
          <div>变化: ${p.riskVelocity > 0 ? '↑' : p.riskVelocity < 0 ? '↓' : '→'} ${Math.abs(p.riskVelocity)}</div>
          <div>待处理: ${p.pendingIssues}项</div>`
      },
    },
    legend: { show: false },
    grid: { left: 16, right: 16, top: 16, bottom: 16, containLabel: true },
    xAxis: {
      type: 'value',
      name: '当前风险',
      nameLocation: 'center',
      nameGap: 30,
      nameTextStyle: { color: '#5F6B7A', fontSize: 12 },
      min: 0,
      max: 100,
      axisLabel: { color: '#8A94A6', fontSize: 11 },
      splitLine: { lineStyle: { color: '#E8EEF5', type: 'dashed' } },
    },
    yAxis: {
      type: 'value',
      name: '风险变化速度',
      nameLocation: 'center',
      nameGap: 40,
      nameTextStyle: { color: '#5F6B7A', fontSize: 12 },
      axisLabel: { color: '#8A94A6', fontSize: 11 },
      splitLine: { lineStyle: { color: '#E8EEF5', type: 'dashed' } },
    },
    series,
  }, true)
}

onMounted(() => {
  if (chartRef.value) {
    chart.value = echarts.init(chartRef.value)
    render()
    chart.value.on('click', (params: any) => {
      if (params.data?.patient) emit('patientClick', params.data.patient)
    })
  }
})

watch(() => props.patients, render, { deep: true })

let resizeObserver: ResizeObserver | undefined
onMounted(() => {
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart.value?.resize())
    resizeObserver.observe(chartRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart.value?.dispose()
})
</script>

<style scoped>
.risk-matrix {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 8px;
  padding: 16px;
}

.risk-matrix__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.risk-matrix__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
}

.risk-matrix__legend {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-secondary, #667085);
}

.risk-matrix__legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.risk-matrix__legend-dot {
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
