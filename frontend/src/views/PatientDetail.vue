<template>
  <PatientDetailLayout
    :name="displayName"
    :bed="displayBed"
    :gender-age="displayGenderAge"
    :diagnosis="displayDiagnosis"
    :dept="displayDept"
    :his-pid="displayHisPid"
    :active-area="activeArea"
    :safety-items="safetyItems"
    :evidence-modal-open="evidenceModalOpen"
    :evidence-modal="evidenceModal"
    :open-evidence="openEvidence"
    @back="backToList"
    @update:active-area="setArea"
  >
    <template #header-actions>
      <button class="pd-action-btn" type="button" @click="loadClinicalSummary">
        生成查房摘要
      </button>
    </template>

    <!-- Sub-views -->
    <PatientOverviewView
      v-if="activeArea === 'overview'"
      :risks="overviewRisks"
      :vitals="overviewVitals"
      :vitals-source="vitalsSourceText"
      :vitals-time="heroMonitorUpdatedAt"
      :shift-tasks="shiftTasks"
      :trend-preview="trendPreview"
      @acknowledge-risk="acknowledgeRisk"
      @open-evidence="openEvidenceFromRisk"
      @open-tasks="openTasks"
      @go-monitoring="setArea('monitoring')"
    />

    <PatientMonitoringView
      v-if="activeArea === 'monitoring'"
      :trend-window="trendWindow"
      :trend-points="trendPoints"
      :trend-option="trendOption"
      :forecast-meta="forecastMeta"
      :forecast-enabled="trajectoryPublicConfig.enabled"
      :forecast-horizon="trajectoryPublicConfig.horizon_hours"
      :forecast-data="vitalForecast.state.data"
      :waveform-selected-channel="waveformSelectedChannel"
      :waveform-hours="waveformHours"
      :waveform-loading="waveformLoading"
      :waveform-channel-options="waveformChannelOptions"
      :waveform-points="waveformPoints"
      :waveform-qc="waveformQc"
      :waveform-events="waveformEvents"
      :labs="labs"
      :fmt-time="fmtTime"
      :lab-flag="labFlag"
      :on-refresh-trend="loadTrend"
      :on-refresh-waveform="loadWaveform"
      @update:trend-window="trendWindow = $event"
      @update:waveform-selected-channel="waveformSelectedChannel = $event"
      @update:waveform-hours="waveformHours = $event"
      @legend-select-changed="saveTrendLegendSelection"
    />

    <PatientTreatmentView
      v-if="activeArea === 'treatment'"
      :ecash-alerts="ecashAlerts"
      :ecash-bundle-alert="latestEcashBundleAlert"
      :mobility-alerts="mobilityAlerts"
      :pe-alerts="peAlerts"
      :drug-columns="drugColumns"
      :drug-table-rows="drugTableRows"
      :assessment-columns="assessmentColumns"
      :assessment-table-rows="assessmentTableRows"
      :sbt-timeline-summary="sbtTimelineSummary"
      :sbt-timeline-records="sbtTimelineRecords"
      :sbt-timeline-ai-summary="sbtTimelineAiSummary"
      :sbt-timeline-loading="sbtTimelineLoading"
      :sbt-timeline-error="sbtTimelineError"
      :fmt-time="fmtTime"
      :alert-type-text="alertTypeText"
      :on-refresh-sbt="() => loadSbtTimeline(true)"
    />

    <PatientDecisionView
      v-if="activeArea === 'decision'"
      :patient-id="patientId"
      :patient="patient"
      :latest-composite-alert="latestCompositeAlert"
      :latest-composite-window-hours="latestCompositeWindowHours"
      :latest-composite-modi="latestCompositeModi"
      :latest-composite-organ-count="latestCompositeOrganCount"
      :latest-composite-involved-text="latestCompositeInvolvedText"
      :composite-radar-option="compositeRadarOption"
      :latest-weaning-alert="latestWeaningAlert"
      :latest-weaning-status="weaningStatus"
      :latest-post-extubation-alert="latestPostExtubationAlert"
      :personalized-threshold-record="personalizedThresholdRecord"
      :personalized-threshold-history="personalizedThresholdHistory"
      :personalized-threshold-approved-record="personalizedThresholdApprovedRecord"
      :personalized-threshold-loading="personalizedThresholdLoading"
      :personalized-threshold-error="personalizedThresholdError"
      :personalized-threshold-reviewing="personalizedThresholdReviewing"
      :review-personalized-threshold="reviewPersonalizedThreshold"
      :alerts="alerts"
      :fmt-time="fmtTime"
      :normalize-severity="normalizeSeverity"
      :alert-severity-text="alertSeverityText"
      :alert-domain-label="alertDomainLabel"
      :alert-priority-label="alertPriorityLabel"
      :alert-source-label="alertSourceLabel"
      :format-alert-value="formatAlertValue"
      :alert-type-text="alertTypeText"
      :alert-category-text="alertCategoryText"
      :alert-detail-fields="alertDetailFields"
      :is-ai-risk-alert="isAiRiskAlert"
      :ai-confidence-class="aiConfidenceClass"
      :ai-risk-confidence-level="aiRiskConfidenceLevel"
      :ai-risk-level-text="aiRiskLevelText"
      :feedback-outcome-text="feedbackOutcomeText"
      :submit-ai-feedback="submitAiFeedback"
      :ai-risk-organ-rows="aiRiskOrganRows"
      :ai-risk-validation-issues="aiRiskValidationIssues"
      :ai-risk-hallucinations="aiRiskHallucinations"
      :ai-risk-evidence-list="aiRiskEvidenceList"
      :open-evidence="openEvidence"
      :ai-risk-explainability-rows="aiRiskExplainabilityRows"
      :format-alert-extra="formatAlertExtra"
      :acknowledge-alert="acknowledgeAlert"
      :focused-organ="selectedBodyOrgan"
      :focused-alert-types="focusedAlertTypes"
      :similar-case-review="similarCaseReview"
      :similar-case-loading="similarCaseLoading"
      :similar-case-error="similarCaseError"
      :on-refresh-similar="() => loadSimilarCaseReview(true)"
      :pics-risk-record="picsRiskRecord"
      :on-open-ai-tab="() => setArea('documents')"
    />

    <PatientDocumentsView
      v-if="activeArea === 'documents'"
      :patient-id="patientId"
      :patient="patient"
      :ai-lab-loading="aiLabLoading"
      :ai-lab-summary="aiLabSummary"
      :load-ai-lab="loadAiLab"
      :render-ai-rich-text="renderAiRichText"
      :ai-lab-error="aiLabError"
      :ai-rule-loading="aiRuleLoading"
      :load-ai-rules="loadAiRules"
      :ai-rule-rows="aiRuleRows"
      :ai-rule-columns="aiRuleColumns"
      :ai-rule-text="aiRuleText"
      :ai-rule-error="aiRuleError"
      :ai-risk-loading="aiRiskLoading"
      :load-ai-risk="loadAiRisk"
      :latest-ai-risk-alert="latestAiRiskAlert"
      :ai-confidence-class="aiConfidenceClass"
      :ai-risk-confidence-level="aiRiskConfidenceLevel"
      :ai-risk-level-text="aiRiskLevelText"
      :ai-risk-evidence-list="aiRiskEvidenceList"
      :open-evidence="openEvidence"
      :ai-risk-hallucinations="aiRiskHallucinations"
      :ai-risk-forecast="aiRiskForecast"
      :ai-risk-text="aiRiskText"
      :ai-risk-error="aiRiskError"
      :integrated-risk-loading="integratedRiskLoading"
      :load-integrated-risk="loadIntegratedRisk"
      :integrated-risk-report="integratedRiskReport"
      :integrated-risk-error="integratedRiskError"
      :metabolic-phase-loading="metabolicPhaseLoading"
      :load-metabolic-phase="loadMetabolicPhase"
      :metabolic-phase-record="metabolicPhaseRecord"
      :metabolic-phase-error="metabolicPhaseError"
      :beta-blocker-loading="betaBlockerAdvisorLoading"
      :load-beta-blocker-advisor="loadBetaBlockerAdvisor"
      :beta-blocker-advisor-record="betaBlockerAdvisorRecord"
      :beta-blocker-advisor-error="betaBlockerAdvisorError"
      :fibrinolysis-loading="fibrinolysisLoading"
      :load-fibrinolysis="loadFibrinolysis"
      :fibrinolysis-record="fibrinolysisRecord"
      :fibrinolysis-error="fibrinolysisError"
      :prone-position-loading="pronePositionLoading"
      :load-prone-position="loadPronePosition"
      :prone-position-record="pronePositionRecord"
      :prone-position-error="pronePositionError"
      :pics-risk-loading="picsRiskLoading"
      :load-pics-risk="loadPicsRisk"
      :pics-risk-record="picsRiskRecord"
      :pics-risk-error="picsRiskError"
      :on-open-followup-tab="() => setArea('decision')"
      :ai-handoff-loading="aiHandoffLoading"
      :load-ai-handoff="loadAiHandoff"
      :copy-handoff-summary="copyHandoffSummary"
      :ai-handoff="aiHandoff"
      :ai-handoff-confidence="aiHandoffConfidence"
      :normalize-list="normalizeList"
      :ai-handoff-error="aiHandoffError"
      :knowledge-loading="knowledgeLoading"
      :load-knowledge-docs="loadKnowledgeDocs"
      :handle-reload-knowledge="handleReloadKnowledge"
      :knowledge-docs="knowledgeDocs"
      :knowledge-status="knowledgeStatus"
      :selected-knowledge-doc-id="selectedKnowledgeDocId"
      :load-knowledge-document="loadKnowledgeDocument"
      :selected-knowledge-doc="selectedKnowledgeDoc"
      :knowledge-scope-text="knowledgeScopeText"
      :knowledge-error="knowledgeError"
    />
  </PatientDetailLayout>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePatientDetail } from './patient-detail/usePatientDetail'
