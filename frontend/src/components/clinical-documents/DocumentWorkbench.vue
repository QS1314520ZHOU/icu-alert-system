<template>
  <div class="document-workbench">
    <header class="dw-header">
      <div class="dw-header-left">
        <span class="dw-header-icon">ICU</span>
        <div>
          <div class="dw-header-title">ICU查房与病程生成工作台</div>
          <div class="dw-header-sub">患者状态 → 趋势变化 → 系统A/P → 今日目标 → 可签署病程</div>
        </div>
      </div>
      <div class="dw-header-actions">
        <a-select v-model:value="hours" size="small" class="dw-hours-select">
          <a-select-option :value="12">过去12小时</a-select-option>
          <a-select-option :value="24">过去24小时</a-select-option>
          <a-select-option :value="48">过去48小时</a-select-option>
        </a-select>
        <a-button type="primary" :loading="generating" @click="handleGenerate">生成查房工作台</a-button>
        <a-button :disabled="!draft" :loading="saving" @click="handleSave">{{ dirty ? '保存修改' : '保存草稿' }}</a-button>
        <a-button :disabled="!draftId" :loading="exporting" @click="handleExport">导出DOCX</a-button>
        <a-button type="primary" :disabled="!draft || finalized" class="dw-finalize-btn" @click="handleFinalize">
          {{ finalized ? '已签署' : '签署定稿' }}
        </a-button>
      </div>
    </header>

    <HallucinationWarning v-if="warnings.length" :warnings="warnings" />

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
          {{ formatTime(h.created_at) }} - {{ statusLabel(h.status) }}
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

    <template v-if="workbenchDraft">
      <section class="patient-banner">
        <div class="patient-main">
          <strong>{{ workbenchDraft.patient_banner.bed_no }}床</strong>
          <span>{{ workbenchDraft.patient_banner.age }}岁 {{ workbenchDraft.patient_banner.sex }}</span>
          <span>ICU第{{ workbenchDraft.patient_banner.icu_day }}天</span>
          <span class="patient-diagnosis">{{ workbenchDraft.patient_banner.primary_diagnosis }}</span>
        </div>
        <div class="patient-badges">
          <span>过敏：{{ workbenchDraft.patient_banner.allergy_status }}</span>
          <span>隔离：{{ workbenchDraft.patient_banner.isolation_status }}</span>
          <span>代码状态：{{ workbenchDraft.patient_banner.code_status }}</span>
        </div>
      </section>

      <section class="support-strip">
        <article v-for="item in workbenchDraft.organ_support" :key="item.key" :class="['support-item', `is-${item.status}`]">
          <div class="support-label">{{ item.label }}</div>
          <div class="support-summary">{{ item.summary }}</div>
          <button v-if="item.evidence_refs.length" type="button" class="evidence-link" @click="openEvidence(item.evidence_refs)">
            依据 {{ item.evidence_refs.join(', ') }}
          </button>
          <div v-if="item.missing_data.length" class="missing-line">缺失：{{ formatMissingList(item.missing_data) }}</div>
        </article>
      </section>

      <section v-if="qualityChips.length" class="quality-strip">
        <span class="quality-title">关键缺失</span>
        <span v-for="chip in qualityChips" :key="chip" class="quality-chip">{{ missingLabel(chip) }}</span>
      </section>

      <div class="dw-body">
        <aside class="dw-left">
          <section class="panel">
            <h3>过去24小时关键事件</h3>
            <div v-if="workbenchDraft.timeline.length" class="timeline-list">
              <article v-for="event in workbenchDraft.timeline" :key="event.id" :class="['timeline-event', `tone-${event.severity || 'low'}`]">
                <time>{{ event.occurred_at }}</time>
                <strong>{{ displayClinicalText(event.title, '关键事件') }}</strong>
                <p>{{ displayClinicalText(event.description, '暂无描述') }}</p>
                <button v-if="event.evidence_refs.length" type="button" class="evidence-link" @click="openEvidence(event.evidence_refs)">
                  {{ event.evidence_refs.join(', ') }}
                </button>
              </article>
            </div>
            <div v-else class="empty-text">暂无关键事件。</div>
          </section>

          <section class="panel">
            <h3>趋势摘要</h3>
            <div class="trend-grid">
              <div v-for="item in trendSummary" :key="item.label" class="trend-item">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
                <em>{{ item.trend }}</em>
              </div>
            </div>
          </section>
        </aside>

        <main class="dw-center">
          <ProgressNoteEditor
            :draft="workbenchDraft"
            :citations="citations"
            :context="contextSnapshot"
            :readonly="finalized"
            @update:draft="onDraftUpdate"
            @open-evidence="openEvidence"
          />
        </main>

        <aside class="dw-right">
          <section class="panel">
            <h3>今日目标</h3>
            <div class="goal-list">
              <label v-for="goal in workbenchDraft.daily_goals" :key="goal.id" class="goal-item">
                <input type="checkbox" :checked="goal.status === 'done'" :disabled="finalized" @change="toggleGoal(goal.id)" />
                <span>
                  <strong>{{ displayClinicalText(goal.label, '目标') }}</strong>
                  <em>{{ displayClinicalText(goal.target, '待查房确认') }}</em>
                  <small v-if="goal.missing_data?.length">缺失：{{ formatMissingList(goal.missing_data) }}</small>
                </span>
              </label>
            </div>
          </section>

          <section class="panel">
            <h3>风险任务</h3>
            <div v-if="workbenchDraft.risk_tasks.length" class="risk-list">
              <article v-for="task in workbenchDraft.risk_tasks" :key="task.id" :class="['risk-card', `tone-${task.priority}`]">
                <div class="risk-head">
                  <strong>{{ displayClinicalText(task.title, '风险任务') }}</strong>
                  <span>{{ priorityLabel(task.priority) }}</span>
                </div>
                <p v-for="why in task.why_triggered" :key="why.id">{{ displayClinicalText(why.text, '需复核') }}</p>
                <ul>
                  <li v-for="item in task.confirm_items" :key="item">{{ displayClinicalText(item, '复核项') }}</li>
                </ul>
                <div class="risk-actions">
                  <button v-for="action in task.suggested_actions" :key="action.action_type" type="button" :disabled="finalized" @click="handleTaskAction(task.id, action.action_type)">
                    {{ actionLabel(action.label) }}
                  </button>
                </div>
              </article>
            </div>
            <div v-else class="empty-text">暂无风险任务。</div>
          </section>
        </aside>
      </div>

      <section class="note-preview panel">
        <div class="note-preview-head">
          <h3>可签署病程预览</h3>
          <span>{{ workbenchDraft.note_preview.style }} · {{ workbenchDraft.note_preview.is_overridden ? '人工覆盖' : '结构化派生' }}</span>
        </div>
        <pre>{{ notePreviewText }}</pre>
      </section>
    </template>

    <div v-else class="dw-empty">
      <div class="dw-empty-icon">ICU</div>
      <div class="dw-empty-title">生成 ICU 查房工作台</div>
      <div class="dw-empty-hint">系统会基于过去{{ hours }}小时临床数据生成结构化A/P、今日目标、风险任务和可签署病程。</div>
    </div>

    <a-drawer v-model:open="evidenceDrawerOpen" title="引用依据" placement="right" width="420">
      <CitationPanel :citations="selectedCitations" :context="contextSnapshot" />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Button as AButton,
  Drawer as ADrawer,
  Modal as AModal,
  Select as ASelect,
  SelectOption as ASelectOption,
  message,
} from 'ant-design-vue'
import {
  exportDraft,
  finalizeDraft,
  generateProgressNote,
  getDraft,
  isWorkbenchDraft,
  listDraftVersions,
  listPatientDrafts,
  updateDraft,
  type Citation,
  type DraftContent,
  type DraftVersion,
  type RoundingWorkbenchDraft,
} from '../../api/clinicalDocuments'
import { formatClinicalText } from '../../utils/displayLabels'
import CitationPanel from './CitationPanel.vue'
import HallucinationWarning from './HallucinationWarning.vue'
import ProgressNoteEditor from './ProgressNoteEditor.vue'

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
const draftHistory = ref<any[]>([])
const selectedHistoryId = ref<string | undefined>(undefined)
const versions = ref<DraftVersion[]>([])
const selectedVersionNo = ref<number | undefined>(undefined)
const evidenceDrawerOpen = ref(false)
const selectedEvidenceRefs = ref<string[]>([])

