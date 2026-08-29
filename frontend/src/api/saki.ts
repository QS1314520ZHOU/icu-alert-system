/**
 * S-AKI 单病种科研中心 API 客户端
 */
import api from './index'

const BASE = '/api/disease-center/saki'

// ---- 接口定义 ----

export interface SepsisPhenotype {
  is_sepsis: boolean
  sofa_score: number
  sofa_delta: number
  baseline_sofa: number
  infection_evidence: { verdict: string; confidence: string; sources: any[] }
  organ_scores: Record<string, number>
  calc_time: string
  version: string
  evidence: any[]
}

export interface AKIPhenotype {
  aki_stage: number
  creatinine_baseline: number | null
  creatinine_current: number | null
  creatinine_ratio: number | null
  aki_type: string
  calc_time: string
  version: string
  evidence: any[]
}

export interface SAKICase {
  patient_id: string
  patient_name?: string
  department?: string
  is_saki: boolean
  saki_probability: string
  aki_stage: number
  sepsis_phenotype: SepsisPhenotype
  aki_phenotype: AKIPhenotype
  temporal_association: {
    associated: boolean
    sepsis_onset_time: string
    aki_onset_time: string
    time_delta_hours: number
  }
  risk_factors: any[]
  review_status: string
  evidence: any[]
  created_at: string
  updated_at: string
}

export interface SAKICohort {
  cohort_id: string
  name: string
  patient_count: number
  filters: Record<string, any>
  created_by: string
  created_at: string
}

export interface SAKIAuditEvent {
  event_id: string
  action: string
  resource_type: string
  resource_id: string
  actor: string
  details: Record<string, any>
  timestamp: string
}

// ---- 健康检查 ----
export const getSakiHealth = () => api.get(`${BASE}/health`)
export const getSakiConfig = () => api.get(`${BASE}/config`)

// ---- 表型计算 ----
export const calculateSepsisPhenotype = (patientId: string) =>
  api.post(`${BASE}/phenotype/sepsis/${patientId}`)

export const calculateAKIPhenotype = (patientId: string) =>
  api.post(`${BASE}/phenotype/aki/${patientId}`)

export const calculateSAKIPhenotype = (patientId: string) =>
  api.post(`${BASE}/phenotype/saki/${patientId}`)

export const batchPhenotypeCalculate = (patientIds: string[]) =>
  api.post(`${BASE}/phenotype/batch`, { patient_ids: patientIds })

// ---- 病例管理 ----
export const getSakiCases = (params?: Record<string, any>) =>
  api.get(`${BASE}/cases`, { params })

export const getSakiCaseDetail = (caseId: string) =>
  api.get(`${BASE}/cases/${caseId}`)

export const reviewSakiCase = (caseId: string, review: { reviewer_id: string; result: string; notes?: string }) =>
  api.post(`${BASE}/cases/${caseId}/review`, review)

export const getSakiCaseStatistics = () =>
  api.get(`${BASE}/cases/statistics`)

export const identifySakiCases = (params?: { patient_ids?: string[] }) =>
  api.post(`${BASE}/cases/identify`, params)

// ---- 队列管理 ----
export const buildSakiCohort = (params: { name?: string; filters: Record<string, any> }) =>
  api.post(`${BASE}/cohorts/build`, params)

export const getSakiCohorts = () =>
  api.get(`${BASE}/cohorts`)

export const getSakiCohortDetail = (cohortId: string) =>
  api.get(`${BASE}/cohorts/${cohortId}`)

export const getSakiCohortPatients = (cohortId: string, params?: Record<string, any>) =>
  api.get(`${BASE}/cohorts/${cohortId}/patients`, { params })

export const generateSakiSnapshot = (cohortId: string) =>
  api.post(`${BASE}/cohorts/${cohortId}/snapshot`)

export const deleteSakiCohort = (cohortId: string) =>
  api.delete(`${BASE}/cohorts/${cohortId}`)

// ---- 统计分析 ----
export const runTable1 = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/table1`, params)

export const runKM = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/km`, params)

export const runLogistic = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/logistic`, params)

export const runCox = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/cox`, params)

export const runROC = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/roc`, params)

export const runCreatinineTrajectory = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/creatinine-trajectory`, params)

export const runForest = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/forest`, params)

export const runOutcomes = (params: Record<string, any>) =>
  api.post(`${BASE}/analysis/outcomes`, params)

// ---- 数据质量与字段映射 ----
export const getSakiQualityCheck = () =>
  api.get(`${BASE}/quality/check`)

export const getFieldMappings = (params?: { collection?: string }) =>
  api.get(`${BASE}/field-mapping`, { params })

export const updateFieldMappings = (params: { collection: string; standard_name: string; hospital_fields: string[]; description?: string }) =>
  api.put(`${BASE}/field-mapping`, params)

// ---- 审计日志 ----
export const getSakiAuditLog = (params?: Record<string, any>) =>
  api.get(`${BASE}/audit`, { params })

// ---- 演示数据 ----
export const seedSakiDemoData = (count?: number) =>
  api.post(`${BASE}/demo/seed`, null, { params: { count: count || 50 } })

export const cleanupSakiTestData = () =>
  api.post(`${BASE}/demo/cleanup`)

// ---- 免责声明 ----
export const getSakiDisclaimer = () =>
  api.get(`${BASE}/disclaimer`)
