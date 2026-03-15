<template>
  <article
    :class="['card', `card--${patient.alertLevel || 'none'}`, { 'card--flash': patient.alertFlash }]"
    @click="emit('select', patient._id)"
  >
    <!-- Section 1: Top Bar & Diagnosis -->
    <section class="sec-top">
      <header class="card-header">
        <div class="header-main">
          <span class="bed-no">{{ patient.hisBed }}</span>
          <h2 class="patient-name">{{ patient.name || '—' }}</h2>
          <span class="patient-meta">{{ patient.gender === 'Female' ? '女' : '男' }}/{{ patient.age }}</span>
        </div>
      </header>
      <div class="subtitle-row">
        <span class="diag-text" :title="patient.clinicalDiagnosis">{{ shortDiag(patient.clinicalDiagnosis) || '无初步诊断' }}</span>
        <span v-if="bedcard?.identity?.allergies || patient.allergies" class="allergy-tag">
          ⚠️{{ bedcard?.identity?.allergies || patient.allergies }}
        </span>
      </div>
    </section>

    <!-- Section 2: Vitals Telemetry (The Focus) -->
    <section class="sec-vitals">
      <div class="vital-grid">
        <div v-for="v in vitalsData" :key="v.label" :class="['vital-item', v.colorClass]">
          <span class="v-label">{{ v.label }}</span>
          <span class="v-val">{{ v.value }}<small v-if="v.unit && v.value !== '--'">{{ v.unit }}</small></span>
        </div>
      </div>
    </section>

    <!-- Section 3: Devices & Tubes (Clean) -->
    <section class="sec-logistics" v-if="bedcard?.devices?.length || bedcard?.tubes?.length">
      <div v-if="bedcard?.devices?.length" class="dev-line">
        <span v-for="(dev, idx) in bedcard.devices.slice(0, 1)" :key="idx" class="dev-span">
          <i class="dev-dot"></i>{{ dev.name }}
        </span>
      </div>
      <div v-if="bedcard?.tubes?.length" class="tube-line" :class="{ 'is-hover-expand': !showAllTubes }">
        <span :class="['tube-inline-list', { 'is-folded': !showAllTubes }]">
          <span v-for="(t, idx) in formattedTubesList" :key="idx" class="tube-item-wrap">
            <span :class="['tube-item', tubeClass(t.dwellDays)]">{{ t.name }} D{{ t.dwellDays }}</span>
            <span v-if="Number(idx) < formattedTubesList.length - 1" class="sep"> · </span>
          </span>
        </span>
        <span v-if="bedcard.tubes.length > 2" class="tube-extra" @click.stop="showAllTubes = !showAllTubes">
          {{ showAllTubes ? '收起' : `+${bedcard.tubes.length - 2}根` }}
        </span>
      </div>
    </section>

    <!-- Section 4: Alerts Tickers -->
    <section class="sec-alerts" v-if="bedcard?.notes?.length || bundleProgress">
      <div class="alert-line" v-if="bundleProgress">
        <span class="alert-dot alert-dot--yellow"></span> Bundle {{ bundleProgress }}
      </div>
      <div v-for="(note, idx) in bedcard?.notes?.slice(0, 1)" :key="idx" class="alert-line">
        <span class="alert-dot alert-dot--red"></span> {{ note }}
      </div>
    </section>

    <!-- Section 5: Footer (Micro Dots + Pills) -->
    <section class="sec-footer">
      <div class="bundle-dots">
        <span
          v-for="light in bundleLights(patient)"
          :key="light.key"
          :class="['mini-dot', `mini--${light.state}`]"
          :title="light.name"
        >{{ light.key }}</span>
      </div>
      <div class="footer-pills">
        <span v-if="bedcard?.identity?.isolation" class="pill pill--iso">{{ bedcard.identity.isolation }}</span>
        <span v-if="patientDiet(patient)" class="pill pill--diet">{{ patientDiet(patient) }}</span>
      </div>
    </section>
  </article>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { getPatientBedcard } from '../../api'

const props = defineProps<{
  patient: any
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
}>()

const bedcard = ref<any>(null)
const showAllTubes = ref(false)

