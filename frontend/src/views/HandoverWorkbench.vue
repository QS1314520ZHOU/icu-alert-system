<template>
  <div class="handover-workbench">
    <!-- Error banner -->
    <a-alert v-if="error" :message="error" type="error" closable @close="error = ''" style="margin-bottom: 12px" />

    <!-- Left sidebar: Patient list -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2 class="page-title">🩺 智能交接班</h2>
        <a-select
          v-if="!routeDeptCode"
          v-model:value="deptFilter"
          :options="deptOptions"
          size="small"
          placeholder="选择病区"
          style="width: 140px"
          @change="onDeptFilterChange"
        />
        <span v-else class="dept-locked">{{ deptOptions[0]?.label || routeDeptName || routeDeptCode }}</span>
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
            <div class="placeholder-sub">选择患者后，系统将自动带出身份与现况信息</div>
          </div>
        </template>

        <template v-else>
          <!-- Top toolbar -->
          <div class="content-toolbar">
            <div class="patient-banner">
              <span class="banner-bed">{{ currentHandover?.sections?.identify?.bed || activePatient?.bed || '?' }}床</span>
              <span class="banner-name">{{ currentHandover?.sections?.identify?.name || activePatient?.name || '未选择患者' }}</span>
              <span v-if="activePatient?.has_critical" class="banner-badge banner-critical">⚠️ {{ activePatient.critical_count }}</span>
              <span v-if="activePatient?.diagnosis" class="banner-diagnosis">{{ activePatient.diagnosis }}</span>
              <span class="banner-meta">{{ editableSections?.identify?.admission_no || activePatient?.raw?.mrn || activePatient?.raw?.hisPid || '' }}</span>
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
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
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
import { getPatients, getDepartments, getRecentAlerts } from '../api'

// ── Types ────────────────────────────────────────────────────────────

interface PatientBrief {
  patient_id: string
  bed: string
  name: string
  diagnosis: string
  has_draft: boolean
  status: string
  has_critical: boolean
  critical_count: number
  raw?: any
}

// ── Route ─────────────────────────────────────────────────────────────

const route = useRoute()

const routeDeptCode = computed(() => {
  const raw = route.query.dept_code || route.query.deptCode
  if (Array.isArray(raw)) return raw[0]?.trim() ?? ''
  if (typeof raw === 'string') return raw.trim()
  return ''
})

const routeDeptName = computed(() => {
  const raw = route.query.dept
  if (Array.isArray(raw)) return raw[0]?.trim() ?? ''
  if (typeof raw === 'string') return raw.trim()
  return ''
})

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
const activePatient = ref<PatientBrief | null>(null)
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

const patientBriefs = ref<PatientBrief[]>([])
const deptOptions = ref<Array<{ label: string; value: string }>>([
  { label: '全部病区', value: '' },
])

let requestToken = 0

function effectiveDeptCode(): string | undefined {
  return (deptFilter.value || routeDeptCode.value) || undefined
}

// ── Data Loading ──────────────────────────────────────────────────────

async function loadDepartments() {
  try {
    const res = await getDepartments()
    const departments: Array<{ dept: string; deptCode: string; patientCount: number }> =
      res.data?.departments || []

    if (routeDeptCode.value) {
      const match = departments.find((d) => d.deptCode === routeDeptCode.value)
      const label = match?.dept || routeDeptName.value || routeDeptCode.value
      deptOptions.value = [{ label, value: routeDeptCode.value }]
      deptFilter.value = routeDeptCode.value
    } else {
      deptOptions.value = [
        { label: '全部病区', value: '' },
        ...departments.map((d) => ({ label: d.dept, value: d.deptCode })),
      ]
      deptFilter.value = ''
    }
  } catch {
    if (routeDeptCode.value) {
      deptOptions.value = [{ label: routeDeptName.value || routeDeptCode.value, value: routeDeptCode.value }]
      deptFilter.value = routeDeptCode.value
    }
  }
}

async function loadPatients() {
  const token = ++requestToken
  patientsLoading.value = true

  try {
    const res = await getPatients({
      dept_code: effectiveDeptCode(),
      dept: routeDeptName.value || undefined,
      patient_scope: 'in_dept',
    })
    if (token !== requestToken) return

    const list: any[] = res.data?.patients || []

    patientBriefs.value = list.map((p: any) => ({
      patient_id: String(p._id),
      bed: String(p.hisBed || p.bed || ''),
      name: String(p.name || ''),
      diagnosis: String(p.diagnosis || ''),
      has_draft: false,
      status: '',
      critical_count: Array.isArray(p.clinicalTags) ? p.clinicalTags.length : 0,
      has_critical: Array.isArray(p.clinicalTags) && p.clinicalTags.length > 0,
      raw: p,
    }))

    patientsLoading.value = false

    // Fire async hydration (don't await — render first, enrich later)
    hydrateCriticalAlerts(token)
    hydrateHandoverStatus(token)
  } catch {
    if (token === requestToken) {
      patientsLoading.value = false
    }
  }
}

