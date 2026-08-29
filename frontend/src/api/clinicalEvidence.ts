/**
 * 临床证据链 API 客户端
 */
import api from './index'

// ── 类型定义 ──────────────────────────────────────────

export type ContextType =
  | 'organ_system' | 'risk' | 'order' | 'nursing'
  | 'weaning' | 'discharge' | 'rule_noise' | 'vitals' | 'unclosed'

export type OrganSystem =
  | 'respiratory' | 'circulatory' | 'renal' | 'hepatic'
  | 'neurologic' | 'coagulation' | 'infection' | 'nutrition'

export type TimeRange = '1h' | '6h' | '12h' | '24h' | '48h' | '72h' | '7d'

export interface EvidenceParams {
  context_type: ContextType
  context_id?: string
  organ_system?: OrganSystem
  time_range?: TimeRange
  include_raw?: boolean
  include_ai?: boolean
}

export interface EvidenceMetric {
  code: string
  name: string
  value: number | string | null
  unit: string
  observed_at: string | null
  min?: number
  max?: number
  count?: number
  reference_range: string
  abnormal_flag: 'normal' | 'high' | 'low' | 'critical' | 'missing'
}

export interface TrendPoint {
  time: string
  value: number | null
}

export interface EvidenceTrend {
  code: string
  name: string
  points: TrendPoint[]
  reference_range: string
}

export interface EvidenceRow {
  record_id: string
  patient_id: string
  observed_at: string | null
  category: string
  code: string
  name: string
  value: number | string | null
  unit: string
  reference_range: string
  abnormal_flag: string
  source_system?: string
  collection_name?: string
  data_quality: string
}

export interface RuleCalculationItem {
  label?: string
  name?: string
  score?: number
  value?: number | string
  ok?: boolean
  description?: string
}

export interface RuleCalculation {
  score_type: string
  total_score?: number
  items: RuleCalculationItem[]
  calc_time?: string
  description?: string
  lights?: { label: string; ok: boolean }[]
  statistical_scope?: string
}

export interface AiAnalysis {
  supporting_evidence: string[]
  opposing_evidence: string[]
  uncertainties: string[]
  disclaimer: string
  model: string
  generated_at: string | null
}

export interface TimelineEvent {
  time: string | null
  event_type: string
  title: string
  severity: string
  detail: string
}

export interface MissingDataItem {
  code: string
  name: string
  reason: string
  impact: string
}

export interface Provenance {
  patient_id: string
  context_type: string
  context_id?: string
  time_range: string
  query_since: string
  data_sources: string[]
}

export interface EvidenceResponse {
  conclusion: string
  severity: 'critical' | 'high' | 'warning' | 'info' | 'stable'
  confidence: number
  generated_at: string
  data_cutoff_at: string
  metrics: EvidenceMetric[]
  trends: EvidenceTrend[]
  evidence_rows: EvidenceRow[]
  rule_calculation: RuleCalculation | null
  ai_analysis: AiAnalysis | null
  timeline: TimelineEvent[]
  missing_data: MissingDataItem[]
  provenance: Provenance
  model_version: string
  rule_version: string
}

// ── API 调用 ──────────────────────────────────────────

export const getPatientEvidence = (patientId: string, params: EvidenceParams) =>
  api.get<{ code: number; data: EvidenceResponse }>(
    `/api/patients/${patientId}/evidence`,
    { params, timeout: 30000 },
  )
