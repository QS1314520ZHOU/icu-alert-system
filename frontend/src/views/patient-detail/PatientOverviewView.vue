<template>
  <div class="overview-view">
    <!-- 主风险区：只展开1条最严重预警 -->
    <PatientPrimaryRisk
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
        <div v-if="topRisks.length" class="top-risks">
          <div v-for="(risk, idx) in topRisks" :key="idx" class="risk-item" :class="`risk-${risk.tone || 'warn'}`">
            <span class="risk-index">{{ Number(idx) + 1 }}</span>
            <span class="risk-text">{{ risk.text }}</span>
          </div>
        </div>
        <div v-if="clinicalSummary.worsening_indicators?.length" class="worsening">
          <span class="worsening-label">恶化指标：</span>
          <span>{{ clinicalSummary.worsening_indicators.join('、') }}</span>
        </div>
      </div>
      <a-empty v-else-if="!clinicalSummaryLoading" description="暂无临床摘要" :image-style="{ height: '40px' }" />
      </CollapseSection>

      <!-- 生命体征概览条 -->
      <CollapseSection default-open>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">生命体征</h3></template>
        <template #extra><span class="section-meta">{{ vitalsSourceText }} · {{ heroMonitorUpdatedAt }}</span></template>
        <div class="vitals-grid">
          <div v-for="v in vitalCards" :key="v.label" class="vital-card" :class="`vital-${v.tone}`">
            <span class="vital-label">{{ v.label }}</span>
            <span class="vital-value">{{ v.value }}</span>
            <span v-if="v.unit" class="vital-unit">{{ v.unit }}</span>
          </div>
        </div>
      </CollapseSection>
    </div>

    <!-- 双栏：脓毒症Bundle + 器官系统 -->
    <div class="overview-grid" v-if="sepsisBundleStatusResolved?.status !== 'none'">
      <CollapseSection default-open>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">脓毒症 Bundle</h3></template>
        <template #extra><a-tag :color="bundleLightColor">{{ sepsisBundleStatusText }}</a-tag></template>
        <div class="bundle-summary">
          <p class="bundle-conclusion">{{ sepsisBundleConclusion }}</p>
          <div class="bundle-meta">
            <span v-if="sepsisBundleTimelineText">{{ sepsisBundleTimelineText }}</span>
            <span v-if="sepsisBundleExtraText">{{ sepsisBundleExtraText }}</span>
            <span v-if="sepsisBundleComplianceSummary">{{ sepsisBundleComplianceSummary }}</span>
          </div>
        </div>
      </CollapseSection>
      <CollapseSection default-open>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">器官系统</h3></template>
        <div class="organs-grid">
          <div v-for="organ in patientBodyMapDetails" :key="organ.key" class="organ-card">
            <div class="organ-header">
              <span class="organ-label">{{ organ.label }}</span>
              <span class="organ-status" :class="organStatusClass(organ.key)">{{ organStatusText(organ.key) }}</span>
            </div>
            <p v-if="organ.evidence" class="organ-evidence">{{ organ.evidence }}</p>
          </div>
        </div>
      </CollapseSection>
    </div>

    <!-- 器官系统 (无脓毒症时单独展示) -->
    <section v-if="sepsisBundleStatusResolved?.status === 'none'" class="overview-section">
      <div class="section-header"><h3>器官系统</h3></div>
      <div class="organs-grid">
        <div v-for="organ in patientBodyMapDetails" :key="organ.key" class="organ-card">
          <div class="organ-header">
            <span class="organ-label">{{ organ.label }}</span>
            <span class="organ-status" :class="organStatusClass(organ.key)">{{ organStatusText(organ.key) }}</span>
          </div>
          <p v-if="organ.evidence" class="organ-evidence">{{ organ.evidence }}</p>
        </div>
      </div>
    </section>

    <!-- 下一步行动 (半宽) -->
    <section class="overview-section overview-section--narrow">
      <div class="section-header"><h3>下一步行动</h3></div>
      <div class="actions-list">
        <div v-for="(action, idx) in actionItems" :key="idx" class="action-item">
          <span class="action-priority" :class="`priority-${action.tone || 'default'}`">{{ action.priority || '建议' }}</span>
          <span class="action-text">{{ action.text }}</span>
        </div>
      </div>
    </section>

    <!-- 生命体征趋势图 -->
    <section class="overview-section">
      <MultiVitalTrendChart
        title="生命体征趋势"
        :x-data="trendXData"
        :metrics="trendMetrics"
        :height="380"
        :loading="trendLoading"
        :explanation="trendExplanation"
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
import { computed, ref } from 'vue'
import { usePatientDetail } from '../../composables/usePatientDetail'
import PatientPrimaryRisk from './components/PatientPrimaryRisk.vue'
import CollapseSection from '../../components/common/CollapseSection.vue'
import { MultiVitalTrendChart, ClinicalTimeline } from '../../components/charts'
import type { VitalMetric } from '../../components/charts'
import type { TimelineEvent } from '../../components/charts'

