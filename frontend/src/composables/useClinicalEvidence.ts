/**
 * useClinicalEvidence — 临床证据链状态管理
 *
 * 封装证据加载、缓存、错误处理，供证据抽屉组件使用。
 */
import { ref, computed, shallowRef } from 'vue'
import { getPatientEvidence } from '../api/clinicalEvidence'
import type {
  EvidenceParams, EvidenceResponse,
  OrganSystem, TimeRange,
} from '../api/clinicalEvidence'

// 模块级缓存：key = `${patientId}|${contextType}|${contextId}|${organSystem}`
const _cache = new Map<string, { data: EvidenceResponse; ts: number }>()
const CACHE_TTL = 60_000 // 60秒缓存

export function useClinicalEvidence() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const evidence = shallowRef<EvidenceResponse | null>(null)
  const currentKey = ref('')

  // ── 计算属性 ──────────────────────────────────────

  const hasMissingData = computed(() =>
    (evidence.value?.missing_data?.length ?? 0) > 0,
  )

  /** 证据完整率（0~1），来源于 confidence.evidence_completeness */
  const confidenceLevel = computed(() => {
    const c = evidence.value?.confidence?.evidence_completeness
    if (c == null) return 'unknown'
    if (c >= 0.9) return 'high'
    if (c >= 0.7) return 'medium'
    if (c >= 0.4) return 'low'
    return 'very-low'
  })

  const confidencePercent = computed(() => {
    const c = evidence.value?.confidence?.evidence_completeness
    return c != null ? Math.round(c * 100) : undefined
  })

  const severityColor = computed(() => {
    const map: Record<string, string> = {
      critical: '#DC2626',
      high: '#EA580C',
      warning: '#D97706',
      info: '#2563EB',
      stable: '#16A34A',
    }
    return map[evidence.value?.severity ?? 'info'] || '#6B7280'
  })

  const severityLabel = computed(() => {
    const map: Record<string, string> = {
      critical: '危急',
      high: '高风险',
      warning: '预警',
      info: '一般',
      stable: '稳定',
    }
    return map[evidence.value?.severity ?? 'info'] || '未知'
  })

  const abnormalMetrics = computed(() =>
    (evidence.value?.metrics ?? []).filter(
      m => m.abnormal_flag === 'critical' || m.abnormal_flag === 'high' || m.abnormal_flag === 'low',
    ),
  )

  const normalMetrics = computed(() =>
    (evidence.value?.metrics ?? []).filter(m => m.abnormal_flag === 'normal'),
  )

  const hasAiAnalysis = computed(() =>
    evidence.value?.ai_analysis !== null && evidence.value?.ai_analysis !== undefined,
  )

  // ── 加载方法 ──────────────────────────────────────

  function _cacheKey(patientId: string, params: EvidenceParams): string {
    return [patientId, params.context_type, params.context_id || '', params.organ_system || '', params.time_range || '24h'].join('|')
  }

  async function loadEvidence(patientId: string, params: EvidenceParams): Promise<EvidenceResponse | null> {
    if (!patientId) {
      error.value = '缺少患者ID'
      return null
    }

    const key = _cacheKey(patientId, params)
    currentKey.value = key

    // 检查缓存
    const cached = _cache.get(key)
    if (cached && Date.now() - cached.ts < CACHE_TTL) {
      evidence.value = cached.data
      error.value = null
      return cached.data
    }

    loading.value = true
    error.value = null

    try {
      const { data: res } = await getPatientEvidence(patientId, params)

      // 检查是否已被新的请求取代
      if (currentKey.value !== key) return null

      const result = res.data
      evidence.value = result
      _cache.set(key, { data: result, ts: Date.now() })
      return result
    } catch (err: any) {
      if (currentKey.value !== key) return null
      error.value = err?.response?.data?.detail || err?.message || '证据加载失败'
      evidence.value = null
      return null
    } finally {
      if (currentKey.value === key) {
        loading.value = false
      }
    }
  }

  function clearCache() {
    _cache.clear()
  }

  function clearPatientCache(patientId: string) {
    for (const key of _cache.keys()) {
      if (key.startsWith(`${patientId}|`)) {
        _cache.delete(key)
      }
    }
  }

  // ── 便捷方法 ──────────────────────────────────────

  async function loadOrganEvidence(patientId: string, organSystem: OrganSystem, timeRange?: TimeRange) {
    return loadEvidence(patientId, {
      context_type: 'organ_system',
      organ_system: organSystem,
      time_range: timeRange || '24h',
    })
  }

  async function loadRiskEvidence(patientId: string, alertId?: string, timeRange?: TimeRange) {
    return loadEvidence(patientId, {
      context_type: 'risk',
      context_id: alertId,
      time_range: timeRange || '24h',
    })
  }

  async function loadOrderEvidence(patientId: string, orderId?: string, timeRange?: TimeRange) {
    return loadEvidence(patientId, {
      context_type: 'order',
      context_id: orderId,
      time_range: timeRange || '24h',
    })
  }

  async function loadNursingEvidence(patientId: string, nursingKey?: string, timeRange?: TimeRange) {
    return loadEvidence(patientId, {
      context_type: 'nursing',
      context_id: nursingKey,
      time_range: timeRange || '24h',
    })
  }

  async function loadWeaningEvidence(patientId: string, timeRange?: TimeRange) {
    return loadEvidence(patientId, {
      context_type: 'weaning',
      time_range: timeRange || '24h',
    })
  }

  async function loadDischargeEvidence(patientId: string, timeRange?: TimeRange) {
    return loadEvidence(patientId, {
      context_type: 'discharge',
      time_range: timeRange || '24h',
    })
  }

  async function loadRuleNoiseEvidence(patientId: string, ruleId?: string, timeRange?: TimeRange) {
    return loadEvidence(patientId, {
      context_type: 'rule_noise',
      context_id: ruleId,
      time_range: timeRange || '24h',
    })
  }

  return {
    // 状态
    loading,
    error,
    evidence,
    // 计算属性
    hasMissingData,
    confidenceLevel,
    confidencePercent,
    severityColor,
    severityLabel,
    abnormalMetrics,
    normalMetrics,
    hasAiAnalysis,
    // 核心方法
    loadEvidence,
    clearCache,
    clearPatientCache,
    // 便捷方法
    loadOrganEvidence,
    loadRiskEvidence,
    loadOrderEvidence,
    loadNursingEvidence,
    loadWeaningEvidence,
    loadDischargeEvidence,
    loadRuleNoiseEvidence,
  }
}
