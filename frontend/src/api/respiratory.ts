import { aiApi as api } from './http'

export type RespiratoryScopeParams = { dept?: string; dept_code?: string; patient_scope?: 'in_dept' | 'out_dept' | 'all' }

export const getRespiratoryDashboard = (params?: RespiratoryScopeParams) => api.get('/api/respiratory/dashboard', { params })
export const getVentilatedPatients = (params?: RespiratoryScopeParams) => api.get('/api/respiratory/ventilated-patients', { params })
export const getSbtCandidates = (params?: RespiratoryScopeParams) => api.get('/api/respiratory/sbt-candidates', { params })
export const getRespiratoryWorklist = (params?: RespiratoryScopeParams) => api.get('/api/respiratory/worklist', { params })
export const closeRespiratoryWorklistTask = (taskId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/worklist/${encodeURIComponent(taskId)}/close`, payload)
export const postSbtStatus = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/sbt/${patientId}/status`, payload)
export const getVentilatorTimeline = (patientId: string, hours = 72) =>
  api.get(`/api/respiratory/${patientId}/ventilator-timeline`, { params: { hours } })
export const getRespiratoryDeteriorationForecast = (patientId: string) =>
  api.get(`/api/respiratory/${patientId}/deterioration-forecast`)
export const getAirwayRecords = (patientId: string) => api.get(`/api/respiratory/${patientId}/airway-records`)
export const postAirwayRecord = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/${patientId}/airway-records`, payload)
export const getAirwayPlan = (patientId: string) => api.get(`/api/respiratory/${patientId}/airway-plan`)
export const postAirwayPlan = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/${patientId}/airway-plan`, payload)

export const postRespiratoryTaskDone = (patientId: string, payload: Record<string, any>) =>
  api.post(`/api/respiratory/${patientId}/airway-records`, {
    ...payload,
    note: payload?.note || '呼吸治疗工作台一键闭环记录。',
  })