async function hydrateCriticalAlerts(token: number) {
  try {
    const res = await getRecentAlerts(200, {
      dept_code: effectiveDeptCode(),
      dept: routeDeptName.value || undefined,
      pending: true,
    })
    if (token !== requestToken) return

    const records: any[] = res.data?.records || []
    const criticalMap = new Map<string, number>()
    for (const r of records) {
      const sev = String(r.severity || '').toLowerCase()
      if (sev === 'critical' || sev === 'high') {
        const pid = String(r.patient_id || '')
        criticalMap.set(pid, (criticalMap.get(pid) || 0) + 1)
      }
    }

    patientBriefs.value = patientBriefs.value.map((p) => {
      const count = criticalMap.get(p.patient_id) || 0
      return { ...p, critical_count: count, has_critical: count > 0 }
    })
  } catch {
    // Keep the fallback values from loadPatients
  }
}

async function hydrateHandoverStatus(token: number) {
  const statusMap = new Map<string, { status: string; has_draft: boolean }>()

  for (let i = 0; i < patientBriefs.value.length; i += 8) {
    if (token !== requestToken) return
    const batch = patientBriefs.value.slice(i, i + 8)

    await Promise.all(
      batch.map(async (p) => {
        try {
          const res = await getPatientHandoverHistory(p.patient_id, { limit: 1 })
          const latest = (res.data?.handovers || [])[0]
          if (latest) {
            const st = String(latest.status || '')
            statusMap.set(p.patient_id, { status: st, has_draft: st === 'draft' })
          }
        } catch {
          // Skip this patient
        }
      })
    )
  }

  if (token !== requestToken) return

  // Merge into current patientBriefs (preserves critical alert counts from hydrateCriticalAlerts)
  patientBriefs.value = patientBriefs.value.map((p) => {
    const s = statusMap.get(p.patient_id)
    return s ? { ...p, status: s.status, has_draft: s.has_draft } : p
  })
}

function onDeptFilterChange() {
  loadPatients()
}

// ── Lifecycle ─────────────────────────────────────────────────────────

onMounted(() => {
  loadDepartments() // sets deptFilter internally based on routeDeptCode
  if (!routeDeptCode.value) {
    deptFilter.value = ''
  }
  loadPatients()
})

watch(
  () => [routeDeptCode.value, routeDeptName.value],
  () => {
    loadPatients()
  }
)

// ── Actions ──────────────────────────────────────────────────────────

