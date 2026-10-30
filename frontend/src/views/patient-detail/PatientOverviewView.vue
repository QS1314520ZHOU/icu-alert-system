<template>
  <div class="overview-view">
    <!-- 结论先行：当前判断 + 异常要点 + 下一步 -->
    <section class="pov-brief" :class="`pov-brief--${briefTone}`">
      <div class="pov-brief-head">
        <span class="pov-brief-title">当前判断</span>
        <span class="pov-brief-meta">{{ vitalsSourceText }} · {{ heroMonitorUpdatedAt }}</span>
      </div>
      <div class="pov-brief-body">
        <div class="pov-brief-main">
          <div class="pov-headline" :class="`pov-headline--${briefTone}`">{{ briefHeadline }}</div>
          <div class="pov-chips">
            <span v-for="c in abnormalVitals" :key="c.label" class="pov-chip" :class="c.tone === 'critical' ? 'crit' : 'warn'">{{ c.label }} {{ c.value }}</span>
            <span v-for="o in abnormalOrgans" :key="o.key" class="pov-chip" :class="organStatusClass(o.key) === 'organ-critical' ? 'crit' : 'warn'">{{ o.label }}{{ organStatusText(o.key) }}</span>
            <span v-if="sepsisActive" class="pov-chip warn">脓毒症 {{ sepsisBundleStatusText }}</span>
            <span v-if="openAlertCount" class="pov-chip crit">未处理预警 {{ openAlertCount }}</span>
            <span v-else class="pov-chip ok">无未处理预警</span>
          </div>
        </div>
        <div class="pov-next">
          <div class="pov-next-title">下一步</div>
          <ol>
            <li v-for="(a, i) in actionItems.slice(0, 4)" :key="i">{{ a.text }}</li>
          </ol>
        </div>
      </div>
    </section>

    <!-- 主风险区：只展开1条最严重预警 -->
    <PatientPrimaryRisk
      v-if="primaryAlert"
      :alert="primaryAlert"
      :patient="patient"
      :sepsis="sepsisBundleStatusResolved"
      @acknowledge="acknowledgeAlert"
      @open-evidence="openEvidence"
    />

    <!-- 双栏：临床摘要 + 生命体征 -->
    <div class="overview-grid">
      <CollapseSection default-open>
      <template #title><h3 style="margin:0;font-size:15px;font-weight:600">临床摘要</h3></template>
      <template #extra><a-spin v-if="clinicalSummaryLoading" size="small" /></template>
      <div v-if="clinicalSummary" class="clinical-summary">
        <div v-if="topProblems.length" class="top-risks">
          <div v-for="(risk, idx) in topProblems" :key="idx" class="risk-item" :class="`risk-${risk.tone}`">
            <span class="risk-index">{{ Number(idx) + 1 }}</span>
            <div class="risk-body">
              <div class="risk-head">
                <span class="risk-text">{{ risk.text }}</span>
                <span v-if="risk.status" class="risk-status" :class="{ 'risk-status--open': risk.status === '待处理' }">{{ risk.status }}</span>
              </div>
              <ul v-if="risk.evidence.length" class="risk-evidence">
                <li v-for="e in risk.evidence" :key="e">{{ e }}</li>
              </ul>
              <div v-if="risk.suggestions.length" class="risk-suggest">建议：{{ risk.suggestions.join('；') }}</div>
              <div v-if="risk.reviewTime" class="risk-review">复评时间 {{ fmtShort(risk.reviewTime) }}</div>
            </div>
          </div>
        </div>
        <div v-if="worseningItems.length" class="worsening">
          <span class="worsening-label">恶化指标：</span>
          <span v-for="w in worseningItems" :key="w.key" class="worsening-item">
            {{ w.name }}<b :class="`dir-${w.direction}`">{{ w.arrow }}</b>{{ w.value }}<span class="worsening-time">{{ w.time }}</span>
          </span>
        </div>
        <div v-if="pendingTaskCount" class="worsening">
          <span class="worsening-label">待闭环：</span>
          <span>{{ pendingTaskCount }} 项（未处理预警需确认处置并设置复评）</span>
        </div>
        <p class="summary-window">统计窗口：近 {{ clinicalSummary.hours || 24 }} 小时 · {{ clinicalSummary.safety_notice || '系统辅助摘要，需床旁确认' }}</p>
      </div>
      <a-empty v-else-if="!clinicalSummaryLoading" description="暂无临床摘要" :image-style="{ height: '40px' }" />
      </CollapseSection>

      <!-- 生命体征概览条 -->
      <CollapseSection default-open>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">生命体征</h3></template>
        <template #extra><span class="section-meta">{{ vitalsSourceText }} · {{ heroMonitorUpdatedAt }}</span></template>
        <div class="vitals-grid">
          <div v-for="v in vitalCards" :key="v.label" class="vital-card" :class="`vital-${v.tone}`" :title="v.rule">
            <span class="vital-label">{{ v.label }}</span>
            <span class="vital-value">{{ v.value }}</span>
            <span v-if="v.unit" class="vital-unit">{{ v.unit }}</span>
            <span class="vital-ref">参考 {{ v.ref }}</span>
            <span v-if="v.delta" class="vital-delta" :class="`delta-${v.deltaDir}`">{{ v.delta }}</span>
          </div>
        </div>
      </CollapseSection>
    </div>

    <!-- 脓毒症集束化：结论 + 1h/3h 时窗 + 要素三态 -->
    <SepsisBundleCard v-if="sepsisBundleStatusResolved?.status !== 'none'" :status="sepsisBundleStatusResolved" class="overview-block" />

    <!-- 器官系统：异常排前 -->
    <CollapseSection default-open class="overview-block">
      <template #title><h3 style="margin:0;font-size:15px;font-weight:600">器官系统</h3></template>
      <div class="organs-grid">
        <div v-for="organ in sortedOrgans" :key="organ.key" class="organ-card">
          <div class="organ-header">
            <span class="organ-label">{{ organ.label }}</span>
            <span class="organ-status" :class="organStatusClass(organ.key)">{{ organStatusText(organ.key) }}</span>
          </div>
          <p v-if="organ.evidence || organHintEvidence(organ.key)" class="organ-evidence">{{ [organHintEvidence(organ.key), organ.evidence].filter(Boolean).join('；') }}</p>
        </div>
      </div>
      <p class="organ-source">器官状态来自近期预警与当前 MAP/乳酸/SpO₂/RR；肾、肝、凝血、神经未见预警时显示"未见异常"，不代表已完成实验室评估。</p>
    </CollapseSection>

    <!-- 生命体征趋势图 -->
    <section class="overview-section">
      <MultiVitalTrendChart
        title="生命体征趋势"
        :x-data="trendXData"
        :metrics="trendMetrics"
        :height="380"
        :loading="trendLoading"
        :explanation="trendExplanation"
        :time-ranges="trendRanges"
        default-range="24h"
        @range-change="onRangeChange"
      />
    </section>

    <!-- 24小时临床事件时间线 -->
    <section class="overview-section">
      <ClinicalTimeline
        title="24小时临床事件"
        :events="timelineEvents"
        :type-filters="eventTypeFilters"
        :loading="eventsLoading"
        empty-message="过去24小时无记录事件"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { Empty as AEmpty, Spin as ASpin } from 'ant-design-vue'