import PatientDetailLayout from './patient-detail/PatientDetailLayout.vue'
import PatientOverviewView from './patient-detail/PatientOverviewView.vue'
import PatientMonitoringView from './patient-detail/PatientMonitoringView.vue'
import PatientTreatmentView from './patient-detail/PatientTreatmentView.vue'
import PatientDecisionView from './patient-detail/PatientDecisionView.vue'
import PatientDocumentsView from './patient-detail/PatientDocumentsView.vue'
import type { DetailAreaKey } from './patient-detail/types'

const router = useRouter()

const {
  // Navigation
  activeArea, setArea,
  // Patient
  patient, vitals, displayName, displayDiagnosis, displayDept, displayBed, displayGenderAge,
  // Hero
  heroMonitorUpdatedAt, vitalsSourceText,
  // Body map
  selectedBodyOrgan, focusedAlertTypes,
  // Alerts
  alerts, alertTypeText, formatAlertValue, latestAiRiskAlert, latestCompositeAlert, latestCompositeOrganCount,
  latestCompositeWindowHours, latestCompositeModi, latestCompositeInvolvedText, compositeRadarOption,
  latestWeaningAlert, weaningStatus, latestPostExtubationAlert, latestEcashBundleAlert,
  // Weaning
  // SBT timeline
  sbtTimelineSummary, sbtTimelineRecords, sbtTimelineAiSummary, sbtTimelineLoading, sbtTimelineError, loadSbtTimeline,
  // Clinical summary
  loadClinicalSummary,
  // Trend
  trendWindow, trendPoints, trendOption, forecastMeta, saveTrendLegendSelection, loadTrend,
  // Waveform
  waveformHours, waveformSelectedChannel, waveformPoints, waveformQc, waveformEvents, waveformLoading, waveformChannelOptions, loadWaveform,
  // Labs/Drugs/Assessments
  labs, drugTableRows, assessmentTableRows, drugColumns, assessmentColumns,
  // Similar cases
  similarCaseReview, similarCaseLoading, similarCaseError, loadSimilarCaseReview,
  // Personalized thresholds
  personalizedThresholdRecord, personalizedThresholdHistory, personalizedThresholdApprovedRecord,
  personalizedThresholdLoading, personalizedThresholdError, personalizedThresholdReviewing,
  reviewPersonalizedThreshold,
  // AI
  aiLabSummary, aiRuleText, aiRuleRows, aiRuleColumns, aiRiskText, aiRiskForecast,
  integratedRiskReport, metabolicPhaseRecord, betaBlockerAdvisorRecord, fibrinolysisRecord,
  pronePositionRecord, picsRiskRecord, aiHandoff,
  aiLabError, aiRuleError, aiRiskError, integratedRiskError, metabolicPhaseError,
  betaBlockerAdvisorError, fibrinolysisError, pronePositionError, picsRiskError, aiHandoffError,
  aiLabLoading, aiRuleLoading, aiRiskLoading, integratedRiskLoading, metabolicPhaseLoading,
  betaBlockerAdvisorLoading, fibrinolysisLoading, pronePositionLoading, picsRiskLoading, aiHandoffLoading,
  loadAiHandoff, copyHandoffSummary, submitAiFeedback,
  loadAiLab, loadAiRules, loadAiRisk, loadIntegratedRisk, loadMetabolicPhase,
  loadBetaBlockerAdvisor, loadFibrinolysis, loadPronePosition, loadPicsRisk,
  // Knowledge
  knowledgeDocs, selectedKnowledgeDocId, selectedKnowledgeDoc, knowledgeLoading, knowledgeError, knowledgeStatus,
  handleReloadKnowledge, loadKnowledgeDocs, loadKnowledgeDocument,
  // Evidence modal
  evidenceModalOpen, evidenceModal, openEvidence,
  // Formatting
  fmtBP, fmtTemp, fmtTime, formatHeroMetric, formatAlertExtra,
  labFlag, renderAiRichText, knowledgeScopeText, aiRiskOrganRows, aiRiskValidationIssues,
  aiRiskHallucinations, aiRiskEvidenceList, aiRiskExplainabilityRows,
  normalizeSeverity, isAiRiskAlert, aiRiskConfidenceLevel,
  alertDomainLabel, alertPriorityLabel, alertSourceLabel,
  alertSeverityText, alertCategoryText, alertDetailFields, aiConfidenceClass, aiRiskLevelText, feedbackOutcomeText, aiHandoffConfidence, normalizeList,
  // Alerts CRUD
  acknowledgeAlert,
  // ACash alerts
  ecashAlerts, mobilityAlerts, peAlerts,
  // Forecast
  vitalForecast, trajectoryPublicConfig,
} = usePatientDetail()

