<template>
  <article
    :class="['card', `card--${patient.alertLevel || 'none'}`, { 'card--flash': patient.alertFlash }]"
    @click="emit('select', patient._id)"
  >
    <div class="card-head">
      <div class="head-left">
        <span class="avatar-wrap" :style="{ '--av': avatarAccent(patient) }">
          <img class="avatar" :src="avatarFor(patient)" :alt="avatarAlt(patient)" />
        </span>
        <span class="bed">{{ patient.hisBed }}<small>床</small></span>
      </div>
      <span :class="['lamp', `lamp--${patient.alertLevel || 'none'}`]"></span>
    </div>

    <div class="card-id">
      <strong class="name">{{ patient.name || '—' }}</strong>
      <span class="demo">
        <em :class="patient.gender === 'Male' ? 'm' : 'f'">{{ patient.genderText }}</em>
        <em v-if="patient.age">{{ patient.age }}</em>
        <em
          v-if="patient.icuDays != null && patient.icuDays >= 0"
          :class="['icu-d', { long: patient.icuDays > 14 }]"
        >D{{ patient.icuDays }}</em>
      </span>
    </div>

    <div class="tags" v-if="patient.clinicalTags?.length">
      <span
        v-for="tag in patient.clinicalTags.slice(0, 3)"
        :key="tag.tag"
        class="tag"
        :style="{ color: tag.color, borderColor: tag.color + '66' }"
      >
        {{ tag.label }}
      </span>
      <span v-if="patient.clinicalTags.length > 3" class="tag tag-more">
        +{{ patient.clinicalTags.length - 3 }}
      </span>
    </div>

    <p class="diag" :title="patient.clinicalDiagnosis || patient.admissionDiagnosis">
      {{ shortDiag(patient.clinicalDiagnosis || patient.admissionDiagnosis) }}
    </p>

    <div class="care-flags" v-if="patientDiet(patient) || patientIsolation(patient)">
      <span
        v-if="patientDiet(patient)"
        class="care-pill care-pill--diet"
        :title="`饮食：${patientDiet(patient)}`"
      >
        饮食 · {{ shortCare(patientDiet(patient), 8) }}
      </span>
      <span
        v-if="patientIsolation(patient)"
        class="care-pill care-pill--iso"
        :title="`隔离：${patientIsolation(patient)}`"
      >
        隔离 · {{ shortCare(patientIsolation(patient), 8) }}
      </span>
    </div>

    <div v-if="bundleLights(patient).length" class="bundle-lights" :title="bundleTooltip(patient)">
      <span
        v-for="light in bundleLights(patient)"
        :key="light.key"
        :class="['bundle-dot', `bundle-${light.state}`]"
      >
        {{ light.key }}
      </span>
    </div>

    <div class="vitals" v-if="patient.vitals?.source">
      <div class="vg">
        <div :class="['vi', vc('hr', patient.vitals.hr)]">
          <label>HR</label>
          <span>{{ patient.vitals.hr ?? '–' }}</span>
        </div>
        <div :class="['vi', 'vi-spo2', vc('spo2', patient.vitals.spo2)]">
          <label>SpO₂</label>
          <span>{{ patient.vitals.spo2 != null ? patient.vitals.spo2 + '%' : '–' }}</span>
        </div>
        <div :class="['vi', vc('rr', patient.vitals.rr)]">
          <label>RR</label>
          <span>{{ patient.vitals.rr ?? '–' }}</span>
        </div>
      </div>
      <div class="vg">
        <div :class="['vi', 'vi-bp', vc('sys', patient.vitals.nibp_sys)]">
          <label>BP</label>
          <span>{{ bp(patient.vitals) }}</span>
        </div>
        <div :class="['vi', vc('temp', patient.vitals.temp)]">
          <label>T</label>
          <span>{{ temp(patient.vitals.temp) }}</span>
        </div>
      </div>
      <time class="vt">{{ clock(patient.vitals.time) }}</time>
    </div>
    <div class="vitals vitals--empty" v-else>无监护数据</div>

    <div class="doc" v-if="patient.bedDoctor">{{ patient.bedDoctor }}</div>
  </article>
