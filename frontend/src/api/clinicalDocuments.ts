/**
 * Clinical document API wrappers.
 */
import axios from 'axios'

const aiApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 45000,
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

export type StatementKind = 'fact' | 'inference' | 'recommendation'
export type Priority = 'critical' | 'high' | 'medium' | 'low'
export type ReviewStatus = 'unreviewed' | 'reviewed' | 'edited'

export interface ClinicalStatement {
  id: string
  kind: StatementKind
  text: string
  confidence?: 'low' | 'medium' | 'high'
  evidence_refs: string[]
  missing_data?: string[]
  review_required?: boolean
}

export interface PatientBanner {
  bed_no: string
  age: string
  sex: string
  icu_day: string
  primary_diagnosis: string
  current_diagnosis?: string
  allergy_status: string
  isolation_status: string
  code_status: string
}

export interface OrganSupportItem {
  key: 'vent' | 'pressor' | 'crrt' | 'sedation' | 'lines' | 'infection'
  label: string
  status: 'active' | 'inactive' | 'unknown'
  summary: string
  missing_data: string[]
  evidence_refs: string[]
}

export interface TimelineEvent {
  id: string
  occurred_at: string
  category: 'vital' | 'lab' | 'medication' | 'procedure' | 'vent' | 'alert' | 'note'
  title: string
  description: string
  severity?: Priority
  evidence_refs: string[]
}

export interface SystemAPCard {
  id: string
  system:
    | 'neuro'
    | 'resp'
    | 'cv'
    | 'renal_fluid'
    | 'gi_nutrition'
    | 'id'
    | 'heme'
    | 'endo'
    | 'lines_devices'
    | 'goals'
  title: string
  priority: Priority
  status: ClinicalStatement[]
  trend: ClinicalStatement[]
  assessment: ClinicalStatement[]
  plan_items: ClinicalStatement[]
  missing_data: string[]
  evidence_refs: string[]
  review_status: ReviewStatus
}

export interface DailyGoal {
  id: string
  category:
    | 'map'
    | 'oxygenation'
    | 'rass'
    | 'fluid_balance'
    | 'antibiotics'
    | 'nutrition'
    | 'lines'
    | 'rehab'
    | 'family_communication'
    | 'night_plan'
  label: string
  target: string
  status: 'open' | 'done' | 'not_applicable'
  evidence_refs: string[]
  missing_data?: string[]
}

export interface RiskTask {
  id: string
  priority: Priority
  category: string
  title: string
  why_triggered: ClinicalStatement[]
  confirm_items: string[]
  suggested_actions: Array<{
    label: string
    action_type: 'add_to_plan' | 'create_order_draft_placeholder' | 'snooze' | 'dismiss'
  }>
  status: 'open' | 'done' | 'dismissed' | 'snoozed'
}

export interface NotePreview {
  style: 'APSO' | 'SOAP'
  generated_text: string
  final_text_override?: string | null
  is_overridden: boolean
  generated_from_hash: string
}

export interface RoundingWorkbenchDraft {
  schema_version: 'icu_rounding_workbench.v1'
  content_type: 'rounding_workbench'
  generated_at: string
  context_window: {
    start: string
    end: string
  }
  patient_banner: PatientBanner
  organ_support: OrganSupportItem[]
  timeline: TimelineEvent[]
  system_ap: SystemAPCard[]
  daily_goals: DailyGoal[]
  risk_tasks: RiskTask[]
  note_preview: NotePreview
  quality_checks: {
    critical_missing_data: string[]
    stale_data: Array<{ name: string; last_observed_at: string; age_hours: number }>
    contradictions: string[]
    warnings: string[]
  }
  raw_ai_tags: string[]
}

export interface LegacySoapDraft {
  subjective: string
  objective: Record<string, string | null | undefined>
  assessment: Record<string, string>
  plan: string[]
  overall_trend?: string
  key_concerns?: string[]
}

export type DraftContent = RoundingWorkbenchDraft | LegacySoapDraft

export interface VentilatorContext {
  mode: string
  fio2: number
  peep: number
  vt: number
  pplat: number
  pf_ratio: number | null
}

export interface ClinicalDocumentContextSnapshot {
  vent?: VentilatorContext | null
  [key: string]: any
}

export interface Citation {
  id?: string
  ref?: string
  source?: string
  source_type?: string
  title?: string
  observed_at?: string
  summary?: string
  raw_value?: any
}

export interface DraftResponse {
  draft_id: string
  draft: DraftContent
  citations: Citation[]
  hallucination_warnings: string[]
  context_snapshot: ClinicalDocumentContextSnapshot | null
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

export function isWorkbenchDraft(draft: DraftContent | null | undefined): draft is RoundingWorkbenchDraft {
  if (!draft || typeof draft !== 'object') return false
  const value = draft as any
  return (
    String(value.content_type || '').trim() === 'rounding_workbench'
    || String(value.schema_version || '').trim() === 'icu_rounding_workbench.v1'
    || (
      Array.isArray(value.organ_support)
      && Array.isArray(value.system_ap)
      && value.patient_banner
      && value.note_preview
    )
  )
}

export const generateProgressNote = (data: GenerateReq) =>
  aiApi.post<DraftResponse>('/api/clinical-documents/generate', data)

export const getDraft = (id: string) =>
  api.get<DraftResponse>(`/api/clinical-documents/${id}`)

export const updateDraft = (id: string, content: DraftContent) =>
  api.put(`/api/clinical-documents/${id}`, { content })

export const finalizeDraft = (id: string, signer: string) =>
  api.post(`/api/clinical-documents/${id}/finalize`, { signer })

export const listPatientDrafts = (patientId: string, limit = 10) =>
  api.get(`/api/clinical-documents/patients/${patientId}`, { params: { limit } })

export const listDraftVersions = (draftId: string) =>
  api.get(`/api/clinical-documents/${draftId}/versions`)

export const exportDraft = (id: string, format: 'docx' | 'pdf' = 'docx') =>
  api.post(`/api/clinical-documents/${id}/export`, { format }, { responseType: 'blob' })
