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

const bundleApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

// AI 调用可能耗时较长，单独加长超时
const aiApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 90000,
})

// 获取科室列表
export const getDepartments = () => api.get('/api/departments')

// 获取在院患者列表（支持按科室筛选）
export const getPatients = (params?: { dept?: string; dept_code?: string }) =>
  api.get('/api/patients', { params })

// 获取患者生命体征
export const getPatientVitals = (patientId: string) =>
  api.get(`/api/patients/${patientId}/vitals`)

// 获取患者详情
export const getPatientDetail = (patientId: string) =>
  api.get(`/api/patients/${patientId}`)

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

// 获取用药记录
export const getPatientDrugs = (patientId: string) =>
  api.get(`/api/patients/${patientId}/drugs`)

// 获取护理评估历史
export const getPatientAssessments = (patientId: string) =>
  api.get(`/api/patients/${patientId}/assessments`)

// 获取预警历史
export const getPatientAlerts = (patientId: string) =>
  api.get(`/api/patients/${patientId}/alerts`)

export const postPatientAlertsViewed = (patientId: string, payload?: { alert_ids?: string[]; actor?: string; source?: string }) =>
  api.post(`/api/patients/${patientId}/alerts/view`, payload || {})

export const postAlertAcknowledge = (alertId: string, payload?: { actor?: string; note?: string }) =>
  api.post(`/api/alerts/${alertId}/acknowledge`, payload || {})

// 获取最近预警
export const getRecentAlerts = (limit = 50, params?: { dept?: string; dept_code?: string }) =>
  analyticsApi.get('/api/alerts/recent', { params: { limit, ...(params || {}) } })

// 获取预警统计
export const getAlertStats = (window = '24h') =>
  analyticsApi.get('/api/alerts/stats', { params: { window } })

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

export const saveAiMdtWorkspace = (
  patientId: string,
  payload: {
    decisions?: Array<{ id?: string; action?: string; owner?: string; deadline?: string; monitoring?: string; review_time?: string; status?: string; note?: string }>
    consult_record?: string
    progress_record?: string
    order_drafts?: Array<{ id?: string; category?: string; order_text?: string; priority?: string; status?: string; source?: string }>
  }
) => aiApi.post(`/api/ai/mdt-workspace/${patientId}`, payload)

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

// 健康检查
export const healthCheck = () => api.get('/health')

export default api