import { computed, onMounted, ref } from 'vue'
import { usePatientDetail } from '../../composables/usePatientDetail'
import PatientPrimaryRisk from './components/PatientPrimaryRisk.vue'
import SepsisBundleCard from '../../components/sepsis/SepsisBundleCard.vue'
import CollapseSection from '../../components/common/CollapseSection.vue'
import { MultiVitalTrendChart, ClinicalTimeline } from '../../components/charts'
import type { VitalMetric } from '../../components/charts'
import type { TimelineEvent } from '../../components/charts'

const {
  patient, vitals, alerts, clinicalSummary, clinicalSummaryLoading,
  sepsisBundleStatusResolved, sepsisBundleStatusText,
  patientBodyMapDetails, patientBodyMapStates, patientActionRail,
  vitalsSourceText, heroMonitorUpdatedAt, trendPoints, trendWindow, trendLoaded, loadTrend,
  acknowledgeAlert, openEvidence,
  normalizeSeverity,
} = usePatientDetail()

// 主风险：取最严重的一条预警
const primaryAlert = computed(() => {
  if (!alerts.value?.length) return null
  const severityOrder: Record<string, number> = { critical: 0, high: 1, warning: 2 }
  return [...alerts.value].sort((a: any, b: any) => {
    const sa = severityOrder[normalizeSeverity(a?.severity)] ?? 3
    const sb = severityOrder[normalizeSeverity(b?.severity)] ?? 3
    return sa - sb
  })[0] || null
})

