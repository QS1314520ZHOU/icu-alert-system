<template>
  <div class="document-workbench">
    <!-- Header toolbar -->
    <header class="dw-header">
      <div class="dw-header-left">
        <span class="dw-header-icon">📝</span>
        <span class="dw-header-title">病历文书工作台</span>
      </div>
      <div class="dw-header-actions">
        <a-select v-model:value="hours" size="small" class="dw-hours-select">
          <a-select-option :value="12">过去12小时</a-select-option>
          <a-select-option :value="24">过去24小时</a-select-option>
          <a-select-option :value="48">过去48小时</a-select-option>
        </a-select>
        <a-button type="primary" :loading="generating" @click="handleGenerate">
          ✨ AI生成
        </a-button>
        <a-button :disabled="!draft" @click="handleSave" :loading="saving">
          {{ dirty ? '保存修改' : '保存草稿' }}
        </a-button>
        <a-button :disabled="!draftId" @click="handleExport" :loading="exporting">
          导出DOCX
        </a-button>
        <a-button type="primary" :disabled="!draft || finalized" @click="handleFinalize" class="dw-finalize-btn">
          {{ finalized ? '已签署' : '签署定稿' }}
        </a-button>
      </div>
    </header>

    <!-- Hallucination warnings -->
    <HallucinationWarning
      v-if="warnings.length"
      :warnings="warnings"
    />

    <!-- Draft history dropdown -->
    <div v-if="draftHistory.length" class="dw-history-bar">
      <span class="dw-history-label">历史草稿 ({{ draftHistory.length }})</span>
      <a-select
        v-model:value="selectedHistoryId"
        placeholder="选择历史草稿"
        size="small"
        class="dw-history-select"
        allow-clear
        @change="loadHistoryDraft"
      >
        <a-select-option v-for="h in draftHistory" :key="h.draft_id" :value="h.draft_id">
          {{ formatTime(h.created_at) }} — {{ h.status }}
        </a-select-option>
      </a-select>
      <a-select
        v-if="versions.length"
        v-model:value="selectedVersionNo"
        placeholder="版本回看"
        size="small"
        class="dw-version-select"
        allow-clear
        :disabled="finalized"
        @change="restoreVersion"
      >
        <a-select-option v-for="v in versions" :key="v.version_no" :value="v.version_no">
          v{{ v.version_no }} - {{ formatTime(v.modified_at) }}
        </a-select-option>
      </a-select>
      <span v-if="dirty" class="dw-dirty">有未保存修改</span>
      <span v-else-if="draft" class="dw-saved">已保存</span>
    </div>

    <!-- Three-panel body -->
    <div class="dw-body">
      <aside class="dw-left">
        <ContextPreview :context="contextSnapshot" />
      </aside>

      <main class="dw-center">
        <ProgressNoteEditor
          v-if="draft"
          :draft="draft"
          :citations="citations"
          :readonly="finalized"
          @update:draft="onDraftUpdate"
          @section-focus="onSectionFocus"
        />
        <div v-else class="dw-empty">
          <div class="dw-empty-icon">📄</div>
          <div class="dw-empty-title">点击「AI生成」开始撰写病程记录</div>
          <div class="dw-empty-hint">AI 将基于过去{{ hours }}小时的临床数据自动生成 SOAP 格式病程记录</div>
        </div>
      </main>

      <aside class="dw-right">
        <CitationPanel
          :citations="focusedCitations"
          :context="contextSnapshot"
        />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  Button as AButton,
  Modal as AModal,
  Select as ASelect,
  SelectOption as ASelectOption,
  message,
} from 'ant-design-vue'
import {
  generateProgressNote,
  getDraft,
  updateDraft,
  finalizeDraft,
  listPatientDrafts,
  listDraftVersions,
  exportDraft,
  type DraftContent,
  type Citation,
  type DraftVersion,
} from '../../api/clinicalDocuments'
import HallucinationWarning from './HallucinationWarning.vue'
import ContextPreview from './ContextPreview.vue'
import ProgressNoteEditor from './ProgressNoteEditor.vue'
import CitationPanel from './CitationPanel.vue'

