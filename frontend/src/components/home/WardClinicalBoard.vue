<template>
  <section class="wcb">
    <header class="wcb-head">
      <span class="wcb-head__title">{{ title }}</span>
      <span class="wcb-head__meta">
        <template v-if="windowText">{{ windowText }}</template>
        <button type="button" class="wcb-head__btn" :disabled="busy" @click="reload">{{ busy ? '加载中…' : '刷新' }}</button>
      </span>
    </header>

    <div v-if="error && !rows.length" class="wcb-state wcb-state--err">床位数据加载失败：{{ error }}</div>
    <div v-else-if="busy && !rows.length" class="wcb-state">正在读取床位与本班数据…</div>
    <div v-else-if="!rows.length" class="wcb-state">{{ emptyText }}</div>

    <template v-else>
      <!-- 结论 -->
      <div class="wcb-brief">
        <p class="wcb-brief__headline" :class="`is-${headlineTone}`">{{ headline }}</p>
        <div class="wcb-tiles">
          <div class="wcb-tile"><b>{{ rows.length }}</b><span>{{ scopeLabel }}</span></div>
          <div class="wcb-tile" :class="{ 'is-crit': counts.critical }"><b>{{ counts.critical }}</b><span>危急</span></div>
          <div class="wcb-tile" :class="{ 'is-warn': counts.high }"><b>{{ counts.high }}</b><span>高危</span></div>
          <div class="wcb-tile" :class="{ 'is-crit': counts.criticalValues }"><b>{{ counts.criticalValues }}</b><span>本班危急值</span></div>
          <div class="wcb-tile" :class="{ 'is-warn': counts.unclosed }"><b>{{ counts.unclosed }}</b><span>未闭环告警</span></div>
          <div class="wcb-tile"><b>{{ counts.vent }}<small>/{{ counts.vaso }}/{{ counts.crrt }}</small></b><span>机械通气/升压/CRRT</span></div>
        </div>
        <p v-if="sourceGaps.length" class="wcb-gap">数据源未接入或读取失败：{{ sourceGaps.join('、') }}，相关数字可能偏低，不代表 0。</p>
      </div>

      <!-- 筛选 -->
      <div class="wcb-filter">
        <button v-for="f in filters" :key="f.key" type="button" class="wcb-filter__btn" :class="{ 'is-on': filter === f.key }" @click="filter = f.key">
          {{ f.label }} <em>{{ f.count }}</em>
        </button>
      </div>

      <!-- 床位卡 -->
      <div class="wcb-grid">
        <article v-for="p in visibleRows" :key="p.patient_id" class="wcb-card" :class="`risk-${p.risk_level}`" @click="goPatient(p.patient_id)">
          <div class="wcb-card__top">
            <span class="wcb-card__bed">{{ p.bed || '—' }}<small>床</small></span>
            <span class="wcb-card__name">{{ p.name || '未知' }}</span>
            <span
              v-if="vitalMismatch(p)"
              class="wcb-chip chip-warn"
              title="分级来自已触发的预警规则；当前体征已超出危急阈值但尚未触发预警，请床旁复核"
            >体征异常</span>
            <span class="wcb-chip" :class="`chip-${riskTone(p.risk_level)}`">{{ RISK_LABELS[p.risk_level] || '未评估' }}</span>
          </div>
          <div class="wcb-card__diag" :title="p.diagnosis">{{ p.diagnosis || '诊断未记录' }}</div>

          <div class="wcb-vitals">
            <span v-for="v in vitalCells(p.patient_id)" :key="v.k" class="wcb-vital" :class="v.tone && `is-${v.tone}`">
              <i>{{ v.k }}</i>{{ v.v }}
            </span>
            <span
              v-if="vitalTime(p.patient_id)"
              class="wcb-vital-time"
              :class="{ 'is-stale': vitalStale(p.patient_id) }"
              :title="vitalStale(p.patient_id) ? '最近一次体征记录超过 1 小时，数值可能已变化' : '最近一次体征记录时间'"
            >{{ vitalTime(p.patient_id) }}{{ vitalStale(p.patient_id) ? ' 已超1h' : '' }}</span>
          </div>

          <ul v-if="reasonsOf(p).length" class="wcb-reasons">
            <li v-for="r in reasonsOf(p).slice(0, 3)" :key="r">{{ r }}</li>
          </ul>
          <div v-else-if="abnormalVitals(p.patient_id).length" class="wcb-reasons wcb-reasons--vital">
            未触发预警，但体征异常：{{ abnormalVitals(p.patient_id).join('、') }}
          </div>
          <div v-else class="wcb-reasons wcb-reasons--none">本班无触发项</div>

          <div class="wcb-card__foot">
            <span class="wcb-support">
              <em v-if="p.has_ventilator">机械通气</em>
              <em v-if="p.has_vasoactive" class="warn">升压药</em>
              <em v-if="p.has_crrt">CRRT</em>
              <em v-if="p.high_risk_line_count > 0" class="warn">高危管路×{{ p.high_risk_line_count }}</em>
            </span>
            <span class="wcb-card__actions">
              <span class="wcb-ho" :class="`ho-${p.handover_status || 'not_started'}`">交班{{ HANDOVER_STATUS_LABELS[p.handover_status || 'not_started'] || '未开始' }}</span>
              <button type="button" class="wcb-link" @click.stop="goAlerts(p.patient_id)">预警</button>
              <button type="button" class="wcb-link" @click.stop="goHandover(p.patient_id)">交班</button>
            </span>
          </div>
        </article>
      </div>
      <p v-if="!visibleRows.length" class="wcb-state">当前筛选下无患者</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getBatchVitals } from '../../api'