// 生命体征卡片：当前值 + 参考范围 + 较窗口起点的变化（只给数值不给参照，床旁无法判断）
function pointMap(p: any) { return p?.ibp_map ?? p?.nibp_map ?? p?.map }
function firstInWindow(getter: (p: any) => any): number | null {
  for (const p of trendPoints.value || []) {
    const n = Number(getter(p))
    if (getter(p) !== null && getter(p) !== undefined && Number.isFinite(n)) return n
  }
  return null
}
function deltaInfo(current: any, getter: (p: any) => any, digits = 0) {
  const cur = Number(current)
  const first = firstInWindow(getter)
  if (current === null || current === undefined || !Number.isFinite(cur) || first === null) return { delta: '', deltaDir: 'flat' }
  const d = cur - first
  const txt = digits ? d.toFixed(digits) : String(Math.round(d))
  const dir = Math.abs(d) < (digits ? 0.2 : 1) ? 'flat' : d > 0 ? 'up' : 'down'
  return { delta: `较${trendWindow.value}前 ${d > 0 ? '+' : ''}${txt}`, deltaDir: dir }
}
const vitalCards = computed(() => {
  const v = vitals.value || {}
  const map = v.ibp_map ?? v.nibp_map
  return [
    { label: 'HR', value: v.hr ?? '—', unit: 'bpm', tone: hrTone(v.hr), ref: '60–100', rule: '危急 >120 或 <50；警告 >100 或 <60', ...deltaInfo(v.hr, (p) => p.hr) },
    { label: v.ibp_map != null ? 'MAP(有创)' : 'MAP(无创)', value: map ?? '—', unit: 'mmHg', tone: mapTone(map), ref: '≥65', rule: '危急 <55；警告 <65', ...deltaInfo(map, pointMap) },
    { label: 'SpO₂', value: v.spo2 ?? '—', unit: '%', tone: spo2Tone(v.spo2), ref: '≥92', rule: '危急 <88；警告 <92', ...deltaInfo(v.spo2, (p) => p.spo2) },
    { label: 'RR', value: v.rr ?? '—', unit: '/min', tone: rrTone(v.rr), ref: '12–25', rule: '危急 >35 或 <8；警告 >25 或 <12', ...deltaInfo(v.rr, (p) => p.rr) },
    { label: 'T', value: v.temp != null ? Number(v.temp).toFixed(1) : '—', unit: '°C', tone: tempTone(v.temp), ref: '36.0–38.5', rule: '危急 >39.5 或 <35；警告 >38.5 或 <36', ...deltaInfo(v.temp, (p) => p.temp, 1) },
    { label: '乳酸', value: v.lactate ?? '—', unit: 'mmol/L', tone: lactateTone(v.lactate), ref: '≤2', rule: '危急 >4；警告 >2', delta: '', deltaDir: 'flat' },
  ]
})

// ── 结论先行 ──
const TONE_RANK: Record<string, number> = { critical: 0, warning: 1 }
const abnormalVitals = computed(() => vitalCards.value
  .filter((c) => c.tone === 'critical' || c.tone === 'warning')
  .sort((a, b) => (TONE_RANK[a.tone] ?? 9) - (TONE_RANK[b.tone] ?? 9)))