const props = defineProps<{ patientId: string }>()

const hours = ref(24)
const generating = ref(false)
const saving = ref(false)
const exporting = ref(false)
const finalized = ref(false)
const dirty = ref(false)
const draftId = ref('')
const draft = ref<DraftContent | null>(null)
const citations = ref<Citation[]>([])
const warnings = ref<string[]>([])
const contextSnapshot = ref<any>(null)
const focusedSection = ref('')
const draftHistory = ref<any[]>([])
const selectedHistoryId = ref<string | undefined>(undefined)
const versions = ref<DraftVersion[]>([])
const selectedVersionNo = ref<number | undefined>(undefined)

const focusedCitations = computed(() => {
  if (!focusedSection.value || !draft.value) return citations.value
  const sectionData = (draft.value as any)[focusedSection.value]
  if (!sectionData) return citations.value
  const text = typeof sectionData === 'string' ? sectionData : JSON.stringify(sectionData)
  return citations.value.filter((c: Citation) => text.includes(`[${c.ref}]`))
})

onMounted(async () => {
  await loadDraftHistory()
})

async function loadDraftHistory() {
  try {
    const { data } = await listPatientDrafts(props.patientId)
    draftHistory.value = data.items || []
    if (!draft.value && draftHistory.value.length) {
      const latest = draftHistory.value[0]
      selectedHistoryId.value = latest?.draft_id
      if (selectedHistoryId.value) await loadHistoryDraft(selectedHistoryId.value)
    }
  } catch {
    // ignore
  }
}

async function loadHistoryDraft(id: any) {
  if (!id) return
  const idStr = String(id)
  try {
    const { data } = await getDraft(idStr)
    draftId.value = id
    draft.value = data.draft || (data as any).current_content
    citations.value = data.citations || []
    warnings.value = data.hallucination_warnings || []
    contextSnapshot.value = data.context_snapshot
    finalized.value = (data as any).status === 'finalized'
    dirty.value = false
    selectedVersionNo.value = undefined
    await loadVersions()
  } catch {
    message.error('加载草稿失败')
  }
}

async function loadVersions() {
  if (!draftId.value) {
    versions.value = []
    return
  }
  try {
    const { data } = await listDraftVersions(draftId.value)
    versions.value = data.versions || []
  } catch {
    versions.value = []
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    const { data } = await generateProgressNote({
      patient_id: props.patientId,
      hours: hours.value,
    })
    draftId.value = data.draft_id
    draft.value = data.draft
    citations.value = data.citations
    warnings.value = data.hallucination_warnings
    contextSnapshot.value = data.context_snapshot
    finalized.value = false
    dirty.value = false
    selectedHistoryId.value = data.draft_id
    selectedVersionNo.value = undefined
    versions.value = []
    message.success('AI 病程记录生成完成')
    await loadDraftHistory()
  } catch (err: any) {
    message.error(`生成失败: ${err?.response?.data?.detail || err.message || '未知错误'}`)
  } finally {
    generating.value = false
  }
}

