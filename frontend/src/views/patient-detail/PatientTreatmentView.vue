<template>
  <div class="treatment-view">
    <CollapseSection default-open>
      <template #title><h3 style="margin:0;font-size:15px;font-weight:600">脓毒症 Bundle</h3></template>
      <template #extra>
        <div class="bundle-actions">
          <a-button size="small" @click="loadSepsisBundleStatus">刷新</a-button>
          <a-button v-if="sepsisBundleHasReviewPending" size="small" type="primary" @click="openSepsisBundleReviewDialog">审核要素</a-button>
          <a-button size="small" @click="openSepsisBundleExecutionDialog">记录执行</a-button>
        </div>
      </template>
      <div v-if="sepsisBundleStatusResolved" class="bundle-detail">
        <div class="bundle-status-row">
          <a-tag :color="bundleLightColor">{{ sepsisBundleStatusText }}</a-tag>
          <span class="bundle-conclusion">{{ sepsisBundleConclusion }}</span>
        </div>
        <div class="bundle-meta">
          <span v-if="sepsisBundleTimelineText">{{ sepsisBundleTimelineText }}</span>
          <span v-if="sepsisBundleExtraText">{{ sepsisBundleExtraText }}</span>
          <span v-if="sepsisBundleComplianceSummary">{{ sepsisBundleComplianceSummary }}</span>
        </div>
        <div v-if="sepsisBundleV2Info" class="bundle-v2-info">
          <a-tag color="blue">Bundle v2</a-tag>
          <span>感染判定：{{ sepsisInfectionVerdictText }}</span>
        </div>
      </div>
      <a-empty v-else description="暂无脓毒症Bundle数据" :image-style="{ height: '40px' }" />
    </CollapseSection>
    <div class="treatment-grid">
      <CollapseSection default-open>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">脱机评估</h3></template>
        <template #extra><a-button size="small" @click="loadWeaningStatus">刷新</a-button></template>
        <div v-if="weaningStatus" class="weaning-detail">
          <div class="weaning-risk">
            <span class="risk-label">风险等级：</span>
            <a-tag :color="weaningRiskTone === 'danger' ? 'error' : weaningRiskTone === 'warn' ? 'warning' : 'success'">{{ weaningRiskLabel }}</a-tag>
          </div>
          <p class="weaning-recommendation">{{ weaningRecommendationText }}</p>
          <div v-if="weaningTopEvidence.length" class="weaning-evidence">
            <span class="evidence-label">依据：</span>
            <ul><li v-for="(e, idx) in weaningTopEvidence" :key="idx">{{ e }}</li></ul>
          </div>
        </div>
        <a-empty v-else description="暂无脱机评估数据" :image-style="{ height: '40px' }" />
      </CollapseSection>
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">自主呼吸试验 (SBT)</h3></template>
        <template #extra><a-button size="small" @click="loadSbtTimeline(true)" :loading="sbtTimelineLoading">刷新</a-button></template>
        <div v-if="sbtTimelineLoading" class="loading-placeholder"><a-spin /></div>
        <div v-else-if="sbtTimelineRecords.length" class="sbt-timeline">
          <div v-for="record in sbtTimelineRecords" :key="record.id || record.time" class="sbt-record">
            <div class="sbt-time">{{ fmtTime(record.time) }}</div>
            <div class="sbt-content">
              <span class="sbt-type">{{ record.type || record.test_type || 'SBT' }}</span>
              <span class="sbt-result" :class="sbtResultClass(record)">{{ sbtResultText(record) }}</span>
              <span v-if="record.duration_minutes" class="sbt-duration">{{ record.duration_minutes }}分钟</span>
            </div>
            <p v-if="record.notes || record.comment" class="sbt-notes">{{ record.notes || record.comment }}</p>
          </div>
        </div>
        <a-empty v-else-if="sbtTimelineLoaded" description="暂无SBT记录" :image-style="{ height: '40px' }" />
      </CollapseSection>
    </div>
    <div class="treatment-grid">
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">eCASH 解放束</h3></template>
        <template #extra><a-tag v-if="ecashAlerts.length" :color="liberationBundleColor">{{ liberationBundleStatus }}</a-tag></template>
        <div v-if="ecashAlerts.length" class="liberation-list">
          <div v-for="alert in ecashAlerts" :key="alert._id || alert.id" class="liberation-item" :class="'severity-' + normalizeSeverity(alert.severity)">
            <div class="liberation-header">
              <span class="liberation-title">{{ alertTypeText(alert.alert_type) }}</span>
              <a-tag :color="severityColor(alert.severity)" size="small">{{ severityLabel(alert.severity) }}</a-tag>
            </div>
            <p class="liberation-desc">{{ alert.description || alert.summary || '' }}</p>
            <div v-if="alert.value || alert.unit" class="liberation-value">数值：{{ alert.value }}{{ alert.unit ? ' ' + alert.unit : '' }}</div>
          </div>
        </div>
        <a-empty v-else description="暂无eCASH解放束数据" :image-style="{ height: '40px' }" />
      </CollapseSection>
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">早期活动 (ICU-AW)</h3></template>
        <template #extra><a-tag v-if="mobilityAlerts.length" :color="mobilityRiskColor">{{ mobilityRiskText }}</a-tag></template>
        <div v-if="mobilityAlerts.length" class="mobility-list">
          <div v-for="alert in mobilityAlerts" :key="alert._id || alert.id" class="mobility-item">
            <div class="mobility-header">
              <span class="mobility-title">{{ alertTypeText(alert.alert_type) }}</span>
              <a-tag :color="severityColor(alert.severity)" size="small">{{ severityLabel(alert.severity) }}</a-tag>
            </div>
            <p class="mobility-desc">{{ alert.description || alert.summary || '' }}</p>
          </div>
        </div>
        <a-empty v-else description="暂无早期活动数据" :image-style="{ height: '40px' }" />
      </CollapseSection>
    </div>
    <div class="treatment-grid">
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">营养监测</h3></template>
        <template #extra><a-tag v-if="nutritionAlerts.length" :color="nutritionStatusColor">{{ nutritionStatusText }}</a-tag></template>
        <div v-if="nutritionAlerts.length" class="nutrition-list">
          <div v-for="alert in nutritionAlerts" :key="alert._id || alert.id" class="nutrition-item">
            <div class="nutrition-header">
              <span class="nutrition-title">{{ alertTypeText(alert.alert_type) }}</span>
              <a-tag :color="severityColor(alert.severity)" size="small">{{ severityLabel(alert.severity) }}</a-tag>
            </div>
            <p class="nutrition-desc">{{ alert.description || alert.summary || '' }}</p>
            <div v-if="alert.value" class="nutrition-value">数值：{{ alert.value }}{{ alert.unit ? ' ' + alert.unit : '' }}</div>
          </div>
        </div>
        <a-empty v-else description="暂无营养监测数据" :image-style="{ height: '40px' }" />
      </CollapseSection>
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">出入量平衡</h3></template>
        <div v-if="fluidBalanceSummary" class="fluid-balance">
          <div class="fluid-stats">
            <div class="fluid-stat net" :class="fluidNetClass">
              <span class="stat-label">24h净平衡</span>
              <span class="stat-value">{{ fluidBalanceSummary.net24h }} ml</span>
            </div>
          </div>
        </div>
        <a-empty v-else description="暂无出入量数据" :image-style="{ height: '40px' }" />
      </CollapseSection>
    </div>
    <div class="treatment-grid">
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">用药记录</h3></template>
        <template #extra><a-button size="small" @click="loadDrugs" :loading="!drugsLoaded && drugs.length === 0">刷新</a-button></template>
        <a-table v-if="drugs.length" :columns="drugColumns" :data-source="drugTableRows" :pagination="{ pageSize: 10 }" size="small" row-key="drugId" />
        <a-empty v-else-if="drugsLoaded" description="暂无用药记录" :image-style="{ height: '40px' }" />
      </CollapseSection>
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">护理评估</h3></template>
        <template #extra><a-button size="small" @click="loadAssessments" :loading="!assessmentsLoaded && assessments.length === 0">刷新</a-button></template>
        <a-table v-if="assessments.length" :columns="assessmentColumns" :data-source="assessmentTableRows" :pagination="{ pageSize: 10 }" size="small" row-key="assessmentId" />
        <a-empty v-else-if="assessmentsLoaded" description="暂无护理评估" :image-style="{ height: '40px' }" />
      </CollapseSection>
    </div>
    <CollapseSection>
      <template #title><h3 style="margin:0;font-size:15px;font-weight:600">长期随访 (PICS)</h3></template>
      <Suspense>
        <LongTermFollowupTab :patient-id="patientId" :patient="patient" />
        <template #fallback><div class="loading-placeholder"><a-spin /></div></template>
      </Suspense>
    </CollapseSection>
  </div>
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import CollapseSection from '../../components/common/CollapseSection.vue'
import { usePatientDetail } from '../../composables/usePatientDetail'

