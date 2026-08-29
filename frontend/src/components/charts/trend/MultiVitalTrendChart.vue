<template>
  <div class="multi-vital">
    <div class="multi-vital__header">
      <span class="multi-vital__title">{{ title ?? '生命体征趋势' }}</span>
      <div class="multi-vital__controls">
        <a-checkbox-group v-model:value="visibleMetrics" :options="metricOptions" size="small" />
        <a-radio-group v-model:value="selectedRange" size="small" button-style="solid">
          <a-radio-button v-for="r in timeRanges" :key="r.value" :value="r.value">{{ r.label }}</a-radio-button>
        </a-radio-group>
      </div>
    </div>

    <div class="multi-vital__body" ref="chartRef" :style="{ height: height + 'px' }" />

    <ClinicalEmptyState
      v-if="loading"
      type="loading"
      message="生命体征数据加载中"
      size="small"
    />
    <ClinicalEmptyState
      v-else-if="!hasData"
      type="no-data"
      message="暂无生命体征数据，请检查监护仪连接"
      size="small"
    />

    <ChartExplanation
      v-if="explanation && hasData"
      :description="explanation.description"
      :key-finding="explanation.keyFinding"
      :source="explanation.source"
      :data-time="explanation.dataTime"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Checkbox as ACheckbox, Radio as ARadio } from 'ant-design-vue'
import { METRIC } from '../../../styles/tokens/colors'
import { FONT_FAMILY } from '../../../styles/tokens/typography'
import ChartExplanation from '../base/ChartExplanation.vue'
import ClinicalEmptyState from '../base/ClinicalEmptyState.vue'

const ACheckboxGroup = ACheckbox.Group
const ARadioGroup = ARadio.Group
const ARadioButton = ARadio.Button

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, CanvasRenderer])

export interface VitalMetric {
  key: string
  name: string
  data: number[]
  unit: string
  color?: string
  normalRange?: [number, number]
  /** Y轴索引（用于多Y轴） */
  yAxisIndex?: number
}

export interface VitalExplanation {
  description: string
  keyFinding?: string
  source?: string
  dataTime?: string
}

const props = withDefaults(defineProps<{
  title?: string
  xData: string[]
  metrics: VitalMetric[]
  height?: number
  timeRanges?: { label: string; value: string }[]
  defaultRange?: string
  events?: { xAxis: string; label: string; color?: string }[]
  loading?: boolean
  explanation?: VitalExplanation
}>(), {
  height: 400,
  timeRanges: () => [
    { label: '6h', value: '6h' },
    { label: '12h', value: '12h' },
    { label: '24h', value: '24h' },
    { label: '72h', value: '72h' },
  ],
})

const emit = defineEmits<{ rangeChange: [string]; retry: [] }>()

const chartRef = ref<HTMLElement>()
const chart = shallowRef<echarts.ECharts>()
const selectedRange = ref(props.defaultRange ?? '24h')
const visibleMetrics = ref(props.metrics.map(m => m.key))

const hasData = computed(() => props.metrics.some(m => m.data.length > 0))

const metricOptions = computed(() =>
  props.metrics.map(m => ({ label: m.name, value: m.key }))
)

function getMetricColor(m: VitalMetric): string {
  const key = m.key.toLowerCase().replace(/[^a-z]/g, '')
  return m.color ?? (METRIC as any)[key] ?? '#1677FF'
}

function render() {
  if (!chart.value || !hasData.value) return

  // 计算需要几个Y轴
  const visibleM = props.metrics.filter(m => visibleMetrics.value.includes(m.key))
  const yAxisCount = Math.min(visibleM.length, 3) // 最多3个Y轴

  const yAxes: any[] = []
  for (let i = 0; i < yAxisCount; i++) {
    yAxes.push({
      type: 'value',
      position: i === 0 ? 'left' : i === 1 ? 'right' : 'right',
      offset: i === 2 ? 60 : 0,
      axisLine: { show: false },
      axisLabel: { color: '#8A94A6', fontSize: 10, fontFamily: FONT_FAMILY.primary },
      splitLine: i === 0 ? { lineStyle: { color: '#E8EEF5', type: 'dashed' } } : { show: false },
    })
  }

  const series = visibleM.map((m, i) => {
    const color = getMetricColor(m)
    const seriesConfig: any = {
      name: m.name,
      type: 'line',
      data: m.data,
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      showSymbol: false,
      lineStyle: { width: 2, color },
      itemStyle: { color },
      yAxisIndex: m.yAxisIndex ?? Math.min(i, yAxisCount - 1),
    }
    if (m.normalRange) {
      seriesConfig.markArea = {
        silent: true,
        data: [[{ yAxis: m.normalRange[0], itemStyle: { color: color + '08' } }, { yAxis: m.normalRange[1] }]],
      }
    }
    return seriesConfig
  })

  // 添加事件标记线到第一个系列
  if (props.events?.length && series.length > 0) {
    series[0].markLine = {
      silent: true,
      symbol: 'none',
      data: props.events.map(ev => ({
        xAxis: ev.xAxis,
        lineStyle: { color: ev.color ?? '#1677FF', type: 'dashed', width: 1 },
        label: { formatter: ev.label, fontSize: 10, color: ev.color ?? '#1677FF', position: 'insideEndTop' },
      })),
    }
  }

  chart.value.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#DCE5EF',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: '#17233D', fontSize: 12, fontFamily: FONT_FAMILY.primary },
      extraCssText: 'box-shadow: 0 4px 12px rgba(16,24,40,0.08); border-radius: 8px;',
      formatter: (params: any) => {
        if (!Array.isArray(params)) return ''
        let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        params.forEach((p: any) => {
          const m = visibleM.find(m => m.name === p.seriesName)
          html += `<div style="display:flex;align-items:center;gap:4px;font-size:12px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>${p.seriesName}: <b>${p.value}</b> ${m?.unit ?? ''}</div>`
        })
        return html
      },
    },
    legend: {
      top: 0,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: '#5F6B7A', fontSize: 12, fontFamily: FONT_FAMILY.primary },
    },
    grid: { left: 12, right: 16, top: 40, bottom: 12, containLabel: true },
    xAxis: {
      type: 'category',
      data: props.xData,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#DCE5EF' } },
      axisLabel: { color: '#8A94A6', fontSize: 11, fontFamily: FONT_FAMILY.primary },
    },
    yAxis: yAxes,
    series,
  }, true)
}

onMounted(() => {
  if (chartRef.value) {
    chart.value = echarts.init(chartRef.value)
    render()
  }
})

watch(() => [props.metrics, props.xData, props.events, visibleMetrics.value], render, { deep: true })
watch(selectedRange, v => emit('rangeChange', v))

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
.multi-vital {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 8px;
  padding: 16px;
}

.multi-vital__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.multi-vital__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
}

.multi-vital__controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.multi-vital__body {
  width: 100%;
}
</style>
