<template>
  <div class="detail-tab trend-tab">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <a-radio-group :value="trendWindow" size="small" @update:value="(v: any) => emit('update:trendWindow', v)">
          <a-radio-button value="24h">24h</a-radio-button>
          <a-radio-button value="48h">48h</a-radio-button>
          <a-radio-button value="7d">7d</a-radio-button>
        </a-radio-group>
        <span class="toolbar-hint">按窗口复盘生命体征波动与灌注/氧合变化。</span>
      </div>
      <div class="toolbar-right">
        <ForecastStatusChip :meta="forecastMeta" :enabled="forecastEnabled" :horizon="forecastHorizon" :forecast-data="forecastData" />
        <a-button size="small" @click="onRefresh">刷新</a-button>
      </div>
    </div>

    <section v-if="summaryCards.length" class="summary-grid">
      <article v-for="card in summaryCards" :key="card.key" class="summary-card">
        <span>{{ card.label }}</span>
        <strong>{{ card.current }}</strong>
        <small>{{ card.delta }}</small>
      </article>
    </section>

    <div v-if="trendPoints?.length" class="chart-panel">
      <div class="chart-wrap">
        <DetailChart
          :option="trendOption"
          :init-options="chartInitOptions"
          autoresize
          @legendselectchanged="(event: any) => emit('legendSelectChanged', event?.selected || {})"
        />
      </div>
    </div>
    <div v-else class="tab-empty">暂无趋势数据</div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { Button as AButton, RadioButton as ARadioButton, RadioGroup as ARadioGroup } from 'ant-design-vue'
import { chartInitOptions as createChartInitOptions } from '../../charts/displayQuality'
import ForecastStatusChip from './ForecastStatusChip.vue'
import type { ForecastMeta } from '../../composables/useVitalForecast'

const props = defineProps<{
  trendWindow: string
  trendPoints: any[]
  trendOption: any
  onRefresh: () => void
  forecastMeta: ForecastMeta
  forecastEnabled: boolean
  forecastHorizon: number
  forecastData?: any
}>()

const emit = defineEmits<{
  (e: 'update:trendWindow', value: string): void
  (e: 'legendSelectChanged', value: Record<string, boolean>): void
}>()

const DetailChart = defineAsyncComponent(async () => {
  await import('../../charts/patient-detail')
  const mod = await import('vue-echarts')
  return mod.default
})

const chartInitOptions = createChartInitOptions()

function pickLast(key: string) {
  const rows = Array.isArray(props.trendPoints) ? props.trendPoints : []
  for (let idx = rows.length - 1; idx >= 0; idx -= 1) {
    const value = Number(rows[idx]?.[key])
    if (Number.isFinite(value)) return value
  }
  return null
}

function pickFirst(key: string) {
  const rows = Array.isArray(props.trendPoints) ? props.trendPoints : []
  for (let idx = 0; idx < rows.length; idx += 1) {
    const value = Number(rows[idx]?.[key])
    if (Number.isFinite(value)) return value
  }
  return null
}

function diffText(current: number | null, previous: number | null, unit = '') {
  if (current == null || previous == null) return '趋势基线不足'
  const delta = current - previous
  const prefix = delta > 0 ? '+' : ''
  return `${prefix}${delta.toFixed(Math.abs(delta) >= 10 ? 0 : 1)}${unit}`
}

const summaryCards = computed(() => {
  const defs = [
    { key: 'hr', label: 'HR', unit: '/min' },
    { key: 'spo2', label: 'SpO2', unit: '%' },
    { key: 'rr', label: 'RR', unit: '/min' },
    { key: 'temp', label: '体温', unit: '°C' },
  ]
  return defs.map((item) => {
    const current = pickLast(item.key)
    const first = pickFirst(item.key)
    return {
      key: item.key,
      label: item.label,
      current: current == null ? '—' : `${current.toFixed(item.key === 'temp' ? 1 : 0)}${item.unit}`,
      delta: diffText(current, first, item.unit),
    }
  })
})
</script>

<style scoped>
.detail-tab {
  display: grid;
  gap: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.toolbar-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.toolbar-hint {
  color: var(--text-secondary);
  font-size: 12px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.summary-card {
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface) 0%, var(--bg-surface) 100%);
  border: 1px solid rgba(80,199,255,.12);
}
.summary-card span,
.summary-card small {
  color: var(--text-secondary);
  font-size: 12px;
}
.summary-card strong {
  display: block;
  margin-top: 6px;
  color: var(--text-primary);
  font-size: 20px;
  font-weight: 800;
}
.summary-card small {
  display: block;
  margin-top: 8px;
}
.chart-panel {
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface) 0%, var(--bg-surface) 100%);
  border: 1px solid rgba(80,199,255,.12);
  box-shadow: var(--card-shadow);
}
.chart-wrap {
  height: 360px;
}
.tab-empty {
  color: var(--accent);
  font-size: 12px;
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface),.58);
  border: 1px dashed rgba(80,199,255,.14);
}
.trend-tab :deep(.ant-radio-group) {
  display: inline-flex;
  gap: 6px;
}
.trend-tab :deep(.ant-radio-button-wrapper) {
  border-radius: 10px !important;
  border: 1px solid rgba(80,199,255,.14) !important;
  background: var(--bg-surface),.78) !important;
  color: var(--accent) !important;
}
.trend-tab :deep(.ant-radio-button-wrapper::before) {
  display: none !important;
}
.trend-tab :deep(.ant-radio-button-wrapper-checked) {
  background: var(--bg-surface) 0%, rgba(7,63,86,.98) 100%) !important;
  color: var(--text-primary) !important;
  border-color: rgba(110,231,249,.28) !important;
}
.trend-tab :deep(.ant-btn) {
  background: var(--bg-surface),.78);
  border-color: rgba(80,199,255,.14);
  color: var(--text-primary);
}
@media (max-width: 920px) {
  .summary-grid {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 640px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
}

html[data-theme='light'] .toolbar-hint,
html[data-theme='light'] .summary-card span,
html[data-theme='light'] .summary-card small,
html[data-theme='light'] .trend-tab .tab-empty { color: #5f7690; }
html[data-theme='light'] .summary-card,
html[data-theme='light'] .trend-tab .chart-panel {
  background:
    var(--bg-surface), rgba(56,189,248,0) 40%),
    var(--bg-surface) 0%, rgba(243,248,253,.98) 100%);
  border-color: rgba(187,204,220,.72);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .summary-card strong { color: var(--text-secondary); }
html[data-theme='light'] .trend-tab .tab-empty {
  background: rgba(238,245,252,.92);
  border-color: rgba(153,183,206,.5);
}
html[data-theme='light'] .trend-tab :deep(.ant-radio-button-wrapper) {
  border-color: rgba(187,204,220,.72) !important;
  background: var(--bg-surface), rgba(239,245,250,.98)) !important;
  color: #56718d !important;
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .trend-tab :deep(.ant-radio-button-wrapper-checked) {
  background: var(--bg-surface) 0%, rgba(29,78,216,.98) 100%) !important;
  color: var(--text-primary) !important;
  border-color: rgba(59,130,246,.34) !important;
}
html[data-theme='light'] .trend-tab :deep(.ant-btn) {
  background: var(--bg-surface), rgba(241,246,251,.98));
  border-color: rgba(187,204,220,.72);
  color: var(--text-secondary);
  box-shadow: var(--card-shadow);
}
</style>