const workbenchDraft = computed<RoundingWorkbenchDraft | null>(() => {
  const candidates = [
    draft.value,
    selectedHistoryDraftContent.value,
    draftHistory.value[0]?.current_content,
    draftHistory.value[0]?.draft,
    draftHistory.value.find((item) => String(item?.draft_id || '') === String(draftId.value || '')),
    ...draftHistory.value.flatMap((item) => [item?.current_content, item?.draft, item]),
  ]
  for (const candidate of candidates) {
    const content = unwrapDraftContent(candidate)
    if (isWorkbenchLikeDraft(content)) return normalizeWorkbenchForDisplay(coerceWorkbenchDraft(content))
  }
  return null
})

const selectedHistoryDraftContent = computed(() => {
  const selectedId = String(selectedHistoryId.value || draftId.value || '').trim()
  if (!selectedId) return null
  const item = draftHistory.value.find((row) => String(row?.draft_id || '') === selectedId)
  return item?.current_content || item?.draft || null
})

const selectedCitations = computed(() => {
  if (!selectedEvidenceRefs.value.length) return citations.value
  return citations.value.filter((item) => selectedEvidenceRefs.value.includes(citationId(item)))
})

const qualityChips = computed(() => workbenchDraft.value?.quality_checks?.critical_missing_data?.slice(0, 8) || [])