const LongTermFollowupTab = defineAsyncComponent(() => import('../../components/patient-detail/LongTermFollowupTab.vue'))

const {
  patient, route,
  sepsisBundleStatusResolved, sepsisBundleStatusText, sepsisBundleConclusion,
  sepsisBundleTimelineText, sepsisBundleExtraText, sepsisBundleComplianceSummary,
  sepsisBundleV2Info, sepsisInfectionVerdictText, sepsisBundleHasReviewPending,
  loadSepsisBundleStatus, openSepsisBundleReviewDialog, openSepsisBundleExecutionDialog,
  weaningStatus, weaningRiskTone, weaningRiskLabel, weaningRecommendationText,
  weaningTopEvidence, loadWeaningStatus,
  sbtTimelineRecords, sbtTimelineLoading, sbtTimelineLoaded,
  loadSbtTimeline,
  drugs, drugsLoaded, drugColumns, drugTableRows, loadDrugs,
  assessments, assessmentsLoaded, assessmentColumns, assessmentTableRows, loadAssessments,
  ecashAlerts, mobilityAlerts, bedcard, alerts,
  fmtTime, alertTypeText, normalizeSeverity,
} = usePatientDetail()

const patientId = computed(() => String(route.params.patientId || route.params.id || ''))

// ---- 出入量 ----
const fluidBalanceSummary = computed(() => {
  const net = bedcard.value?.metrics?.netFluid24h
  if (net == null) return null
  return { net24h: net }
})

