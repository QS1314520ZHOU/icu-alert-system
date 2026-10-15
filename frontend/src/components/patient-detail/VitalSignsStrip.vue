<template>
  <div class="vital-strip">
    <div v-for="item in vitals" :key="item.key" :class="['vital-strip__item', `is-${item.tone}`]">
      <div class="vital-strip__bar"></div>
      <div class="vital-strip__body">
        <span class="vital-strip__label">{{ item.label }}</span>
        <span class="vital-strip__value">{{ item.display }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  vitalsSnapshot?: Record<string, any>
}>()

function tone(kind: string, value: any): 'normal' | 'warning' | 'critical' {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'normal'
  switch (kind) {
    case 'hr': return n < 60 || n > 120 ? 'warning' : 'normal'
    case 'map': return n < 65 ? 'critical' : n > 100 ? 'warning' : 'normal'
    case 'spo2': return n < 92 ? 'critical' : n < 95 ? 'warning' : 'normal'
    case 'temp': return n < 36 || n > 38 ? 'warning' : 'normal'
    case 'lactate': return n > 4 ? 'critical' : n > 2 ? 'warning' : 'normal'
    case 'urine': return n < 0.3 ? 'critical' : n < 0.5 ? 'warning' : 'normal'
    default: return 'normal'
  }
}

function fmt(value: any, unit: string, digits: number): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return `${n.toFixed(digits)}${unit}`
}

const vitals = computed(() => {
  const s = props.vitalsSnapshot || {}
  return [
    { key: 'hr',      label: 'HR',    display: fmt(s.hr?.current, ' bpm', 0),           tone: tone('hr', s.hr?.current) },
    { key: 'map',     label: 'MAP',   display: fmt(s.map?.current, ' mmHg', 0),         tone: tone('map', s.map?.current) },
    { key: 'spo2',    label: 'SpO₂',  display: fmt(s.spo2?.current, '%', 0),            tone: tone('spo2', s.spo2?.current) },
    { key: 'temp',    label: 'T',     display: fmt(s.temp?.current, '℃', 1),            tone: tone('temp', s.temp?.current) },
    { key: 'lactate', label: '乳酸',   display: fmt(s.lactate?.current, ' mmol/L', 1),   tone: tone('lactate', s.lactate?.current) },
    { key: 'urine',   label: '尿量',   display: fmt(s.urine_ml_kg_h_6h, ' mL/kg/h', 2), tone: tone('urine', s.urine_ml_kg_h_6h) },
  ]
})
</script>

<style scoped>
.vital-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.vital-strip__item {
  display: flex;
  align-items: stretch;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  overflow: hidden;
}
.vital-strip__bar {
  width: 3px;
  flex-shrink: 0;
}
.is-normal .vital-strip__bar { background: var(--color-normal); }
.is-warning .vital-strip__bar { background: var(--color-warning); }
.is-critical .vital-strip__bar { background: var(--color-danger); }
.vital-strip__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  min-width: 0;
}
.vital-strip__label {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.vital-strip__value {
  font-size: var(--text-body);
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}
.is-warning .vital-strip__value { color: var(--color-warning); }
.is-critical .vital-strip__value { color: var(--color-danger); }
@media (max-width: 720px) {
  .vital-strip { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 480px) {
  .vital-strip { grid-template-columns: repeat(2, 1fr); }
}
</style>