const vitalsData = computed(() => {
  const v = bedcard.value?.metrics?.vitals || props.patient?.vitals || {}
  return [
    { label: 'HR', value: v.hr ?? '--', colorClass: vitalClass('hr', v.hr) },
    { label: 'BP', value: v.sbp ? `${v.sbp}/${v.dbp || '--'}` : '--', colorClass: vitalClass('bp', v.sbp) },
    { label: 'SpO₂', value: v.spo2 ?? '--', unit: '%', colorClass: vitalClass('spo2', v.spo2) },
    { label: 'T', value: temp(v.t || v.temp), unit: '℃', colorClass: vitalClass('t', v.t || v.temp) }
  ]
})

const formattedTubesList = computed(() => {
  return bedcard.value?.tubes || []
})

const bundleProgress = computed(() => {
  const lights = (bundleLights(props.patient) || []).filter(l => l.state !== 'unknown')
  if (!lights.length) return ''
  const done = lights.filter(l => l.state === 'green').length
  return `${done}/${lights.length}`
})

async function loadBedcard() {
  if (!props.patient?._id) return
  try {
    const res = await getPatientBedcard(props.patient._id)
    if (res.data?.code === 0) {
      bedcard.value = res.data.data
    }
  } catch (err) {
    console.error('Failed to load bedcard:', err)
  }
}

onMounted(loadBedcard)
watch(() => props.patient?._id, loadBedcard)

function vitalClass(type: string, val: any) {
  if (val == null) return ''
  const n = parseFloat(val)
  if (isNaN(n)) return ''
  
  if (type === 'hr') {
    if (n >= 120 || n <= 40) return 'vital--red'
    if (n >= 100 || n <= 50) return 'vital--orange'
  }
  if (type === 'bp') {
    if (n >= 180 || n <= 80) return 'vital--red'
    if (n >= 140 || n <= 90) return 'vital--orange'
  }
  if (type === 'spo2') {
    if (n <= 85) return 'vital--red'
    if (n <= 90) return 'vital--orange'
  }
  if (type === 't') {
    if (n >= 39 || n <= 35) return 'vital--red'
    if (n >= 38 || n <= 36) return 'vital--orange'
  }
  return ''
}

function tubeClass(days: any) {
  const d = parseInt(days)
  if (isNaN(d)) return ''
  if (d >= 14) return 'tube--red'
  if (d >= 7) return 'tube--orange'
  return ''
}




function temp(v: any) {
  if (v == null) return '--'
  const n = Number(v)
  return Number.isNaN(n) ? '--' : n.toFixed(1)
}

function shortDiag(s: string) {
  if (!s) return '无初步诊断'
  const first = s.split('|')[0] ?? s
  return first.length > 20 ? `${first.slice(0, 20)}…` : first
}

function patientDiet(patient: any) {
  return String(patient?.diet || patient?.dietType || patient?.nutritionType || '').trim()
}


function bundleLights(patient: any) {
  const lights = patient?.bundleStatus?.lights || {}
  const items = [
    { key: 'A', name: '镇痛' }, { key: 'B', name: '呼吸' },
    { key: 'C', name: '镇静' }, { key: 'D', name: '谵妄' },
    { key: 'E', name: '活动' }, { key: 'F', name: '家属' }
  ]
  const stateMap: Record<string, string> = { green: '依从', yellow: '部分', red: '未评', unknown: '空' }
  return items.map(i => ({ ...i, state: lights[i.key] || 'unknown', statusText: stateMap[lights[i.key]] || '未知' }))
}
</script>

<style scoped>
.card {
  width: 280px;
  max-height: 380px; /* Increased slightly for content */
  background: var(--card-bg);
  border-radius: 8px; /* Slightly smoother */
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 0;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow-y: auto;
  scrollbar-width: none;
  border: 1px solid var(--card-border);
  box-shadow: var(--card-shadow);
  position: relative;
}
.card::-webkit-scrollbar { display: none; }
.card:hover { 
  transform: translateY(-3px); 
  background: var(--card-hover);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.12);
}

