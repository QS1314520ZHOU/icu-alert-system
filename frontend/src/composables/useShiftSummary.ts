/**
 * 交接班：当前班次全病区总结（患者交班 / 待办与未闭环 页面共用）
 * 数据来自 GET /api/handover/shifts/current/summary
 */
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { useAuthStore } from '../stores/auth'

export interface ShiftPatientStat {
  patient_id: string
  bed: string
  name: string
  diagnosis: string
  isolation: string
  is_critical: boolean
  risk_level: 'critical' | 'high' | 'medium' | 'stable' | string
  risk_reasons?: string[]
  risk_rule?: string
  has_ventilator: boolean
  has_vasoactive: boolean
  has_crrt: boolean
  alert_count: number
  unclosed_alert_count: number
  critical_value_count: number
  high_risk_line_count: number
  handover_status?: string
  handover_id?: string
  handover_updated_at?: string
}

export const RISK_LABELS: Record<string, string> = {
  critical: '危急',
  high: '高危',
  medium: '中危',
  stable: '平稳',
}
export const RISK_COLORS: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  stable: 'green',
}
export const HANDOVER_STATUS_LABELS: Record<string, string> = {
  not_started: '未开始',
  draft: '草稿',
  submitted: '待签收',
  acknowledged: '已签收',
  returned: '已退回',
}
export const HANDOVER_STATUS_COLORS: Record<string, string> = {
  not_started: 'default',
  draft: 'orange',
  submitted: 'blue',
  acknowledged: 'green',
  returned: 'red',
}
export const RISK_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, stable: 3 }

/** 后端未返回 risk_reasons 时（旧版本），按同一规则在前端推导依据 */
export function deriveRiskReasons(p: ShiftPatientStat): string[] {
  if (Array.isArray(p.risk_reasons) && p.risk_reasons.length) return p.risk_reasons
  const r: string[] = []
  if (p.critical_value_count > 0) r.push(`本班危急值${p.critical_value_count}条`)
  if (p.has_vasoactive) r.push('使用血管活性药')
  if (p.has_crrt) r.push('CRRT治疗中')
  if (p.unclosed_alert_count > 0) r.push(`未闭环告警${p.unclosed_alert_count}条`)
  if (p.has_ventilator) r.push('机械通气中')
  if (p.high_risk_line_count > 0) r.push(`高危管路${p.high_risk_line_count}条`)
  return r
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function useShiftSummary() {
  const route = useRoute()
  const authStore = useAuthStore()
  const loading = ref(false)
  const error = ref('')
  const summary = ref<any>(null)

  const deptCode = computed(() => authStore.deptCode || (route.query.dept_code as string) || '')
  const patients = computed<ShiftPatientStat[]>(() =>
    Array.isArray(summary.value?.patients) ? summary.value.patients : [],
  )

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const res = await api.get('/api/handover/shifts/current/summary', {
        params: { dept_code: deptCode.value },
      })
      summary.value = res.data?.summary || null
    } catch (e: any) {
      error.value = e?.response?.data?.detail || e?.message || '加载班次总结失败'
      summary.value = null
    } finally {
      loading.value = false
    }
  }

  return { loading, error, summary, patients, deptCode, load }
}
