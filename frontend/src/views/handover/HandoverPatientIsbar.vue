<template>
  <div class="isbar-page">
    <!-- Left: Patient list -->
    <aside class="isbar-sidebar">
      <div class="sidebar-search">
        <a-input v-model:value="searchText" placeholder="搜索患者..." size="small" allow-clear />
      </div>
      <div class="patient-list">
        <div
          v-for="p in filteredPatients"
          :key="p.patient_id"
          class="patient-item"
          :class="{ 'patient-item--active': p.patient_id === activePatientId }"
          @click="selectPatient(p)"
        >
          <span class="patient-bed">{{ p.bed }}床</span>
          <span class="patient-name">{{ p.name }}</span>
          <span v-if="p.is_critical" class="patient-badge patient-badge--critical">危</span>
          <span v-if="p.has_ventilator" class="patient-badge patient-badge--vent">V</span>
        </div>
      </div>
    </aside>

    <!-- Center: ISBAR editor -->
    <main class="isbar-main">
      <a-spin :spinning="loading">
        <template v-if="!activePatientId">
          <div class="empty-hint">
            <p>👈 请从左侧选择患者</p>
          </div>
        </template>
        <template v-else>
          <!-- Toolbar -->
          <div class="isbar-toolbar">
            <div class="toolbar-patient">
              <span class="toolbar-bed">{{ currentHandover?.sections?.identify?.bed || '?' }}床</span>
              <span class="toolbar-name">{{ currentHandover?.sections?.identify?.name || '未知' }}</span>
              <a-tag v-if="currentHandover?.ai_status?.status === 'unavailable'" color="orange">AI不可用</a-tag>
              <a-tag v-else-if="currentHandover?.ai_status?.status === 'success'" color="blue">AI已生成</a-tag>
            </div>
            <div class="toolbar-actions">
              <a-button size="small" :loading="generating" @click="onGenerate">生成草稿</a-button>
              <a-button size="small" :loading="saving" @click="onSave">保存</a-button>
              <a-button size="small" type="primary" :disabled="!canSubmit" :loading="submitting" @click="onSubmit">提交</a-button>
            </div>
          </div>

          <!-- AI status banner -->
          <a-alert
            v-if="currentHandover?.ai_status?.status === 'unavailable'"
            message="已生成系统预填草稿，AI摘要暂不可用，请人工补充。"
            type="warning"
            show-icon
            :banner="true"
            style="margin-bottom: 12px"
          />

          <!-- ISBAR Editor -->
          <IsbarEditor
            v-if="currentHandover"
            :sections="editableSections"
            :ai-generated-fields="currentHandover.ai_generated_fields || []"
            :content-sources="currentHandover.content_sources || {}"
            :status="currentHandover.status"
            @update:sections="onSectionsUpdate"
            @field-edit="onFieldEdit"
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
            style="margin-top: 12px"
          />
        </template>
      </a-spin>
    </main>

    <!-- Right: Evidence & diagnostics -->
    <aside class="isbar-evidence" :class="{ 'isbar-evidence--collapsed': !showEvidence }">
      <div class="evidence-toggle" @click="showEvidence = !showEvidence">
        {{ showEvidence ? '收起' : '数据' }}
      </div>
      <template v-if="showEvidence">
        <a-tabs size="small" v-model:activeKey="evidenceTab">
          <a-tab-pane key="evidence" tab="证据">
            <HandoverEvidencePanel :items="currentHandover?.evidence || []" />
          </a-tab-pane>
          <a-tab-pane key="sources" tab="数据源">
            <DataCompleteness :items="completenessItems" />
          </a-tab-pane>
          <a-tab-pane key="diagnostic" tab="诊断">
            <div class="diagnostic-content">
              <p v-if="diagnosticLoading">加载中...</p>
              <template v-else-if="diagnostic">
                <div class="diag-item">
                  <span class="diag-label">患者匹配：</span>
                  <span :class="diagnostic.identity_resolution?.matched ? 'diag-ok' : 'diag-fail'">
                    {{ diagnostic.identity_resolution?.matched ? '是' : '否' }}
                  </span>
                </div>
                <div class="diag-item">
                  <span class="diag-label">班次：</span>
                  <span>{{ diagnostic.shift?.name || '-' }}</span>
                </div>
                <div v-for="(src, key) in diagnostic.sources" :key="key" class="diag-item">
                  <span class="diag-label">{{ key }}：</span>
                  <span :class="src.status === 'available' ? 'diag-ok' : src.status === 'failed' ? 'diag-fail' : 'diag-warn'">
                    {{ src.status }} ({{ src.count }}条)
                  </span>
                </div>
              </template>
              <p v-else class="diag-hint">选择患者后自动加载诊断</p>
            </div>
          </a-tab-pane>
        </a-tabs>
      </template>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Spin as ASpin, Button as AButton, Input as AInput, Tag as ATag, Alert as AAlert, Tabs as ATabs, TabPane as ATabPane, message } from 'ant-design-vue'
