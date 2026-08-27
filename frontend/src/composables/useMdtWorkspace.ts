/**
 * MDT 会诊工作台 — 状态与业务逻辑 composable
 *
 * 从 MdtBoard.vue 中提取，负责：
 * - 患者加载、评估生成
 * - 决议 CRUD、医生确认
 * - 工作区保存、文书生成
 * - 会话管理（切换、新建、复制）
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  generateAiDocument,
  getAiMdtWorkspace,
  getAiMdtWorkspaceSession,
  getAiMultiAgentAssessment,
  getAiSystemPanels,
  getPatientAlerts,
  getPatientDetail,
  getPatientDrugs,
  getPatientVitalsTrend,
  getPatients,
  listAiMdtWorkspaceSessions,
  postAiMdtDecisionConfirm,
  saveAiMdtWorkspace,
} from '../api'
import { getOperatorIdentity } from '../utils/operatorIdentity'
import { BODY_MAP_ORGAN_LABELS, bodyMapSeverityText, type BodyMapOrganKey, type BodyMapSeverity } from '../utils/bodyMap'

/* ── 类型 ───────────────────────────────────────── */

export interface MdtDecision {
  id: string
  action: string
  owner: string
  deadline: string
  monitoring: string
  review_time: string
  status: string
  note: string
  requires_confirmation: boolean
  confirmation_status: string
  confirmed_at?: string | null
  confirmed_by?: string | null
  version?: number
  safety_notice?: string
}

export interface MdtStepRow {
  key: 'patient' | 'review' | 'decision' | 'archive'
  index: string
  title: string
  desc: string
  done: boolean
}

export interface SessionTemplate {
  readonly key: string
  readonly label: string
  readonly summary: string
  readonly tags: readonly string[]
  readonly participants: readonly string[]
  readonly decisions: readonly {
    readonly action: string
    readonly owner: string
    readonly deadline: string
    readonly monitoring: string
    readonly review_time: string
  }[]
}

/* ── 常量 ───────────────────────────────────────── */

export const SESSION_TEMPLATES: readonly SessionTemplate[] = [
  {
    key: 'sepsis',
    label: '脓毒症会诊',
    summary: '围绕感染控制、循环复苏、乳酸下降与器官支持快速形成一轮 MDT 处置。',
    tags: ['脓毒症', '感染', '循环'],
    participants: ['ICU', '感染', '呼吸', '药学'],
    decisions: [
      { action: '1小时内复核血培养与抗菌药覆盖', owner: '感染科', deadline: '1h', monitoring: '培养结果 / PCT / CRP', review_time: '6h' },
      { action: '按乳酸与灌注指标评估复苏目标', owner: 'ICU主治', deadline: '立即', monitoring: 'MAP / 乳酸 / 尿量', review_time: '2h' },
      { action: '评估呼吸支持与撤机窗口', owner: '呼吸治疗师', deadline: '6h', monitoring: 'SpO2 / P/F / RR', review_time: '6h' },
    ],
  },
  {
    key: 'weaning',
    label: '撤机失败复评',
    summary: '聚焦通气参数、镇静谵妄、循环耐受与营养储备，快速定位撤机失败主因。',
    tags: ['撤机', '呼吸', '谵妄'],
    participants: ['ICU', '呼吸治疗', '神经', '营养'],
    decisions: [
      { action: '复核呼吸机参数与自主呼吸试验失败原因', owner: '呼吸治疗师', deadline: '立即', monitoring: 'FiO2 / PEEP / RR / Vte', review_time: '4h' },
      { action: '调整镇静镇痛并筛查谵妄', owner: '值班医生', deadline: '2h', monitoring: 'RASS / CAM-ICU', review_time: '4h' },
      { action: '补齐营养与肌力评估', owner: '营养师', deadline: '12h', monitoring: '蛋白 / 摄入量 / 肌力', review_time: '24h' },
    ],
  },
  {
    key: 'renal',
    label: '肾替代治疗评审',
    summary: '针对 AKI/CRRT 患者统一评审液体平衡、电解质与抗感染剂量调整。',
    tags: ['CRRT', 'AKI', '液体管理'],
    participants: ['ICU', '肾内', '药学'],
    decisions: [
      { action: '复核 CRRT 指征与超滤目标', owner: '肾内科', deadline: '2h', monitoring: '尿量 / 肌酐 / 酸碱', review_time: '6h' },
      { action: '同步调整肾功能相关药物剂量', owner: '临床药师', deadline: '4h', monitoring: '药物暴露 / 肾功能', review_time: '12h' },
      { action: '更新液体出入平衡与血流动力学策略', owner: 'ICU主治', deadline: '立即', monitoring: '净平衡 / MAP / 乳酸', review_time: '6h' },
    ],
  },
] as const

const DOMAIN_LABELS: Record<string, string> = {
  hemodynamic: '循环', respiratory: '呼吸', infection: '感染',
  renal: '肾脏', neuro: '神经', nutrition: '营养', pharmacy: '药学',
  hemodynamic_agent: '循环', respiratory_agent: '呼吸', infection_agent: '感染',
  renal_agent: '肾脏', neuro_agent: '神经', nutrition_agent: '营养', pharmacy_agent: '药学',
}

const BODY_SEVERITY_RANK: Record<string, number> = { normal: 0, warning: 1, high: 2, critical: 3 }

/* ── 辅助函数 ───────────────────────────────────── */

export function domainLabel(domain: any): string {
  return DOMAIN_LABELS[String(domain || '')] || String(domain || '') || '未知专科'
}

function bodySeverityRank(value: any): number {
  return BODY_SEVERITY_RANK[String(value || 'normal')] || 0
}

function priorityToBodySeverity(priority: any): BodyMapSeverity {
  const key = String(priority || 'medium').toLowerCase()
  if (key === 'critical') return 'critical'
  if (key === 'high') return 'high'
  if (key === 'low') return 'normal'
  return 'warning'
}