const fluidNetClass = computed(() => {
  const net = fluidBalanceSummary.value?.net24h
  if (net == null) return ''
  if (net > 500) return 'net-positive-warn'
  if (net > 0) return 'net-positive'
  if (net < -500) return 'net-negative-warn'
  return 'net-negative'
})

// ---- eCASH解放束 ----
const liberationBundleColor = computed(() => {
  if (!ecashAlerts.value.length) return 'default'
  const hasSevere = ecashAlerts.value.some((a: any) => normalizeSeverity(a?.severity) === 'critical' || normalizeSeverity(a?.severity) === 'high')
  if (hasSevere) return 'error'
  if (ecashAlerts.value.length > 0) return 'warning'
  return 'success'
})

const liberationBundleStatus = computed(() => {
  const count = ecashAlerts.value.length
  if (!count) return '无数据'
  const severe = ecashAlerts.value.filter((a: any) => normalizeSeverity(a?.severity) === 'critical' || normalizeSeverity(a?.severity) === 'high').length
  if (severe > 0) return `${severe}项需关注`
  return `${count}项评估`
})

// ---- 早期活动 ----
const mobilityRiskColor = computed(() => {
  if (!mobilityAlerts.value.length) return 'default'
  const hasSevere = mobilityAlerts.value.some((a: any) => normalizeSeverity(a?.severity) === 'critical' || normalizeSeverity(a?.severity) === 'high')
  if (hasSevere) return 'error'
  return 'warning'
})

const mobilityRiskText = computed(() => {
  const count = mobilityAlerts.value.length
  if (!count) return '无风险'
  const severe = mobilityAlerts.value.filter((a: any) => normalizeSeverity(a?.severity) === 'critical' || normalizeSeverity(a?.severity) === 'high').length
  if (severe > 0) return `${severe}项高风险`
  return `${count}项评估`
})

// ---- 营养监测 ----
const nutritionAlertTypes = new Set(['nutrition_start_delay', 'nutrition_calorie_not_reached', 'nutrition_feeding_intolerance', 'nutrition_refeeding_risk', 'nutrition_monitor'])
const nutritionAlerts = computed(() =>
  alerts.value.filter((a: any) => nutritionAlertTypes.has(String(a?.alert_type || '')))
)

const nutritionStatusColor = computed(() => {
  if (!nutritionAlerts.value.length) return 'default'
  const hasSevere = nutritionAlerts.value.some((a: any) => normalizeSeverity(a?.severity) === 'critical' || normalizeSeverity(a?.severity) === 'high')
  if (hasSevere) return 'error'
  return 'warning'
})

const nutritionStatusText = computed(() => {
  const count = nutritionAlerts.value.length
  if (!count) return '正常'
  const severe = nutritionAlerts.value.filter((a: any) => normalizeSeverity(a?.severity) === 'critical' || normalizeSeverity(a?.severity) === 'high').length
  if (severe > 0) return `${severe}项异常`
  return `${count}项监测`
})