// Computed: patient ID
const patientId = computed(() => String(patient.value?._id || ''))

// Computed: display HIS PID
const displayHisPid = computed(() =>
  patient.value?.hisPid || patient.value?.hisPID || '无'
)

// Computed: safety items for the header strip
const safetyItems = computed(() => {
  const items: Array<{ key: string; text: string; level: 'danger' | 'warning' | 'info' }> = []
  const p = patient.value || {}

  // Allergies
  if (p.allergies || p.allergyText) {
    items.push({ key: 'allergy', text: `过敏：${p.allergies || p.allergyText}`, level: 'danger' })
  }

  // Isolation
  if (p.isolation || p.isolationType) {
    items.push({ key: 'isolation', text: `隔离：${p.isolation || p.isolationType}`, level: 'warning' })
  }

  // Mechanical ventilation
  if (p.ventilator || p.mechanicalVentilation) {
    items.push({ key: 'vent', text: '机械通气', level: 'info' })
  }

  // CRRT
  if (p.crrt || p.crrtActive) {
    items.push({ key: 'crrt', text: 'CRRT', level: 'info' })
  }

  return items
})

// Computed: overview risks
const overviewRisks = computed(() => {
  const risks: Array<{
    id?: string
    name: string
    severity: 'critical' | 'high' | 'warning' | 'info'
    severityText: string
    conclusion: string
    evidence?: string[]
    suggestion?: string
  }> = []

  // Add alerts as risks
  for (const alert of alerts.value.slice(0, 5)) {
    const severity = normalizeSeverity(alert?.severity)
    risks.push({
      id: alert?._id,
      name: alert?.title || alert?.alert_type || '未知风险',
      severity: severity as any,
      severityText: alertSeverityText(alert?.severity),
      conclusion: alert?.summary || alert?.message || '',
      evidence: Array.isArray(alert?.evidence) ? alert.evidence.slice(0, 3) : [],
      suggestion: alert?.recommendation || '',
    })
  }

  return risks
})