</template>

<script setup lang="ts">
import maleChild from '../../assets/avatars/male-child.svg'
import maleAdult from '../../assets/avatars/male-adult.svg'
import maleElder from '../../assets/avatars/male-elder.svg'
import femaleChild from '../../assets/avatars/female-child.svg'
import femaleAdult from '../../assets/avatars/female-adult.svg'
import femaleElder from '../../assets/avatars/female-elder.svg'

const props = defineProps<{
  patient: any
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
}>()

const avatarMap = {
  male: { child: maleChild, adult: maleAdult, elder: maleElder },
  female: { child: femaleChild, adult: femaleAdult, elder: femaleElder },
  neutral: { child: maleChild, adult: maleAdult, elder: maleElder },
} as const

function ageGroup(age: any): 'child' | 'adult' | 'elder' {
  const s = String(age ?? '').trim()
  if (!s) return 'adult'
  if (s.endsWith('天') || s.endsWith('月')) return 'child'
  const m = s.match(/(\d+)/)
  if (m) {
    const n = Number(m[1])
    if (Number.isFinite(n)) {
      if (n < 14) return 'child'
      if (n >= 60) return 'elder'
      return 'adult'
    }
  }
  return 'adult'
}

function avatarFor(patient: any) {
  const gender =
    patient?.gender === 'Female' ? 'female' :
    patient?.gender === 'Male' ? 'male' : 'neutral'
  return avatarMap[gender][ageGroup(patient?.age)]
}

function avatarAlt(patient: any) {
  const genderText = patient?.gender === 'Female' ? '女性' : patient?.gender === 'Male' ? '男性' : '未知性别'
  const group = ageGroup(patient?.age)
  const groupText = group === 'child' ? '儿童' : group === 'elder' ? '老年' : '成人'
  return `${genderText}${groupText}头像`
}

function avatarAccent(patient: any) {
  const level = String(patient?.alertLevel || 'none')
  if (level === 'critical') return '#f5222d'
  if (level === 'warning') return '#faad14'
  if (level === 'normal') return '#52c41a'
  return '#1890ff'
}

function vc(k: string, v: any): string {
  if (v == null || v === '') return ''
  const n = Number(v)
  if (Number.isNaN(n)) return ''
  const t: Record<string, [number, number, number, number]> = {
    hr: [40, 50, 110, 130],
    spo2: [85, 92, 999, 999],
    sys: [70, 85, 160, 200],
    temp: [34, 35.5, 38.5, 40],
    rr: [6, 10, 25, 35],
  }
  const current = t[k]
  if (!current) return ''
  const [critLow, warnLow, warnHigh, critHigh] = current
  if (n < critLow || n > critHigh) return 'crit'
  if (n < warnLow || n > warnHigh) return 'warn'
  return 'ok'
}

function bp(vitals: any) {
  const s = vitals?.nibp_sys
  const d = vitals?.nibp_dia
  return s != null || d != null ? `${s ?? '–'}/${d ?? '–'}` : '–'
}

function temp(v: any) {
  if (v == null) return '–'
  const n = Number(v)
  return Number.isNaN(n) ? '–' : n.toFixed(1)
}

function clock(t: any) {
  if (!t) return ''
  try {
    const d = new Date(t)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ''
  }
}

function shortDiag(s: string) {
  if (!s) return '—'
  const first = s.split('|')[0] ?? s
  return first.length > 16 ? `${first.slice(0, 16)}…` : first
}

function patientDiet(patient: any) {
  return String(
    patient?.diet ??
    patient?.dietType ??
    patient?.dietName ??
    patient?.nutritionType ??
    '',
  ).trim()
}

function patientIsolation(patient: any) {
  return String(
    patient?.isolation ??
    patient?.isolationType ??
    patient?.isolateType ??
    patient?.infectionIsolation ??
    '',
  ).trim()
}

function shortCare(v: any, n = 8) {
  const s = String(v ?? '').trim()
  if (!s) return ''
  return s.length > n ? `${s.slice(0, n)}…` : s
}

