<template>
  <div class="alert-funnel">
    <div class="alert-funnel__header">
      <span class="alert-funnel__title">{{ title ?? '告警处置漏斗' }}</span>
    </div>

    <div class="alert-funnel__body" ref="chartRef" :style="{ height: height + 'px' }" />

    <ClinicalEmptyState
      v-if="loading"
      type="loading"
      message="告警数据加载中"
      size="small"
    />
    <ClinicalEmptyState
      v-else-if="!hasData"
      type="no-data"
      message="过去24小时无告警"
      size="small"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { FunnelChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { FONT_FAMILY } from '../../../styles/tokens/typography'
import ClinicalEmptyState from '../base/ClinicalEmptyState.vue'

echarts.use([FunnelChart, TooltipComponent, LegendComponent, CanvasRenderer])

export interface FunnelStage {
  name: string
  value: number
  color?: string
  /** 该阶段点击路由 */
  route?: string
}

const props = withDefaults(defineProps<{
  title?: string
  stages: FunnelStage[]
  height?: number
  loading?: boolean
}>(), {
  height: 300,
})

const emit = defineEmits<{ stageClick: [FunnelStage] }>()

const chartRef = ref<HTMLElement>()
const chart = shallowRef<echarts.ECharts>()
const hasData = computed(() => props.stages.some(s => s.value > 0))

const defaultColors = ['#D92D20', '#F79009', '#1677FF', '#12A66A', '#27B3B8']

function render() {
  if (!chart.value || !hasData.value) return

  chart.value.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#DCE5EF',
      borderWidth: 1,
      textStyle: { color: '#17233D', fontSize: 12, fontFamily: FONT_FAMILY.primary },
      extraCssText: 'box-shadow: 0 4px 12px rgba(16,24,40,0.08); border-radius: 8px;',
      formatter: (p: any) => `${p.name}: <b>${p.value}</b> (${p.percent}%)`,
    },
    series: [{
      type: 'funnel',
      left: '10%',
      top: 10,
      bottom: 10,
      width: '80%',
      min: 0,
      max: Math.max(...props.stages.map(s => s.value)),
      minSize: '20%',
      maxSize: '100%',
      sort: 'descending',
      gap: 4,
      label: {
        show: true,
        position: 'inside',
        formatter: '{b}: {c}',
        fontSize: 12,
        fontFamily: FONT_FAMILY.primary,
        color: '#fff',
      },
      data: props.stages.map((s, i) => ({
        name: s.name,
        value: s.value,
        itemStyle: { color: s.color ?? defaultColors[i % defaultColors.length] },
        stage: s,
      })),
    }],
  }, true)
}

onMounted(() => {
  if (chartRef.value) {
    chart.value = echarts.init(chartRef.value)
    render()
    chart.value.on('click', (params: any) => {
      if (params.data?.stage) emit('stageClick', params.data.stage)
    })
  }
})

watch(() => props.stages, render, { deep: true })

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
.alert-funnel {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 8px;
  padding: 16px;
}

.alert-funnel__header {
  margin-bottom: 12px;
}

.alert-funnel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
}
</style>