// ---- 通用 ----
function severityColor(severity: string): string {
  const s = normalizeSeverity(severity)
  const map: Record<string, string> = { critical: 'red', high: 'orange', medium: 'gold', low: 'green', info: 'blue' }
  return map[s] || 'default'
}

function severityLabel(severity: string): string {
  const s = normalizeSeverity(severity)
  const map: Record<string, string> = { critical: '危急', high: '高', medium: '中', low: '低', info: '信息' }
  return map[s] || severity
}

const bundleLightColor = computed(() => {
  const map: Record<string, string> = { green: 'success', blue: 'processing', yellow: 'warning', orange: 'warning', red: 'error', gray: 'default' }
  return map[sepsisBundleStatusResolved.value?.light] || 'default'
})

function sbtResultClass(record: any) {
  const result = String(record?.result || record?.status || '').toLowerCase()
  if (result === 'pass' || result === 'success' || result === '通过') return 'sbt-pass'
  if (result === 'fail' || result === 'failure' || result === '未通过') return 'sbt-fail'
  return ''
}

function sbtResultText(record: any) {
  const result = String(record?.result || record?.status || '')
  const map: Record<string, string> = { pass: '通过', success: '通过', fail: '未通过', failure: '未通过', pending: '进行中' }
  return map[result.toLowerCase()] || result || '—'
}
</script>

<style scoped>
.treatment-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.treatment-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.treatment-grid > .treatment-section {
  margin: 0;
}

@media (max-width: 900px) {
  .treatment-grid {
    grid-template-columns: 1fr;
  }
}

.treatment-section {
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

.bundle-actions {
  display: flex;
  gap: 8px;
}

.bundle-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bundle-status-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bundle-conclusion {
  font-size: 13px;
  color: #333;
  margin: 0;
}

.bundle-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #999;
}

.bundle-v2-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
}

/* Weaning */
.weaning-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.weaning-risk {
  display: flex;
  align-items: center;
  gap: 8px;
}

.risk-label {
  font-size: 13px;
  color: #666;
}

.weaning-recommendation {
  margin: 0;
  font-size: 13px;
  color: #333;
  line-height: 1.6;
}

.weaning-evidence {
  font-size: 12px;
  color: #666;
}

.evidence-label {
  font-weight: 600;
}

.weaning-evidence ul {
  margin: 4px 0 0 16px;
  padding: 0;
}

.weaning-evidence li {
  margin-bottom: 2px;
}

/* SBT Timeline */
.loading-placeholder {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

.sbt-timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sbt-record {
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafbfc;
}

.sbt-time {
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
}

.sbt-content {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sbt-type {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.sbt-result {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #f5f5f5;
  color: #666;
}

.sbt-pass { background: #f6ffed; color: #52c41a; }
.sbt-fail { background: #fff1f0; color: #ff4d4f; }

.sbt-duration {
  font-size: 12px;
  color: #999;
}

.sbt-notes {
  margin: 6px 0 0;
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}

/* Fluid balance */
.fluid-balance {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fluid-stats {
  display: flex;
  gap: 16px;
}

.fluid-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  border-radius: 6px;
  background: #f5f5f5;
}

.fluid-stat .stat-label {
  font-size: 12px;
  color: #999;
}

.fluid-stat .stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.fluid-stat.net-positive-warn { background: #fff1f0; }
.fluid-stat.net-positive-warn .stat-value { color: #ff4d4f; }
.fluid-stat.net-positive { background: #fff7e6; }
.fluid-stat.net-positive .stat-value { color: #fa8c16; }
.fluid-stat.net-negative { background: #f6ffed; }
.fluid-stat.net-negative .stat-value { color: #52c41a; }
.fluid-stat.net-negative-warn { background: #f6ffed; }
.fluid-stat.net-negative-warn .stat-value { color: #389e0d; }

/* eCASH Liberation */
.liberation-list, .mobility-list, .nutrition-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.liberation-item, .mobility-item, .nutrition-item {
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafbfc;
}

.liberation-item.severity-critical { border-left: 3px solid #ff4d4f; }
.liberation-item.severity-high { border-left: 3px solid #fa8c16; }
.liberation-item.severity-medium { border-left: 3px solid #faad14; }

.liberation-header, .mobility-header, .nutrition-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.liberation-title, .mobility-title, .nutrition-title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.liberation-desc, .mobility-desc, .nutrition-desc {
  margin: 0;
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}

.liberation-value, .nutrition-value {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
</style>












