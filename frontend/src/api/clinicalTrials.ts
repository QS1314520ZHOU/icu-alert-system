import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 120000 })

export const getClinicalTrials = () => api.get('/api/clinical-trials')
export const postClinicalTrial = (payload: Record<string, any>) => api.post('/api/clinical-trials', payload)
export const putClinicalTrial = (trialId: string, payload: Record<string, any>) =>
  api.put(`/api/clinical-trials/${trialId}`, payload)
export const deleteClinicalTrial = (trialId: string) => api.delete(`/api/clinical-trials/${trialId}`)
export const postParseCriteria = (trialId: string, payload: Record<string, any>) =>
  api.post(`/api/clinical-trials/${trialId}/parse-criteria`, payload)
export const postActivateTrial = (trialId: string) => api.post(`/api/clinical-trials/${trialId}/activate`)
export const postDeactivateTrial = (trialId: string) => api.post(`/api/clinical-trials/${trialId}/deactivate`)
export const postScreenTrials = () => api.post('/api/clinical-trials/screen')
export const getTrialCandidates = () => api.get('/api/clinical-trials/candidates')
export const getPatientTrialMatches = (patientId: string) => api.get(`/api/clinical-trials/patients/${patientId}/matches`)
export const postCandidateStatus = (candidateId: string, payload: Record<string, any>) =>
  api.post(`/api/clinical-trials/candidates/${encodeURIComponent(candidateId)}/status`, payload)
