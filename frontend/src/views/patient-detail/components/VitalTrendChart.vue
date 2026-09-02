<template>
  <div class="vital-trend-chart">
    <div v-if="loading" class="chart-loading">
      <a-spin />
      <span>加载趋势数据...</span>
    </div>
    <div v-else-if="!points.length" class="chart-empty">
      <a-empty description="暂无趋势数据" :image-style="{ height: '40px' }" />
    </div>
    <div v-else class="chart-content">
      <div class="chart-legend">
        <div v-for="item in legendItems" :key="item.key" class="legend-item" :class="{ inactive: !item.visible }" @click="toggleLegend(item.key)">
          <span class="legend-dot" :style="{ background: item.color }"></span>
          <span class="legend-label">{{ item.label }}</span>
        </div>
      </div>
      <div class="chart-area" ref="chartRef">
        <!-- 简化版SVG趋势图 -->
        <svg :width="chartWidth" :height="chartHeight" class="trend-svg">
          <!-- 网格线 -->
          <line v-for="i in 5" :key="`grid-${i}`"
            :x1="0" :y1="i * (chartHeight / 6)"
            :x2="chartWidth" :y2="i * (chartHeight / 6)"
            stroke="#f0f0f0" stroke-width="1"
          />
          <!-- 数据线 -->
          <polyline
            v-for="line in chartLines"
            :key="line.key"
            :points="line.points"
            fill="none"
            :stroke="line.color"
            stroke-width="2"
            stroke-linejoin="round"
          />
        </svg>
      </div>
      <div class="chart-info">
        <span class="info-window">{{ window }} 数据</span>
        <span class="info-points">{{ points.length }} 个数据点</span>
        <span v-if="forecastMeta?.model_name" class="info-forecast">预测模型: {{ forecastMeta.model_name }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps<{
  points: any[]
  loading: boolean
  forecastMeta?: any
  window: string
}>()

const chartRef = ref<HTMLElement | null>(null)
const chartWidth = ref(600)
const chartHeight = ref(200)

const colors: Record<string, string> = {
  hr: '#ff4d4f',
  map: '#1890ff',
  spo2: '#52c41a',
  rr: '#faad14',
  temp: '#722ed1',
  lactate: '#eb2f96',
}

const legendItems = computed(() => {
  const keys = new Set<string>()
  props.points.forEach((p: any) => {
    Object.keys(p).forEach(k => {
      if (k !== 'time' && k !== 'timestamp' && p[k] != null) keys.add(k)
    })
  })
  return Array.from(keys).map(key => ({
    key,
    label: key.toUpperCase(),
    color: colors[key.toLowerCase()] || '#999',
    visible: true,
  }))
})

const visibleKeys = ref<Set<string>>(new Set())

// 异步数据到达后同步 visibleKeys
watch(legendItems, (items) => {
  if (items.length && visibleKeys.value.size === 0) {
    items.forEach(item => visibleKeys.value.add(item.key))
  }
}, { immediate: true })

const chartLines = computed(() => {
  if (!props.points.length) return []
  const keys = Array.from(visibleKeys.value)
  if (!keys.length) return []

  const timeRange = props.points.length
  const xStep = chartWidth.value / Math.max(timeRange - 1, 1)

  return keys.map(key => {
    const values = props.points.map((p: any) => Number(p[key])).filter(v => !isNaN(v))
    if (!values.length) return { key, points: '', color: colors[key.toLowerCase()] || '#999' }

    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    const yPadding = 20

    const pointsStr = props.points.map((p: any, i: number) => {
      const val = Number(p[key])
      if (isNaN(val)) return ''
      const x = i * xStep
      const y = yPadding + (1 - (val - min) / range) * (chartHeight.value - 2 * yPadding)
      return `${x},${y}`
    }).filter(Boolean).join(' ')

    return {
      key,
      points: pointsStr,
      color: colors[key.toLowerCase()] || '#999',
    }
  })
})

function toggleLegend(key: string) {
  if (visibleKeys.value.has(key)) {
    visibleKeys.value.delete(key)
  } else {
    visibleKeys.value.add(key)
  }
}

onMounted(() => {
  // 监听resize — 用 nextTick 确保 v-else 分支已渲染
  nextTick(() => {
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        chartWidth.value = entry.contentRect.width
      }
    })
    if (chartRef.value) observer.observe(chartRef.value)
    onUnmounted(() => observer.disconnect())
  })
})
</script>

<style scoped>
.vital-trend-chart {
  min-height: 200px;
}

.chart-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: #999;
}

.chart-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #666;
  transition: opacity 0.2s;
}

.legend-item.inactive {
  opacity: 0.4;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.chart-area {
  width: 100%;
  overflow: hidden;
}

.trend-svg {
  width: 100%;
  height: auto;
}

.chart-info {
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: #999;
}

.info-forecast {
  color: #1890ff;
}
</style>
