/**
 * useClinicalWorkflow — 临床工作台共享状态与逻辑
 *
 * 所有子视图通过同一个 composable 实例共享数据，
 * 避免重复请求接口。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  closeClinicalTask,
  getClinicalPatientHandoff,
  getClinicalPatientStory,
  getClinicalRoleHome,
  getTreatmentRecommendation,
  postClinicalTask,
} from '../api'
import { useAuthStore } from '../stores/auth'

/* ───── 标签映射 ───── */
const labelMap: Record<string, string> = {
  clinical_document: '临床文书记录',
  prone_position_monitor: '俯卧位通气监测',
  'PRE-DELIRIC': '谵妄高风险',
  'pre-deliric': '谵妄高风险',
  DELIRIC: '谵妄风险',
  deliric: '谵妄风险',
  SOFA: 'SOFA 器官功能评分',
  qSOFA: 'qSOFA 感染风险评分',
  sofa: 'SOFA 器官功能评分',
  qsofa: 'qSOFA 感染风险评分',
  sepsis: '脓毒症风险',
  septic_shock: '脓毒性休克风险',
  ards: 'ARDS 风险',
  aki: '急性肾损伤风险',
  ventilator_asynchrony: '呼吸机不同步',
  driving_pressure: '驱动压偏高',
  mechanical_power: '机械功率升高',
  lung_protective_ventilation: '肺保护性通气未达标',
  post_extubation_failure_risk: '拔管后失败风险',
  extubation_failure_risk: '拔管失败风险',
  weaning: '撤机评估',
  pplat_high: '平台压升高',
}