const ORGAN_RANK: Record<string, number> = { 'organ-critical': 0, 'organ-warning': 1, 'organ-caution': 2, 'organ-normal': 3, 'organ-unknown': 4 }
const sortedOrgans = computed(() => [...(patientBodyMapDetails.value || [])]
  .sort((a: any, b: any) => (ORGAN_RANK[organStatusClass(a.key)] ?? 9) - (ORGAN_RANK[organStatusClass(b.key)] ?? 9)))
const abnormalOrgans = computed(() => sortedOrgans.value.filter((o: any) => ['organ-critical', 'organ-warning'].includes(organStatusClass(o.key))))
const sepsisActive = computed(() => {
  const st = String(sepsisBundleStatusResolved.value?.status || 'none').toLowerCase()
  return !['none', 'completed', 'inactive', ''].includes(st)
})
const openAlertCount = computed(() => (alerts.value || []).filter((a: any) => !a?.acknowledged && !a?.is_acknowledged && !a?.handled).length)
const briefTone = computed(() => {
  if (topProblems.value[0]?.tone === 'critical' || abnormalVitals.value.some((c) => c.tone === 'critical')) return 'critical'
  if (topProblems.value.length || abnormalVitals.value.length || sepsisActive.value || openAlertCount.value) return 'warning'
  return 'ok'
})
const briefHeadline = computed(() => {
  if (topProblems.value[0]?.text) return topProblems.value[0].text
  const crit = abnormalVitals.value.filter((c) => c.tone === 'critical')
  if (crit.length) return `${crit.length} 项体征达危急阈值：${crit.map((c) => `${c.label} ${c.value}${c.unit}`).join('，')}`
  if (abnormalVitals.value.length) return `${abnormalVitals.value.length} 项体征偏离参考范围`
  if (sepsisActive.value) return `脓毒症集束化治疗：${sepsisBundleStatusText.value}`
  return '当前体征在参考范围内，无未处理预警'
})

