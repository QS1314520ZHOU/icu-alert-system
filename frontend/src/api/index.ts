import axios from 'axios'

const api = axios.create({
  // Use same-origin in dev so Vite proxy can handle /api and /health.
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 10000,
})

// Analytics 页面会并发请求多个聚合接口，给它更宽松的超时窗口。
const analyticsApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

// 科研分析任务可能需要较长排队/计算时间，单独提供更长超时窗口。
const researchApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 180000,
})

const bundleApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

const alertsApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

// AI 调用可能耗时较长，单独加长超时
const aiApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 120000,
})

// 获取科室列表
export const getDepartments = () => api.get('/api/departments')

// 获取患者列表（支持按科室与科研范围筛选）
export const getPatients = (params?: { dept?: string; dept_code?: string; patient_scope?: 'in_dept' | 'out_dept' | 'all' }) =>
  api.get('/api/patients', { params })

export type PatientPriorityFilter = {
  dept?: string
  dept_code?: string
  limit?: number
}

export const getPatientPriority = (params?: PatientPriorityFilter) =>
  analyticsApi.get('/api/patients/priority', { params })

// 获取患者生命体征
export const getPatientVitals = (patientId: string) =>
  api.get(`/api/patients/${patientId}/vitals`)

// 获取患者详情
export const getPatientDetail = (patientId: string) =>
  api.get(`/api/patients/${patientId}`)

export const getPatientClinicalSummary = (patientId: string, params?: { hours?: number }) =>
  analyticsApi.get(`/api/patients/${patientId}/clinical-summary`, { params })

export const getAiWatching = (patientId: string, hours = 1) =>
  api.get(`/api/patients/${patientId}/ai-watching`, { params: { hours } })

// 获取患者床旁概览卡片数据 (增强型)
export const getPatientBedcard = (patientId: string) =>
  api.get(`/api/patients/${patientId}/bedcard`)

// 批量获取患者 Bundle 灯状态
export const getPatientBundleStatuses = (patientIds: string[]) =>
  bundleApi.post('/api/patients/bundle-status', patientIds)

// 获取患者检验结果
export const getPatientLabs = (patientId: string) =>
  api.get(`/api/patients/${patientId}/labs`)

// 获取生命体征趋势
export const getPatientVitalsTrend = (patientId: string, window = '24h') =>
  api.get(`/api/patients/${patientId}/vitals/trend`, { params: { window } })

export const getPatientVitalsForecast = (patientId: string, params?: { codes?: string; horizon_hours?: number }) =>
  api.get(`/api/patients/${patientId}/vitals/forecast`, { params })

// 获取用药记录
export const getPatientDrugs = (patientId: string) =>
  api.get(`/api/patients/${patientId}/drugs`)

// 获取护理评估历史
export const getPatientAssessments = (patientId: string) =>
  api.get(`/api/patients/${patientId}/assessments`)

// 获取预警历史
export const getPatientAlerts = (patientId: string) =>
  alertsApi.get(`/api/patients/${patientId}/alerts`)

export const postPatientAlertsViewed = (patientId: string, payload?: { alert_ids?: string[]; actor?: string; source?: string }) =>
  api.post(`/api/patients/${patientId}/alerts/view`, payload || {})

export const postAlertAcknowledge = (alertId: string, payload?: { actor?: string; note?: string; disposition?: string; override_reason_code?: string; override_reason_text?: string }) =>
  api.post(`/api/alerts/${alertId}/acknowledge`, payload || {})

export const postAlertDisposition = (
  alertId: string,
  payload: {
    action: string
    reason?: string
    actor?: string
    review_after_minutes?: number
    review_metrics?: string[]
  }
) => api.post(`/api/alerts/${alertId}/disposition`, payload)

export const postAlertReview = (
  alertId: string,
  payload: {
    result: string
    evidence?: string[]
    actor?: string
  }
) => api.post(`/api/alerts/${alertId}/review`, payload)

