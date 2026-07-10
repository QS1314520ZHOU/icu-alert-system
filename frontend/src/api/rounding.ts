import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 120000 })

export const getRoundingPatients = (params?: { dept?: string; dept_code?: string; limit?: number }) =>
  api.get('/api/rounding/patients', { params })
export const getRoundingSummary = (patientId: string, hours = 24) =>
  api.get(`/api/rounding/${patientId}/summary`, { params: { hours } })
export const postRoundingAiInsights = (patientId: string, hours = 24) =>
  api.post(`/api/rounding/${patientId}/ai-insights`, { hours })
export const postRoundingExport = (payload: { patient_ids: string[]; hours?: number; format?: 'markdown' | 'html' }) =>
  api.post('/api/rounding/export', payload)
export const getRoundingVersions = (patientId: string, limit = 20) =>
  api.get(`/api/rounding/${patientId}/versions`, { params: { limit } })
export const postRoundingVersion = (patientId: string, payload: { content: string; status?: string; source?: string; summary_snapshot?: Record<string, any> }) =>
  api.post(`/api/rounding/${patientId}/versions`, payload)
export const postRoundingVersionConfirm = (patientId: string, versionId: string, payload?: { status?: string; note?: string }) =>
  api.post(`/api/rounding/${patientId}/versions/${versionId}/confirm`, payload || {})