/* 3px Left Border Severity */
.card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px; /* Slightly thicker */
  border-top-left-radius: 8px;
  border-bottom-left-radius: 8px;
  background: transparent;
}
.card--critical::before { background: #F87171; }
.card--high::before { background: #FB923C; }
.card--warning::before { background: #FBBF24; }
.card--normal::before { background: #34D399; }

/* Severity-based text coloring */
.card--critical .patient-name, .card--critical .bed-no { color: #F87171; }

section { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
section:first-of-type { margin-top: 0; }

/* Section 1: Top Bar */
.card-header { display: flex; justify-content: space-between; align-items: baseline; }
.header-main { display: flex; align-items: baseline; gap: 10px; flex: 1; min-width: 0; }
.bed-no { font-family: 'SF Mono', 'Consolas', monospace; font-size: 20px; font-weight: 900; color: var(--text-main); }
.patient-name { font-size: 16px; font-weight: 700; color: var(--text-main); margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.patient-meta { font-size: 12px; color: var(--text-muted); font-weight: 600; }

.subtitle-row { display: flex; align-items: center; gap: 6px; }
.diag-text { font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; opacity: 0.85; }
.allergy-tag { font-size: 10px; font-weight: 800; background: rgba(248, 113, 113, 0.1); border: 1px solid rgba(248, 113, 113, 0.4); color: #F87171; padding: 1px 6px; border-radius: 4px; flex-shrink: 0; }

/* Section 2: Vitals Telemetry */
.sec-vitals {
  padding: 10px 8px;
  background: var(--vitals-bg);
  border-radius: 6px;
  border: 1px solid var(--card-border);
}
.vital-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.vital-item { display: flex; flex-direction: column; align-items: center; justify-content: center; }
.v-label { font-size: 10px; color: var(--text-muted); font-weight: 800; text-transform: uppercase; margin-bottom: -1px; opacity: 0.7; }
.v-val { font-size: 26px; font-weight: 800; font-family: 'SF Mono', 'Consolas', monospace; color: var(--text-main); line-height: 1; font-variant-numeric: tabular-nums; }
.v-val small { font-size: 10px; opacity: 0.5; margin-left: 1px; font-weight: 400; }

/* Alerting Colors */
.vital--orange .v-val { color: #FB923C; }
.vital--red .v-val { color: #F87171; animation: flash-crit 1.5s infinite; }
@keyframes flash-crit { 0%, 100% { opacity: 1; } 50% { opacity: 0.75; } }

/* Section 3: Logistics */
.sec-logistics { font-size: 11px; color: var(--text-muted); gap: 6px; }
.dev-line { font-weight: 600; display: flex; align-items: center; gap: 6px; color: var(--text-main); opacity: 0.9; }
.dev-dot { width: 6px; height: 6px; border-radius: 50%; background: #60A5FA; display: inline-block; }
.tube-line { display: flex; align-items: baseline; gap: 6px; color: var(--text-muted); position: relative; }
.tube-item { transition: all 0.2s; padding: 0 5px; border-radius: 4px; background: var(--pill-bg); color: var(--text-muted); line-height: 1.7; border: 1px solid var(--card-border); }
.tube--orange { background: rgba(251, 146, 60, 0.1); color: #FB923C; border-color: rgba(251, 146, 60, 0.2); }
.tube--red { background: rgba(248, 113, 113, 0.1); color: #F87171; border-color: rgba(248, 113, 113, 0.2); }
.tube-inline-list { flex: 1; display: block; overflow: hidden; }
.tube-inline-list.is-folded { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card:hover .tube-inline-list.is-folded { -webkit-line-clamp: unset; display: block; }
.card:hover .tube-extra { display: none; }
.tube-extra { color: var(--text-muted); font-weight: 700; cursor: pointer; flex-shrink: 0; padding-top: 4px; font-size: 10px; }

/* Section 4: Alerts Tickers */
.sec-alerts { font-size: 11px; font-weight: 700; gap: 4px; }
.alert-line { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }
.alert-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.alert-dot--red { background: #F87171; }
.alert-dot--yellow { background: #FBBF24; }
.alert-dot--green { background: #34D399; }

/* Section 5: Footer Cluster */
.sec-footer { flex-direction: row; align-items: center; justify-content: space-between; padding-top: 8px; gap: 8px; border-top: 1px solid var(--card-border); }
.bundle-dots { display: flex; gap: 4px; }
.mini-dot { width: 14px; height: 14px; border-radius: 50%; font-size: 9px; font-weight: 900; display: flex; align-items: center; justify-content: center; color: #fff; border: 1px solid var(--card-border); }
.mini--green { background: #34D399; }
.mini--yellow { background: #FBBF24; }
.mini--red { background: #F87171; }
.mini--unknown { background: var(--pill-bg); color: var(--text-muted); }

.footer-pills { display: flex; gap: 6px; }
.pill { font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 5px; white-space: nowrap; border: 1px solid transparent; }
.pill--iso { background: rgba(251, 146, 60, 0.1); border-color: rgba(251, 146, 60, 0.3); color: #FB923C; }
.pill--diet { background: rgba(52, 211, 153, 0.1); border-color: rgba(52, 211, 153, 0.3); color: #34D399; }
</style>
