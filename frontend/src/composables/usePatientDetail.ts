/**
 * usePatientDetail — 患者详情页核心 composable
 *
 * 集中管理患者身份、生命体征、预警、脓毒症 Bundle、脱机评估等共享状态。
 * 各子页面/组件通过 usePatientDetail() 获取响应式数据，无需重复请求。
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  getPatientDetail,
  getPatientBedcard,
  getPatientVitals,
  getPatientLabs,
  getPatientVitalsTrend,
  getPatientDrugs,
  getPatientAssessments,
  getPatientAlerts,
  getPatientClinicalSummary,
  postPatientAlertsViewed,
  postAlertAcknowledge,
  postAlertDisposition,
  getPatientSepsisBundleStatus,
  submitSepsisBundleElementReview,
  recordSepsisBundleExecution,
  getPatientWeaningTimeline,
  getPatientSimilarCaseOutcomes,
  getPatientWeaningStatus,
  getAiLabSummary,
  getAiRuleRecommendations,
  getAiRiskForecast,
  getAiIntegratedRiskReport,
  getAiMetabolicPhase,
  getAiBetaBlockerAdvisor,
  getAiFibrinolysisMonitor,
  getAiPronePositionMonitor,
  getAiPicsRisk,
  getPatientHandoffSummary,
  getKnowledgeChunk,
  getKnowledgeDocument,
  getKnowledgeDocuments,
  getKnowledgeStatus,
  postAiFeedback,
  reviewPatientPersonalizedThreshold,
  getPatientPersonalizedThresholdHistory,
  getPatientPersonalizedThresholds,
  reloadKnowledge,
  getWaveformChannels,
  getWaveformSegments,
  getWaveformQuality,
  getWaveformEvents,
} from '../api'
import { getOperatorIdentity } from '../utils/operatorIdentity'
import { useRuntimePublicConfigStore } from '../stores/runtimePublicConfig'
import { useVitalForecast } from './useVitalForecast'
import { onAlertMessage } from '../services/alertSocket'
import {
  buildDeviceMarkers,
  buildPatientOrganStateFromAlerts,
  normalizeBodyMapOrganKey,
} from '../utils/bodyMap'

// ─── Types ───
export type DetailTabKey =
  | 'ecash' | 'mobility' | 'pe' | 'trend' | 'waveform' | 'labs'
  | 'drugs' | 'assess' | 'sbt' | 'alerts' | 'similar' | 'followup'
  | 'twin' | 'ai' | 'documents'

export type DetailDensityMode = 'compact' | 'full'
export type DetailTabGroup = 'focus' | 'monitor' | 'therapy' | 'history' | 'ai' | 'all'

// ─── Singleton state ───
// 用模块级变量保证同一路由下多个组件共享同一份数据
let _instance: ReturnType<typeof _createPatientDetail> | null = null
let _currentPatientId: string | null = null

export function usePatientDetail() {
  const route = useRoute()
  const patientId = String(route.params.patientId || route.params.id || '')

  // 切换患者时重置
  if (_instance && _currentPatientId !== patientId) {
    _instance.resetDetailState()
    _instance = null
  }

  if (!_instance) {
    _currentPatientId = patientId
    _instance = _createPatientDetail(patientId)
  }

  return _instance
}

function _createPatientDetail(_initialPatientId: string) {
  const route = useRoute()
  const router = useRouter()
  const runtimePublicConfig = useRuntimePublicConfigStore()
  const vitalForecast = useVitalForecast()

  // ─── Core refs ───
  const patient = ref<any>(null)
  const bedcard = ref<any>(null)
  const vitals = ref<any>(null)
  const alerts = ref<any[]>([])
  const clinicalSummary = ref<any>(null)
  const clinicalSummaryLoading = ref(false)

  // ─── Sepsis bundle ───
  const sepsisBundleStatus = ref<any>(null)
  const sepsisBundleNow = ref(Date.now())
  let sepsisBundleTimer: ReturnType<typeof setInterval> | null = null

  // ─── Weaning / SBT ───
  const weaningStatus = ref<any>(null)
  const sbtTimelineSummary = ref<any>(null)
  const sbtTimelineRecords = ref<any[]>([])
  const sbtTimelineAiSummary = ref<any>(null)
  const sbtTimelineLoading = ref(false)
  const sbtTimelineError = ref('')
  const sbtTimelineLoaded = ref(false)

  // ─── Trend / Waveform / Labs / Drugs / Assessments ───
  const trendWindow = ref('24h')
  const trendPoints = ref<any[]>([])
  const trendLoaded = ref(false)
  const waveformHours = ref(6)
  const waveformSelectedChannel = ref('')
  const waveformChannels = ref<any[]>([])
  const waveformPoints = ref<any[]>([])
  const waveformQc = ref<any>(null)
  const waveformEvents = ref<any[]>([])
  const waveformLoading = ref(false)
  const waveformError = ref('')
  const labs = ref<any[]>([])
  const drugs = ref<any[]>([])
  const assessments = ref<any[]>([])
  const labsLoaded = ref(false)
  const drugsLoaded = ref(false)
  const assessmentsLoaded = ref(false)

  // ─── Similar cases ───
  const similarCaseReview = ref<any>(null)
  const similarCaseLoading = ref(false)
  const similarCaseError = ref('')
  const similarCaseLoaded = ref(false)

  // ─── Personalized thresholds ───
  const personalizedThresholdRecord = ref<any>(null)
  const personalizedThresholdHistory = ref<any[]>([])
  const personalizedThresholdApprovedRecord = ref<any>(null)
  const personalizedThresholdLoading = ref(false)
  const personalizedThresholdError = ref('')
  const personalizedThresholdReviewing = ref(false)
  const thresholdReviewDialogOpen = ref(false)
  const thresholdReviewTarget = ref<any>(null)
  const thresholdReviewStatus = ref<'approved' | 'rejected'>('approved')
  const thresholdReviewReviewer = ref('')
  const thresholdReviewComment = ref('')

  // ─── AI state ───
  const aiLabSummary = ref('')
  const aiRuleText = ref('')
  const aiRulePayload = ref<any[] | null>(null)
  const aiRiskText = ref('')
  const aiRiskForecast = ref<any>(null)
  const integratedRiskReport = ref<any>(null)
  const metabolicPhaseRecord = ref<any>(null)
  const betaBlockerAdvisorRecord = ref<any>(null)
  const fibrinolysisRecord = ref<any>(null)
  const pronePositionRecord = ref<any>(null)
  const picsRiskRecord = ref<any>(null)
  const aiHandoff = ref<any>(null)
  const aiLabError = ref('')
  const aiRuleError = ref('')
  const aiRiskError = ref('')
  const integratedRiskError = ref('')
  const metabolicPhaseError = ref('')
  const betaBlockerAdvisorError = ref('')
  const fibrinolysisError = ref('')
  const pronePositionError = ref('')
  const picsRiskError = ref('')
  const aiHandoffError = ref('')
  const aiLabLoading = ref(false)
  const aiRuleLoading = ref(false)
  const aiRiskLoading = ref(false)
  const integratedRiskLoading = ref(false)
  const metabolicPhaseLoading = ref(false)
  const betaBlockerAdvisorLoading = ref(false)
  const fibrinolysisLoading = ref(false)
  const pronePositionLoading = ref(false)
  const picsRiskLoading = ref(false)
  const aiHandoffLoading = ref(false)
  const aiAutoLoaded = ref(false)

  // ─── Knowledge ───
  const knowledgeDocs = ref<any[]>([])
  const selectedKnowledgeDocId = ref<string>('')
  const selectedKnowledgeDoc = ref<any>(null)
  const knowledgeLoading = ref(false)
  const knowledgeError = ref('')
  const knowledgeStatus = ref<any>(null)

  // ─── Evidence modal ───
  const evidenceModalOpen = ref(false)
  const evidenceModal = ref<any>({
    title: '', source: '', package_name: '', package_version: '',
    category: '', owner: '', updated_at: '', priority: null,
    local_ref: '', recommendation: '', recommendation_grade: '',
    section_title: '', tags: [], content: '', related_chunks: [],
  })

  // ─── Clinical trials ───
  const trialMatches = ref<any[]>([])
  const trialMatchLoading = ref(false)
  const trialMatchError = ref('')

  // ─── WebSocket ───
  let offIntegratedRiskWs: (() => void) | null = null

  // ─── Sepsis bundle dialog state ───
  const sepsisBundleReviewDialogVisible = ref(false)
  const sepsisBundleExecutionDialogVisible = ref(false)
  const sepsisBundleReviewForm = ref({
    element_key: 'fluid_resuscitation',
    applicability: 'individualized',
    individualized_target_ml: undefined as number | undefined,
    reason: '',
    version: 0,
  })
  const sepsisBundleExecutionForm = ref({
    element_key: '',
    status: 'met',
    completed_at: '',
    value: null as any,
    reason: '',
  })
  const sepsisBundleSubmitting = ref(false)

  // ─── Body map ───
  const selectedBodyOrgan = ref('respiratory')
  const focusedAlertTypes = ref<string[]>([])
  const compositeOrganOrder = ['respiratory', 'circulatory', 'renal', 'coagulation', 'hepatic', 'neurologic']
  const compositeOrganLabelDefault: Record<string, string> = {
    respiratory: '呼吸', circulatory: '循环', renal: '肾脏',
    coagulation: '凝血', hepatic: '肝脏', neurologic: '神经',
  }

  // ═══════════════════════════════════════════
  //  Display computed
  // ═══════════════════════════════════════════

  const displayName = computed(() =>
    patient.value?.name || patient.value?.hisName || '加载中...'
  )
  const displaySubTitle = computed(() => {
    const bed = patient.value?.hisBed || patient.value?.bed || '--'
    const gender = patient.value?.genderText || patient.value?.hisSex || ''
    const age = patient.value?.age || patient.value?.hisAge || ''
    return `${bed}床 | ${gender} ${age}`.trim()
  })
  const displayDiagnosis = computed(() =>
    patient.value?.clinicalDiagnosis ||
    patient.value?.admissionDiagnosis ||
    patient.value?.hisDiagnose ||
    '暂无'
  )
  const displayAdmissionTime = computed(() => {
    const raw = patient.value?.icuAdmissionTime || patient.value?.admissionTime
    return fmtTime(raw) || '未知'
  })
  const displayHisPid = computed(() =>
    patient.value?.hisPid || patient.value?.hisPID || '无'
  )
  const displayDept = computed(() =>
    patient.value?.hisDept || patient.value?.dept || '未知科室'
  )
  const displayBed = computed(() =>
    patient.value?.hisBed || patient.value?.bed || '—'
  )
  const displayGenderAge = computed(() =>
    [patient.value?.genderText || patient.value?.hisSex || '', patient.value?.age || patient.value?.hisAge || '']
      .filter(Boolean)
      .join(' ')
  )
  const patientSilhouette = computed<'female' | 'male'>(() => {
    const text = String(patient.value?.gender || patient.value?.genderText || patient.value?.hisSex || '').toLowerCase()
    if (text.includes('female') || text.includes('女')) return 'female'
    if (text.includes('male') || text.includes('男')) return 'male'
    return 'female'
  })

  // ─── Vitals display ───
  const vitalsSourceText = computed(() => {
    if (!vitals.value?.source) return ''
    if (vitals.value.source === 'monitor') return '监护仪'
    if (vitals.value.source === 'nurse_manual') return '护士录入'
    return '未知'
  })
  const heroMonitorUpdatedAt = computed(() => fmtTime(vitals.value?.time) || '—')
  const heroFactRows = computed(() => [
    { label: '患者', value: displayName.value },
    { label: '性别 / 年龄', value: displayGenderAge.value || '—' },
    { label: '科室', value: displayDept.value },
    { label: '床位', value: `${displayBed.value}床` },
  ])
  const heroVitalsRows = computed(() => {
    const v = vitals.value || {}
    return [
      { label: 'HR', value: v?.hr != null ? formatHeroMetric(v.hr) : '—' },
      { label: 'BP', value: fmtBP(v) },
      { label: 'MAP', value: formatHeroMetric(v?.ibp_map ?? v?.nibp_map) },
      { label: 'RR', value: v?.rr != null ? formatHeroMetric(v.rr) : '—' },
      { label: 'SpO₂', value: v?.spo2 != null ? `${formatHeroMetric(v.spo2)}%` : '—' },
      { label: 'T', value: fmtTemp(v?.temp) },
    ]
  })

  // ─── Sepsis bundle computed ───
  const sepsisBundleStatusResolved = computed(() => {
    const status = sepsisBundleStatus.value || {}
    const now = sepsisBundleNow.value
    const rawStatus = String(status?.status || 'none').toLowerCase()
    const deadline1h = status?.deadline_1h ? dayjs(status.deadline_1h).valueOf() : null
    const deadline3h = status?.deadline_3h ? dayjs(status.deadline_3h).valueOf() : null
    let effectiveStatus = rawStatus || 'none'

    if (rawStatus === 'pending') {
      if (typeof deadline3h === 'number' && now >= deadline3h) effectiveStatus = 'overdue_3h'
      else if (typeof deadline1h === 'number' && now >= deadline1h) effectiveStatus = 'overdue_1h'
    }

    const remaining1h = typeof deadline1h === 'number' ? Math.floor((deadline1h - now) / 1000) : null
    const remaining3h = typeof deadline3h === 'number' ? Math.floor((deadline3h - now) / 1000) : null
    const startedAt = status?.bundle_started_at ? dayjs(status.bundle_started_at).valueOf() : null
    const elapsedMinutes = typeof startedAt === 'number' ? Math.max(0, (now - startedAt) / 60000) : null

    let light = String(status?.light || 'gray').toLowerCase()
    let label = String(status?.label || '未进入计时')
    if (effectiveStatus === 'met') { light = 'green'; label = '1h已达标' }
    else if (effectiveStatus === 'met_late') { light = 'orange'; label = '已补执行(超1h)' }
    else if (effectiveStatus === 'overdue_3h') { light = 'red'; label = '3h仍未执行' }
    else if (effectiveStatus === 'overdue_1h') { light = 'red'; label = '1h已超时' }
    else if (effectiveStatus === 'pending') {
      if (remaining1h != null && remaining1h <= 30 * 60) { light = 'yellow'; label = '1h窗口临近' }
      else { light = 'blue'; label = '1h内待完成' }
    }

    return {
      ...status, status: effectiveStatus, light, label,
      remaining_seconds_to_1h: remaining1h,
      remaining_seconds_to_3h: remaining3h,
      elapsed_minutes: elapsedMinutes != null ? Number(elapsedMinutes.toFixed(1)) : null,
    }
  })

  const sepsisBundleStatusLight = computed(() => sepsisBundleStatusResolved.value?.light || 'gray')
  const sepsisBundleStatusText = computed(() => sepsisBundleStatusResolved.value?.label || '未进入计时')
  const sepsisBundleV2Info = computed(() => sepsisBundleStatusResolved.value?.bundle_version === 2)

  const sepsisInfectionVerdictText = computed(() => {
    const v = sepsisBundleStatusResolved.value?.infection_verdict
    const map: Record<string, string> = {
      supported: '感染证据支持', possible: '感染可能',
      not_supported: '无感染证据', unknown: '感染证据不明',
    }
    return map[v] || v || '—'
  })
  const sepsisInfectionLight = computed(() => {
    const v = sepsisBundleStatusResolved.value?.infection_verdict
    if (v === 'supported') return 'green'
    if (v === 'possible') return 'yellow'
    if (v === 'not_supported') return 'red'
    return 'gray'
  })
  const sepsisBundleFluidRiskCautions = computed(() =>
    sepsisBundleStatusResolved.value?.fluid_risk_cautions || []
  )
  const sepsisBundleComplianceSummary = computed(() => {
    const c = sepsisBundleStatusResolved.value?.bundle_compliance
    if (!c) return ''
    const ratio = c.compliance_ratio != null ? `${(c.compliance_ratio * 100).toFixed(0)}%` : '—'
    const denom = c.applicable_confirmed ?? 0
    const num = c.completed_on_time ?? 0
    let extra = ''
    if (c.review_pending_count) extra += ` 待确认${c.review_pending_count}`
    if (c.not_applicable_count) extra += ` 不适用${c.not_applicable_count}`
    if (c.contraindicated_count) extra += ` 禁忌${c.contraindicated_count}`
    if (c.data_missing_count) extra += ` 缺数据${c.data_missing_count}`
    return `合规率 ${ratio} (${num}/${denom})${extra}`
  })
  const sepsisBundleHasReviewPending = computed(() => {
    const elements = sepsisBundleStatusResolved.value?.bundle_elements
    if (!elements) return false
    return Object.values(elements).some((item: any) => {
      const a = item?.applicability
      const cr = item?.clinical_review
      return a === 'review_pending' || cr?.status === 'pending'
    })
  })
  const sepsisBundleConclusion = computed(() => {
    const status = sepsisBundleStatusResolved.value
    const name = status?.first_antibiotic_name ? ` · ${status.first_antibiotic_name}` : ''
    const isV2 = status?.bundle_version === 2
    if (status?.status === 'met') return `Hour-1 Bundle 已在 1 小时内完成${name}`
    if (status?.status === 'met_late') return `Bundle 已补执行，但超过 1h 时限${name}`
    if (status?.status === 'overdue_3h') return 'Bundle 已超过 3h 仍未完成'
    if (status?.status === 'overdue_1h') return 'Bundle 已超过 1h 未完成'
    if (status?.status === 'pending') {
      return isV2
        ? `已检出感染+器官功能异常，进入筛查计时${name}`
        : `已进入脓毒症救治清单计时，请盯紧首剂抗生素${name}`
    }
    return '未进入脓毒症 1 小时集束化治疗计时'
  })
  const sepsisBundleTimelineText = computed(() => {
    const r = sepsisBundleStatusResolved.value
    if (r?.status === 'met' || r?.status === 'met_late') {
      return r.elapsed_minutes != null ? `耗时 ${r.elapsed_minutes} 分钟` : ''
    }
    if (r?.remaining_seconds_to_1h != null) return `距 1h 时限 ${formatCountdown(r.remaining_seconds_to_1h)}`
    return ''
  })
  const sepsisBundleExtraText = computed(() => {
    const r = sepsisBundleStatusResolved.value
    if (r?.status === 'pending' && r.remaining_seconds_to_3h != null) {
      return `距 3h 时限 ${formatCountdown(r.remaining_seconds_to_3h)}`
    }
    return ''
  })

  const sepsisBundleReviewableElements = computed(() => {
    const elements = sepsisBundleStatusResolved.value?.bundle_elements
    if (!elements) return []
    return Object.entries(elements)
      .filter(([, item]: [string, any]) => item?.clinical_review?.status === 'pending' || item?.applicability === 'review_pending')
      .map(([key, item]: [string, any]) => ({
        key,
        applicability: item?.applicability || 'review_pending',
        version: item?.clinical_review?.version || 0,
        label: ({
          fluid_resuscitation: '液体复苏', antibiotic_assessment: '抗菌药评估',
          lactate: '乳酸检测', lactate_repeat: '乳酸复测',
          blood_culture: '血培养', infection_source: '感染灶评估',
          clinician_path_confirmation: '路径确认',
        } as Record<string, string>)[key] || key,
      }))
  })

  // ─── Weaning computed ───
  const weaningAssessment = computed(() => weaningStatus.value?.weaning || {})
  const sbtAssessment = computed(() => weaningStatus.value?.sbt || {})
  const postExtubationRisk = computed(() => weaningStatus.value?.post_extubation_risk || {})
  const weaningRiskTone = computed(() => {
    const level = String(weaningAssessment.value?.risk_level || '').toLowerCase()
    if (level === 'critical' || level === 'high') return 'danger'
    if (level === 'warning') return 'warn'
    return 'stable'
  })
  const weaningRiskLabel = computed(() => {
    const level = String(weaningAssessment.value?.risk_level || '').toLowerCase()
    if (level === 'critical') return '极高风险'
    if (level === 'high') return '高风险'
    if (level === 'warning') return '中风险'
    if (weaningAssessment.value?.has_assessment) return '低风险'
    return '待评估'
  })
  const weaningRecommendationText = computed(() => {
    if (weaningAssessment.value?.recommendation) return String(weaningAssessment.value.recommendation)
    return '暂无脱机评估'
  })
  const weaningTopEvidence = computed(() => {
    const rows = Array.isArray(weaningAssessment.value?.factors) ? weaningAssessment.value.factors : []
    return rows.map((row: any) => String(row?.evidence || '').trim()).filter(Boolean).slice(0, 3)
  })

  // ─── Post-extubation hero ───
  const postExtubationHeroVisible = computed(() => !!postExtubationRisk.value?.has_alert)
  const postExtubationHeroTone = computed(() => {
    const level = String(postExtubationRisk.value?.risk_level || '').toLowerCase()
    if (level === 'critical' || level === 'high') return 'danger'
    if (level === 'warning') return 'warn'
    return 'stable'
  })
  const postExtubationHeroSeverityText = computed(() => {
    const level = String(postExtubationRisk.value?.risk_level || '').toLowerCase()
    if (level === 'critical') return '极高'
    if (level === 'high') return '高'
    if (level === 'warning') return '中'
    return '低'
  })
  const postExtubationHeroTitle = computed(() => '拔管后再插管高风险')
  const postExtubationHeroSummary = computed(() => {
    const r = postExtubationRisk.value
    if (r?.summary) return String(r.summary)
    const hours = r?.hours_since_extubation
    if (hours != null) return `拔管后 ${hours} 小时，再插管风险评分升高`
    return '拔管后再插管风险评估异常'
  })
  const postExtubationHeroSuggestion = computed(() => {
    const r = postExtubationRisk.value
    if (r?.suggestion) return String(r.suggestion)
    if (r?.risk_level === 'critical') return '建议立即评估是否需要重新插管'
    if (r?.risk_level === 'high') return '建议加强呼吸监测，准备应急预案'
    return ''
  })
  const postExtubationHeroChips = computed(() => {
    const r = postExtubationRisk.value
    const chips: { label: string; value: string }[] = []
    if (r?.rr != null) chips.push({ label: 'RR', value: String(r.rr) })
    if (r?.spo2 != null) chips.push({ label: 'SpO₂', value: `${r.spo2}%` })
    if (r?.accessory_muscle_use != null) chips.push({ label: '辅助呼吸肌', value: r.accessory_muscle_use ? '有' : '无' })
    if (r?.hours_since_extubation != null) chips.push({ label: '拔管后', value: `${r.hours_since_extubation}h` })
    return chips
  })

  // ─── Alert computed ───
  const latestWeaningAlert = computed(() =>
    alerts.value.find((a: any) => String(a?.alert_type || '') === 'weaning')
  )
  const latestPostExtubationAlert = computed(() =>
    alerts.value.find((a: any) => String(a?.alert_type || '') === 'post_extubation_failure_risk')
  )
  const latestCompositeAlert = computed(() =>
    alerts.value.find((a: any) =>
      String(a?.alert_type || '') === 'multi_organ_deterioration_trend' ||
      String(a?.category || '') === 'composite_deterioration')
  )
  const latestAiRiskAlert = computed(() =>
    alerts.value.find((a: any) => String(a?.alert_type || '') === 'ai_risk')
  )
  const latestCompositeExtra = computed(() => latestCompositeAlert.value?.extra || {})
  const latestCompositeWindowHours = computed(() => latestCompositeExtra.value?.window_hours ?? 4)
  const latestCompositeModi = computed(() => latestCompositeExtra.value?.modi ?? latestCompositeAlert.value?.value ?? null)
  const latestCompositeOrganCount = computed(() => {
    const count = latestCompositeExtra.value?.organ_count
    if (count != null) return count
    const involved = latestCompositeExtra.value?.involved_organs
    return Array.isArray(involved) ? involved.length : 0
  })
  const latestCompositeInvolvedText = computed(() => {
    const labels = latestCompositeExtra.value?.organ_labels_cn || {}
    const involved = Array.isArray(latestCompositeExtra.value?.involved_organs)
      ? latestCompositeExtra.value.involved_organs : []
    const names = involved
      .map((k: any) => labels?.[String(k)] || compositeOrganLabelDefault[String(k)] || String(k))
      .filter(Boolean)
    return names.length ? `涉及系统: ${names.join(' / ')}` : '涉及系统: 暂无'
  })

  const patientBodyMapStates = computed(() => buildPatientOrganStateFromAlerts(alerts.value))
  const patientBodyMapDetails = computed(() => {
    const aiRows = aiRiskOrganRows(latestAiRiskAlert.value)
    const aiMap = new Map<string, any>()
    aiRows.forEach((row: any) => {
      const key = normalizeBodyMapOrganKey(row?.key)
      if (!key) return
      aiMap.set(key, row)
    })
    return compositeOrganOrder.map((key) => {
      const aiRow = aiMap.get(key)
      const label = compositeOrganLabelDefault[key] || key
      const alertCount = Number(latestCompositeExtra.value?.organ_alert_counts?.[key] || 0)
      return {
        key, label,
        status_text: aiRow?.status_text || undefined,
        evidence: aiRow?.evidence || (alertCount ? `近 ${latestCompositeWindowHours.value}h 关联 ${alertCount} 条预警` : ''),
      }
    })
  })
  const deviceBodyMarkers = computed(() => buildDeviceMarkers({ alerts: alerts.value, bedcard: bedcard.value }))

  // ─── Filtered alerts by category ───
  const ecashAlertTypes = new Set(['liberation_bundle', 'ecash_pain_overdue', 'ecash_pain_uncontrolled', 'ecash_rass_off_target', 'ecash_sat_due', 'ecash_benzo_in_use', 'ecash_sat_stress_reaction', 'sedation', 'delirium_risk', 'sedation_delirium_conversion'])
  const mobilityAlertTypes = new Set(['icu_aw_risk', 'early_mobility_recommendation', 'vte_immobility_no_prophylaxis'])
  const peAlertTypes = new Set(['pe_suspected', 'pe_wells_high'])

  const ecashAlerts = computed(() => sortAlertsDesc(alerts.value.filter((row: any) => ecashAlertTypes.has(String(row?.alert_type || '')))))
  const mobilityAlerts = computed(() => sortAlertsDesc(alerts.value.filter((row: any) => mobilityAlertTypes.has(String(row?.alert_type || '')))))
  const peAlerts = computed(() => sortAlertsDesc(alerts.value.filter((row: any) => peAlertTypes.has(String(row?.alert_type || '')))))
  const latestEcashBundleAlert = computed(() => ecashAlerts.value.find((row: any) => String(row?.alert_type || '') === 'liberation_bundle') || ecashAlerts.value[0] || null)

  // ─── Action rail ───
  const patientActionRail = computed(() => {
    const items: { priority: string; text: string; tone: string }[] = []
    const sepsisStatus = sepsisBundleStatusResolved.value?.status
    if (sepsisStatus === 'pending' || sepsisStatus === 'overdue_1h') {
      items.push({ priority: '紧急', text: `脓毒症Bundle ${sepsisBundleStatusText.value}`, tone: 'critical' })
    }
    if (sepsisBundleHasReviewPending.value) {
      items.push({ priority: '待办', text: '脓毒症Bundle要素待审核', tone: 'high' })
    }
    const weaningLevel = String(weaningAssessment.value?.risk_level || '').toLowerCase()
    if (weaningLevel === 'critical' || weaningLevel === 'high') {
      items.push({ priority: '关注', text: `脱机评估风险：${weaningRiskLabel.value}`, tone: 'high' })
    }
    if (postExtubationHeroVisible.value) {
      items.push({ priority: '关注', text: postExtubationHeroTitle.value, tone: 'high' })
    }
    const criticalAlerts = alerts.value.filter((a: any) => normalizeSeverity(a?.severity) === 'critical')
    if (criticalAlerts.length > 0) {
      items.push({ priority: '紧急', text: `${criticalAlerts.length} 条危急预警待处理`, tone: 'critical' })
    }
    if (items.length === 0) {
      items.push({ priority: '正常', text: '当前无紧急待办', tone: 'default' })
    }
    return items
  })

  // ─── Forecast config ───
  const forecastCodes = ['HR', 'MAP', 'SpO2', 'RR', 'Temp']
  const trajectoryPublicConfig = computed(() => {
    const cfg = runtimePublicConfig.trajectory || {}
    return {
      enabled: cfg.enabled !== false,
      horizon_hours: Number(cfg.horizon_hours || 6),
      default_codes: Array.isArray(cfg.default_codes) && cfg.default_codes.length ? cfg.default_codes : forecastCodes,
    }
  })
  const forecastMeta = computed(() => vitalForecast.meta.value)
  const trendLegendStorageKey = computed(() => `icu_forecast_legend_${getOperatorIdentity() || 'anonymous'}`)
  const trendLegendSelected = ref<Record<string, boolean>>({})

  // ─── Drug / assessment table ───
  const drugColumns = [
    { title: '药品', dataIndex: 'drugNameText', key: 'drugName' },
    { title: '剂量', dataIndex: 'doseText', key: 'dose' },
    { title: '用法', dataIndex: 'routeText', key: 'route' },
    { title: '频次', dataIndex: 'frequencyText', key: 'frequency' },
    { title: '执行时间', dataIndex: 'executeTimeText', key: 'executeTime' },
  ]
  const assessmentColumns = [
    { title: '时间', dataIndex: 'timeText', key: 'time' },
    { title: 'GCS', dataIndex: 'gcsText', key: 'gcs' },
    { title: 'RASS', dataIndex: 'rassText', key: 'rass' },
    { title: '疼痛', dataIndex: 'painText', key: 'pain' },
    { title: '谵妄', dataIndex: 'deliriumText', key: 'delirium' },
    { title: 'Braden', dataIndex: 'bradenText', key: 'braden' },
  ]
  const drugTableRows = computed(() =>
    drugs.value.map((row: any) => ({
      ...row,
      drugNameText: formatDrugName(row),
      doseText: formatDose(row),
      routeText: row?.route || '—',
      frequencyText: row?.frequency || '—',
      executeTimeText: fmtTime(row?.executeTime) || '—',
    }))
  )
  const assessmentTableRows = computed(() =>
    assessments.value.map((row: any) => ({
      ...row,
      timeText: fmtTime(row?.time) || '—',
      gcsText: row?.gcs ?? '—',
      rassText: row?.rass ?? '—',
      painText: row?.pain ?? '—',
      deliriumText: row?.delirium ?? '—',
      bradenText: row?.braden ?? '—',
    }))
  )

  // ─── AI computed ───
  const aiRuleRows = computed(() => {
    if (Array.isArray(aiRulePayload.value) && aiRulePayload.value.length) {
      return normalizeAiRuleItems(aiRulePayload.value)
    }
    return parseAiRuleRows(aiRuleText.value)
  })
  const aiHandoffConfidence = computed(() => String(aiHandoff.value?.confidence_level || '').toLowerCase())

  const aiRuntimeSummary = computed(() => {
    const meta = aiRiskForecast.value?.model_meta || {}
    const runtime = meta.runtime || {}
    const predictionSource = String(aiRiskForecast.value?.prediction_source || meta?.prediction_source || '')
    const modelName = String(meta?.model_name || meta?.name || '')
    const modelVersion = String(meta?.model_version || '')
    const modelStatus = String(meta?.model_status || runtime?.reason || '')
    const fallbackUsed = Boolean(meta?.fallback_used || false)
    const hasError = Boolean(aiLabError.value || aiRuleError.value || aiRiskError.value || aiHandoffError.value)

    const pills: string[] = []
    if (modelName && modelName !== 'unknown') pills.push(`${modelName}${modelVersion && modelVersion !== 'unknown' ? ` v${modelVersion}` : ''}`)
    if (predictionSource === 'rule_estimate') pills.push('规则估算')
    if (predictionSource === 'trained_model') pills.push('模型预测')
    if (predictionSource === 'unavailable') pills.push('模型不可用')
    if (fallbackUsed) pills.push('已降级')
    if (modelStatus) pills.push(modelStatus)

    let level = hasError ? 'red' : 'cyan'
    let text = hasError ? 'AI服务异常' : 'AI服务正常'
    let detail = hasError ? '部分 AI 能力返回错误，请检查模型与后端运行态。' : '主模型与知识证据链路可用。'

    if (predictionSource === 'rule_estimate') { level = 'warning'; text = '规则模式'; detail = '未检测到本地模型权重，当前使用启发式规则评估。' }
    else if (predictionSource === 'unavailable') { level = 'red'; text = '模型不可用'; detail = '模型加载或推理失败，且未启用规则回退。' }

    return { level, text, detail, pills }
  })

  // ─── Workbench summaries ───
  const followupWorkbenchSnapshot = computed(() => patient.value?.current_profile?.followup_case || {})
  const similarWorkbenchSummary = computed(() => {
    const summary = similarCaseReview.value?.summary || {}
    const outcomes = summary?.outcomes || {}
    const bullets = [
      summary?.matched_cases != null ? `匹配 ${summary.matched_cases} 例` : '',
      summary?.survival_rate != null ? `存活率 ${Math.round(Number(summary.survival_rate || 0) * 100)}%` : '',
      outcomes['死亡'] != null ? `死亡 ${outcomes['死亡']} 例` : '',
      summary?.degraded ? '当前为降级模式' : '',
    ].filter(Boolean)
    return {
      title: summary?.degraded ? '相似病例回顾已降级' : '相似病例回顾已接入',
      detail: similarCaseError.value || summary?.fallback_message || (similarCaseLoaded.value ? '可查看相似病例结局、分布与病例对照。' : '点击进入后加载向量检索 + 大模型相似病例分析。'),
      bullets,
    }
  })
  const thresholdWorkbenchSummary = computed(() => ({
    title: personalizedThresholdRecord.value ? '个性化阈值审核流程已接入' : '个性化阈值待生成',
    detail: personalizedThresholdRecord.value?.reasoning?.overall_reasoning || personalizedThresholdError.value || '支持待审核、已批准、已拒绝闭环，并记录审核人、审核备注与生效版本。',
    status: ({ pending_review: '待审核', approved: '已批准', rejected: '已拒绝' } as Record<string, string>)[String(personalizedThresholdRecord.value?.status || 'pending_review').toLowerCase()] || '待审核',
    reviewer: personalizedThresholdRecord.value?.reviewer || '',
    comment: personalizedThresholdRecord.value?.review_comment || '',
  }))

  // ═══════════════════════════════════════════
  //  Helper functions
  // ═══════════════════════════════════════════

  function formatCountdown(seconds?: number | null) {
    if (seconds == null) return '—'
    const safe = Math.max(0, Math.floor(seconds))
    const h = Math.floor(safe / 3600)
    const m = Math.floor((safe % 3600) / 60)
    const s = safe % 60
    if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`
    return `${m}m ${String(s).padStart(2, '0')}s`
  }

  function formatHeroMetric(value: any) {
    if (value == null || value === '') return '—'
    const num = Number(value)
    if (!Number.isFinite(num)) return String(value)
    return Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1)
  }

  function formatClinicalNumber(value: any, digits = 1) {
    if (value == null || value === '') return '—'
    const num = Number(value)
    if (!Number.isFinite(num)) return String(value)
    const rounded = Number(num.toFixed(digits))
    if (digits <= 0 || Math.abs(rounded - Math.round(rounded)) < 1e-9) return String(Math.round(rounded))
    return rounded.toFixed(digits).replace(/\.?0+$/, '')
  }

  function formatClinicalMeasure(value: any, unit = '', digits = 1) {
    const text = formatClinicalNumber(value, digits)
    return text === '—' ? text : `${text}${unit}`
  }

  function formatTime(value: any) {
    if (!value) return '—'
    try {
      const d = new Date(value)
      if (isNaN(d.getTime())) return String(value)
      return d.toLocaleString('zh-CN', { hour12: false })
    } catch { return String(value) }
  }

  function statusLabel(status: string | undefined | null) {
    const map: Record<string, string> = {
      met: '✓ 符合', not_met: '✗ 不符合', unknown: '? 待确认',
      not_excluded: '⚠ 未排除', supported: '✓ 可排除',
    }
    return map[String(status ?? '')] ?? '—'
  }

  function fmtBP(v: any) {
    const s = v?.nibp_sys, d = v?.nibp_dia
    return s != null || d != null ? `${s ?? '—'}/${d ?? '—'}` : '—'
  }
  function fmtTemp(v: any) {
    if (v == null) return '—'
    const n = Number(v)
    return isNaN(n) ? '—' : n.toFixed(1)
  }
  function fmtTime(t: any) {
    if (!t) return ''
    try { return dayjs(t).format('YYYY-MM-DD HH:mm') } catch { return '' }
  }
  function fmtTimeShort(t: any) {
    if (!t) return ''
    try { return dayjs(t).format('MM-DD HH:mm') } catch { return '' }
  }

  function sortAlertsDesc(rows: any[]) {
    return [...rows].sort((a: any, b: any) => dayjs(b?.created_at).valueOf() - dayjs(a?.created_at).valueOf())
  }

  function normalizeSeverity(raw: any) {
    const s = String(raw || '').toLowerCase()
    if (s === 'critical' || s.includes('crit')) return 'critical'
    if (s === 'high' || s.includes('high')) return 'high'
    return 'warning'
  }

  function alertSeverityText(raw: any) {
    const sev = normalizeSeverity(raw)
    if (sev === 'critical') return '危急'
    if (sev === 'high') return '高风险'
    return '预警'
  }

  function alertDomainLabel(raw: any) {
    const map: Record<string, string> = {
      physiologic_alarm: '生理危急', clinical_risk: '临床风险',
      workflow_reminder: '流程提醒', quality_gap: '质控缺项',
      data_quality: '数据质量', ai_advisory: 'AI建议', unknown: '未分类',
    }
    return map[String(raw || '').toLowerCase()] || '未分类'
  }

  function alertPriorityLabel(raw: any) {
    const map: Record<string, string> = { p0: 'P0', p1: 'P1', p2: 'P2', p3: 'P3' }
    return map[String(raw || '').toLowerCase()] || ''
  }

  function alertSourceLabel(raw: any) {
    const map: Record<string, string> = {
      rule: '规则', trained_model: '模型', heuristic: '启发式',
      llm: 'LLM', manual: '人工', device_native: '设备', hybrid: '混合',
    }
    return map[String(raw || '').toLowerCase()] || '未知来源'
  }

  function alertTypeText(raw: any) {
    const t = String(raw || '')
    if (!t) return ''
    const map: Record<string, string> = {
      lab_threshold: '检验阈值', trend_analysis: '趋势恶化', sofa: 'SOFA评分',
      qsofa: 'qSOFA评分', septic_shock: '脓毒性休克', ards: 'ARDS',
      ards_oxygenation_screen: 'ARDS氧合筛查', ventilator_lung_injury_risk: '肺保护通气偏离',
      aki: '急性肾损伤', dic: 'DIC', gi_bleeding: '消化道出血', gcs_drop: 'GCS下降',
      hit: 'HIT', nephrotoxicity: '肾毒性', sedation: '镇静风险', qt_risk: 'QT风险',
      af_afl_new_onset: '新发房颤/房扑', brady_hypotension: '心动过缓合并低压',
      qtc_prolonged: 'QTc明显延长', opioid_high_dose_resp_risk: '阿片高剂量呼吸抑制风险',
      opioid_respiratory_depression: '阿片呼吸抑制', opioid_withdrawal_risk: '阿片戒断风险',
      weaning: '撤机评估', nurse_reminder: '护理提醒', ai_risk: 'AI风险',
      fluid_balance: '液体平衡', delirium_risk: '谵妄风险',
      sedation_delirium_conversion: '镇静转谵妄', glucose_variability: '血糖波动',
      hypoglycemia: '低血糖', glucose_drop_fast: '血糖快速下降',
      glucose_recheck_reminder: '血糖复查提醒', hyperglycemia_no_insulin: '高血糖未启胰岛素',
      abx_timeout: '抗菌药复核超时', abx_stop_recommendation: 'PCT停药评估',
      abx_tdm_reminder: '抗生素TDM提醒', abx_duration_exceeded: '抗生素疗程超限',
      vte_prophylaxis_omission: 'VTE预防遗漏', vte_bleeding_linkage: 'VTE出血风险联动',
      vte_immobility_no_prophylaxis: '制动无VTE预防', nutrition_start_delay: '营养启动延迟',
      nutrition_calorie_not_reached: '热卡未达标', nutrition_feeding_intolerance: '喂养不耐受',
      nutrition_refeeding_risk: '再喂养风险', multi_organ_deterioration_trend: '多器官恶化趋势',
      liberation_bundle: 'eCASH解放束', icu_aw_risk: 'ICU获得性衰弱高风险',
      early_mobility_recommendation: '早期活动推荐', pe_suspected: '肺栓塞检测',
      pe_wells_high: '肺栓塞Wells评分', post_extubation_failure_risk: '拔管后呼吸衰竭风险',
    }
    return map[t] || '临床预警'
  }

  function alertCategoryText(raw: any) {
    const t = String(raw || '')
    if (!t) return ''
    const map: Record<string, string> = {
      vital_signs: '生命体征', syndrome: '综合征', lab_results: '检验',
      trend: '趋势', nurse: '护理', ai: 'AI', ventilator: '呼吸机',
      drug_safety: '用药安全', fluid_balance: '液体平衡', glycemic_control: '血糖管理',
      antibiotic_stewardship: '抗菌药管理', vte_prophylaxis: 'VTE预防',
      nutrition_monitor: '营养监测', composite_deterioration: '复合恶化',
      device_management: '装置管理', bundle: '解放束', hemodynamic: '血流动力学',
      crrt: 'CRRT', dose_adjustment: '剂量调整',
    }
    return map[t] || '其他'
  }

  function labFlag(item: any) {
    const flag = item.resultFlag || item.abnormalFlag || item.flag
    if (!flag) return ''
    const f = String(flag)
    if (f.includes('H') || f.includes('↑')) return 'lab-high'
    if (f.includes('L') || f.includes('↓')) return 'lab-low'
    return ''
  }

  function isAiRiskAlert(item: any) {
    return String(item?.alert_type || '') === 'ai_risk'
  }
  function aiConfidenceClass(level: string) {
    const v = String(level || '').toLowerCase()
    if (v === 'low') return 'ai-confidence-low'
    if (v === 'medium') return 'ai-confidence-medium'
    return 'ai-confidence-high'
  }
  function normalizeConfidenceLevel(raw: any) {
    const v = String(raw || '').toLowerCase()
    if (v === 'low' || v === 'medium' || v === 'high') return v
    return 'medium'
  }
  function aiRiskConfidenceLevel(item: any) {
    return normalizeConfidenceLevel(
      item?.extra?.confidence?.overall ||
      item?.extra?.explainability?.confidence_level || 'medium'
    )
  }
  function aiRiskLevelText(raw: any) {
    let v = String(raw || '').toLowerCase()
    v = v.replace(/\[\^[^\]]+\]/g, '').trim()
    if (v === 'critical' || v === '极高') return '极高'
    if (v === 'high' || v === '高') return '高'
    if (v === 'warning' || v === 'warn') return '中'
    if (v === 'medium' || v === '中') return '中'
    if (v === 'low' || v === '低') return '低'
    return '—'
  }
  function feedbackOutcomeText(raw: any) {
    const v = String(raw || '').toLowerCase()
    if (v === 'confirmed') return '采纳'
    if (v === 'dismissed') return '忽略'
    if (v === 'inaccurate') return '不准确'
    return '—'
  }
  function aiRiskOrganRows(item: any) {
    const organ = item?.extra?.organ_assessment
    const organLabels: Record<string, string> = {
      respiratory: '呼吸', cardiovascular: '循环', renal: '肾脏',
      hepatic: '肝脏', coagulation: '凝血', neurological: '神经',
    }
    const statusLabels: Record<string, string> = {
      normal: '正常', impaired: '受损', failure: '衰竭',
    }
    if (!organ || typeof organ !== 'object') return []
    return Object.entries(organ)
      .map(([key, val]: [string, any]) => ({
        key,
        label: organLabels[key] || key,
        status_text: statusLabels[String(val?.status || '').toLowerCase()] || String(val?.status || '—'),
        evidence: String(val?.evidence || ''),
        confidence_level: normalizeConfidenceLevel(val?.confidence_level),
      }))
      .filter((x) => x.label)
  }
  function aiRiskValidationIssues(item: any) {
    const issues = item?.extra?.safety_validation?.issues
    return Array.isArray(issues) ? issues : []
  }
  function aiRiskHallucinations(item: any) {
    const flags = item?.extra?.hallucination_flags
    return Array.isArray(flags) ? flags : []
  }
  function aiRiskEvidenceList(item: any) {
    const evidence = item?.extra?.evidence_sources
    return Array.isArray(evidence) ? evidence : []
  }
  function aiRiskExplainabilityRows(item: any) {
    const rows = item?.extra?.explainability?.top_factors
    return Array.isArray(rows) ? rows : []
  }

  function formatAlertExtra(extra: any) {
    try { return JSON.stringify(extra, null, 2) } catch { return '' }
  }

  function formatAlertValue(a: any) {
    if (!a) return '—'
    const t = String(a.alert_type || '')
    const p = String(a.parameter || '')
    const v = a.value
    const extra = a.extra || {}

    if (t === 'dic') { const score = extra?.score ?? v; return score != null ? `DIC=${score}` : '—' }
    if (t === 'ards') { const pf = v ?? extra?.pf_ratio; return pf != null ? `P/F=${Math.round(Number(pf))}` : '—' }
    if (t === 'aki') { return v != null ? `AKI=${v}期` : '—' }
    if (t === 'qsofa') { return v != null ? `qSOFA=${v}` : '—' }
    if (t === 'sofa' || t === 'septic_shock') { return v != null ? `SOFA=${v}` : '—' }
    if (t === 'multi_organ_deterioration_trend') {
      const modi = extra?.modi ?? v
      const n = extra?.organ_count
      if (modi != null && n != null) return `MODI=${modi} (${n}系统)`
      if (modi != null) return `MODI=${modi}`
      return '多器官恶化趋势'
    }
    if (t === 'lab_threshold') {
      const unit = extra?.unit || ''
      const labelMap: Record<string, string> = {
        k: 'K⁺', na: 'Na⁺', ica: 'iCa', ca: 'Ca', lac: 'Lac', glu: 'Glu',
        hb: 'Hb', plt: 'PLT', cr: 'Cr', pct: 'PCT', inr: 'INR', pt: 'PT',
      }
      const label = labelMap[p] || extra?.raw_name || ''
      if (v == null) return '—'
      return label ? `${label}=${v}${unit}` : `${v}${unit}`
    }
    return v ?? '—'
  }

  function formatDrugName(row: any) {
    return row?.drugName || row?.drug_name || row?.name || '—'
  }
  function formatDose(row: any) {
    const d = row?.dose || row?.dosage
    const u = row?.doseUnit || row?.dose_unit || row?.unit || ''
    return d != null ? `${d}${u}` : '—'
  }

  function normalizeList(raw: any): string[] {
    if (!Array.isArray(raw)) return []
    return raw.map((x) => String(x || '').trim()).filter(Boolean)
  }

  // ─── AI rule parsing ───
  function stripMarkdownFence(raw: string) {
    const text = String(raw || '').trim()
    if (!text) return ''
    const fullFence = text.match(/^```(?:json|markdown|md)?\s*([\s\S]*?)\s*```$/i)
    if (fullFence?.[1]) return fullFence[1].trim()
    return text.replace(/^```(?:json|markdown|md)?\s*/i, '').replace(/\s*```$/, '').trim()
  }
  function stripModelThinking(raw: any) {
    return String(raw || '')
      .replace(/<think\b[^>]*>[\s\S]*?<\/think>/gi, '')
      .replace(/<reasoning\b[^>]*>[\s\S]*?<\/reasoning>/gi, '')
      .replace(/<analysis\b[^>]*>[\s\S]*?<\/analysis>/gi, '')
      .replace(/^\s*(思考过程|推理过程|内部推理|模型思考|Chain\s*of\s*Thought|Reasoning)\s*[：:]\s*[\s\S]*?(?=(\n\s*)?(```|\{|\[|#{1,4}\s|结论[：:]|建议[：:]|评估[：:]|摘要[：:]))/i, '')
      .replace(/^\s*(思考|Thinking|Reasoning)\s*[：:]\s*$/gim, '')
      .trim()
  }
  function parseRuleJsonArray(text: string): any[] {
    const candidates = [text]
    const codeBlocks = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/gi) || []
    codeBlocks.forEach((block) => { const inner = stripMarkdownFence(block); if (inner) candidates.unshift(inner) })
    const arrBlock = text.match(/\[[\s\S]*\]/)
    if (arrBlock?.[0] && arrBlock[0] !== text) candidates.unshift(arrBlock[0])
    for (const candidate of candidates) {
      try { const parsed = JSON.parse(candidate); if (Array.isArray(parsed)) return parsed } catch {}
    }
    return []
  }
  function normalizeAiRuleItems(items: any[]) {
    const sevMap: Record<string, string> = {
      warning: '提醒', high: '高风险', critical: '危急', warn: '提醒',
      高危: '高风险', 高风险: '高风险', 危急: '危急', 提醒: '提醒', 警告: '提醒',
    }
    return items.map((it: any, idx: number) => {
      const severityRaw = String(it?.severity || '').toLowerCase()
      return {
        key: String(idx + 1),
        parameter: String(it?.parameter || it?.name || '—'),
        operator: String(it?.operator || '—'),
        threshold: it?.threshold != null ? String(it.threshold) : '—',
        severity: sevMap[severityRaw] || String(it?.severity || '—'),
        reason: String(it?.reason || it?.description || '—'),
      }
    })
  }
  function parseRuleMarkdownTable(text: string): any[] {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.includes('|'))
    if (lines.length < 3) return []
    const tableLines = lines.filter((l) => /^\|?.+\|.+\|?$/.test(l))
    if (tableLines.length < 3) return []
    const header = (tableLines[0] || '').replace(/^\||\|$/g, '').split('|').map((c) => c.trim().toLowerCase())
    const divider = tableLines[1] || ''
    if (!header.length || !/^[|\s:\-]+$/.test(divider)) return []
    const indexOf = (names: string[]) => header.findIndex((c) => names.some((n) => c.includes(n)))
    const parameterIdx = indexOf(['parameter', '参数', '指标', '监测'])
    const operatorIdx = indexOf(['operator', '方向', '条件', '符号'])
    const thresholdIdx = indexOf(['threshold', '阈值'])
    const severityIdx = indexOf(['severity', '级别', '风险'])
    const reasonIdx = indexOf(['reason', '依据', '理由', '说明'])
    if (parameterIdx < 0) return []
    return tableLines.slice(2).map((line) => {
      const cells = line.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      return {
        parameter: cells[parameterIdx] || '',
        operator: operatorIdx >= 0 ? (cells[operatorIdx] || '') : '',
        threshold: thresholdIdx >= 0 ? (cells[thresholdIdx] || '') : '',
        severity: severityIdx >= 0 ? (cells[severityIdx] || '') : '',
        reason: reasonIdx >= 0 ? (cells[reasonIdx] || '') : '',
      }
    }).filter((row) => row.parameter)
  }
  function parseRuleNarrativeLines(text: string): any[] {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
    const rows: any[] = []
    const severityTokens = ['critical', 'high', 'warning', '危急', '高风险', '高危', '提醒', '警告']
    for (const line of lines) {
      const clean = line.replace(/^[\d\-*•、.\s]+/, '').trim()
      if (!clean || clean.length < 4) continue
      const operatorMatch = clean.match(/>=|<=|>|<|≥|≤/)
      if (!operatorMatch) continue
      const severity = severityTokens.find((t) => clean.toLowerCase().includes(t.toLowerCase())) || ''
      const operator = operatorMatch[0] || ''
      const [leftPart = '', rightPartRaw = ''] = clean.split(operator, 2)
      const thresholdMatch = (rightPartRaw || '').match(/^([^\s，。,；;]+)/)
      rows.push({
        parameter: leftPart.replace(/[：:]+$/, '').trim(),
        operator, threshold: thresholdMatch?.[1] || '', severity, reason: clean,
      })
    }
    return rows.filter((r) => r.parameter && r.threshold)
  }
  function parseAiRuleRows(raw: any) {
    const text = stripMarkdownFence(String(raw || ''))
    if (!text) return []
    const arr = parseRuleJsonArray(text)
    const normalized = arr.length ? arr : (parseRuleMarkdownTable(text).length ? parseRuleMarkdownTable(text) : parseRuleNarrativeLines(text))
    if (!normalized.length) return []
    return normalizeAiRuleItems(normalized)
  }

  function formatAiError(raw: any) {
    const s = String(raw || '')
    if (!s) return ''
    if (s.includes('503') || s.toLowerCase().includes('service unavailable')) return 'AI服务暂不可用(503)'
    if (s.toLowerCase().includes('401') || s.toLowerCase().includes('unauthorized')) return '智能鉴权失败(401)'
    if (s.toLowerCase().includes('403')) return 'AI权限不足(403)'
    return s
  }

  function knowledgeScopeText(scope: any) {
    const v = String(scope || '').toLowerCase()
    if (v === 'institutional') return '院内SOP/制度'
    if (v === 'external') return '外部指南'
    if (v === 'local') return '本地资料'
    return '未知'
  }

  function readTrendLegendSelection() {
    try {
      const raw = localStorage.getItem(trendLegendStorageKey.value)
      trendLegendSelected.value = raw ? JSON.parse(raw) : {}
    } catch { trendLegendSelected.value = {} }
  }

  function saveTrendLegendSelection(selected: Record<string, boolean>) {
    trendLegendSelected.value = selected || {}
    try { localStorage.setItem(trendLegendStorageKey.value, JSON.stringify(trendLegendSelected.value)) } catch {}
  }

  // ═══════════════════════════════════════════
  //  Data loading
  // ═══════════════════════════════════════════

  async function loadDetailPage() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    await Promise.allSettled([
      (async () => { try { const res = await getPatientDetail(patientId); patient.value = res.data.patient || null } catch (e) { console.error('加载患者失败', e) } })(),
      (async () => { try { const vRes = await getPatientVitals(patientId, 15000); vitals.value = vRes.data.vitals || null } catch (e) { console.error('加载生命体征失败', e) } })(),
      (async () => { try { const res = await getPatientBedcard(patientId, 15000); bedcard.value = res.data?.data || null } catch (e) { console.error('加载床旁概览卡失败', e) } })(),
      loadAlerts(),
      loadClinicalSummary(),
      loadSepsisBundleStatus(),
      loadWeaningStatus(),
      loadClinicalTrialMatches(),
    ])
  }

  async function loadAlerts() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    try {
      const res = await getPatientAlerts(patientId)
      alerts.value = res.data.records || []
      const alertIds = alerts.value.map((item: any) => String(item?._id || '').trim()).filter(Boolean).slice(0, 50)
      if (alertIds.length) {
        postPatientAlertsViewed(patientId, { alert_ids: alertIds, actor: getOperatorIdentity(), source: 'patient_detail' }).catch(() => undefined)
      }
    } catch (e) { console.error('加载预警失败', e) }
  }

  async function loadClinicalSummary() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    clinicalSummaryLoading.value = true
    try {
      const res = await getPatientClinicalSummary(patientId)
      clinicalSummary.value = res.data?.summary || null
    } catch (e) { console.error('加载临床摘要失败', e) }
    finally { clinicalSummaryLoading.value = false }
  }

  async function loadSepsisBundleStatus() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    try {
      const res = await getPatientSepsisBundleStatus(patientId)
      sepsisBundleStatus.value = res.data?.status || null
      sepsisBundleNow.value = Date.now()
    } catch (e) { console.error('加载脓毒症状态失败', e); sepsisBundleStatus.value = null }
  }

  async function loadWeaningStatus() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    try {
      const res = await getPatientWeaningStatus(patientId)
      weaningStatus.value = res.data?.status || null
    } catch (e) { console.error('加载脱机评估失败', e); weaningStatus.value = null }
  }

  async function loadClinicalTrialMatches() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    trialMatchLoading.value = true; trialMatchError.value = ''
    try {
      const { getPatientTrialMatches } = await import('../api/clinicalTrials')
      const res = await getPatientTrialMatches(patientId)
      trialMatches.value = res.data?.matches || []
    } catch (e: any) { trialMatchError.value = e?.message || '临床试验匹配加载失败' }
    finally { trialMatchLoading.value = false }
  }

  async function loadTrend() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    try {
      const res = await getPatientVitalsTrend(patientId, trendWindow.value)
      trendPoints.value = res.data.points || []
      trendLoaded.value = true
    } catch (e) { console.warn('趋势数据加载较慢', e) }
  }

  async function loadWaveform() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    waveformLoading.value = true
    waveformError.value = ''
    try {
      const [channelsRes, segmentsRes] = await Promise.all([
        getWaveformChannels(patientId, { hours: waveformHours.value }),
        waveformSelectedChannel.value
          ? getWaveformSegments(patientId, { channel: waveformSelectedChannel.value, hours: waveformHours.value })
          : Promise.resolve({ data: { rows: [] } }),
      ])
      // 后端返回 { rows: [...] } 格式
      waveformChannels.value = channelsRes.data?.rows || channelsRes.data?.channels || []
      if (!waveformSelectedChannel.value && waveformChannels.value.length) {
        waveformSelectedChannel.value = waveformChannels.value[0]?.channel || waveformChannels.value[0]?.key || ''
        if (waveformSelectedChannel.value) {
          const segRes = await getWaveformSegments(patientId, { channel: waveformSelectedChannel.value, hours: waveformHours.value })
          waveformPoints.value = segRes.data?.rows || segRes.data?.segments || []
        }
      } else {
        waveformPoints.value = segmentsRes.data?.rows || segmentsRes.data?.segments || []
      }
      // Load QC and events if channel selected
      if (waveformSelectedChannel.value) {
        const [qcRes, eventsRes] = await Promise.all([
          getWaveformQuality(patientId, { channel: waveformSelectedChannel.value, hours: waveformHours.value }),
          getWaveformEvents(patientId, { channel: waveformSelectedChannel.value, hours: waveformHours.value }),
        ])
        waveformQc.value = qcRes.data?.qc || null
        waveformEvents.value = eventsRes.data?.events || []
      }
    } catch (e: any) {
      const status = e?.response?.status
      if (status === 401 || status === 403) waveformError.value = '无权访问波形数据'
      else if (status === 404) waveformError.value = '波形服务未配置'
      else if (status >= 500) waveformError.value = '波形服务异常，请稍后重试'
      else waveformError.value = e?.message || '波形数据加载失败'
      console.warn('波形数据加载失败', e)
    }
    finally { waveformLoading.value = false }
  }

  async function loadLabs() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId || labsLoaded.value) return
    try { const res = await getPatientLabs(patientId); labs.value = res.data.exams || []; labsLoaded.value = true }
    catch (e) { console.warn('检验数据加载较慢', e) }
  }

  async function loadDrugs() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId || drugsLoaded.value) return
    try { const res = await getPatientDrugs(patientId); drugs.value = res.data.records || []; drugsLoaded.value = true }
    catch (e) { console.warn('用药数据加载较慢', e) }
  }

  async function loadAssessments() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId || assessmentsLoaded.value) return
    try { const res = await getPatientAssessments(patientId); assessments.value = res.data.records || []; assessmentsLoaded.value = true }
    catch (e) { console.warn('评估数据加载较慢', e) }
  }

  async function loadSbtTimeline(force = false) {
    if (sbtTimelineLoading.value) return
    if (sbtTimelineLoaded.value && !force) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    sbtTimelineLoading.value = true; sbtTimelineError.value = ''
    try {
      const res = await getPatientWeaningTimeline(patientId, 40)
      sbtTimelineSummary.value = res.data?.summary || null
      sbtTimelineAiSummary.value = res.data?.ai_summary || null
      sbtTimelineRecords.value = Array.isArray(res.data?.timeline) ? res.data.timeline : []
    } catch (e: any) {
      sbtTimelineError.value = e?.response?.data?.message || '自主呼吸试验记录加载失败'
      sbtTimelineSummary.value = null; sbtTimelineAiSummary.value = null; sbtTimelineRecords.value = []
    } finally { sbtTimelineLoading.value = false; sbtTimelineLoaded.value = true }
  }

  async function loadSimilarCaseReview(force = false) {
    if (similarCaseLoading.value) return
    if (similarCaseLoaded.value && !force) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    similarCaseLoading.value = true; similarCaseError.value = ''
    try {
      const res = await getPatientSimilarCaseOutcomes(patientId, 10)
      similarCaseReview.value = res.data?.review || null
      similarCaseError.value = String(res.data?.review?.summary?.fallback_message || '').trim()
    } catch (e: any) {
      const fallbackMessage = String(e?.message || '').toLowerCase().includes('timeout')
        ? 'AI分析响应较慢，已切换为降级模式' : 'AI服务暂时不可用，已切换为降级模式'
      similarCaseError.value = fallbackMessage
      similarCaseReview.value = { summary: { matched_cases: 0, degraded: true, fallback_message: fallbackMessage }, cases: [] }
    } finally { similarCaseLoading.value = false; similarCaseLoaded.value = true }
  }

  async function loadPersonalizedThresholds(force = false) {
    if (personalizedThresholdLoading.value) return
    if (personalizedThresholdRecord.value && !force) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    personalizedThresholdLoading.value = true; personalizedThresholdError.value = ''
    try {
      const [latestRes, historyRes] = await Promise.all([
        getPatientPersonalizedThresholds(patientId),
        getPatientPersonalizedThresholdHistory(patientId, { limit: 6 }),
      ])
      personalizedThresholdRecord.value = latestRes.data?.record || null
      personalizedThresholdHistory.value = Array.isArray(historyRes.data?.rows) ? historyRes.data.rows : []
      personalizedThresholdApprovedRecord.value = personalizedThresholdHistory.value.find((r: any) => String(r?.status || '').toLowerCase() === 'approved') || null
    } catch (e) { console.warn('个性化阈值加载较慢', e) }
    finally { personalizedThresholdLoading.value = false }
  }

  // ─── AI loaders ───
  async function loadAiLab() {
    if (aiLabLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    aiLabError.value = ''; aiLabLoading.value = true
    try {
      const res = await getAiLabSummary(patientId)
      aiLabSummary.value = stripModelThinking(res.data.summary || '')
      aiLabError.value = formatAiError(res.data.error || '')
    } catch { aiLabError.value = '智能服务不可用' }
    finally { aiLabLoading.value = false }
  }

  async function loadAiRules() {
    if (aiRuleLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    aiRuleError.value = ''; aiRuleLoading.value = true
    try {
      const res = await getAiRuleRecommendations(patientId)
      const recommendations = res.data.recommendations
      aiRulePayload.value = Array.isArray(recommendations) ? recommendations : null
      const rawText = res.data.raw_text
      if (typeof rawText === 'string' && rawText.trim()) aiRuleText.value = stripModelThinking(rawText)
      else if (typeof recommendations === 'string') aiRuleText.value = stripModelThinking(recommendations)
      else if (Array.isArray(recommendations)) aiRuleText.value = stripModelThinking(JSON.stringify(recommendations, null, 2))
      else aiRuleText.value = ''
      aiRuleError.value = formatAiError(res.data.error || '')
    } catch { aiRuleError.value = '智能服务不可用' }
    finally { aiRuleLoading.value = false }
  }

  async function loadAiRisk() {
    if (aiRiskLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    aiRiskError.value = ''; aiRiskLoading.value = true
    try {
      const res = await getAiRiskForecast(patientId)
      aiRiskForecast.value = res.data || null
      aiRiskText.value = stripModelThinking(res.data.risk_summary || '')
      aiRiskError.value = formatAiError(res.data.error || '')
    } catch { aiRiskForecast.value = null; aiRiskError.value = '智能服务不可用' }
    finally { aiRiskLoading.value = false }
  }

  async function loadIntegratedRisk(refresh = false) {
    if (integratedRiskLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    integratedRiskError.value = ''; integratedRiskLoading.value = true
    try {
      const res = await getAiIntegratedRiskReport(patientId, { refresh })
      integratedRiskReport.value = res.data.report || null
      integratedRiskError.value = formatAiError(res.data.error || '')
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.response?.data?.message || e?.message || ''
      integratedRiskError.value = msg ? formatAiError(msg) : '综合风险服务暂时不可用'
    } finally { integratedRiskLoading.value = false }
  }

  async function loadMetabolicPhase(refresh = false) {
    if (metabolicPhaseLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    metabolicPhaseError.value = ''; metabolicPhaseLoading.value = true
    try {
      const res = await getAiMetabolicPhase(patientId, { refresh })
      metabolicPhaseRecord.value = res.data.record || null
      metabolicPhaseError.value = metabolicPhaseRecord.value?.degraded ? '' : formatAiError(res.data.error || '')
    } catch {
      metabolicPhaseRecord.value = { phase: 'insufficient_data', phase_label: '数据不足', degraded: true }
      metabolicPhaseError.value = ''
    } finally { metabolicPhaseLoading.value = false }
  }

  async function loadBetaBlockerAdvisor(refresh = false) {
    if (betaBlockerAdvisorLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    betaBlockerAdvisorError.value = ''; betaBlockerAdvisorLoading.value = true
    try {
      const res = await getAiBetaBlockerAdvisor(patientId, { refresh })
      betaBlockerAdvisorRecord.value = res.data.record || null
      betaBlockerAdvisorError.value = formatAiError(res.data.error || '')
    } catch { betaBlockerAdvisorError.value = '智能服务不可用' }
    finally { betaBlockerAdvisorLoading.value = false }
  }

  async function loadFibrinolysis(refresh = false) {
    if (fibrinolysisLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    fibrinolysisError.value = ''; fibrinolysisLoading.value = true
    try {
      const res = await getAiFibrinolysisMonitor(patientId, { refresh })
      fibrinolysisRecord.value = res.data.record || null
      fibrinolysisError.value = formatAiError(res.data.error || '')
    } catch { fibrinolysisError.value = '智能服务不可用' }
    finally { fibrinolysisLoading.value = false }
  }

  async function loadPronePosition(refresh = false) {
    if (pronePositionLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    pronePositionError.value = ''; pronePositionLoading.value = true
    try {
      const res = await getAiPronePositionMonitor(patientId, { refresh })
      pronePositionRecord.value = res.data.record || null
      pronePositionError.value = formatAiError(res.data.error || '')
    } catch { pronePositionError.value = '智能服务不可用' }
    finally { pronePositionLoading.value = false }
  }

  async function loadPicsRisk(refresh = false) {
    if (picsRiskLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    picsRiskError.value = ''; picsRiskLoading.value = true
    try {
      const res = await getAiPicsRisk(patientId, { refresh })
      picsRiskRecord.value = res.data.record || null
      picsRiskError.value = formatAiError(res.data.error || '')
    } catch { picsRiskError.value = '智能服务不可用' }
    finally { picsRiskLoading.value = false }
  }

  async function loadAiHandoff() {
    if (aiHandoffLoading.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    aiHandoffError.value = ''; aiHandoffLoading.value = true
    try {
      const res = await getPatientHandoffSummary(patientId)
      aiHandoff.value = res.data?.summary || null
      aiHandoffError.value = formatAiError(res.data?.error || '')
    } catch { aiHandoffError.value = '智能服务不可用' }
    finally { aiHandoffLoading.value = false }
  }

  async function loadAiAll() {
    if (aiAutoLoaded.value) return
    aiAutoLoaded.value = true
    void loadAiLab(); void loadAiRules(); void loadAiRisk()
    void loadIntegratedRisk(); void loadMetabolicPhase()
    void loadBetaBlockerAdvisor(); void loadFibrinolysis()
    void loadPronePosition(); void loadPicsRisk()
  }

  // ─── Knowledge loaders ───
  async function loadKnowledgeDocs() {
    if (knowledgeLoading.value) return
    knowledgeLoading.value = true; knowledgeError.value = ''
    try {
      const [res, statusRes] = await Promise.all([getKnowledgeDocuments(), getKnowledgeStatus()])
      knowledgeDocs.value = Array.isArray(res.data?.documents) ? res.data.documents : []
      knowledgeStatus.value = statusRes.data?.status || null
      if (!selectedKnowledgeDocId.value && knowledgeDocs.value.length) {
        selectedKnowledgeDocId.value = String(knowledgeDocs.value[0].doc_id || '')
        await loadKnowledgeDocument(selectedKnowledgeDocId.value)
      }
    } catch { knowledgeError.value = '离线知识包加载失败' }
    finally { knowledgeLoading.value = false }
  }

  async function loadKnowledgeDocument(docId?: any) {
    const id = String(docId || selectedKnowledgeDocId.value || '').trim()
    if (!id) return
    knowledgeLoading.value = true; knowledgeError.value = ''
    try { const res = await getKnowledgeDocument(id); selectedKnowledgeDoc.value = res.data?.document || null }
    catch { knowledgeError.value = '离线文档加载失败' }
    finally { knowledgeLoading.value = false }
  }

  async function handleReloadKnowledge() {
    if (knowledgeLoading.value) return
    knowledgeLoading.value = true; knowledgeError.value = ''
    try {
      const res = await reloadKnowledge()
      const [docsRes, statusRes] = await Promise.all([getKnowledgeDocuments(), getKnowledgeStatus()])
      knowledgeDocs.value = Array.isArray(docsRes.data?.documents) ? docsRes.data.documents : []
      knowledgeStatus.value = statusRes.data?.status || res.data?.status || null
      message.success(res.data?.message || '知识库已热更新')
    } catch { knowledgeError.value = '知识库热更新失败'; message.error('知识库热更新失败') }
    finally { knowledgeLoading.value = false }
  }

  // ─── Alert actions ───
  async function acknowledgeAlert(item: any, disposition = '', meta?: { override_reason_code?: string; override_reason_text?: string }) {
    const alertId = String(item?._id || '').trim()
    if (!alertId) { message.error('缺少告警ID'); return }
    try {
      const workflowActions = new Set(['handled', 'resolved', 'watching', 'false_positive', 'duplicate', 'data_error', 'handoff_doctor', 'handoff_nurse', 'review_2h'])
      const action = disposition === 'review_2h' ? 'needs_review' : disposition === 'resolved' ? 'handled' : disposition || 'handled'
      const res = workflowActions.has(disposition)
        ? await postAlertDisposition(alertId, { actor: getOperatorIdentity(), action, reason: meta?.override_reason_text || meta?.override_reason_code || '', review_after_minutes: disposition === 'review_2h' ? 120 : undefined })
        : await postAlertAcknowledge(alertId, { actor: getOperatorIdentity(), ...(disposition ? { disposition } : {}), ...(meta?.override_reason_code ? { override_reason_code: meta.override_reason_code } : {}), ...(meta?.override_reason_text ? { override_reason_text: meta.override_reason_text } : {}) })
      const record = res.data?.record
      if (record) {
        const idx = alerts.value.findIndex((row: any) => String(row?._id || '') === String(record?._id || ''))
        if (idx >= 0) alerts.value[idx] = record
      }
      message.success(disposition ? `告警已确认` : '告警已确认')
    } catch (e: any) { message.error(e?.response?.data?.message || '告警确认失败') }
  }

  async function submitAiFeedback(item: any, outcome: 'confirmed' | 'dismissed' | 'inaccurate') {
    const predictionId = String(item?._id || '').trim()
    if (!predictionId) { message.error('缺少预警ID'); return }
    try {
      await postAiFeedback({ prediction_id: predictionId, outcome, module: 'ai_risk', detail: { patient_id: String(item?.patient_id || ''), rule_id: String(item?.rule_id || ''), alert_type: String(item?.alert_type || '') } })
      if (!item.ai_feedback) item.ai_feedback = {}
      item.ai_feedback.outcome = outcome
      item.ai_feedback.updated_at = new Date().toISOString()
      message.success('AI反馈已记录')
    } catch { message.error('AI反馈提交失败') }
  }

  async function openEvidence(evidence: any) {
    const chunkId = String(evidence?.chunk_id || '').trim()
    if (!chunkId) { message.warning('缺少本地证据ID'); return }
    try {
      const res = await getKnowledgeChunk(chunkId)
      const chunk = res.data?.chunk || {}
      evidenceModal.value = {
        title: chunk.title || evidence.title || '离线指南证据',
        source: chunk.source || evidence.source || '',
        package_name: chunk.package_name || '', package_version: chunk.package_version || '',
        category: chunk.category || '', owner: chunk.owner || '',
        updated_at: chunk.updated_at || '', priority: chunk.priority ?? null,
        local_ref: chunk.local_ref || '', recommendation: chunk.recommendation || evidence.recommendation || '',
        recommendation_grade: chunk.recommendation_grade || '', section_title: chunk.section_title || '',
        tags: Array.isArray(chunk.tags) ? chunk.tags : [],
        content: chunk.content || evidence.quote || '',
        related_chunks: Array.isArray(chunk.related_chunks) ? chunk.related_chunks : [],
      }
      evidenceModalOpen.value = true
    } catch {
      evidenceModal.value = { title: evidence.title || '证据', source: evidence.source || '', content: evidence.quote || '加载失败', tags: [], related_chunks: [] }
      evidenceModalOpen.value = true
    }
  }

  // ─── Sepsis bundle actions ───
  function openSepsisBundleReviewDialog() {
    const elements = sepsisBundleReviewableElements.value
    if (elements.length > 0) {
      const first = elements[0]!
      sepsisBundleReviewForm.value = { element_key: first.key, applicability: 'individualized', individualized_target_ml: undefined, reason: '', version: first.version }
    }
    sepsisBundleReviewDialogVisible.value = true
  }

  async function submitSepsisBundleReview() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    sepsisBundleSubmitting.value = true
    try {
      const payload: any = {
        element_key: sepsisBundleReviewForm.value.element_key,
        applicability: sepsisBundleReviewForm.value.applicability,
        reason: sepsisBundleReviewForm.value.reason || '临床医生确认',
        version: sepsisBundleReviewForm.value.version,
        actor: getOperatorIdentity() || undefined, role: 'doctor',
      }
      if (sepsisBundleReviewForm.value.applicability === 'individualized') payload.individualized_target_ml = sepsisBundleReviewForm.value.individualized_target_ml
      await submitSepsisBundleElementReview(patientId, payload)
      sepsisBundleReviewDialogVisible.value = false
      await loadSepsisBundleStatus()
    } catch (e: any) { alert(e?.response?.data?.message || '提交失败') }
    finally { sepsisBundleSubmitting.value = false }
  }

  function openSepsisBundleExecutionDialog() {
    sepsisBundleExecutionForm.value = { element_key: 'fluid_resuscitation', status: 'met', completed_at: new Date().toISOString(), value: null, reason: '' }
    sepsisBundleExecutionDialogVisible.value = true
  }

  async function submitSepsisBundleExecution() {
    const patientId = String(route.params.patientId || route.params.id || '')
    if (!patientId) return
    sepsisBundleSubmitting.value = true
    try {
      await recordSepsisBundleExecution(patientId, {
        element_key: sepsisBundleExecutionForm.value.element_key,
        status: sepsisBundleExecutionForm.value.status,
        completed_at: sepsisBundleExecutionForm.value.completed_at || undefined,
        value: sepsisBundleExecutionForm.value.value,
        reason: sepsisBundleExecutionForm.value.reason,
        actor: getOperatorIdentity() || undefined,
      })
      sepsisBundleExecutionDialogVisible.value = false
      await loadSepsisBundleStatus()
    } catch (e: any) { alert(e?.response?.data?.message || '记录失败') }
    finally { sepsisBundleSubmitting.value = false }
  }

  // ─── Threshold review ───
  async function reviewPersonalizedThreshold(record: any, status: 'approved' | 'rejected', meta?: { reviewer?: string; review_comment?: string }) {
    if (!meta) {
      thresholdReviewTarget.value = record || null
      thresholdReviewStatus.value = status
      thresholdReviewReviewer.value = ''
      thresholdReviewComment.value = status === 'approved' ? '同意采用该个性化阈值建议。' : '暂不采用该个性化阈值建议。'
      thresholdReviewDialogOpen.value = true
      return
    }
    await submitPersonalizedThresholdReview(record, status, meta)
  }

  async function submitPersonalizedThresholdReview(record: any, status: 'approved' | 'rejected', meta: { reviewer?: string; review_comment?: string }) {
    if (personalizedThresholdReviewing.value) return
    const patientId = String(route.params.patientId || route.params.id || '')
    const recordId = String(record?._id || '')
    if (!patientId || !recordId) return
    personalizedThresholdReviewing.value = true
    try {
      await reviewPatientPersonalizedThreshold(patientId, recordId, { status, reviewer: meta?.reviewer || '', review_comment: meta?.review_comment || '' })
      message.success(status === 'approved' ? '已批准个性化阈值建议' : '已拒绝个性化阈值建议')
      thresholdReviewDialogOpen.value = false; thresholdReviewTarget.value = null
      await loadPersonalizedThresholds(true)
    } catch (e: any) { message.error(e?.response?.data?.message || '审核失败') }
    finally { personalizedThresholdReviewing.value = false }
  }

  async function confirmThresholdReview() {
    if (!thresholdReviewTarget.value) return
    await submitPersonalizedThresholdReview(thresholdReviewTarget.value, thresholdReviewStatus.value, {
      reviewer: thresholdReviewReviewer.value.trim(),
      review_comment: thresholdReviewComment.value.trim(),
    })
  }

  function cancelThresholdReview() {
    thresholdReviewDialogOpen.value = false; thresholdReviewTarget.value = null
  }

  // ─── Handoff ───
  async function copyHandoffSummary() {
    if (!aiHandoff.value) return
    try {
      const s = aiHandoff.value || {}
      const lines = [
        `Illness severity: ${s.illness_severity || 'watcher'}`,
        `Patient summary: ${s.patient_summary || ''}`,
        `Action list: ${normalizeList(s.action_list).join('；')}`,
        `Situation awareness: ${normalizeList(s.situation_awareness).join('；')}`,
        `Synthesis by receiver: ${s.synthesis_by_receiver || ''}`,
        `Confidence: ${s.confidence_level || 'low'}`,
      ]
      await navigator.clipboard.writeText(lines.join('\n'))
      aiHandoffError.value = '交班摘要已复制'
      setTimeout(() => { if (aiHandoffError.value === '交班摘要已复制') aiHandoffError.value = '' }, 1500)
    } catch { aiHandoffError.value = '复制失败' }
  }

  // ─── Reset ───
  function resetDetailState() {
    vitalForecast.abort('patient_switch')
    patient.value = null; bedcard.value = null; vitals.value = null
    selectedBodyOrgan.value = 'respiratory'; focusedAlertTypes.value = []
    trendPoints.value = []; trendLoaded.value = false
    waveformSelectedChannel.value = ''; waveformChannels.value = []; waveformPoints.value = []
    waveformQc.value = null; waveformEvents.value = []; waveformLoading.value = false; waveformError.value = ''
    labs.value = []; drugs.value = []; assessments.value = []
    labsLoaded.value = false; drugsLoaded.value = false; assessmentsLoaded.value = false
    alerts.value = []; trialMatches.value = []; trialMatchLoading.value = false; trialMatchError.value = ''
    sepsisBundleStatus.value = null; weaningStatus.value = null
    sbtTimelineSummary.value = null; sbtTimelineRecords.value = []; sbtTimelineAiSummary.value = null
    sbtTimelineLoading.value = false; sbtTimelineError.value = ''; sbtTimelineLoaded.value = false
    similarCaseReview.value = null; similarCaseLoading.value = false; similarCaseError.value = ''; similarCaseLoaded.value = false
    personalizedThresholdRecord.value = null; personalizedThresholdHistory.value = []; personalizedThresholdApprovedRecord.value = null
    personalizedThresholdLoading.value = false; personalizedThresholdError.value = ''; personalizedThresholdReviewing.value = false
    thresholdReviewDialogOpen.value = false; thresholdReviewTarget.value = null; thresholdReviewReviewer.value = ''; thresholdReviewComment.value = ''
    sepsisBundleNow.value = Date.now()
    aiLabLoading.value = false; aiRuleLoading.value = false; aiRiskLoading.value = false
    integratedRiskLoading.value = false; metabolicPhaseLoading.value = false
    betaBlockerAdvisorLoading.value = false; fibrinolysisLoading.value = false
    pronePositionLoading.value = false; picsRiskLoading.value = false; aiHandoffLoading.value = false
    knowledgeLoading.value = false; aiAutoLoaded.value = false
    aiLabSummary.value = ''; aiRuleText.value = ''; aiRulePayload.value = null
    aiRiskText.value = ''; aiRiskForecast.value = null; integratedRiskReport.value = null
    metabolicPhaseRecord.value = null; betaBlockerAdvisorRecord.value = null
    fibrinolysisRecord.value = null; pronePositionRecord.value = null
    picsRiskRecord.value = null; aiHandoff.value = null
    knowledgeDocs.value = []; selectedKnowledgeDocId.value = ''; selectedKnowledgeDoc.value = null
    aiLabError.value = ''; aiRuleError.value = ''; aiRiskError.value = ''
    integratedRiskError.value = ''; metabolicPhaseError.value = ''
    betaBlockerAdvisorError.value = ''; fibrinolysisError.value = ''
    pronePositionError.value = ''; picsRiskError.value = ''
    aiHandoffError.value = ''; knowledgeError.value = ''
  }

  // ─── Lifecycle ───
  function startSepsisBundleClock() {
    if (sepsisBundleTimer) clearInterval(sepsisBundleTimer)
    sepsisBundleTimer = setInterval(() => { sepsisBundleNow.value = Date.now() }, 1000)
  }

  function bindIntegratedRiskSocket() {
    if (offIntegratedRiskWs) offIntegratedRiskWs()
    offIntegratedRiskWs = onAlertMessage((msg: any) => {
      if (String(msg?.type || '') !== 'integrated_risk_report') return
      const payload = msg?.data || {}
      const patientId = String(route.params.patientId || route.params.id || '')
      if (!patientId || String(payload?.patient_id || '') !== patientId) return
      integratedRiskReport.value = payload; integratedRiskError.value = ''
    })
  }

  function initLifecycle() {
    readTrendLegendSelection()
    startSepsisBundleClock()
    bindIntegratedRiskSocket()
    void loadDetailPage()
  }

  function cleanupLifecycle() {
    if (sepsisBundleTimer) clearInterval(sepsisBundleTimer)
    sepsisBundleTimer = null
    if (offIntegratedRiskWs) offIntegratedRiskWs()
    offIntegratedRiskWs = null
    vitalForecast.abort('unmount')
  }

  // ═══════════════════════════════════════════
  //  Return public API
  // ═══════════════════════════════════════════

  return {
    // Core data
    patient, bedcard, vitals, alerts, clinicalSummary, clinicalSummaryLoading,

    // Display
    displayName, displaySubTitle, displayDiagnosis, displayAdmissionTime,
    displayHisPid, displayDept, displayBed, displayGenderAge, patientSilhouette,
    vitalsSourceText, heroMonitorUpdatedAt, heroFactRows, heroVitalsRows,

    // Sepsis
    sepsisBundleStatus, sepsisBundleNow, sepsisBundleStatusResolved,
    sepsisBundleStatusLight, sepsisBundleStatusText, sepsisBundleV2Info,
    sepsisInfectionVerdictText, sepsisInfectionLight,
    sepsisBundleFluidRiskCautions, sepsisBundleComplianceSummary,
    sepsisBundleHasReviewPending, sepsisBundleConclusion,
    sepsisBundleTimelineText, sepsisBundleExtraText,
    sepsisBundleReviewableElements,
    sepsisBundleReviewDialogVisible, sepsisBundleExecutionDialogVisible,
    sepsisBundleReviewForm, sepsisBundleExecutionForm, sepsisBundleSubmitting,

    // Weaning
    weaningStatus, weaningAssessment, sbtAssessment, postExtubationRisk,
    weaningRiskTone, weaningRiskLabel, weaningRecommendationText, weaningTopEvidence,
    latestWeaningAlert, latestPostExtubationAlert,
    postExtubationHeroVisible, postExtubationHeroTone, postExtubationHeroSeverityText,
    postExtubationHeroTitle, postExtubationHeroSummary, postExtubationHeroSuggestion,
    postExtubationHeroChips,
    sbtTimelineSummary, sbtTimelineRecords, sbtTimelineAiSummary,
    sbtTimelineLoading, sbtTimelineError, sbtTimelineLoaded,

    // Alerts
    latestCompositeAlert, latestAiRiskAlert,
    latestCompositeExtra, latestCompositeWindowHours, latestCompositeModi,
    latestCompositeOrganCount, latestCompositeInvolvedText,
    patientBodyMapStates, patientBodyMapDetails, deviceBodyMarkers,
    ecashAlerts, mobilityAlerts, peAlerts, latestEcashBundleAlert,

    // Body map
    selectedBodyOrgan, focusedAlertTypes,
    compositeOrganOrder, compositeOrganLabelDefault,

    // Trend / Waveform / Labs / Drugs / Assessments
    trendWindow, trendPoints, trendLoaded,
    waveformHours, waveformSelectedChannel, waveformChannels, waveformPoints,
    waveformQc, waveformEvents, waveformLoading, waveformError,
    labs, drugs, assessments, labsLoaded, drugsLoaded, assessmentsLoaded,
    drugColumns, assessmentColumns, drugTableRows, assessmentTableRows,

    // Forecast
    forecastCodes, trajectoryPublicConfig, forecastMeta,
    trendLegendStorageKey, trendLegendSelected,

    // Similar cases
    similarCaseReview, similarCaseLoading, similarCaseError, similarCaseLoaded,

    // Thresholds
    personalizedThresholdRecord, personalizedThresholdHistory,
    personalizedThresholdApprovedRecord, personalizedThresholdLoading,
    personalizedThresholdError, personalizedThresholdReviewing,
    thresholdReviewDialogOpen, thresholdReviewTarget,
    thresholdReviewStatus, thresholdReviewReviewer, thresholdReviewComment,

    // AI
    aiLabSummary, aiRuleText, aiRulePayload, aiRiskText, aiRiskForecast,
    integratedRiskReport, metabolicPhaseRecord, betaBlockerAdvisorRecord,
    fibrinolysisRecord, pronePositionRecord, picsRiskRecord, aiHandoff,
    aiLabError, aiRuleError, aiRiskError, integratedRiskError,
    metabolicPhaseError, betaBlockerAdvisorError, fibrinolysisError,
    pronePositionError, picsRiskError, aiHandoffError,
    aiLabLoading, aiRuleLoading, aiRiskLoading, integratedRiskLoading,
    metabolicPhaseLoading, betaBlockerAdvisorLoading, fibrinolysisLoading,
    pronePositionLoading, picsRiskLoading, aiHandoffLoading, aiAutoLoaded,
    aiRuleRows, aiHandoffConfidence, aiRuntimeSummary,

    // Knowledge
    knowledgeDocs, selectedKnowledgeDocId, selectedKnowledgeDoc,
    knowledgeLoading, knowledgeError, knowledgeStatus,

    // Evidence modal
    evidenceModalOpen, evidenceModal,

    // Clinical trials
    trialMatches, trialMatchLoading, trialMatchError,

    // Workbench
    followupWorkbenchSnapshot, similarWorkbenchSummary, thresholdWorkbenchSummary,

    // Helpers
    fmtBP, fmtTemp, fmtTime, fmtTimeShort, formatHeroMetric, formatClinicalNumber,
    formatClinicalMeasure, formatTime, statusLabel, sortAlertsDesc,
    normalizeSeverity, alertSeverityText, alertDomainLabel, alertPriorityLabel,
    alertSourceLabel, alertTypeText, alertCategoryText, labFlag,
    isAiRiskAlert, aiConfidenceClass, normalizeConfidenceLevel,
    aiRiskConfidenceLevel, aiRiskLevelText, feedbackOutcomeText,
    aiRiskOrganRows, aiRiskValidationIssues, aiRiskHallucinations,
    aiRiskEvidenceList, aiRiskExplainabilityRows,
    formatAlertExtra, formatAlertValue, formatDrugName, formatDose,
    normalizeList, knowledgeScopeText, formatAiError,
    stripModelThinking, stripMarkdownFence,

    // Action rail
    patientActionRail,

    // Actions
    loadDetailPage, loadAlerts, loadClinicalSummary, loadSepsisBundleStatus,
    loadWeaningStatus, loadTrend, loadLabs, loadDrugs, loadAssessments,
    loadWaveform, loadSbtTimeline, loadSimilarCaseReview, loadPersonalizedThresholds,
    loadAiLab, loadAiRules, loadAiRisk, loadIntegratedRisk,
    loadMetabolicPhase, loadBetaBlockerAdvisor, loadFibrinolysis,
    loadPronePosition, loadPicsRisk, loadAiHandoff, loadAiAll,
    loadKnowledgeDocs, loadKnowledgeDocument, handleReloadKnowledge,
    acknowledgeAlert, submitAiFeedback, openEvidence,
    openSepsisBundleReviewDialog, submitSepsisBundleReview,
    openSepsisBundleExecutionDialog, submitSepsisBundleExecution,
    reviewPersonalizedThreshold, confirmThresholdReview, cancelThresholdReview,
    copyHandoffSummary, resetDetailState,
    readTrendLegendSelection, saveTrendLegendSelection,

    // Lifecycle
    initLifecycle, cleanupLifecycle,

    // Router
    route, router,
  }
}