async function handleSave() {
  if (!draft.value || !draftId.value) return
  saving.value = true
  try {
    await updateDraft(draftId.value, draft.value)
    dirty.value = false
    message.success('草稿已保存')
    await loadVersions()
    await loadDraftHistory()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleFinalize() {
  if (!draftId.value) return
  AModal.confirm({
    title: '签署确认',
    content: '定稿后内容不可修改，是否确认签署？',
    okText: '确认签署',
    cancelText: '取消',
    async onOk() {
      try {
        if (dirty.value && draft.value) {
          await updateDraft(draftId.value, draft.value)
          dirty.value = false
        }
        await finalizeDraft(draftId.value, '当前医生')
        finalized.value = true
        message.success('已签署定稿')
        await loadDraftHistory()
      } catch {
        message.error('签署失败')
      }
    },
  })
}

function onDraftUpdate(d: DraftContent) {
  draft.value = d
  dirty.value = true
}

function restoreVersion(versionNo: any) {
  if (!versionNo) return
  const found = versions.value.find((v) => v.version_no === Number(versionNo))
  if (!found) return
  draft.value = JSON.parse(JSON.stringify(found.content || {}))
  dirty.value = true
  message.info(`已载入 v${found.version_no}，保存后生效`)
}

async function handleExport() {
  if (!draftId.value) return
  exporting.value = true
  try {
    const { data } = await exportDraft(draftId.value, 'docx')
    const blob = data instanceof Blob ? data : new Blob([data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `ProgressNote_${props.patientId}_${new Date().toISOString().slice(0, 10)}.docx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch {
    message.error('导出失败')
  } finally {
    exporting.value = false
  }
}

function onSectionFocus(section: string) {
  focusedSection.value = section
}

function formatTime(raw: any): string {
  if (!raw) return '—'
  try {
    const d = new Date(raw)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return String(raw)
  }
}
</script>

<style scoped>
.document-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 600px;
  background: #f5f5f5;
  border-radius: 8px;
  overflow: hidden;
}

/* Header */
.dw-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}
.dw-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dw-header-icon { font-size: 20px; }
.dw-header-title {
  font-weight: 600;
  font-size: 16px;
}
.dw-header-patient {
  font-size: 12px;
  color: #8c8c8c;
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 4px;
}
.dw-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dw-hours-select {
  width: 130px;
}
.dw-finalize-btn {
  background: #52c41a !important;
  border-color: #52c41a !important;
}
.dw-finalize-btn:disabled {
  background: #d9d9d9 !important;
  border-color: #d9d9d9 !important;
}

/* History bar */
.dw-history-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}
.dw-history-label {
  font-size: 12px;
  color: #595959;
  white-space: nowrap;
}
.dw-history-select {
  width: 240px;
}
.dw-version-select {
  width: 180px;
}
.dw-dirty,
.dw-saved {
  font-size: 12px;
  white-space: nowrap;
}
.dw-dirty {
  color: #d48806;
}
.dw-saved {
  color: #52c41a;
}

/* Three-panel body */
.dw-body {
  display: grid;
  grid-template-columns: 260px 1fr 260px;
  flex: 1;
  overflow: hidden;
}
.dw-left, .dw-right {
  overflow-y: auto;
  padding: 12px;
  background: #fff;
  border-right: 1px solid #f0f0f0;
}
.dw-right {
  border-right: none;
  border-left: 1px solid #f0f0f0;
}
.dw-center {
  padding: 16px;
  overflow-y: auto;
  background: #fafafa;
}

/* Empty state */
.dw-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: #bfbfbf;
}
.dw-empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}
.dw-empty-title {
  font-size: 16px;
  font-weight: 500;
  color: #8c8c8c;
  margin-bottom: 8px;
}
.dw-empty-hint {
  font-size: 13px;
  color: #bfbfbf;
}

/* ================= Dark Theme Overrides ================= */
:global(.theme-dark) .document-workbench {
  background: #07111d;
  color: #d9e6f3;
}
:global(.theme-dark) .dw-header {
  background: #0d1a2b;
  border-bottom: 1px solid rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .dw-header-title {
  color: #d9e6f3;
}
:global(.theme-dark) .dw-header-patient {
  color: #7f93ab;
  background: #07111d;
}
:global(.theme-dark) .dw-history-bar {
  background: #0d1a2b;
  border-bottom: 1px solid rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .dw-history-label {
  color: #7f93ab;
}
:global(.theme-dark) .dw-dirty {
  color: #fbbf24;
}
:global(.theme-dark) .dw-saved {
  color: #34d399;
}
:global(.theme-dark) .dw-left,
:global(.theme-dark) .dw-right {
  background: #0d1a2b;
  border-color: rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .dw-center {
  background: #07111d;
}
:global(.theme-dark) .dw-empty-title {
  color: #7f93ab;
}
:global(.theme-dark) .dw-empty-hint {
  color: #586b82;
}
</style>
