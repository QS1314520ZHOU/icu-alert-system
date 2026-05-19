import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { getPatientVitalsForecast } from '../api'

export type ForecastStatus = 'idle' | 'loading' | 'ready' | 'refreshing' | 'error'

export type ForecastMeta = {
  status: ForecastStatus
  source: 'chronos' | 'heuristic' | ''
  horizon: number
  generatedAt: string
  qualityLevel: 'normal' | 'low' | ''
  fallbackReason: string
  error: string
  dataPoints: number
  modelVersion: string
  latencyMs: number
}

type LoadArgs = {
  patientId: string
  trendWindow: string
  horizon: number
  codes: string[]
  historyLastTs: string
}

const CACHE_TTL_MS = 30 * 1000
const MAX_CACHE_SIZE = 20
const cache = new Map<string, { ts: number; data: any }>()

function trackForecast(event: string, payload: Record<string, any> = {}) {
  try {
    const detail = { event: `forecast.${event}`, ...payload, at: Date.now() }
    window.dispatchEvent(new CustomEvent('icu-forecast-event', { detail }))
    if (import.meta.env.DEV) console.debug('[forecast]', detail)
  } catch {
    // no-op
  }
}

function parseTrendWindowHours(tw: string | undefined | null): number | null {
  if (!tw) return null
  const match = tw.match(/^(\d+)(h|d)$/i)
  if (!match) return null
  const value = parseInt(match[1], 10)
  if (isNaN(value) || value <= 0) return null
  return match[2].toLowerCase() === 'd' ? value * 24 : value
}

function cacheKey(args: LoadArgs) {
  return JSON.stringify({
    patientId: args.patientId,
    trendWindow: args.trendWindow,
    horizon: args.horizon,
    codes: [...args.codes].sort().join(','),
    historyLastTs: args.historyLastTs || '',
  })
}

function setCache(key: string, data: any) {
  cache.set(key, { ts: Date.now(), data })
  while (cache.size > MAX_CACHE_SIZE) {
    const first = cache.keys().next().value
    if (!first) break
    cache.delete(first)
  }
}

function qualityLevel(data: any): 'normal' | 'low' | '' {
  const series = data?.series || {}
  const rows = Object.values(series) as any[]
  if (!rows.length) return ''
  // Strong signal: any single indicator explicitly marked level='low' → overall low
  const strongLow = rows.some((row: any) => row?.data_quality?.level === 'low')
  if (strongLow) return 'low'
  // Majority voting: >=50% of indicators insufficient → overall low
  const insufficient = rows.filter((row: any) => {
    const history = Array.isArray(row?.history) ? row.history : []
    return row?.data_quality?.ok === false || history.length < 3
  }).length
  return insufficient / rows.length >= 0.5 ? 'low' : 'normal'
}

function dataPointCount(data: any) {
  return Object.values(data?.series || {}).reduce((sum: number, row: any) => {
    return sum + (Array.isArray(row?.history) ? row.history.length : 0)
  }, 0)
}

function metaFromData(data: any, status: ForecastStatus, latencyMs = 0, error = ''): ForecastMeta {
  const model = data?.model_meta || {}
  const disabledOrError = data?.available === false && !data?.source
  return {
    status,
    source: disabledOrError ? '' : data?.source === 'chronos' ? 'chronos' : data?.source === 'heuristic' ? 'heuristic' : '',
    horizon: Number(data?.horizon_hours || 0),
    generatedAt: String(data?.generated_at || ''),
    qualityLevel: qualityLevel(data),
    fallbackReason: String(data?.fallback_reason || data?.reason || ''),
    error,
    dataPoints: dataPointCount(data),
    modelVersion: String(model?.calibration_version || model?.config_version || ''),
    latencyMs,
  }
}

export function useVitalForecast() {
  const state = reactive({
    status: 'idle' as ForecastStatus,
    data: null as any,
    error: '',
    source: '' as 'chronos' | 'heuristic' | '',
    latencyMs: 0,
  })
  const seq = ref(0)
  let controller: AbortController | null = null
  let retryTimer: number | null = null

  function abort(reason = 'patient_switch') {
    seq.value += 1
    if (controller) {
      controller.abort()
      controller = null
      trackForecast(reason === 'patient_switch' ? 'aborted_by_patient_switch' : 'aborted', {})
    }
    if (retryTimer != null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  async function load(args: LoadArgs, options: { retry?: boolean } = {}) {
    if (!args.patientId || !args.codes.length) return
    if (args.horizon < 1 || args.horizon > 12) {
      state.status = 'error'
      state.error = 'invalid_horizon'
      trackForecast('invalid_horizon', { patientId: args.patientId, horizon: args.horizon })
      return
    }

    const key = cacheKey(args)
    const cached = cache.get(key)
    if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
      state.data = cached.data
      state.status = 'ready'
      state.error = ''
      state.source = cached.data?.source || ''
      trackForecast('cache_hit', { patientId: args.patientId, horizon: args.horizon, source: state.source })
      return
    }

    abort('refresh')
    const currentSeq = ++seq.value
    controller = new AbortController()
    const started = performance.now()
    state.status = state.data ? 'refreshing' : 'loading'
    state.error = ''
    trackForecast('request', { patientId: args.patientId, horizon: args.horizon })
    try {
      const hours = parseTrendWindowHours(args.trendWindow)
      const res = await getPatientVitalsForecast(args.patientId, { codes: args.codes.join(','), horizon_hours: args.horizon, ...(hours != null ? { hours } : {}) }, controller.signal)
      if (controller.signal.aborted || currentSeq !== seq.value) return
      const latencyMs = Math.round(performance.now() - started)
      state.data = res.data || {}
      state.status = state.data?.available === false && !state.data?.source ? 'error' : 'ready'
      state.source = state.data?.source === 'chronos' ? 'chronos' : state.data?.source === 'heuristic' ? 'heuristic' : ''
      state.latencyMs = latencyMs
      state.error = state.status === 'error' ? String(state.data?.fallback_reason || state.data?.reason || 'forecast_unavailable') : ''
      setCache(key, state.data)
      if (state.status === 'error') {
        trackForecast('error', { patientId: args.patientId, horizon: args.horizon, latency_ms: latencyMs, error: state.error })
        return
      }
      trackForecast('success', { patientId: args.patientId, horizon: args.horizon, latency_ms: latencyMs, source: state.source, quality_level: qualityLevel(state.data) })
      if (state.source === 'heuristic') {
        trackForecast('fallback_used', { patientId: args.patientId, horizon: args.horizon, latency_ms: latencyMs, source: state.source, quality_level: qualityLevel(state.data) })
      }
    } catch (error: any) {
      if (controller?.signal.aborted || currentSeq !== seq.value) return
      const latencyMs = Math.round(performance.now() - started)
      if (!options.retry) {
        retryTimer = window.setTimeout(() => void load(args, { retry: true }), 2000)
        return
      }
      state.status = 'error'
      state.error = error?.message || 'forecast_unavailable'
      state.data = null
      state.source = ''
      state.latencyMs = latencyMs
      trackForecast('error', { patientId: args.patientId, horizon: args.horizon, latency_ms: latencyMs, error: state.error })
    }
  }

  const meta = computed<ForecastMeta>(() => metaFromData(state.data, state.status, state.latencyMs, state.error))

  onBeforeUnmount(() => abort('unmount'))

  return { state, meta, load, abort }
}
