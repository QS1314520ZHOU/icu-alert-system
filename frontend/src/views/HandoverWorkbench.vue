<template>
  <div class="handover-workbench">
    <!-- Error banner -->
    <a-alert v-if="error" :message="error" type="error" closable @close="error = ''" style="margin-bottom: 12px" />

    <!-- Left sidebar: Patient list -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2 class="page-title">🩺 智能交接班</h2>
        <a-select
          v-model:value="deptFilter"
          :options="deptOptions"
          size="small"
          placeholder="选择病区"
          style="width: 140px"
        />
      </div>
      <HandoverPatientList
        :patients="patientBriefs"
        :active-patient-id="activePatientId"
        :loading="patientsLoading"
        :search-text="patientSearch"
        @select="onSelectPatient"
        @search="patientSearch = $event"
      />
    </aside>

    <!-- Main content area -->
    <main class="content">
      <a-spin :spinning="loading">
        <template v-if="!activePatientId">
          <div class="placeholder">
            <div class="placeholder-icon">👈</div>
            <div class="placeholder-text">请从左侧选择患者开始交接班</div>
          </div>
        </template>

        <template v-else>
          <!-- Top toolbar -->
          <div class="content-toolbar">
            <div class="patient-banner">
              <span class="banner-bed">{{ currentHandover?.sections?.identify?.bed || '?' }}床</span>
              <span class="banner-name">{{ currentHandover?.sections?.identify?.name || activePatientId }}</span>
              <span class="banner-meta">{{ currentHandover?.sections?.identify?.admission_no }}</span>
            </div>
            <div class="toolbar-actions">
              <a-button
                type="primary"
                :loading="generating"
                @click="onGenerate"
                :disabled="!activePatientId"
              >
                🤖 AI 生成草稿
              </a-button>
              <a-button @click="onViewBrief" :disabled="!currentHandover">📄 简报</a-button>
              <a-button @click="onViewHistory" :disabled="!activePatientId">📜 历史</a-button>
              <a-button
                type="default"
                :loading="saving"
                @click="onSave"
                :disabled="!currentHandover"
              >
                💾 保存
              </a-button>
            </div>
          </div>

          <!-- Main two-column layout -->
          <div class="content-body">
            <div class="editor-col">
              <IsbarEditor
                v-if="currentHandover"
                :sections="editableSections"
                :ai-generated-fields="currentHandover.ai_generated_fields || []"
                :content-sources="currentHandover.content_sources || {}"
                :status="currentHandover.status"
                @update:sections="onSectionsUpdate"
                @field-edit="onFieldEdit"
              />

              <!-- Confirm / Acknowledge actions -->
              <div class="submit-bar" v-if="currentHandover">
                <template v-if="currentHandover.status === 'draft' || currentHandover.status === 'not_created'">
                  <a-input v-model:value="operator" placeholder="交班人" size="small" style="width: 140px" />
                  <a-button type="primary" :disabled="!operator" :loading="confirming" @click="onConfirm">
                    提交交班
                  </a-button>
                </template>
              </div>
            </div>

            <div class="panel-col">
              <!-- Evidence panel -->
              <HandoverEvidencePanel
                v-if="showEvidence"
                :items="currentHandover?.evidence || []"
              />

              <!-- Brief panel -->
              <HandoverBrief
                v-if="showBrief"
                :brief="briefData"
                @mode-change="onBriefModeChange"
              />

              <!-- History panel -->
              <HandoverHistory
                v-if="showHistory"
                :items="historyItems"
                :loading="historyLoading"
                @select="onSelectHistory"
              />

              <!-- Acknowledgement panel -->
              <AcknowledgementPanel
                v-if="currentHandover?.status === 'submitted'"
                :forced-items="forcedConfirmations"
                :status="currentHandover.status"
                :loading="acknowledging"
                @acknowledge="onAcknowledge"
                @reject="onReject"
                @update:forced-items="forcedConfirmations = $event"
              />
            </div>
          </div>
        </template>
      </a-spin>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  Alert as AAlert,
  Spin as ASpin,
  Button as AButton,
  Input as AInput,
  Select as ASelect,
  message,
} from 'ant-design-vue'
import HandoverPatientList from '../components/handover/HandoverPatientList.vue'
import IsbarEditor from '../components/handover/IsbarEditor.vue'
import HandoverBrief from '../components/handover/HandoverBrief.vue'
import HandoverEvidencePanel from '../components/handover/HandoverEvidencePanel.vue'
import HandoverHistory from '../components/handover/HandoverHistory.vue'
import AcknowledgementPanel from '../components/handover/AcknowledgementPanel.vue'
import {
  generateHandover,
  getPatientHandoverHistory,
  updateHandoverContent,
  confirmHandover,
  acknowledgeHandover,
  rejectHandover,
  getHandoverBrief,
  getForcedAlerts,
  type HandoverBrief as BriefType,
} from '../api/handover'

