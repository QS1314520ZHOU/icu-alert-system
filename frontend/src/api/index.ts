import axios from 'axios'

const api = axios.create({
  // Use same-origin in dev so Vite proxy can handle /api and /health.
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 10000,
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

// 健康检查
export const healthCheck = () => api.get('/health')

export default api
