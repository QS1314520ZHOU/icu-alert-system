<template>
  <div class="score-trend">
    <div class="score-trend__header">
      <span class="score-trend__title">{{ title ?? '评分趋势' }}</span>
      <span v-if="currentScore !== undefined" class="score-trend__current">
        <span class="score-trend__score-value" :style="{ color: scoreColor }">{{ currentScore }}</span>
        <span class="score-trend__score-label">{{ scoreName }}评分</span>
      </span>
    </div>

    <div class="score-trend__body" ref="chartRef" :style="{ height: height + 'px' }" />

    <ClinicalEmptyState
      v-if="loading"
      type="loading"
      message="评分数据加载中"
      size="small"
    />
    <ClinicalEmptyState
      v-else-if="!hasData"
      type="no-data"
      message="暂无评分数据"
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
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { lineChartBase, getChartColor } from '../../../charts/icuTheme'
import { SCORE } from '../../../styles/tokens/colors'
import ChartExplanation from '../base/ChartExplanation.vue'
import ClinicalEmptyState from '../base/ClinicalEmptyState.vue'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

export interface ScoreComponent {
  name: string
  data: number[]
  color?: string
}

export interface ScoreExplanation {
  description: string
  keyFinding?: string
  source?: string
  dataTime?: string
}

const props = withDefaults(defineProps<{
  /** 图表标题 */
  title?: string
  /** 评分名称 (SOFA/NEWS2/qSOFA) */
  scoreName?: string
  /** 评分版本 */
  scoreVersion?: string
  /** X轴时间标签 */
  xData: string[]
  /** 总分趋势 */
  totalScores: number[]
  /** 分项得分 */
  components?: ScoreComponent[]
  /** 当前总分 */
  currentScore?: number
  /** 图表高度 */
  height?: number
  /** 是否堆叠分项 */
  stacked?: boolean
  /** 加载中 */
  loading?: boolean
  /** 图表说明 */
  explanation?: ScoreExplanation
}>(), {
  scoreName: 'SOFA',
  height: 300,
})

const chartRef = ref<HTMLElement>()
const chart = shallowRef<echarts.ECharts>()
const hasData = computed(() => props.totalScores.length > 0)

const scoreColor = computed(() => {
  const key = props.scoreName.toLowerCase() as keyof typeof SCORE
  return SCORE[key] ?? '#1677FF'
})

function render() {
  if (!chart.value || !hasData.value) return

  const series: any[] = []

  // 分项堆叠柱状图
  if (props.components?.length && props.stacked) {
    props.components.forEach((comp, i) => {
      series.push({
        name: comp.name,
        type: 'bar',
        stack: 'score',
        data: comp.data,
        barWidth: '40%',
        itemStyle: { color: comp.color ?? getChartColor(i), borderRadius: [0, 0, 0, 0] },
      })
    })
    // 最顶层圆角
    if (series.length) {
      series[series.length - 1].itemStyle.borderRadius = [4, 4, 0, 0]
    }
  }

  // 总分趋势线
  series.push({
    name: `${props.scoreName}总分`,
    type: 'line',
    data: props.totalScores,
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { width: 2.5, color: scoreColor.value },
    itemStyle: { color: scoreColor.value },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: scoreColor.value + '20' },
        { offset: 1, color: scoreColor.value + '02' },
      ]),
    },
    z: 10,
  })

  chart.value.setOption({
    ...lineChartBase(props.xData),
    series,
  }, true)
}

onMounted(() => {
  if (chartRef.value) {
    chart.value = echarts.init(chartRef.value)
    render()
  }
})

watch(() => [props.totalScores, props.components, props.xData], render, { deep: true })

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
.score-trend {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 8px;
  padding: 16px;
}

.score-trend__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.score-trend__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
}

.score-trend__current {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.score-trend__score-value {
  font-family: 'Rajdhani', sans-serif;
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}

.score-trend__score-label {
  font-size: 12px;
  color: var(--color-text-tertiary, #8A94A6);
}
</style>
