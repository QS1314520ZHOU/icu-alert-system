<template>
  <div class="mdt-page">
    <!-- 顶部：Header + 步骤条 -->
    <a-card :bordered="false" class="mdt-hero">
      <MdtHeader
        :patient-label="selectedPatientLabel"
        :patient-headline="patientHeadline"
        :severity-label="mdtSeverityLabel"
        :severity-tone="mdtSeverityTone"
        :closure-percent="closurePercent"
        :pending-confirmation-count="pendingConfirmationCount"
        :workspace-dirty="workspaceDirty"
        :is-session-closed="isSessionClosed"
        @open-session-drawer="sessionDrawerOpen = true"
      />
      <MdtStepBar v-model="currentMdtStep" :steps="mdtStepRows" />
    </a-card>

    <!-- 主体：侧边栏 + 步骤内容 -->
    <section class="mdt-step-layout">
      <aside class="mdt-summary-rail">
        <MdtSummaryRail
          :patient-headline="patientHeadline"
          :patient-subline="patientSubline"
          :severity-label="mdtSeverityLabel"
          :decision-total-count="decisionRows.length"
          :pending-confirmation-count="pendingConfirmationCount"
          :completed-decision-count="completedDecisionCount"
          :closure-percent="closurePercent"
          :next-action-text="nextActionText"
          :todo-rows="todoRows"
        />
      </aside>

      <main class="mdt-step-main">
        <MdtPatientStep
          v-if="currentMdtStep === 'patient'"
          v-model:selected-patient-id="selectedPatientId"
          :patient-options="patientOptions"
          :patient-headline="patientHeadline"
          :patient-subline="patientSubline"
          :loading="loading"
          :organ-rows="mdtOrganRows"
          :organ-states="mdtOrganStates"
          :organ-tooltips="mdtOrganTooltips"
          :selected-patient-out-of-dept-hint="selectedPatientOutOfDeptHint"
          @generate="handleGenerateAssessment"
          @open-patient="openPatientDetail"
          @organ-click="handleMdtOrganClick"
          @next="goMdtStep('review')"
        />

        <MdtReviewStep
          v-else-if="currentMdtStep === 'review'"
          :meta-summary="metaSummary"
          :mdt-severity-label="mdtSeverityLabel"
          :active-system-label="activeSystemLabel"
          :conflict-rows="conflictRows"
          :specialist-rows="specialistRows"
          :system-cards="systemCards"
          :active-specialist="activeSpecialist"
          :syncable-ai-actions="syncableAiActions"
          :is-generating-assessment="isGeneratingAssessment"
          @select-specialist="selectSpecialist"
          @sync-decisions="syncDecisionsFromMetaActions"
          @next="goMdtStep('decision')"
        />

        <MdtDecisionStep
          v-else-if="currentMdtStep === 'decision'"
          :decision-rows="guidedDecisionRows"
          :pending-confirmation-count="pendingConfirmationCount"
          :pending-decision-count="pendingDecisionCount"
          :in-progress-decision-count="inProgressDecisionCount"
          :completed-decision-count="completedDecisionCount"
          :dismissed-decision-count="dismissedDecisionCount"
          :saving-workspace="savingWorkspace"
          :is-session-closed="isSessionClosed"
          :confirming-decision-ids="confirmingDecisionIds"
          @add="addDecision"
          @save="saveWorkspace"
          @fill-defaults="fillDecisionDefaults"
          @confirm="confirmDecision"
          @mark-status="markDecisionStatus"
          @remove="removeDecision"
          @next="goMdtStep('archive')"
        />

        <MdtArchiveStep
          v-else-if="currentMdtStep === 'archive'"
          v-model:tags-text="tagsText"
          v-model:participants-text="participantsText"
          v-model:final-summary="finalSummary"
          v-model:consult-record="consultRecord"
          v-model:progress-record="progressRecord"
          :document-status-rows="documentStatusRows"
          :generating-doc-type="generatingDocType"
          :auto-session-summary="autoSessionSummary"
          :mdt-summary-preview="latestMdtDocumentPreview"
          :is-session-closed="isSessionClosed"
          :saving-workspace="savingWorkspace"
          @save="saveWorkspace"
          @generate-document="generateDocument"
          @copy-summary="copyText(autoSessionSummary, '会诊摘要已复制')"
          @close-session="closeCurrentSession"
          @export-session="exportCurrentSession"
        />
      </main>
    </section>

    <!-- 历史会话抽屉 -->
    <MdtSessionDrawer
      v-model:open="sessionDrawerOpen"
      :sessions="visibleWorkspaceSessions"
      :current-session-id="currentSessionId"
      :session-list-open-only="sessionListOpenOnly"
      :session-search="sessionSearch"
      :session-phase-filter="sessionPhaseFilter"
      @update:session-list-open-only="sessionListOpenOnly = $event"
      @update:session-search="sessionSearch = $event"
      @update:session-phase-filter="sessionPhaseFilter = $event"
      @switch-session="switchSession"
      @start-new-session="startNewSession"
      @duplicate-current-session="duplicateCurrentSession"
      @export-current-session="exportCurrentSession"
      @close-current-session="closeCurrentSession"
      @reopen-current-session="reopenCurrentSession"
    />

    <div v-if="error" class="error-box">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { Card as ACard } from 'ant-design-vue'