const noisyMissingLabels = new Set([
  'bedside',
  '床旁记录',
  '事实依据',
  '当前呼吸模式',
  '当前呼吸机模式',
  '当前呼吸支持方式',
  '升压药名称及剂量',
  '升压药剂量',
  'CRRT状态',
  '24h尿量',
  '尿量',
  '24h出入量',
  '24h液体平衡',
  '镇静评分',
  '谵妄评估',
  '镇痛镇静用药',
  'CVC天数',
  '尿管天数',
  '管路留置天数',
  '抗菌药疗程',
  '抗菌药疗程天数',
  '培养结果',
  'WBC/PCT/CRP',
])

function cleanMissingItems(items: any = []): string[] {
  const list = Array.isArray(items)
    ? items
    : String(items || '')
      .replace(/P\/F ratio/g, 'P/F_ratio')
      .split(/[、,，;；\n]+|\s+(?=(?:FiO2|PEEP|RASS|CAM-ICU|24h|尿量|抗菌|培养|WBC|PCT|CRP|CVC|CRRT))/i)
      .map((item) => item.replace(/P\/F_ratio/g, 'P/F ratio'))
      .filter(Boolean)
  const output: string[] = []
  for (const item of list || []) {
    const raw = String(item || '').trim()
    const label = missingLabel(raw)
    if (!label || noisyMissingLabels.has(raw) || noisyMissingLabels.has(label)) continue
    if (!output.includes(label)) output.push(label)
  }
  return output
}

function normalizeWorkbenchForDisplay(value: RoundingWorkbenchDraft): RoundingWorkbenchDraft {
  const cloned = JSON.parse(JSON.stringify(value || {})) as RoundingWorkbenchDraft
  cloned.patient_banner = {
    ...cloned.patient_banner,
    allergy_status: displayClinicalText(cloned.patient_banner?.allergy_status, '未提供'),
    isolation_status: displayClinicalText(cloned.patient_banner?.isolation_status, '未提供'),
    code_status: displayClinicalText(cloned.patient_banner?.code_status, '未提供'),
  }
  cloned.organ_support = (cloned.organ_support || []).map((item: any) => ({
    ...item,
    label: displayClinicalText(item.label, '器官支持'),
    summary: String(item.summary || '').startsWith('未提供') ? '待查房确认' : displayClinicalText(item.summary, '待查房确认'),
    missing_data: cleanMissingItems(item.missing_data || []),
  }))
  cloned.timeline = (cloned.timeline || []).map((item: any) => ({
    ...item,
    title: displayClinicalText(item.title, '关键事件'),
    description: displayClinicalText(item.description, '暂无描述'),
  }))
  cloned.daily_goals = (cloned.daily_goals || []).map((item: any) => ({
    ...item,
    label: displayClinicalText(item.label, '目标'),
    target: displayClinicalText(item.target, '待查房确认'),
    missing_data: cleanMissingItems(item.missing_data || []),
  }))
  cloned.risk_tasks = (cloned.risk_tasks || []).map((task: any) => ({
    ...task,
    category: displayClinicalText(task.category, '通用'),
    title: displayClinicalText(task.title, '风险任务'),
    why_triggered: (task.why_triggered || []).map((stmt: any) => ({
      ...stmt,
      text: displayClinicalText(stmt.text, '需复核'),
      missing_data: cleanMissingItems(stmt.missing_data || []),
    })),
    confirm_items: (task.confirm_items || []).map((item: any) => displayClinicalText(item, '复核项')),
    suggested_actions: (task.suggested_actions || []).map((action: any) => ({
      ...action,
      label: actionLabel(action.label),
    })),
  }))
  cloned.system_ap = (cloned.system_ap || []).map((card: any) => ({
    ...card,
    title: systemTitle(card.title || card.system),
    missing_data: cleanMissingItems(card.missing_data || []),
    status: cleanStatements(card.status || []),
    trend: cleanStatements(card.trend || []),
    assessment: cleanStatements(card.assessment || []),
    plan_items: cleanStatements(card.plan_items || []),
  }))
  if (cloned.quality_checks) {
    cloned.quality_checks.critical_missing_data = cleanMissingItems(cloned.quality_checks.critical_missing_data || [])
    cloned.quality_checks.warnings = (cloned.quality_checks.warnings || []).map((item: any) => displayClinicalText(item, '需复核'))
    cloned.quality_checks.contradictions = (cloned.quality_checks.contradictions || []).map((item: any) => displayClinicalText(item, '需复核'))
  }
  return cloned
}

