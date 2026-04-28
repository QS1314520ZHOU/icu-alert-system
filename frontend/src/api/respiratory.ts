import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 60000 })

export const getVentilatedPatients = () => api.get('/api/respiratory/ventilated-patients')
export const getSbtCandidates = () => api.get('/api/respiratory/sbt-candidates')
export const postSbtStatus = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/sbt/${patientId}/status`, payload)
export const getVentilatorTimeline = (patientId: string, hours = 72) =>
  api.get(`/api/respiratory/${patientId}/ventilator-timeline`, { params: { hours } })
export const getAirwayRecords = (patientId: string) => api.get(`/api/respiratory/${patientId}/airway-records`)
export const postAirwayRecord = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/${patientId}/airway-records`, payload)
export const getAirwayPlan = (patientId: string) => api.get(`/api/respiratory/${patientId}/airway-plan`)
export const postAirwayPlan = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/${patientId}/airway-plan`, payload)
