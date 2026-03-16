<template>
  <article
    :class="['card', `card--${patient.alertLevel || 'none'}`, { 'card--flash': patient.alertFlash }]"
    @click="emit('select', patient._id)"
  >
    <section class="sec-top">
      <header class="card-header">
        <div class="patient-identity">
          <span class="bed-no">{{ patient.hisBed }}</span>
          <div class="identity-copy">
            <div class="monitor-line">
              <span class="monitor-label">ICU MONITOR</span>
              <span class="monitor-sep"></span>
              <span class="monitor-code">CH {{ patient.hisBed || '--' }}</span>
            </div>
            <div class="name-row">
              <h2 class="patient-name">{{ patient.name || '—' }}</h2>
              <span class="patient-meta">{{ genderLabel }}/{{ patient.age || '—' }}</span>
            </div>
            <p class="diag-text" :title="patient.clinicalDiagnosis">{{ shortDiag(patient.clinicalDiagnosis) || '无初步诊断' }}</p>
          </div>
        </div>
        <div :class="['status-badge', `status-badge--${patient.alertLevel || 'none'}`]">
          <span class="status-caption">ALERT</span>
          <strong>{{ alertStatus }}</strong>
        </div>
      </header>
      <div class="patient-tags">
        <span v-if="bedcard?.identity?.allergies || patient.allergies" class="allergy-tag">
          过敏：{{ bedcard?.identity?.allergies || patient.allergies }}
        </span>
      </div>
    </section>

    <section class="sec-vitals">
      <div class="section-head">
        <span class="section-title">生命体征</span>
        <span class="section-desc">最近一次监测</span>
      </div>
      <div class="vital-grid">
        <div v-for="v in vitalsData" :key="v.key" :class="['vital-item', `vital-item--${v.key}`, v.colorClass]">
          <span class="v-label">{{ v.label }}</span>
          <span class="v-val">{{ v.value }}<small v-if="v.unit && v.value !== '--'">{{ v.unit }}</small></span>
        </div>
      </div>
    </section>

    <section class="sec-logistics" v-if="bedcard?.devices?.length || bedcard?.tubes?.length">
      <div class="section-head">
        <span class="section-title">设备与管路</span>
        <span v-if="bedcard?.tubes?.length" class="section-desc">{{ bedcard.tubes.length }} 项留置</span>
      </div>
      <div v-if="bedcard?.devices?.length" class="info-block">
        <span class="info-label">设备</span>
        <div class="device-list">
          <span v-for="(dev, idx) in bedcard.devices.slice(0, 2)" :key="idx" class="device-tag">
            <i class="dev-dot"></i>{{ dev.name }}
          </span>
        </div>
      </div>
      <div v-if="bedcard?.tubes?.length" class="info-block">
        <span class="info-label">管路</span>
        <div :class="['tube-list', { 'tube-list--folded': !showAllTubes }]">
          <span v-for="(t, idx) in formattedTubesList" :key="idx" :class="['tube-item', tubeClass(t.dwellDays)]">
            {{ t.name }} D{{ t.dwellDays }}
          </span>
        </div>
        <button v-if="bedcard.tubes.length > 4" type="button" class="tube-toggle" @click.stop="showAllTubes = !showAllTubes">
          {{ showAllTubes ? '收起' : `展开全部（${bedcard.tubes.length}）` }}
        </button>
      </div>
    </section>

    <section class="sec-alerts" v-if="bedcard?.notes?.length || bundleProgress">
      <div class="section-head">
        <span class="section-title">护理提醒</span>
      </div>
      <div class="alert-line" v-if="bundleProgress">
        <span class="alert-dot alert-dot--yellow"></span>
        <span class="alert-text">Bundle 完成度 {{ bundleProgress }}</span>
      </div>
      <div v-for="(note, idx) in bedcard?.notes?.slice(0, 2)" :key="idx" class="alert-line">
        <span class="alert-dot alert-dot--red"></span>
        <span class="alert-text">{{ note }}</span>
      </div>
    </section>

    <section class="sec-footer">
      <div class="bundle-panel">
        <div class="bundle-head">
          <span class="footer-title">ABCDEF Bundle</span>
          <span v-if="bundleProgress" class="bundle-score">{{ bundleProgress }}</span>
        </div>
        <div class="bundle-dots">
          <span
            v-for="light in bundleLights(patient)"
            :key="light.key"
            :class="['mini-dot', `mini--${light.state}`]"
            :title="`${light.name}：${light.statusText}`"
          >{{ light.key }}</span>
        </div>
      </div>
      <div class="footer-pills">
        <span
          v-if="patient.alertLevel && patient.alertLevel !== 'none'"
          :class="['pill', 'pill--severity', `pill--severity-${patient.alertLevel}`]"
        >{{ alertStatus }}</span>
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
const genderLabel = computed(() => props.patient?.gender === 'Female' ? '女' : props.patient?.gender === 'Male' ? '男' : '—')
const alertStatus = computed(() => {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高风险',
    warning: '预警',
    normal: '稳定',
    none: '待评估'
  }
  return map[props.patient?.alertLevel || 'none'] || '待评估'
})