function fmtShort(t: any) {
  if (!t) return ''
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return String(t)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 临床摘要：主要问题 + 触发依据 + 建议（后端 top_problems；兼容旧字段 top_3_risks）
const topProblems = computed(() => {
  const cs = clinicalSummary.value || {}
  const items: any[] = Array.isArray(cs.top_problems) && cs.top_problems.length ? cs.top_problems : (cs.top_3_risks || [])
  const toneMap: Record<string, string> = { critical: 'critical', high: 'high', warning: 'warning', unknown: 'default' }
  return items.slice(0, 3).map((r: any) => ({
    text: typeof r === 'string' ? r : (r.problem || r.text || r.description || ''),
    tone: toneMap[String(r?.risk || r?.tone || r?.severity || 'warning').toLowerCase()] || 'warning',
    evidence: (Array.isArray(r?.evidence) ? r.evidence : r?.evidence ? [r.evidence] : []).map(String).slice(0, 4),
    suggestions: (Array.isArray(r?.suggestions) ? r.suggestions : r?.suggestions ? [r.suggestions] : []).map(String).slice(0, 3),
    status: r?.status || '',
    reviewTime: r?.review_time || '',
  }))
})
const worseningItems = computed(() => {
  const list = clinicalSummary.value?.worsening_indicators
  if (!Array.isArray(list)) return []
  return list.map((w: any, i: number) => {
    if (typeof w === 'string') return { key: `${i}`, name: w, arrow: '', direction: 'change', value: '', time: '' }
    const direction = w?.direction || 'change'
    const value = w?.to !== undefined && w?.to !== null ? `${w.from != null ? `${w.from}→` : ''}${w.to}${w.unit || ''}` : ''
    return { key: `${i}`, name: w?.name || '指标', arrow: direction === 'up' ? '↑' : direction === 'down' ? '↓' : '↕', direction, value, time: fmtShort(w?.time) }
  })
})
const pendingTaskCount = computed(() => (Array.isArray(clinicalSummary.value?.pending_tasks) ? clinicalSummary.value.pending_tasks.length : 0))

// 行动列表
const actionItems = computed(() => {
  if (patientActionRail?.value?.length) return patientActionRail.value
  return [{ priority: '建议', text: '暂无待办事项', tone: 'default' }]
})

// 器官状态：预警推导 + 当前体征/乳酸兜底（仅靠预警时，无预警会全部显示"正常"，与乳酸 4.2 等事实矛盾）
const LEVEL_RANK: Record<string, number> = { critical: 0, failure: 0, high: 1, impaired: 1, warning: 2, normal: 3 }
const vitalOrganHints = computed<Record<string, { level: string; evidence: string }>>(() => {
  const v = vitals.value || {}
  const out: Record<string, { level: string; evidence: string }> = {}
  const map = Number(v.ibp_map ?? v.nibp_map ?? v.map)
  const lac = Number(v.lactate)
  const spo2 = Number(v.spo2)
  const rr = Number(v.rr)
  const circ: string[] = []
  let circLevel = ''
  if (Number.isFinite(map) && (v.ibp_map ?? v.nibp_map ?? v.map) != null) {
    if (map < 55) { circLevel = 'critical'; circ.push(`MAP ${map}`) } else if (map < 65) { circLevel = circLevel || 'impaired'; circ.push(`MAP ${map}`) }
  }
  if (Number.isFinite(lac) && v.lactate != null) {
    if (lac > 4) { circLevel = 'critical'; circ.push(`乳酸 ${lac}`) } else if (lac > 2) { circLevel = circLevel || 'impaired'; circ.push(`乳酸 ${lac}`) }
  }
  if (circLevel) out.circulatory = { level: circLevel, evidence: `当前 ${circ.join('、')}` }
  const resp: string[] = []
  let respLevel = ''
  if (Number.isFinite(spo2) && v.spo2 != null) {
    if (spo2 < 88) { respLevel = 'critical'; resp.push(`SpO₂ ${spo2}%`) } else if (spo2 < 92) { respLevel = 'impaired'; resp.push(`SpO₂ ${spo2}%`) }
  }
  if (Number.isFinite(rr) && v.rr != null && (rr > 25 || rr < 8)) { respLevel = respLevel || 'impaired'; resp.push(`RR ${rr}`) }
  if (respLevel) out.respiratory = { level: respLevel, evidence: `当前 ${resp.join('、')}` }
  return out
})
function organLevel(key: string): string {
  const state = (patientBodyMapStates.value as any)?.[key]
  const alertLevel = state ? String(state.level || state || '').toLowerCase() : ''
  const hint = vitalOrganHints.value[key]?.level || ''
  if (!alertLevel) return hint
  if (!hint) return alertLevel
  return (LEVEL_RANK[hint] ?? 9) < (LEVEL_RANK[alertLevel] ?? 9) ? hint : alertLevel
}
function organHintEvidence(key: string) { return vitalOrganHints.value[key]?.evidence || '' }
function organStatusClass(key: string) {
  const level = organLevel(key)
  if (!level) return 'organ-unknown'
  if (level === 'critical' || level === 'failure') return 'organ-critical'
  if (level === 'high' || level === 'impaired') return 'organ-warning'
  if (level === 'warning') return 'organ-caution'
  return 'organ-normal'
}

function organStatusText(key: string) {
  const level = organLevel(key)
  if (!level) return '—'
  const map: Record<string, string> = { normal: '未见异常', impaired: '受损', failure: '衰竭', warning: '预警', high: '高风险', critical: '危急' }
  return map[level] || level || '—'
}

// 生命体征色调
function hrTone(v: any) { if (v == null) return 'default'; return v > 120 || v < 50 ? 'critical' : v > 100 || v < 60 ? 'warning' : 'normal' }
function mapTone(v: any) { if (v == null) return 'default'; return v < 55 ? 'critical' : v < 65 ? 'warning' : 'normal' }
function spo2Tone(v: any) { if (v == null) return 'default'; return v < 88 ? 'critical' : v < 92 ? 'warning' : 'normal' }
function rrTone(v: any) { if (v == null) return 'default'; return v > 35 || v < 8 ? 'critical' : v > 25 || v < 12 ? 'warning' : 'normal' }
function tempTone(v: any) { if (v == null) return 'default'; return v > 39.5 || v < 35 ? 'critical' : v > 38.5 || v < 36 ? 'warning' : 'normal' }
function lactateTone(v: any) { if (v == null) return 'default'; return v > 4 ? 'critical' : v > 2 ? 'warning' : 'normal' }

// ── 生命体征趋势图数据 ──
const trendLoading = ref(false)
const selectedRange = ref('24h')

const trendXData = computed(() => {
  const points = trendPoints.value
  if (!points?.length) return []
  return points.map((p: any) => {
    const t = p.time || p.timestamp
    if (!t) return ''
    const d = new Date(t)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  })
})

const trendMetrics = computed<VitalMetric[]>(() => {
  const points = trendPoints.value
  if (!points?.length) return []
  const metrics: VitalMetric[] = []
  // 保留空值以与时间轴对齐（过滤掉会导致曲线错位）
  const extract = (getter: (p: any) => any) => points.map((p: any) => {
    const n = Number(getter(p))
    return getter(p) === null || getter(p) === undefined || !Number.isFinite(n) ? null : n
  })
  const hasAny = (arr: (number | null)[]) => arr.some((x) => x !== null)
  const hrVals = extract((p) => p.hr)
  const mapVals = extract(pointMap)
  const spo2Vals = extract((p) => p.spo2)
  const rrVals = extract((p) => p.rr)
  const tempVals = extract((p) => p.temp)
  const lactateVals = extract((p) => p.lactate)
  if (hasAny(hrVals)) metrics.push({ key: 'hr', name: '心率', data: hrVals, unit: 'bpm', normalRange: [60, 100] })
  if (hasAny(mapVals)) metrics.push({ key: 'map', name: 'MAP', data: mapVals, unit: 'mmHg', normalRange: [65, 100] })
  if (hasAny(spo2Vals)) metrics.push({ key: 'spo2', name: 'SpO₂', data: spo2Vals, unit: '%', normalRange: [92, 100] })
  if (hasAny(rrVals)) metrics.push({ key: 'rr', name: '呼吸频率', data: rrVals, unit: '/min', normalRange: [12, 25] })
  if (hasAny(tempVals)) metrics.push({ key: 'temp', name: '体温', data: tempVals, unit: '°C', normalRange: [36, 38.5] })
  if (hasAny(lactateVals)) metrics.push({ key: 'lactate', name: '乳酸', data: lactateVals, unit: 'mmol/L', normalRange: [0, 2] })
  return metrics
})

const trendExplanation = computed(() => {
  if (!trendMetrics.value.length) return undefined
  const v = vitals.value || {}
  const findings: string[] = []
  if (v.hr > 120) findings.push('心率偏快')
  if (v.hr < 50) findings.push('心率偏慢')
  if ((v.ibp_map ?? v.nibp_map) < 65) findings.push('MAP偏低')
  if (v.spo2 < 92) findings.push('SpO₂偏低')
  if (v.lactate > 2) findings.push('乳酸升高')
  return {
    description: `该图显示患者过去${selectedRange.value}的生命体征趋势变化。`,
    keyFinding: findings.length ? `当前关注: ${findings.join('、')}` : undefined,
    source: '监护仪、LIS',
    dataTime: heroMonitorUpdatedAt.value,
  }
})

// 后端支持的窗口：6h/12h/24h/48h/7d
const trendRanges = [
  { label: '6h', value: '6h' },
  { label: '12h', value: '12h' },
  { label: '24h', value: '24h' },
  { label: '48h', value: '48h' },
  { label: '7天', value: '7d' },
]
async function onRangeChange(range: string) {
  if (!range || range === trendWindow.value) return
  selectedRange.value = range
  trendWindow.value = range
  trendLoading.value = true
  try { await loadTrend() } finally { trendLoading.value = false }
}
onMounted(async () => {
  selectedRange.value = trendWindow.value
  if (!trendLoaded.value) {
    trendLoading.value = true
    try { await loadTrend() } finally { trendLoading.value = false }
  }
})

// ── 24小时临床事件时间线 ──
const eventsLoading = ref(false)

const timelineEvents = computed<TimelineEvent[]>(() => {
  // 从告警和临床数据中提取事件
  const events: TimelineEvent[] = []
  const alertList = alerts.value || []
  const since = Date.now() - 24 * 3600 * 1000
  alertList.forEach((a: any) => {
    const t = new Date(a.created_at || a.time).getTime()
    if (Number.isFinite(t) && t < since) return
    events.push({
      id: a._id || a.id,
      time: a.created_at || a.time,
      type: '告警',
      title: a.name || a.rule_id || '告警',
      description: a.description || [a.parameter, a.value !== undefined && a.value !== null ? `当时值 ${a.value}` : '', a.condition ? `条件 ${typeof a.condition === 'object' ? JSON.stringify(a.condition) : a.condition}` : ''].filter(Boolean).join(' · '),
      source: '规则引擎',
      severity: normalizeSeverity(a.severity) === 'high' ? 'warning' : normalizeSeverity(a.severity) as 'critical' | 'warning' | 'info' | 'normal',
    })
  })
  // 按时间排序
  return events.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime()).slice(0, 20)
})

