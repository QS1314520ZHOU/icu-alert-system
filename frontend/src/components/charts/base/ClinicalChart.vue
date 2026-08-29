<template>
  <div class="clinical-chart" :style="{ height: height + 'px' }">
    <!-- 图表容器 -->
    <div ref="chartRef" class="clinical-chart__canvas" :aria-label="ariaLabel"></div>

    <!-- 加载状态 -->
    <div v-if="loading" class="clinical-chart__loading">
      <div class="clinical-chart__spinner"></div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && isEmpty" class="clinical-chart__empty">
      <span class="clinical-chart__empty-icon">📊</span>
      <span class="clinical-chart__empty-text">{{ emptyText }}</span>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="clinical-chart__error">
      <span class="clinical-chart__error-icon">⚠</span>
      <span class="clinical-chart__error-text">{{ error }}</span>
      <button class="clinical-chart__retry" @click="$emit('retry')">重试</button>
    </div>

    <!-- 工具栏 -->
    <div v-if="showToolbar && !loading && !isEmpty" class="clinical-chart__toolbar">
      <button title="导出PNG" @click="handleExportPNG" class="clinical-chart__tool-btn">📷</button>
      <button title="导出SVG" @click="handleExportSVG" class="clinical-chart__tool-btn">📐</button>
      <button v-if="description" title="图表说明" @click="showDescription = !showDescription" class="clinical-chart__tool-btn">❓</button>
    </div>

    <!-- 图表说明 -->
    <div v-if="showDescription && description" class="clinical-chart__desc">
      {{ description }}
    </div>

    <!-- 数据更新时间 -->
    <div v-if="updatedAt" class="clinical-chart__time">
      {{ updatedAt }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import type { EChartsOption } from 'echarts'
import { useClinicalChart } from '../../../composables/useClinicalChart'

const props = withDefaults(defineProps<{
  option?: EChartsOption | null
  loading?: boolean
  error?: string
  height?: number
  emptyText?: string
  description?: string
  updatedAt?: string
  ariaLabel?: string
  showToolbar?: boolean
}>(), {
  loading: false,
  error: '',
  height: 300,
  emptyText: '暂无数据',
  ariaLabel: '临床数据图表',
  showToolbar: false,
})

defineEmits<{
  (e: 'retry'): void
}>()

const chartRef = ref<HTMLElement | null>(null)
const showDescription = ref(false)

const isEmpty = computed(() => {
  if (props.loading || props.error) return false
  if (!props.option) return true
  // 检查 series 是否为空
  const series = (props.option as any)?.series
  if (!series) return true
  if (Array.isArray(series)) {
    return series.every((s: any) => !s.data || s.data.length === 0)
  }
  return !series.data || series.data.length === 0
})

const { exportPNG, exportSVG } = useClinicalChart({
  containerRef: chartRef,
  option: toRef(props, 'option'),
  loading: toRef(props, 'loading'),
  height: props.height,
  autoresize: true,
})

function handleExportPNG() {
  const url = exportPNG(2)
  if (url) downloadDataUrl(url, 'chart.png')
}

function handleExportSVG() {
  const url = exportSVG()
  if (url) downloadDataUrl(url, 'chart.svg')
}

function downloadDataUrl(dataUrl: string, filename: string) {
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  a.click()
}
</script>

<style scoped>
.clinical-chart {
  position: relative;
  width: 100%;
  min-height: 100px;
}

.clinical-chart__canvas {
  width: 100%;
  height: 100%;
}

/* Loading */
.clinical-chart__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.7);
  z-index: 2;
}

.clinical-chart__spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #E8EEF5;
  border-top-color: #2563EB;
  border-radius: 50%;
  animation: chart-spin 0.8s linear infinite;
}

@keyframes chart-spin {
  to { transform: rotate(360deg); }
}

/* Empty */
.clinical-chart__empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  z-index: 1;
}

.clinical-chart__empty-icon {
  font-size: 32px;
  opacity: 0.4;
}

.clinical-chart__empty-text {
  font-size: 13px;
  color: #94A3B8;
}

/* Error */
.clinical-chart__error {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  z-index: 1;
}

.clinical-chart__error-icon {
  font-size: 28px;
}

.clinical-chart__error-text {
  font-size: 13px;
  color: #DC2626;
}

.clinical-chart__retry {
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid #DCE3EC;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}

.clinical-chart__retry:hover {
  background: #F0F6FF;
}

/* Toolbar */
.clinical-chart__toolbar {
  position: absolute;
  top: 4px;
  right: 4px;
  display: flex;
  gap: 2px;
  z-index: 3;
  opacity: 0;
  transition: opacity 0.2s;
}

.clinical-chart:hover .clinical-chart__toolbar {
  opacity: 1;
}

.clinical-chart__tool-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: rgba(255,255,255,0.8);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.clinical-chart__tool-btn:hover {
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}

/* Description */
.clinical-chart__desc {
  position: absolute;
  bottom: 24px;
  left: 8px;
  right: 8px;
  padding: 8px 12px;
  background: rgba(255,255,255,0.95);
  border: 1px solid #E8EEF5;
  border-radius: 6px;
  font-size: 12px;
  color: #52606D;
  line-height: 1.5;
  z-index: 4;
}

/* Update time */
.clinical-chart__time {
  position: absolute;
  bottom: 2px;
  right: 8px;
  font-size: 10px;
  color: #94A3B8;
  z-index: 1;
}
</style>
