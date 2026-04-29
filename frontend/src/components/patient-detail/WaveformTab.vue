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
import { formatBeijingTime } from '../../utils/time'

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
    return formatBeijingTime(row?.time, '—')
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
html[data-theme='light'] .waveform-tab .chart-panel,
html[data-theme='light'] .waveform-tab .side-panel,
html[data-theme='light'] .waveform-tab .side-block {
  border-color: rgba(187, 204, 220, 0.72);
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.06), rgba(59, 130, 246, 0) 36%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(245,249,253,.98) 100%);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}
html[data-theme='light'] .waveform-tab .side-title {
  color: #47627e;
}
html[data-theme='light'] .waveform-tab .side-list,
html[data-theme='light'] .waveform-tab .side-empty,
html[data-theme='light'] .waveform-tab .tab-empty {
  color: #6f8399;
}
html[data-theme='light'] .waveform-tab .qc-pill {
  background: #ffffff;
  border-color: rgba(187, 204, 220, 0.72);
  color: #223a54;
}
html[data-theme='light'] .waveform-tab .qc-pill.is-good {
  color: #047857;
  border-color: rgba(16, 185, 129, 0.28);
  background: rgba(220, 252, 231, 0.9);
}
html[data-theme='light'] .waveform-tab .qc-pill.is-fair {
  color: #b45309;
  border-color: rgba(245, 158, 11, 0.28);
  background: rgba(254, 243, 199, 0.9);
}
html[data-theme='light'] .waveform-tab .qc-pill.is-poor {
  color: #b91c1c;
  border-color: rgba(239, 68, 68, 0.28);
  background: rgba(254, 226, 226, 0.92);
}
html[data-theme='light'] .waveform-tab :deep(.ant-btn),
html[data-theme='light'] .waveform-tab :deep(.ant-select-selector),
html[data-theme='light'] .waveform-tab :deep(.ant-radio-button-wrapper) {
  background: rgba(241, 246, 251, 0.98) !important;
  border-color: rgba(187, 204, 220, 0.72) !important;
  color: #1f3852 !important;
}
html[data-theme='light'] .waveform-tab :deep(.ant-select-selection-placeholder) {
  color: #6f8399 !important;
}
html[data-theme='light'] .waveform-tab :deep(.ant-radio-button-wrapper-checked) {
  background: linear-gradient(180deg, rgba(37,99,235,.94) 0%, rgba(29,78,216,.98) 100%) !important;
  border-color: rgba(59, 130, 246, 0.32) !important;
  color: #f8fbff !important;
}
@media (max-width: 980px) { .waveform-grid { grid-template-columns: 1fr; } }
</style>
