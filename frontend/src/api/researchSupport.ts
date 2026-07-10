import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 180000 })
export type ResearchScopeParams = { department?: string; dept?: string; dept_code?: string; patient_scope?: 'in_dept' | 'out_dept' | 'all' }

export const getResearchProjects = () => api.get('/api/research/projects')
export const postResearchProject = (payload: Record<string, any>) => api.post('/api/research/projects', payload)
export const putResearchProject = (projectId: string, payload: Record<string, any>) =>
  api.put(`/api/research/projects/${projectId}`, payload)
export const deleteResearchProject = (projectId: string) => api.delete(`/api/research/projects/${projectId}`)
export const getTopicSuggestions = (params?: ResearchScopeParams) => api.get('/api/research/topic-suggestions', { params })
export const postGenerateTopicSuggestions = (payload?: ResearchScopeParams) => api.post('/api/research/topic-suggestions/generate', payload || {})
export const postOmopExport = (payload: Record<string, any>) => api.post('/api/research/omop/export', payload)
export const getDataQuality = (params?: ResearchScopeParams) => api.get('/api/research/data-quality', { params })
