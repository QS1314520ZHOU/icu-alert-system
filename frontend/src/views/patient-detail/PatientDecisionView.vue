<template>
  <div class="pd-decision">
    <!-- Sub-navigation -->
    <nav class="pd-sub-nav" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        role="tab"
        :aria-selected="activeTab === tab.key"
        :class="['pd-sub-btn', { 'is-active': activeTab === tab.key }]"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- Tab Content -->
    <div class="pd-sub-content">
      <PatientAlertsTab
        v-if="activeTab === 'alerts'"
        :latest-composite-alert="latestCompositeAlert"
        :latest-composite-window-hours="latestCompositeWindowHours"
        :latest-composite-modi="latestCompositeModi"
        :latest-composite-organ-count="latestCompositeOrganCount"
        :latest-composite-involved-text="latestCompositeInvolvedText"
        :composite-radar-option="compositeRadarOption"
        :latest-weaning-alert="latestWeaningAlert"
        :latest-weaning-status="latestWeaningStatus"
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
        :focused-organ="focusedOrgan"
        :focused-alert-types="focusedAlertTypes"
      />

      <PatientSimilarCasesTab
        v-if="activeTab === 'similar'"
        :review="similarCaseReview"
        :loading="similarCaseLoading"
        :error="similarCaseError"
        :on-refresh="onRefreshSimilar"
        :fmt-time="fmtTime"
      />

      <PatientLongTermFollowupTab
        v-if="activeTab === 'followup'"
        :patient-id="patientId"
        :patient="patient"
        :pics-risk-record="picsRiskRecord"
        :open-ai-tab="onOpenAiTab"
      />

      <PatientDigitalTwinTab
        v-if="activeTab === 'twin'"
        :patient-id="patientId"
        :patient="patient"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, defineAsyncComponent } from 'vue'

const PatientAlertsTab = defineAsyncComponent(() => import('../../components/patient-detail/AlertsTab.vue'))
const PatientSimilarCasesTab = defineAsyncComponent(() => import('../../components/patient-detail/SimilarCasesTab.vue'))
const PatientLongTermFollowupTab = defineAsyncComponent(() => import('../../components/patient-detail/LongTermFollowupTab.vue'))
const PatientDigitalTwinTab = defineAsyncComponent(() => import('../../components/patient-detail/DigitalTwinTab.vue'))

defineProps<{
  patientId: string
  patient: any
  latestCompositeAlert: any
  latestCompositeWindowHours: number
  latestCompositeModi: any
  latestCompositeOrganCount: number
  latestCompositeInvolvedText: string
  compositeRadarOption: any
  latestWeaningAlert: any
  latestWeaningStatus: any
  latestPostExtubationAlert: any
  personalizedThresholdRecord: any
  personalizedThresholdHistory: any[]
  personalizedThresholdApprovedRecord: any
  personalizedThresholdLoading: boolean
  personalizedThresholdError: string
  personalizedThresholdReviewing: boolean
  reviewPersonalizedThreshold: (record: any, status: 'approved' | 'rejected', meta?: any) => void
  alerts: any[]
  fmtTime: (t: any) => string
  normalizeSeverity: (s: any) => string
  alertSeverityText: (s: any) => string
  alertDomainLabel: (t: any) => string
  alertPriorityLabel: (p: any) => string
  alertSourceLabel: (s: any) => string
  formatAlertValue: (a: any) => string
  alertTypeText: (t: any) => string
  alertCategoryText: (c: any) => string
  alertDetailFields: (a: any) => any[]
  isAiRiskAlert: (a: any) => boolean
  aiConfidenceClass: (c: any) => string
  aiRiskConfidenceLevel: (a: any) => string
  aiRiskLevelText: (a: any) => string
  feedbackOutcomeText: (o: any) => string
  submitAiFeedback: (item: any, outcome: 'confirmed' | 'dismissed' | 'inaccurate') => void
  aiRiskOrganRows: (item: any) => any[]
  aiRiskValidationIssues: (item: any) => any[]
  aiRiskHallucinations: (item: any) => any[]
  aiRiskEvidenceList: (item: any) => any[]
  openEvidence: (evidence: any) => void
  aiRiskExplainabilityRows: (item: any) => any[]
  formatAlertExtra: (extra: any) => string
  acknowledgeAlert: (item: any, disposition?: string) => void
  focusedOrgan: string
  focusedAlertTypes: string[]
  similarCaseReview: any
  similarCaseLoading: boolean
  similarCaseError: string
  onRefreshSimilar: () => void
  picsRiskRecord: any
  onOpenAiTab: () => void
}>()

const activeTab = ref('alerts')

const tabs = [
  { key: 'alerts', label: '当前预警' },
  { key: 'similar', label: '相似病例' },
  { key: 'followup', label: '随访与试验' },
  { key: 'twin', label: 'What-if' },
]
</script>

<style scoped>
.pd-decision {
  display: flex;
  flex-direction: column;
  gap: var(--section-gap, 24px);
}

.pd-sub-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  background: var(--color-bg-surface, #FFFFFF);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  overflow-x: auto;
}

.pd-sub-btn {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  border: 1px solid transparent;
  border-radius: var(--radius-md, 6px);
  background: transparent;
  color: var(--color-text-secondary, #667085);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.pd-sub-btn:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-primary, #18212B);
}

.pd-sub-btn.is-active {
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  border-color: var(--color-primary, #2563EB);
  color: var(--color-primary, #2563EB);
  font-weight: 600;
}

.pd-sub-content {
  background: var(--color-bg-surface, #FFFFFF);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
}

@media (max-width: 390px) {
  .pd-sub-nav {
    padding: 4px 8px;
    gap: 2px;
  }

  .pd-sub-btn {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>
