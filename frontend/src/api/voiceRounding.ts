import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 120000, // ASR + LLM 可能较慢
})

export interface VoiceRoundingDraft {
  _id: string
  patient_id: string
  status: 'draft' | 'confirmed'
  raw_text: string
  cleaned_text: string
  corrected_text: string
  needs_human_review: boolean
  suspect: string[]
  degraded: boolean
  created_at: string
}

export interface VoiceRoundingRecord {
  _id: string
  patient_id: string
  source: 'voice_rounding'
  status: 'confirmed'
  text: string
  draft_id: string
  confirmed_by: string
  confirmed_at: string
}

/**
 * 上传音频，返回 draft 转写结果。
 * 音频格式：浏览器 MediaRecorder 默认 webm/opus。
 */
export const transcribeAudio = (patientId: string, formData: FormData) =>
  api.post<VoiceRoundingDraft>(`/api/voice-rounding/${patientId}/transcribe`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

/**
 * 医生确认后入库为正式查房记录。
 */
export const confirmVoiceRounding = (
  patientId: string,
  payload: { final_text: string; draft_id?: string; actor?: string }
) => {
  const fd = new FormData()
  fd.append('final_text', payload.final_text)
  if (payload.draft_id) fd.append('draft_id', payload.draft_id)
  if (payload.actor) fd.append('actor', payload.actor)
  return api.post<VoiceRoundingRecord>(`/api/voice-rounding/${patientId}/confirm`, fd)
}
