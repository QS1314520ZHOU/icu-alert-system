import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 60000 })

export type NutritionScopeParams = { dept?: string; dept_code?: string; patient_scope?: 'in_dept' | 'out_dept' | 'all' }
export type NutritionDashboardParams = NutritionScopeParams & { detail?: boolean }

export const getNutritionDashboard = (params?: NutritionDashboardParams) =>
  api.get('/api/nutrition/dashboard', { params })

export const getNutritionPatient = (patientId: string) =>
  api.get(`/api/nutrition/${patientId}`)

export const postNutritionTask = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/nutrition/${patientId}/task`, payload)

export const getNutritionTasks = (patientId: string) =>
  api.get(`/api/nutrition/${patientId}/tasks`)

export const closeNutritionTask = (taskId: string, payload?: Record<string, any>) =>
  api.post(`/api/nutrition/tasks/${taskId}/close`, payload || {})

export const postNutritionAiAdvice = (patientId: string, params?: { refresh?: boolean }) =>
  api.post(`/api/nutrition/${patientId}/ai-advice`, undefined, { params })
