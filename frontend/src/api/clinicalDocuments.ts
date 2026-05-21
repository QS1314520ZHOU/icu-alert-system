/**
 * Clinical Documents API — TypeScript wrappers.
 */
import axios from 'axios'

// Use the same AI api instance (longer timeout) as the rest of the app
const aiApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 120000,
})

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 10000,
})

export interface GenerateReq {
  patient_id: string
  doc_type?: string
  hours?: number
}

export interface DraftContent {
  subjective: string
  objective: {
    vitals: string
    labs: string
    drugs: string
    ventilator?: string | null
    alerts?: string | null
  }
  assessment: Record<string, string>
  plan: string[]
  overall_trend: '好转' | '平稳' | '恶化'
  key_concerns: string[]
}

export interface Citation {
  ref: string
  source: string
}

export interface DraftResponse {
  draft_id: string
  draft: DraftContent
  citations: Citation[]
  hallucination_warnings: string[]
  context_snapshot: any
  model?: string
  status?: string
  current_content?: DraftContent
  finalized_by?: string
  finalized_at?: string
  updated_at?: string
}

export interface DraftVersion {
  draft_id: string
  version_no: number
  content: DraftContent
  modified_at: string
}

export const generateProgressNote = (data: GenerateReq) =>
  aiApi.post<DraftResponse>('/api/clinical-documents/generate', data)

export const getDraft = (id: string) =>
  api.get<DraftResponse>(`/api/clinical-documents/${id}`)

export const updateDraft = (id: string, content: DraftContent) =>
  api.put(`/api/clinical-documents/${id}`, { content })

export const finalizeDraft = (id: string, signer: string) =>
  api.post(`/api/clinical-documents/${id}/finalize`, { signer })

export const listPatientDrafts = (patientId: string, limit = 20) =>
  api.get(`/api/clinical-documents/patients/${patientId}`, { params: { limit } })

export const listDraftVersions = (draftId: string) =>
  api.get(`/api/clinical-documents/${draftId}/versions`)

export const exportDraft = (id: string, format: 'docx' | 'pdf' = 'docx') =>
  api.post(`/api/clinical-documents/${id}/export`, { format }, { responseType: 'blob' })
