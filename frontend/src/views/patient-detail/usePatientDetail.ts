import { ref, computed, nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import { getPatientDetail, getPatientBedcard, getPatientPersonalizedThresholdHistory, getPatientPersonalizedThresholds, getPatientVitals, getPatientLabs, getPatientVitalsTrend, getPatientDrugs, getPatientAssessments, getPatientAlerts, getPatientClinicalSummary, postPatientAlertsViewed, postAlertAcknowledge, getPatientSepsisBundleStatus, submitSepsisBundleElementReview, recordSepsisBundleExecution, getPatientWeaningTimeline, getPatientSimilarCaseOutcomes, getPatientWeaningStatus, getAiLabSummary, getAiRuleRecommendations, getAiRiskForecast, getAiIntegratedRiskReport, getAiMetabolicPhase, getAiBetaBlockerAdvisor, getAiFibrinolysisMonitor, getAiPronePositionMonitor, getAiPicsRisk, getWaveformChannels, getWaveformEvents, getWaveformQuality, getWaveformSegments, getPatientHandoffSummary, getKnowledgeChunk, getKnowledgeDocument, getKnowledgeDocuments, getKnowledgeStatus, postAiFeedback, reviewPatientPersonalizedThreshold, reloadKnowledge } from '../../api'
import { getPatientTrialMatches } from '../../api/clinicalTrials'
import { getOperatorIdentity } from '../../utils/operatorIdentity'
import { useRuntimePublicConfigStore } from '../../stores/runtimePublicConfig'
import { useVitalForecast } from '../../composables/useVitalForecast'
import { onAlertMessage } from '../../services/alertSocket'
import { buildDeviceMarkers, buildPatientOrganStateFromAlerts } from '../../utils/bodyMap'
import { detailTabOrder } from './types'
import type { DetailTabKey, DetailAreaKey } from './types'

type DetailTabGroup = 'focus' | 'monitor' | 'therapy' | 'history' | 'ai' | 'all'

export function usePatientDetail() {
  const route = useRoute()
  const router = useRouter()
  const runtimePublicConfig = useRuntimePublicConfigStore()
  const vitalForecast = useVitalForecast()
  const detailTabKeys = new Set<string>(detailTabOrder)
  const activeArea = ref<DetailAreaKey>((route.query.area as DetailAreaKey) || 'overview')
  const detailTabGroup = ref<DetailTabGroup>('focus')
  const areaTabGroupMap: Record<DetailAreaKey, { group: DetailTabGroup; tab: DetailTabKey }> = {
    overview: { group: 'focus', tab: 'trend' },
    monitoring: { group: 'monitor', tab: 'trend' },
    treatment: { group: 'therapy', tab: 'drugs' },
    decision: { group: 'focus', tab: 'alerts' },
    documents: { group: 'ai', tab: 'ai' },
  }
  function switchTabGroup(group: DetailTabGroup) { detailTabGroup.value = group }
  function setArea(area: DetailAreaKey) {
    activeArea.value = area
    const { group, tab } = areaTabGroupMap[area]
    switchTabGroup(group)
    activeTab.value = tab
    router.replace({ query: { ...route.query, area, tab } })
  }
  function normalizeDetailTab(raw: any): DetailTabKey { const key = String(raw || '').trim(); return detailTabKeys.has(key) ? (key as DetailTabKey) : 'trend' }
  const activeTab = ref<DetailTabKey>(normalizeDetailTab(route.query.tab))
  const tabsAnchor = ref<HTMLElement | null>(null)
  async function openTab(tab: DetailTabKey) { activeTab.value = tab; await nextTick(); tabsAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  async function openTopicTab(tab: string) { activeTab.value = normalizeDetailTab(tab); await nextTick(); tabsAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  const patient = ref<any>(null)
  const bedcard = ref<any>(null)
  const vitals = ref<any>(null)
  const selectedBodyOrgan = ref('respiratory')
  const focusedAlertTypes = ref<string[]>([])
  const trendWindow = ref('24h')
  const trendPoints = ref<any[]>([])
  const trendLoaded = ref(false)
  const forecastCodes = ['HR', 'MAP', 'SpO2', 'RR', 'Temp']
  const trajectoryPublicConfig = computed(() => { const cfg = runtimePublicConfig.trajectory || {}; return { enabled: cfg.enabled !== false, horizon_hours: Number(cfg.horizon_hours || 6), default_codes: Array.isArray(cfg.default_codes) && cfg.default_codes.length ? cfg.default_codes : forecastCodes } })
  const forecastMeta = computed(() => vitalForecast.meta.value)
  const trendLegendStorageKey = computed(() => `icu_forecast_legend_${getOperatorIdentity() || 'anonymous'}`)
  const trendLegendSelected = ref<Record<string, boolean>>({})
  const waveformHours = ref(6)
  const waveformSelectedChannel = ref('')
  const waveformChannels = ref<any[]>([])
  const waveformPoints = ref<any[]>([])
  const waveformQc = ref<any>(null)
  const waveformEvents = ref<any[]>([])
  const waveformLoading = ref(false)
  const labs = ref<any[]>([])
  const drugs = ref<any[]>([])
  const assessments = ref<any[]>([])
  const labsLoaded = ref(false)
  const drugsLoaded = ref(false)
  const assessmentsLoaded = ref(false)
  const alerts = ref<any[]>([])
  const clinicalSummary = ref<any>(null)
  const clinicalSummaryLoading = ref(false)
  const trialMatches = ref<any[]>([])
  const trialMatchLoading = ref(false)
  const trialMatchError = ref('')
  const sepsisBundleStatus = ref<any>(null)
  const sepsisBundleNow = ref(Date.now())
  let sepsisBundleTimer: ReturnType<typeof setInterval> | null = null
  const weaningStatus = ref<any>(null)
  const sbtTimelineSummary = ref<any>(null)
  const sbtTimelineRecords = ref<any[]>([])
  const sbtTimelineAiSummary = ref<any>(null)
  const sbtTimelineLoading = ref(false)
  const sbtTimelineError = ref('')
  const sbtTimelineLoaded = ref(false)
  const similarCaseReview = ref<any>(null)
  const similarCaseLoading = ref(false)
  const similarCaseError = ref('')
  const similarCaseLoaded = ref(false)
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
  const sepsisBundleReviewDialogVisible = ref(false)
  const sepsisBundleExecutionDialogVisible = ref(false)
  const sepsisBundleReviewForm = ref({ element_key: 'fluid_resuscitation', applicability: 'individualized', individualized_target_ml: undefined as number | undefined, reason: '', version: 0 })
  const sepsisBundleExecutionForm = ref({ element_key: '', status: 'met', completed_at: '', value: null as any, reason: '' })
  const sepsisBundleSubmitting = ref(false)
  const compositeOrganOrder = ['respiratory', 'circulatory', 'renal', 'coagulation', 'hepatic', 'neurologic']
  const compositeOrganLabelDefault: Record<string, string> = { respiratory: '呼吸', circulatory: '循环', renal: '肾脏', coagulation: '凝血', hepatic: '肝脏', neurologic: '神经' }
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
  const knowledgeDocs = ref<any[]>([])
  const selectedKnowledgeDocId = ref<string>('')
  const selectedKnowledgeDoc = ref<any>(null)
  const knowledgeLoading = ref(false)
  const knowledgeError = ref('')
  const knowledgeStatus = ref<any>(null)
  const evidenceModalOpen = ref(false)
  const evidenceModal = ref<any>({ title: '', source: '', package_name: '', package_version: '', category: '', owner: '', updated_at: '', priority: null, local_ref: '', recommendation: '', recommendation_grade: '', section_title: '', tags: [], content: '', related_chunks: [] })
  let offIntegratedRiskWs: (() => void) | null = null
  // ===== FORMATTING FUNCTIONS =====
  function fmtBP(v: any) { const s = v?.nibp_sys, d = v?.nibp_dia; return s != null || d != null ? `${s ?? '—'}/${d ?? '—'}` : '—' }
  function fmtTemp(v: any) { if (v == null) return '—'; const n = Number(v); return isNaN(n) ? '—' : n.toFixed(1) }
  function fmtTime(t: any) { if (!t) return ''; try { return dayjs(t).format('YYYY-MM-DD HH:mm') } catch { return '' } }
  function fmtTimeShort(t: any) { if (!t) return ''; try { return dayjs(t).format('MM-DD HH:mm') } catch { return '' } }
  function numberOrNull(value: any) { const n = Number(value); return Number.isFinite(n) ? n : null }
  function formatHeroMetric(value: any) { if (value == null || value === '') return '—'; const num = Number(value); if (!Number.isFinite(num)) return String(value); return Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1) }
  function formatClinicalNumber(value: any, digits = 1) { if (value == null || value === '') return '—'; const num = Number(value); if (!Number.isFinite(num)) return String(value); const r = Number(num.toFixed(digits)); if (digits <= 0 || Math.abs(r - Math.round(r)) < 1e-9) return String(Math.round(r)); return r.toFixed(digits).replace(/\.?0+$/, '') }
  function formatClinicalMeasure(value: any, unit = '', digits = 1) { const t = formatClinicalNumber(value, digits); return t === '—' ? t : `${t}${unit}` }
  function formatHeroPercent(value: any) { const t = formatHeroMetric(value); return t === '—' ? t : `${t}%` }
  function formatHeroHours(value: any) { if (value == null || value === '') return '—'; const num = Number(value); if (!Number.isFinite(num)) return String(value); if (num < 1) return `${Math.max(1, Math.round(num * 60))}min`; return `${num.toFixed(num >= 10 ? 0 : 1)}h` }
  function formatCountdown(seconds?: number | null) { if (seconds == null) return '—'; const safe = Math.max(0, Math.floor(seconds)); const h = Math.floor(safe / 3600), m = Math.floor((safe % 3600) / 60), s = safe % 60; return h > 0 ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s).padStart(2, '0')}s` }
  function escapeHtml(raw: string) { return raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
  function stripMarkdownFence(raw: string) { const text = String(raw || '').trim(); if (!text) return ''; const m = text.match(/^`(?:json|markdown|md)?\s*([\s\S]*?)\s*`$/i); return m?.[1] ? m[1].trim() : text.replace(/^`(?:json|markdown|md)?\s*/i, '').replace(/\s*`$/, '').trim() }
  function stripModelThinking(raw: any) { return String(raw || '').replace(/<think\b[^>]*>[\s\S]*?<\/think>/gi, '').replace(/<reasoning\b[^>]*>[\s\S]*?<\/reasoning>/gi, '').replace(/<analysis\b[^>]*>[\s\S]*?<\/analysis>/gi, '').trim() }
  void escapeHtml
  function formatAiError(raw: any) { const s = String(raw || ''); if (!s) return ''; if (s.includes('503')) return 'AI\u670D\u52A1\u6682\u4E0D\u53EF\u7528(503)'; if (s.includes('401')) return '\u9274\u6743\u5931\u8D25(401)'; return s }
  function normalizeSeverity(raw: any) { const s = String(raw || '').toLowerCase(); if (s === 'critical' || s.includes('crit')) return 'critical'; if (s === 'high' || s.includes('high')) return 'high'; return 'warning' }
  function topicToneFromSeverity(severity: any) { const s = String(severity || '').toLowerCase(); return (s === 'critical' || s === 'high') ? 'rose' : s === 'warning' ? 'amber' : 'cyan' }
  function sortAlertsDesc(rows: any[]) { return [...rows].sort((a: any, b: any) => dayjs(b?.created_at).valueOf() - dayjs(a?.created_at).valueOf()) }
  function normalizeList(raw: any): string[] { if (!Array.isArray(raw)) return []; return raw.map((x) => String(x || '').trim()).filter(Boolean) }
  function normalizeConfidenceLevel(raw: any) { const v = String(raw || '').toLowerCase(); return (v === 'low' || v === 'medium' || v === 'high') ? v : 'medium' }
  function readTrendLegendSelection() { try { trendLegendSelected.value = JSON.parse(localStorage.getItem(trendLegendStorageKey.value) || '') || {} } catch { trendLegendSelected.value = {} } }
  function saveTrendLegendSelection(sel: Record<string, boolean>) { trendLegendSelected.value = sel || {}; try { localStorage.setItem(trendLegendStorageKey.value, JSON.stringify(sel)) } catch {} }
  function handoffPlainText() { const s = aiHandoff.value || {}; return [`Illness severity: ${s.illness_severity || '—'}`, `Patient summary: ${s.patient_summary || '—'}`, `Confidence: ${s.confidence_level || '—'}`].join('\n') }
  async function copyHandoffSummary() { if (!aiHandoff.value) return; try { await navigator.clipboard.writeText(handoffPlainText()); message.success('\u4EA4\u73ED\u6458\u8981\u5DF2\u590D\u5236') } catch {} }
  function alertTypeText(raw: any) { const t = String(raw || ''); const m: Record<string, string> = { lab_threshold: 'lab', sofa: 'SOFA', qsofa: 'qSOFA', weaning: 'weaning', ai_risk: 'AI', liberation_bundle: 'eCASH' }; return m[t] || t.split('_').join(' ') }
  function formatAlertValue(a: any) { return a?.value ?? '—' }
  function aiRiskOrganRows(item: any) { const organ = item?.extra?.organ_assessment; const organLabels: Record<string, string> = { respiratory: '呼吸', cardiovascular: '循环', renal: '肾脏', hepatic: '肝脏', coagulation: '凝血', neurological: '神经' }; const statusLabels: Record<string, string> = { normal: '正常', impaired: '受损', failure: '衰竭' }; if (!organ || typeof organ !== 'object') return []; return Object.entries(organ).map(([key, val]: [string, any]) => ({ key, label: organLabels[key] || key, status_text: statusLabels[String(val?.status || '').toLowerCase()] || String(val?.status || '—'), evidence: String(val?.evidence || ''), confidence_level: normalizeConfidenceLevel(val?.confidence_level) })).filter((x) => x.label) }
  function formatDrugName(record: any) { return record?.drugName || record?.orderName || record?.drugSpec || '—' }
  function formatDose(record: any) { const dose = record?.dose; const unit = record?.doseUnit; if (dose == null || dose === '') return '—'; return unit ? `${dose}${unit}` : String(dose) }
  const displayName = computed(() => patient.value?.name || patient.value?.hisName || '加载中...')
  const displayDiagnosis = computed(() => patient.value?.clinicalDiagnosis || patient.value?.admissionDiagnosis || patient.value?.hisDiagnose || '暂无')
  const displayAdmissionTime = computed(() => { const raw = patient.value?.icuAdmissionTime || patient.value?.admissionTime; return fmtTime(raw) || '未知' })
  const displayDept = computed(() => patient.value?.hisDept || patient.value?.dept || '未知科室')
  const displayBed = computed(() => patient.value?.hisBed || patient.value?.bed || '—')
  const displayGenderAge = computed(() => [patient.value?.genderText || patient.value?.hisSex || '', patient.value?.age || patient.value?.hisAge || ''].filter(Boolean).join(' '))
  const patientSilhouette = computed<'female' | 'male'>(() => { const t = String(patient.value?.gender || patient.value?.genderText || '').toLowerCase(); return (t.includes('female') || t.includes('女')) ? 'female' : 'male' })
  const heroMonitorUpdatedAt = computed(() => fmtTime(vitals.value?.time) || '—')
  const heroVitalsRows = computed(() => { const v = vitals.value || {}; const m = formatHeroMetric(v?.ibp_map ?? v?.nibp_map); return [{ label: 'HR', value: v?.hr != null ? formatHeroMetric(v.hr) : '—' }, { label: 'BP', value: fmtBP(v) }, { label: 'MAP', value: m }, { label: 'RR', value: v?.rr != null ? formatHeroMetric(v.rr) : '—' }, { label: 'SpO₂', value: v?.spo2 != null ? `${formatHeroMetric(v.spo2)}%` : '—' }, { label: 'T', value: fmtTemp(v?.temp) }] })
  const sepsisBundleStatusResolved = computed(() => { const status = sepsisBundleStatus.value || {}; const now = sepsisBundleNow.value; const raw = String(status?.status || 'none').toLowerCase(); const d1h = status?.deadline_1h ? dayjs(status.deadline_1h).valueOf() : null; const d3h = status?.deadline_3h ? dayjs(status.deadline_3h).valueOf() : null; let eff = raw || 'none'; if (raw === 'pending') { if (typeof d3h === 'number' && now >= d3h) eff = 'overdue_3h'; else if (typeof d1h === 'number' && now >= d1h) eff = 'overdue_1h' } const r1h = typeof d1h === 'number' ? Math.floor((d1h - now) / 1000) : null; const r3h = typeof d3h === 'number' ? Math.floor((d3h - now) / 1000) : null; let light = 'gray', label = '未进入计时'; if (eff === 'met') { light = 'green'; label = '1h已达标' } else if (eff === 'met_late') { light = 'orange'; label = '已补执行(超1h)' } else if (eff === 'overdue_3h') { light = 'red'; label = '3h仍未执行' } else if (eff === 'overdue_1h') { light = 'red'; label = '1h已超时' } else if (eff === 'pending') { if (r1h != null && r1h <= 1800) { light = 'yellow'; label = '1h窗口临近' } else { light = 'blue'; label = '1h内待完成' } } return { ...status, status: eff, light, label, remaining_seconds_to_1h: r1h, remaining_seconds_to_3h: r3h } })
  const sepsisBundleStatusLight = computed(() => sepsisBundleStatusResolved.value?.light || 'gray')
  const sepsisBundleStatusText = computed(() => sepsisBundleStatusResolved.value?.label || '未进入计时')
  const sepsisBundleConclusion = computed(() => { const s = sepsisBundleStatusResolved.value; if (s?.status === 'met') return 'Bundle 已完成'; if (s?.status === 'met_late') return 'Bundle 已补执行'; if (s?.status === 'overdue_3h') return 'Bundle 超3h未完成'; if (s?.status === 'overdue_1h') return 'Bundle 超1h未完成'; return '未进入计时' })
  const sepsisBundleTimelineText = computed(() => { const s = sepsisBundleStatusResolved.value; const started = s?.bundle_started_at ? fmtTime(s.bundle_started_at) : ''; const dl = s?.deadline_1h ? fmtTime(s.deadline_1h) : ''; if (s?.status === 'met' || s?.status === 'met_late') return `\u8D77\u70B9 ${started}`; if (s?.status === 'pending' || s?.status === 'overdue_1h') return `\u8D77\u70B9 ${started} \u00B7 1h\u622A\u6B62 ${dl}`; return '\u672A\u89C1\u8BA1\u65F6\u8BB0\u5F55' })
  const sepsisBundleExtraText = computed(() => { const s = sepsisBundleStatusResolved.value; if (s?.status === 'pending') return `\u5269\u4F59 ${formatCountdown(s.remaining_seconds_to_1h)}`; if (s?.status === 'overdue_1h') return '\u5DF2\u8D85\u65F6'; return '' })
  const weaningAssessment = computed(() => weaningStatus.value?.weaning || {})
  const sbtAssessment = computed(() => weaningStatus.value?.sbt || {})
  const weaningRiskLabel = computed(() => { const lv = String(weaningAssessment.value?.risk_level || '').toLowerCase(); if (lv === 'critical') return '极高风险'; if (lv === 'high') return '高风险'; if (lv === 'warning') return '中风险'; return weaningAssessment.value?.has_assessment ? '低风险' : '待评估' })
  const weaningRecommendationText = computed(() => weaningAssessment.value?.recommendation ? String(weaningAssessment.value.recommendation) : '暂无脱机评估')
  const vitalsSourceText = computed(() => { if (!vitals.value?.source) return ''; if (vitals.value.source === 'monitor') return '监护仪'; return '未知' })
  const latestCompositeAlert = computed(() => alerts.value.find((a: any) => String(a?.alert_type || '') === 'multi_organ_deterioration_trend'))
  const latestAiRiskAlert = computed(() => alerts.value.find((a: any) => String(a?.alert_type || '') === 'ai_risk'))
  const latestCompositeExtra = computed(() => latestCompositeAlert.value?.extra || {})
  const latestCompositeOrganCount = computed(() => latestCompositeExtra.value?.organ_count ?? 0)
  const patientBodyMapStates = computed(() => buildPatientOrganStateFromAlerts(alerts.value))
  const patientBodyMapDetails = computed(() => compositeOrganOrder.map((key) => ({ key, label: compositeOrganLabelDefault[key] || key })))
  const deviceBodyMarkers = computed(() => buildDeviceMarkers({ alerts: alerts.value, bedcard: bedcard.value }))
  const ecashAlerts = computed(() => sortAlertsDesc(alerts.value.filter((r: any) => ['liberation_bundle', 'ecash_pain_overdue', 'ecash_pain_uncontrolled', 'ecash_rass_off_target', 'ecash_sat_due', 'ecash_benzo_in_use', 'sedation', 'delirium_risk', 'sedation_delirium_conversion'].includes(String(r?.alert_type || '')))))
  const mobilityAlerts = computed(() => sortAlertsDesc(alerts.value.filter((r: any) => ['icu_aw_risk', 'early_mobility_recommendation', 'vte_immobility_no_prophylaxis'].includes(String(r?.alert_type || '')))))
  const peAlerts = computed(() => sortAlertsDesc(alerts.value.filter((r: any) => ['pe_suspected', 'pe_wells_high'].includes(String(r?.alert_type || '')))))
  const drugTableRows = computed(() => drugs.value.map((r: any) => ({ ...r, drugNameText: formatDrugName(r), doseText: formatDose(r), routeText: r?.route || '—', frequencyText: r?.frequency || '—', executeTimeText: fmtTime(r?.executeTime) || '—' })))
  const assessmentTableRows = computed(() => assessments.value.map((r: any) => ({ ...r, timeText: fmtTime(r?.time) || '—', gcsText: r?.gcs ?? '—', rassText: r?.rass ?? '—', painText: r?.pain ?? '—', deliriumText: r?.delirium ?? '—', bradenText: r?.braden ?? '—' })))

  // ===== LOAD FUNCTIONS =====
  async function loadAlerts() { const pid = route.params.patientId || route.params.id as string; if (!pid) return; try { const res = await getPatientAlerts(pid); alerts.value = res.data.records || []; const ids = alerts.value.map((i: any) => String(i?._id || '')).filter(Boolean).slice(0, 50); if (ids.length) postPatientAlertsViewed(pid, { alert_ids: ids, actor: getOperatorIdentity(), source: 'patient_detail' }).catch(() => undefined) } catch {} }
  async function loadClinicalSummary() { const pid = String(route.params.patientId || route.params.id || '').trim(); if (!pid) return; clinicalSummaryLoading.value = true; try { const res = await getPatientClinicalSummary(pid, { hours: 24 }); clinicalSummary.value = res.data?.data || null } catch { clinicalSummary.value = null } finally { clinicalSummaryLoading.value = false } }
  async function loadSepsisBundleStatus() { const pid = route.params.patientId || route.params.id as string; if (!pid) return; try { const res = await getPatientSepsisBundleStatus(pid); sepsisBundleStatus.value = res.data?.status || null; sepsisBundleNow.value = Date.now() } catch { sepsisBundleStatus.value = null } }
  async function loadWeaningStatus() { const pid = route.params.patientId || route.params.id as string; if (!pid) return; try { const res = await getPatientWeaningStatus(pid); weaningStatus.value = res.data?.status || null } catch { weaningStatus.value = null } }
  async function loadTrend() { const pid = route.params.patientId || route.params.id as string; if (!pid) return; try { const res = await getPatientVitalsTrend(pid, trendWindow.value); trendPoints.value = res.data.points || []; trendLoaded.value = true } catch {} }
  async function loadLabs() { const pid = route.params.patientId || route.params.id as string; if (!pid || labsLoaded.value) return; try { const res = await getPatientLabs(pid); labs.value = res.data.exams || []; labsLoaded.value = true } catch {} }
  async function loadDrugs() { const pid = route.params.patientId || route.params.id as string; if (!pid || drugsLoaded.value) return; try { const res = await getPatientDrugs(pid); drugs.value = res.data.records || []; drugsLoaded.value = true } catch {} }
  async function loadAssessments() { const pid = route.params.patientId || route.params.id as string; if (!pid || assessmentsLoaded.value) return; try { const res = await getPatientAssessments(pid); assessments.value = res.data.records || []; assessmentsLoaded.value = true } catch {} }
  async function loadClinicalTrialMatches() { if (trialMatchLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; trialMatchLoading.value = true; try { const res = await getPatientTrialMatches(pid); trialMatches.value = res.data?.matches || [] } catch { trialMatchError.value = 'failed' } finally { trialMatchLoading.value = false } }
  async function loadSbtTimeline(force = false) { if (sbtTimelineLoading.value) return; if (sbtTimelineLoaded.value && !force) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; sbtTimelineLoading.value = true; try { const res = await getPatientWeaningTimeline(pid, 40); sbtTimelineSummary.value = res.data?.summary || null; sbtTimelineRecords.value = Array.isArray(res.data?.timeline) ? res.data.timeline : [] } catch (e: any) { sbtTimelineError.value = e?.response?.data?.message || 'failed' } finally { sbtTimelineLoading.value = false; sbtTimelineLoaded.value = true } }
  async function loadSimilarCaseReview(force = false) { if (similarCaseLoading.value) return; if (similarCaseLoaded.value && !force) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; similarCaseLoading.value = true; try { const res = await getPatientSimilarCaseOutcomes(pid, 10); similarCaseReview.value = res.data?.review || null } catch { similarCaseReview.value = { summary: { matched_cases: 0, degraded: true }, cases: [], historical_case_insight: { summary: 'failed', pattern_bullets: [] } } } finally { similarCaseLoading.value = false; similarCaseLoaded.value = true } }
  async function loadPersonalizedThresholds(force = false) { if (personalizedThresholdLoading.value) return; if (personalizedThresholdRecord.value && !force) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; personalizedThresholdLoading.value = true; try { const [l, h] = await Promise.all([getPatientPersonalizedThresholds(pid), getPatientPersonalizedThresholdHistory(pid, { limit: 6 })]); personalizedThresholdRecord.value = l.data?.record || null; personalizedThresholdHistory.value = Array.isArray(h.data?.rows) ? h.data.rows : [] } catch {} finally { personalizedThresholdLoading.value = false } }
  async function loadWaveform() { if (waveformLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; waveformLoading.value = true; try { const cr = await getWaveformChannels(pid, { hours: 24 }); waveformChannels.value = Array.isArray(cr.data?.rows) ? cr.data.rows : []; if (!waveformSelectedChannel.value && waveformChannels.value.length) waveformSelectedChannel.value = String(waveformChannels.value[0]?.channel || ''); if (!waveformSelectedChannel.value) { waveformPoints.value = []; waveformQc.value = null; waveformEvents.value = []; return } const [seg, qc, ev] = await Promise.all([getWaveformSegments(pid, { channel: waveformSelectedChannel.value, hours: waveformHours.value, limit: 2000 }), getWaveformQuality(pid, { channel: waveformSelectedChannel.value, hours: waveformHours.value }), getWaveformEvents(pid, { channel: waveformSelectedChannel.value, hours: waveformHours.value })]); waveformPoints.value = Array.isArray(seg.data?.rows) ? seg.data.rows : []; waveformQc.value = qc.data?.qc || null; waveformEvents.value = Array.isArray(ev.data?.events) ? ev.data.events : [] } catch {} finally { waveformLoading.value = false } }
  async function loadAiLab() { if (aiLabLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; aiLabLoading.value = true; try { const r = await getAiLabSummary(pid); aiLabSummary.value = stripModelThinking(r.data.summary || ''); aiLabError.value = formatAiError(r.data.error || '') } catch { aiLabError.value = 'failed' } finally { aiLabLoading.value = false } }
  async function loadAiRules() { if (aiRuleLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; aiRuleLoading.value = true; try { const r = await getAiRuleRecommendations(pid); aiRulePayload.value = Array.isArray(r.data.recommendations) ? r.data.recommendations : null; aiRuleText.value = stripModelThinking(typeof r.data.raw_text === 'string' ? r.data.raw_text : JSON.stringify(r.data.recommendations || '', null, 2)); aiRuleError.value = formatAiError(r.data.error || '') } catch { aiRuleError.value = 'failed' } finally { aiRuleLoading.value = false } }
  async function loadAiRisk() { if (aiRiskLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; aiRiskLoading.value = true; try { const r = await getAiRiskForecast(pid); aiRiskForecast.value = r.data || null; aiRiskText.value = stripModelThinking(r.data.risk_summary || ''); aiRiskError.value = formatAiError(r.data.error || '') } catch { aiRiskError.value = 'failed' } finally { aiRiskLoading.value = false } }
  async function loadIntegratedRisk(refresh = false) { if (integratedRiskLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; integratedRiskLoading.value = true; try { const r = await getAiIntegratedRiskReport(pid, { refresh }); integratedRiskReport.value = r.data.report || null; integratedRiskError.value = formatAiError(r.data.error || '') } catch { integratedRiskError.value = 'failed' } finally { integratedRiskLoading.value = false } }
  async function loadMetabolicPhase(refresh = false) { if (metabolicPhaseLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; metabolicPhaseLoading.value = true; try { const r = await getAiMetabolicPhase(pid, { refresh }); metabolicPhaseRecord.value = r.data.record || null } catch { metabolicPhaseRecord.value = { phase: 'insufficient_data', degraded: true } } finally { metabolicPhaseLoading.value = false } }
  async function loadBetaBlockerAdvisor(refresh = false) { if (betaBlockerAdvisorLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; betaBlockerAdvisorLoading.value = true; try { const r = await getAiBetaBlockerAdvisor(pid, { refresh }); betaBlockerAdvisorRecord.value = r.data.record || null; betaBlockerAdvisorError.value = formatAiError(r.data.error || '') } catch { betaBlockerAdvisorError.value = 'failed' } finally { betaBlockerAdvisorLoading.value = false } }
  async function loadFibrinolysis(refresh = false) { if (fibrinolysisLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; fibrinolysisLoading.value = true; try { const r = await getAiFibrinolysisMonitor(pid, { refresh }); fibrinolysisRecord.value = r.data.record || null } catch { fibrinolysisRecord.value = { score_type: 'fibrinolysis_monitor', assessment: { phenotype: 'insufficient_data' }, degraded: true } } finally { fibrinolysisLoading.value = false } }
  async function loadPronePosition(refresh = false) { if (pronePositionLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; pronePositionLoading.value = true; try { const r = await getAiPronePositionMonitor(pid, { refresh }); pronePositionRecord.value = r.data.record || null } catch { pronePositionError.value = 'failed' } finally { pronePositionLoading.value = false } }
  async function loadPicsRisk(refresh = false) { if (picsRiskLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; picsRiskLoading.value = true; try { const r = await getAiPicsRisk(pid, { refresh }); picsRiskRecord.value = r.data.record || null } catch { picsRiskError.value = 'failed' } finally { picsRiskLoading.value = false } }
  async function loadAiHandoff() { if (aiHandoffLoading.value) return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; aiHandoffLoading.value = true; try { const r = await getPatientHandoffSummary(pid); aiHandoff.value = r.data.summary || null; aiHandoffError.value = formatAiError(r.data.error || '') } catch { aiHandoffError.value = 'failed' } finally { aiHandoffLoading.value = false } }
  async function loadKnowledgeDocs() { if (knowledgeLoading.value) return; knowledgeLoading.value = true; try { const [r, s] = await Promise.all([getKnowledgeDocuments(), getKnowledgeStatus()]); knowledgeDocs.value = Array.isArray(r.data?.documents) ? r.data.documents : []; knowledgeStatus.value = s.data?.status || null; if (!selectedKnowledgeDocId.value && knowledgeDocs.value.length) { selectedKnowledgeDocId.value = String(knowledgeDocs.value[0].doc_id || ''); await loadKnowledgeDocument(selectedKnowledgeDocId.value) } } catch { knowledgeError.value = 'failed' } finally { knowledgeLoading.value = false } }
  async function loadKnowledgeDocument(docId?: any) { const id = String(docId || selectedKnowledgeDocId.value || '').trim(); if (!id) return; knowledgeLoading.value = true; try { const r = await getKnowledgeDocument(id); selectedKnowledgeDoc.value = r.data?.document || null } catch { knowledgeError.value = 'failed' } finally { knowledgeLoading.value = false } }
  async function handleReloadKnowledge() { if (knowledgeLoading.value) return; knowledgeLoading.value = true; try { await reloadKnowledge(); const [r, s] = await Promise.all([getKnowledgeDocuments(), getKnowledgeStatus()]); knowledgeDocs.value = Array.isArray(r.data?.documents) ? r.data.documents : []; knowledgeStatus.value = s.data?.status || null; message.success('knowledge updated') } catch { knowledgeError.value = 'failed' } finally { knowledgeLoading.value = false } }
  async function loadAiAll() { if (aiAutoLoaded.value) return; aiAutoLoaded.value = true; await Promise.allSettled([loadAiLab(), loadAiRules(), loadAiRisk(), loadIntegratedRisk(), loadMetabolicPhase(), loadBetaBlockerAdvisor(), loadFibrinolysis(), loadPronePosition(), loadPicsRisk(), loadKnowledgeDocs()]) }
  async function ensureForecast() { if (activeTab.value !== 'trend') return; const pid = route.params.patientId || route.params.id as string; if (!pid) return; const tw = trendWindow.value; const hlt = forecastHistoryLastTs.value; await runtimePublicConfig.loadTrajectoryConfig(); if (activeTab.value !== 'trend' || String(route.params.patientId || route.params.id || '') !== pid || trendWindow.value !== tw) return; const cfg = trajectoryPublicConfig.value; if (cfg.enabled === false) { vitalForecast.abort('disabled'); vitalForecast.state.data = null; return } const horizon = Number(cfg.horizon_hours || 6); const codes = cfg.default_codes || forecastCodes; await vitalForecast.load({ patientId: pid, trendWindow: tw, horizon, codes, historyLastTs: hlt }) }
  async function submitSepsisBundleReview() { const pid = route.params.patientId || route.params.id as string; if (!pid) return; sepsisBundleSubmitting.value = true; try { await submitSepsisBundleElementReview(pid, { element_key: sepsisBundleReviewForm.value.element_key, applicability: sepsisBundleReviewForm.value.applicability, reason: sepsisBundleReviewForm.value.reason || 'confirmed', version: sepsisBundleReviewForm.value.version, actor: getOperatorIdentity() || undefined }); sepsisBundleReviewDialogVisible.value = false; await loadSepsisBundleStatus() } catch (e: any) { alert(e?.response?.data?.message || 'failed') } finally { sepsisBundleSubmitting.value = false } }
  async function submitSepsisBundleExecution() { const pid = route.params.patientId || route.params.id as string; if (!pid) return; sepsisBundleSubmitting.value = true; try { await recordSepsisBundleExecution(pid, { element_key: sepsisBundleExecutionForm.value.element_key, status: sepsisBundleExecutionForm.value.status, completed_at: sepsisBundleExecutionForm.value.completed_at || undefined, value: sepsisBundleExecutionForm.value.value, reason: sepsisBundleExecutionForm.value.reason, actor: getOperatorIdentity() || undefined }); sepsisBundleExecutionDialogVisible.value = false; await loadSepsisBundleStatus() } catch (e: any) { alert(e?.response?.data?.message || 'failed') } finally { sepsisBundleSubmitting.value = false } }
  function openSepsisBundleReviewDialog() { const els = sepsisBundleReviewableElements.value; if (els.length > 0) { const first = els[0]!; sepsisBundleReviewForm.value = { element_key: first.key, applicability: 'individualized', individualized_target_ml: undefined, reason: '', version: first.version } } sepsisBundleReviewDialogVisible.value = true }
  function openSepsisBundleExecutionDialog() { sepsisBundleExecutionForm.value = { element_key: 'fluid_resuscitation', status: 'met', completed_at: new Date().toISOString(), value: null, reason: '' }; sepsisBundleExecutionDialogVisible.value = true }
  async function acknowledgeAlert(item: any, disposition = '') { const aid = String(item?._id || '').trim(); if (!aid) return; try { await postAlertAcknowledge(aid, { actor: getOperatorIdentity(), ...(disposition ? { disposition } : {}) }); message.success('confirmed') } catch (e: any) { message.error(e?.response?.data?.message || 'failed') } }
  async function submitAiFeedback(item: any, outcome: 'confirmed' | 'dismissed' | 'inaccurate') { const pid2 = String(item?._id || '').trim(); if (!pid2) return; try { await postAiFeedback({ prediction_id: pid2, outcome, module: 'ai_risk', detail: { patient_id: String(item?.patient_id || ''), rule_id: String(item?.rule_id || ''), alert_type: String(item?.alert_type || '') } }); message.success('recorded') } catch { message.error('failed') } }
  async function openEvidence(evidence: any) { const cid = String(evidence?.chunk_id || '').trim(); if (!cid) { message.warning('no chunk id'); return } try { const r = await getKnowledgeChunk(cid); const c = r.data?.chunk || {}; evidenceModal.value = { title: c.title || evidence.title || '', source: c.source || evidence.source || '', package_name: c.package_name || '', package_version: c.package_version || '', category: c.category || '', owner: c.owner || '', updated_at: c.updated_at || '', priority: c.priority ?? null, local_ref: c.local_ref || '', recommendation: c.recommendation || evidence.recommendation || '', recommendation_grade: c.recommendation_grade || '', section_title: c.section_title || '', tags: Array.isArray(c.tags) ? c.tags : [], content: c.content || evidence.quote || '', related_chunks: Array.isArray(c.related_chunks) ? c.related_chunks : [] }; evidenceModalOpen.value = true } catch { evidenceModal.value = { ...evidenceModal.value, content: evidence.quote || 'failed', source: evidence.source || '' }; evidenceModalOpen.value = true } }
  async function reviewPersonalizedThreshold(record: any, status: 'approved' | 'rejected', meta?: { reviewer?: string; review_comment?: string }) { if (!meta) { thresholdReviewTarget.value = record; thresholdReviewStatus.value = status; thresholdReviewDialogOpen.value = true; return } const pid2 = route.params.patientId || route.params.id as string; const rid = String(record?._id || ''); if (!pid2 || !rid) return; personalizedThresholdReviewing.value = true; try { await reviewPatientPersonalizedThreshold(pid2, rid, { status, reviewer: meta?.reviewer || '', review_comment: meta?.review_comment || '' }); thresholdReviewDialogOpen.value = false; await loadPersonalizedThresholds(true) } catch { message.error('failed') } finally { personalizedThresholdReviewing.value = false } }
  function resetDetailState() { vitalForecast.abort('patient_switch'); patient.value = null; bedcard.value = null; vitals.value = null; alerts.value = []; labs.value = []; drugs.value = []; assessments.value = []; labsLoaded.value = false; drugsLoaded.value = false; assessmentsLoaded.value = false; sepsisBundleStatus.value = null; weaningStatus.value = null; similarCaseReview.value = null; similarCaseLoaded.value = false; aiAutoLoaded.value = false; aiRiskForecast.value = null; aiHandoff.value = null }
  function startSepsisBundleClock() { if (sepsisBundleTimer) clearInterval(sepsisBundleTimer); sepsisBundleTimer = setInterval(() => { sepsisBundleNow.value = Date.now() }, 1000) }
  function bindIntegratedRiskSocket() { if (offIntegratedRiskWs) offIntegratedRiskWs(); offIntegratedRiskWs = onAlertMessage((msg: any) => { if (String(msg?.type || '') !== 'integrated_risk_report') return; const payload = msg?.data || {}; const pid = String(route.params.patientId || route.params.id || ''); if (!pid || String(payload?.patient_id || '') !== pid) return; integratedRiskReport.value = payload }) }
  async function loadDetailPage() { const pid = route.params.patientId || route.params.id as string; if (!pid) return; await Promise.allSettled([(async () => { try { const r = await getPatientDetail(pid); patient.value = r.data.patient || null } catch {} })(), (async () => { try { const r = await getPatientVitals(pid, 15000); vitals.value = r.data.vitals || null } catch {} })(), (async () => { try { const r = await getPatientBedcard(pid, 15000); bedcard.value = r.data?.data || null } catch {} })(), loadAlerts(), loadClinicalSummary(), loadSepsisBundleStatus(), loadWeaningStatus(), loadClinicalTrialMatches()]); void ensureActiveTabData(activeTab.value) }
  function ensureActiveTabData(tab: string) { if (tab === 'trend') { if (!trendLoaded.value) { void loadTrend() } else { void ensureForecast() } } if (tab === 'labs') void loadLabs(); if (tab === 'drugs') void loadDrugs(); if (tab === 'assess') void loadAssessments() }
  const forecastHistoryLastTs = computed(() => { const rows = trendPoints.value || []; return String(rows[rows.length - 1]?.time || '') })
  const sepsisBundleReviewableElements = computed(() => { const elements = sepsisBundleStatusResolved.value?.bundle_elements; if (!elements) return []; return Object.entries(elements).filter(([, item]: [string, any]) => item?.clinical_review?.status === 'pending' || item?.applicability === 'review_pending').map(([key, item]: [string, any]) => ({ key, applicability: item?.applicability || 'review_pending', version: item?.clinical_review?.version || 0, label: ({ fluid_resuscitation: 'fluid', antibiotic_assessment: 'abx' } as Record<string, string>)[key] || key })) })
  const aiRuntimeSummary = computed(() => { const meta = aiRiskForecast.value?.model_meta || {}; const ps = String(aiRiskForecast.value?.prediction_source || meta?.prediction_source || ''); const hasErr = Boolean(aiLabError.value || aiRuleError.value || aiRiskError.value); const pills: string[] = []; if (meta?.model_name) pills.push(meta.model_name); if (ps === 'rule_estimate') pills.push('rule'); let level = hasErr ? 'red' : 'cyan'; let text = hasErr ? 'AI error' : 'AI ok'; if (ps === 'rule_estimate') { level = 'warning'; text = 'Rule mode' } return { level, text, detail: '', pills } })

  // ===== WATCHERS =====
  watch(trendWindow, () => { trendLoaded.value = false; vitalForecast.abort('refresh'); if (activeTab.value === 'trend') void loadTrend() })
  watch(waveformHours, () => { if (activeTab.value === 'waveform') void loadWaveform() })
  watch(waveformSelectedChannel, () => { if (activeTab.value === 'waveform') void loadWaveform() })
  watch(activeTab, (tab) => { ensureActiveTabData(tab); if (String(route.query.tab || '') !== tab) router.replace({ query: { ...route.query, tab } }); if (tab === 'sbt') void loadSbtTimeline(); if (tab === 'waveform') void loadWaveform(); if (tab === 'similar') void loadSimilarCaseReview(); if (tab === 'ai') { void loadAiAll(); if (!aiHandoff.value && !aiHandoffLoading.value) void loadAiHandoff() } })
  watch(() => route.query.tab, (next) => { const normalized = normalizeDetailTab(next); if (normalized !== activeTab.value) activeTab.value = normalized })
  watch(() => route.params.patientId || route.params.id, (next, prev) => { if (next && next !== prev) { resetDetailState(); void loadDetailPage() } })
  watch(patientBodyMapStates, (next) => { const entries = Object.entries(next || {}); const top = entries.sort((a, b) => { const rank = (v: string) => ({ normal: 0, warning: 1, high: 2, critical: 3 } as Record<string, number>)[v] || 0; return rank(String(b[1])) - rank(String(a[1])) })[0]; if (!selectedBodyOrgan.value || (top && String((next as any)?.[selectedBodyOrgan.value as keyof typeof next] || 'normal') === 'normal')) { selectedBodyOrgan.value = String(top?.[0] || 'respiratory') } }, { immediate: true })

  // ===== LIFECYCLE =====
  onMounted(() => { readTrendLegendSelection(); startSepsisBundleClock(); bindIntegratedRiskSocket(); void loadDetailPage() })
  onBeforeUnmount(() => { if (sepsisBundleTimer) clearInterval(sepsisBundleTimer); sepsisBundleTimer = null; if (offIntegratedRiskWs) offIntegratedRiskWs(); offIntegratedRiskWs = null; vitalForecast.abort('unmount') })

  // ===== ADDITIONAL COMPUTED =====
  const latestWeaningAlert = computed(() => alerts.value.find((a: any) => String(a?.alert_type || '') === 'weaning'))
  const latestPostExtubationAlert = computed(() => alerts.value.find((a: any) => String(a?.alert_type || '') === 'post_extubation_failure_risk'))
  const latestPostExtubationExtra = computed(() => latestPostExtubationAlert.value?.extra || {})
  const latestCompositeWindowHours = computed(() => latestCompositeExtra.value?.window_hours ?? 4)
  const latestCompositeModi = computed(() => latestCompositeExtra.value?.modi ?? latestCompositeAlert.value?.value ?? null)

  // Alert severity/category helpers
  function alertSeverityText(raw: any) { const sev = normalizeSeverity(raw); if (sev === 'critical') return '危急'; if (sev === 'high') return '高风险'; return '预警' }
  function alertCategoryText(raw: any) { const map: Record<string, string> = { vital_signs: '生命体征', syndrome: '综合征', lab_results: '检验', trend: '趋势', nurse: '护理', ai: 'AI', ventilator: '呼吸机', drug_safety: '用药安全', fluid_balance: '液体平衡', composite_deterioration: '复合恶化', device_management: '装置管理', bundle: '解放束' }; return map[String(raw || '')] || String(raw || '').split('_').join(' ') }
  function alertDetailFields(item: any) { const t = String(item?.alert_type || ''); const extra = item?.extra || {}; const fields: Array<{ label: string; value: any }> = []; if (t === 'sofa' || t === 'septic_shock') { const sofa = extra?.sofa || extra; fields.push({ label: 'SOFA', value: sofa?.score ?? item?.value }, { label: 'ΔSOFA', value: sofa?.delta }) } else if (t === 'qsofa') { fields.push({ label: 'qSOFA', value: item?.value }, { label: 'SBP', value: extra?.sbp }, { label: 'RR', value: extra?.rr }) } else { fields.push({ label: '值', value: item?.value }) } return fields }
  function aiConfidenceClass(level: string) { const v = String(level || '').toLowerCase(); if (v === 'low') return 'ai-confidence-low'; if (v === 'medium') return 'ai-confidence-medium'; return 'ai-confidence-high' }
  function aiRiskLevelText(raw: any) { let v = String(raw || '').toLowerCase().replace(/\[\^[^\]]+\]/g, '').trim(); if (v === 'critical' || v === '极高') return '极高'; if (v === 'high' || v === '高') return '高'; if (v === 'warning' || v === 'warn' || v === 'medium' || v === '中') return '中'; if (v === 'low' || v === '低') return '低'; return v || '—' }
  function feedbackOutcomeText(raw: any) { const v = String(raw || '').toLowerCase(); if (v === 'confirmed') return '采纳'; if (v === 'dismissed') return '忽略'; if (v === 'inaccurate') return '不准确'; return String(raw || '—') }
  const aiHandoffConfidence = computed(() => String(aiHandoff.value?.confidence_level || '').toLowerCase())
  const latestCompositeInvolvedText = computed(() => {
    const labels = latestCompositeExtra.value?.organ_labels_cn || {}
    const involved = Array.isArray(latestCompositeExtra.value?.involved_organs) ? latestCompositeExtra.value.involved_organs : []
    const names = involved.map((k: any) => labels?.[String(k)] || compositeOrganLabelDefault[String(k)] || String(k)).filter(Boolean)
    return names.length ? `涉及系统: ${names.join(' / ')}` : '涉及系统: 暂无'
  })
  const latestEcashBundleAlert = computed(() => ecashAlerts.value.find((row: any) => String(row?.alert_type || '') === 'liberation_bundle') || ecashAlerts.value[0] || null)
  const weaningRiskTone = computed(() => {
    const level = String(weaningAssessment.value?.risk_level || '').toLowerCase()
    if (level === 'critical' || level === 'high') return 'danger'
    if (level === 'warning') return 'warn'
    return 'stable'
  })
  const waveformChannelOptions = computed(() => waveformChannels.value.map((row: any) => ({ label: `${row.channel} (${row.sample_points || 0})`, value: row.channel })))
  const aiRuleColumns = [
    { title: '指标', dataIndex: 'parameter', key: 'parameter', width: 220, ellipsis: true },
    { title: '方向', dataIndex: 'operator', key: 'operator', width: 76, align: 'center' as const },
    { title: '阈值', dataIndex: 'threshold', key: 'threshold', width: 96, align: 'center' as const },
    { title: '级别', dataIndex: 'severity', key: 'severity', width: 96, align: 'center' as const },
    { title: '依据', dataIndex: 'reason', key: 'reason', width: 320, ellipsis: true },
  ]
  function normalizeAiRuleItems(items: any[]) { return (items || []).map((r: any) => ({ parameter: r?.parameter || r?.name || '—', operator: r?.operator || r?.direction || '—', threshold: r?.threshold ?? r?.value ?? '—', severity: r?.severity || r?.level || '—', reason: r?.reason || r?.evidence || '' })) }
  function parseAiRuleRows(raw: any) { try { const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw; return normalizeAiRuleItems(Array.isArray(parsed) ? parsed : []) } catch { return [] } }
  const aiRuleRows = computed(() => { if (Array.isArray(aiRulePayload.value) && aiRulePayload.value.length) return normalizeAiRuleItems(aiRulePayload.value); return parseAiRuleRows(aiRuleText.value) })
  function renderAiRichText(text: any) { return stripModelThinking(stripMarkdownFence(String(text || ''))) }
  function knowledgeScopeText(scope: any) { const value = String(scope || '').toLowerCase(); if (value === 'institutional') return '院内SOP/制度'; if (value === 'external') return '外部指南'; if (value === 'local') return '本地资料'; return value || '未知' }
  function isAiRiskAlert(item: any) { return String(item?.alert_type || '') === 'ai_risk' }
  function aiRiskConfidenceLevel(item: any) { return normalizeConfidenceLevel(item?.extra?.confidence?.overall || item?.extra?.explainability?.confidence_level || 'medium') }
  function aiRiskValidationIssues(item: any) { const issues = item?.extra?.safety_validation?.issues; return Array.isArray(issues) ? issues : [] }
  function aiRiskHallucinations(item: any) { const flags = item?.extra?.hallucination_flags; return Array.isArray(flags) ? flags : [] }
  function aiRiskEvidenceList(item: any) { const evidence = item?.extra?.evidence_sources; return Array.isArray(evidence) ? evidence : [] }
  function aiRiskExplainabilityRows(item: any) { const rows = item?.extra?.explainability?.top_factors; return Array.isArray(rows) ? rows : [] }
  function formatAlertExtra(extra: any) { try { return JSON.stringify(extra, null, 2) } catch { return '' } }
  function labFlag(item: any) { const flag = item.resultFlag || item.abnormalFlag || item.flag; if (!flag) return ''; const f = String(flag); if (f.includes('H') || f.includes('↑')) return 'lab-high'; if (f.includes('L') || f.includes('↓')) return 'lab-low'; return '' }
  function alertDomainLabel(raw: any) { const map: Record<string, string> = { physiologic_alarm: '生理危急', clinical_risk: '临床风险', workflow_reminder: '流程提醒', quality_gap: '质控缺项', data_quality: '数据质量', ai_advisory: 'AI建议', unknown: '未分类' }; return map[String(raw || '').toLowerCase()] || '' }
  function alertPriorityLabel(raw: any) { const map: Record<string, string> = { p0: 'P0', p1: 'P1', p2: 'P2', p3: 'P3' }; return map[String(raw || '').toLowerCase()] || '' }
  function alertSourceLabel(raw: any) { const map: Record<string, string> = { rule: '规则', trained_model: '模型', heuristic: '启发式', llm: 'LLM', manual: '人工', device_native: '设备', hybrid: '混合' }; return map[String(raw || '').toLowerCase()] || '' }
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
  const trendMetricDefs = [
    { key: 'hr', code: 'HR', name: 'HR', forecastName: 'HR · 预测', color: '#15558D', threshold: 12, get: (p: any) => numberOrNull(p.hr) },
    { key: 'map', code: 'MAP', name: 'MAP', forecastName: 'MAP · 预测', color: '#1A9C5B', threshold: 8, get: (p: any) => numberOrNull(p.ibp_map ?? p.nibp_map) },
    { key: 'spo2', code: 'SpO2', name: 'SpO2', forecastName: 'SpO2 · 预测', color: '#a78bfa', threshold: 3, get: (p: any) => numberOrNull(p.spo2) },
    { key: 'rr', code: 'RR', name: 'RR', forecastName: 'RR · 预测', color: '#E8901C', threshold: 5, get: (p: any) => numberOrNull(p.rr) },
    { key: 'temp', code: 'Temp', name: '体温', forecastName: '体温 · 预测', color: '#D9342B', threshold: 0.8, get: (p: any) => numberOrNull(p.temp) },
  ]
  function alphaColor(hex: string, alpha: number) {
    const clean = hex.replace('#', '')
    const r = parseInt(clean.slice(0, 2), 16)
    const g = parseInt(clean.slice(2, 4), 16)
    const b = parseInt(clean.slice(4, 6), 16)
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  const trendOption = computed(() => {
    const forecast = vitalForecast.state.data || {}
    const forecastSeries = forecast?.series || {}
    const meta = vitalForecast.meta.value
    void meta
    void forecastHistoryLastTs
    const tooltipLookup = new Map<string, any>()
    const series: any[] = []
    trendMetricDefs.forEach((metric) => {
      const historyData = trendPoints.value.map((p) => { const value = metric.get(p); return p?.time && value != null ? [p.time, value] : null }).filter(Boolean) as any[]
      const lastHistory = [...historyData].reverse().find((row) => row?.[1] != null)
      series.push({ id: `${metric.key}_hist`, name: metric.name, type: 'line', smooth: true, showSymbol: false, connectNulls: true, data: historyData, lineStyle: { width: 2, color: metric.color }, itemStyle: { color: metric.color } })
      const rows = Array.isArray(forecastSeries?.[metric.code]?.forecast) ? forecastSeries[metric.code].forecast : []
      if (rows.length) {
        const forecastData = rows.map((r: any) => [r.time, r.value]).filter((r: any) => r[0] && r[1] != null)
        if (lastHistory) forecastData.unshift(lastHistory)
        series.push({ id: `${metric.key}_forecast`, name: metric.forecastName, type: 'line', smooth: true, showSymbol: false, connectNulls: true, data: forecastData, lineStyle: { width: 1.5, type: 'dashed', color: alphaColor(metric.color, 0.55) }, itemStyle: { color: alphaColor(metric.color, 0.55) } })
      }
      if (lastHistory) tooltipLookup.set(metric.name, { name: metric.name, value: lastHistory[1], color: metric.color, threshold: metric.threshold })
    })
    return { tooltip: { trigger: 'axis', confine: true }, grid: { left: 56, right: 24, top: 40, bottom: 40 }, xAxis: { type: 'time' }, yAxis: { type: 'value', scale: true }, series, legend: { show: true, top: 4, textStyle: { fontSize: 11 } } }
  })
  const compositeRadarOption = computed(() => {
    const extra = latestCompositeExtra.value || {}
    const scoreMap = extra?.organ_scores || {}
    const labels = extra?.organ_labels_cn || {}
    const values = compositeOrganOrder.map((k) => { const raw = Number(scoreMap?.[k] ?? 0); return Number.isNaN(raw) ? 0 : Math.max(0, Math.min(3, raw)) })
    const indicator = compositeOrganOrder.map((k) => ({ name: labels?.[k] || compositeOrganLabelDefault[k] || k, max: 3 }))
    return { tooltip: { trigger: 'item', confine: true }, radar: { indicator, radius: '63%', splitNumber: 3, axisName: { color: '#7d93b5', fontSize: 11 }, axisLine: { lineStyle: { color: '#214368' } }, splitLine: { lineStyle: { color: ['#183357', '#1f3f67', '#26547c'] } }, splitArea: { areaStyle: { color: ['rgba(15, 33, 56, 0.28)', 'rgba(17, 37, 63, 0.22)', 'rgba(24, 53, 90, 0.16)'] } } }, series: [{ type: 'radar', data: [{ value: values, name: '器官严重程度', areaStyle: { color: 'rgba(56, 189, 248, 0.24)' }, lineStyle: { color: '#15558D', width: 2 }, itemStyle: { color: '#0ea5e9' } }] }] }
  })

  // ===== RETURN =====
  return {
    // Navigation
    activeArea, setArea, activeTab, tabsAnchor, openTab, openTopicTab, normalizeDetailTab,
    // Patient
    patient, bedcard, vitals, displayName, displayDiagnosis, displayAdmissionTime, displayDept, displayBed, displayGenderAge, patientSilhouette,
    // Hero
    heroMonitorUpdatedAt, heroVitalsRows, vitalsSourceText,
    // Body map
    selectedBodyOrgan, focusedAlertTypes, patientBodyMapStates, patientBodyMapDetails, deviceBodyMarkers,
    // Alerts
    alerts, alertTypeText, formatAlertValue, sortAlertsDesc,
    // Sepsis bundle
    sepsisBundleStatusResolved, sepsisBundleStatusLight, sepsisBundleStatusText, sepsisBundleConclusion, sepsisBundleTimelineText, sepsisBundleExtraText,
    sepsisBundleReviewDialogVisible, sepsisBundleExecutionDialogVisible, sepsisBundleReviewForm, sepsisBundleExecutionForm, sepsisBundleSubmitting,
    sepsisBundleReviewableElements, submitSepsisBundleReview, submitSepsisBundleExecution, openSepsisBundleReviewDialog, openSepsisBundleExecutionDialog,
    // Weaning
    weaningStatus, weaningAssessment, sbtAssessment, weaningRiskLabel, weaningRecommendationText,
    // SBT timeline
    sbtTimelineSummary, sbtTimelineRecords, sbtTimelineAiSummary, sbtTimelineLoading, sbtTimelineError, loadSbtTimeline,
    // Clinical summary
    clinicalSummary, clinicalSummaryLoading, loadClinicalSummary,
    // Trend
    trendWindow, trendPoints, trendLoaded, trendLegendSelected, readTrendLegendSelection, saveTrendLegendSelection,
    // Waveform
    waveformHours, waveformSelectedChannel, waveformChannels, waveformPoints, waveformQc, waveformEvents, waveformLoading, loadWaveform,
    // Labs/Drugs/Assessments
    labs, drugs, assessments, loadLabs, loadDrugs, loadAssessments, drugTableRows, assessmentTableRows,
    // Similar cases
    similarCaseReview, similarCaseLoading, similarCaseError, similarCaseLoaded, loadSimilarCaseReview,
    // Personalized thresholds
    personalizedThresholdRecord, personalizedThresholdHistory, personalizedThresholdApprovedRecord,
    personalizedThresholdLoading, personalizedThresholdError, personalizedThresholdReviewing,
    thresholdReviewDialogOpen, thresholdReviewTarget, thresholdReviewStatus, thresholdReviewReviewer, thresholdReviewComment,
    reviewPersonalizedThreshold,
    // Trial matches
    trialMatches, trialMatchLoading, trialMatchError,
    // AI
    aiLabSummary, aiRuleText, aiRulePayload, aiRiskText, aiRiskForecast,
    integratedRiskReport, metabolicPhaseRecord, betaBlockerAdvisorRecord, fibrinolysisRecord,
    pronePositionRecord, picsRiskRecord, aiHandoff,
    aiLabError, aiRuleError, aiRiskError, integratedRiskError, metabolicPhaseError,
    betaBlockerAdvisorError, fibrinolysisError, pronePositionError, picsRiskError, aiHandoffError,
    aiLabLoading, aiRuleLoading, aiRiskLoading, integratedRiskLoading, metabolicPhaseLoading,
    betaBlockerAdvisorLoading, fibrinolysisLoading, pronePositionLoading, picsRiskLoading, aiHandoffLoading,
    aiRuntimeSummary, loadAiAll, loadAiHandoff, copyHandoffSummary, submitAiFeedback,
    loadAiLab, loadAiRules, loadAiRisk, loadIntegratedRisk, loadMetabolicPhase,
    loadBetaBlockerAdvisor, loadFibrinolysis, loadPronePosition, loadPicsRisk,
    // Knowledge
    knowledgeDocs, selectedKnowledgeDocId, selectedKnowledgeDoc, knowledgeLoading, knowledgeError, knowledgeStatus,
    handleReloadKnowledge, loadKnowledgeDocs, loadKnowledgeDocument,
    // Evidence modal
    evidenceModalOpen, evidenceModal, openEvidence,
    // Formatting
    fmtBP, fmtTemp, fmtTime, fmtTimeShort, formatHeroMetric, formatClinicalNumber, formatClinicalMeasure,
    formatHeroPercent, formatHeroHours, formatCountdown, formatDrugName, formatDose, formatAlertExtra,
    labFlag, knowledgeScopeText, aiRiskOrganRows, aiRiskValidationIssues,
    aiRiskHallucinations, aiRiskEvidenceList, aiRiskExplainabilityRows,
    topicToneFromSeverity, normalizeSeverity, normalizeConfidenceLevel, isAiRiskAlert, aiRiskConfidenceLevel,
    alertDomainLabel, alertPriorityLabel, alertSourceLabel,
    alertSeverityText, alertCategoryText, alertDetailFields, aiConfidenceClass, aiRiskLevelText,
    feedbackOutcomeText, aiHandoffConfidence, normalizeList,
    // Alerts CRUD
    acknowledgeAlert, resetDetailState,
    // Load all
    loadDetailPage, loadAlerts, loadTrend,
    // Constants
    compositeOrganOrder, compositeOrganLabelDefault, forecastMeta, forecastHistoryLastTs,
    // ACash alerts
    ecashAlerts, mobilityAlerts, peAlerts, latestEcashBundleAlert,
    // Additional computed
    latestWeaningAlert, latestPostExtubationAlert, latestPostExtubationExtra,
    latestCompositeExtra, latestCompositeWindowHours, latestCompositeModi, latestCompositeInvolvedText,
    weaningRiskTone, waveformChannelOptions,
    trendOption, compositeRadarOption,
    drugColumns, assessmentColumns,
    aiRuleColumns, aiRuleRows, renderAiRichText,
    latestAiRiskAlert, latestCompositeAlert, latestCompositeOrganCount,
    // Forecast
    vitalForecast, trajectoryPublicConfig,
  }
}