import {
  useShiftSummary, deriveRiskReasons, formatDateTime, RISK_LABELS, RISK_ORDER,
  HANDOVER_STATUS_LABELS, type ShiftPatientStat,
} from '../../composables/useShiftSummary'

const props = withDefaults(defineProps<{
  title?: string
  /** 只展示这些患者（如医生分管床位）；为空则展示全科 */
  patientIds?: string[]
  scopeLabel?: string
  emptyText?: string
  defaultFilter?: 'all' | 'focus' | 'support'
}>(), {
  title: '床位临床概览',
  patientIds: () => [],
  scopeLabel: '在科患者',
  emptyText: '当前班次暂无在科患者数据',
  defaultFilter: 'all',
})

const route = useRoute()
const router = useRouter()
const { loading, error, summary, patients, deptCode, load } = useShiftSummary()
const vitals = ref<Record<string, any>>({})
const vitalsLoading = ref(false)
const filter = ref<'all' | 'focus' | 'support'>(props.defaultFilter)

const busy = computed(() => loading.value || vitalsLoading.value)

const rows = computed<ShiftPatientStat[]>(() => {
  const ids = new Set((props.patientIds || []).map(String).filter(Boolean))
  const list = ids.size ? patients.value.filter((p) => ids.has(String(p.patient_id))) : patients.value
  return [...list].sort((a, b) =>
    (RISK_ORDER[a.risk_level] ?? 9) - (RISK_ORDER[b.risk_level] ?? 9)
    || String(a.bed).localeCompare(String(b.bed), 'zh-CN', { numeric: true }))
})

const counts = computed(() => {
  const c = { critical: 0, high: 0, criticalValues: 0, unclosed: 0, vent: 0, vaso: 0, crrt: 0 }
  for (const p of rows.value) {
    if (p.risk_level === 'critical') c.critical++
    if (p.risk_level === 'high') c.high++
    c.criticalValues += Number(p.critical_value_count || 0)
    c.unclosed += Number(p.unclosed_alert_count || 0)
    if (p.has_ventilator) c.vent++
    if (p.has_vasoactive) c.vaso++
    if (p.has_crrt) c.crrt++
  }
  return c
})

