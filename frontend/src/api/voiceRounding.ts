import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 120000, // ASR + LLM 可能较慢
})

/**
 * 结构化 suspect 条目。
 * 后端返回的是结构化对象，不是扁平字符串。
 */
export interface VoiceRoundingSuspect {
  term: string
  type:
    | 'drug_confusable'
    | 'number_override'
    | 'dialect_uncertain'
    | 'low_confidence'
    | 'unit_uncertain'
    | 'other'
  note: string
  start_ms?: number | null
  end_ms?: number | null
}

/**
 * 转写片段（为未来时间戳和说话人扩展预留）。
 */
export interface VoiceRoundingSegment {
  start_ms?: number | null
  end_ms?: number | null
  text?: string
  confidence?: number | null
  speaker_id?: string | null
}

/**
 * 音频处理信息。
 */
export interface VoiceRoundingProcessing {
  audio_normalized: boolean
  asr_mode: string
  llm_corrected: boolean
  source_format?: string
}

/**
 * 语音查房草稿（转写结果）。
 */
export interface VoiceRoundingDraft {
  _id: string
  patient_id: string
  status: 'draft' | 'confirmed'
  raw_text: string
  cleaned_text: string
  corrected_text: string
  needs_human_review: boolean
  suspect: VoiceRoundingSuspect[]
  /** 向后兼容：扁平 suspect 列表 */
  suspect_terms?: string[]
  degraded: boolean
  duration_seconds: number
  segments: VoiceRoundingSegment[]
  processing?: VoiceRoundingProcessing
  created_at: string
}

/**
 * 语音查房草稿（流式扩展字段）。
 */
export interface VoiceRoundingDraftStream extends VoiceRoundingDraft {
  summary_text?: string | null
  summary_sections?: Array<{ title: string; content: string }> | null
  summary_degraded?: boolean
  session_id?: string
  dropped_chunks?: number
}

/**
 * 语音查房确认记录。
 */
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
 * 音频格式：浏览器 MediaRecorder 产生的 WebM/Opus、OGG/Opus 等。
 * 服务端会自动转换为 16kHz 单声道 WAV/PCM。
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

/** Voice rounding capabilities returned by GET /capabilities */
export interface VoiceRoundingCapabilities {
  streaming_enabled: boolean
  offline_enabled: boolean
  max_session_seconds: number
  supported_sample_rates: number[]
}

/** Fetch streaming / offline capabilities before deciding UI mode. */
export const getVoiceRoundingCapabilities = () =>
  api.get<VoiceRoundingCapabilities>('/api/voice-rounding/capabilities')