function cleanStatements(items: any[] = []) {
  return (items || []).map((stmt: any) => ({
    ...stmt,
    text: displayClinicalText(stmt.text, ''),
    missing_data: cleanMissingItems(stmt.missing_data || []),
  }))
}

function systemTitle(value: any): string {
  const key = String(value || '').trim()
  const normalized = key.toLowerCase().replace(/[\s-]+/g, '_')
  const map: Record<string, string> = {
    neuro: '神经',
    'neuro_神经': '神经',
    resp: '呼吸 / 氧合',
    'resp_呼吸_/_氧合': '呼吸 / 氧合',
    cv: '循环 / 灌注',
    'cv_循环_/_灌注': '循环 / 灌注',
    renal_fluid: '肾脏 / 液体',
    'renal/fluid': '肾脏 / 液体',
    'renal/fluid_肾脏_/_液体': '肾脏 / 液体',
    gi_nutrition: '消化 / 营养',
    'gi/nutrition': '消化 / 营养',
    'gi/nutrition_消化_/_营养': '消化 / 营养',
    id: '感染',
    'id_感染': '感染',
    heme: '血液 / 凝血',
    'heme_凝血_/_血液': '血液 / 凝血',
    endo: '内分泌 / 代谢',
    'endo_内分泌_/_代谢': '内分泌 / 代谢',
    lines_devices: '管路 / 装置',
    'lines/devices': '管路 / 装置',
    'lines/devices_管路_/_装置': '管路 / 装置',
    goals: '今日目标 / 夜间预案',
    'goals_今日目标_/_夜间预案': '今日目标 / 夜间预案',
  }
  return map[key] || map[normalized] || displayClinicalText(key, '系统评估')
}

function unwrapDraftContent(value: any): any {
  let current = value
  for (let i = 0; i < 3; i += 1) {
    if (typeof current === 'string') {
      const text = current.trim()
      if (!text.startsWith('{')) return current
      try {
        current = JSON.parse(text)
        continue
      } catch {
        return current
      }
    }
    if (current && typeof current === 'object') {
      if (current.current_content) {
        current = current.current_content
        continue
      }
      if (current.draft && current.draft !== current) {
        current = current.draft
        continue
      }
    }
    break
  }
  return current
}

function isWorkbenchLikeDraft(value: any): boolean {
  if (!value || typeof value !== 'object') return false
  return isWorkbenchDraft(value)
    || String(value.content_type || '').trim() === 'rounding_workbench'
    || String(value.schema_version || '').trim() === 'icu_rounding_workbench.v1'
    || Array.isArray(value.organ_support)
    || Array.isArray(value.system_ap)
}