import { useMdtWorkspace } from '../composables/useMdtWorkspace'
import MdtArchiveStep from '../components/mdt/MdtArchiveStep.vue'
import MdtDecisionStep from '../components/mdt/MdtDecisionStep.vue'
import MdtHeader from '../components/mdt/MdtHeader.vue'
import MdtPatientStep from '../components/mdt/MdtPatientStep.vue'
import MdtReviewStep from '../components/mdt/MdtReviewStep.vue'
import MdtSessionDrawer from '../components/mdt/MdtSessionDrawer.vue'
import MdtStepBar from '../components/mdt/MdtStepBar.vue'
import MdtSummaryRail from '../components/mdt/MdtSummaryRail.vue'

void ACard

const {
  // 状态
  loading, error, selectedPatientId, sessionDrawerOpen, sessionListOpenOnly,
  sessionSearch, sessionPhaseFilter, savingWorkspace, generatingDocType,
  currentSessionId, currentMdtStep, confirmingDecisionIds,
  consultRecord, progressRecord, finalSummary, participantsText, tagsText,
  // 派生
  patientOptions, specialistRows, conflictRows, metaSummary, activeSpecialist,
  syncableAiActions, systemCards, mdtOrganRows, mdtOrganStates, mdtOrganTooltips,
  isGeneratingAssessment, decisionRows, guidedDecisionRows,
  pendingConfirmationCount, pendingDecisionCount, inProgressDecisionCount,
  completedDecisionCount, dismissedDecisionCount, closurePercent,
  documentStatusRows, latestMdtDocumentPreview, autoSessionSummary,
  isSessionClosed, workspaceDirty, visibleWorkspaceSessions,
  patientHeadline, patientSubline, selectedPatientLabel, selectedPatientOutOfDeptHint,
  mdtSeverityTone, mdtSeverityLabel, todoRows, nextActionText, mdtStepRows,
  // 方法
  handleGenerateAssessment, saveWorkspace, generateDocument,
  addDecision, removeDecision, markDecisionStatus, confirmDecision,
  fillDecisionDefaults, syncDecisionsFromMetaActions,
  switchSession, startNewSession, duplicateCurrentSession,
  exportCurrentSession, closeCurrentSession, reopenCurrentSession,
  copyText, goMdtStep, selectSpecialist, openPatientDetail,
} = useMdtWorkspace()

const activeSystemLabel = ''

function handleMdtOrganClick(organKey: string) {
  const row = mdtOrganRows.value.find((item: any) => item.organKey === organKey)
  if (row?.agent) selectSpecialist(row.agent)
}
</script>

<style scoped>
.mdt-page {
  display: grid;
  gap: 14px;
  min-height: calc(100vh - 88px);
  padding: 16px;
  background: var(--bg-base);
}
.mdt-hero {
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  box-shadow: var(--card-shadow);
}
.mdt-hero :deep(.ant-card-body) {
  padding: 14px 16px;
}
.mdt-step-layout {
  display: grid;
  grid-template-columns: minmax(260px, 0.28fr) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}
.mdt-summary-rail,
.mdt-step-main {
  min-width: 0;
}
.mdt-step-main {
  display: grid;
  gap: 14px;
}
.error-box {
  padding: 10px 14px;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--card-radius);
  background: rgba(239, 68, 68, 0.08);
  color: #ef4444;
  font-size: 13px;
}
@media (max-width: 1280px) {
  .mdt-step-layout {
    grid-template-columns: 1fr;
  }
  .mdt-summary-rail {
    order: 2;
  }
  .mdt-step-main {
    order: 1;
  }
}
@media (max-width: 720px) {
  .mdt-page {
    padding: 12px;
  }
}
</style>