import { useAuthStore } from '../../stores/auth'
import api from '../../api'
import {
  generateHandover,
  getPatientHandoverHistory,
  updateHandoverContent,
  confirmHandover,
  acknowledgeHandover,
  rejectHandover,
} from '../../api/handover'
import IsbarEditor from '../../components/handover/IsbarEditor.vue'
import HandoverEvidencePanel from '../../components/handover/HandoverEvidencePanel.vue'
import AcknowledgementPanel from '../../components/handover/AcknowledgementPanel.vue'
import { DataCompleteness } from '../../components/handover/charts'

const route = useRoute()
const authStore = useAuthStore()

// State
const loading = ref(false)
const generating = ref(false)
const saving = ref(false)
const submitting = ref(false)
const acknowledging = ref(false)
const diagnosticLoading = ref(false)
const searchText = ref('')
const showEvidence = ref(true)
const evidenceTab = ref('evidence')

const patients = ref<any[]>([])
const activePatientId = ref('')
const currentHandover = ref<any>(null)
const editableSections = ref<any>({})
const editedFields = ref<string[]>([])
const forcedConfirmations = ref<any[]>([])
const diagnostic = ref<any>(null)

const deptCode = computed(() => authStore.deptCode || (route.query.dept_code as string) || '')

const filteredPatients = computed(() => {
  const q = searchText.value.toLowerCase()
  if (!q) return patients.value
  return patients.value.filter(p =>
    (p.name || '').toLowerCase().includes(q) ||
    (p.bed || '').includes(q)
  )
})

const canSubmit = computed(() =>
  currentHandover.value?.status === 'draft' && authStore.effectiveUserId
)

const completenessItems = computed(() => {
  if (!diagnostic.value?.sources) return []
  const src = diagnostic.value.sources
  const labels: Record<string, string> = {
    vitals: '生命体征', labs: '检验', io: '出入量', medications: '用药',
    ventilator: '呼吸机', lines: '管路', assessments: '评估',
    events: '护理事件', orders: '医嘱', alerts: '告警',
  }
  return Object.entries(src).map(([key, val]: [string, any]) => ({
    label: labels[key] || key,
    status: val.status || 'empty',
    count: val.count || 0,
    source: val.source || '',
  }))
})

// Load patients
async function loadPatients() {
  try {
    const res = await api.get('/api/patients', { params: { dept_code: deptCode.value, patient_scope: 'in_dept' } })
    patients.value = res.data?.patients || []
  } catch (e: any) {
    console.error('Failed to load patients:', e)
  }
}

// Select patient
async function selectPatient(p: any) {
  activePatientId.value = p.patient_id || p._id || ''
  if (!activePatientId.value) return

  loading.value = true
  try {
    // Load handover history
    const histRes = await getPatientHandoverHistory(activePatientId.value, { limit: 1 })
    const handovers = histRes.data?.handovers || []
    if (handovers.length > 0) {
      currentHandover.value = handovers[0]!
      editableSections.value = structuredClone(handovers[0]!.sections || {})
    } else {
      currentHandover.value = null
      editableSections.value = {}
    }

    // Load diagnostic
    loadDiagnostic()
  } catch (e: any) {
    console.error('Failed to load patient handover:', e)
  } finally {
    loading.value = false
  }
}

// Load diagnostic
async function loadDiagnostic() {
  if (!activePatientId.value) return
  diagnosticLoading.value = true
  try {
    const res = await api.get(`/api/handover/patients/${activePatientId.value}/context-preview`, {
      params: { dept_code: deptCode.value }
    })
    diagnostic.value = res.data || null
  } catch (e) {
    diagnostic.value = null
  } finally {
    diagnosticLoading.value = false
  }
}