function coerceWorkbenchDraft(value: any): RoundingWorkbenchDraft {
  return {
    schema_version: 'icu_rounding_workbench.v1',
    content_type: 'rounding_workbench',
    generated_at: value.generated_at || new Date().toISOString(),
    context_window: value.context_window || { start: '', end: '' },
    patient_banner: value.patient_banner || {
      bed_no: '',
      age: '',
      sex: '',
      icu_day: '',
      primary_diagnosis: '',
      allergy_status: '未提供',
      isolation_status: '未提供',
      code_status: '未提供',
    },
    organ_support: Array.isArray(value.organ_support) ? value.organ_support : [],
    timeline: Array.isArray(value.timeline) ? value.timeline : [],
    system_ap: Array.isArray(value.system_ap) ? value.system_ap : [],
    daily_goals: Array.isArray(value.daily_goals) ? value.daily_goals : [],
    risk_tasks: Array.isArray(value.risk_tasks) ? value.risk_tasks : [],
    note_preview: value.note_preview || {
      style: 'APSO',
      generated_text: '',
      final_text_override: null,
      is_overridden: false,
      generated_from_hash: '',
    },
    quality_checks: value.quality_checks || {
      critical_missing_data: [],
      stale_data: [],
      contradictions: [],
      warnings: [],
    },
    raw_ai_tags: Array.isArray(value.raw_ai_tags) ? value.raw_ai_tags : [],
  }
}

function missingLabel(value: string): string {
  const map: Record<string, string> = {
    FiO2: '吸氧浓度',
    PEEP: '呼气末正压',
    'P/F ratio': '氧合指数',
    RASS: '镇静评分',
    'CAM-ICU': '谵妄评估',
    '抗菌药疗程天数': '抗菌药疗程',
    bedside: '',
  }
  return map[value] || value
}

function formatMissingList(items: string[] = []): string {
  return cleanMissingItems(items).join('、')
}

const trendSummary = computed(() => {
  const v = contextSnapshot.value?.v || {}
  return [
    { label: 'HR', value: rangeText(v.hr), trend: trendText(v.hr?.trend) },
    { label: 'MAP', value: rangeText(v.map), trend: trendText(v.map?.trend) },
    { label: 'SpO2', value: rangeText(v.spo2, '%'), trend: trendText(v.spo2?.trend) },
    { label: 'T', value: rangeText(v.temp, '℃'), trend: trendText(v.temp?.trend) },
    { label: 'RR', value: rangeText(v.rr), trend: trendText(v.rr?.trend) },
  ]
})

const notePreviewText = computed(() => {
  const preview = workbenchDraft.value?.note_preview
  return formatClinicalText(preview?.final_text_override || preview?.generated_text || '', '')
})

function displayClinicalText(value: any, fallback = '暂无') {
  return formatClinicalText(value, fallback)
}

function actionLabel(value: any): string {
  const raw = String(value || '').trim()
  const map: Record<string, string> = {
    add_to_plan: '加入计划',
    create_order_draft_placeholder: '生成医嘱草稿',
    snooze: '暂缓',
    dismiss: '不采纳',
    '加入今日计划': '加入计划',
    '生成医嘱草稿占位': '生成医嘱草稿',
  }
  return map[raw] || displayClinicalText(raw, '处理')
}

onMounted(loadDraftHistory)

watch(() => props.patientId, () => {
  draftId.value = ''
  draft.value = null
  citations.value = []
  warnings.value = []
  contextSnapshot.value = null
  draftHistory.value = []
  selectedHistoryId.value = undefined
  versions.value = []
  selectedVersionNo.value = undefined
  dirty.value = false
  void loadDraftHistory()
})