const headline = computed(() => {
  const c = counts.value
  const urgent = rows.value.filter((p) => p.risk_level === 'critical' || p.risk_level === 'high')
  if (!urgent.length) {
    return c.unclosed ? `无危急/高危患者，仍有 ${c.unclosed} 条未闭环告警待处理` : '当前无危急/高危患者，按常规巡视'
  }
  const beds = urgent.slice(0, 4).map((p) => `${p.bed}床`).join('、')
  const parts = [`${beds}${urgent.length > 4 ? ` 等 ${urgent.length} 人` : ''}需优先处理`]
  if (c.criticalValues) parts.push(`本班危急值 ${c.criticalValues} 条`)
  if (c.unclosed) parts.push(`未闭环告警 ${c.unclosed} 条`)
  return parts.join('；')
})
const headlineTone = computed(() => (counts.value.critical ? 'crit' : counts.value.high || counts.value.unclosed ? 'warn' : 'ok'))

const filters = computed(() => [
  { key: 'all' as const, label: '全部', count: rows.value.length },
  { key: 'focus' as const, label: '危急/高危', count: counts.value.critical + counts.value.high },
  { key: 'support' as const, label: '生命支持', count: rows.value.filter(isSupport).length },
])
const visibleRows = computed(() => {
  if (filter.value === 'focus') return rows.value.filter((p) => p.risk_level === 'critical' || p.risk_level === 'high')
  if (filter.value === 'support') return rows.value.filter(isSupport)
  return rows.value
})

const SOURCE_LABELS: Record<string, string> = { orders: '医嘱', tasks: '护理任务', alerts: '告警', devices: '设备', vitals: '生命体征', labs: '检验' }
const sourceGaps = computed(() => {
  const s = summary.value || {}
  const list = [...(s.missing_sources || []), ...(s.failed_sources || [])]
  return Array.from(new Set(list.map((x: string) => SOURCE_LABELS[x] || x)))
})
const windowText = computed(() => {
  const s = summary.value
  if (!s) return ''
  const name = s.shift_name || s.shift?.name || ''
  return [name, s.data_start ? `${formatDateTime(s.data_start)} 起` : ''].filter(Boolean).join(' · ')
})

function isSupport(p: ShiftPatientStat) { return !!(p.has_ventilator || p.has_vasoactive || p.has_crrt) }
function reasonsOf(p: ShiftPatientStat) { return deriveRiskReasons(p) }
function riskTone(level: string) {
  if (level === 'critical') return 'crit'
  if (level === 'high' || level === 'medium') return 'warn'
  if (level === 'stable') return 'ok'
  return 'muted'
}

function num(v: any): number | null {
  const n = Number(v)
  return v == null || v === '' || !Number.isFinite(n) ? null : n
}
function pick(v: any, ...keys: string[]) {
  for (const k of keys) { const n = num(v?.[k]); if (n != null) return n }
  return null
}
function tone(kind: string, n: number | null): '' | 'crit' | 'warn' {
  if (n == null) return ''
  switch (kind) {
    case 'HR': return n >= 130 || n <= 40 ? 'crit' : n >= 110 || n <= 50 ? 'warn' : ''
    case 'MAP': return n < 60 ? 'crit' : n < 65 || n > 110 ? 'warn' : ''
    case 'SpO₂': return n < 88 ? 'crit' : n < 92 ? 'warn' : ''
    case 'RR': return n >= 35 || n <= 8 ? 'crit' : n >= 25 || n <= 10 ? 'warn' : ''
    case 'T': return n >= 39.5 || n < 35 ? 'crit' : n >= 38.3 || n < 36 ? 'warn' : ''
    default: return ''
  }
}
function vitalCells(pid: string) {
  const v = vitals.value[pid]
  const cells = [
    { k: 'HR', n: pick(v, 'hr'), fmt: (n: number) => String(Math.round(n)) },
    { k: 'MAP', n: pick(v, 'map', 'ibp_map', 'nibp_map'), fmt: (n: number) => String(Math.round(n)) },
    { k: 'SpO₂', n: pick(v, 'spo2'), fmt: (n: number) => `${Math.round(n)}%` },
    { k: 'RR', n: pick(v, 'rr'), fmt: (n: number) => String(Math.round(n)) },
    { k: 'T', n: pick(v, 'temp', 't'), fmt: (n: number) => n.toFixed(1) },
  ]
  return cells.map((c) => ({ k: c.k, v: c.n == null ? '—' : c.fmt(c.n), tone: tone(c.k, c.n) }))
}
/** 超出危急阈值的体征（仅展示，不改变后端分级） */
function abnormalVitals(pid: string) {
  return vitalCells(pid).filter((c) => c.tone === 'crit').map((c) => `${c.k} ${c.v}`)
}
/** 分级为平稳/低危/未评估，但体征已达危急阈值：提示复核 */
function vitalMismatch(p: ShiftPatientStat) {
  if (p.risk_level === 'critical' || p.risk_level === 'high') return false
  return abnormalVitals(p.patient_id).length > 0
}
function vitalStale(pid: string) {
  const t = vitals.value[pid]?.time
  if (!t) return false
  const ms = new Date(t).getTime()
  return Number.isFinite(ms) && Date.now() - ms > 60 * 60 * 1000
}
function vitalTime(pid: string) {
  const t = vitals.value[pid]?.time
  return t ? formatDateTime(t).slice(6) : ''
}