const vitalsData = computed(() => {
  const v = bedcard.value?.metrics?.vitals || props.patient?.vitals || {}
  return [
    { key: 'hr', label: 'HR', value: v.hr ?? '--', colorClass: vitalClass('hr', v.hr) },
    { key: 'bp', label: 'BP', value: v.sbp ? `${v.sbp}/${v.dbp || '--'}` : '--', colorClass: vitalClass('bp', v.sbp) },
    { key: 'spo2', label: 'SpO₂', value: v.spo2 ?? '--', unit: '%', colorClass: vitalClass('spo2', v.spo2) },
    { key: 'temp', label: 'T', value: temp(v.t || v.temp), unit: '℃', colorClass: vitalClass('t', v.t || v.temp) }
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
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&display=swap');

.card {
  width: 100%;
  min-height: 330px;
  max-height: 420px;
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.12) 0%, rgba(56, 189, 248, 0) 28%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.98) 0%, rgba(4, 12, 22, 0.99) 100%);
  border-radius: 14px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
  overflow-y: auto;
  scrollbar-width: none;
  border: 1px solid rgba(77, 196, 255, 0.16);
  box-shadow: 0 14px 32px rgba(2, 6, 23, 0.38);
  position: relative;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
}
.card::-webkit-scrollbar { display: none; }
.card:hover {
  transform: translateY(-4px);
  border-color: rgba(103, 232, 249, 0.34);
  box-shadow: 0 20px 38px rgba(2, 6, 23, 0.5), 0 0 18px rgba(34, 211, 238, 0.1);
}

