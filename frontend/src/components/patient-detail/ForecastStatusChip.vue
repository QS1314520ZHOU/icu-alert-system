<template>
  <a-popover v-if="visible" placement="bottomRight" trigger="click">
    <template #content>
      <div class="forecast-popover">
        <div><strong>来源</strong><span>{{ sourceText }}</span></div>
        <div><strong>预测窗口</strong><span>{{ meta.horizon || horizon }}h</span></div>
        <div><strong>生成时间</strong><span>{{ generatedText }}</span></div>
        <div><strong>数据点</strong><span>{{ meta.dataPoints || 0 }}</span></div>
        <div v-if="meta.modelVersion"><strong>版本</strong><span>{{ meta.modelVersion }}</span></div>
        <div v-if="meta.fallbackReason"><strong>降级原因</strong><span>{{ fallbackText }}</span></div>
        <div v-if="meta.error"><strong>错误</strong><span>{{ meta.error }}</span></div>
      </div>
    </template>
    <button type="button" :class="['forecast-chip', `forecast-chip--${tone}`]">
      <span class="forecast-dot"></span>
      <span>{{ chipText }}</span>
      <b v-if="meta.qualityLevel === 'low'">数据不足</b>
    </button>
  </a-popover>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Popover as APopover } from 'ant-design-vue'
import dayjs from 'dayjs'
import type { ForecastMeta } from '../../composables/useVitalForecast'

const props = defineProps<{
  meta: ForecastMeta
  enabled: boolean
  horizon: number
}>()

const visible = computed(() => props.enabled && props.meta.status !== 'idle')
const generatedText = computed(() => props.meta.generatedAt ? dayjs(props.meta.generatedAt).format('HH:mm') : '—')
const tone = computed(() => {
  if (props.meta.status === 'error') return 'error'
  if (props.meta.source === 'heuristic') return 'fallback'
  return 'ready'
})
const sourceText = computed(() => props.meta.source === 'chronos' ? 'Chronos' : props.meta.source === 'heuristic' ? '线性外推' : '预测暂不可用')
const fallbackText = computed(() => {
  const map: Record<string, string> = {
    model_not_loaded: 'Chronos 模型未加载',
    insufficient_history: '历史数据不足',
    model_inference_error: '模型推理失败',
  }
  return map[props.meta.fallbackReason] || props.meta.fallbackReason
})
const chipText = computed(() => {
  if (props.meta.status === 'loading') return '预测生成中'
  if (props.meta.status === 'refreshing') return '预测刷新中'
  if (props.meta.status === 'error') return '预测暂不可用'
  const horizon = props.meta.horizon || props.horizon
  if (props.meta.source === 'heuristic') return `线性外推 · ${horizon}h预测 · 模型未加载`
  return `Chronos · ${horizon}h预测 · ${generatedText.value} 生成`
})
</script>

<style scoped>
.forecast-chip {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.16);
  background: rgba(8, 28, 44, 0.78);
  color: #dffbff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.forecast-chip--ready { border-color: rgba(52, 211, 153, 0.28); color: #a7f3d0; }
.forecast-chip--fallback { border-color: rgba(251, 191, 36, 0.28); color: #fde68a; }
.forecast-chip--error { border-color: rgba(148, 163, 184, 0.24); color: #cbd5e1; }
.forecast-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 0 0 10px currentColor;
}
.forecast-chip b {
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(251, 191, 36, 0.14);
  color: #fde68a;
  font-size: 10px;
}
.forecast-popover {
  display: grid;
  gap: 8px;
  min-width: 220px;
}
.forecast-popover div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  color: #64748b;
  font-size: 12px;
}
.forecast-popover strong {
  color: #1f2937;
}
</style>