async function loadVitals() {
  vitalsLoading.value = true
  try {
    const params = deptCode.value ? { dept_code: deptCode.value, patient_scope: 'in_dept' } : { patient_scope: 'in_dept' }
    const res = await getBatchVitals(params)
    vitals.value = res?.data?.vitals || {}
  } catch {
    vitals.value = {}
  } finally {
    vitalsLoading.value = false
  }
}
function reload() { void load(); void loadVitals() }

function goPatient(id: string) { router.push({ path: `/patient/${id}`, query: route.query }) }
function goAlerts(id: string) { router.push({ path: `/patient/${id}/alerts`, query: route.query }) }
function goHandover(id: string) { router.push({ name: 'handover-patient', params: { patientId: id }, query: route.query }) }

onMounted(reload)
watch(() => props.defaultFilter, (v) => { filter.value = v })
defineExpose({ reload })
</script>

<style scoped>
.wcb { background: #fff; border: 1px solid #E6E5E3; border-radius: 10px; overflow: hidden }
.wcb-head { height: 38px; background: #5392FF; color: #fff; display: flex; align-items: center; justify-content: space-between; padding: 0 16px }
.wcb-head__title { font-size: 14px; font-weight: 600 }
.wcb-head__meta { display: flex; align-items: center; gap: 10px; font-size: 12px }
.wcb-head__btn { border: 1px solid rgba(255,255,255,.6); background: transparent; color: #fff; border-radius: 6px; padding: 1px 10px; font-size: 12px; cursor: pointer }
.wcb-head__btn:disabled { opacity: .6; cursor: default }
.wcb-state { padding: 18px 16px; font-size: 13px; color: #57534E }
.wcb-state--err { color: #B91C1C }
.wcb-brief { padding: 12px 16px 4px }
.wcb-brief__headline { margin: 0 0 10px; font-size: 15px; font-weight: 600; color: #1C1917; padding-left: 10px; border-left: 3px solid #5392FF }
.wcb-brief__headline.is-crit { border-left-color: #DC2626; color: #991B1B }
.wcb-brief__headline.is-warn { border-left-color: #D97706 }
.wcb-tiles { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px }
.wcb-tile { border: 1px solid #E6E5E3; border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; background: #FAFAF9 }
.wcb-tile b { font-size: 20px; line-height: 1.2; color: #1C1917 }
.wcb-tile b small { font-size: 14px; color: #57534E; font-weight: 600 }
.wcb-tile span { font-size: 12px; color: #57534E }
.wcb-tile.is-crit { background: #FEF2F2; border-color: #FCA5A5 } .wcb-tile.is-crit b { color: #B91C1C }
.wcb-tile.is-warn { background: #FFFBEB; border-color: #FCD34D } .wcb-tile.is-warn b { color: #B45309 }
.wcb-gap { margin: 8px 0 0; font-size: 12px; color: #B45309 }
.wcb-filter { display: flex; gap: 6px; padding: 10px 16px 0 }
.wcb-filter__btn { border: 1px solid #E6E5E3; background: #fff; border-radius: 999px; padding: 2px 12px; font-size: 12px; color: #44403C; cursor: pointer }
.wcb-filter__btn em { font-style: normal; font-weight: 600; margin-left: 2px }
.wcb-filter__btn.is-on { background: #EEF4FF; border-color: #5392FF; color: #1D4ED8 }
.wcb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; padding: 10px 16px 16px }
.wcb-card { border: 1px solid #E6E5E3; border-left: 4px solid #D6D3D1; border-radius: 8px; padding: 10px 12px; cursor: pointer; display: flex; flex-direction: column; gap: 6px; background: #fff; transition: box-shadow .15s }
.wcb-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08) }
.wcb-card.risk-critical { border-left-color: #DC2626 }
.wcb-card.risk-high { border-left-color: #F59E0B }
.wcb-card.risk-medium { border-left-color: #FCD34D }
.wcb-card.risk-stable { border-left-color: #6BBF8E }
.wcb-card__top { display: flex; align-items: center; gap: 8px }
.wcb-card__bed { font-size: 18px; font-weight: 700; color: #1C1917 }
.wcb-card__bed small { font-size: 12px; font-weight: 500; margin-left: 1px; color: #57534E }
.wcb-card__name { font-size: 14px; font-weight: 600; color: #1C1917; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.wcb-chip { font-size: 12px; padding: 1px 8px; border-radius: 999px; border: 1px solid #E6E5E3; background: #FAFAF9; color: #57534E; white-space: nowrap }
.chip-crit { background: #FEF2F2; color: #B91C1C; border-color: #FCA5A5 }
.chip-warn { background: #FFFBEB; color: #B45309; border-color: #FCD34D }
.chip-ok { background: #E7F5EE; color: #2F7D55; border-color: #A7D9BF }
.wcb-card__diag { font-size: 12px; color: #44403C; overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.wcb-vitals { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; font-size: 13px; font-weight: 600; color: #1C1917; font-variant-numeric: tabular-nums }
.wcb-vital i { font-style: normal; font-size: 11px; font-weight: 500; color: #78716C; margin-right: 2px }
.wcb-vital.is-crit { color: #B91C1C } .wcb-vital.is-warn { color: #B45309 }
.wcb-vital-time { margin-left: auto; font-size: 11px; font-weight: 400; color: #78716C }
.wcb-reasons { margin: 0; padding-left: 16px; font-size: 12px; color: #991B1B; line-height: 1.6 }
.risk-high .wcb-reasons, .risk-medium .wcb-reasons { color: #92400E }
.wcb-reasons--none { padding-left: 0; color: #78716C }
.wcb-reasons--vital { padding-left: 0; color: #B45309 }
.wcb-vital-time.is-stale { color: #B45309 }
.wcb-card__foot { display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-top: auto; padding-top: 6px; border-top: 1px dashed #EDECEA }
.wcb-support { display: flex; flex-wrap: wrap; gap: 4px }
.wcb-support em { font-style: normal; font-size: 11px; padding: 0 6px; border-radius: 4px; background: #EEF4FF; color: #1D4ED8 }
.wcb-support em.warn { background: #FFFBEB; color: #B45309 }
.wcb-card__actions { display: flex; align-items: center; gap: 8px; white-space: nowrap }
.wcb-ho { font-size: 11px; color: #78716C }
.wcb-ho.ho-acknowledged { color: #2F7D55 } .wcb-ho.ho-returned { color: #B91C1C } .wcb-ho.ho-submitted { color: #1D4ED8 }
.wcb-link { border: 0; background: none; padding: 0; font-size: 12px; color: #2563EB; cursor: pointer }
.wcb-link:hover { text-decoration: underline }
@media (max-width: 1100px) { .wcb-tiles { grid-template-columns: repeat(3, minmax(0, 1fr)) } }
</style>
