import axios from 'axios'

const api = axios.create({
  // Use same-origin in dev so Vite proxy can handle /api and /health.
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 10000,
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

// 获取最近预警
export const getRecentAlerts = (limit = 50, params?: { dept?: string; dept_code?: string }) =>
  api.get('/api/alerts/recent', { params: { limit, ...(params || {}) } })

// 获取预警统计
export const getAlertStats = (window = '24h') =>
  api.get('/api/alerts/stats', { params: { window } })

// Analytics: 预警频率
export const getAlertAnalyticsFrequency = (params?: {
  window?: string
  bucket?: 'hour' | 'day'
  dept?: string
  dept_code?: string
}) => api.get('/api/alerts/analytics/frequency', { params })

// Analytics: 规则热力图
export const getAlertAnalyticsHeatmap = (params?: {
  window?: string
  top_n?: number
  dept?: string
  dept_code?: string
}) => api.get('/api/alerts/analytics/heatmap', { params })

// Analytics: 科室/床位排名
export const getAlertAnalyticsRankings = (params?: {
  window?: string
  top_n?: number
  dept?: string
  dept_code?: string
}) => api.get('/api/alerts/analytics/rankings', { params })

// AI: 检验摘要
export const getAiLabSummary = (patientId: string) =>
  aiApi.get(`/api/ai/lab-summary/${patientId}`)

// AI: 规则推荐
export const getAiRuleRecommendations = (patientId: string) =>
  aiApi.get(`/api/ai/rule-recommendations/${patientId}`)

// AI: 风险预测
export const getAiRiskForecast = (patientId: string) =>
  aiApi.get(`/api/ai/risk-forecast/${patientId}`)

// 健康检查
export const healthCheck = () => api.get('/health')

export default api