// Generate
async function onGenerate() {
  if (!activePatientId.value) return
  generating.value = true
  try {
    const res = await generateHandover({ patient_id: activePatientId.value })
    currentHandover.value = res.data?.handover || null
    editableSections.value = structuredClone(currentHandover.value?.sections || {})

    if (currentHandover.value?.ai_status?.status === 'unavailable') {
      message.warning('AI暂不可用，已生成系统预填草稿')
    } else {
      message.success('草稿已生成')
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

// Save
async function onSave() {
  if (!currentHandover.value?.handover_id) return
  saving.value = true
  try {
    const res = await updateHandoverContent(currentHandover.value.handover_id, {
      sections: editableSections.value,
      edited_fields: editedFields.value,
    })
    currentHandover.value = res.data?.handover || null
    editedFields.value = []
    message.success('已保存')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// Submit
async function onSubmit() {
  if (!currentHandover.value?.handover_id) return
  submitting.value = true
  try {
    await onSave()
    const res = await confirmHandover(currentHandover.value.handover_id, {
      operator: authStore.effectiveUserId || '',
    })
    currentHandover.value = res.data?.handover || null
    message.success('已提交，等待签收')
  } catch (e: any) {
    message.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

// Acknowledge
async function onAcknowledge() {
  if (!currentHandover.value?.handover_id) return
  acknowledging.value = true
  try {
    const res = await acknowledgeHandover(currentHandover.value.handover_id, {
      operator: authStore.effectiveUserId || '',
      forced_confirmations: forcedConfirmations.value,
    })
    currentHandover.value = res.data?.handover || null
    message.success('签收成功')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '签收失败')
  } finally {
    acknowledging.value = false
  }
}

// Reject
async function onReject() {
  if (!currentHandover.value?.handover_id) return
  acknowledging.value = true
  try {
    const res = await rejectHandover(currentHandover.value.handover_id, {
      operator: authStore.effectiveUserId || '',
      reason: '需修改后重新提交',
    })
    currentHandover.value = res.data?.handover || null
    message.info('已退回草稿')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '退回失败')
  } finally {
    acknowledging.value = false
  }
}

function onSectionsUpdate(sections: any) {
  editableSections.value = sections
}

function onFieldEdit(fieldPath: string) {
  if (!editedFields.value.includes(fieldPath)) {
    editedFields.value.push(fieldPath)
  }
}

onMounted(() => {
  loadPatients()
})
</script>

<style scoped>
.isbar-page {
  display: grid;
  grid-template-columns: 240px 1fr 300px;
  height: 100%;
  overflow: hidden;
}

/* Left sidebar */
.isbar-sidebar {
  border-right: 1px solid #DCE5EF;
  background: #F9FAFB;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-search { padding: 12px; border-bottom: 1px solid #DCE5EF; }
.patient-list { flex: 1; overflow-y: auto; }
.patient-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; cursor: pointer; border-bottom: 1px solid #F0F3F7;
  font-size: 13px;
}
.patient-item:hover { background: #E6F4FF; }
.patient-item--active { background: #E6F4FF; border-left: 3px solid #1677FF; }
.patient-bed { font-weight: 600; color: #17233D; min-width: 32px; }
.patient-name { flex: 1; color: #5F6B7A; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.patient-badge { font-size: 10px; padding: 1px 4px; border-radius: 3px; font-weight: 600; }
.patient-badge--critical { background: #FEF3F2; color: #D92D20; }
.patient-badge--vent { background: #E6F4FF; color: #2E90FA; }

/* Main editor */
.isbar-main {
  overflow-y: auto;
  padding: 16px;
}
.empty-hint {
  text-align: center;
  padding: 80px 0;
  color: #8A94A6;
  font-size: 16px;
}
.isbar-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-patient { display: flex; align-items: center; gap: 8px; }
.toolbar-bed { font-size: 16px; font-weight: 600; color: #17233D; }
.toolbar-name { font-size: 14px; color: #5F6B7A; }
.toolbar-actions { display: flex; gap: 8px; }

/* Right evidence panel */
.isbar-evidence {
  border-left: 1px solid #DCE5EF;
  background: #F9FAFB;
  overflow-y: auto;
  position: relative;
}
.isbar-evidence--collapsed { width: 40px; }
.evidence-toggle {
  position: absolute; top: 8px; right: 8px; z-index: 1;
  font-size: 11px; color: #2E90FA; cursor: pointer; padding: 2px 6px;
  background: #E6F4FF; border-radius: 4px;
}

.diagnostic-content { padding: 8px; font-size: 12px; }
.diag-item { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #F0F3F7; }
.diag-label { color: #5F6B7A; }
.diag-ok { color: #12A66A; font-weight: 500; }
.diag-warn { color: #F79009; font-weight: 500; }
.diag-fail { color: #D92D20; font-weight: 500; }
.diag-hint { color: #8A94A6; text-align: center; padding: 20px 0; }

@media (max-width: 1024px) {
  .isbar-page { grid-template-columns: 1fr; }
  .isbar-sidebar { display: none; }
  .isbar-evidence { position: fixed; bottom: 0; left: 0; right: 0; height: 50vh; z-index: 100; border-top: 1px solid #DCE5EF; }
}
</style>