async function loadDraftHistory() {
  try {
    const { data } = await listPatientDrafts(props.patientId)
    draftHistory.value = data.items || []
    if (draftHistory.value.length) {
      const selectedId = String(selectedHistoryId.value || '').trim()
      const currentContent = unwrapDraftContent(draft.value)
      const selectedRow = draftHistory.value.find((item) => String(item?.draft_id || '') === selectedId)
      const currentRow = draftHistory.value.find((item) => String(item?.draft_id || '') === String(draftId.value || ''))
      const latestWorkbenchRow = draftHistory.value.find((item) => isWorkbenchLikeDraft(unwrapDraftContent(item?.current_content || item?.draft)))
      const preferred = selectedRow || (isWorkbenchLikeDraft(currentContent) ? currentRow : latestWorkbenchRow) || draftHistory.value[0]

      if (!isWorkbenchLikeDraft(currentContent) || String(draftId.value || '') !== String(preferred?.draft_id || '')) {
        const preferredContent = unwrapDraftContent(preferred?.current_content || preferred?.draft || null)
        selectedHistoryId.value = preferred.draft_id
        draftId.value = preferred.draft_id
        draft.value = isWorkbenchLikeDraft(preferredContent) ? preferredContent : null
        citations.value = preferred.citations || []
        warnings.value = preferred.hallucination_warnings || []
        contextSnapshot.value = preferred.context_snapshot || null
        finalized.value = preferred.status === 'finalized'
        dirty.value = false
        selectedVersionNo.value = undefined
      }

      if (preferred?.draft_id && !dirty.value) {
        await loadHistoryDraft(preferred.draft_id, { silent: true })
      } else if (!isWorkbenchLikeDraft(unwrapDraftContent(draft.value)) && preferred?.draft_id) {
        await loadHistoryDraft(preferred.draft_id, { silent: true })
      } else {
        await loadVersions()
      }
    } else if (!isWorkbenchLikeDraft(unwrapDraftContent(draft.value))) {
      draftId.value = ''
      selectedHistoryId.value = undefined
      draft.value = null
      versions.value = []
    }
  } catch {
    draftHistory.value = []
  }
}