export function useClinicalWorkflow() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()

  /* ───── 基础状态 ───── */
  const loading = ref(false)
  const home = ref<any>(null)
  const storyOpen = ref(false)
  const storyLoading = ref(false)
  const story = ref<any>(null)
  const handoffText = ref('')
  const selectedPatient = ref<any>(null)
  const activeStoryMode = ref<'story' | 'handoff'>('story')
  const featureDetail = ref<any>(null)
  const featureTaskId = ref('')
  const treatmentRecommendation = ref<any>(null)
  const treatmentLoading = ref(false)
  const expandedFeatureKeys = ref(new Set<string>())
  const activeSignalFilter = ref('')

  let homeRequestSeq = 0
  const roleHomeCache = new Map<string, any>()
  const roleHomeInflight = new Map<string, Promise<any>>()

  /* ───── 路由参数解析 ───── */
  function firstRouteQuery(...keys: string[]) {
    for (const key of keys) {
      const value = route.query[key]
      const text = String(Array.isArray(value) ? value[0] : value || '').trim()
      if (text) return text
    }
    return ''
  }

  const routeUserName = computed(() => firstRouteQuery('userName', 'useName', 'username', 'user_id', 'userId'))
  const routeRole = computed(() => firstRouteQuery('role', 'userRole'))
  const routeDeptCode = computed(() => firstRouteQuery('dept_code', 'deptCode') || auth.deptCode || '')
  const routeDept = computed(() => firstRouteQuery('dept', 'department'))

  /* ───── 核心数据 ───── */
  const cards = computed(() => home.value?.cards || [])
  const priorityQueue = computed(() => home.value?.priority_queue || [])
  const playbook = computed(() => home.value?.playbook || [])
  const scannerReview = computed(() => home.value?.scanner_review || [])
  const storyClusters = computed(() => story.value?.clusters || [])
  const nursingTasks = computed(() => home.value?.nursing_tasks || [])
  const doctorGaps = computed(() => home.value?.doctor_gaps || [])
  const qualityActions = computed(() => home.value?.quality_actions || [])
  const directorDigest = computed(() => home.value?.director_digest || {})
  const isDirector = computed(() => home.value?.role === 'director')
  const isHeadNurse = computed(() => home.value?.role === 'head_nurse')
  const isManager = computed(() => isDirector.value || isHeadNurse.value)
  const icuDayFlow = computed(() => home.value?.icu_day_flow || [])
  const stickyFeatures = computed(() => home.value?.sticky_features || {})
  const roleDistribution = computed(() => home.value?.role_distribution || [])
  const openTasks = computed(() => home.value?.open_tasks || {})
  const openTaskItems = computed(() => openTasks.value?.items || [])
  const openTaskTotal = computed(() => openTasks.value?.total || openTaskItems.value.length || 0)
  const clinicalVisuals = computed(() => home.value?.clinical_visuals || {})
  const bedHeatmap = computed(() => clinicalVisuals.value?.bed_heatmap || [])
  const nursingOmissions = computed(() => clinicalVisuals.value?.nursing_omissions || [])
  const nursingCompletion = computed(() => clinicalVisuals.value?.nursing_completion || {})
  const orderSwimlanes = computed(() => clinicalVisuals.value?.order_swimlanes || [])
  const antibioticIntensity = computed(() => clinicalVisuals.value?.antibiotic_intensity || {})
  const antibioticSummary = computed(() => antibioticIntensity.value?.summary || {})
  const antibioticPatients = computed(() => antibioticIntensity.value?.patients || [])
  const antibioticTasks = computed(() => antibioticIntensity.value?.tasks || [])
  const weaningLights = computed(() => clinicalVisuals.value?.weaning_lights || [])
  const dischargeLights = computed(() => clinicalVisuals.value?.discharge_lights || [])
  const rescueTimeline = computed(() => clinicalVisuals.value?.rescue_timeline || [])
  const familyCards = computed(() => clinicalVisuals.value?.family_cards || [])
  const nursingTodoCount = computed(() => nursingOmissions.value.filter((item: any) => item.status === 'todo').length)

  /* ───── 角色/账号 ───── */
  const roleLabel = computed(() => ({
    nurse: '护士',
    head_nurse: '护士长',
    doctor: '医生',
    director: '主任',
  }[home.value?.role as string] || '临床'))

  const accountLabel = computed(() =>
    home.value?.account?.trueName || home.value?.account?.display_name || home.value?.account?.userName || routeUserName.value || '未识别账号',
  )
  const scopeLabel = computed(() =>
    home.value?.account?.dept || routeDept.value || home.value?.account?.dept_code || routeDeptCode.value || '当前科室',
  )

  /* ───── 工具函数 ───── */
  function pct(value: any) {
    const num = Number(value || 0)
    return `${Math.round(num * 100)}%`
  }

  function riskTone(value: any) {
    const score = Number(value || 0)
    if (score >= 8) return 'risk-high'
    if (score >= 4) return 'risk-mid'
    return 'risk-low'
  }

  function clinicalText(value: any) {
    let text = String(value || '').trim()
    if (!text) return ''
    Object.entries(labelMap)
      .sort(([a], [b]) => b.length - a.length)
      .forEach(([key, label]) => {
        text = text.split(key).join(label)
      })
    text = text.split('->').join('→').split('_').join(' ')
    return text
  }

  function shortTaskText(value: any, max = 34) {
    const text = clinicalText(value).replace(/\s+/g, ' ').trim()
    return text.length > max ? `${text.slice(0, max)}...` : text
  }

  function dedupeHandoffLines(value: any) {
    const seen = new Set<string>()
    const result: string[] = []
    String(value || '').split(/\r?\n/).forEach((line) => {
      const normalized = line.replace(/^-\s*/, '').trim()
      if (normalized && seen.has(normalized)) return
      if (normalized) seen.add(normalized)
      result.push(clinicalText(line))
    })
    return result.join('\n')
  }

  function patientSignalText(row: any) {
    return JSON.stringify(row || {}).toLowerCase()
  }

  function findPatientInHome(patientId: string) {
    const id = String(patientId || '')
    const rows = [
      ...priorityQueue.value,
      ...nursingTasks.value,
      ...doctorGaps.value,
      ...bedHeatmap.value,
      ...orderSwimlanes.value,
      ...weaningLights.value,
      ...dischargeLights.value,
      ...familyCards.value,
    ]
    return rows.find((row: any) => String(row?.patient_id || '') === id) || { patient_id: id, name: '患者', bed: '--' }
  }

  function firstPatientId() {
    return String(priorityQueue.value?.[0]?.patient_id || '')
  }

  function normalizeRouteRole(value: string) {
    const raw = String(value || '').toLowerCase()
    if (/head|护士长/.test(raw)) return 'head_nurse'
    if (/nurse|护士/.test(raw)) return 'nurse'
    if (/director|主任/.test(raw)) return 'director'
    if (/doctor|医生/.test(raw)) return 'doctor'
    return raw || 'doctor'
  }

  function roleHomeCacheKey() {
    return [routeUserName.value, normalizeRouteRole(routeRole.value), routeDeptCode.value, routeDept.value].join('|')
  }

  /* ───── 抗菌药计算 ───── */
  const activeAntibioticPatient = computed(() => {
    const patient = selectedPatient.value
    if (!patient?.hisPid && !patient?.patient_id) return null
    const label = `${patient?.bed || ''}床`
    return antibioticPatients.value.find((row: any) =>
      String(row.hisPid || '') === String(patient.hisPid || '')
      || String(row.patient || '').includes(label),
    ) || null
  })
  const activeAntibioticSummary = computed(() => activeAntibioticPatient.value?.summary || antibioticSummary.value || {})
  const activeAntibioticRows = computed(() => activeAntibioticPatient.value?.daily || antibioticIntensity.value?.daily || [])
  const activeAntibioticBars = computed(() => {
    const rows = activeAntibioticRows.value || []
    const max = Math.max(...rows.map((row: any) => Number(row.value || 0)), 1)
    return rows.map((row: any) => ({
      ...row,
      percent: Math.max(8, Math.round((Number(row.value || 0) / max) * 100)),
    }))
  })

  /* ───── 优先队列过滤 ───── */
  const filteredPriorityQueue = computed(() => {
    const rows = priorityQueue.value || []
    const key = activeSignalFilter.value
    if (!key) return rows
    const roleKeys: Record<string, string[]> = {
      nurse: ['护理', 'nursing', '管路', '尿量', '压疮', '谵妄', '镇静'],
      doctor: ['查房', '医嘱', '感染', '撤机', '抗菌', '肾', '呼吸', '循环'],
      director: ['未闭环', '规则', '质控', '高危'],
      focus: ['高危', '未闭环'],
      nursing: ['护理', '管路', '尿量', '压疮', '谵妄', '镇静'],
      quality: ['未闭环', '重复', '规则'],
      antibiotic: ['抗菌', '感染', '脓毒'],
      rescue: ['抢救', '休克', '循环', '乳酸'],
      respiratory: ['呼吸', '氧', 'vent', '撤机', '拔管', 'ards', 'spo2'],
      circulatory: ['循环', '休克', '血压', '乳酸', 'sepsis', '脓毒'],
      renal: ['肾', '尿量', '肌酐', 'aki', 'crrt'],
      coagulation: ['凝血', '出血', '血小板', '抗凝'],
      neurologic: ['谵妄', '神经', '意识', '镇静', 'rass'],
      hepatic: ['肝', '胆红素', '转氨酶'],
    }
    const tokens = roleKeys[key] || [key]
    const matched = rows.filter((row: any) => tokens.some(token => patientSignalText(row).includes(String(token).toLowerCase())))
    return matched.length ? matched : rows
  })

  /* ───── 操作函数 ───── */
  function selectPatient(patientId: string, mode: 'story' | 'handoff') {
    selectedPatient.value = findPatientInHome(patientId)
    activeStoryMode.value = mode
    void loadTreatmentRecommendation(patientId)
  }

  async function loadTreatmentRecommendation(patientId: string) {
    const id = String(patientId || '')
    if (!id) return
    treatmentLoading.value = true
    try {
      const res = await getTreatmentRecommendation(id)
      treatmentRecommendation.value = res.data || null
    }
    catch (error: any) {
      treatmentRecommendation.value = { available: false, reason: error?.message || 'AI 治疗策略接口暂不可用' }
    }
    finally {
      treatmentLoading.value = false
    }
  }

  function goPatientDetail(patientId: string) {
    if (!patientId) {
      message.warning('缺少患者ID，无法进入患者详情')
      return
    }
    void router.push({ path: `/patient/${patientId}`, query: route.query })
  }

  function openRoundingSheet(patientId?: string) {
    const id = String(patientId || firstPatientId() || '').trim()
    if (!id) {
      message.info('当前暂无可打开的查房患者。')
      return
    }
    void router.push({
      path: '/rounding-sheet',
      query: { ...route.query, patientId: id, focus: 'rounding' },
    })
  }

  function toggleFeatureExpanded(key: string) {
    const next = new Set(expandedFeatureKeys.value)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    expandedFeatureKeys.value = next
  }

  function applySignalFilter(key: string) {
    activeSignalFilter.value = activeSignalFilter.value === key ? '' : key
  }

  async function openStory(patientId: string) {
    if (!patientId) {
      message.warning('缺少患者ID，无法打开患者事件链')
      return
    }
    selectPatient(patientId, 'story')
    featureDetail.value = null
    message.loading({ content: '正在打开患者事件链...', key: 'clinical-story', duration: 0 })
    storyOpen.value = true
    storyLoading.value = true
    handoffText.value = ''
    story.value = null
    try {
      const { data } = await getClinicalPatientStory(patientId, { hours: 24 })
      story.value = data?.story || data
      message.success({ content: '患者事件链已打开', key: 'clinical-story', duration: 1.5 })
    }
    catch (error: any) {
      message.error({ content: error?.message || '患者事件链加载失败', key: 'clinical-story' })
    }
    finally {
      storyLoading.value = false
    }
  }

  async function openHandoff(patientId: string) {
    if (!patientId) {
      message.warning('缺少患者ID，无法生成交班摘要')
      return
    }
    selectPatient(patientId, 'handoff')
    featureDetail.value = null
    message.loading({ content: '正在生成交班摘要...', key: 'clinical-story', duration: 0 })
    storyOpen.value = true
    storyLoading.value = true
    handoffText.value = ''
    story.value = null
    try {
      const { data } = await getClinicalPatientHandoff(patientId, { role: home.value?.role || 'doctor', hours: 12 })
      handoffText.value = data?.handoff?.handoff_text || ''
      story.value = data?.handoff?.story || null
      message.success({ content: '交班摘要已打开', key: 'clinical-story', duration: 1.5 })
    }
    catch (error: any) {
      message.error({ content: error?.message || '交班摘要加载失败', key: 'clinical-story' })
    }
    finally {
      storyLoading.value = false
    }
  }

  function checklistForMode(mode: string, item: any) {
    const patientLine = item?.bed || item?.name ? `关联患者：${item?.bed || '--'}床 ${item?.name || '患者'}` : ''
    const detail = String(item?.detail || '').trim()
    const map: Record<string, string[]> = {
      story: ['按时间顺序查看过去24小时关键事件。', '确认高危告警是否已有医嘱、护理执行或病程记录。', '必要时进入患者详情核对原始数据。'],
      rounding: ['查房时先确认当前主要问题是否变化。', '核对证据链：检验、生命体征、用药、管路和护理记录。', '把缺失复查或医嘱补到今日计划。'],
      nursing: ['先确认患者现场状态和监护趋势。', '复核管路、皮肤、镇静、谵妄、出入量和执行记录。', '交班前把未完成事项继续留给下一班。'],
      order_gap: ['确认系统提示是否确实适用于该患者。', '核对"该有但没有"的复查、预防、治疗或记录。', '由医生决定是否补开医嘱，系统不自动下医嘱。'],
      discharge: ['核对循环、氧合、意识、管路和高级生命支持是否稳定。', '确认护理级别和普通病区承接能力。', '主任或上级医生最终确认是否转出。'],
      family: ['用家属能听懂的话说明目前主要问题。', '说明今天比昨天好转、恶化或持平的地方。', '讲清下一步计划和最需要警惕的风险。'],
      medication: ['复核肾功能、肝功能和 CRRT 状态。', '检查抗菌药疗程、剂量、TDM 和相互作用。', '关注镇静镇痛、抗凝、胰岛素、血管活性药变化。'],
      preview: ['如果未来24小时恶化，先想最可能原因。', '提前布置复查、监测频率和护理观察点。', '把预案写进交班，减少夜班临时追数据。'],
    }
    const checklist = map[mode] ?? map.story ?? []
    return [patientLine, ...checklist, detail].filter(Boolean)
  }

  async function showFeatureDetail(item: any, feature: any) {
    const mode = String(feature?.detailMode || item?.kind || 'story')
    const patientId = String(item?.patient_id || firstPatientId())
    if (patientId) selectPatient(patientId, mode === 'story' ? 'story' : 'handoff')
    else selectedPatient.value = { patient_id: '', name: '暂无患者', bed: '--' }
    featureDetail.value = {
      owner: feature?.owner,
      title: `${feature?.title || '临床任务'}：${shortTaskText(item?.title || '任务详情', 24)}`,
      detail: shortTaskText(item?.detail || feature?.subtitle || '系统已整理该任务的临床核对重点。', 56),
      checklist: checklistForMode(mode, item),
    }
    featureTaskId.value = ''
    try {
      const { data } = await postClinicalTask({
        patient_id: patientId,
        bed: item?.bed,
        name: item?.name,
        module: 'clinical_workflow',
        task_type: mode,
        title: item?.title || feature?.title || '临床任务',
        detail: item?.detail || feature?.subtitle || '',
        priority: item?.priority || item?.tone || 'medium',
        source: 'ICU智能协同工作台',
      })
      featureTaskId.value = data?.task?.task_id || ''
    }
    catch {
      message.warning('任务已打开，但写入闭环记录失败')
    }
    storyOpen.value = true
    storyLoading.value = false
    handoffText.value = ''
    story.value = null
  }

  async function closeCurrentFeatureTask() {
    if (!featureTaskId.value) return
    await closeClinicalTask(featureTaskId.value, { outcome: '已完成' })
    message.success('任务已闭环')
    featureTaskId.value = ''
    await loadHome()
  }

  function openExistingTask(task: any) {
    const patientId = String(task?.patient_id || '')
    if (patientId) selectPatient(patientId, 'handoff')
    featureTaskId.value = task?.task_id || ''
    featureDetail.value = {
      owner: task?.module_label || '临床任务',
      title: `${task?.bed_label || task?.bed || '--'}床：${task?.title || '待处理任务'}`,
      detail: shortTaskText(task?.detail || '请确认现场状态、处置记录和后续计划。', 56),
      checklist: checklistForMode(task?.task_type || 'story', task),
    }
    storyOpen.value = true
    storyLoading.value = false
    handoffText.value = ''
    story.value = null
  }

  function showVisualPatient(row: any, mode: string) {
    const patientId = String(row?.patient_id || firstPatientId())
    const feature = {
      owner: 'ICU',
      title: ({
        order_gap: '医嘱闭环',
        weaning: '撤机评估',
        discharge: '转出评估',
        family: '家属沟通',
      } as Record<string, string>)[mode] || '临床任务',
      detailMode: mode,
      subtitle: '系统已整理为可点击任务。',
    }
    const lightDetailFn = (r: any, t: string) => {
      const lights = Array.isArray(r?.lights) ? r.lights : []
      const bad = lights.filter((l: any) => !l.ok).map((l: any) => l.label)
      return bad.length ? `${t}未达标：${bad.join('、')}` : `${t}灯号全部通过，可进入人工确认。`
    }
    const item = {
      patient_id: patientId,
      bed: row?.bed,
      name: row?.name,
      title: row?.bed ? `${row.bed}床 ${feature.title}` : feature.title,
      detail: mode === 'weaning'
        ? lightDetailFn(row, '撤机')
        : mode === 'discharge'
          ? lightDetailFn(row, '转出')
          : mode === 'family'
            ? '按"问题、变化、风险、计划"生成家属沟通卡。'
            : '按"告警、医嘱、执行、复查、结果"核对闭环状态。',
    }
    showFeatureDetail(item, feature)
  }

  function buildFallbackHome() {
    const userName = routeUserName.value
    const role = normalizeRouteRole(routeRole.value)
    const deptCode = routeDeptCode.value
    const dept = routeDept.value
    return {
      code: 0,
      title: '临床工作台',
      role,
      account: {
        userName,
        display_name: userName,
        role,
        dept_code: deptCode,
        dept,
        found: Boolean(userName),
      },
      cards: [],
      priority_queue: [],
      playbook: [],
      scanner_review: [],
      nursing_tasks: [],
      doctor_gaps: [],
      quality_actions: [],
      director_digest: {},
      icu_day_flow: [],
      ai_toolbox: [],
      sticky_features: {},
      role_distribution: [],
      open_tasks: { total: 0, items: [] },
      clinical_visuals: {},
      degraded: true,
    }
  }

  async function loadHome() {
    const seq = ++homeRequestSeq
    const cacheKey = roleHomeCacheKey()
    const cached = roleHomeCache.get(cacheKey)
    home.value = cached || buildFallbackHome()
    loading.value = !cached
    try {
      let request = roleHomeInflight.get(cacheKey)
      if (!request) {
        request = getClinicalRoleHome({
          userName: routeUserName.value || undefined,
          role: routeRole.value || undefined,
          dept_code: routeDeptCode.value || undefined,
          dept: routeDept.value || undefined,
        }).then(res => res.data).finally(() => roleHomeInflight.delete(cacheKey))
        roleHomeInflight.set(cacheKey, request)
      }
      const data = await request
      if (seq !== homeRequestSeq) return
      home.value = data
      roleHomeCache.set(cacheKey, data)
    }
    catch (error: any) {
      if (seq !== homeRequestSeq) return
      const isTimeout = String(error?.code || error?.message || '').toLowerCase().includes('timeout') || error?.code === 'ECONNABORTED'
      if (!cached) home.value = buildFallbackHome()
      message.warning(isTimeout ? '工作台数据加载较慢，已先按当前账号展示，可稍后刷新。' : '工作台数据暂时加载失败，已先按当前账号展示。')
    }
    finally {
      if (seq === homeRequestSeq) loading.value = false
    }
  }

  /* ───── 启动 ───── */
  watch(() => [
    route.query.userName, route.query.useName, route.query.username, route.query.user_id, route.query.userId,
    route.query.role, route.query.userRole,
    route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department,
  ], () => {
    void loadHome()
  })

  return {
    // 路由
    route,
    router,
    // 基础状态
    loading,
    home,
    storyOpen,
    storyLoading,
    story,
    handoffText,
    selectedPatient,
    activeStoryMode,
    featureDetail,
    featureTaskId,
    treatmentRecommendation,
    treatmentLoading,
    expandedFeatureKeys,
    activeSignalFilter,
    // 核心数据
    cards,
    priorityQueue,
    playbook,
    scannerReview,
    storyClusters,
    nursingTasks,
    doctorGaps,
    qualityActions,
    directorDigest,
    isDirector,
    isHeadNurse,
    isManager,
    icuDayFlow,
    stickyFeatures,
    roleDistribution,
    openTaskItems,
    openTaskTotal,
    bedHeatmap,
    nursingOmissions,
    nursingCompletion,
    orderSwimlanes,
    antibioticIntensity,
    antibioticSummary,
    antibioticPatients,
    antibioticTasks,
    weaningLights,
    dischargeLights,
    rescueTimeline,
    familyCards,
    nursingTodoCount,
    activeAntibioticPatient,
    activeAntibioticSummary,
    activeAntibioticBars,
    filteredPriorityQueue,
    // 角色
    roleLabel,
    accountLabel,
    scopeLabel,
    routeUserName,
    routeRole,
    routeDeptCode,
    routeDept,
    // 工具函数
    pct,
    riskTone,
    clinicalText,
    shortTaskText,
    dedupeHandoffLines,
    patientSignalText,
    findPatientInHome,
    firstPatientId,
    normalizeRouteRole,
    // 操作函数
    selectPatient,
    goPatientDetail,
    openRoundingSheet,
    toggleFeatureExpanded,
    applySignalFilter,
    openStory,
    openHandoff,
    showFeatureDetail,
    closeCurrentFeatureTask,
    openExistingTask,
    showVisualPatient,
    loadHome,
    loadTreatmentRecommendation,
  }
}