.card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-top-left-radius: 14px;
  border-bottom-left-radius: 14px;
  background: transparent;
}
.card::after {
  content: '';
  position: absolute;
  inset: 10px;
  border: 1px solid rgba(72, 193, 255, 0.06);
  border-radius: 10px;
  pointer-events: none;
}
.card .sec-top::before,
.card .sec-footer::after {
  content: '';
  display: block;
  width: 34px;
  height: 1px;
  background: linear-gradient(90deg, rgba(103, 232, 249, 0.34), rgba(103, 232, 249, 0));
}
.card .sec-top::before {
  margin-bottom: 2px;
}
.card .sec-footer::after {
  align-self: flex-end;
  margin-top: 2px;
}
.card--critical::before { background: linear-gradient(180deg, #fb7185 0%, #ef4444 100%); }
.card--high::before { background: linear-gradient(180deg, #fb923c 0%, #f97316 100%); }
.card--warning::before { background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%); }
.card--normal::before { background: linear-gradient(180deg, #34d399 0%, #10b981 100%); }
.card--none::before { background: linear-gradient(180deg, #38bdf8 0%, #0ea5e9 100%); }
.card--flash {
  animation: card-pulse 1.8s ease-in-out infinite;
}
@keyframes card-pulse {
  0%, 100% { box-shadow: 0 14px 32px rgba(2, 6, 23, 0.38); }
  50% { box-shadow: 0 18px 40px rgba(239, 68, 68, 0.24), 0 0 24px rgba(251, 90, 122, 0.12); }
}

section { display: flex; flex-direction: column; gap: 7px; }

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.patient-identity {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}
.bed-no {
  min-width: 60px;
  padding: 6px 10px;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(9, 45, 70, 0.98) 0%, rgba(6, 25, 42, 0.98) 100%);
  border: 1px solid rgba(90, 214, 255, 0.26);
  color: #82f7ff;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
  text-align: center;
  box-shadow: inset 0 0 12px rgba(34, 211, 238, 0.08);
}
.identity-copy {
  min-width: 0;
  flex: 1;
}
.monitor-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.monitor-label,
.monitor-code {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: #5de6ef;
}
.monitor-code {
  color: #7dd3fc;
}
.monitor-sep {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(93, 230, 239, 0.34), rgba(93, 230, 239, 0));
}
.name-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.patient-name {
  font-size: 18px;
  font-weight: 800;
  color: #eefcff;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.02em;
}
.patient-meta {
  font-size: 12px;
  color: #8ea9c3;
  font-weight: 600;
  white-space: nowrap;
}
.diag-text {
  margin: 4px 0 0;
  font-size: 11px;
  color: #9ec0da;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.status-badge {
  flex-shrink: 0;
  min-width: 76px;
  padding: 6px 8px;
  border-radius: 10px;
  border: 1px solid transparent;
  background:
    linear-gradient(180deg, rgba(10, 33, 50, 0.94) 0%, rgba(7, 23, 38, 0.98) 100%);
  color: #cbd5e1;
  text-transform: uppercase;
  display: grid;
  gap: 2px;
  justify-items: end;
  box-shadow: inset 0 0 0 1px rgba(109, 216, 255, 0.05);
}
.status-caption {
  font-size: 9px;
  line-height: 1;
  letter-spacing: 0.18em;
  color: #6abed2;
}
.status-badge strong {
  font-size: 11px;
  line-height: 1.1;
  letter-spacing: 0.08em;
}
.status-badge--critical { background: rgba(71, 16, 28, 0.9); border-color: rgba(248, 113, 113, 0.34); color: #ff98aa; box-shadow: 0 0 16px rgba(251, 90, 122, 0.1); }
.status-badge--high { background: rgba(71, 36, 10, 0.88); border-color: rgba(251, 146, 60, 0.34); color: #ffb36c; }
.status-badge--warning { background: rgba(75, 54, 10, 0.88); border-color: rgba(251, 191, 36, 0.34); color: #ffd66b; }
.status-badge--normal { background: rgba(7, 63, 55, 0.88); border-color: rgba(45, 212, 191, 0.3); color: #56f0c7; }
.status-badge--none { background: rgba(8, 28, 44, 0.88); border-color: rgba(56, 189, 248, 0.2); color: #99dfff; }

.patient-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.allergy-tag {
  font-size: 11px;
  font-weight: 700;
  background: rgba(71, 16, 28, 0.84);
  border: 1px solid rgba(248, 113, 113, 0.24);
  color: #ff95a8;
  padding: 5px 10px;
  border-radius: 8px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.section-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: #68f5ff;
  text-transform: uppercase;
}
.section-desc {
  font-size: 10px;
  color: #72a7c5;
}

.sec-vitals,
.sec-logistics,
.sec-alerts,
.sec-footer {
  padding: 10px;
  background: linear-gradient(180deg, rgba(5, 18, 31, 0.92) 0%, rgba(7, 16, 28, 0.86) 100%);
  border: 1px solid rgba(71, 196, 255, 0.12);
  border-radius: 10px;
  box-shadow: inset 0 1px 0 rgba(171, 237, 255, 0.04);
}
.vital-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.vital-item {
  min-height: 74px;
  padding: 9px 10px;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(8, 31, 49, 0.98) 0%, rgba(6, 21, 35, 0.98) 100%);
  border: 1px solid rgba(71, 196, 255, 0.14);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: inset 0 0 0 1px rgba(11, 71, 95, 0.2);
}
.v-label {
  font-size: 10px;
  color: #7ecce1;
  font-weight: 700;
  letter-spacing: 0.14em;
}
.v-val {
  font-size: 24px;
  font-weight: 800;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
  color: #ecfeff;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  word-break: break-all;
  text-shadow: 0 0 10px rgba(110, 231, 249, 0.12);
}
.vital-item--bp .v-val {
  font-size: 20px;
}
.v-val small {
  font-size: 10px;
  opacity: 0.72;
  margin-left: 4px;
  font-weight: 600;
}
.vital--orange {
  background: linear-gradient(180deg, rgba(88, 46, 12, 0.94) 0%, rgba(36, 25, 12, 0.92) 100%);
  border-color: rgba(251, 146, 60, 0.28);
  box-shadow: inset 0 0 0 1px rgba(251, 146, 60, 0.12), 0 0 12px rgba(251, 146, 60, 0.08);
}
.vital--orange .v-label,
.vital--orange .v-val { color: #fdba74; }
.vital--red {
  background: linear-gradient(180deg, rgba(87, 17, 33, 0.94) 0%, rgba(46, 11, 20, 0.92) 100%);
  border-color: rgba(248, 113, 113, 0.28);
  box-shadow: inset 0 0 0 1px rgba(248, 113, 113, 0.12), 0 0 14px rgba(248, 113, 113, 0.08);
}
.vital--red .v-label,
.vital--red .v-val { color: #fda4af; }

.sec-logistics,
.sec-alerts {
  gap: 10px;
}
.info-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.info-label {
  font-size: 10px;
  color: #7f91ab;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.device-list,
.tube-list,
.footer-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.device-tag,
.tube-item,
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
  background: rgba(8, 30, 46, 0.88);
  border: 1px solid rgba(71, 196, 255, 0.12);
  color: #d9f9ff;
  font-size: 10px;
  line-height: 1.2;
}
.dev-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3ee7c0;
  display: inline-block;
  box-shadow: 0 0 0 4px rgba(62, 231, 192, 0.12);
}
.tube-list--folded {
  max-height: 72px;
  overflow: hidden;
}
.tube-item {
  color: #bcecff;
}
.tube--orange {
  background: rgba(76, 43, 12, 0.92);
  color: #fdba74;
  border-color: rgba(251, 146, 60, 0.22);
}
.tube--red {
  background: rgba(70, 16, 28, 0.92);
  color: #fda4af;
  border-color: rgba(248, 113, 113, 0.22);
}
.tube-toggle {
  align-self: flex-start;
  padding: 0;
  border: none;
  background: transparent;
  color: #67e8f9;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
}

.alert-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: #d7fbff;
}
.alert-text {
  font-size: 11px;
  line-height: 1.4;
  color: #c7e6f5;
}
.alert-dot {
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.alert-dot--red { background: #fb7185; }
.alert-dot--yellow { background: #fbbf24; box-shadow: 0 0 8px rgba(251, 191, 36, 0.32); }

.sec-footer {
  margin-top: auto;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid rgba(71, 196, 255, 0.12);
}
.bundle-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(8, 30, 46, 0.9) 0%, rgba(5, 18, 31, 0.94) 100%);
  border: 1px solid rgba(80, 199, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.bundle-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.footer-title {
  font-size: 10px;
  font-weight: 700;
  color: #68f5ff;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.bundle-score {
  font-size: 10px;
  font-family: 'SF Mono', 'Consolas', monospace;
  color: #d8f7ff;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(7, 22, 36, 0.96);
  border: 1px solid rgba(80, 199, 255, 0.14);
}
.bundle-dots {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding-top: 6px;
  border-top: 1px solid rgba(80, 199, 255, 0.08);
}
.mini-dot {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-family: 'Rajdhani', sans-serif;
}
.mini--green { background: linear-gradient(180deg, #34d399 0%, #10b981 100%); box-shadow: 0 0 12px rgba(52, 211, 153, 0.16); }
.mini--yellow { background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%); box-shadow: 0 0 12px rgba(251, 191, 36, 0.16); }
.mini--red { background: linear-gradient(180deg, #fb7185 0%, #ef4444 100%); box-shadow: 0 0 12px rgba(251, 113, 133, 0.16); }
.mini--unknown { background: rgba(12, 41, 62, 0.9); color: #7ecce1; }

.footer-pills {
  justify-content: flex-end;
  align-items: center;
  align-self: stretch;
  align-content: flex-start;
  max-width: 42%;
}
.pill {
  font-size: 10px;
  font-weight: 700;
}
.pill--severity {
  background: rgba(8, 28, 44, 0.88);
  color: #dff8ff;
}
.pill--severity-critical { background: rgba(70, 16, 28, 0.92); color: #ff98aa; border-color: rgba(248, 113, 113, 0.24); }
.pill--severity-high { background: rgba(76, 43, 12, 0.92); color: #fdba74; border-color: rgba(251, 146, 60, 0.24); }
.pill--severity-warning { background: rgba(75, 54, 10, 0.92); color: #fcd34d; border-color: rgba(251, 191, 36, 0.24); }
.pill--severity-normal { background: rgba(7, 63, 55, 0.92); color: #5eead4; border-color: rgba(45, 212, 191, 0.24); }
.pill--iso { background: rgba(42, 22, 81, 0.9); border-color: rgba(167, 139, 250, 0.24); color: #d0b8ff; }
.pill--diet { background: rgba(8, 56, 42, 0.92); border-color: rgba(74, 222, 128, 0.24); color: #86efac; }

@media (max-width: 640px) {
  .card {
    padding: 14px;
    border-radius: 12px;
  }
  .patient-name {
    font-size: 16px;
  }
  .v-val {
    font-size: 22px;
  }
  .vital-item--bp .v-val {
    font-size: 18px;
  }
  .sec-footer {
    flex-direction: column;
    align-items: flex-start;
  }
  .bundle-panel,
  .footer-pills {
    max-width: none;
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
