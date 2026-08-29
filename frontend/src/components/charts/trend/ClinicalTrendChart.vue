<template>
  <div class="trend-chart">
    <div class="trend-chart__header">
      <span class="trend-chart__title">{{ title }}</span>
      <div class="trend-chart__controls">
        <a-radio-group v-if="timeRanges" v-model:value="selectedRange" size="small" button-style="solid">
          <a-radio-button v-for="r in timeRanges" :key="r.value" :value="r.value">{{ r.label }}</a-radio-button>
        </a-radio-group>
      </div>
    </div>

    <div class="trend-chart__body" ref="chartRef" :style="{ height: height + 'px' }" />

    <ClinicalEmptyState
      v-if="loading"
      type="loading"
      message="趋势数据加载中"
      size="small"
    />
    <ClinicalEmptyState
      v-else-if="error"
      type="error"
      :message="error"
      size="small"
      action-text="重试"
      @action="$emit('retry')"
    />
    <ClinicalEmptyState
      v-else-if="!hasData"
      type="no-data"
      :message="emptyMessage ?? '暂无趋势数据'"
      size="small"
    />

    <ChartExplanation
      v-if="explanation && hasData"
      :description="explanation.description"
      :key-finding="explanation.keyFinding"
      :source="explanation.source"
      :data-time="explanation.dataTime"
      :raw-data-route="explanation.rawDataRoute"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Radio as ARadio } from 'ant-design-vue'
import { lineChartBase, getChartColor } from '../../../charts/icuTheme'
import { METRIC } from '../../../styles/tokens/colors'
import ChartExplanation from '../base/ChartExplanation.vue'
import ClinicalEmptyState from '../base/ClinicalEmptyState.vue'

const ARadioGroup = ARadio.Group
const ARadioButton = ARadio.Button

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, DataZoomComponent, CanvasRenderer])

export interface TrendSeries {
  name: string
  data: number[]
  color?: string
  unit?: string
  normalRange?: [number, number]
  /** Y轴索引，支持多Y轴 */
  yAxisIndex?: number
}

export interface ChartExplanationData {
  description: string
  keyFinding?: string
  source?: string
  dataTime?: string
  rawDataRoute?: string
}

const props = withDefaults(defineProps<{
  /** 图表标题 */
  title?: string
  /** X轴时间标签 */
  xData: string[]
  /** 数据系列 */
  series: TrendSeries[]
  /** 图表高度 */
  height?: number
  /** 时间范围选项 */
  timeRanges?: { label: string; value: string }[]
  /** 默认时间范围 */
  defaultRange?: string
  /** 是否显示区域填充 */
  areaFill?: boolean
  /** 是否显示dataZoom */
  dataZoom?: boolean
  /** 多Y轴配置 */
  multiYAxis?: boolean
  /** 事件标记 [{xAxis, label, color}] */
  events?: { xAxis: string; label: string; color?: string }[]
  /** 加载中 */
  loading?: boolean
  /** 错误信息 */
  error?: string
  /** 空状态提示 */
  emptyMessage?: string
  /** 图表说明 */
  explanation?: ChartExplanationData
}>(), {
  height: 360,
  areaFill: true,
})

const emit = defineEmits<{ retry: []; rangeChange: [string] }>()

const chartRef = ref<HTMLElement>()
const chart = shallowRef<echarts.ECharts>()
const selectedRange = ref(props.defaultRange ?? props.timeRanges?.[0]?.value ?? '')

const hasData = computed(() => props.series.some(s => s.data.length > 0))

function getColor(s: TrendSeries, i: number): string {
  // 优先使用指标固定颜色
  const metricKey = s.name.toLowerCase().replace(/[^a-z]/g, '')
  const metricColor = (METRIC as any)[metricKey]
  return s.color ?? metricColor ?? getChartColor(i)
}

function render() {
  if (!chart.value || !hasData.value) return

  const yAxes: any[] = [{ type: 'value', axisLine: { show: false }, axisLabel: { color: '#8A94A6', fontSize: 11 }, splitLine: { lineStyle: { color: '#E8EEF5', type: 'dashed' } } }]

  if (props.multiYAxis && props.series.length > 1) {
    yAxes.push({ type: 'value', axisLine: { show: false }, axisLabel: { color: '#8A94A6', fontSize: 11 }, splitLine: { show: false } })
  }

  const chartSeries = props.series.map((s, i) => {
    const color = getColor(s, i)
    const base: any = {
      name: s.name,
      type: 'line',
      data: s.data,
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      showSymbol: false,
      lineStyle: { width: 2, color },
      itemStyle: { color },
      yAxisIndex: s.yAxisIndex ?? 0,
    }
    if (props.areaFill) {
      base.areaStyle = { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: color + '20' }, { offset: 1, color: color + '02' }]) }
    }
    if (s.normalRange) {
      base.markArea = {
        silent: true,
        data: [[{ yAxis: s.normalRange[0], itemStyle: { color: 'rgba(18,166,106,0.06)' } }, { yAxis: s.normalRange[1] }]],
      }
    }
    return base
  })

  // 添加事件标记线
  if (props.events?.length) {
    const firstSeries = chartSeries[0]
    if (!firstSeries.markLine) {
      firstSeries.markLine = { silent: true, symbol: 'none', data: [] }
    }
    props.events.forEach(ev => {
      firstSeries.markLine.data.push({
        xAxis: ev.xAxis,
        lineStyle: { color: ev.color ?? '#1677FF', type: 'dashed', width: 1 },
        label: { formatter: ev.label, fontSize: 10, color: ev.color ?? '#1677FF' },
      })
    })
  }

  const option: any = {
    ...lineChartBase(props.xData),
    yAxis: yAxes,
    series: chartSeries,
  }

  if (props.dataZoom) {
    option.dataZoom = [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 20, bottom: 0, start: 0, end: 100, borderColor: 'transparent', backgroundColor: '#F4F7FB', fillerColor: 'rgba(22,119,255,0.08)', handleStyle: { color: '#1677FF' } },
    ]
    option.grid.bottom = 40
  }

  chart.value.setOption(option, true)
}

onMounted(() => {
  if (chartRef.value) {
    chart.value = echarts.init(chartRef.value)
    render()
  }
})

watch(() => [props.series, props.xData, props.events], render, { deep: true })
watch(selectedRange, (v) => emit('rangeChange', v))

// ResizeObserver
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
.trend-chart {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 8px;
  padding: 16px;
}

.trend-chart__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.trend-chart__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
}

.trend-chart__body {
  width: 100%;
}
</style>
