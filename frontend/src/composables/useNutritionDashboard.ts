/**
 * useNutritionDashboard — 营养支持工作台共享状态与逻辑
 */
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { getClinicalAccount, getDepartments } from '../api'
import {
  closeNutritionTask,
  getNutritionDashboard,
  getNutritionPatient,
  postNutritionAiAdvice,
  postNutritionTask,
  type NutritionScopeParams,
} from '../api/nutrition'
import { formatBeijingTime } from '../utils/time'
import { useAuthStore } from '../stores/auth'

export function useNutritionDashboard() {
  const route = useRoute()
  const auth = useAuthStore()

  /* ── 基础状态 ── */
  const loading = ref(false)
  const detailLoading = ref(false)
  const keyword = ref('')
  const riskFilter = ref('all')
  const patients = ref<any[]>([])
  const stats = ref<any>({})
  const priorities = ref<any[]>([])
  const roleActions = ref<any>({})
  const scopeName = ref('')

  /* ── 抽屉状态 ── */
  const drawerOpen = ref(false)
  const drawerPatient = ref<any>(null)
  const aiAdvice = ref<any>(null)
  const aiLoading = ref(false)

  /* ── 路由参数 ── */
  const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim())
  const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
  const routeUserName = computed(() => String(route.query.userName || '').trim())
  const scopeLabel = computed(() => scopeName.value || routeDeptName.value || '全部 ICU 在科患者')

  /* ── 筛选选项 ── */
  const riskOptions = [
    { value: 'all', label: '全部床位' },
    { value: 'high', label: '高风险' },
    { value: '未启动', label: '未启动' },
    { value: '热量未达标', label: '热量未达标' },
    { value: '再喂养风险', label: '再喂养风险' },
    { value: 'EN不耐受', label: 'EN不耐受' },
    { value: '血糖风险', label: '血糖风险' },
    { value: 'NRS待评', label: '评分待补' },
    { value: 'EN', label: 'EN' },
    { value: 'PN', label: 'PN' },
    { value: '混合', label: '混合' },
    { value: '未开始', label: '未开始' },
  ]

  /* ── 患者筛选 ── */
  const filteredPatients = computed(() => {
    const q = keyword.value.trim().toLowerCase()
    return patients.value.filter((row) => {
      if (riskFilter.value === 'high' && row.risk_level !== 'high') return false
      if (['EN', 'PN', '混合', '未开始'].includes(riskFilter.value) && row.route !== riskFilter.value) return false
      if (!['all', 'high', 'EN', 'PN', '混合', '未开始'].includes(riskFilter.value) && !(row.risk_tags || []).includes(riskFilter.value)) return false
      if (!q) return true
      return [row.bed_no, row.name, row.diagnosis, row.route].some((item) => String(item || '').toLowerCase().includes(q))
    })
  })

  /* ── 紧急患者排序 ── */
  const urgentPatients = computed(() => {
    return [...filteredPatients.value].sort((a, b) => computeNutritionPriority(b) - computeNutritionPriority(a))
  })

  function computeNutritionPriority(patient: any): number {
    let p = 0
    if (patient?.risk_level === 'high') p += 10
    if (patient?.risk_level === 'medium') p += 5
    const tags = patient?.risk_tags || []
    if (tags.includes('再喂养风险')) p += 8
    if (tags.includes('热量未达标')) p += 6
    if (tags.includes('蛋白未达标')) p += 4
    if (tags.includes('EN不耐受')) p += 6
    if (tags.includes('血糖风险')) p += 4
    if (tags.includes('未启动')) p += 7
    if (tags.includes('脂肪乳风险')) p += 5
    return p
  }

  /* ── 侧边栏数据 ── */

  /** 今日待办（优先事项） */
  const todayTasks = computed(() => {
    if (priorities.value.length) {
      return priorities.value.slice(0, 6).map((item: any) => ({
        ...item,
        tone: item.tone || (isHotTag(item.action) ? 'danger' : 'info'),
      }))
    }
    // 回退：从 roleActions 生成
    const rows: any[] = []
    for (const item of (roleActions.value?.nurse || []).slice(0, 3)) {
      rows.push({ ...item, tone: 'warning' })
    }
    for (const item of (roleActions.value?.doctor || []).slice(0, 3)) {
      rows.push({ ...item, tone: 'info' })
    }
    return rows.slice(0, 6)
  })

  /** 即将超时（高风险 + 未启动） */
  const timeoutItems = computed(() => {
    return patients.value
      .filter((r: any) => {
        const tags = r.risk_tags || []
        return r.risk_level === 'high' || tags.includes('未启动') || tags.includes('再喂养风险')
      })
      .slice(0, 4)
      .map((r: any) => ({
        ...r,
        reason: getTimeoutReason(r),
        tone: 'danger',
      }))
  })

  function getTimeoutReason(patient: any): string {
    const tags = patient?.risk_tags || []
    if (tags.includes('再喂养风险')) return '再喂养风险'
    if (tags.includes('未启动')) return '营养未启动'
    if (tags.includes('热量未达标')) return '热量未达标'
    return '高风险'
  }

  /** 需要医生确认（PN 复核 + 主任关注） */
  const doctorConfirmItems = computed(() => {
    const rows: any[] = []
    for (const item of (roleActions.value?.doctor || []).slice(0, 3)) {
      rows.push({ ...item, tone: 'warning' })
    }
    for (const item of (roleActions.value?.director || []).slice(0, 2)) {
      rows.push({ ...item, tone: 'danger' })
    }
    return rows.slice(0, 4)
  })

  /* ── KPI（保留给侧边栏摘要用） ── */
  const kpis = computed(() => [
    { key: 'not-reached', label: '未达标', value: stats.value.not_reached_count || 0, tone: 'warn', filter: '热量未达标' },
    { key: 'refeeding', label: '再喂养', value: stats.value.refeeding_count || 0, tone: 'danger', filter: '再喂养风险' },
    { key: 'not-started', label: '未启动', value: stats.value.not_started_count || 0, tone: 'danger', filter: '未开始' },
    { key: 'pn', label: 'PN复核', value: stats.value.pn_review_count || 0, tone: 'info', filter: 'PN' },
    { key: 'avg', label: '平均达标', value: `${stats.value.avg_kcal_pct || 0}%`, tone: 'stable', filter: 'all' },
  ])

  /* ── 趋势数据 ── */
  const wardTrend = computed(() => {
    const rows = patients.value.filter((row) => Array.isArray(row.trend_7d))
    if (!rows.length) return [0, 0, 0, 0, 0, 0, 0]
    return Array.from({ length: 7 }, (_, idx) => {
      const values = rows.map((row) => Number(row.trend_7d?.[idx]?.pct || 0))
      return Math.round(values.reduce((sum, item) => sum + item, 0) / Math.max(1, values.length))
    })
  })
  const avgTrend = computed(() => Math.round(wardTrend.value.reduce((sum, item) => sum + item, 0) / Math.max(1, wardTrend.value.length)))

  /* ── 抽屉相关计算 ── */
  const toleranceText = computed(() => {
    const level = drawerPatient.value?.tolerance?.level
    if (level === 'danger') return '中断'
    if (level === 'warn') return '观察'
    if (level === 'stable') return '平稳'
    return '待评'
  })
  const glucoseRange = computed(() => {
    const trend = drawerPatient.value?.glucose_trend || {}
    if (trend.min == null || trend.max == null) return '待评'
    return `${trend.min}-${trend.max}`
  })
  const glucosePoints = computed(() => drawerPatient.value?.glucose_trend?.points || [])
  const qualityMissing = computed(() => {
    const missing = drawerPatient.value?.data_quality?.missing || []
    return missing.length ? missing.slice(0, 2).join(' / ') : '完整'
  })
  const deliverySourceLabel = computed(() => {
    const source = String(drawerPatient.value?.delivery_source || '')
    if (/drugExe/i.test(source)) return '实际执行'
    if (source.includes('医嘱')) return '医嘱估算'
    return source || '执行估算'
  })

  const labRows = computed(() => {
    const labs = drawerPatient.value?.labs || {}
    const map: Array<[string, string]> = [
      ['p', 'P'], ['k', 'K'], ['mg', 'Mg'], ['glucose', '血糖'],
      ['tg', 'TG'], ['albumin', '白蛋白'], ['prealbumin', '前白蛋白'], ['crp', 'CRP'],
    ]
    return map.map(([key, label]) => {
      const lab = labs[key] || {}
      return {
        key,
        label,
        value: lab.value != null ? `${lab.value}${lab.unit ? ` ${lab.unit}` : ''}` : '—',
        time: fmt(lab.time),
      }
    })
  })

  /* ── 辅助函数 ── */
  function fmt(v: any) { return formatBeijingTime(v, '—') }
  function routeCount(name: string) { return stats.value.route_counts?.[name] || 0 }
  function routePct(name: string) {
    const total = Number(stats.value.patient_count || 0)
    return total ? `${Math.round((routeCount(name) / total) * 100)}%` : '0%'
  }
  function compactTags(patient: any) {
    const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags.filter(Boolean) : []
    return tags.length ? tags.slice(0, 3) : ['稳定']
  }
  function patientTone(patient: any) {
    if (patient?.risk_level === 'high') return 'danger'
    if (patient?.risk_level === 'medium') return 'warn'
    return 'stable'
  }
  function isHotTag(tag: string) {
    return ['未启动', '再喂养风险', '热量未达标', '蛋白未达标', '血糖风险', '脂肪乳风险', 'EN不耐受'].includes(tag)
  }
  function levelText(level: string) {
    return ({ danger: '高危', warn: '关注', stable: '平稳', unknown: '待评' } as Record<string, string>)[level || 'unknown'] || '待评'
  }
  function glucoseX(idx: any) {
    const len = Math.max(1, glucosePoints.value.length - 1)
    return Math.round((Number(idx || 0) / len) * 100)
  }
  function glucoseY(value: any) {
    const num = Number(value || 0)
    return Math.max(6, Math.min(92, Math.round(((num - 3) / 12) * 100)))
  }

  function shortNutritionIssue(patient: any): string {
    const tags = patient?.risk_tags || []
    if (tags.includes('再喂养风险')) return '再喂养风险'
    if (tags.includes('EN不耐受')) return 'EN不耐受'
    if (tags.includes('热量未达标')) return '热量未达标'
    if (tags.includes('蛋白未达标')) return '蛋白未达标'
    if (tags.includes('血糖风险')) return '血糖风险'
    if (tags.includes('未启动')) return '营养未启动'
    if (tags.includes('脂肪乳风险')) return '脂肪乳风险'
    if (patient?.risk_level === 'high') return '高风险'
    return '稳定'
  }

  function nextNutritionAction(patient: any): string {
    const tags = patient?.risk_tags || []
    if (tags.includes('再喂养风险')) return '监测电解质'
    if (tags.includes('EN不耐受')) return '调整EN方案'
    if (tags.includes('热量未达标')) return '补充热量'
    if (tags.includes('未启动')) return '启动营养'
    if (tags.includes('血糖风险')) return '调整血糖'
    if (patient?.route === 'PN') return 'PN复核'
    return '查看'
  }

  /* ── 请求参数 ── */
  function requestParams(): NutritionScopeParams {
    const params: NutritionScopeParams = { patient_scope: 'in_dept' }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDeptName.value) params.dept = routeDeptName.value
    return params
  }

  async function resolveScopeName() {
    if (routeDeptName.value && !/^\d+$/.test(routeDeptName.value)) {
      scopeName.value = routeDeptName.value
      return
    }
    try {
      if (routeUserName.value) {
        const { data } = await getClinicalAccount({
          userName: routeUserName.value,
          dept_code: routeDeptCode.value || undefined,
          dept: routeDeptName.value || undefined,
        })
        const dept = String(data?.account?.dept || '').trim()
        if (dept && dept !== routeDeptCode.value) {
          scopeName.value = dept
          return
        }
      }
      if (routeDeptCode.value) {
        const { data } = await getDepartments()
        const hit = (data?.departments || []).find((item: any) => String(item.deptCode || '').trim() === routeDeptCode.value)
        scopeName.value = String(hit?.dept || '').trim()
        return
      }
    } catch {
      scopeName.value = ''
    }
  }

  /* ── API 调用 ── */
  async function loadAll() {
    loading.value = true
    try {
      await resolveScopeName()
      const { data } = await getNutritionDashboard(requestParams())
      patients.value = data?.patients || []
      stats.value = data?.stats || {}
      priorities.value = data?.priorities || []
      roleActions.value = data?.role_actions || {}
    } finally {
      loading.value = false
    }
    detailLoading.value = true
    try {
      const { data } = await getNutritionDashboard({ ...requestParams(), detail: true })
      patients.value = data?.patients || patients.value
      stats.value = data?.stats || stats.value
      priorities.value = data?.priorities || priorities.value
      roleActions.value = data?.role_actions || roleActions.value
    } finally {
      detailLoading.value = false
    }
  }

  async function openPatient(row: any) {
    drawerPatient.value = row
    drawerOpen.value = true
    aiAdvice.value = null
    const { data } = await getNutritionPatient(row.patient_id)
    drawerPatient.value = data?.patient || row
    if (data?.meta?.refreshing) {
      window.setTimeout(async () => {
        if (!drawerOpen.value || drawerPatient.value?.patient_id !== row.patient_id) return
        const refreshed = await getNutritionPatient(row.patient_id)
        if (!refreshed.data?.meta?.refreshing) {
          drawerPatient.value = refreshed.data?.patient || drawerPatient.value
        }
      }, 1200)
    }
  }

  async function openById(patientId: string) {
    const hit = patients.value.find((item) => item.patient_id === patientId)
    if (hit) await openPatient(hit)
  }

  async function loadAiAdvice(refresh = false) {
    if (!drawerPatient.value) return
    aiLoading.value = true
    try {
      const { data } = await postNutritionAiAdvice(drawerPatient.value.patient_id, { refresh })
      aiAdvice.value = data?.advice || null
    } finally {
      aiLoading.value = false
    }
  }

  async function createTask(action: any) {
    if (!drawerPatient.value) return
    const { data } = await postNutritionTask(drawerPatient.value.patient_id, {
      title: action.title,
      target: action.target,
      task_type: action.task_type,
      priority: action.priority || (isHotTag(action.title) ? 'high' : 'medium'),
      payload: action.payload,
      source: '营养支持工作台',
    })
    drawerPatient.value.tasks = [data?.task, ...(drawerPatient.value.tasks || [])].filter(Boolean)
    message.success('已生成营养任务')
  }

  async function closeTask(task: any) {
    if (!task?.task_id || !drawerPatient.value) return
    const { data } = await closeNutritionTask(task.task_id, { outcome: '已完成' })
    drawerPatient.value.tasks = (drawerPatient.value.tasks || []).map((item: any) =>
      item.task_id === task.task_id ? data?.task || { ...item, status: 'closed' } : item,
    )
    message.success('任务已闭环')
  }

  /* ── 路由监听 ── */
  watch(() => [route.query.userName, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
    void loadAll()
  })

  return {
    /* 状态 */
    loading,
    detailLoading,
    keyword,
    riskFilter,
    riskOptions,
    patients,
    stats,
    priorities,
    roleActions,
    scopeLabel,
    kpis,

    /* 筛选后数据 */
    filteredPatients,
    urgentPatients,

    /* 侧边栏数据 */
    todayTasks,
    timeoutItems,
    doctorConfirmItems,
    wardTrend,
    avgTrend,

    /* 抽屉 */
    drawerOpen,
    drawerPatient,
    aiAdvice,
    aiLoading,
    toleranceText,
    glucoseRange,
    glucosePoints,
    qualityMissing,
    deliverySourceLabel,
    labRows,

    /* 函数 */
    loadAll,
    openPatient,
    openById,
    loadAiAdvice,
    createTask,
    closeTask,
    fmt,
    routeCount,
    routePct,
    compactTags,
    patientTone,
    isHotTag,
    levelText,
    glucoseX,
    glucoseY,
    shortNutritionIssue,
    nextNutritionAction,
  }
}
