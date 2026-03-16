<template>
  <div class="bed-grid">
    <div
      v-for="patient in patients"
      :key="patient._id"
      :class="['bed-card', `bed-${patient.alertLevel || 'none'}`, { flash: patient.alertFlash }]"
    >
      <div class="bed-head">
        <div class="bed-head-main">
          <div class="bed-no">{{ patient.hisBed || '--' }}床</div>
          <div class="bed-tags">
            <span class="bed-tag">ICU</span>
            <span :class="['bed-tag', 'bed-tag--soft', `bed-tag--${patient.alertLevel || 'none'}`]">
              {{ alertText(patient.alertLevel) }}
            </span>
          </div>
        </div>
        <span :class="['lamp', `lamp-${patient.alertLevel || 'none'}`]"></span>
      </div>
      <div class="bed-name-row">
        <div class="bed-name">{{ patient.name || '—' }}</div>
        <div class="bed-meta">{{ genderText(patient.gender) }} / {{ patient.age || '—' }}</div>
      </div>
      <div class="bed-diag">{{ shortDiag(patient.clinicalDiagnosis || patient.admissionDiagnosis) }}</div>
      <div class="bed-vitals">
        <div class="vital-cell">
          <span>HR</span>
          <b>{{ patient.vitals?.hr ?? '—' }}</b>
        </div>
        <div class="vital-cell">
          <span>SpO₂</span>
          <b>{{ patient.vitals?.spo2 ?? '—' }}</b>
        </div>
        <div class="vital-cell">
          <span>RR</span>
          <b>{{ patient.vitals?.rr ?? '—' }}</b>
        </div>
        <div class="vital-cell vital-cell--bp">
          <span>BP</span>
          <b>{{ formatBp(patient.vitals) }}</b>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  patients: any[]
}>()

function genderText(v: any) {
  if (v === 'Male' || v === '男') return '男'
  if (v === 'Female' || v === '女') return '女'
  return '—'
}

function alertText(v: any) {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高危',
    warning: '预警',
    normal: '稳定',
    none: '监测中',
  }
  return map[String(v || 'none')] || '监测中'
}

function shortDiag(v: any) {
  const s = String(v || '').trim()
  if (!s) return '暂无诊断信息'
  const first = s.split('|')[0] || s
  return first.length > 18 ? `${first.slice(0, 18)}…` : first
}

function formatBp(vitals: any) {
  const sys = vitals?.nibp_sys ?? vitals?.ibp_sys
  const dia = vitals?.nibp_dia ?? vitals?.ibp_dia
  if (sys == null) return '—'
  return `${sys}/${dia ?? '--'}`
}
</script>

<style scoped>
.bed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(188px, 1fr));
  gap: 10px;
}
.bed-card {
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.1) 0%, rgba(56, 189, 248, 0) 26%),
    linear-gradient(180deg, rgba(8, 22, 36, 0.96) 0%, rgba(5, 14, 25, 0.98) 100%);
  border: 1px solid rgba(80, 199, 255, 0.14);
  border-radius: 12px;
  padding: 10px 10px 11px;
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 8px 20px rgba(0,0,0,.2);
}
.bed-card::after {
  content: '';
  position: absolute;
  inset: 8px;
  border: 1px solid rgba(72, 193, 255, 0.05);
  border-radius: 9px;
  pointer-events: none;
}
.bed-card.flash { animation: flash-border 1.2s ease-in-out infinite; }
.bed-critical { border-color: rgba(251, 90, 122, 0.3); }
.bed-warning { border-color: rgba(245, 158, 11, 0.28); }
.bed-high { border-color: rgba(249, 115, 22, 0.28); }
.bed-normal { border-color: rgba(52, 211, 153, 0.2); }
.bed-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.bed-head-main {
  min-width: 0;
}
.bed-no {
  font-size: 18px;
  font-weight: 700;
  color: #7de8f6;
  line-height: 1.05;
}
.bed-tags {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.bed-tag {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(9, 35, 52, 0.9);
  border: 1px solid rgba(80, 199, 255, 0.12);
  color: #73d9ee;
  font-size: 10px;
  letter-spacing: .08em;
}
.bed-tag--soft {
  color: #dffbff;
}
.bed-tag--critical { color: #fda4af; border-color: rgba(248,113,113,.24); background: rgba(70,16,28,.9); }
.bed-tag--high { color: #fdba74; border-color: rgba(249,115,22,.24); background: rgba(71,36,10,.9); }
.bed-tag--warning { color: #fcd34d; border-color: rgba(245,158,11,.24); background: rgba(75,54,10,.9); }
.bed-tag--normal { color: #6ee7b7; border-color: rgba(52,211,153,.22); background: rgba(7,63,55,.88); }
.bed-tag--none { color: #93c5fd; }
.bed-name-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
  margin: 8px 0 4px;
}
.bed-name {
  font-size: 14px;
  color: #effcff;
  font-weight: 700;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bed-meta {
  color: #7ecce1;
  font-size: 10px;
  white-space: nowrap;
}
.bed-diag {
  color: #8fb8ca;
  font-size: 11px;
  line-height: 1.35;
  min-height: 30px;
}
.bed-vitals {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 8px;
}
.vital-cell {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 8px;
  background: rgba(7, 27, 42, 0.84);
  border: 1px solid rgba(80,199,255,.1);
  font-size: 10px;
  color: #7ecce1;
}
.vital-cell span {
  letter-spacing: .08em;
}
.vital-cell b {
  color: #effcff;
  font-size: 14px;
  font-family: 'JetBrains Mono', monospace;
}
.vital-cell--bp {
  grid-column: 1 / -1;
}
.vital-cell--bp b {
  font-size: 13px;
}
.lamp { width: 8px; height: 8px; border-radius: 50%; }
.lamp-critical { background: #ef4444; box-shadow: 0 0 6px #ef4444; }
.lamp-warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
.lamp-high { background: #f97316; box-shadow: 0 0 6px #f97316; }
.lamp-normal { background: #22c55e; }
.lamp-none { background: #334155; }

@keyframes flash-border {
  0%, 100% { box-shadow: 0 0 0 rgba(239, 68, 68, 0); }
  50% { box-shadow: 0 0 18px rgba(239, 68, 68, 0.35); }
}

@media (max-width: 1100px) {
  .bed-grid {
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  }
}
</style>