async function loadHistoryDraft(id: any, options: any = {}) {
  if (!id) return
  const idStr = String(id)
  try {
    const { data } = await getDraft(idStr)
    const content = unwrapDraftContent(data.draft || data.current_content || data)
    draftId.value = idStr
    selectedHistoryId.value = idStr
    draft.value = isWorkbenchLikeDraft(content) ? content : null
    citations.value = data.citations || []
    warnings.value = data.hallucination_warnings || []
    contextSnapshot.value = data.context_snapshot
    finalized.value = (data as any).status === 'finalized'
    dirty.value = false
    selectedVersionNo.value = undefined
    await loadVersions()
  } catch {
    if (!options?.silent) message.error('加载草稿失败')
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
    const { data } = await generateProgressNote({ patient_id: props.patientId, hours: hours.value })
    draftId.value = data.draft_id
    draft.value = unwrapDraftContent(data.draft || data.current_content || null)
    citations.value = data.citations || []
    warnings.value = data.hallucination_warnings || []
    contextSnapshot.value = data.context_snapshot
    finalized.value = false
    dirty.value = false
    selectedHistoryId.value = data.draft_id
    selectedVersionNo.value = undefined
    versions.value = []
    message.success('ICU查房工作台已生成')
    await loadDraftHistory()
  } catch (err: any) {
    message.error(`生成失败：${displayClinicalText(err?.response?.data?.detail || err.message || '未知错误', '未知错误')}`)
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

function onDraftUpdate(nextDraft: DraftContent) {
  draft.value = nextDraft
  dirty.value = true
}

function restoreVersion(versionNo: any) {
  if (!versionNo) return
  const found = versions.value.find((v) => v.version_no === Number(versionNo))
  if (!found) return
  draft.value = unwrapDraftContent(JSON.parse(JSON.stringify(found.content || {})))
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
    link.download = `ICU病程记录_${props.patientId}_${new Date().toISOString().slice(0, 10)}.docx`
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

function openEvidence(refs: string[]) {
  selectedEvidenceRefs.value = refs
  evidenceDrawerOpen.value = true
}

function toggleGoal(goalId: string) {
  if (!workbenchDraft.value || finalized.value) return
  const next = JSON.parse(JSON.stringify(workbenchDraft.value)) as RoundingWorkbenchDraft
  const goal = next.daily_goals.find((item) => item.id === goalId)
  if (goal) {
    goal.status = goal.status === 'done' ? 'open' : 'done'
    onDraftUpdate(next)
  }
}

function handleTaskAction(taskId: string, actionType: string) {
  if (!workbenchDraft.value || finalized.value) return
  const next = JSON.parse(JSON.stringify(workbenchDraft.value)) as RoundingWorkbenchDraft
  const task = next.risk_tasks.find((item) => item.id === taskId)
  if (!task) return
  if (actionType === 'dismiss') task.status = 'dismissed'
  else if (actionType === 'snooze') task.status = 'snoozed'
  else if (actionType === 'add_to_plan') {
    task.status = 'done'
    const goalsCard = next.system_ap.find((card) => card.system === 'goals')
    goalsCard?.plan_items.push({
      id: `task_${taskId}_${Date.now()}`,
      kind: 'recommendation',
      text: `处理风险任务：${task.title}`,
      evidence_refs: task.why_triggered.flatMap((item) => item.evidence_refs || []),
      missing_data: [],
      review_required: true,
    })
  } else if (actionType === 'create_order_draft_placeholder') {
    message.info('已作为医嘱草稿占位动作记录，请在医嘱系统中复核创建。')
  }
  onDraftUpdate(next)
}

function citationId(item: Citation): string {
  return String(item.id || item.ref || '')
}

function priorityLabel(priority: string) {
  const map: Record<string, string> = { critical: '危急', high: '高', medium: '中', low: '低' }
  return map[priority] || priority
}

function rangeText(stat: any, unit = '') {
  if (!stat || stat.min == null || stat.max == null) return '未提供'
  return stat.min === stat.max ? `${stat.min}${unit}` : `${stat.min}-${stat.max}${unit}`
}

function trendText(raw: any) {
  const map: Record<string, string> = {
    up: '上升',
    down: '下降',
    stable: '平稳',
    volatile: '波动',
    no_data: '无数据',
    insufficient: '数据不足',
  }
  return map[String(raw || '')] || raw || '未提供'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = { draft: '草稿', finalized: '已定稿' }
  return map[status] || status || '未知'
}

function formatTime(raw: any): string {
  if (!raw) return '-'
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
  gap: 8px;
  min-height: 0;
  background: #f5f7fb;
  border-radius: 4px;
  overflow: visible;
  color: #1f2937;
}

.dw-header,
.dw-history-bar,
.patient-banner,
.support-strip,
.quality-strip,
.panel,
.legacy-shell {
  background: #FFFFFF;
  border: 1px solid #edf1f7;
}

.dw-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  flex: 0 0 auto;
}

.dw-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dw-header-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 30px;
  border-radius: 6px;
  background: #e6f4ff;
  color: #15558D;
  font-size: 12px;
  font-weight: 800;
}

.dw-header-title {
  font-weight: 700;
  font-size: 16px;
}

.dw-header-sub {
  margin-top: 2px;
  color: #667085;
  font-size: 12px;
}

.dw-header-actions,
.dw-history-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.dw-hours-select {
  width: 132px;
}

.dw-finalize-btn {
  background: #1A9C5B !important;
  border-color: #1A9C5B !important;
}

.dw-history-bar {
  justify-content: flex-start;
  padding: 5px 14px;
  flex: 0 0 auto;
}

.dw-history-label,
.dw-dirty,
.dw-saved {
  font-size: 12px;
  white-space: nowrap;
}

.dw-history-label {
  color: #667085;
}

.dw-history-select {
  width: 240px;
}

.dw-version-select {
  width: 180px;
}

.dw-dirty {
  color: #d97706;
}

.dw-saved {
  color: #1A9C5B;
}

.patient-banner {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 14px;
  flex: 0 0 auto;
}

.patient-main,
.patient-badges {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.patient-main strong {
  font-size: 18px;
  color: #1D2129;
}

.patient-diagnosis {
  font-weight: 600;
  color: #15558D;
}

.patient-badges span,
.quality-chip {
  padding: 3px 8px;
  border-radius: 4px;
  background: #f2f4f7;
  font-size: 12px;
  color: #475467;
}

.support-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 6px;
  padding: 7px 10px;
  flex: 0 0 auto;
}

.support-item {
  min-height: 76px;
  padding: 8px;
  border: 1px solid #edf1f7;
  border-radius: 4px;
  background: #f8fafc;
}

.support-item.is-active {
  border-color: #93c5fd;
  background: #eff6ff;
}

.support-label {
  font-weight: 700;
  font-size: 13px;
}

.support-summary {
  display: -webkit-box;
  margin-top: 4px;
  overflow: hidden;
  color: #344054;
  font-size: 12px;
  line-height: 1.35;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.missing-line {
  margin-top: 4px;
  color: #b45309;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.quality-strip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 14px;
  flex: 0 0 auto;
}

.quality-title {
  font-weight: 700;
  font-size: 12px;
  color: #b45309;
}

.dw-body {
  display: grid;
  grid-template-columns: minmax(260px, 0.82fr) minmax(520px, 1.5fr) minmax(280px, 0.9fr);
  gap: 10px;
  padding: 0 10px;
  flex: 0 0 auto;
  min-height: 0;
  overflow: visible;
  align-items: start;
}

.dw-left,
.dw-right {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
  overflow: visible;
}

.dw-center {
  min-width: 0;
  min-height: 0;
  overflow: visible;
  padding-right: 2px;
}

.panel {
  border-radius: 4px;
  padding: 9px;
  min-height: 0;
}

.panel h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #1D2129;
}

.timeline-list,
.risk-list,
.goal-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
}

