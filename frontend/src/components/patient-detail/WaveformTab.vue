<template>
  <div class="detail-tab waveform-tab">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <a-select
          :value="selectedChannel"
          :options="channelOptions"
          style="width: 220px"
          placeholder="选择通道"
          @update:value="(v: any) => emit('update:selectedChannel', String(v || ''))"
        />
        <a-radio-group :value="hours" size="small" @update:value="(v: any) => emit('update:hours', Number(v || 6))">
          <a-radio-button :value="6">6h</a-radio-button>
          <a-radio-button :value="12">12h</a-radio-button>
          <a-radio-button :value="24">24h</a-radio-button>
        </a-radio-group>
      </div>
      <a-button size="small" :loading="loading" @click="onRefresh">刷新</a-button>
    </div>
    <div class="waveform-grid">
      <div class="chart-panel">
        <div v-if="points?.length" class="chart-wrap">
          <DetailChart :option="chartOption" autoresize />
        </div>
        <div v-else class="tab-empty">暂无波形/时序数据</div>
      </div>
      <div class="side-panel">
        <div class="side-block">
          <div class="side-title">信号质量</div>
          <div class="qc-pill" :class="`is-${qc?.band || 'poor'}`">
            {{ qc?.band || 'poor' }}
            <strong>{{ qc?.score ?? '—' }}</strong>
          </div>
          <ul class="side-list">
            <li v-for="(item, idx) in qcIssues" :key="`qc-${idx}`">{{ item }}</li>
          </ul>
        </div>
        <div class="side-block">
          <div class="side-title">事件识别</div>
          <ul class="side-list">
            <li v-for="(item, idx) in events" :key="`event-${idx}`">{{ item.type }} · {{ item.detail || '—' }}</li>
          </ul>
          <div v-if="!events?.length" class="side-empty">暂无事件</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { Button as AButton, RadioButton as ARadioButton, RadioGroup as ARadioGroup, Select as ASelect } from 'ant-design-vue'
import { icuCategoryAxis, icuGrid, icuTooltip, icuValueAxis } from '../../charts/icuTheme'

const props = defineProps<{
  loading: boolean
  selectedChannel: string
  channelOptions: Array<{ label: string; value: string }>
  hours: number
  points: any[]
  qc: any
  events: any[]
  onRefresh: () => void
}>()

const emit = defineEmits<{
  (e: 'update:selectedChannel', value: string): void
  (e: 'update:hours', value: number): void
}>()

const DetailChart = defineAsyncComponent(async () => {
  await import('../../charts/patient-detail')
  const mod = await import('vue-echarts')
  return mod.default
})

const chartOption = computed(() => {
  const rows = Array.isArray(props.points) ? props.points : []
  const xs = rows.map((row: any) => {
    const value = String(row?.time || '')
    return value ? value.slice(5, 16).replace('T', ' ') : '—'
  })
  const ys = rows.map((row: any) => row?.value ?? null)
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({ trigger: 'axis' }),
    grid: icuGrid({ left: 40, right: 18, top: 18, bottom: 28 }),
    xAxis: icuCategoryAxis(xs),
    yAxis: icuValueAxis(),
    series: [{ name: props.selectedChannel || 'signal', type: 'line', smooth: true, symbol: 'none', data: ys }],
  }
})

const qcIssues = computed(() => Array.isArray(props.qc?.issues) ? props.qc.issues : [])
</script>

<style scoped>
.detail-tab { display: grid; gap: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.toolbar-left { display: flex; gap: 8px; flex-wrap: wrap; }
.waveform-grid { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(280px, .9fr); gap: 12px; }
.chart-panel, .side-panel { padding: 12px; border-radius: 12px; background: linear-gradient(180deg, rgba(7,20,34,.92) 0%, rgba(4,12,22,.94) 100%); border: 1px solid rgba(80,199,255,.12); }
.chart-wrap { height: 360px; }
.side-panel { display: grid; gap: 10px; }
.side-block { display: grid; gap: 8px; border: 1px solid rgba(80,199,255,.10); border-radius: 10px; padding: 10px; background: rgba(8,28,44,.52); }
.side-title { color: #7ecce1; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.qc-pill { display: inline-flex; align-items: center; gap: 8px; width: fit-content; padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(80,199,255,.14); color: #dffbff; }
.qc-pill.is-good { border-color: rgba(16,185,129,.28); color: #6ee7b7; }
.qc-pill.is-fair { border-color: rgba(245,158,11,.28); color: #fcd34d; }
.qc-pill.is-poor { border-color: rgba(239,68,68,.28); color: #fca5a5; }
.side-list { margin: 0; padding-left: 18px; color: #cfe4ff; font-size: 12px; line-height: 1.6; }
.side-empty, .tab-empty { color: #7ccfe4; font-size: 12px; }
.waveform-tab :deep(.ant-btn), .waveform-tab :deep(.ant-select-selector), .waveform-tab :deep(.ant-radio-button-wrapper) { background: rgba(8,28,44,.78) !important; border-color: rgba(80,199,255,.14) !important; color: #dffbff !important; }
.waveform-tab :deep(.ant-radio-button-wrapper-checked) { background: linear-gradient(180deg, rgba(11,107,137,.96) 0%, rgba(7,63,86,.98) 100%) !important; }
@media (max-width: 980px) { .waveform-grid { grid-template-columns: 1fr; } }
</style>
