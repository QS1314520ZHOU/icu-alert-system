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
      <div
        v-if="patient.postExtubationRisk?.has_alert"
        :class="['extub-risk-card', `extub-risk-card--${riskTone(patient.postExtubationRisk?.severity)}`]"
      >
        <div class="extub-risk-head">
          <span class="extub-risk-title">抢救期风险卡</span>
          <span :class="['extub-risk-pill', `extub-risk-pill--${riskTone(patient.postExtubationRisk?.severity)}`]">
            {{ riskText(patient.postExtubationRisk?.severity) }}
          </span>
        </div>
        <div class="extub-risk-subtitle">拔管后再插管高风险</div>
        <div class="extub-risk-main">{{ riskSummary(patient.postExtubationRisk) }}</div>
        <div class="extub-risk-metrics">
          <span class="extub-risk-chip">RR {{ formatMetric(patient.postExtubationRisk?.rr) }}</span>
          <span class="extub-risk-chip">SpO₂ {{ formatPercent(patient.postExtubationRisk?.spo2) }}</span>
          <span class="extub-risk-chip">拔管后 {{ formatHours(patient.postExtubationRisk?.hours_since_extubation) }}</span>
        </div>
        <div class="extub-risk-brief">
          <span class="extub-risk-brief-label">迷你抢救摘要</span>
          <span class="extub-risk-brief-text">{{ riskSuggestion(patient.postExtubationRisk?.severity) }}</span>
        </div>
      </div>
      <aside
        v-if="patient.postExtubationRisk?.has_alert"
        :class="['bed-hover-drawer', `bed-hover-drawer--${riskTone(patient.postExtubationRisk?.severity)}`]"
      >
        <div class="bed-hover-head">
          <span class="bed-hover-tag">抢救期风险卡</span>
          <span :class="['bed-hover-pill', `bed-hover-pill--${riskTone(patient.postExtubationRisk?.severity)}`]">
            {{ riskText(patient.postExtubationRisk?.severity) }}
          </span>
        </div>
        <div class="bed-hover-title">{{ riskDrawerTitle() }}</div>
        <div class="bed-hover-block">
          <div class="bed-hover-label">当前判断</div>
          <div class="bed-hover-main">{{ riskSummary(patient.postExtubationRisk) }}</div>
        </div>
        <div class="bed-hover-block">
          <div class="bed-hover-label">主要依据</div>
          <div class="bed-hover-chip-row">
            <span class="bed-hover-chip">RR {{ formatMetric(patient.postExtubationRisk?.rr) }}</span>
            <span class="bed-hover-chip">SpO₂ {{ formatPercent(patient.postExtubationRisk?.spo2) }}</span>
            <span class="bed-hover-chip">拔管后 {{ formatHours(patient.postExtubationRisk?.hours_since_extubation) }}</span>
          </div>
        </div>
        <div class="bed-hover-block bed-hover-block--suggestion">
          <div class="bed-hover-label">处置建议</div>
          <div class="bed-hover-suggestion">{{ riskSuggestion(patient.postExtubationRisk?.severity) }}</div>
        </div>
      </aside>
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

function riskTone(value: any) {
  const sev = String(value || '').toLowerCase()
  if (sev === 'critical') return 'critical'
  if (sev === 'high') return 'high'
  return 'warning'
}

function riskText(value: any) {
  const sev = riskTone(value)
  if (sev === 'critical') return '危急'
  if (sev === 'high') return '高危'
  return '关注'
}

function formatMetric(value: any) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  return Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1)
}

function formatPercent(value: any) {
  const text = formatMetric(value)
  return text === '—' ? text : `${text}%`
}

function formatHours(value: any) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  if (num < 1) return `${Math.max(1, Math.round(num * 60))}min`
  return `${num.toFixed(num >= 10 ? 0 : 1)}h`
}

function riskSummary(risk: any) {
  if (!risk) return '拔管后监测中'
  const rr = formatMetric(risk?.rr)
  const spo2 = formatPercent(risk?.spo2)
  const hours = formatHours(risk?.hours_since_extubation)
  return `拔管后 ${hours} 呼吸负荷升高 · RR ${rr} / SpO₂ ${spo2}`
}

function riskDrawerTitle() {
  return '拔管后再插管高风险'
}