// Computed: overview vitals
const overviewVitals = computed(() => {
  const v = vitals.value || {}
  const items = [
    { label: 'HR', value: v?.hr != null ? formatHeroMetric(v.hr) : '—', unit: 'bpm', status: getVitalStatus('hr', v?.hr), trend: getVitalTrend('hr') },
    { label: 'BP', value: fmtBP(v), unit: 'mmHg', status: getVitalStatus('bp', v?.nibp_sys), trend: getVitalTrend('bp') },
    { label: 'SpO₂', value: v?.spo2 != null ? `${formatHeroMetric(v.spo2)}%` : '—', unit: '', status: getVitalStatus('spo2', v?.spo2), trend: getVitalTrend('spo2') },
    { label: 'RR', value: v?.rr != null ? formatHeroMetric(v.rr) : '—', unit: '/min', status: getVitalStatus('rr', v?.rr), trend: getVitalTrend('rr') },
    { label: 'T', value: fmtTemp(v?.temp), unit: '°C', status: getVitalStatus('temp', v?.temp), trend: getVitalTrend('temp') },
    { label: 'MAP', value: formatHeroMetric(v?.ibp_map ?? v?.nibp_map), unit: 'mmHg', status: getVitalStatus('map', v?.ibp_map ?? v?.nibp_map), trend: getVitalTrend('map') },
  ]
  return items
})