async function onSelectPatient(patient: any) {
  activePatientId.value = patient.patient_id || patient._id
  activePatient.value = patient
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
      const loaded = JSON.parse(JSON.stringify((list[0] as any).sections || {}))
      editableSections.value = mergePatientFacts(loaded, activePatient.value?.raw)
    } else {
      currentHandover.value = null
      editableSections.value = prefillSectionsFromPatient(activePatient.value?.raw)
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
    editableSections.value = mergePatientFacts(
      JSON.parse(JSON.stringify(currentHandover.value?.sections || {})),
      activePatient.value?.raw
    )
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

function mergePatientFacts(sections: Record<string, any>, raw: any): Record<string, any> {
  if (!raw) return sections
  const s = JSON.parse(JSON.stringify(sections || {}))
  s.identify = s.identify || {}
  s.situation = s.situation || {}
  const fill = (obj: any, key: string, val: any) => {
    const cur = obj[key]
    const empty = cur == null || cur === '' || (Array.isArray(cur) && cur.length === 0)
    if (empty && val != null && val !== '') obj[key] = val
  }
  fill(s.identify, 'bed', String(raw.hisBed || raw.bed || ''))
  fill(s.identify, 'name', String(raw.name || ''))
  fill(s.identify, 'sex', raw.gender === 'Male' ? '男' : raw.gender === 'Female' ? '女' : String(raw.sex || ''))
  fill(s.identify, 'age', String(raw.age || ''))
  fill(s.identify, 'admission_no', String(raw.mrn || raw.hisPid || ''))
  fill(s.identify, 'medical_group', String(raw.medicalGroup || ''))
  if (Array.isArray(raw.clinicalTags) && raw.clinicalTags.length) {
    const tags = raw.clinicalTags.map((t: any) => typeof t === 'string' ? t : (t?.label || '')).filter(Boolean)
    fill(s.identify, 'special_tags', tags)
  }
  fill(s.situation, 'diagnosis', String(raw.diagnosis || ''))
  fill(s.situation, 'surgery', raw.patientOperations?.[0]?.name || '')
  if (raw.icuAdmissionTime)
    fill(s.situation, 'icu_day', String(Math.max(0, Math.floor((Date.now() - new Date(raw.icuAdmissionTime).getTime()) / 86400000))))
  if (raw.patientOperations?.[0]?.endTime)
    fill(s.situation, 'post_op_day', String(Math.max(0, Math.floor((Date.now() - new Date(raw.patientOperations[0].endTime).getTime()) / 86400000))))
  return s
}

function prefillSectionsFromPatient(raw: any): Record<string, any> {
  const sections = initEmptySections()
  if (!raw) return sections

  const s = sections
  s.identify.bed = String(raw.hisBed || raw.bed || '')
  s.identify.name = String(raw.name || '')
  s.identify.sex = raw.gender === 'Male' ? '男' : raw.gender === 'Female' ? '女' : String(raw.sex || '')
  s.identify.age = String(raw.age || '')
  s.identify.admission_no = String(raw.mrn || raw.hisPid || '')
  s.identify.medical_group = String(raw.medicalGroup || '')
  s.identify.special_tags = Array.isArray(raw.clinicalTags)
    ? raw.clinicalTags.map((t: any) => (typeof t === 'string' ? t : t?.label || '')).filter(Boolean)
    : []
  s.situation.diagnosis = String(raw.diagnosis || '')
  s.situation.surgery = raw.patientOperations?.[0]?.name || ''
  if (raw.icuAdmissionTime) {
    const days = Math.max(0, Math.floor((Date.now() - new Date(raw.icuAdmissionTime).getTime()) / 86400000))
    s.situation.icu_day = String(days)
  }
  if (raw.patientOperations?.[0]?.endTime) {
    const pod = Math.max(0, Math.floor((Date.now() - new Date(raw.patientOperations[0].endTime).getTime()) / 86400000))
    s.situation.post_op_day = String(pod)
  }
  s.background.past_history = String(raw.pastHistory || '')
  s.background.isolation = String(raw.isolation || '')
  s.background.allergies = String(raw.allergic || '')

  return sections
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

/* ── Sidebar ──────────────────────────────────────────────── */
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
.dept-locked {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  padding: 4px 8px;
  background: rgba(56, 189, 248, 0.08);
  border-radius: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Content ──────────────────────────────────────────────── */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

/* Empty state */
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 500px;
  color: var(--text-secondary);
}
.placeholder-icon {
  font-size: 72px;
  margin-bottom: 20px;
  opacity: 0.6;
}
.placeholder-text {
  font-size: 17px;
  font-weight: 500;
}
.placeholder-sub {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 8px;
  opacity: 0.75;
}

/* ── Toolbar / Banner ─────────────────────────────────────── */
.content-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 12px 20px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.patient-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.banner-bed {
  font-size: 14px;
  font-weight: 700;
  background: var(--accent);
  color: #fff;
  padding: 3px 12px;
  border-radius: 8px;
  white-space: nowrap;
}
.banner-name { font-size: 15px; font-weight: 600; }
.banner-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}
.banner-critical { background: #fef2f2; color: #dc2626; }
.banner-diagnosis {
  font-size: 12px;
  color: var(--text-secondary);
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.banner-meta { font-size: 12px; color: var(--text-secondary); }
.toolbar-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* ── Two-column body ──────────────────────────────────────── */
.content-body {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 16px;
  align-items: start;
}
.editor-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 20px;
}

/* ── ISBAR Section Cards ──────────────────────────────────── */
.editor-col :deep(.ant-collapse) {
  background: transparent;
  border: none;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.editor-col :deep(.ant-collapse-item) {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  border: none;
  overflow: hidden;
}
.editor-col :deep(.ant-collapse-header) {
  font-size: 14px;
  font-weight: 600;
  padding: 14px 18px;
  border-left: 4px solid var(--accent);
  background: #fafbfc;
  align-items: center;
}
.editor-col :deep(.ant-collapse-content) {
  border-top: 1px solid #f0f0f0;
}
.editor-col :deep(.ant-collapse-content-box) {
  padding: 16px 18px;
}

/* ── Form fields inside ISBAR ──────────────────────────────── */
.editor-col :deep(.field-row) {
  margin-bottom: 12px;
}
.editor-col :deep(.field-row label) {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
  display: block;
  margin-bottom: 4px;
}
.editor-col :deep(.ant-input),
.editor-col :deep(.ant-select-selector),
.editor-col :deep(textarea.ant-input) {
  border-radius: 6px;
  border-color: #e2e8f0;
  transition: border-color 0.2s;
}
.editor-col :deep(.ant-input:focus),
.editor-col :deep(textarea.ant-input:focus),
.editor-col :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.12);
}

/* ── Section grid ─────────────────────────────────────────── */
.editor-col :deep(.section-grid.two-col) {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 20px;
}

/* ── Submit bar ───────────────────────────────────────────── */
.submit-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

/* ── Panel cards ──────────────────────────────────────────── */
.panel-col :deep(.ant-card),
.panel-col :deep(> div) {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.panel-col :deep(.ant-alert) {
  border-radius: 10px;
}
.panel-col :deep(.ant-alert-error) {
  border-left: 4px solid #dc2626;
}
.panel-col :deep(.ant-alert-warning) {
  border-left: 4px solid #f59e0b;
}

/* ── Responsive ───────────────────────────────────────────── */
@media (max-width: 1100px) {
  .content-body {
    grid-template-columns: 1fr;
  }
  .panel-col {
    position: static;
  }
  .editor-col :deep(.section-grid.two-col) {
    grid-template-columns: 1fr;
  }
}
</style>