function bundleLights(patient: any) {
  const lights = patient?.bundleStatus?.lights || {}
  return ['A', 'B', 'C', 'D', 'E', 'F'].map((key) => ({
    key,
    state: lights[key] || 'unknown',
  }))
}

function bundleTooltip(patient: any) {
  const rows = bundleLights(patient).map((x: any) => `${x.key}:${x.state}`)
  return `ABCDEF Bundle - ${rows.join(' / ')}`
}
</script>

<style scoped>
.card {
  position: relative;
  background: #111119;
  border: 1px solid #1a1a28;
  border-radius: 12px;
  padding: 14px 14px 10px;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  border-color: #2a2a3c;
}
.card--critical {
  border-color: #ef444433;
  background: linear-gradient(170deg, #1a0a0e 0%, #111119 35%);
}
.card--warning {
  border-color: #f59e0b28;
  background: linear-gradient(170deg, #1a150a 0%, #111119 35%);
}
.card--high {
  border-color: #f9731628;
  background: linear-gradient(170deg, #1a120a 0%, #111119 35%);
}
.card--normal { border-color: #22c55e18; }
.card--flash { animation: flash-border 1.2s ease-in-out infinite; }

.card-head { display: flex; justify-content: space-between; align-items: center; }
.head-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.avatar-wrap {
  width: 38px;
  height: 38px;
  border-radius: 9px;
  background: color-mix(in srgb, var(--av) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--av) 60%, #1a1a28);
  box-shadow: 0 0 8px color-mix(in srgb, var(--av) 45%, transparent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 7px;
  background: #0b0b14;
  border: 1px solid #1a1a28;
  padding: 3px;
  object-fit: contain;
}
.bed {
  font-size: 22px;
  font-weight: 900;
  color: #60a5fa;
  font-family: 'SF Mono', 'JetBrains Mono', 'Consolas', monospace;
  letter-spacing: -0.5px;
}
.bed small { font-size: 11px; font-weight: 400; color: #444; margin-left: 1px; }
.lamp { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.lamp--critical { background: #ef4444; box-shadow: 0 0 8px #ef4444; animation: blink 1.4s infinite; }
.lamp--warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b88; }
.lamp--high { background: #f97316; box-shadow: 0 0 6px #f9731688; }
.lamp--normal { background: #22c55e; }
.lamp--none { background: #333; }

.card-id { display: flex; align-items: baseline; gap: 8px; }
.name { font-size: 15px; color: #e2e2e2; letter-spacing: 0.3px; }
.demo { display: flex; gap: 5px; font-size: 11px; color: #666; }
.demo em { font-style: normal; }
.demo .m { color: #60a5fa; }
.demo .f { color: #f472b6; }
.icu-d {
  font-family: monospace;
  font-weight: 700;
  font-size: 11px;
  color: #888;
  background: #1a1a28;
  padding: 0 4px;
  border-radius: 3px;
}
.icu-d.long { color: #f59e0b; background: #f59e0b15; }

.tags { display: flex; gap: 4px; flex-wrap: wrap; }
.tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border: 1px solid;
  border-radius: 3px;
  line-height: 16px;
  letter-spacing: 0.3px;
}
.tag-more { color: #555; border-color: #333; }
.diag { font-size: 12px; color: #666; line-height: 1.3; margin: 0; }

.care-flags { display: flex; gap: 4px; flex-wrap: wrap; }
.care-pill {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  border-radius: 4px;
  padding: 1px 7px;
  border: 1px solid;
  max-width: 100%;
  white-space: nowrap;
}
.care-pill--diet { color: #34d399; border-color: #34d39966; background: #34d39912; }
.care-pill--iso { color: #f59e0b; border-color: #f59e0b66; background: #f59e0b12; }

.bundle-lights { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.bundle-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 800;
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.bundle-green { background: #22c55e; }
.bundle-yellow { background: #f59e0b; color: #111827; }
.bundle-red { background: #ef4444; }
.bundle-unknown { background: #475569; }

.doc { font-size: 10px; color: #444; margin-top: auto; padding-top: 2px; }

.vitals {
  background: #0b0b14;
  border-radius: 8px;
  padding: 8px;
  margin-top: 2px;
}
.vitals--empty { text-align: center; color: #333; font-size: 11px; padding: 12px; }
.vg { display: flex; gap: 4px; margin-bottom: 4px; }
.vg:last-of-type { margin-bottom: 0; }
.vi {
  flex: 1;
  text-align: center;
  background: #0f0f1c;
  border-radius: 5px;
  padding: 5px 2px 4px;
}
.vi-bp { flex: 1.4; }
.vi label {
  display: block;
  font-size: 9px;
  font-weight: 600;
  color: #555;
  letter-spacing: 0.5px;
  margin-bottom: 1px;
}
.vi span {
  font-size: 17px;
  font-weight: 800;
  font-family: 'SF Mono', 'JetBrains Mono', 'Consolas', monospace;
  color: #ccc;
  line-height: 1;
}
.vi:first-child label { color: #22c55e88; }
.vi:first-child.ok span { color: #22c55e; }
.vi-spo2 label { color: #06b6d488; }
.vi-spo2.ok span { color: #06b6d4; }
.vi.crit { background: #ef444412; }
.vi.crit span { color: #ef4444; }
.vi.crit label { color: #ef444488; }
.vi.warn { background: #f59e0b10; }
.vi.warn span { color: #f59e0b; }
.vi.warn label { color: #f59e0b88; }
.vi.ok span { color: #a3e635; }
.vi-bp label { color: #ef444466; }
.vi-bp.ok span { color: #f87171; }
.vi:last-child label { color: #fb923c66; }
.vi:last-child.ok span { color: #fb923c; }
.vt {
  display: block;
  text-align: right;
  font-size: 9px;
  color: #333;
  margin-top: 3px;
  font-family: monospace;
}

@keyframes blink { 0%, 100% { opacity: 1 } 50% { opacity: 0.25 } }
@keyframes flash-border {
  0%, 100% { box-shadow: 0 0 0 rgba(239, 68, 68, 0); }
  50% { box-shadow: 0 0 18px rgba(239, 68, 68, 0.35); }
}

@media (max-width: 640px) {
  .card { padding: 12px 12px 10px; }
}

:global(html[data-theme='light']) .card {
  background: #ffffff;
  border-color: #d8e2f0;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
}
:global(html[data-theme='light']) .card:hover {
  border-color: #9bb1d1;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
}
:global(html[data-theme='light']) .card--critical { background: linear-gradient(170deg, #fff2f2 0%, #ffffff 45%); }
:global(html[data-theme='light']) .card--warning,
:global(html[data-theme='light']) .card--high { background: linear-gradient(170deg, #fff8ed 0%, #ffffff 45%); }
:global(html[data-theme='light']) .card--normal { background: linear-gradient(170deg, #f2fff7 0%, #ffffff 45%); }
:global(html[data-theme='light']) .bed small,
:global(html[data-theme='light']) .demo,
:global(html[data-theme='light']) .diag,
:global(html[data-theme='light']) .doc,
:global(html[data-theme='light']) .vt { color: #6b7b94; }
:global(html[data-theme='light']) .name { color: #0f172a; }
:global(html[data-theme='light']) .icu-d { background: #e9eef8; color: #51607a; }
:global(html[data-theme='light']) .tag-more { color: #677893; border-color: #bcc9dc; }
:global(html[data-theme='light']) .bundle-dot { border-color: rgba(15, 23, 42, 0.08); }
:global(html[data-theme='light']) .vitals {
  background: #f2f6fc;
  border: 1px solid #d9e2f1;
}
:global(html[data-theme='light']) .vitals--empty { color: #90a0b8; }
:global(html[data-theme='light']) .vi {
  background: #ffffff;
  border: 1px solid #dee6f4;
}
:global(html[data-theme='light']) .vi label { color: #5f6f8d; }
:global(html[data-theme='light']) .vi span { color: #22314d; }
</style>