// 目前时间线只接入了告警事件，不展示无数据的用药/操作/检验筛选项
const eventTypeFilters = [
  { label: '告警', value: '告警' },
]
</script>

<style scoped>
.overview-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 2-column grid */
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.overview-grid > .overview-section {
  margin: 0;
}

/* Narrow sections (left-aligned, max-width) */
.overview-section--narrow {
  max-width: 640px;
}

@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
  .overview-section--narrow {
    max-width: 100%;
  }
}

.overview-section {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: var(--text-section-title);
  font-weight: 600;
  color: var(--color-text-primary);
}

.section-meta {
  font-size: var(--text-label);
  color: var(--color-text-tertiary);
}

/* Vitals grid */
.vitals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(84px, 1fr));
  gap: 10px;
}

.vital-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 8px;
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
  border: 1px solid var(--color-divider);
}

.vital-label {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  font-weight: 500;
  text-transform: uppercase;
}

.vital-value {
  font-size: var(--text-metric-normal);
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.2;
}

.vital-unit {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
}

.vital-critical .vital-value { color: var(--color-danger); }
.vital-warning .vital-value { color: var(--color-warning); }
.vital-normal .vital-value { color: var(--color-normal); }

/* Clinical summary */
.top-risks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.risk-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
  border-left: 3px solid var(--color-border-strong);
}