export function shortText(value: any, max = 52): string {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}...` : text || '暂无'
}

export function priorityLabel(priority: any): string {
  const key = String(priority || 'medium').toLowerCase()
  return ({ critical: '危急', high: '高优先', medium: '中优先', low: '低优先' } as Record<string, string>)[key] || '中优先'
}

export function phaseLabel(phase: any): string {
  const key = String(phase || 'finalizing').toLowerCase()
  return ({ collecting: '收集中', conflict_review: '冲突评审', finalizing: '裁决定稿', closed: '已关闭' } as Record<string, string>)[key] || '裁决定稿'
}

export function decisionStatusLabel(status: any): string {
  return ({
    pending_confirmation: '待医生确认',
    doctor_confirmed: '医生已确认',
    pending: '确认后待执行',
    in_progress: '进行中',
    completed: '已完成',
    rejected: '医生不采纳',
    needs_revision: '需修改',
    dismissed: '已取消',
    draft: '草稿',
  } as Record<string, string>)[String(status || 'pending_confirmation').toLowerCase()] || '待医生确认'
}

function isDecisionConfirmed(item: any): boolean {
  const status = String(item?.status || '').toLowerCase()
  const confirmationStatus = String(item?.confirmation_status || '').toLowerCase()
  return Boolean(item?.confirmed_at) || confirmationStatus === 'confirmed' || status === 'doctor_confirmed' || item?.requires_confirmation === false
}

export function needsDoctorConfirmation(item: any): boolean {
  const status = String(item?.status || 'pending_confirmation').toLowerCase()
  const confirmationStatus = String(item?.confirmation_status || '').toLowerCase()
  if (isDecisionConfirmed(item)) return false
  if (confirmationStatus === 'rejected') return false
  return ['pending_confirmation', 'needs_revision'].includes(status) || item?.requires_confirmation !== false
}

function normalizeDecision(item: any, idx = 0): MdtDecision {
  const row = { ...(item || {}) }
  let status = String(row.status || '').trim().toLowerCase()
  const confirmationStatus = String(row.confirmation_status || '').trim().toLowerCase()
  const confirmed = Boolean(row.confirmed_at) || confirmationStatus === 'confirmed' || status === 'doctor_confirmed' || row.requires_confirmation === false
  if (['pending', 'in_progress', 'completed'].includes(status) && !confirmed) status = 'pending_confirmation'
  if (!status) status = 'pending_confirmation'
  if (confirmed && status === 'pending_confirmation') status = 'doctor_confirmed'
  return {
    ...row,
    id: row.id || `decision-${Date.now()}-${idx}`,
    status,
    owner: String(row.owner || '').trim() || '值班医生',
    deadline: String(row.deadline || '').trim() || (idx === 0 ? '立即' : '6h'),
    monitoring: String(row.monitoring || '').trim() || '按系统指标复评',
    review_time: String(row.review_time || '').trim() || '6h',
    requires_confirmation: confirmed ? false : (row.requires_confirmation === false ? false : true),
    confirmation_status: row.confirmation_status || (confirmed ? 'confirmed' : 'pending'),
    safety_notice: row.safety_notice || 'AI 生成内容仅为待审核建议草案，不能作为医嘱直接执行；必须由执业医生结合床旁情况确认。',
  }
}

function normalizeDecisionList(rows: any[]): MdtDecision[] {
  return (Array.isArray(rows) ? rows : []).map((item, idx) => normalizeDecision(item, idx)).filter((item) => String(item.action || '').trim())
}

/* ── Composable ─────────────────────────────────── */

export function useMdtWorkspace() {
  const router = useRouter()
  const route = useRoute()

  // 核心状态
  const loading = ref(false)
  const error = ref('')
  const patients = ref<any[]>([])
  const patient = ref<any>(null)
  const assessment = ref<any>(null)
  const selectedPatientId = ref('')
  const activeAgent = ref('')
  const currentLoadToken = ref(0)
  const trendWindow = ref<'24h' | '72h'>('24h')
  const vitalsTrendPoints = ref<any[]>([])
  const drugs = ref<any[]>([])
  const alerts = ref<any[]>([])
  const systemPanels = ref<Record<string, any>>({})
  const workspaceRecord = ref<any>(null)
  const workspaceDocuments = ref<any[]>([])
  const generatedOrderDrafts = ref<any[]>([])
  const decisions = ref<MdtDecision[]>([])
  const consultRecord = ref('')
  const progressRecord = ref('')
  const finalSummary = ref('')
  const participantsText = ref('')
  const tagsText = ref('')
  const savingWorkspace = ref(false)
  const generatingDocType = ref('')
  const workspaceSessions = ref<any[]>([])
  const currentSessionId = ref('')
  const currentMdtStep = ref<'patient' | 'review' | 'decision' | 'archive'>('patient')
  const sessionDrawerOpen = ref(false)
  const sessionListOpenOnly = ref(true)
  const sessionSearch = ref('')
  const sessionPhaseFilter = ref('')
  const lastSavedSnapshot = ref('')
  const selectedTemplateKey = ref('')
  const activityLog = ref<any[]>([])
  const confirmingDecisionIds = ref<Set<string>>(new Set())

  // ── 派生数据 ──────────────────────────────────────

  const patientOptions = computed(() =>
    patients.value.map((item: any) => ({
      value: String(item?._id || ''),
      label: `${item?.hisBed || '--'}床 · ${item?.name || item?.hisName || '未知患者'} · ${item?.clinicalDiagnosis || item?.admissionDiagnosis || '暂无诊断'}${item?.__mdtFallbackCurrent ? ' · 当前已选' : ''}`,
    }))
  )
  const assessmentRecord = computed(() => assessment.value?.assessment || assessment.value || null)
  const assessmentResult = computed(() => assessmentRecord.value?.result || assessmentRecord.value || {})
  const specialistRows = computed(() => Object.values(assessmentResult.value?.assessments || {}) as any[])
  const conflictRows = computed(() => Array.isArray(assessmentResult.value?.conflicts) ? assessmentResult.value.conflicts : [])
  const metaSummaryRecord = computed(() => assessmentResult.value?.meta_agent || {})
  const metaSummary = computed(() => String(metaSummaryRecord.value?.summary || assessmentRecord.value?.summary || '暂无总控智能体裁决摘要'))
  const metaActions = computed(() => Array.isArray(metaSummaryRecord.value?.final_actions) ? metaSummaryRecord.value.final_actions : [])
  const priorityRows = computed(() => Array.isArray(metaSummaryRecord.value?.top_priorities) ? metaSummaryRecord.value.top_priorities : [])
  const activeSpecialist = computed(() => specialistRows.value.find((item: any) => item.agent === activeAgent.value) || specialistRows.value[0] || null)
  const syncableAiActions = computed(() => {
    const rows = [
      ...metaActions.value,
      ...priorityRows.value.map((item: any) => item?.action || item?.recommendation || item?.summary || item?.title || ''),
      ...specialistRows.value.flatMap((item: any) => Array.isArray(item?.recommendations) ? item.recommendations : []),
    ]
    const actions = rows.map((item: any) => {
      if (typeof item === 'string') return item.trim()
      return String(item?.action || item?.recommendation || item?.summary || item?.title || '').trim()
    }).filter(Boolean)
    return Array.from(new Set<string>(actions)).slice(0, 8)
  })
  const systemCards = computed(() => {
    const systems = [
      { agent: 'hemodynamic_agent', domain: 'hemodynamic', label: '循环系统' },
      { agent: 'respiratory_agent', domain: 'respiratory', label: '呼吸系统' },
      { agent: 'infection_agent', domain: 'infection', label: '感染系统' },
      { agent: 'renal_agent', domain: 'renal', label: '肾脏系统' },
      { agent: 'neuro_agent', domain: 'neuro', label: '神经系统' },
      { agent: 'nutrition_agent', domain: 'nutrition', label: '营养代谢' },
      { agent: 'pharmacy_agent', domain: 'pharmacy', label: '药学安全' },
    ]
    return systems.map((item) => {
      const row = specialistRows.value.find((entry: any) => entry.agent === item.agent) || null
      return {
        ...item,
        priority: row?.priority || 'medium',
        hasData: Boolean(row),
        summary: row?.summary || '暂无该系统专科分析结果',
        concerns: row?.concerns || [],
        recommendations: row?.recommendations || [],
        evidence: row?.evidence || [],
      }
    })
  })

  const mdtDomainToOrgan: Record<string, BodyMapOrganKey | ''> = {
    hemodynamic: 'circulatory', respiratory: 'respiratory', infection: 'circulatory',
    renal: 'renal', neuro: 'neurologic', nutrition: 'hepatic', pharmacy: 'coagulation',
  }
  const mdtOrganRows = computed(() => systemCards.value.map((item: any) => {
    const severity = priorityToBodySeverity(item.priority)
    return { ...item, organKey: mdtDomainToOrgan[item.domain] || '', severity, text: bodyMapSeverityText(severity) }
  }).sort((a: any, b: any) => bodySeverityRank(b.severity) - bodySeverityRank(a.severity)))
  const mdtOrganStates = computed(() => {
    const states: Record<string, BodyMapSeverity> = {
      neurologic: 'normal', respiratory: 'normal', circulatory: 'normal',
      hepatic: 'normal', coagulation: 'normal', renal: 'normal',
    }
    for (const row of mdtOrganRows.value) {
      if (!row.organKey) continue
      if (bodySeverityRank(row.severity) > bodySeverityRank(states[row.organKey])) states[row.organKey] = row.severity
    }
    return states
  })
  const mdtOrganTooltips = computed(() => Object.fromEntries(Object.entries(mdtOrganStates.value).map(([key, severity]) => {
    const row = mdtOrganRows.value.find((item: any) => item.organKey === key)
    return [key, {
      label: BODY_MAP_ORGAN_LABELS[key as BodyMapOrganKey] || key,
      statusText: bodyMapSeverityText(severity),
      detail: row?.summary ? shortText(row.summary, 34) : '暂无突出专科意见',
      severity,
    }]
  })))
  const isGeneratingAssessment = computed(() => Boolean(selectedPatientId.value) && loading.value && !specialistRows.value.length)

  const decisionRows = computed<MdtDecision[]>(() => decisions.value.length ? decisions.value : [{
    id: 'decision-1',
    action: metaActions.value[0] || '等待 MDT 形成结构化决议后展示执行追踪。',
    owner: '值班医生', deadline: '6h', monitoring: '按系统指标复评', review_time: '6h',
    status: 'pending_confirmation', note: '', requires_confirmation: true, confirmation_status: 'pending',
  }])
  const pendingConfirmationCount = computed(() => decisionRows.value.filter((item) => needsDoctorConfirmation(item)).length)
  const pendingDecisionCount = computed(() => decisionRows.value.filter((item) => ['doctor_confirmed', 'pending'].includes(String(item.status || '').toLowerCase())).length)
  const inProgressDecisionCount = computed(() => decisionRows.value.filter((item) => String(item.status || '') === 'in_progress').length)
  const completedDecisionCount = computed(() => decisionRows.value.filter((item) => String(item.status || '') === 'completed').length)
  const dismissedDecisionCount = computed(() => decisionRows.value.filter((item) => ['dismissed', 'rejected'].includes(String(item.status || '').toLowerCase())).length)
  const guidedDecisionRows = computed(() => decisionRows.value.slice(0, 6))

  const closurePercent = computed(() => {
    const total = decisionRows.value.length
    if (!total) return 0
    return Math.round((completedDecisionCount.value / total) * 100)
  })

  const latestGeneratedDocuments = computed(() =>
    workspaceDocuments.value.reduce((acc: Record<string, any>, item: any) => {
      const key = String(item?.doc_type || '')
      if (key && !acc[key]) acc[key] = item
      return acc
    }, {})
  )
  const documentStatusRows = computed(() => [
    { key: 'mdt_summary', label: '讨论材料', status: latestGeneratedDocuments.value.mdt_summary ? '已生成' : '待生成', detail: latestGeneratedDocuments.value.mdt_summary ? '可继续刷新' : '建议会前先生成' },
    { key: 'consultation_request', label: '会诊记录', status: consultRecord.value ? '已填写' : '待填写', detail: consultRecord.value ? `${consultRecord.value.length} 字` : '可由 AI 生成' },
    { key: 'daily_progress', label: '病程记录', status: progressRecord.value ? '已填写' : '待填写', detail: progressRecord.value ? `${progressRecord.value.length} 字` : '可由 AI 生成' },
  ])
  const mdtSummarySections = computed(() => {
    const doc = latestGeneratedDocuments.value.mdt_summary?.document || {}
    const sections = Array.isArray(doc.sections) ? doc.sections : []
    return sections
      .map((item: any) => ({ heading: String(item?.heading || '').trim(), content: String(item?.content || '').trim() }))
      .filter((item: any) => item.heading && item.content)
      .slice(0, 6)
  })
  const latestMdtDocumentPreview = computed(() => {
    if (mdtSummarySections.value.length) {
      return mdtSummarySections.value.map((item: any) => `${item.heading}：${shortText(item.content, 80)}`).join('\n')
    }
    return shortText(latestGeneratedDocuments.value.mdt_summary?.document?.document_text || latestGeneratedDocuments.value.mdt_summary?.summary || '已生成', 220)
  })

  const isSessionClosed = computed(() => String(workspaceRecord.value?.phase || '') === 'closed')
  const workspaceDirty = computed(() => {
    const snapshot = JSON.stringify({
      session_id: currentSessionId.value || '',
      phase: workspaceRecord.value?.phase || 'finalizing',
      decisions: decisions.value,
      consult_record: consultRecord.value,
      progress_record: progressRecord.value,
      final_summary: finalSummary.value,
      participants: sessionParticipants.value,
      tags: sessionTags.value,
      order_drafts: generatedOrderDrafts.value,
      template_name: selectedTemplateKey.value,
      activity_log: activityLog.value,
    })
    return Boolean(lastSavedSnapshot.value) && snapshot !== lastSavedSnapshot.value
  })
  const visibleWorkspaceSessions = computed(() =>
    workspaceSessions.value
      .filter((item: any) => {
        if (sessionListOpenOnly.value && String(item.phase || '') === 'closed') return false
        if (sessionPhaseFilter.value && String(item.phase || '') !== sessionPhaseFilter.value) return false
        const q = sessionSearch.value.trim().toLowerCase()
        if (!q) return true
        const hay = `${item.title || ''} ${item.summary || ''}`.toLowerCase()
        return hay.includes(q)
      })
      .sort((a: any, b: any) => {
        const aClosed = String(a?.phase || '') === 'closed' ? 1 : 0
        const bClosed = String(b?.phase || '') === 'closed' ? 1 : 0
        if (aClosed !== bClosed) return aClosed - bClosed
        return new Date(b?.updated_at || 0).getTime() - new Date(a?.updated_at || 0).getTime()
      })
  )
  const sessionParticipants = computed(() => participantsText.value.split(/[\n,，;；]+/g).map((item) => item.trim()).filter(Boolean))
  const sessionTags = computed(() => tagsText.value.split(/[\n,，;；]+/g).map((item) => item.trim()).filter(Boolean))

  const patientHeadline = computed(() => patient.value?.name || patient.value?.hisName || '未选择患者')
  const patientSubline = computed(() => {
    if (selectedPatientId.value && loading.value && !patient.value) return '患者信息加载中'
    if (!patient.value) return '可从患者详情页带入，或在本页直接选择'
    const bed = patient.value?.hisBed || patient.value?.bed || '--'
    const diagnosis = patient.value?.clinicalDiagnosis || patient.value?.admissionDiagnosis || '暂无诊断'
    return `${bed}床 · ${diagnosis}`
  })
  const selectedPatientLabel = computed(() => {
    if (patient.value) {
      const bed = patient.value?.hisBed || patient.value?.bed || '--'
      return `${bed}床 · ${patientHeadline.value}`
    }
    return selectedPatientId.value ? '患者已选择' : '未选择患者'
  })
  const selectedPatientOutOfDeptHint = computed(() => {
    const selected = patients.value.find((item: any) => String(item?._id || '') === String(selectedPatientId.value || ''))
    return selected?.__mdtFallbackCurrent ? '当前患者不在当前科室在线列表中。' : ''
  })

  const mdtSeverityTone = computed(() => {
    if (conflictRows.value.length >= 2) return 'critical'
    if (priorityRows.value.some((item: any) => String(item.priority || '').toLowerCase() === 'critical')) return 'critical'
    if (conflictRows.value.length || priorityRows.value.some((item: any) => String(item.priority || '').toLowerCase() === 'high')) return 'warning'
    return 'soft'
  })
  const mdtSeverityLabel = computed(() => {
    return ({ critical: '高风险', warning: '需关注', soft: '相对平稳' } as Record<string, string>)[mdtSeverityTone.value] || '相对平稳'
  })

  const autoSessionSummary = computed(() => {
    const parts: string[] = []
    if (metaSummary.value) parts.push(`总控结论：${metaSummary.value}`)
    if (conflictRows.value.length) parts.push(`冲突焦点：${conflictRows.value.map((item: any) => item.summary || '跨专科冲突').slice(0, 2).join('；')}`)
    if (metaActions.value.length) parts.push(`关键动作：${metaActions.value.slice(0, 3).join('；')}`)
    if (pendingConfirmationCount.value || pendingDecisionCount.value || inProgressDecisionCount.value || completedDecisionCount.value) {
      parts.push(`执行概况：待确认${pendingConfirmationCount.value}，待执行${pendingDecisionCount.value}，进行中${inProgressDecisionCount.value}，已完成${completedDecisionCount.value}`)
    }
    return parts.join('\n')
  })

  const todoRows = computed(() =>
    decisionRows.value
      .filter((item) => ['pending', 'in_progress', 'pending_confirmation'].includes(String(item.status || 'pending')))
      .slice(0, 5)
  )
  const nextActionText = computed(() => metaActions.value[0] || todoRows.value[0]?.action || '等待总控智能体生成行动建议')

  const mdtStepRows = computed<MdtStepRow[]>(() => [
    { key: 'patient', index: '01', title: '选择患者', desc: '选择患者并生成 MDT', done: Boolean(selectedPatientId.value && assessmentResult.value) },
    { key: 'review', index: '02', title: '审阅意见', desc: '总控结论与专科意见', done: Boolean(decisionRows.value.length || syncableAiActions.value.length) },
    { key: 'decision', index: '03', title: '决议确认', desc: '形成决议并确认', done: decisionRows.value.length > 0 && pendingConfirmationCount.value === 0 },
    { key: 'archive', index: '04', title: '文书归档', desc: '生成记录并归档', done: isSessionClosed.value },
  ])

  // ── 操作方法 ──────────────────────────────────────

  function appendActivityLog(title: string, detail: string) {
    activityLog.value = [{ title, detail, created_at: new Date().toISOString() }, ...activityLog.value].slice(0, 80)
  }

  function setPhase(phase: 'collecting' | 'conflict_review' | 'finalizing' | 'closed') {
    workspaceRecord.value = { ...(workspaceRecord.value || {}), phase }
    appendActivityLog('切换阶段', `当前会话进入${phaseLabel(phase)}`)
  }

  function stepFromPhase(phase?: string) {
    if (phase === 'collecting') return 'patient' as const
    if (phase === 'conflict_review') return 'review' as const
    if (phase === 'finalizing') return 'decision' as const
    if (phase === 'closed') return 'archive' as const
    return 'patient' as const
  }

  function phaseFromStep(step: string) {
    if (step === 'patient') return 'collecting'
    if (step === 'review') return 'conflict_review'
    if (step === 'decision') return 'finalizing'
    if (step === 'archive') return 'finalizing'
    return 'collecting'
  }

  function goMdtStep(step: 'patient' | 'review' | 'decision' | 'archive') {
    currentMdtStep.value = step
    setPhase(phaseFromStep(step) as 'collecting' | 'conflict_review' | 'finalizing' | 'closed')
  }

  function selectSpecialist(agent: string) {
    activeAgent.value = agent
  }

  async function loadPatientOptions() {
    const deptCode = String(route.query.deptCode || route.query.dept_code || '')
    const res = await getPatients(deptCode ? { dept_code: deptCode, patient_scope: 'in_dept' } : { patient_scope: 'in_dept' })
    const list = Array.isArray(res.data?.patients) ? res.data.patients : []
    const currentId = String(selectedPatientId.value || route.query.patient_id || route.query.patientId || '').trim()
    if (currentId && !list.some((item: any) => String(item?._id || '') === currentId)) {
      try {
        const detailRes = await getPatientDetail(currentId)
        const currentPatient = detailRes.data?.patient
        if (currentPatient?._id) list.unshift({ ...currentPatient, __mdtFallbackCurrent: true })
      } catch { /* ignore */ }
    }
    patients.value = list
  }

  async function loadWorkspaceExtras(patientId: string) {
    const [trendRes, drugsRes, alertsRes, workspaceRes, systemPanelsRes] = await Promise.all([
      getPatientVitalsTrend(patientId, trendWindow.value === '72h' ? '48h' : '24h'),
      getPatientDrugs(patientId),
      getPatientAlerts(patientId),
      getAiMdtWorkspace(patientId),
      getAiSystemPanels(patientId, { window: trendWindow.value }),
    ])
    vitalsTrendPoints.value = Array.isArray(trendRes.data?.points) ? trendRes.data.points : []
    drugs.value = Array.isArray(drugsRes.data?.records) ? drugsRes.data.records : []
    alerts.value = Array.isArray(alertsRes.data?.records) ? alertsRes.data.records : []
    workspaceRecord.value = workspaceRes.data?.workspace || null
    workspaceDocuments.value = Array.isArray(workspaceRes.data?.documents) ? workspaceRes.data.documents : []
    generatedOrderDrafts.value = Array.isArray(workspaceRes.data?.order_drafts) ? workspaceRes.data.order_drafts : []
    workspaceSessions.value = Array.isArray(workspaceRes.data?.sessions) ? workspaceRes.data.sessions : []
    currentSessionId.value = String(workspaceRecord.value?.session_id || workspaceSessions.value[0]?.session_id || '')
    activityLog.value = Array.isArray(workspaceRecord.value?.activity_log) ? workspaceRecord.value.activity_log : []
    selectedTemplateKey.value = String(workspaceRecord.value?.template_name || '')
    systemPanels.value = systemPanelsRes.data?.panels || {}
    decisions.value = Array.isArray(workspaceRecord.value?.decisions) && workspaceRecord.value.decisions.length
      ? normalizeDecisionList(workspaceRecord.value.decisions)
      : metaActions.value.slice(0, 4).map((item: string, idx: number) => ({
          id: `decision-${idx + 1}`, action: item, owner: '值班医生', deadline: idx === 0 ? '立即' : '6h',
          monitoring: '按系统指标复评', review_time: '6h', status: 'pending_confirmation', note: '',
          requires_confirmation: true, confirmation_status: 'pending',
        }))
    consultRecord.value = String(workspaceRecord.value?.consult_record || '')
    progressRecord.value = String(workspaceRecord.value?.progress_record || '')
    finalSummary.value = String(workspaceRecord.value?.final_summary || '')
    participantsText.value = Array.isArray(workspaceRecord.value?.participants) ? workspaceRecord.value.participants.join('、') : ''
    tagsText.value = Array.isArray(workspaceRecord.value?.tags) ? workspaceRecord.value.tags.join('、') : ''
    lastSavedSnapshot.value = JSON.stringify({
      session_id: currentSessionId.value || '', phase: workspaceRecord.value?.phase || 'finalizing',
      decisions: decisions.value, consult_record: consultRecord.value, progress_record: progressRecord.value,
      final_summary: finalSummary.value, participants: sessionParticipants.value, tags: sessionTags.value,
      order_drafts: generatedOrderDrafts.value, template_name: selectedTemplateKey.value, activity_log: activityLog.value,
    })
  }

  async function loadAssessment(refresh = false) {
    if (!selectedPatientId.value) return
    const loadToken = currentLoadToken.value + 1
    currentLoadToken.value = loadToken
    loading.value = true
    error.value = ''
    assessment.value = null
    systemPanels.value = {}
    activeAgent.value = ''
    try {
      const [patientRes, assessmentRes] = await Promise.all([
        getPatientDetail(selectedPatientId.value),
        getAiMultiAgentAssessment(selectedPatientId.value, { refresh }),
        loadWorkspaceExtras(selectedPatientId.value),
      ])
      if (loadToken !== currentLoadToken.value) return
      patient.value = patientRes.data?.patient || null
      assessment.value = assessmentRes.data || null
      activeAgent.value = specialistRows.value[0]?.agent || ''
      if (!decisions.value.length && metaActions.value.length) {
        decisions.value = metaActions.value.slice(0, 4).map((item: string, idx: number) => normalizeDecision({
          id: `decision-${idx + 1}`, action: item, owner: '值班医生', deadline: idx === 0 ? '立即' : '6h',
          monitoring: '按系统指标复评', review_time: '6h', status: 'pending_confirmation', note: '',
        }, idx))
      }
    } catch {
      if (loadToken !== currentLoadToken.value) return
      error.value = 'MDT 会诊加载失败，请检查患者数据和后端多智能体接口。'
    } finally {
      if (loadToken === currentLoadToken.value) loading.value = false
    }
  }

  function handleGenerateAssessment() {
    if (!selectedPatientId.value) { message.warning('请先选择患者'); return }
    void loadAssessment(true)
  }

  async function saveWorkspace() {
    if (!selectedPatientId.value) return
    savingWorkspace.value = true
    try {
      const res = await saveAiMdtWorkspace(selectedPatientId.value, {
        session_id: currentSessionId.value || undefined,
        phase: workspaceRecord.value?.phase || 'finalizing',
        decisions: decisions.value, consult_record: consultRecord.value, progress_record: progressRecord.value,
        final_summary: finalSummary.value, participants: sessionParticipants.value, tags: sessionTags.value,
        order_drafts: generatedOrderDrafts.value, template_name: selectedTemplateKey.value || undefined,
        activity_log: activityLog.value,
      })
      workspaceRecord.value = res.data?.workspace || null
      currentSessionId.value = String(workspaceRecord.value?.session_id || currentSessionId.value || '')
      const sessionsRes = await listAiMdtWorkspaceSessions(selectedPatientId.value)
      workspaceSessions.value = Array.isArray(sessionsRes.data?.sessions) ? sessionsRes.data.sessions : workspaceSessions.value
      lastSavedSnapshot.value = JSON.stringify({
        session_id: currentSessionId.value || '', phase: workspaceRecord.value?.phase || 'finalizing',
        decisions: decisions.value, consult_record: consultRecord.value, progress_record: progressRecord.value,
        final_summary: finalSummary.value, participants: sessionParticipants.value, tags: sessionTags.value,
        order_drafts: generatedOrderDrafts.value, template_name: selectedTemplateKey.value, activity_log: activityLog.value,
      })
      appendActivityLog('保存会话', `已保存 ${decisions.value.length} 条决议`)
    } finally {
      savingWorkspace.value = false
    }
  }

  async function generateDocument(docType: 'mdt_summary' | 'daily_progress' | 'consultation_request') {
    if (!selectedPatientId.value) return
    generatingDocType.value = docType
    try {
      const res = await generateAiDocument(selectedPatientId.value, { doc_type: docType, time_range: { hours: trendWindow.value === '72h' ? 72 : 24 } })
      const doc = res.data?.document
      if (doc) {
        workspaceDocuments.value = [doc, ...workspaceDocuments.value.filter((item: any) => item?._id !== doc?._id)]
        const text = extractGeneratedDocumentText(doc, docType)
        if (docType === 'consultation_request') consultRecord.value = text
        if (docType === 'daily_progress') progressRecord.value = text
        appendActivityLog('生成文书', `${({ mdt_summary: '讨论材料', daily_progress: '病程记录', consultation_request: '会诊记录' } as Record<string, string>)[docType] || docType} 已更新`)
      }
    } finally {
      generatingDocType.value = ''
    }
  }

  function addDecision() {
    decisions.value = [...decisions.value, {
      id: `decision-${Date.now()}`, action: '', owner: '值班医生', deadline: '6h',
      monitoring: '按系统指标复评', review_time: '6h', status: 'pending_confirmation', note: '',
      requires_confirmation: true, confirmation_status: 'pending',
    }]
    appendActivityLog('新增决议', '已新增 1 条决议')
  }

  function removeDecision(id: string) {
    const hit = decisions.value.find((item) => item.id === id)
    decisions.value = decisions.value.filter((item) => item.id !== id)
    appendActivityLog('删除决议', hit?.action || '已删除 1 条决议')
  }

  function markDecisionStatus(id: string, status: string) {
    let action = ''
    decisions.value = decisions.value.map((item) => {
      if (item.id === id) {
        action = item.action || ''
        if (['in_progress', 'completed'].includes(status) && needsDoctorConfirmation(item)) {
          message.warning('该 AI 建议尚未由医生确认，不能直接进入执行状态')
          return item
        }
        return { ...item, status }
      }
      return item
    })
    appendActivityLog('更新决议状态', `${action || '决议'} -> ${decisionStatusLabel(status)}`)
  }

  async function confirmDecision(row: any, action: 'confirm' | 'reject' | 'revise' = 'confirm') {
    if (!selectedPatientId.value || !currentSessionId.value || !row?.id) {
      message.warning('请先保存 MDT 会话，再进行医生确认')
      return
    }
    const actor = getOperatorIdentity() || 'doctor'
    const id = String(row.id)
    confirmingDecisionIds.value = new Set([...confirmingDecisionIds.value, id])
    try {
      const res = await postAiMdtDecisionConfirm(selectedPatientId.value, currentSessionId.value, id, {
        action, actor, note: row.note || '', expected_version: Number(row.version || 1),
      })
      if (Number(res.data?.code) !== 0) throw new Error(res.data?.message || '确认失败')
      const next = res.data?.decision || {}
      decisions.value = decisions.value.map((item) => item.id === id ? normalizeDecision({ ...item, ...next }, 0) : item)
      appendActivityLog(action === 'confirm' ? '医生确认' : '医生反馈', `${row.action || '决议'} -> ${decisionStatusLabel(next.status)}`)
      message.success(action === 'confirm' ? '医生已确认' : '已记录反馈')
    } catch (err: any) {
      message.error(err?.response?.data?.message || err?.message || '确认失败')
    } finally {
      const nextSet = new Set(confirmingDecisionIds.value)
      nextSet.delete(id)
      confirmingDecisionIds.value = nextSet
    }
  }

  function fillDecisionDefaults() {
    if (isSessionClosed.value) return
    decisions.value = decisionRows.value.map((item, idx) => ({
      ...item,
      id: item.id || `decision-${Date.now()}-${idx}`,
      owner: String(item.owner || '').trim() || '值班医生',
      deadline: String(item.deadline || '').trim() || (idx === 0 ? '立即' : '6h'),
      monitoring: String(item.monitoring || '').trim() || '按系统指标复评',
      review_time: String(item.review_time || '').trim() || '6h',
      status: String(item.status || '').trim() || 'pending_confirmation',
      requires_confirmation: item.requires_confirmation === false ? false : true,
      confirmation_status: item.confirmation_status || (item.confirmed_at ? 'confirmed' : 'pending'),
    }))
    appendActivityLog('补全决议字段', '已补全负责人、时限、监测指标与复评时间')
  }

  function syncDecisionsFromMetaActions() {
    if (isSessionClosed.value) { message.warning('已归档，不能同步'); return }
    if (!syncableAiActions.value.length) { message.info('暂无可同步动作'); return }
    const existing = new Set(decisions.value.map((item) => String(item.action || '').trim()).filter(Boolean))
    const additions = syncableAiActions.value
      .filter((item) => !existing.has(String(item || '').trim()))
      .map((item, idx) => ({
        id: `decision-ai-${Date.now()}-${idx}`, action: item, owner: '值班医生',
        deadline: idx === 0 ? '立即' : '6h', monitoring: '按系统指标复评', review_time: '6h',
        status: 'pending_confirmation', note: '由总控智能体同步，需医生确认',
        requires_confirmation: true, confirmation_status: 'pending',
      }))
    if (!additions.length) { message.info('AI 动作已在决议列表中'); return }
    decisions.value = [...decisions.value, ...additions]
    appendActivityLog('同步 AI 动作', `已追加 ${additions.length} 条`)
    message.success(`已同步 ${additions.length} 条 AI 动作`)
  }

  async function switchSession(sessionId: string) {
    if (!selectedPatientId.value || !sessionId) return
    if (workspaceDirty.value && !window.confirm('有未保存变更，确认切换？')) return
    const res = await getAiMdtWorkspaceSession(selectedPatientId.value, sessionId)
    workspaceRecord.value = res.data?.workspace || null
    workspaceDocuments.value = Array.isArray(res.data?.documents) ? res.data.documents : []
    generatedOrderDrafts.value = Array.isArray(res.data?.order_drafts) ? res.data.order_drafts : []
    currentSessionId.value = sessionId
    decisions.value = Array.isArray(workspaceRecord.value?.decisions) ? normalizeDecisionList(workspaceRecord.value.decisions) : []
    consultRecord.value = String(workspaceRecord.value?.consult_record || '')
    progressRecord.value = String(workspaceRecord.value?.progress_record || '')
    finalSummary.value = String(workspaceRecord.value?.final_summary || '')
    participantsText.value = Array.isArray(workspaceRecord.value?.participants) ? workspaceRecord.value.participants.join('、') : ''
    tagsText.value = Array.isArray(workspaceRecord.value?.tags) ? workspaceRecord.value.tags.join('、') : ''
    activityLog.value = Array.isArray(workspaceRecord.value?.activity_log) ? workspaceRecord.value.activity_log : []
    selectedTemplateKey.value = String(workspaceRecord.value?.template_name || '')
    lastSavedSnapshot.value = ''
  }

  function startNewSession() {
    if (workspaceDirty.value && !window.confirm('有未保存变更，确认新建？')) return
    currentSessionId.value = ''
    workspaceRecord.value = { phase: 'collecting' }
    decisions.value = metaActions.value.slice(0, 4).map((item: string, idx: number) => normalizeDecision({
      id: `decision-${idx + 1}`, action: item, owner: '值班医生', deadline: idx === 0 ? '立即' : '6h',
      monitoring: '按系统指标复评', review_time: '6h', status: 'pending_confirmation', note: '',
    }, idx))
    consultRecord.value = ''; progressRecord.value = ''; finalSummary.value = ''
    participantsText.value = ''; tagsText.value = ''; selectedTemplateKey.value = ''
    activityLog.value = []
    appendActivityLog('新建会话', '已新建一轮 MDT 会诊')
    lastSavedSnapshot.value = ''
  }

  function duplicateCurrentSession() {
    if (!currentSessionId.value) return
    currentSessionId.value = ''
    workspaceRecord.value = { ...(workspaceRecord.value || {}), phase: 'collecting' }
    decisions.value = decisions.value.map((item, idx) => normalizeDecision({ ...item, id: `decision-${Date.now()}-${idx}`, status: 'pending_confirmation', confirmed_at: null, confirmed_by: null, requires_confirmation: true }, idx))
    generatedOrderDrafts.value = generatedOrderDrafts.value.map((item: any, idx: number) => ({ ...item, id: `order-${Date.now()}-${idx}` }))
    finalSummary.value = finalSummary.value || autoSessionSummary.value
    activityLog.value = [{ title: '复制会话', detail: `由 ${currentSessionLabel.value} 复制`, created_at: new Date().toISOString() }, ...activityLog.value].slice(0, 80)
    lastSavedSnapshot.value = ''
  }

  function exportCurrentSession() {
    const payload = {
      session_id: currentSessionId.value || null, title: currentSessionLabel.value,
      phase: workspaceRecord.value?.phase || 'finalizing',
      patient: { id: selectedPatientId.value, name: patientHeadline.value, summary: patientSubline.value },
      summary: metaSummary.value, template_name: selectedTemplateKey.value || null,
      actions: metaActions.value, conflicts: conflictRows.value, decisions: decisions.value,
      consult_record: consultRecord.value, progress_record: progressRecord.value,
      final_summary: finalSummary.value, participants: sessionParticipants.value, tags: sessionTags.value,
      activity_log: activityLog.value, order_drafts: generatedOrderDrafts.value,
      exported_at: new Date().toISOString(),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `mdt_session_${currentSessionId.value || Date.now()}.json`; a.click()
    URL.revokeObjectURL(url)
  }

  async function closeCurrentSession() {
    if (!consultRecord.value.trim()) consultRecord.value = autoSessionSummary.value
    if (!progressRecord.value.trim()) progressRecord.value = autoSessionSummary.value
    setPhase('closed')
    await saveWorkspace()
  }

  function reopenCurrentSession() {
    if (!isSessionClosed.value) return
    setPhase('collecting')
    appendActivityLog('复开会话', '已恢复为收集中')
  }

  async function copyText(text: string, successText = '已复制') {
    const value = String(text || '').trim()
    if (!value) return
    try { await navigator.clipboard.writeText(value); appendActivityLog('复制', successText) }
    catch { error.value = '复制失败' }
  }

  function extractGeneratedDocumentText(doc: any, docType: string): string {
    const document = doc?.document || {}
    const rawText = String(document?.document_text || '').trim()
    const sections = Array.isArray(document?.sections) ? document.sections : []
    const sectionText = sections
      .map((item: any) => { const h = String(item?.heading || '').trim(); const c = String(item?.content || '').trim(); return h && c ? `${h}：${c}` : '' })
      .filter(Boolean).join('\n')
    const text = rawText || sectionText
    if (text) return text
    if (docType === 'consultation_request') {
      return ['会诊目的：请相关专科协助评估。', `患者概况：${patientHeadline.value}，${patientSubline.value}。`, '申请原因：请结合 MDT 冲突焦点补充。', '需协助事项：明确诊断、治疗方向、风险边界和复评时间。'].join('\n')
    }
    if (docType === 'daily_progress') {
      return ['病情变化：请补充近24小时变化。', `今日评估：${patientHeadline.value}，${patientSubline.value}。`, '处理经过：请补充已执行处置。', '后续计划：继续按 MDT 决议复评。'].join('\n')
    }
    return ''
  }

  const currentSessionLabel = computed(() => {
    const hit = workspaceSessions.value.find((item: any) => String(item.session_id || '') === String(currentSessionId.value || ''))
    return hit?.title || '当前会话'
  })

  function openPatientDetail() {
    if (!selectedPatientId.value) return
    router.push({ path: `/patient/${selectedPatientId.value}`, query: { tab: 'twin' } })
  }

  // ── 生命周期 ──────────────────────────────────────

  watch(() => route.query.patient_id ?? route.query.patientId, (value) => {
    const next = String(Array.isArray(value) ? value[0] : value || '').trim()
    if (next && next !== selectedPatientId.value) selectedPatientId.value = next
  }, { immediate: true })

  watch(selectedPatientId, (value, oldValue) => {
    if (!value) return
    if (workspaceDirty.value && !window.confirm('有未保存变更，确认切换患者？')) {
      selectedPatientId.value = String(oldValue || ''); return
    }
    router.replace({ path: '/mdt', query: { ...route.query, patient_id: value } })
    void loadAssessment(false)
  })

  watch(trendWindow, () => {
    if (selectedPatientId.value) void loadWorkspaceExtras(selectedPatientId.value)
  })

  watch(() => workspaceRecord.value?.phase, (phase) => {
    const next = stepFromPhase(String(phase || ''))
    if (currentMdtStep.value !== next) currentMdtStep.value = next
  })

  watch(currentMdtStep, (step, previous) => {
    if (step === previous) return
    const nextPhase = phaseFromStep(step)
    if (String(workspaceRecord.value?.phase || '') !== nextPhase) {
      setPhase(nextPhase as 'collecting' | 'conflict_review' | 'finalizing' | 'closed')
    }
  })

  onMounted(async () => {
    try {
      await loadPatientOptions()
      if (!selectedPatientId.value && patientOptions.value.length) {
        selectedPatientId.value = patientOptions.value[0]?.value || ''
      }
    } catch { error.value = '患者列表加载失败' }
  })

  return {
    // 状态
    loading, error, patients, patient, assessment, selectedPatientId, activeAgent,
    trendWindow, vitalsTrendPoints, drugs, alerts, systemPanels,
    workspaceRecord, workspaceDocuments, generatedOrderDrafts, decisions,
    consultRecord, progressRecord, finalSummary, participantsText, tagsText,
    savingWorkspace, generatingDocType, workspaceSessions, currentSessionId,
    currentMdtStep, sessionDrawerOpen, sessionListOpenOnly, sessionSearch,
    sessionPhaseFilter, selectedTemplateKey, activityLog, confirmingDecisionIds,
    // 派生
    patientOptions, assessmentRecord, assessmentResult, specialistRows, conflictRows,
    metaSummary, metaActions, priorityRows, activeSpecialist, syncableAiActions,
    systemCards, mdtOrganRows, mdtOrganStates, mdtOrganTooltips, isGeneratingAssessment,
    decisionRows, pendingConfirmationCount, pendingDecisionCount, inProgressDecisionCount,
    completedDecisionCount, dismissedDecisionCount, guidedDecisionRows,
    closurePercent, documentStatusRows, latestMdtDocumentPreview, mdtSummarySections,
    isSessionClosed, workspaceDirty, visibleWorkspaceSessions,
    sessionParticipants, sessionTags, patientHeadline, patientSubline,
    selectedPatientLabel, selectedPatientOutOfDeptHint,
    mdtSeverityTone, mdtSeverityLabel, autoSessionSummary, todoRows, nextActionText,
    mdtStepRows, currentSessionLabel,
    // 方法
    loadPatientOptions, loadAssessment, handleGenerateAssessment, saveWorkspace,
    generateDocument, addDecision, removeDecision, markDecisionStatus, confirmDecision,
    fillDecisionDefaults, syncDecisionsFromMetaActions, switchSession, startNewSession,
    duplicateCurrentSession, exportCurrentSession, closeCurrentSession, reopenCurrentSession,
    copyText, goMdtStep, selectSpecialist, openPatientDetail, appendActivityLog,
  }
}
