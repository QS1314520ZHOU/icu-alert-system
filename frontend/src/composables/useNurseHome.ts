import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getNurseHome, postNurseTaskExecute, postNurseReminderFeedback } from '../api'
import { useAuthStore } from '../stores/auth'
import { formatAlertTypeLabel } from '../utils/displayLabels'

const CACHE_TTL_MS = 2 * 60 * 1000
const cache = new Map<string, { ts: number; data: any }>()

export function useNurseHome() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()
  const loading = ref(false)
  const error = ref('')
  const home = ref<any>(null)

  // ── 身份解析 ──
  function firstIdentityQuery(...keys: string[]) {
    for (const key of keys) {
      const value = route.query[key]
      const text = String(Array.isArray(value) ? value[0] : value || '').trim()
      if (text) return text
    }
    return ''
  }

  const routeIdentity = computed(() => firstIdentityQuery('user_id', 'userId', 'userName', 'useName', 'username'))
  const userId = computed(() => String(routeIdentity.value || auth.effectiveUserId || '').trim())
  const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim())
  const routeDept = computed(() => String(route.query.dept || route.query.department || auth.dept || '').trim())
  const accountName = computed(() => home.value?.account?.display_name || home.value?.account?.userName || userId.value || '未识别护士')

  const cacheKey = computed(() => JSON.stringify({
    user_id: userId.value,
    shift_code: 'auto',
    dept: routeDept.value,
    dept_code: routeDeptCode.value,
  }))

  // ── 数据 ──
  const beds = computed(() => home.value?.beds || [])
  const workload = computed(() => home.value?.workload || {})
  const shift = computed(() => home.value?.shift || null)
  const timeline = computed(() => home.value?.timeline || [])
  const bundles = computed(() => home.value?.bundles || [])
  const activeAlerts = computed(() => home.value?.active_alerts || [])

  // 危急/高风险 (P0/P1 physiologic_alarm + clinical_risk P0/P1)
  const criticalAlerts = computed(() =>
    activeAlerts.value.filter((a: any) => {
      const domain = String(a?.alert_domain || '').toLowerCase()
      const priority = String(a?.priority || '').toLowerCase()
      return domain === 'physiologic_alarm' || (domain === 'clinical_risk' && (priority === 'p0' || priority === 'p1'))
    })
  )

  // 流程任务 (workflow_reminder + quality_gap)
  const workflowTasks = computed(() =>
    activeAlerts.value.filter((a: any) => {
      const domain = String(a?.alert_domain || '').toLowerCase()
      return domain === 'workflow_reminder' || domain === 'quality_gap'
    })
  )

  // ── 班次信息 ──
  const shiftText = computed(() => {
    const s = shift.value
    if (!s) return '班次待配置'
    return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
  })

  const shiftEndSoon = computed(() => {
    const end = new Date(shift.value?.end || 0).getTime()
    return end > 0 && end - Date.now() <= 60 * 60 * 1000
  })

  // ── 床位排序 ──
  function bedSortParts(value: any) {
    const raw = String(value || '').trim()
    const normalized = raw
      .replace(/[０-９]/g, (char: string) => String.fromCharCode(char.charCodeAt(0) - 0xfee0))
      .replace(/[\s_-]+/g, '')
    const numberHit = normalized.match(/\d+/)
    return {
      hasNumber: numberHit ? 0 : 1,
      number: numberHit ? Number(numberHit[0]) : Number.MAX_SAFE_INTEGER,
      suffix: numberHit ? normalized.slice((numberHit.index || 0) + numberHit[0].length) : normalized,
      raw: normalized,
    }
  }

  function sortBeds(rows: any[]) {
    return [...(rows || [])].sort((a: any, b: any) => {
      const left = bedSortParts(a?.bed)
      const right = bedSortParts(b?.bed)
      if (left.hasNumber !== right.hasNumber) return left.hasNumber - right.hasNumber
      if (left.number !== right.number) return left.number - right.number
      return left.suffix.localeCompare(right.suffix, 'zh-CN', { numeric: true, sensitivity: 'base' })
    })
  }

  const sortedBeds = computed(() => sortBeds(beds.value))

  // ── 工具函数 ──
  function displayBed(value: any) {
    const text = String(value || '').trim()
    if (!text || text === '--') return '--床'
    return text.includes('床') ? text : `${text}床`
  }

  function fmt(value: any) {
    return value ? new Date(value).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--'
  }

  function displayName(value: any) {
    return formatAlertTypeLabel(value).replace(/\bBundle\b/gi, '防控清单')
  }

  function bedDotClass(row: any) {
    const key = String(row?.risk_level || row?.severity || row?.status || '').toLowerCase()
    if (['critical', 'danger', 'red', '危急'].includes(key)) return 'is-critical'
    if (['high', 'warning', 'warn', 'yellow', '关注', '高危'].includes(key)) return 'is-warn'
    return 'is-muted'
  }

  function priorityDot(priority: string) {
    const p = String(priority || '').toLowerCase()
    if (p === 'p0') return 'dot-p0'
    if (p === 'p1') return 'dot-p1'
    return 'dot-p2'
  }

  // ── 数据加载 ──
  async function load() {
    if (!userId.value) {
      error.value = '未识别当前账号。'
      return
    }
    const cached = cache.get(cacheKey.value)
    const canUseCache = cached && Date.now() - cached.ts < CACHE_TTL_MS
    if (canUseCache) {
      home.value = cached.data
      loading.value = false
    } else {
      loading.value = true
    }
    error.value = ''
    try {
      const params: { user_id: string; shift_code: string; dept?: string; dept_code?: string } = {
        user_id: userId.value,
        shift_code: 'auto',
      }
      if (routeDeptCode.value) params.dept_code = routeDeptCode.value
      else if (routeDept.value) params.dept = routeDept.value
      const { data } = await getNurseHome(params)
      home.value = data?.data || {}
      cache.set(cacheKey.value, { ts: Date.now(), data: home.value })
      auth.updateAccount(home.value?.account)
    } catch (err: any) {
      if (!canUseCache) error.value = err?.message || '护士首页加载失败'
    } finally {
      loading.value = false
    }
  }

  // ── 任务操作 ──
  async function executeTask(task: any, action: string) {
    if (!task) return
    await postNurseTaskExecute(task.task_id, {
      action,
      patient_id: task.patient_id,
      actor: userId.value,
    })
    await load()
  }

  // ── AI 提醒反馈 ──
  async function feedbackReminder(item: any, disposition: string) {
    const alertId = String(item?._id || item?.alert_id || '').trim()
    if (!alertId) return
    await postNurseReminderFeedback(alertId, {
      actor: userId.value,
      disposition,
      note: disposition === 'escalate' ? '护士首页转给医生' : disposition === 'false_positive' ? '护士首页反馈不是问题' : '护士首页标记已处理',
      override_reason_code: disposition === 'false_positive' ? 'not_nursing_issue' : undefined,
    })
    await load()
  }

  // ── 路由 ──
  function goPatient(id: string) {
    if (id) router.push({ path: `/patient/${id}`, query: route.query })
  }

  function cleanDuplicateIdentityQuery() {
    const query = auth.cleanIdentityQuery(route.query)
    if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ path: route.path, query })
  }

  return {
    loading,
    error,
    home,
    userId,
    accountName,
    routeDeptCode,
    routeDept,
    beds,
    sortedBeds,
    workload,
    shift,
    shiftText,
    shiftEndSoon,
    timeline,
    bundles,
    activeAlerts,
    criticalAlerts,
    workflowTasks,
    load,
    executeTask,
    feedbackReminder,
    goPatient,
    cleanDuplicateIdentityQuery,
    displayBed,
    fmt,
    displayName,
    bedDotClass,
    priorityDot,
  }
}
