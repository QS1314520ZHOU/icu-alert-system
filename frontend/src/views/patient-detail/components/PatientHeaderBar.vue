<template>
  <div class="header-bar">
    <div class="header-left">
      <a-button type="text" size="small" @click="$emit('back')" class="back-btn">
        ← 返回
      </a-button>
      <div class="patient-identity">
        <h1 class="patient-name">{{ displayName }}</h1>
        <div class="patient-meta">
          <span class="meta-bed">{{ displayBed }}床</span>
          <span class="meta-sep">|</span>
          <span>{{ displayGenderAge }}</span>
          <span class="meta-sep">|</span>
          <span>{{ displayDept }}</span>
          <span class="meta-sep">|</span>
          <span>入院 {{ displayAdmissionTime }}</span>
        </div>
      </div>
    </div>

    <div class="header-right">
      <div class="vitals-quick">
        <div v-for="v in quickVitals" :key="v.label" class="quick-vital" :class="`qv-${v.tone}`">
          <span class="qv-label">{{ v.label }}</span>
          <span class="qv-value">{{ v.value }}</span>
        </div>
      </div>
      <div class="header-controls">
        <a-radio-group :value="density" size="small" @change="$emit('density-change', $event.target.value)">
          <a-radio-button value="compact">紧凑</a-radio-button>
          <a-radio-button value="full">完整</a-radio-button>
        </a-radio-group>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePatientDetail } from '../../../composables/usePatientDetail'

const props = defineProps<{
  patient: any
  vitals: any
  bedcard: any
  alerts: any[]
  loading: boolean
}>()

defineEmits<{
  (e: 'back'): void
  (e: 'density-change', mode: string): void
}>()

const {
  displayName, displayBed, displayGenderAge, displayDept, displayAdmissionTime,
} = usePatientDetail()

const density = defineModel<string>('density', { default: 'full' })

const quickVitals = computed(() => {
  const v = props.vitals || {}
  return [
    { label: 'HR', value: v.hr ?? '—', tone: hrTone(v.hr) },
    { label: 'MAP', value: v.ibp_map ?? v.nibp_map ?? '—', tone: mapTone(v.ibp_map ?? v.nibp_map) },
    { label: 'SpO₂', value: v.spo2 != null ? `${v.spo2}%` : '—', tone: spo2Tone(v.spo2) },
  ]
})

function hrTone(v: any) { if (v == null) return 'default'; return v > 120 || v < 50 ? 'critical' : v > 100 || v < 60 ? 'warning' : 'normal' }
function mapTone(v: any) { if (v == null) return 'default'; return v < 55 ? 'critical' : v < 65 ? 'warning' : 'normal' }
function spo2Tone(v: any) { if (v == null) return 'default'; return v < 88 ? 'critical' : v < 92 ? 'warning' : 'normal' }
</script>

<style scoped>
.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  gap: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-btn {
  color: #666;
}

.patient-identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.patient-name {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #1a1a1a;
}

.patient-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #666;
}

.meta-bed {
  font-weight: 600;
  color: #1890ff;
}

.meta-sep {
  color: #d9d9d9;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.vitals-quick {
  display: flex;
  gap: 12px;
}

.quick-vital {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 10px;
  border-radius: 6px;
  background: #fafbfc;
  border: 1px solid #f0f0f0;
}

.qv-label {
  font-size: 10px;
  color: #999;
  font-weight: 500;
}

.qv-value {
  font-size: 16px;
  font-weight: 700;
  color: #1a1a1a;
}

.qv-critical .qv-value { color: #ff4d4f; }
.qv-warning .qv-value { color: #faad14; }
.qv-normal .qv-value { color: #52c41a; }
</style>