// Computed: shift tasks (placeholder - would come from API)
const shiftTasks = computed(() => {
  return []
})

// Computed: trend preview based on current risk
const trendPreview = computed(() => {
  // Show relevant trends based on the primary risk
  const primaryRisk = overviewRisks.value[0]
  if (!primaryRisk) return []

  const items: Array<{ label: string; current: string; unit: string; direction: 'up' | 'down' | 'stable' }> = []
  const v = vitals.value || {}

  // Always show key vitals
  if (v?.hr != null) items.push({ label: 'HR', current: formatHeroMetric(v.hr), unit: 'bpm', direction: 'stable' })
  if (v?.nibp_map != null || v?.ibp_map != null) items.push({ label: 'MAP', current: formatHeroMetric(v.ibp_map ?? v.nibp_map), unit: 'mmHg', direction: 'stable' })
  if (v?.spo2 != null) items.push({ label: 'SpO₂', current: `${formatHeroMetric(v.spo2)}%`, unit: '', direction: 'stable' })

  return items
})

// Helper: get vital status
function getVitalStatus(type: string, value: any): 'normal' | 'warning' | 'critical' | 'empty' {
  if (value == null) return 'empty'
  const num = Number(value)
  if (isNaN(num)) return 'empty'

  // Simple threshold checks (would be configurable in production)
  switch (type) {
    case 'hr':
      if (num < 50 || num > 120) return 'critical'
      if (num < 60 || num > 100) return 'warning'
      return 'normal'
    case 'spo2':
      if (num < 90) return 'critical'
      if (num < 95) return 'warning'
      return 'normal'
    case 'rr':
      if (num < 8 || num > 30) return 'critical'
      if (num < 12 || num > 20) return 'warning'
      return 'normal'
    case 'temp':
      if (num < 35 || num > 39) return 'critical'
      if (num < 36 || num > 37.5) return 'warning'
      return 'normal'
    case 'map':
      if (num < 60 || num > 100) return 'critical'
      if (num < 65 || num > 90) return 'warning'
      return 'normal'
    default:
      return 'normal'
  }
}

// Helper: get vital trend (placeholder - would use historical data)
function getVitalTrend(_type: string): 'up' | 'down' | 'stable' {
  return 'stable'
}

// Navigation
function backToList() {
  router.push('/patients')
}

function acknowledgeRisk(risk: any) {
  if (risk?.id) {
    acknowledgeAlert({ _id: risk.id })
  }
}

function openEvidenceFromRisk(risk: any) {
  if (risk?.evidence?.length) {
    openEvidence({ chunk_id: risk.evidence[0] })
  }
}

function openTasks() {
  // Would open task drawer
}

// Tab-to-area mapping for backward compatibility
const tabToAreaMap: Record<string, DetailAreaKey> = {
  trend: 'monitoring',
  waveform: 'monitoring',
  labs: 'monitoring',
  drugs: 'treatment',
  assess: 'treatment',
  sbt: 'treatment',
  ecash: 'treatment',
  mobility: 'treatment',
  pe: 'treatment',
  alerts: 'decision',
  twin: 'decision',
  similar: 'decision',
  followup: 'decision',
  ai: 'documents',
  documents: 'documents',
}

// Watch for route query changes to map old tabs to new areas.
// NOTE: This watcher must NOT call setArea() because setArea() calls
// router.replace(), which would re-trigger this watcher and create an
// infinite loop. Instead, update activeArea directly.
const validAreas: DetailAreaKey[] = ['overview', 'monitoring', 'treatment', 'decision', 'documents']
watch(() => router.currentRoute.value.query, (query) => {
  // If area is explicitly set and valid, use it
  if (query.area) {
    const area = query.area as DetailAreaKey
    if (validAreas.includes(area)) {
      activeArea.value = area
      return
    }
  }

  // If tab is set (old format), map to area
  if (query.tab) {
    const tab = String(query.tab)
    const area = tabToAreaMap[tab] || 'overview'
    activeArea.value = area as DetailAreaKey
    return
  }

  // Default to overview
  activeArea.value = 'overview'
}, { immediate: true })
</script>

<style scoped>
.pd-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 16px;
  background: var(--color-primary, #2563EB);
  color: #FFFFFF;
  border: none;
  border-radius: var(--radius-button, 6px);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.pd-action-btn:hover {
  background: var(--color-primary-hover, #1D4ED8);
}
</style>
