<template>
  <section class="twin-avatar-panel">
    <div class="twin-avatar-panel__head">
      <div>
        <div class="twin-avatar-panel__kicker">数字人体</div>
        <div class="twin-avatar-panel__title">可视化虚拟患者</div>
      </div>
      <span class="twin-avatar-panel__time">{{ calcTime }}</span>
    </div>

    <OrganHeatmapFigure
      :organ-states="organStates"
      :show-legend="true"
      :silhouette="silhouette"
    />

    <div v-if="metricBadges.length" class="twin-avatar-panel__metrics">
      <article v-for="item in metricBadges" :key="item.key" :class="['twin-avatar-panel__metric', `is-${item.tone || 'normal'}`]">
        <div class="twin-avatar-panel__metric-head">
          <strong>{{ item.label }}</strong>
          <span v-if="item.trendText" :class="['twin-avatar-panel__trend', `is-${item.trendTone || 'stable'}`]">{{ item.trendText }}</span>
        </div>
        <div class="twin-avatar-panel__metric-value">{{ item.value }}</div>
        <div v-if="item.meta" class="twin-avatar-panel__metric-meta">{{ item.meta }}</div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OrganHeatmapFigure from '../common/OrganHeatmapFigure.vue'
import { mergeOrganStateMaps } from '../../utils/bodyMap'

const props = defineProps<{
  snapshot?: any
  vitalsSnapshot?: any
  scores?: any
  calcTime?: string
  silhouette?: 'female' | 'male'
}>()

function fmtMetric(value: any, unit = '', digits = 0) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  return `${digits > 0 ? num.toFixed(digits) : Math.round(num)}${unit}`.trim()
}

function trendArrow(value: any) {
  const key = String(value || '').toLowerCase()
  if (key === 'up') return '↗'
  if (key === 'down') return '↘'
  return '→'
}

function trendTone(value: any) {
  const key = String(value || '').toLowerCase()
  if (key === 'up') return 'up'
  if (key === 'down') return 'down'
  return 'stable'
}

function trendText(value: any) {
  const key = String(value || '').toLowerCase()
  if (key === 'up') return '上升'
  if (key === 'down') return '下降'
  if (key === 'stable') return '平稳'
  return ''
}

function toneByMetric(kind: string, value: any) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'normal'
  if (kind === 'spo2') {
    if (n < 88) return 'critical'
    if (n < 92) return 'high'
    return 'normal'
  }
  if (kind === 'rr') {
    if (n >= 32 || n <= 8) return 'critical'
    if (n >= 26 || n <= 10) return 'high'
    return 'normal'
  }
  if (kind === 'map') {
    if (n < 55) return 'critical'
    if (n < 65) return 'high'
    return 'normal'
  }
  if (kind === 'hr') {
    if (n >= 135 || n <= 40) return 'critical'
    if (n >= 115 || n <= 50) return 'high'
    return 'normal'
  }
  if (kind === 'temp') {
    if (n >= 39.5 || n <= 35) return 'critical'
    if (n >= 38.5 || n <= 36) return 'high'
    return 'normal'
  }
  if (kind === 'lactate') {
    if (n >= 4) return 'critical'
    if (n >= 2.5) return 'high'
    return 'normal'
  }
  if (kind === 'urine') {
    if (n < 0.3) return 'critical'
    if (n < 0.5) return 'high'
    return 'normal'
  }
  if (kind === 'vaso') {
    if (n >= 0.2) return 'critical'
    if (n >= 0.08) return 'high'
    return 'warning'
  }
  return 'normal'
}

const organStates = computed(() =>
  mergeOrganStateMaps({
    neurologic: toneByMetric('temp', props.snapshot?.temp?.current),
    respiratory: ['spo2', 'rr'].map((key) => toneByMetric(key, props.snapshot?.[key]?.current)).sort((a, b) => ['normal', 'warning', 'high', 'critical'].indexOf(b) - ['normal', 'warning', 'high', 'critical'].indexOf(a))[0] || 'normal',
    circulatory: ['map', 'hr', 'vaso'].map((key) => toneByMetric(key, key === 'vaso' ? props.snapshot?.vasoactive_support?.current_dose_ug_kg_min : props.snapshot?.[key]?.current)).sort((a, b) => ['normal', 'warning', 'high', 'critical'].indexOf(b) - ['normal', 'warning', 'high', 'critical'].indexOf(a))[0] || 'normal',
    hepatic: toneByMetric('lactate', props.snapshot?.lactate?.current),
    coagulation: 'normal',
    renal: toneByMetric('urine', props.snapshot?.urine_ml_kg_h_6h),
  })
)

