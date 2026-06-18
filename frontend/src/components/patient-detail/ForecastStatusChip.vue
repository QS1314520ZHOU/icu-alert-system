<template>
  <a-popover v-if="visible" placement="bottomRight" trigger="click">
    <template #content>
      <div class="forecast-popover">
        <div><strong>来源</strong><span>{{ sourceText }}</span></div>
        <div><strong>预测窗口</strong><span>{{ meta.horizon || horizon }}h</span></div>
        <div><strong>历史回看</strong><span>{{ historyWindowText }}</span></div>
        <div><strong>生成时间</strong><span>{{ generatedText }}</span></div>
        <div><strong>数据点</strong><span>{{ meta.dataPoints || 0 }}</span></div>
        <div v-if="meta.modelVersion"><strong>版本</strong><span>{{ meta.modelVersion }}</span></div>
        <div v-if="meta.fallbackReason"><strong>降级原因</strong><span>{{ fallbackText }}</span></div>
        <div v-if="meta.error"><strong>错误</strong><span>{{ errorText }}</span></div>
        <template v-if="indicatorDetails.length">
          <div class="forecast-popover-divider"></div>
          <div class="forecast-popover-section-title">各指标数据点</div>
          <div v-for="item in indicatorDetails" :key="item.code" class="forecast-indicator-row">
            <span class="forecast-indicator-code">{{ item.code }}</span>
            <span :class="['forecast-indicator-count', item.insufficient ? 'forecast-indicator-warn' : '']">{{ item.points }}点{{ item.insufficient ? ' ⚠' : '' }}</span>
          </div>
        </template>
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
import { forecastErrorText, type ForecastMeta } from '../../composables/useVitalForecast'

const props = defineProps<{
  meta: ForecastMeta
  enabled: boolean
  horizon: number
  forecastData?: any
}>()

const visible = computed(() => props.enabled && props.meta.status !== 'idle')
const generatedText = computed(() => props.meta.generatedAt ? dayjs(props.meta.generatedAt).format('HH:mm') : '—')
const tone = computed(() => {
  if (props.meta.status === 'error') return 'error'
  if (props.meta.source === 'heuristic') return 'fallback'
  return 'ready'
})
const sourceText = computed(() => props.meta.source === 'chronos' ? '时序预测模型' : props.meta.source === 'heuristic' ? '规则外推' : '预测暂不可用')
const fallbackText = computed(() => {
  const map: Record<string, string> = {
    model_not_loaded: '模型未就绪，已暂不可用',
    model_not_ready: '模型未就绪，已暂不可用',
    insufficient_history: '历史数据不足',
    model_inference_error: '模型推理失败',
    forecast_timeout: '预测计算超时，请稍后重试',
    forecast_unavailable: '预测暂不可用',
    forecast_threshold_breach: '预测达到预警阈值',
  }
  return map[props.meta.fallbackReason] || forecastErrorText(props.meta.fallbackReason)
})
const errorText = computed(() => {
  const raw = String(props.meta.error || '').trim()
  if (!raw) return ''
  return forecastErrorText(raw)
})
const chipText = computed(() => {
  if (props.meta.status === 'loading') return '预测生成中'
  if (props.meta.status === 'refreshing') return '预测刷新中'
  if (props.meta.status === 'error') return '预测暂不可用'
  const horizon = props.meta.horizon || props.horizon
  if (props.meta.source === 'heuristic') return `规则外推 · ${horizon}小时预测 · 模型未就绪`
  return `时序模型 · ${horizon}小时预测 · ${generatedText.value} 生成`
})

const historyWindowText = computed(() => {
  const series = props.forecastData?.series || {}
  const first = Object.values(series)[0] as any
  const hours = first?.history_window_hours
  if (!hours) return '24小时'
  return hours >= 24 && hours % 24 === 0 ? `${hours / 24}天（${hours}小时）` : `${hours}小时`
})

const indicatorDetails = computed(() => {
  const series = props.forecastData?.series || {}
  return Object.entries(series).map(([code, row]: [string, any]) => {
    const history = Array.isArray(row?.history) ? row.history : []
    const points = row?.fetched_points ?? history.length
    const qualityOk = row?.data_quality?.ok !== false
    const insufficient = !qualityOk || Number(points) < 3
    return { code, points, insufficient }
  })
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
.forecast-popover-divider {
  height: 1px;
  background: #e5e7eb;
  margin: 4px 0;
}
.forecast-popover-section-title {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 600;
  display: block !important;
}
.forecast-indicator-row {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  gap: 12px;
}
.forecast-indicator-code {
  color: #374151;
  font-weight: 500;
}
.forecast-indicator-count {
  color: #6b7280;
}
.forecast-indicator-warn {
  color: #d97706;
  font-weight: 600;
}
</style>
