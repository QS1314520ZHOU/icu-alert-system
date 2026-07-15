/**
 * Handover — API module.
 *
 * Typed API functions for ISBAR structured handover endpoints.
 */
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 15000,
})

const aiApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 120000,
})

// ── Types ───────────────────────────────────────────────────────────

export interface GenerateReq {
  patient_id: string
  handover_type?: string   // "nurse_bedside" | "nurse_ward" | "doctor"
  shift_code?: string
}

export interface UpdateContentReq {
  sections: Record<string, any>
  edited_fields?: string[]
}

export interface ConfirmReq {
  operator: string
}

export interface AcknowledgeReq {
  operator: string
  forced_confirmations?: Array<Record<string, any>>
}

export interface RejectReq {
  operator: string
  reason?: string
}

export interface HandoverBrief {
  mode: string
  blocks: Array<{
    section: string
    icon: string
    lines: string[]
    urgent?: boolean
    tags?: string[]
  }>
  one_liner?: string
  key_points?: string[]
  has_critical?: boolean
}

export interface HandoverResponse {
  code: number
  handover: Record<string, any>
}

export interface HandoverListResponse {
  code: number
  handovers: Array<Record<string, any>>
  total: number
}

export interface HandoverBriefResponse {
  code: number
  handover_id: string
  patient_id: string
  mode: string
  brief: HandoverBrief
}

export interface ForcedAlertsResponse {
  code: number
  patient_id: string
  forced_confirmations: Array<{
    item_id: string
    item_type: string
    description: string
    confirmed: boolean
    confirmed_by: string
    confirmed_at: string
  }>
  total: number
}

// ── API Functions ───────────────────────────────────────────────────

/** Generate an AI-drafted ISBAR handover document. */
export const generateHandover = (data: GenerateReq) =>
  aiApi.post<HandoverResponse>('/api/handover/generate', data)

/** Get a single handover document by ID. */
export const getHandover = (handoverId: string) =>
  api.get<HandoverResponse>(`/api/handover/${handoverId}`)

/** List handover history for a patient. */
export const getPatientHandoverHistory = (
  patientId: string,
  params?: { limit?: number; handover_type?: string }
) =>
  api.get<HandoverListResponse>(`/api/handover/patients/${patientId}/history`, { params })

/** Manually edit handover content. */
export const updateHandoverContent = (handoverId: string, data: UpdateContentReq) =>
  api.put<HandoverResponse>(`/api/handover/${handoverId}/content`, data)

/** Confirm and submit handover for acknowledgment. */
export const confirmHandover = (handoverId: string, data: ConfirmReq) =>
  api.post<HandoverResponse>(`/api/handover/${handoverId}/confirm`, data)

/** Acknowledge handover (incoming shift signs off). */
export const acknowledgeHandover = (handoverId: string, data: AcknowledgeReq) =>
  api.post<HandoverResponse>(`/api/handover/${handoverId}/acknowledge`, data)

/** Reject a submitted handover back to draft. */
export const rejectHandover = (handoverId: string, data: RejectReq) =>
  api.post<HandoverResponse>(`/api/handover/${handoverId}/reject`, data)

/** Get deterministic handover brief (no LLM). */
export const getHandoverBrief = (
  handoverId: string,
  mode: 'full' | 'compact' | 'ward' = 'full'
) =>
  api.get<HandoverBriefResponse>(`/api/handover/${handoverId}/brief`, { params: { mode } })

/** Get forced alerts that must be confirmed during handover. */
export const getForcedAlerts = (
  patientId: string,
  params?: { since?: string; until?: string }
) =>
  api.get<ForcedAlertsResponse>(`/api/handover/patients/${patientId}/forced-alerts`, { params })