function riskSuggestion(value: any) {
  const sev = riskTone(value)
  if (sev === 'critical') return '建议立即评估 HFNC / NIV 支持，必要时准备再插管。'
  if (sev === 'high') return '建议尽快复查血气与分泌物负荷，严密观察气道通畅性。'
  return '建议持续加强呼吸支持与床旁复评。'
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
  transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
.bed-card::after {
  content: '';
  position: absolute;
  inset: 8px;
  border: 1px solid rgba(72, 193, 255, 0.05);
  border-radius: 9px;
  pointer-events: none;
}
.bed-card:hover {
  transform: translateY(-2px);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 16px 32px rgba(0,0,0,.28);
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
.extub-risk-card {
  margin-top: 8px;
  padding: 9px 10px 10px;
  border-radius: 10px;
  border: 1px solid rgba(251, 146, 60, 0.22);
  background:
    linear-gradient(180deg, rgba(60, 22, 13, 0.95) 0%, rgba(27, 12, 9, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
}
.extub-risk-card--critical {
  border-color: rgba(251, 90, 122, 0.32);
  background: linear-gradient(180deg, rgba(71, 16, 28, 0.96) 0%, rgba(36, 10, 17, 0.98) 100%);
}
.extub-risk-card--high {
  border-color: rgba(249, 115, 22, 0.28);
}
.extub-risk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.extub-risk-title {
  color: #fef3c7;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
}
.extub-risk-subtitle {
  margin-top: 6px;
  color: #ffd5de;
  font-size: 11px;
  font-weight: 700;
}
.extub-risk-pill {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid transparent;
}
.extub-risk-pill--warning {
  color: #fde68a;
  background: rgba(120, 53, 15, 0.9);
  border-color: rgba(245, 158, 11, 0.2);
}
.extub-risk-pill--high {
  color: #fdba74;
  background: rgba(124, 45, 18, 0.9);
  border-color: rgba(249, 115, 22, 0.24);
}
.extub-risk-pill--critical {
  color: #fecdd3;
  background: rgba(127, 29, 29, 0.9);
  border-color: rgba(251, 113, 133, 0.24);
}
.extub-risk-main {
  margin-top: 6px;
  color: #fff7ed;
  font-size: 12px;
  line-height: 1.35;
  font-weight: 600;
}
.extub-risk-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.extub-risk-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.08);
  color: #ffe7d6;
  font-size: 10px;
}
.extub-risk-brief {
  margin-top: 8px;
  display: grid;
  gap: 4px;
  padding: 7px 8px;
  border-radius: 8px;
  border: 1px solid rgba(55, 199, 147, 0.14);
  background: linear-gradient(180deg, rgba(8, 38, 30, 0.66) 0%, rgba(6, 27, 22, 0.76) 100%);
}
.extub-risk-brief-label {
  color: #8ef2c4;
  font-size: 9px;
  letter-spacing: .12em;
}
.extub-risk-brief-text {
  color: #d9ffe8;
  font-size: 10px;
  line-height: 1.45;
  font-weight: 600;
}
.bed-hover-drawer {
  position: absolute;
  inset: 8px;
  z-index: 3;
  display: grid;
  align-content: start;
  gap: 8px;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(251, 113, 133, .18);
  background:
    linear-gradient(180deg, rgba(46, 12, 22, .97) 0%, rgba(20, 8, 14, .98) 100%);
  box-shadow: 0 16px 28px rgba(0,0,0,.28);
  backdrop-filter: blur(8px);
  opacity: 0;
  transform: translateY(10px);
  pointer-events: none;
  transition: opacity .18s ease, transform .18s ease;
}
.bed-hover-drawer--high {
  border-color: rgba(249, 115, 22, .18);
  background: linear-gradient(180deg, rgba(58, 23, 11, .97) 0%, rgba(22, 11, 8, .98) 100%);
}
.bed-hover-drawer--warning {
  border-color: rgba(245, 158, 11, .16);
  background: linear-gradient(180deg, rgba(56, 35, 10, .96) 0%, rgba(24, 17, 8, .98) 100%);
}
.bed-card:hover .bed-hover-drawer {
  opacity: 1;
  transform: translateY(0);
}
.bed-hover-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.bed-hover-tag,
.bed-hover-pill {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
}
.bed-hover-tag {
  color: #ffe2e8;
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.08);
  letter-spacing: .12em;
}
.bed-hover-pill {
  border: 1px solid transparent;
}
.bed-hover-pill--critical {
  color: #fecdd3;
  background: rgba(127, 29, 29, .76);
  border-color: rgba(251, 113, 133, .24);
}
.bed-hover-pill--high {
  color: #fdba74;
  background: rgba(124, 45, 18, .76);
  border-color: rgba(249, 115, 22, .22);
}
.bed-hover-pill--warning {
  color: #fde68a;
  background: rgba(120, 53, 15, .76);
  border-color: rgba(245, 158, 11, .2);
}
.bed-hover-title {
  color: #fff0f3;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.25;
}
.bed-hover-block {
  display: grid;
  gap: 6px;
}
.bed-hover-label {
  color: #ffced9;
  font-size: 10px;
  letter-spacing: .12em;
}
.bed-hover-main {
  color: #fff8fa;
  font-size: 13px;
  line-height: 1.4;
  font-weight: 700;
}
.bed-hover-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.bed-hover-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.08);
  color: #ffe7ee;
  font-size: 10px;
}
.bed-hover-block--suggestion {
  margin-top: auto;
}
.bed-hover-suggestion {
  color: #ffe5ec;
  font-size: 11px;
  line-height: 1.45;
  font-weight: 600;
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
  .bed-hover-drawer {
    display: none;
  }
}
</style>