const metricBadges = computed(() => {
  const vitals = props.vitalsSnapshot || {}
  const neuroSofa = props.scores?.sofa?.components?.neuro
  return [
    {
      key: 'head',
      anchor: 'head',
      label: '头部',
      value: fmtMetric(props.snapshot?.temp?.current, '℃', 1),
      meta: neuroSofa != null ? `神经 SOFA ${neuroSofa}` : '体温 / 神经',
      tone: toneByMetric('temp', props.snapshot?.temp?.current),
      trendText: vitals?.temp?.trend ? `${trendArrow(vitals.temp.trend)} ${trendText(vitals.temp.trend)}` : '',
      trendTone: trendTone(vitals?.temp?.trend),
    },
    {
      key: 'lungs',
      anchor: 'rightChest',
      label: '肺',
      value: `${fmtMetric(props.snapshot?.spo2?.current, '%', 0)} · ${fmtMetric(props.snapshot?.rr?.current, '/min', 0)}`,
      meta: 'SpO₂ / RR',
      tone: toneByMetric('spo2', props.snapshot?.spo2?.current),
      trendText: vitals?.spo2?.trend ? `${trendArrow(vitals.spo2.trend)} ${trendText(vitals.spo2.trend)}` : '',
      trendTone: trendTone(vitals?.spo2?.trend),
    },
    {
      key: 'heart',
      anchor: 'leftChest',
      label: '心血管',
      value: `${fmtMetric(props.snapshot?.hr?.current, 'bpm', 0)} · ${fmtMetric(props.snapshot?.map?.current, 'mmHg', 0)}`,
      meta: 'HR / MAP',
      tone: toneByMetric('map', props.snapshot?.map?.current),
      trendText: vitals?.map?.trend ? `${trendArrow(vitals.map.trend)} ${trendText(vitals.map.trend)}` : '',
      trendTone: trendTone(vitals?.map?.trend),
    },
    {
      key: 'abdomen',
      anchor: 'abdomen',
      label: '腹部',
      value: `${fmtMetric(props.snapshot?.lactate?.current, 'mmol/L', 1)} · ${fmtMetric(props.snapshot?.urine_ml_kg_h_6h, 'mL/kg/h', 2)}`,
      meta: '乳酸 / 尿量',
      tone: toneByMetric('lactate', props.snapshot?.lactate?.current),
      trendText: vitals?.rr?.trend ? `${trendArrow(vitals.rr.trend)} ${trendText(vitals.rr.trend)}` : '',
      trendTone: trendTone(vitals?.rr?.trend),
    },
    {
      key: 'vaso',
      anchor: 'rightArm',
      label: '血流动力学',
      value: fmtMetric(props.snapshot?.vasoactive_support?.current_dose_ug_kg_min, 'ug/kg/min', 3),
      meta: '血管活性药',
      tone: toneByMetric('vaso', props.snapshot?.vasoactive_support?.current_dose_ug_kg_min),
    },
  ].filter((item) => item.value && item.value !== '—')
})
</script>

<style scoped>
.twin-avatar-panel {
  display: grid;
  gap: 12px;
}
.twin-avatar-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.twin-avatar-panel__kicker {
  color: #7ed6eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.twin-avatar-panel__title {
  margin-top: 4px;
  color: #effcff;
  font-size: 18px;
  font-weight: 800;
}
.twin-avatar-panel__time {
  color: #8fb8ca;
  font-size: 12px;
}
.twin-avatar-panel__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}
.twin-avatar-panel__metric {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(80,199,255,.12);
  background: rgba(8, 28, 44, 0.72);
}
.twin-avatar-panel__metric.is-warning { border-color: rgba(245,158,11,.22); }
.twin-avatar-panel__metric.is-high { border-color: rgba(249,115,22,.24); }
.twin-avatar-panel__metric.is-critical { border-color: rgba(244,63,94,.28); }
.twin-avatar-panel__metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.twin-avatar-panel__metric-head strong,
.twin-avatar-panel__metric-value {
  color: #effcff;
}
.twin-avatar-panel__metric-head strong {
  font-size: 13px;
}
.twin-avatar-panel__metric-value {
  font-size: 16px;
  font-weight: 800;
}
.twin-avatar-panel__metric-meta,
.twin-avatar-panel__trend {
  color: #8fb8ca;
  font-size: 11px;
}
.twin-avatar-panel__trend.is-up { color: #fb7185; }
.twin-avatar-panel__trend.is-down { color: #67e8f9; }
.twin-avatar-panel__trend.is-stable { color: #44f0a9; }
html[data-theme='light'] .twin-avatar-panel__title {
  color: #17324a;
}
html[data-theme='light'] .twin-avatar-panel__kicker,
html[data-theme='light'] .twin-avatar-panel__time {
  color: #56748d;
}
html[data-theme='light'] .twin-avatar-panel__metric {
  background: rgba(255,255,255,.94);
  border-color: rgba(130, 170, 194, 0.24);
}
html[data-theme='light'] .twin-avatar-panel__metric-head strong,
html[data-theme='light'] .twin-avatar-panel__metric-value {
  color: #17324a;
}
html[data-theme='light'] .twin-avatar-panel__metric-meta {
  color: #56748d;
}
</style>