export const getScannerHealth = (params?: { days?: number; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/admin/scanner-health', { params })

export const postScannerHealthRecalculate = (payload?: { days?: number }) =>
  analyticsApi.post('/api/admin/scanner-health/recalculate', payload || {})

export const postScannerHealthInferOutcomes = (params?: { limit?: number; min_age_minutes?: number }) =>
  analyticsApi.post('/api/admin/scanner-health/infer-outcomes', undefined, { params })

export const getAdminQualityClosedLoop = (params?: { days?: number; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/admin/quality-closed-loop', { params })

export const getRuntimeConfig = () =>
  analyticsApi.get('/api/admin/runtime-config')

export const postRuntimeModules = (payload: { modules: any[] }) =>
  analyticsApi.post('/api/admin/runtime-config/modules', payload)

export const postRuntimeAi = (payload: Record<string, any>) =>
  analyticsApi.post('/api/admin/runtime-config/ai', payload)

export const postRuntimeAlertRule = (ruleId: string, payload: Record<string, any>) =>
  analyticsApi.post(`/api/admin/runtime-config/alert-rules/${ruleId}`, payload)

export const postRuntimeFieldMapping = (payload: Record<string, any>) =>
  analyticsApi.post('/api/admin/runtime-config/field-mapping', payload)

export const getClinicalRoleHome = (params?: { userName?: string; role?: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/clinical-workflow/role-home', { params, timeout: 8000 })

export const getClinicalAccount = (params?: { userName?: string; role?: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  api.get('/api/clinical-workflow/account', { params, timeout: 2500 })

export const getClinicalPatientStory = (patientId: string, params?: { hours?: number }) =>
  analyticsApi.get(`/api/clinical-workflow/patients/${patientId}/story`, { params })

export const getClinicalPatientHandoff = (patientId: string, params?: { role?: string; hours?: number }) =>
  analyticsApi.get(`/api/clinical-workflow/patients/${patientId}/handoff`, { params })

export const getClinicalQualitySummary = (params?: { days?: number; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/clinical-workflow/quality-summary', { params })

export const getDoctorHome = (params: { user_id: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/home/doctor', { params })

export const getNurseHome = (params: { user_id: string; shift_code?: string; view?: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/home/nurse', { params })

export const getNurseTimeline = (params: { user_id: string; shift_code?: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/home/nurse/timeline', { params })

export const getNurseBundles = (params: { patient_ids: string[] | string; shift_code?: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.get('/api/home/nurse/bundles', { params })

export const postNurseBundles = (payload: { patient_ids: string[]; shift_code?: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  analyticsApi.post('/api/home/nurse/bundles', payload)

export const postNurseTaskExecute = (taskId: string, payload: Record<string, any>) =>
  analyticsApi.post(`/api/home/nurse/task/${taskId}/execute`, payload)

export const postNurseReminderFeedback = (alertId: string, payload: { actor?: string; disposition?: string; note?: string; override_reason_code?: string; override_reason_text?: string }) =>
  api.post(`/api/alerts/${alertId}/acknowledge`, payload)

export const postNurseHandoffGenerate = (payload: { user_id: string; patient_ids: string[]; shift_code?: string; dept?: string; dept_code?: string; deptCode?: string }) =>
  aiApi.post('/api/home/nurse/handoff/generate', payload)

export const getCurrentShift = (params?: { now?: string }) =>
  api.get('/api/shift/current', { params })

export const getShiftList = (params?: { refresh?: boolean }) =>
  api.get('/api/shift/list', { params })

export const postClinicalTask = (payload: Record<string, any>) =>
  analyticsApi.post('/api/clinical-workflow/tasks', payload)

export const closeClinicalTask = (taskId: string, payload?: Record<string, any>) =>
  analyticsApi.post(`/api/clinical-workflow/tasks/${taskId}/close`, payload || {})

export const getTreatmentRecommendation = (patientId: string) =>
  aiApi.get(`/api/treatment/recommend/${patientId}`)

export const postTreatmentFeedback = (payload: {
  patient_id: string
  recommendation_id: string
  adopted?: boolean
  reason?: string
  actor?: string
}) => aiApi.post('/api/treatment/feedback', payload)

// 获取最近预警
export const getRecentAlerts = (limit = 50, params?: { dept?: string; dept_code?: string; patient_id?: string; bed?: string }) =>
  analyticsApi.get('/api/alerts/recent', { params: { limit, ...(params || {}) } })

// 获取预警统计
export const getAlertStats = (window = '24h', params?: { dept?: string; dept_code?: string }) =>
  analyticsApi.get('/api/alerts/stats', { params: { window, ...(params || {}) } })

export const getAlertLifecycleAnalytics = (params?: { window?: string; dept?: string; dept_code?: string }) =>
  analyticsApi.get('/api/alerts/lifecycle/analytics', { params })

// Bundle 合规总览
export const getBundleOverview = (params?: { dept?: string; dept_code?: string }) =>
  api.get('/api/bundle/overview', { params })

// 导管/装置风险热力图
export const getDeviceRiskHeatmap = (params?: { dept?: string; dept_code?: string }) =>
  api.get('/api/device-risk/heatmap', { params })

// Analytics: 预警频率
export const getAlertAnalyticsFrequency = (params?: {
  window?: string
  bucket?: 'hour' | 'day'
  dept?: string
  dept_code?: string
}) => analyticsApi.get('/api/alerts/analytics/frequency', { params })

// Analytics: 规则热力图
export const getAlertAnalyticsHeatmap = (params?: {
  window?: string
  top_n?: number
  dept?: string
  dept_code?: string
}) => analyticsApi.get('/api/alerts/analytics/heatmap', { params })

// Analytics: 科室/床位排名
export const getAlertAnalyticsRankings = (params?: {
  window?: string
  top_n?: number
  dept?: string
  dept_code?: string
}) => analyticsApi.get('/api/alerts/analytics/rankings', { params })

// Analytics: Sepsis 1h Bundle 月度合规率
export const getSepsisBundleCompliance = (params?: {
  month?: string
  dept?: string
  dept_code?: string
}) => analyticsApi.get('/api/analytics/sepsis-bundle/compliance', { params })

// Analytics: 脱机 / 再插管月度统计
export const getWeaningSummary = (params?: {
  month?: string
  dept?: string
  dept_code?: string
}) => analyticsApi.get('/api/analytics/weaning-summary', { params })

export const getScenarioCoverageAnalytics = (params?: {
  window?: string
  top_n?: number
  dept?: string
  dept_code?: string
}) => analyticsApi.get('/api/analytics/scenario-coverage', { params })

export const getNursingWorkloadAnalytics = (params?: {
  window?: string
  dept?: string
  dept_code?: string
}) => analyticsApi.get('/api/analytics/nursing-workload', { params })

// AI: 检验摘要
export const getAiLabSummary = (patientId: string) =>
  aiApi.get(`/api/ai/lab-summary/${patientId}`)

// AI: 规则推荐
export const getAiRuleRecommendations = (patientId: string) =>
  aiApi.get(`/api/ai/rule-recommendations/${patientId}`)

// AI: 风险预测
export const getAiRiskForecast = (patientId: string) =>
  aiApi.get(`/api/ai/risk-forecast/${patientId}`)

export const getAiProactiveManagement = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/proactive-management/${patientId}`, { params })

export const postAiProactiveInterventionFeedback = (
  patientId: string,
  interventionId: string,
  payload: { record_id?: string; status?: string; adopted?: boolean; note?: string; actor?: string }
) => aiApi.post(`/api/ai/proactive-management/${patientId}/interventions/${interventionId}/feedback`, payload)

export const getAiClinicalReasoning = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/clinical-reasoning/${patientId}`, { params })

export const getAiIntegratedRiskReport = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/integrated-risk/${patientId}`, { params })

export const getAiMetabolicPhase = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/metabolic-phase/${patientId}`, { params })

export const getAiBetaBlockerAdvisor = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/beta-blocker-advisor/${patientId}`, { params })

export const getAiFibrinolysisMonitor = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/fibrinolysis-monitor/${patientId}`, { params })

export const getAiPronePositionMonitor = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/prone-position/${patientId}`, { params })

export const getAiPicsRisk = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/pics-risk/${patientId}`, { params })

export const postAiCausalAnalysis = (
  patientId: string,
  payload: { abnormal_finding: string }
) => aiApi.post(`/api/ai/causal-analysis/${patientId}`, payload)

export const getAiNursingNoteSignals = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/nursing-note-signals/${patientId}`, { params })

export const getAiPatientDigitalTwin = (patientId: string, params?: { refresh?: boolean; hours?: number }) =>
  aiApi.get(`/api/ai/digital-twin/${patientId}`, { params })

export const postAiWhatIfSimulation = (
  patientId: string,
  payload: {
    intervention_type: 'vasopressor_up' | 'fluid_bolus' | 'diuresis' | 'fio2_up' | 'peep_up'
    intervention_label?: string
    horizon_minutes?: number
    dose_delta_pct?: number
    fluid_bolus_ml?: number
    fio2_delta?: number
    peep_delta?: number
    diuretic_intensity?: number
  }
) => aiApi.post(`/api/ai/what-if/${patientId}`, payload)

export const getAiSubphenotype = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/subphenotype/${patientId}`, { params })

export const getAiMultiAgentAssessment = (patientId: string, params?: { refresh?: boolean }) =>
  aiApi.get(`/api/ai/multi-agent/${patientId}`, { params })

export const getAiSystemPanels = (patientId: string, params?: { window?: '24h' | '72h' }) =>
  aiApi.get(`/api/ai/system-panels/${patientId}`, { params })

export const getAiMdtWorkspace = (patientId: string) =>
  aiApi.get(`/api/ai/mdt-workspace/${patientId}`)

export const getAiMdtWorkspaceSession = (patientId: string, sessionId: string) =>
  aiApi.get(`/api/ai/mdt-workspace/${patientId}`, { params: { session_id: sessionId } })

export const listAiMdtWorkspaceSessions = (patientId: string) =>
  aiApi.get(`/api/ai/mdt-workspace/${patientId}/sessions`)

export const saveAiMdtWorkspace = (
  patientId: string,
  payload: {
    session_id?: string
    phase?: string
    decisions?: Array<{ id?: string; action?: string; owner?: string; deadline?: string; monitoring?: string; review_time?: string; status?: string; note?: string }>
    consult_record?: string
    progress_record?: string
    final_summary?: string
    participants?: string[]
    tags?: string[]
    template_name?: string
    activity_log?: Array<{ title?: string; detail?: string; created_at?: string }>
    order_drafts?: Array<{ id?: string; category?: string; order_text?: string; priority?: string; status?: string; source?: string }>
  }
) => aiApi.post(`/api/ai/mdt-workspace/${patientId}`, payload)

export const postAiMdtDecisionConfirm = (
  patientId: string,
  sessionId: string,
  decisionId: string,
  payload: { action: 'confirm' | 'reject' | 'revise'; actor?: string; note?: string; expected_version?: number }
) => aiApi.post(`/api/ai/mdt-workspace/${patientId}/sessions/${sessionId}/decisions/${decisionId}/confirm`, payload)

export const generateAiDocument = (
  patientId: string,
  payload: { doc_type: 'mdt_summary' | 'daily_progress' | 'consultation_request'; time_range?: { start?: string; end?: string; hours?: number } }
) => aiApi.post(`/api/ai/documents/${patientId}`, payload)

// AI: 反馈闭环
export const postAiFeedback = (payload: {
  prediction_id: string
  outcome: 'confirmed' | 'dismissed' | 'inaccurate'
  module?: string
  detail?: Record<string, any>
}) => aiApi.post('/api/ai/feedback', payload)

export const getAiFeedbackSummary = (params?: { days?: number; limit?: number }) =>
  aiApi.get('/api/ai/feedback/summary', { params })

export const getAiMonitorSummary = (params?: { date?: string }) =>
  aiApi.get('/api/ai/monitor/summary', { params })

export const postAiConsultChat = (payload: {
  message: string
  patient_id?: string
  patient_ids?: string[]
  mode?: 'clinical' | 'free'
  history?: Array<{ role: 'user' | 'assistant'; content: string }>
  pending_clarifications?: string[]
}) => aiApi.post('/api/ai/chat-consult', payload)

// AI/RAG: 离线知识片段详情
export const getKnowledgeChunk = (chunkId: string) =>
  aiApi.get(`/api/knowledge/chunks/${encodeURIComponent(chunkId)}`)

export const getKnowledgeDocuments = () =>
  aiApi.get('/api/knowledge/documents')

export const getKnowledgeDocument = (docId: string) =>
  aiApi.get(`/api/knowledge/documents/${encodeURIComponent(docId)}`)

export const getKnowledgeStatus = () =>
  aiApi.get('/api/knowledge/status')

export const reloadKnowledge = () =>
  aiApi.post('/api/knowledge/reload')

// AI: 交班摘要(I-PASS)
export const getPatientHandoffSummary = (patientId: string) =>
  aiApi.get(`/api/patients/${patientId}/handoff-summary`)

// 转出风险评估
export const getPatientDischargeReadiness = (patientId: string) =>
  aiApi.get(`/api/patients/${patientId}/discharge-readiness`)

// Sepsis 1h Bundle 患者状态
export const getPatientSepsisBundleStatus = (patientId: string) =>
  api.get(`/api/patients/${patientId}/sepsis-bundle-status`)

// 脱机评估 / SBT 状态
export const getPatientWeaningStatus = (patientId: string) =>
  api.get(`/api/patients/${patientId}/weaning-status`)

// SBT 结构化记录时间线
export const getPatientSbtRecords = (patientId: string, limit = 20) =>
  api.get(`/api/patients/${patientId}/sbt-records`, { params: { limit } })

// 脱机全时间线（SBT / SAT / Bundle / 拔管风险）
export const getPatientWeaningTimeline = (patientId: string, limit = 40) =>
  api.get(`/api/patients/${patientId}/weaning-timeline`, { params: { limit } })

// 相似病例结局回溯
export const getPatientSimilarCaseOutcomes = (patientId: string, limit = 10) =>
  aiApi.get(`/api/patients/${patientId}/similar-case-outcomes`, { params: { limit } })

// 个性化报警阈值建议
export const getPatientPersonalizedThresholds = (
  patientId: string,
  params?: { status?: 'pending_review' | 'approved' | 'rejected' }
) => api.get(`/api/patients/${patientId}/personalized-thresholds`, { params })

export const getPatientPersonalizedThresholdHistory = (
  patientId: string,
  params?: { status?: 'pending_review' | 'approved' | 'rejected'; limit?: number }
) => api.get(`/api/patients/${patientId}/personalized-thresholds/history`, { params })

export const reviewPatientPersonalizedThreshold = (
  patientId: string,
  recordId: string,
  payload: { status: 'approved' | 'rejected'; reviewer?: string; review_comment?: string }
) => api.post(`/api/patients/${patientId}/personalized-thresholds/${recordId}/review`, payload)

export const getThresholdReviewCenter = (params?: {
  status?: 'pending_review' | 'approved' | 'rejected'
  limit?: number
}) => api.get('/api/personalized-thresholds/review-center', { params })

export const getPatientFollowupCase = (
  patientId: string,
  params?: { ensure_from_pics?: boolean; refresh_pics?: boolean }
) => api.get(`/api/followup_cases/patients/${patientId}`, { params })

export const getPatientFollowupOverview = (
  patientId: string,
  params?: { ensure_from_pics?: boolean; refresh_pics?: boolean }
) => api.get(`/api/followup_cases/patients/${patientId}/overview`, { params })

export const upsertPatientFollowupCase = (
  patientId: string,
  payload?: { source_module?: string; refresh_pics?: boolean; note?: string; actor?: string }
) => api.post(`/api/followup_cases/patients/${patientId}`, payload || {})

export const updateFollowupCaseStatus = (
  caseId: string,
  payload: { status: 'candidate' | 'active' | 'paused' | 'closed'; note?: string; actor?: string }
) => api.post(`/api/followup_cases/${caseId}/status`, payload)

export const getPatientFollowupTasks = (
  patientId: string,
  params?: { status?: string; limit?: number }
) => api.get(`/api/followup_tasks/patients/${patientId}`, { params })

export const createPatientFollowupTask = (
  patientId: string,
  payload: {
    template_key?: string
    title?: string
    description?: string
    category?: string
    due_at?: string
    priority?: string
    owner?: string
    note?: string
    actor?: string
  }
) => api.post(`/api/followup_tasks/patients/${patientId}`, payload)

export const updateFollowupTaskStatus = (
  taskId: string,
  payload: { status: 'open' | 'in_progress' | 'completed' | 'cancelled'; note?: string; actor?: string }
) => api.post(`/api/followup_tasks/${taskId}/status`, payload)

export const getPatientRehabReferrals = (
  patientId: string,
  params?: { status?: string; limit?: number }
) => api.get(`/api/rehab_referrals/patients/${patientId}`, { params })

export const createPatientRehabReferral = (
  patientId: string,
  payload: {
    template_key?: string
    referral_type?: string
    target_service?: string
    reason?: string
    recommendation?: string
    status?: string
    owner?: string
    scheduled_at?: string
    note?: string
    actor?: string
  }
) => api.post(`/api/rehab_referrals/patients/${patientId}`, payload)

export const updateRehabReferralStatus = (
  referralId: string,
  payload: {
    status: 'pending' | 'accepted' | 'scheduled' | 'completed' | 'rejected' | 'cancelled'
    note?: string
    scheduled_at?: string
    actor?: string
  }
) => api.post(`/api/rehab_referrals/${referralId}/status`, payload)

// 科研分析工作台
export const postResearchTable1 = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/table1', payload)

export const postResearchSurvival = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/survival', payload)

export const postResearchRegression = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/regression', payload)

export const postResearchRoc = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/roc', payload)

export const postResearchSubgroup = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/subgroup', payload)

export const postResearchTrend = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/trend', payload)

export const postResearchCorrelation = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/correlation', payload)

export const postResearchDescriptive = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/descriptive', payload)

export const postResearchCohortBuild = (payload: Record<string, any>) =>
  researchApi.post('/api/research/cohort/build', payload)

export const postResearchCohortPreview = postResearchCohortBuild

export const postResearchCohortSave = (payload: Record<string, any>) =>
  researchApi.post('/api/research/cohort/save', payload)

export const listResearchCohorts = (params?: { limit?: number }) =>
  researchApi.get('/api/research/cohort/list', { params })

export const deleteResearchCohort = (cohortId: string) =>
  researchApi.delete(`/api/research/cohort/${encodeURIComponent(cohortId)}`)

export const getResearchAnalyticsTaskStatus = (taskId: string) =>
  researchApi.get(`/api/research/analytics/tasks/${encodeURIComponent(taskId)}/status`)

export const postResearchExportFigure = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/export-figure', payload)

export const postResearchExportTable = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/export-table', payload)

export const postResearchExportBundle = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/export-bundle', payload)

export const previewResearchExport = (payload: Record<string, any>) =>
  researchApi.post('/api/research/export/preview', payload)

export const createResearchExportTask = (payload: Record<string, any>) =>
  researchApi.post('/api/research/export', payload)

export const getResearchExportTaskStatus = (taskId: string) =>
  researchApi.get(`/api/research/export/${encodeURIComponent(taskId)}/status`)

export const listResearchExportHistory = (params?: { status?: string; export_mode?: string }) =>
  researchApi.get('/api/research/export/history', { params })

export const saveResearchSession = (payload: Record<string, any>) =>
  researchApi.post('/api/research/analytics/session/save', payload)

export const listResearchSessions = (params?: { limit?: number }) =>
  researchApi.get('/api/research/analytics/session/list', { params })

export const getResearchSession = (sessionId: string) =>
  researchApi.get(`/api/research/analytics/session/${encodeURIComponent(sessionId)}`)

export const postResearchAiInterpret = (payload: Record<string, any>) =>
  aiApi.post('/api/research/ai/interpret', payload)

export const postResearchAiPlan = (payload: Record<string, any>) =>
  aiApi.post('/api/research/ai/plan', payload)

export const postResearchVariableSummary = (payload: Record<string, any>) =>
  researchApi.post('/api/research/variables/batch-summary', payload)

export const getResearchIcdSearch = (params: { q?: string; limit?: number }) =>
  researchApi.get('/api/research/icd/search', { params })

export const getResearchPlatformStatus = () =>
  researchApi.get('/api/research/platform/status')

export const postResearchPlatformCheck = () =>
  researchApi.post('/api/research/platform/check')

export const getResearchPlatformJobs = (params?: { limit?: number }) =>
  researchApi.get('/api/research/platform/jobs', { params })

export const getResearchPlatformArtifacts = (params?: { limit?: number }) =>
  researchApi.get('/api/research/platform/artifacts', { params })

export const getWaveformChannels = (patientId: string, params?: { hours?: number }) =>
  api.get(`/api/waveforms/patients/${patientId}/channels`, { params })

export const getWaveformSegments = (patientId: string, params: { channel: string; hours?: number; limit?: number }) =>
  api.get(`/api/waveforms/patients/${patientId}/segments`, { params })

export const getWaveformQuality = (patientId: string, params: { channel: string; hours?: number }) =>
  api.get(`/api/waveforms/patients/${patientId}/qc`, { params })

export const getWaveformEvents = (patientId: string, params: { channel: string; hours?: number }) =>
  api.get(`/api/waveforms/patients/${patientId}/events`, { params })

// 健康检查
export const healthCheck = () => api.get('/health')

export default api