.risk-critical { border-left-color: var(--color-danger); background: var(--color-critical-bg); }
.risk-high { border-left-color: var(--color-high-risk); background: var(--color-high-risk-bg); }
.risk-warning, .risk-warn { border-left-color: var(--color-warning); background: var(--color-warning-soft-bg); }

.risk-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-border-strong);
  color: var(--color-text-inverse);
  font-size: var(--text-label);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.risk-critical .risk-index { background: var(--color-danger); }
.risk-high .risk-index { background: var(--color-high-risk); }
.risk-warning .risk-index, .risk-warn .risk-index { background: var(--color-warning); }

.risk-text {
  font-size: var(--text-body);
  color: var(--color-text-primary);
  line-height: 1.5;
}

.worsening {
  margin-top: 8px;
  font-size: var(--text-label);
  color: var(--color-text-tertiary);
}

.worsening-label {
  font-weight: 600;
  color: var(--color-text-secondary);
}

/* Bundle */
.bundle-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bundle-conclusion {
  margin: 0;
  font-size: var(--text-body);
  color: var(--color-text-primary);
}

.bundle-meta {
  display: flex;
  gap: 16px;
  font-size: var(--text-label);
  color: var(--color-text-tertiary);
}

/* Organs grid */
.organs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.organ-card {
  padding: 10px 12px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
}

.organ-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.organ-label {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-text-primary);
}

.organ-status {
  font-size: var(--text-caption);
  padding: 1px 6px;
  border-radius: var(--radius-tag);
  font-weight: 500;
}

.organ-normal { background: var(--color-normal-bg); color: var(--color-normal); }
.organ-caution { background: var(--color-warning-soft-bg); color: var(--color-warning); }
.organ-warning { background: var(--color-high-risk-bg); color: var(--color-high-risk); }
.organ-critical { background: var(--color-critical-bg); color: var(--color-danger); }
.organ-unknown { background: var(--color-bg-surface-secondary); color: var(--color-text-tertiary); }