const {
  patient, vitals, alerts, clinicalSummary, clinicalSummaryLoading,
  sepsisBundleStatusResolved, sepsisBundleStatusText, sepsisBundleConclusion,
  sepsisBundleTimelineText, sepsisBundleExtraText, sepsisBundleComplianceSummary,
  patientBodyMapDetails, patientBodyMapStates, patientActionRail,
  vitalsSourceText, heroMonitorUpdatedAt, trendPoints,
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

// 生命体征卡片
const vitalCards = computed(() => {
  const v = vitals.value || {}
  return [
    { label: 'HR', value: v.hr ?? '—', unit: 'bpm', tone: hrTone(v.hr) },
    { label: 'MAP', value: v.ibp_map ?? v.nibp_map ?? '—', unit: 'mmHg', tone: mapTone(v.ibp_map ?? v.nibp_map) },
    { label: 'SpO₂', value: v.spo2 ?? '—', unit: '%', tone: spo2Tone(v.spo2) },
    { label: 'RR', value: v.rr ?? '—', unit: '/min', tone: rrTone(v.rr) },
    { label: 'T', value: v.temp != null ? Number(v.temp).toFixed(1) : '—', unit: '°C', tone: tempTone(v.temp) },
    { label: '乳酸', value: v.lactate ?? '—', unit: 'mmol/L', tone: lactateTone(v.lactate) },
  ]
})

// 临床摘要：最危险的3件事
const topRisks = computed(() => {
  const items = clinicalSummary.value?.top_3_risks || []
  return items.map((r: any) => ({
    text: r.text || r.description || String(r),
    tone: r.tone || r.severity || 'warn',
  }))
})

// 行动列表
const actionItems = computed(() => {
  if (patientActionRail?.value?.length) return patientActionRail.value
  return [{ priority: '建议', text: '暂无待办事项', tone: 'default' }]
})

// 脓毒症灯光颜色
const bundleLightColor = computed(() => {
  const map: Record<string, string> = { green: 'success', blue: 'processing', yellow: 'warning', orange: 'warning', red: 'error', gray: 'default' }
  return map[sepsisBundleStatusResolved.value?.light] || 'default'
})

// 器官状态
function organStatusClass(key: string) {
  const state = (patientBodyMapStates.value as any)?.[key]
  if (!state) return 'organ-unknown'
  const level = String(state.level || state || '').toLowerCase()
  if (level === 'critical' || level === 'failure') return 'organ-critical'
  if (level === 'high' || level === 'impaired') return 'organ-warning'
  if (level === 'warning') return 'organ-caution'
  return 'organ-normal'
}

function organStatusText(key: string) {
  const state = (patientBodyMapStates.value as any)?.[key]
  if (!state) return '—'
  const level = String(state.level || state || '').toLowerCase()
  const map: Record<string, string> = { normal: '正常', impaired: '受损', failure: '衰竭', warning: '预警', high: '高风险', critical: '危急' }
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
  const extractValues = (key: string) => points.map((p: any) => p[key]).filter((v: any) => v != null)
  const hrVals = extractValues('hr')
  const mapVals = extractValues('map')
  const spo2Vals = extractValues('spo2')
  const rrVals = extractValues('rr')
  const tempVals = extractValues('temp')
  const lactateVals = extractValues('lactate')
  if (hrVals.length) metrics.push({ key: 'hr', name: '心率', data: hrVals, unit: 'bpm', normalRange: [60, 100] })
  if (mapVals.length) metrics.push({ key: 'map', name: 'MAP', data: mapVals, unit: 'mmHg', normalRange: [65, 100] })
  if (spo2Vals.length) metrics.push({ key: 'spo2', name: 'SpO₂', data: spo2Vals, unit: '%', normalRange: [95, 100] })
  if (rrVals.length) metrics.push({ key: 'rr', name: '呼吸频率', data: rrVals, unit: '/min', normalRange: [12, 20] })
  if (tempVals.length) metrics.push({ key: 'temp', name: '体温', data: tempVals, unit: '°C', normalRange: [36, 37.5] })
  if (lactateVals.length) metrics.push({ key: 'lactate', name: '乳酸', data: lactateVals, unit: 'mmol/L', normalRange: [0, 2] })
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

function onRangeChange(range: string) {
  selectedRange.value = range
  // TODO: 重新加载对应时间范围的趋势数据
}

// ── 24小时临床事件时间线 ──
const eventsLoading = ref(false)

const timelineEvents = computed<TimelineEvent[]>(() => {
  // 从告警和临床数据中提取事件
  const events: TimelineEvent[] = []
  const alertList = alerts.value || []
  alertList.forEach((a: any) => {
    events.push({
      id: a._id || a.id,
      time: a.created_at || a.time,
      type: '告警',
      title: a.name || a.rule_id || '告警',
      description: a.description,
      source: '规则引擎',
      severity: normalizeSeverity(a.severity) === 'high' ? 'warning' : normalizeSeverity(a.severity) as 'critical' | 'warning' | 'info' | 'normal',
    })
  })
  // 按时间排序
  return events.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime()).slice(0, 20)
})

const eventTypeFilters = [
  { label: '告警', value: '告警' },
  { label: '用药', value: '用药' },
  { label: '操作', value: '操作' },
  { label: '检验', value: '检验' },
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
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
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
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.section-meta {
  font-size: 12px;
  color: #999;
}

/* Vitals grid */
.vitals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.vital-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 8px;
  border-radius: 6px;
  background: #fafbfc;
  border: 1px solid #f0f0f0;
}

.vital-label {
  font-size: 11px;
  color: #999;
  font-weight: 500;
  text-transform: uppercase;
}

.vital-value {
  font-size: 22px;
  font-weight: 700;
  color: #1a1a1a;
  line-height: 1.2;
}

.vital-unit {
  font-size: 11px;
  color: #999;
}

.vital-critical .vital-value { color: #ff4d4f; }
.vital-warning .vital-value { color: #faad14; }
.vital-normal .vital-value { color: #52c41a; }

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
  border-radius: 6px;
  background: #fafafa;
  border-left: 3px solid #d9d9d9;
}

.risk-critical { border-left-color: #ff4d4f; background: #fff1f0; }
.risk-high { border-left-color: #fa8c16; background: #fff7e6; }
.risk-warning, .risk-warn { border-left-color: #faad14; background: #fffbe6; }

.risk-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #d9d9d9;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.risk-critical .risk-index { background: #ff4d4f; }
.risk-high .risk-index { background: #fa8c16; }
.risk-warning .risk-index, .risk-warn .risk-index { background: #faad14; }

.risk-text {
  font-size: 13px;
  color: #333;
  line-height: 1.5;
}

.worsening {
  margin-top: 8px;
  font-size: 12px;
  color: #999;
}

.worsening-label {
  font-weight: 600;
  color: #666;
}

/* Bundle */
.bundle-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bundle-conclusion {
  margin: 0;
  font-size: 13px;
  color: #333;
}

.bundle-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #999;
}

/* Organs grid */
.organs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.organ-card {
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafbfc;
}

.organ-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.organ-label {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.organ-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.organ-normal { background: #f6ffed; color: #52c41a; }
.organ-caution { background: #fffbe6; color: #faad14; }
.organ-warning { background: #fff7e6; color: #fa8c16; }
.organ-critical { background: #fff1f0; color: #ff4d4f; }
.organ-unknown { background: #f5f5f5; color: #999; }

.organ-evidence {
  margin: 0;
  font-size: 11px;
  color: #999;
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
  border-radius: 6px;
  background: #fafafa;
}

.action-priority {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.priority-critical { background: #fff1f0; color: #ff4d4f; }
.priority-high { background: #fff7e6; color: #fa8c16; }
.priority-default { background: #f0f7ff; color: #1890ff; }

.action-text {
  font-size: 13px;
  color: #333;
}
</style>






