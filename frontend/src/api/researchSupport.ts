import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 180000 })

export const getResearchProjects = () => api.get('/api/research/projects')
export const postResearchProject = (payload: Record<string, any>) => api.post('/api/research/projects', payload)
export const putResearchProject = (projectId: string, payload: Record<string, any>) =>
  api.put(`/api/research/projects/${projectId}`, payload)
export const deleteResearchProject = (projectId: string) => api.delete(`/api/research/projects/${projectId}`)
export const getTopicSuggestions = () => api.get('/api/research/topic-suggestions')
export const postGenerateTopicSuggestions = () => api.post('/api/research/topic-suggestions/generate')
export const postOmopExport = (payload: Record<string, any>) => api.post('/api/research/omop/export', payload)
export const getDataQuality = () => api.get('/api/research/data-quality')