.organ-evidence {
  margin: 0;
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  line-height: 1.4;
}

/* Actions */
.actions-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.action-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
}

.action-priority {
  flex-shrink: 0;
  font-size: var(--text-caption);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-tag);
}

.priority-critical { background: var(--color-critical-bg); color: var(--color-danger); }
.priority-high { background: var(--color-high-risk-bg); color: var(--color-high-risk); }
.priority-default { background: var(--color-primary-bg); color: var(--color-primary); }

.action-text {
  font-size: var(--text-body);
  color: var(--color-text-primary);
}

.risk-body { flex: 1; min-width: 0; }
.risk-head { display: flex; align-items: center; gap: 8px; }
.risk-status { font-size: 11px; padding: 0 6px; border-radius: 4px; background: var(--color-bg-inset); color: var(--color-text-secondary); }
.risk-status--open { background: var(--color-critical-bg); color: var(--color-danger); }
.risk-evidence { margin: 4px 0 0; padding-left: 16px; font-size: 12px; color: var(--color-text-secondary); line-height: 1.6; }
.risk-suggest { margin-top: 2px; font-size: 12px; color: var(--color-text-primary); }
.risk-review { margin-top: 2px; font-size: 11px; color: var(--color-text-tertiary); }
.worsening-item { margin-right: 10px; }
.worsening-item b { margin: 0 2px; }
.dir-up { color: var(--color-danger); }
.dir-down { color: var(--color-primary); }
.worsening-time { margin-left: 4px; font-size: 11px; color: var(--color-text-tertiary); }
.summary-window { margin: 8px 0 0; font-size: 11px; color: var(--color-text-tertiary); }
.vital-ref { font-size: 11px; color: var(--color-text-tertiary); }
.vital-delta { font-size: 11px; color: var(--color-text-secondary); }
.delta-up { color: var(--color-warning); }
.delta-down { color: var(--color-primary); }

/* 结论先行卡片（公司蓝白卡片样式） */
.pov-brief { background: #fff; border: 1px solid #E6E5E3; border-radius: 10px; overflow: hidden; margin-bottom: 12px; }
.pov-brief-head { height: 38px; background: #5392FF; color: #fff; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; }
.pov-brief-title { font-size: 15px; font-weight: 600; }
.pov-brief-meta { font-size: 12px; opacity: .9; }
.pov-brief-body { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 16px; padding: 14px 16px; }
@media (max-width: 900px) { .pov-brief-body { grid-template-columns: 1fr; } }
.pov-headline { font-size: 18px; font-weight: 700; line-height: 1.45; color: #1F2329; }
.pov-headline--critical { color: #B91C1C; }
.pov-headline--warning { color: #B45309; }
.pov-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.pov-chip { font-size: 12px; padding: 2px 8px; border-radius: 4px; border: 1px solid; font-weight: 500; }
.pov-chip.crit { background: #FEF2F2; color: #B91C1C; border-color: #FCA5A5; }
.pov-chip.warn { background: #FFFBEB; color: #B45309; border-color: #FCD34D; }
.pov-chip.ok { background: #E7F5EE; color: #2F7D55; border-color: #A7D9BF; }
.pov-next { background: #F7F8FA; border-radius: 8px; padding: 10px 12px; }
.pov-next-title { font-size: 13px; font-weight: 600; color: #5392FF; margin-bottom: 4px; }
.pov-next ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.6; color: #1F2329; }
.overview-view :deep(.collapse-section) { border-color: #E6E5E3; border-radius: 10px; }
.overview-view :deep(.collapse-header h3) { border-left: 3px solid #5392FF; padding-left: 8px; }
.organ-card:has(.organ-critical) { background: #FEF2F2; border-color: #FCA5A5; }
.organ-card:has(.organ-warning) { background: #FFFBEB; border-color: #FCD34D; }
.overview-block { margin-bottom: 12px; }
.organ-source { margin: 8px 0 0; font-size: 12px; color: #8F959E; }
</style>