.timeline-list {
  max-height: clamp(180px, 28vh, 320px);
}

.goal-list {
  max-height: clamp(160px, 24vh, 260px);
}

.risk-list {
  max-height: clamp(200px, 32vh, 360px);
}

.timeline-event,
.risk-card,
.goal-item,
.trend-item {
  border: 1px solid #edf1f7;
  border-radius: 4px;
  background: #f8fafc;
  padding: 7px;
}

.timeline-event time {
  display: block;
  color: #667085;
  font-size: 11px;
}

.timeline-event strong,
.risk-head strong {
  display: block;
  margin-top: 2px;
  font-size: 13px;
}

.timeline-event p,
.risk-card p {
  margin: 4px 0;
  color: #475467;
  font-size: 12px;
  line-height: 1.5;
}

.evidence-link {
  padding: 0;
  border: none;
  background: transparent;
  color: #15558D;
  font-size: 11px;
  cursor: pointer;
}

.trend-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.trend-item span,
.trend-item em {
  display: block;
  color: #667085;
  font-size: 11px;
  font-style: normal;
}

.trend-item strong {
  display: block;
  margin: 3px 0;
  font-size: 15px;
}

.goal-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  cursor: pointer;
}

.goal-item input {
  margin-top: 3px;
}

.goal-item strong,
.goal-item em,
.goal-item small {
  display: block;
}

.goal-item em {
  color: #475467;
  font-size: 12px;
  font-style: normal;
  line-height: 1.5;
}

.goal-item small {
  color: #b45309;
  font-size: 11px;
}

.risk-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.risk-head span {
  flex: 0 0 auto;
  align-self: flex-start;
  padding: 2px 7px;
  border-radius: 4px;
  background: #FFFFFF;
  color: #c2410c;
  font-size: 11px;
}

.risk-card ul {
  margin: 5px 0 0 16px;
  color: #475467;
  font-size: 12px;
  line-height: 1.6;
}

.risk-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.risk-actions button {
  border: 1px solid #d0d5dd;
  background: #FFFFFF;
  border-radius: 4px;
  padding: 3px 7px;
  font-size: 12px;
  cursor: pointer;
}

.note-preview {
  margin: 0 10px 10px;
  flex: 0 0 auto;
}

.note-preview-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.note-preview-head span {
  color: #667085;
  font-size: 12px;
}

.note-preview pre,
.legacy-shell pre {
  margin: 0;
  max-height: clamp(96px, 18vh, 180px);
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1f2937;
  background: #f8fafc;
  border: 1px solid #edf1f7;
  border-radius: 4px;
  padding: 8px 10px;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.55;
}

.legacy-shell {
  margin: 0 10px 10px;
  border-radius: 4px;
  padding: 16px;
}

.legacy-shell p,
.empty-text {
  color: #667085;
  font-size: 13px;
}

.dw-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 420px;
  color: #98a2b3;
}

.dw-empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 44px;
  border-radius: 4px;
  margin-bottom: 16px;
  background: #eef4ff;
  color: #15558D;
  font-weight: 800;
}

.dw-empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #667085;
  margin-bottom: 8px;
}

.dw-empty-hint {
  font-size: 13px;
  color: #98a2b3;
}

@media (max-width: 1400px) {
  .support-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .dw-body {
    grid-template-columns: minmax(260px, 0.9fr) minmax(460px, 1.4fr);
  }
  .dw-right {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    align-items: start;
  }

  .goal-list,
  .risk-list {
    max-height: clamp(180px, 26vh, 300px);
  }
}

@media (max-width: 900px) {
  .patient-banner,
  .dw-header {
    flex-direction: column;
    align-items: stretch;
  }
  .support-strip,
  .dw-body,
  .dw-right {
    grid-template-columns: 1fr;
  }
}
</style>