// ── State ────────────────────────────────────────────────────────────
const error = ref('')
const loading = ref(false)
const generating = ref(false)
const saving = ref(false)
const confirming = ref(false)
const acknowledging = ref(false)
const patientsLoading = ref(false)
const historyLoading = ref(false)

const activePatientId = ref('')
const patientSearch = ref('')
const deptFilter = ref<string | undefined>()
const operator = ref('')
const currentHandover = ref<Record<string, any> | null>(null)
const editableSections = ref<Record<string, any>>({})
const editedFields = ref<string[]>([])
const forcedConfirmations = ref<any[]>([])

const showBrief = ref(false)
const showEvidence = ref(false)
const showHistory = ref(false)
const briefData = ref<BriefType>({ mode: 'full', blocks: [] })
const historyItems = ref<Array<Record<string, any>>>([])

// Placeholder — real patient data would come from the patient list API
const patientBriefs = ref<Array<any>>([])
const deptOptions = ref<Array<{ label: string; value: string }>>([
  { label: '全部病区', value: '' },
])

// ── Actions ──────────────────────────────────────────────────────────

async function onSelectPatient(patient: any) {
  activePatientId.value = patient.patient_id || patient._id
  await loadLatestHandover()
}

async function loadLatestHandover() {
  if (!activePatientId.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await getPatientHandoverHistory(activePatientId.value, { limit: 1 })
    const list = res.data?.handovers || []
    if (list.length && list[0]) {
      currentHandover.value = list[0]
      editableSections.value = JSON.parse(JSON.stringify((list[0] as any).sections || {}))
    } else {
      currentHandover.value = null
      editableSections.value = initEmptySections()
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载交班记录失败'
    currentHandover.value = null
  } finally {
    loading.value = false
  }
}

async function onGenerate() {
  if (!activePatientId.value) return
  generating.value = true
  error.value = ''
  try {
    const res = await generateHandover({
      patient_id: activePatientId.value,
      handover_type: 'nurse_bedside',
    })
    currentHandover.value = res.data?.handover || null
    editableSections.value = JSON.parse(JSON.stringify(currentHandover.value?.sections || {}))
    const handoverId = currentHandover.value?.handover_id

    // Load forced alerts
    if (handoverId) {
      loadForcedAlerts()
    }
    message.success('AI 草稿生成成功')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'AI 生成失败'
  } finally {
    generating.value = false
  }
}

async function onSave() {
  if (!currentHandover.value?.handover_id) return
  saving.value = true
  error.value = ''
  try {
    await updateHandoverContent(currentHandover.value.handover_id, {
      sections: editableSections.value,
      edited_fields: editedFields.value,
    })
    message.success('保存成功')
    editedFields.value = []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

async function onConfirm() {
  if (!currentHandover.value?.handover_id) return
  confirming.value = true
  try {
    // Save first, then confirm
    await updateHandoverContent(currentHandover.value.handover_id, {
      sections: editableSections.value,
      edited_fields: editedFields.value,
    })
    const res = await confirmHandover(currentHandover.value.handover_id, { operator: operator.value })
    currentHandover.value = res.data?.handover || null
    message.success('交班已提交，等待接班签收')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '提交失败'
  } finally {
    confirming.value = false
  }
}

async function onAcknowledge() {
  if (!currentHandover.value?.handover_id) return
  acknowledging.value = true
  error.value = ''
  try {
    const res = await acknowledgeHandover(currentHandover.value.handover_id, {
      operator: operator.value,
      forced_confirmations: forcedConfirmations.value,
    })
    currentHandover.value = res.data?.handover || null
    message.success('签收成功')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '签收失败'
  } finally {
    acknowledging.value = false
  }
}

async function onReject() {
  if (!currentHandover.value?.handover_id) return
  acknowledging.value = true
  try {
    const res = await rejectHandover(currentHandover.value.handover_id, {
      operator: operator.value,
      reason: '需修改后重新提交',
    })
    currentHandover.value = res.data?.handover || null
    message.info('已退回草稿')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '退回失败'
  } finally {
    acknowledging.value = false
  }
}

async function onViewBrief() {
  if (!currentHandover.value?.handover_id) return
  showBrief.value = !showBrief.value
  showEvidence.value = false
  showHistory.value = false
  if (showBrief.value) {
    try {
      const res = await getHandoverBrief(currentHandover.value.handover_id, 'full')
      briefData.value = res.data?.brief || { mode: 'full', blocks: [] }
    } catch (e: any) {
      error.value = e?.response?.data?.detail || '简报加载失败'
    }
  }
}

async function onViewHistory() {
  if (!activePatientId.value) return
  showHistory.value = !showHistory.value
  showBrief.value = false
  showEvidence.value = false
  if (showHistory.value) {
    await loadHistory()
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const res = await getPatientHandoverHistory(activePatientId.value, { limit: 20 })
    historyItems.value = res.data?.handovers || []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '历史加载失败'
  } finally {
    historyLoading.value = false
  }
}

async function loadForcedAlerts() {
  try {
    const res = await getForcedAlerts(activePatientId.value)
    forcedConfirmations.value = res.data?.forced_confirmations || []
  } catch {
    // Non-critical
  }
}

async function onSelectHistory(item: Record<string, any>) {
  currentHandover.value = item
  editableSections.value = JSON.parse(JSON.stringify(item.sections || {}))
}

function onSectionsUpdate(sections: Record<string, any>) {
  editableSections.value = sections
}

function onFieldEdit(fieldPath: string) {
  if (!editedFields.value.includes(fieldPath)) {
    editedFields.value.push(fieldPath)
  }
}

function onBriefModeChange(mode: string) {
  if (currentHandover.value?.handover_id) {
    getHandoverBrief(currentHandover.value.handover_id, mode as any).then((res) => {
      briefData.value = res.data?.brief || { mode, blocks: [] }
    })
  }
}

function initEmptySections(): Record<string, any> {
  return {
    identify: { bed: '', name: '', sex: '', age: '', admission_no: '', medical_group: '', special_tags: [] },
    situation: { diagnosis: '', surgery: '', post_op_day: '', icu_day: '', main_problems: '', life_support_level: '', life_support_changes: '' },
    background: { admission_course: '', past_history: '', isolation: '', allergies: '' },
    assessment: {
      neuro: { content: '', changes: '' }, resp: { content: '', changes: '' },
      circ: { content: '', changes: '' }, temp: { content: '', changes: '' },
      gi: { content: '', changes: '' }, heme: { content: '', changes: '' },
      specialty: { content: '', changes: '' }, nursing: { content: '', changes: '' },
      lines: { content: '', changes: '' }, skin: { content: '', changes: '' },
      items: { content: '' },
    },
    recommendation: { critical_first: [], tasks: [], pending: [], escalation: [] },
  }
}
</script>

<style scoped>
.handover-workbench {
  display: flex;
  height: calc(100vh - 56px);
  background: var(--bg-base);
  color: var(--text-main);
}

/* Sidebar */
.sidebar {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color, #334155);
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
}
.sidebar-header {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
}

/* Content */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: var(--text-secondary);
}
.placeholder-icon { font-size: 48px; margin-bottom: 12px; }
.placeholder-text { font-size: 16px; }

/* Toolbar */
.content-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: var(--bg-surface);
  border-radius: var(--card-radius);
  border: 1px solid var(--border-color, #334155);
}
.patient-banner {
  display: flex;
  align-items: center;
  gap: 10px;
}
.banner-bed {
  font-size: 14px;
  font-weight: 700;
  background: var(--accent);
  color: #fff;
  padding: 2px 10px;
  border-radius: 6px;
}
.banner-name { font-size: 15px; font-weight: 600; }
.banner-meta { font-size: 12px; color: var(--text-secondary); }
.toolbar-actions {
  display: flex;
  gap: 6px;
}

/* Body */
.content-body {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 16px;
  align-items: start;
}
.editor-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.panel-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 16px;
}

/* Submit bar */
.submit-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--bg-surface);
  border-radius: var(--card-radius);
  border: 1px solid var(--border-color, #334155);
}

@media (max-width: 1280px) {
  .content-body {
    grid-template-columns: 1fr;
  }
  .panel-col {
    position: static;
  }
}
</style>
