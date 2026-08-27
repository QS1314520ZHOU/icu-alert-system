/**
 * useRespiratoryDashboard — 呼吸治疗工作台共享状态与逻辑
 */
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  closeRespiratoryWorklistTask,
  getAirwayPlan,
  getRespiratoryDashboard,
  getRespiratoryDeteriorationForecast,
  getVentilatorTimeline,
  postAirwayPlan,
  postAirwayRecord,
  postRespiratoryTaskDone,
  postSbtStatus,
  type RespiratoryScopeParams,
} from '../api/respiratory'
import { formatBeijingTime } from '../utils/time'
import { useAuthStore } from '../stores/auth'
import { getDepartments } from '../api'

export function useRespiratoryDashboard() {
  const route = useRoute()
  const auth = useAuthStore()

  /* ── 基础状态 ── */
  const deptNameByCode = ref<Record<string, string>>({})
  const loading = ref(false)
  const keyword = ref('')
  const riskFilter = ref('all')
  const patients = ref<any[]>([])
  const stats = ref<any>({})
  const sbt = ref<any>({})
  const completion = ref<any>({})
  const worklist = ref<any>({ tasks: [], summary: {} })

  /* ── 抽屉状态 ── */
  const drawerOpen = ref(false)
  const drawerPatient = ref<any>(null)
  const timeline = ref<any[]>([])
  const airwayPlan = ref<any>({})
  const deteriorationForecast = ref<any>({})

  /* ── 路由参数 ── */
  const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim())
  const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
  const resolvedDeptName = computed(() => deptNameByCode.value[routeDeptCode.value] || '')
  const scopeLabel = computed(() => routeDeptName.value || resolvedDeptName.value || routeDeptCode.value || '全部 ICU 在科患者')

  /* ── 筛选选项 ── */
  const riskOptions = [
    { value: 'all', label: '全部风险' },
    { value: '高驱动压', label: '高驱动压' },
    { value: '低氧合', label: '低氧合' },
    { value: '气囊压待测', label: '气囊压待测' },
    { value: '困难气道', label: '困难气道' },
    { value: 'sbt', label: 'SBT候选' },
  ]

  /* ── 患者筛选 ── */
  const filteredPatients = computed(() => {
    const q = keyword.value.trim().toLowerCase()
    return patients.value.filter((row) => {
      if (riskFilter.value === 'sbt' && row.sbt_candidate_status?.status !== 'candidate') return false
      if (riskFilter.value !== 'all' && riskFilter.value !== 'sbt' && !(row.risk_tags || []).includes(riskFilter.value)) return false
      if (!q) return true
      return [row.bed_no, row.name, row.diagnosis, row.ventilator_mode].some((item) => String(item || '').toLowerCase().includes(q))
    })
  })

  /* ── 紧急患者排序（按风险优先级） ── */
  const urgentPatients = computed(() => {
    return [...filteredPatients.value].sort((a, b) => {
      const pa = computePatientPriority(a)
      const pb = computePatientPriority(b)
      return pb - pa
    })
  })

  function computePatientPriority(patient: any): number {
    let p = 0
    const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags : []
    const score = Number(patient?.safety_score || 0)
    if (tags.includes('低氧合')) p += 10
    if (tags.includes('高驱动压')) p += 8
    if (tags.includes('气囊压待测')) p += 4
    if (tags.includes('困难气道')) p += 6
    if (patient?.sbt_candidate_status?.status === 'candidate') p += 3
    if (score < 60) p += 5
    else if (score < 80) p += 2
    return p
  }

  /* ── 侧边栏数据 ── */

  /** 今日待办（来自 worklist 或自动生成） */
  const todayTasks = computed(() => {
    if (Array.isArray(worklist.value?.tasks) && worklist.value.tasks.length) {
      return worklist.value.tasks.map((item: any) => ({
        ...item,
        tone: item.priority === 'high' ? 'danger' : item.priority === 'medium' ? 'warning' : 'info',
      })).slice(0, 6)
    }
    const rows: any[] = []
    for (const item of sbt.value?.todo || []) {
      rows.push({ ...item, title: `评估 SBT`, reason: `床${item.bed_no || '--'} ${sbtCandidateReason(item)}`, tone: 'info' })
    }
    for (const item of patients.value.filter((r: any) => (r.risk_tags || []).includes('气囊压待测')).slice(0, 3)) {
      rows.push({ ...item, title: '复查气囊压', reason: `床${item.bed_no || '--'} 近8h缺失`, tone: 'warning' })
    }
    return rows.slice(0, 6)
  })

  /** 即将超时（闭环任务中高优先级） */
  const timeoutItems = computed(() => {
    const tasks = completion.value?.tasks || []
    return tasks
      .filter((t: any) => t.priority === 'high')
      .slice(0, 4)
      .map((t: any) => ({
        ...t,
        tone: 'danger',
      }))
  })

  /** 需要医生确认（高驱动压 + 低氧合 患者） */
  const doctorConfirmItems = computed(() => {
    return (patients.value || [])
      .filter((r: any) => {
        const tags = r.risk_tags || []
        return tags.includes('低氧合') || tags.includes('高驱动压')
      })
      .slice(0, 4)
      .map((r: any) => {
        const tags = r.risk_tags || []
        const reason = tags.includes('低氧合') ? '氧合异常' : '驱动压偏高'
        return { ...r, reason, tone: tags.includes('低氧合') ? 'danger' : 'warning' }
      })
  })

  /* ── 辅助函数 ── */
  function fmt(v: any) { return formatBeijingTime(v, '—') }

  function fmtVentParam(key: string, value: any) {
    if (value === null || value === undefined || value === '') return '—'
    const num = Number(value)
    if (!Number.isFinite(num)) return String(value)
    if (key === 'fio2') {
      const fio2 = num > 0 && num <= 1 ? num * 100 : num
      return `${Math.round(fio2)}`
    }
    const decimals: Record<string, number> = {
      peep: 0, vt_set: 0, peak_flow: 0, driving_pressure: 1,
      airway_resistance: 1, p01: 1, pplat: 0, c_stat: 0,
      static_compliance: 0, pf_ratio: 0, etco2: 0, energy_expenditure: 0, rass: 0,
    }
    const digits = decimals[key] ?? 1
    const rounded = Number(num.toFixed(digits))
    return digits === 0 || Number.isInteger(rounded) ? String(Math.round(rounded)) : rounded.toFixed(digits)
  }

  function compactRiskTags(patient: any) {
    const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags.filter(Boolean) : []
    return tags.length ? tags.slice(0, 3) : ['常规复核']
  }

  function patientTone(patient: any) {
    const score = Number(patient?.safety_score || 0)
    const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags : []
    if (tags.includes('低氧合') || tags.includes('高驱动压') || score < 60) return 'danger'
    if (tags.length || score < 80) return 'warn'
    return 'stable'
  }

  function sbtCandidateScore(row: any) {
    let score = 50
    if (Number(row?.pf_ratio || 0) >= 150) score += 15
    if (Number(row?.peep || 99) <= 8) score += 10
    if (Number(row?.fio2 || 1) <= 0.5) score += 10
    const rass = Number(row?.rass)
    if (Number.isFinite(rass) && rass >= -2 && rass <= 1) score += 10
    if (!(row?.risk_tags || []).includes('低氧合')) score += 5
    return Math.min(100, score)
  }

  function sbtCandidateReason(row: any) {
    const blockers = []
    if (row?.rass == null) blockers.push('RASS缺失')
    if (Number(row?.fio2 || 0) > 0.5) blockers.push('FiO2偏高')
    if (Number(row?.peep || 0) > 8) blockers.push('PEEP偏高')
    if ((row?.risk_tags || []).includes('低氧合')) blockers.push('氧合不稳')
    return blockers.length ? `阻碍：${blockers.slice(0, 2).join('、')}` : '建议评估'
  }

  function shortIssue(patient: any): string {
    const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags : []
    if (tags.includes('低氧合')) return '氧合异常'
    if (tags.includes('高驱动压')) return '驱动压偏高'
    if (tags.includes('气囊压待测')) return '气囊压待测'
    if (tags.includes('困难气道')) return '困难气道'
    if (patient?.sbt_candidate_status?.status === 'candidate') return 'SBT可评估'
    return '常规复核'
  }

  function nextAction(patient: any): string {
    const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags : []
    if (tags.includes('低氧合')) return '复核氧合'
    if (tags.includes('高驱动压')) return '复核参数'
    if (tags.includes('气囊压待测')) return '补录气囊压'
    if (patient?.sbt_candidate_status?.status === 'candidate') return '评估SBT'
    return '查看'
  }

  /* ── 抽屉相关计算 ── */
  const airwayPlanView = computed(() => {
    const plan = airwayPlan.value || {}
    const risk = String(plan.risk_level || 'unknown').toLowerCase()
    const isDefault = Boolean(plan.is_default || plan.is_mock)
    const equipment = Array.isArray(plan.backup_equipment) ? plan.backup_equipment.filter(Boolean) : []
    const contacts = Array.isArray(plan.contacts) ? plan.contacts.filter(Boolean) : []
    return {
      statusText: isDefault ? '默认流程提醒' : '已维护预案',
      riskText: risk === 'high' ? '高风险' : risk === 'medium' ? '中风险' : '待评估',
      tagColor: risk === 'high' ? 'red' : risk === 'medium' ? 'gold' : 'blue',
      difficultAirway: Boolean(plan.difficult_airway),
      equipment: equipment.length ? equipment.join(' / ') : '待补充',
      contacts: contacts.length ? contacts.join(' / ') : '待补充',
      note: plan.note || '暂无预案说明，建议由呼吸治疗师与麻醉团队补充。',
    }
  })

  const forecastView = computed(() => {
    const row = deteriorationForecast.value || {}
    const features = row.features || {}
    const forecast = row.forecast || {}
    const completeness = row.data_completeness || {}
    const severity = String(row.severity || row.risk_level || 'none').toLowerCase()
    const ratio = Number(completeness.completeness_ratio)
    return {
      title: row.available ? (severity === 'high' ? '需优先复核' : severity === 'warning' ? '趋势需关注' : '暂无明显恶化') : '数据不足',
      color: severity === 'high' ? 'red' : severity === 'warning' ? 'gold' : 'blue',
      sfRatio: features.latest_sf_ratio != null ? Math.round(Number(features.latest_sf_ratio)) : '—',
      projected: forecast.projected_sf_ratio != null ? Math.round(Number(forecast.projected_sf_ratio)) : '—',
      completeness: Number.isFinite(ratio) ? `${Math.round(ratio * 100)}%` : '—',
      note: row.available ? `特征版本 ${row.feature_schema_version || features.feature_schema_version || '—'}，仅作实验性趋势提示。` : (row.unavailable_reason || '缺少可配对的 SpO2/FiO2 数据。'),
    }
  })

  /* ── 请求参数 ── */
  function requestParams(): RespiratoryScopeParams {
    const params: RespiratoryScopeParams = { patient_scope: 'in_dept' }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDeptName.value) params.dept = routeDeptName.value
    return params
  }

  /* ── API 调用 ── */
  async function loadDeptNameMap() {
    try {
      const res = await getDepartments()
      const rows = Array.isArray(res.data?.departments) ? res.data.departments : []
      const next: Record<string, string> = {}
      rows.forEach((row: any) => {
        const code = String(row?.deptCode || row?.code || row?.dept_code || '').trim()
        const name = String(row?.dept || row?.name || '').trim()
        if (code && name) next[code] = name
      })
      deptNameByCode.value = next
    } catch { /* ignore */ }
  }

  async function loadAll() {
    loading.value = true
    void loadDeptNameMap()
    try {
      const res = await getRespiratoryDashboard(requestParams())
      const d = res.data || {}
      patients.value = d.dashboard?.patients || []
      stats.value = d.dashboard?.stats || {}
      completion.value = d.dashboard?.completion || {}
      sbt.value = d.sbt || {}
      worklist.value = d.worklist || { tasks: [], summary: {} }
    } finally {
      loading.value = false
    }
  }

  async function openPatient(row: any) {
    drawerPatient.value = row
    drawerOpen.value = true
    const [tl, plan, forecast] = await Promise.all([
      getVentilatorTimeline(row.patient_id),
      getAirwayPlan(row.patient_id),
      getRespiratoryDeteriorationForecast(row.patient_id).catch(() => ({ data: {} })),
    ])
    timeline.value = tl.data?.timeline || []
    airwayPlan.value = plan.data?.plan || {}
    deteriorationForecast.value = forecast.data || {}
  }

  async function openTaskPatient(item: any) {
    const row = patients.value.find((p) => p.patient_id === item.patient_id)
    if (row) await openPatient(row)
  }

  async function closeRespTask(item: any) {
    if (item.task_id) {
      await closeRespiratoryWorklistTask(item.task_id, {
        patient_id: item.patient_id,
        status: 'completed',
        result: '床旁已复核',
        note: `闭环：${item.title || '呼吸治疗任务'}。${item.reason || item.detail || ''}`,
      })
    }
    await postRespiratoryTaskDone(item.patient_id, {
      airway_type: '床旁已复核',
      humidification_status: '已复核',
      note: `闭环：${item.title || '呼吸治疗任务'}。${item.detail || ''}`,
    })
    message.success('已记录闭环')
    await loadAll()
  }

  async function recordSbt(row: any, status: 'completed' | 'failed') {
    await postSbtStatus(row.patient_id, {
      status,
      note: status === 'completed' ? '呼吸治疗师工作台记录 SBT 已完成' : '呼吸治疗师工作台记录 SBT 失败，原因待补充',
    })
    message.success(status === 'completed' ? '已记录 SBT 完成' : '已记录 SBT 失败')
    await loadAll()
  }

  async function recordAirway() {
    if (!drawerPatient.value) return
    await postAirwayRecord(drawerPatient.value.patient_id, {
      airway_type: drawerPatient.value.airway_type,
      cuff_pressure: drawerPatient.value.latest_cuff_pressure || '',
      humidification_status: '待床旁确认',
      note: '呼吸治疗师工作台快速补录，请完善痰液性状、固定深度和 VAP bundle。',
    })
    message.success('已创建气道记录草稿')
  }

  async function saveDifficultAirwayPlan() {
    if (!drawerPatient.value) return
    await postAirwayPlan(drawerPatient.value.patient_id, {
      risk_level: 'high',
      difficult_airway: true,
      backup_equipment: ['视频喉镜', '纤支镜', '环甲膜穿刺包'],
      contacts: ['麻醉科', '耳鼻喉科'],
      note: '呼吸治疗师工作台快速标记，需临床团队复核完善。',
    })
    message.success('已标记困难气道预案')
    const plan = await getAirwayPlan(drawerPatient.value.patient_id)
    airwayPlan.value = plan.data?.plan || {}
  }

  /* ── 路由监听 ── */
  watch(() => [route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
    void loadAll()
  })

  return {
    /* 状态 */
    loading,
    keyword,
    riskFilter,
    riskOptions,
    patients,
    stats,
    sbt,
    completion,
    worklist,
    scopeLabel,

    /* 筛选后数据 */
    filteredPatients,
    urgentPatients,

    /* 侧边栏数据 */
    todayTasks,
    timeoutItems,
    doctorConfirmItems,

    /* 抽屉 */
    drawerOpen,
    drawerPatient,
    timeline,
    airwayPlan,
    deteriorationForecast,
    airwayPlanView,
    forecastView,

    /* 函数 */
    loadAll,
    openPatient,
    openTaskPatient,
    closeRespTask,
    recordSbt,
    recordAirway,
    saveDifficultAirwayPlan,
    fmt,
    fmtVentParam,
    compactRiskTags,
    patientTone,
    sbtCandidateScore,
    sbtCandidateReason,
    shortIssue,
    nextAction,
  }
}
