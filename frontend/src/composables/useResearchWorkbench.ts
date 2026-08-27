/**
 * useResearchWorkbench — 科研分析工作台逻辑
 *
 * 提取 ResearchWorkbench.vue 的核心状态、API 调用和计算属性。
 * 变量目录（variableCatalog）保留在视图中，因为它与模板强耦合。
 */
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { useResearchSelectionStore } from '../stores/researchSelection'
import { useAuthStore } from '../stores/auth'
import {
  getDepartments, getPatients, getResearchAnalyticsTaskStatus, getResearchSession,
  listResearchCohorts, listResearchSessions,
  getResearchPlatformArtifacts, getResearchMdroControlSummary,
  getResearchPlatformJobs, getResearchPlatformStatus, getResearchRespiratoryForecastStatus,
  deleteResearchCohort, postResearchExportFigure, postResearchExportTable,
  postResearchPlatformCheck, postResearchCorrelation,
  postResearchRegression, postResearchRoc, postResearchSubgroup, postResearchSurvival,
  postResearchTable1, postResearchTrend, postResearchVariableSummary, saveResearchSession,
} from '../api'

type AnyRecord = Record<string, any>
type AnalysisKey = 'table1' | 'survival' | 'regression' | 'roc' | 'subgroup' | 'trend' | 'correlation'
type LangKey = 'zh' | 'en'
type PartKey = 'interpretation' | 'methods_text' | 'results_text'

export function useResearchWorkbench(variableCatalog: Array<{ field: string; label: string; type: string; category: string; source: string; applicable: string[] }>) {
  const route = useRoute()
  const auth = useAuthStore()
  const researchSelectionStore = useResearchSelectionStore()
  researchSelectionStore.initializeVariables(variableCatalog.map((v) => v.field))
  const { selectedVariables, variableSummaries, selectedPatientIds, patientIdsVersion, cohort: selectionCohort } = storeToRefs(researchSelectionStore)

  /* ───── 基础状态 ───── */
  const tab = ref('prep')
  const cohorts = ref<Array<AnyRecord>>([])
  const cohortPreviewCount = ref(0)
  const patientLoadLoading = ref(false)
  const deptNameByCode = ref<Record<string, string>>({})
  const prepMode = ref<'saved' | 'dept' | 'builder' | ''>('saved')
  const cohortBuilderOpen = ref(false)
  const categoryFlash = reactive<Record<string, string>>({})
  const expandedVariableField = ref<string>('')
  const basePatientIds = ref<string[]>([])
  const originalCohortCount = ref(0)
  const cohortSourceFilters = ref<AnyRecord[]>([])

  /* ───── 作用域 ───── */
  const scope = reactive({
    cohort_id: '', patient_text: '', department: '',
    patient_scope: 'all' as 'in_dept' | 'out_dept' | 'all',
    group_by: 'outcome',
    variables: variableCatalog.map((v) => v.field) as string[],
  })

  /* ───── 加载状态 ───── */
  const loading = reactive({
    table1: false, survival: false, regression: false, roc: false,
    subgroup: false, trend: false, correlation: false,
  })

  /* ───── 分析结果 ───── */
  const table1Result = ref<AnyRecord | null>(null)
  const survivalResult = ref<AnyRecord | null>(null)
  const regressionResult = ref<AnyRecord | null>(null)
  const rocResult = ref<AnyRecord | null>(null)
  const subgroupResult = ref<AnyRecord | null>(null)
  const trendResult = ref<AnyRecord | null>(null)
  const correlationResult = ref<AnyRecord | null>(null)
  const exports = ref<Array<AnyRecord>>([])

  /* ───── 分析表单 ───── */
  const survivalForm = reactive({ timefield: 'los_icu_days', eventfield: 'icu_mortality', group_by: 'outcome', max_time: 28 })
  const regressionForm = reactive({ outcome: 'icu_mortality', outcome_type: 'binary', predictors: ['age', 'sofa_admission'], confounders: ['sex'] as string[] })
  const rocForm = reactive({ outcome: 'icu_mortality', predictors: ['sofa_admission', 'apache2'] as string[] })
  const subgroupForm = reactive({
    exposure: 'vasopressor', outcome: 'icu_mortality',
    outcome_type: 'binary' as 'binary' | 'continuous',
    subgroups: [] as Array<{ key: string; label: string; enabled: boolean; filterText: string }>,
  })
  const trendForm = reactive({ indicators: ['hr', 'map', 'lactate'] as string[], time_reference: 'icu_admission', time_range_hours: 72, interval_hours: 4 })
  const correlationForm = reactive({ variables: ['age', 'sofa_admission', 'apache2', 'los_icu_days'] as string[], method: 'auto' })

  /* ───── 配置面板 ───── */
  const openConfigKeys = reactive<{ [key: string]: string[] }>({
    table1: ['config'], survival: ['config'], regression: ['config'],
    roc: ['config'], trend: ['config'], correlation: ['config'],
  })

  /* ───── AI 状态 ───── */
  function newAiState() {
    return {
      open: false, loading: false, lang: 'zh' as LangKey, part: 'interpretation' as PartKey,
      content: { zh: { interpretation: '', methods_text: '', results_text: '' }, en: { interpretation: '', methods_text: '', results_text: '' } },
    }
  }
  type AiState = ReturnType<typeof newAiState>
  const ai = reactive<{ [K in AnalysisKey]: AiState }>({
    table1: newAiState(), survival: newAiState(), regression: newAiState(),
    roc: newAiState(), subgroup: newAiState(), trend: newAiState(), correlation: newAiState(),
  })

  /* ───── AI Planner ───── */
  const aiPlanner = reactive({
    prompt: '', loading: false, lastPlan: null as AnyRecord | null, lastMessage: '',
    progress: 0,
    steps: [] as Array<{ key: string; title: string; status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'; detail?: string }>,
    logs: [] as Array<{ time: string; level: 'info' | 'success' | 'error'; text: string }>,
  })

  /* ───── 会话 ───── */
  const openSessionDrawer = ref(false)
  const sessionLoading = ref(false)
  const sessionListLoading = ref(false)
  const sessionListError = ref('')
  const sessions = ref<Array<AnyRecord>>([])

  /* ───── 平台状态 ───── */
  const platformStatus = ref<AnyRecord | null>(null)
  const platformStatusLoading = ref(false)
  const platformStatusError = ref('')
  const researchJobs = ref<Array<AnyRecord>>([])
  const researchJobsSummary = ref<AnyRecord>({})
  const researchJobsLoading = ref(false)
  const researchJobsError = ref('')
  const researchArtifacts = ref<Array<AnyRecord>>([])
  const researchArtifactsLoading = ref(false)
  const researchArtifactsError = ref('')
  const respiratoryForecastStatus = ref<AnyRecord>({})
  const mdroControlSummary = ref<AnyRecord>({})
  const topicStatusLoading = ref(false)
  const topicTabs = ['respiratoryForecast', 'mdroControl']

  /* ───── ICD 搜索 ───── */
  const icdSearch = reactive({
    loading: false, keyword: '',
    options: [] as Array<{ value: string; label: string; code: string; name: string }>,
  })
  let summaryFetchSeq = 0

  /* ───── 筛选 ───── */
  const appliedVariableFilters = reactive<Record<string, AnyRecord>>({})
  const variableFilterDrafts = reactive<Record<string, AnyRecord>>({})
  const analysisAutoSync = reactive({ regression: true, roc: true, trend: true, correlation: true })

  /* ───── 路由 ───── */
  const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim())
  const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
  const currentDeptCode = computed(() => routeDeptCode.value)
  const currentDeptName = computed(() => deptNameByCode.value[currentDeptCode.value] || routeDeptName.value || '')
  const currentDeptDisplay = computed(() => currentDeptName.value || currentDeptCode.value || '未知')

  /* ───── 核心计算 ───── */
  const cohortReady = computed(() => selectedPatientIds.value.length > 0)
  const appliedFilterCount = computed(() => Object.keys(appliedVariableFilters).length)
  const currentCohortSummary = computed(() => {
    if (prepMode.value === 'dept') {
      const dept = currentDeptDisplay.value || '当前科室'
      const countText = selectedPatientIds.value.length ? ` | ${selectedPatientIds.value.length}例` : ''
      return `${dept} ${patientScopeLabel(scope.patient_scope)}患者${countText}`
    }
    const snapshot = selectionCohort.value
    if (snapshot) {
      const countText = snapshot.patientCount ? ` | ${snapshot.patientCount}例` : ''
      return `${snapshot.name} | ${patientScopeLabel(snapshot.patientScope)}${countText}`
    }
    if (!scope.cohort_id) return ''
    const match = cohorts.value.find((c) => c.cohort_id === scope.cohort_id)
    if (!match) return ''
    const count = match.n_patients || (match.patient_ids?.length ?? 0)
    return `${match.name || match.cohort_id} | ${count}例`
  })
  const variableGroups = computed(() => {
    const map = new Map<string, typeof variableCatalog>()
    variableCatalog.forEach((item) => {
      const key = item.category || '其他'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(item)
    })
    return Array.from(map.entries())
  })
  const navCompletion = computed<Record<string, boolean>>(() => ({
    table1: Boolean(table1Result.value),
    survival: Boolean(survivalResult.value),
    regression: Boolean(regressionResult.value),
    roc: Boolean(rocResult.value),
    subgroup: Boolean(subgroupResult.value),
    trend: Boolean(trendResult.value),
    correlation: Boolean(correlationResult.value),
  }))
  const groupSummaryCards = computed(() => {
    const defaults = [
      { name: '组A', countText: '--', percentText: '--', type: 'survive' },
      { name: '组B', countText: '--', percentText: '--', type: 'death' },
    ]
    const total = Number(cohortPreviewCount.value || selectedPatientIds.value.length || 0)
    const field = String(scope.group_by || '').trim()
    const summary = getVarSummary(field)
    const dist = (summary.distribution || {}) as Record<string, AnyRecord>
    const norm = (value: string) => String(value || '').trim().toLowerCase()
    const findCount = (keys: string[]) => {
      for (const [rawKey, info] of Object.entries(dist)) {
        if (keys.includes(norm(rawKey))) return Number(info?.count || 0)
      }
      return 0
    }
    const configMap: Record<string, Array<{ name: string; keys: string[]; type: string }>> = {
      outcome: [{ name: '存活组', keys: ['alive', '存活', 'survive'], type: 'survive' }, { name: '死亡组', keys: ['dead', 'death', '死亡'], type: 'death' }],
      icu_mortality: [{ name: '存活组', keys: ['0', 'false', 'no', 'alive'], type: 'survive' }, { name: '死亡组', keys: ['1', 'true', 'yes', 'dead'], type: 'death' }],
      hospital_mortality: [{ name: '存活组', keys: ['0', 'false', 'no', 'alive'], type: 'survive' }, { name: '死亡组', keys: ['1', 'true', 'yes', 'dead'], type: 'death' }],
      mortality_28d: [{ name: '28天存活', keys: ['0', 'false', 'no', 'alive'], type: 'survive' }, { name: '28天死亡', keys: ['1', 'true', 'yes', 'dead'], type: 'death' }],
    }
    const configured = configMap[field]
    if (configured && Object.keys(dist).length) {
      return configured.map((item) => {
        const count = findCount(item.keys)
        return { name: item.name, countText: `${count} 例`, percentText: total > 0 ? `${((count / total) * 100).toFixed(1)}%` : '--', type: item.type }
      })
    }
    return defaults
  })
  const cohortOptions = computed(() => cohorts.value.map((c) => {
    const count = c.n_patients ?? c.patient_count ?? c.patient_ids?.length ?? 0
    const name = c.name || c.cohort_id || '未命名队列'
    return { label: `${name} (${count})`, value: c.cohort_id }
  }))
  const groupByOptions = [
    { label: '结局（存活/死亡）', value: 'outcome' },
    { label: 'ICU死亡', value: 'icu_mortality' },
    { label: '院内死亡', value: 'hospital_mortality' },
    { label: '28天死亡', value: 'mortality_28d' },
    { label: '出科去向', value: 'discharge_dest' },
    { label: '住院天数分层', value: 'los_icu_group' },
    { label: '性别', value: 'sex' },
  ]
  const patientScopeOptions = [
    { label: '全部', value: 'all' },
    { label: '在科', value: 'in_dept' },
    { label: '出科', value: 'out_dept' },
  ]
  const variableOptions = variableCatalog.map((v) => ({ label: `${v.label}`, value: v.field }))
  const continuousVariableOptions = computed(() => variableCatalog.filter((v) => v.type === 'continuous').map((v) => ({ label: v.label, value: v.field })))
  const binaryVariableOptions = computed(() => variableCatalog.filter((v) => v.type === 'binary').map((v) => ({ label: v.label, value: v.field })))
  const correlationVariableOptions = computed(() => variableCatalog
    .filter((v) => v.type === 'continuous')
    .map((v) => {
      const summary = getVarSummary(v.field)
      const nonNull = Number(summary.non_null_count || 0)
      const total = Number(summary.total_count || selectedPatientIds.value.length || 0)
      return { label: `${v.label} (${nonNull}/${total})`, value: v.field }
    }))
  const trendIndicatorOptions = computed(() => {
    const fromSelected = selectedVariables.value
      .filter((field) => variableCatalog.find((item) => item.field === field)?.type === 'continuous')
      .map((field) => ({ label: variableCatalog.find((item) => item.field === field)?.label || field, value: field }))
    const vitals = [
      { label: '心率', value: 'hr' }, { label: '平均动脉压', value: 'map' },
      { label: '乳酸', value: 'lactate' }, { label: '收缩压', value: 'sbp' },
      { label: '舒张压', value: 'dbp' }, { label: '呼吸频率', value: 'rr' },
      { label: '血氧饱和度', value: 'spo2' }, { label: '体温', value: 'temperature' },
    ]
    const map = new Map<string, { label: string; value: string }>()
    ;[...fromSelected, ...vitals].forEach((item) => { if (item?.value && !map.has(item.value)) map.set(item.value, item) })
    return Array.from(map.values())
  })
  const timeFieldOptions = [{ label: 'ICU住院天数', value: 'los_icu_days' }]
  const eventFieldOptions = [
    { label: 'ICU死亡', value: 'icu_mortality' },
    { label: '院内死亡', value: 'hospital_mortality' },
    { label: '28天死亡', value: 'mortality_28d' },
  ]

  /* ───── 工具函数 ───── */
  function patientScopeLabel(scopeValue?: string | null): string {
    return ({ in_dept: '在科', out_dept: '出科', all: '全部' } as Record<string, string>)[String(scopeValue || 'all')] || '全部'
  }
  function typeLabelCN(type: string): string {
    return ({ continuous: '连续变量', categorical: '分类变量', binary: '二分类变量' } as Record<string, string>)[type] || '变量'
  }
  function variableTypeBadge(type: string): string {
    return ({ continuous: '连续', categorical: '分类', binary: '二分' } as Record<string, string>)[type] || '变量'
  }
  function applicableLabel(list?: string[]): string {
    if (!Array.isArray(list) || !list.length) return ''
    const map: Record<string, string> = { table1: '基线', survival: '生存', regression: '回归', roc: 'ROC', subgroup: '亚组', trend: '趋势', correlation: '相关' }
    return list.map((item) => map[item] || item).join(' ')
  }
  function apiErrorMessage(error: any, fallback: string): string {
    const detail = error?.response?.data?.detail || error?.message || ''
    if (String(detail).toLowerCase().includes('timeout')) return '请求超时：任务可能仍在后台执行'
    return detail || fallback
  }
  function getVarSummary(field: string): AnyRecord { return (variableSummaries.value || {})[field] || {} }
  function variableMeta(field: string) { return variableCatalog.find((item) => item.field === field) }
  function analysisLabel(field: string): string { return variableMeta(field)?.label || field }
  function analysisTitle(key: string): string {
    return ({ table1: '基线特征表', survival: '生存分析', regression: '回归分析', roc: 'ROC分析', subgroup: '亚组分析', trend: '趋势分析', correlation: '相关性分析' } as Record<string, string>)[key] || key
  }
  function correlationMethodLabel(method: string): string {
    return ({ auto: '自动选择', pearson: '皮尔逊', spearman: '斯皮尔曼' } as Record<string, string>)[String(method || '').toLowerCase()] || method
  }

  /* ───── 平台标签 ───── */
  function platformKindLabel(v: any): string { return ({ analytics: '统计分析', export: '数据导出', artifact: '导出产物', research: '科研任务' } as any)[String(v || '').toLowerCase()] || '科研任务' }
  function platformStatusLabel(v: any): string { return ({ pending: '待执行', queued: '排队中', processing: '执行中', running: '执行中', completed: '已完成', success: '已完成', failed: '失败', error: '失败', cancelled: '已取消' } as any)[String(v || '').toLowerCase()] || '状态待确认' }
  function platformSourceLabel(v: any): string { return ({ research_export_tasks: '科研导出任务', research_analytics_tasks: '科研分析任务', research: '科研平台' } as any)[String(v || '').toLowerCase()] || '科研平台' }
  function platformArtifactTypeLabel(v: any): string { return ({ export_bundle: '导出包', figure: '图表', table: '表格', csv: '电子表格', zip: '压缩包' } as any)[String(v || '').toLowerCase()] || '产物' }
  function platformModuleLabel(v: any): string { return ({ sklearn: '统计依赖', scipy: '科学计算', pandas: '数据表', numpy: '数值计算', lifelines: '生存分析', matplotlib: '图表' } as any)[String(v || '').toLowerCase()] || v || '依赖' }
  function platformJobTitle(item: AnyRecord): string { return analysisTitle(String(item?.task_type || item?.kind || '')) }
  function platformArtifactTitle(item: AnyRecord): string { return String(item?.title || '').trim() || platformArtifactTypeLabel(item?.artifact_type) }
  function platformAnalysisLabel(v: any): string { return analysisTitle(String(v || '')) }

  /* ───── 患者/队列 ───── */
  function patientIds(): string[] { return Array.from(new Set(String(scope.patient_text || '').split(/[\n,;\s]+/g).map((x) => x.trim()).filter(Boolean))) }
  function scopedPatientIds(): string[] {
    const ids = (selectedPatientIds.value || []).map((x) => String(x || '').trim()).filter(Boolean)
    return ids.length ? Array.from(new Set(ids)) : patientIds()
  }
  function scopePayload() {
    return {
      patient_ids: scopedPatientIds(), cohort_id: scope.cohort_id || null,
      department: scope.department || null, dept_code: currentDeptCode.value || null,
      patient_scope: scope.patient_scope,
    }
  }
  function variablePayload() {
    return scope.variables.map((f) => variableCatalog.find((v) => v.field === f)).filter(Boolean).map((v) => ({ field: v!.field, label: v!.label, type: v!.type }))
  }

  /* ───── 变量筛选 ───── */
  function filterFieldAlias(field: string): string {
    return ({ sofa_admission: 'sofa_max', apache2: 'apache2_max', primary_diagnosis: 'diagnosis', icu_mortality: 'outcome' } as Record<string, string>)[field] || field
  }
  function inverseFilterField(field: string): string {
    return ({ sofa_max: 'sofa_admission', apache2_max: 'apache2', diagnosis: 'primary_diagnosis', outcome: 'icu_mortality' } as Record<string, string>)[field] || field
  }
  function clearAllVariableFilters(resetDraft = false): void {
    Object.keys(appliedVariableFilters).forEach((key) => delete appliedVariableFilters[key])
    if (resetDraft) Object.keys(variableFilterDrafts).forEach((key) => delete variableFilterDrafts[key])
    expandedVariableField.value = ''
  }
  function seedDraft(_field: string): AnyRecord { return { mode: 'none', min: null, max: null, selected: [] as string[] } }
  function draftFilter(field: string): AnyRecord {
    if (!variableFilterDrafts[field]) variableFilterDrafts[field] = seedDraft(field)
    return variableFilterDrafts[field]
  }
  function hasVariableFilter(field: string): boolean { return Boolean(appliedVariableFilters[field]) }
  function filterSummary(field: string): string { return String(appliedVariableFilters[field]?.summary || '') }
  function isVariableSelected(field: string): boolean { return selectedVariables.value.includes(field) }
  function toggleVariable(field: string): void { researchSelectionStore.toggleVariable(field) }
  function selectAllVariables(): void { researchSelectionStore.setSelectedVariables(variableCatalog.map((v) => v.field)) }
  function clearAllVariables(): void { researchSelectionStore.clearSelectedVariables() }
  function toggleCategory(category: string): void {
    const fields = variableCatalog.filter((v) => v.category === category).map((v) => v.field)
    const allSelected = fields.every((field) => selectedVariables.value.includes(field))
    if (allSelected) {
      researchSelectionStore.setSelectedVariables(selectedVariables.value.filter((field) => !fields.includes(field)))
      categoryFlash[category] = '已清空'
    } else {
      researchSelectionStore.selectVariables(fields)
      categoryFlash[category] = '已全选'
    }
    setTimeout(() => { categoryFlash[category] = '' }, 1000)
  }
  function toggleVariablePanel(field: string): void {
    if (expandedVariableField.value === field) { expandedVariableField.value = ''; return }
    const applied = appliedVariableFilters[field]
    variableFilterDrafts[field] = applied ? { ...applied, selected: [...(applied.selected || [])] } : seedDraft(field)
    expandedVariableField.value = field
  }
  function disableAutoSync(key: 'regression' | 'roc' | 'trend' | 'correlation'): void { analysisAutoSync[key] = false }

  /* ───── 队列操作 ───── */
  function togglePrepMode(mode: 'saved' | 'dept' | 'builder'): void { prepMode.value = prepMode.value === mode ? '' : mode }
  function openCohortBuilder(): void { prepMode.value = 'builder'; cohortBuilderOpen.value = true }
  function onCohortBuilderSaved(payload: { cohort: AnyRecord; filters: AnyRecord[] }): void {
    const data = payload.cohort || {}
    const ids = Array.isArray(data.patient_ids) ? data.patient_ids.map((id: any) => String(id || '')).filter(Boolean) : []
    cohortSourceFilters.value = Array.isArray(payload.filters) ? payload.filters : []
    basePatientIds.value = [...ids]
    originalCohortCount.value = ids.length
    scope.patient_text = ids.join('\n')
    scope.cohort_id = data.cohort_id || scope.cohort_id
    prepMode.value = 'builder'
    researchSelectionStore.setCohort({ id: data.cohort_id || null, name: data.name || '自定义队列', type: 'builder', patientCount: ids.length, department: scope.department || currentDeptName.value || null, deptCode: currentDeptCode.value || null, patientScope: scope.patient_scope })
  }
  async function removeCohort(cohortId: string): Promise<void> {
    if (!cohortId) return
    Modal.confirm({
      title: '删除队列', content: '确认删除该队列吗？',
      onOk: async () => {
        try { await deleteResearchCohort(cohortId); cohorts.value = cohorts.value.filter((item) => item.cohort_id !== cohortId); message.success('队列已删除') } catch (e: any) { message.error(apiErrorMessage(e, '删除失败')) }
      },
    })
  }

  /* ───── 变量摘要 ───── */
  async function fetchVariableSummary(silent = false) {
    const ids = selectedPatientIds.value
    const seq = ++summaryFetchSeq
    if (!ids.length) { researchSelectionStore.setVariableSummaries({}); return }
    try {
      const res = await postResearchVariableSummary({ patient_ids: ids, fields: variableCatalog.map((v) => v.field) })
      const summaries = res.data?.summaries || res.data || {}
      const mapped: Record<string, AnyRecord> = {}
      variableCatalog.forEach((item) => { mapped[item.field] = summaries[item.field] || {} })
      if (seq !== summaryFetchSeq) return
      researchSelectionStore.setVariableSummaries(mapped)
    } catch (e: any) { if (!silent) message.warning(apiErrorMessage(e, '变量摘要加载失败')) }
  }

  /* ───── 患者加载 ───── */
  async function loadPatientsByDepartment() {
    const deptCode = String(currentDeptCode.value || '').trim()
    const deptName = String(currentDeptName.value || routeDeptName.value || '').trim()
    if (!deptCode && !deptName) { message.warning('未检测到科室信息'); return }
    patientLoadLoading.value = true
    try {
      const params: AnyRecord = { patient_scope: scope.patient_scope }
      if (deptCode) params.dept_code = deptCode; else params.dept = deptName
      const res = await getPatients(params)
      const list: AnyRecord[] = Array.isArray(res.data?.patients) ? res.data.patients : []
      if (list.length && deptCode && !deptNameByCode.value[deptCode]) {
        const name = String(list[0]?.hisDept || list[0]?.dept || '').trim()
        if (name) deptNameByCode.value[deptCode] = name
      }
      const ids = list.map((row) => row?._id || row?.patient_id || row?.patientId || row?.hisPid || row?.pid).map((id) => String(id || '').trim()).filter(Boolean)
      basePatientIds.value = [...ids]
      originalCohortCount.value = ids.length
      cohortSourceFilters.value = []
      clearAllVariableFilters(true)
      scope.patient_text = ids.join('\n')
      cohortPreviewCount.value = ids.length
      researchSelectionStore.setCohort({ id: null, name: `${currentDeptDisplay.value} ${patientScopeLabel(scope.patient_scope)}患者`, type: 'dept', patientCount: ids.length, department: currentDeptName.value || deptName || null, deptCode: currentDeptCode.value || null, patientScope: scope.patient_scope })
      await fetchVariableSummary()
      if (ids.length) message.success(`已载入 ${ids.length} 名患者`)
      else message.info('当前科室暂无患者')
    } catch (e: any) { message.error(apiErrorMessage(e, '患者加载失败')) } finally { patientLoadLoading.value = false }
  }

  /* ───── 队列选择 ───── */
  function applyCohortSelection(cohortId: string | null | undefined) {
    const token = String(cohortId || '').trim()
    if (!token) return
    const matched = cohorts.value.find((item) => String(item.cohort_id) === token || String(item._id) === token)
    if (!matched) return
    cohortSourceFilters.value = Array.isArray(matched.filters) ? matched.filters : []
    const ids = patientIdsFromRow(matched)
    basePatientIds.value = [...ids]
    originalCohortCount.value = ids.length
    if (ids.length) scope.patient_text = ids.join('\n')
    scope.patient_scope = ['in_dept', 'out_dept', 'all'].includes(String(matched.patient_scope || '')) ? matched.patient_scope : 'all'
    researchSelectionStore.setCohort({ id: token, name: matched.name || matched.cohort_id || '自定义队列', type: 'saved', patientCount: ids.length, department: matched.department || null, deptCode: matched.dept_code || null, patientScope: scope.patient_scope })
    fetchVariableSummary(true)
  }
  function patientIdsFromRow(row: AnyRecord | undefined): string[] {
    if (!row) return []
    for (const pool of [row.patient_ids, row.patients, row.members]) {
      if (Array.isArray(pool) && pool.length) return pool.map((id: any) => String(id || '').trim()).filter(Boolean)
    }
    return []
  }

  /* ───── 分析执行 ───── */
  async function resolveResult(req: Promise<any>): Promise<any> {
    const res = await req; const data = res?.data || {}
    if (data.async && data.task_id) {
      message.info('后台计算中...')
      for (let i = 0; i < 120; i++) {
        const s = await getResearchAnalyticsTaskStatus(String(data.task_id)); const row = s.data || {}
        if (row.status === 'completed') return row.result || {}
        if (row.status === 'failed') throw new Error(row.error || '任务失败')
        await new Promise((r) => setTimeout(r, 1500))
      }
      throw new Error('任务超时')
    }
    return data.result || data
  }

  async function runTable1() {
    loading.table1 = true
    try {
      table1Result.value = await resolveResult(postResearchTable1({ ...scopePayload(), group_by: scope.group_by, variables: variablePayload() }))
      openConfigKeys.table1 = []; message.success('基线特征表完成')
    } catch (e: any) { message.error(apiErrorMessage(e, '基线特征表失败')) } finally { loading.table1 = false }
  }
  async function runSurvival() {
    loading.survival = true
    try { survivalResult.value = await resolveResult(postResearchSurvival({ ...scopePayload(), ...survivalForm })); message.success('生存分析完成') }
    catch (e: any) { message.error(apiErrorMessage(e, '生存分析失败')) } finally { loading.survival = false }
  }
  async function runRegression() {
    loading.regression = true
    try {
      const predictors = Array.from(new Set((regressionForm.predictors || []).filter(Boolean)))
      if (!predictors.length) { message.warning('请选择预测变量'); return }
      regressionResult.value = await resolveResult(postResearchRegression({ ...scopePayload(), outcome: regressionForm.outcome, outcome_type: regressionForm.outcome_type, predictors, confounders: regressionForm.confounders || [] }))
      message.success('回归分析完成')
    } catch (e: any) { message.error(apiErrorMessage(e, '回归分析失败')) } finally { loading.regression = false }
  }
  async function runRoc() {
    loading.roc = true
    try {
      const predictors = Array.from(new Set((rocForm.predictors || []).filter(Boolean)))
      if (!predictors.length) { message.warning('请选择预测指标'); return }
      rocResult.value = await resolveResult(postResearchRoc({ ...scopePayload(), outcome: rocForm.outcome, predictors }))
      message.success('ROC 分析完成')
    } catch (e: any) { message.error(apiErrorMessage(e, 'ROC 分析失败')) } finally { loading.roc = false }
  }
  async function runTrend() {
    loading.trend = true
    try {
      const indicators = Array.from(new Set((trendForm.indicators || []).filter(Boolean)))
      if (!indicators.length) { message.warning('请选择指标'); return }
      trendResult.value = await resolveResult(postResearchTrend({ ...scopePayload(), indicators, group_by: scope.group_by || null, time_reference: trendForm.time_reference, time_range_hours: trendForm.time_range_hours, interval_hours: trendForm.interval_hours }))
      message.success('趋势分析完成')
    } catch (e: any) { message.error(apiErrorMessage(e, '趋势分析失败')) } finally { loading.trend = false }
  }
  async function runSubgroup() {
    const enabled = subgroupForm.subgroups.filter((s) => s.enabled)
    if (!enabled.length) { message.warning('请至少开启一个亚组'); return }
    loading.subgroup = true
    try {
      subgroupResult.value = await resolveResult(postResearchSubgroup({ ...scopePayload(), exposure: subgroupForm.exposure, outcome: subgroupForm.outcome, outcome_type: subgroupForm.outcome_type, subgroups: enabled.map((s) => ({ name: s.label, filter: JSON.parse(s.filterText) })) }))
      message.success('亚组分析完成')
    } catch (e: any) { message.error(apiErrorMessage(e, '亚组分析失败')) } finally { loading.subgroup = false }
  }
  async function runCorrelation() {
    loading.correlation = true
    try {
      const variables = Array.from(new Set((correlationForm.variables || []).filter(Boolean)))
      if (variables.length < 2) { message.warning('至少需要2个变量'); return }
      correlationResult.value = await resolveResult(postResearchCorrelation({ ...scopePayload(), variables, method: correlationForm.method }))
      message.success('相关性分析完成')
    } catch (e: any) { message.error(apiErrorMessage(e, '相关性分析失败')) } finally { loading.correlation = false }
  }

  /* ───── 导出 ───── */
  function addExport(row: AnyRecord, title: string, folder: string) { exports.value.unshift({ ...row, title, arcname: `${folder}/${row.file_name || ''}` }) }
  async function exportFigure(chartType: string) {
    const dataMap: Record<string, AnyRecord | null> = { survival: survivalResult.value, regression: regressionResult.value, roc: rocResult.value, subgroup: subgroupResult.value, trend: trendResult.value, correlation: correlationResult.value }
    const result = dataMap[chartType]; if (!result) return
    try { const res = await postResearchExportFigure({ chart_type: chartType, result, format: 'png', width_mode: 'double', filename: `${chartType}_${Date.now()}.png` }); addExport(res.data || {}, `${analysisTitle(chartType)}图`, 'figures'); message.success('导出成功') }
    catch (e: any) { message.error(apiErrorMessage(e, '导出失败')) }
  }
  async function exportTable() {
    if (!table1Result.value) return
    try { const res = await postResearchExportTable({ title: table1Result.value.title || '基线特征表', table_data: table1Result.value, format: 'docx', filename: `table1_${Date.now()}` }); addExport(res.data || {}, '基线特征表', 'tables'); message.success('导出成功') }
    catch (e: any) { message.error(apiErrorMessage(e, '导出失败')) }
  }
  async function exportTableCsv() {
    if (!table1Result.value) return
    try { const res = await postResearchExportTable({ title: table1Result.value.title || '基线特征表', table_data: table1Result.value, format: 'csv', filename: `table1_${Date.now()}` }); addExport(res.data || {}, '基线特征表(表格)', 'tables'); message.success('导出成功') }
    catch (e: any) { message.error(apiErrorMessage(e, '导出失败')) }
  }

  /* ───── 会话 ───── */
  async function saveSession() {
    sessionLoading.value = true
    try {
      await saveResearchSession({ name: `科研分析_${new Date().toLocaleString('zh-CN')}`, payload: { tab: tab.value, scope: { ...scope }, forms: { survivalForm: { ...survivalForm }, regressionForm: { ...regressionForm }, rocForm: { ...rocForm }, subgroupForm: { ...subgroupForm }, trendForm: { ...trendForm }, correlationForm: { ...correlationForm } }, results: { table1: table1Result.value, survival: survivalResult.value, regression: regressionResult.value, roc: rocResult.value, subgroup: subgroupResult.value, trend: trendResult.value, correlation: correlationResult.value }, exports: exports.value } })
      message.success('会话已保存'); await loadSessions()
    } catch (e: any) { message.error(apiErrorMessage(e, '保存失败')) } finally { sessionLoading.value = false }
  }
  async function loadSessions() {
    sessionListLoading.value = true; sessionListError.value = ''
    try { const res = await listResearchSessions({ limit: 50 }); sessions.value = Array.isArray(res.data?.sessions) ? res.data.sessions : [] }
    catch (e: any) { sessions.value = []; sessionListError.value = apiErrorMessage(e, '加载失败') } finally { sessionListLoading.value = false }
  }
  async function restoreSession(sessionId: string) {
    if (!sessionId) return
    try {
      const res = await getResearchSession(sessionId); const p = (res.data?.payload || {}) as AnyRecord
      if (p.tab) tab.value = String(p.tab)
      if (p.scope) Object.assign(scope, p.scope)
      if (p.forms?.survivalForm) Object.assign(survivalForm, p.forms.survivalForm)
      if (p.forms?.regressionForm) Object.assign(regressionForm, p.forms.regressionForm)
      if (p.forms?.rocForm) Object.assign(rocForm, p.forms.rocForm)
      if (p.forms?.subgroupForm) Object.assign(subgroupForm, p.forms.subgroupForm)
      if (p.forms?.trendForm) Object.assign(trendForm, p.forms.trendForm)
      if (p.forms?.correlationForm) Object.assign(correlationForm, p.forms.correlationForm)
      if (p.results) { table1Result.value = p.results.table1 || null; survivalResult.value = p.results.survival || null; regressionResult.value = p.results.regression || null; rocResult.value = p.results.roc || null; subgroupResult.value = p.results.subgroup || null; trendResult.value = p.results.trend || null; correlationResult.value = p.results.correlation || null }
      exports.value = Array.isArray(p.exports) ? p.exports : []
      message.success('会话已恢复')
    } catch (e: any) { message.error(apiErrorMessage(e, '恢复失败')) }
  }

  /* ───── 平台 ───── */
  async function loadPlatformStatus() {
    platformStatusLoading.value = true; platformStatusError.value = ''
    try { const res = await getResearchPlatformStatus(); platformStatus.value = res.data?.status || null }
    catch (e: any) { platformStatus.value = null; platformStatusError.value = apiErrorMessage(e, '加载失败') } finally { platformStatusLoading.value = false }
  }
  async function runPlatformCheck() {
    platformStatusLoading.value = true
    try { const res = await postResearchPlatformCheck(); platformStatus.value = res.data?.status || null; message.success('自检完成'); await Promise.allSettled([loadPlatformJobs(), loadPlatformArtifacts()]) }
    catch (e: any) { message.error(apiErrorMessage(e, '自检失败')) } finally { platformStatusLoading.value = false }
  }
  async function loadPlatformJobs() {
    researchJobsLoading.value = true; researchJobsError.value = ''
    try { const res = await getResearchPlatformJobs({ limit: 50 }); researchJobs.value = Array.isArray(res.data?.rows) ? res.data.rows : []; researchJobsSummary.value = res.data?.summary || {} }
    catch (e: any) { researchJobs.value = []; researchJobsError.value = apiErrorMessage(e, '加载失败') } finally { researchJobsLoading.value = false }
  }
  async function loadPlatformArtifacts() {
    researchArtifactsLoading.value = true; researchArtifactsError.value = ''
    try { const res = await getResearchPlatformArtifacts({ limit: 50 }); researchArtifacts.value = Array.isArray(res.data?.rows) ? res.data.rows : [] }
    catch (e: any) { researchArtifacts.value = [] } finally { researchArtifactsLoading.value = false }
  }
  async function loadTopicStatuses() {
    topicStatusLoading.value = true
    try {
      const [resp, mdro] = await Promise.all([getResearchRespiratoryForecastStatus({ limit: 20 }).catch(() => ({ data: {} })), getResearchMdroControlSummary({ limit: 20 }).catch(() => ({ data: {} }))])
      respiratoryForecastStatus.value = resp.data || {}; mdroControlSummary.value = mdro.data || {}
    } finally { topicStatusLoading.value = false }
  }
  async function loadDeptNameMap() {
    try {
      const res = await getDepartments(); const rows = Array.isArray(res.data?.departments) ? res.data.departments : []
      const next: Record<string, string> = { ...deptNameByCode.value }
      rows.forEach((row: AnyRecord) => {
        const code = String(row?.deptCode || row?.code || row?.dept_code || '').trim()
        const name = String(row?.dept || row?.name || '').trim()
        if (code && name) next[code] = name
      })
      deptNameByCode.value = next
    } catch { /* ignore */ }
  }
  async function loadCohorts() {
    try { const res = await listResearchCohorts({ limit: 200 }); cohorts.value = Array.isArray(res.data?.cohorts) ? res.data.cohorts : [] } catch { cohorts.value = [] }
  }

  /* ───── 监听 ───── */
  watch(() => scope.cohort_id, (val) => applyCohortSelection(val))
  watch(patientIdsVersion, () => { fetchVariableSummary(true) }, { immediate: true })
  watch(cohorts, () => { if (scope.cohort_id) applyCohortSelection(scope.cohort_id) })
  watch(selectedPatientIds, (ids) => { cohortPreviewCount.value = ids.length })
  watch(() => scope.patient_text, () => { researchSelectionStore.setPatientIds(patientIds()) }, { immediate: true })
  watch(selectedVariables, (val) => {
    scope.variables = [...val]
    const continuous = val.filter((field) => variableCatalog.find((v) => v.field === field)?.type === 'continuous')
    if (analysisAutoSync.regression) regressionForm.predictors = [...val]
    if (analysisAutoSync.roc) rocForm.predictors = [...continuous]
    if (analysisAutoSync.correlation) correlationForm.variables = [...continuous]
  }, { immediate: true })
  watch(prepMode, (mode) => {
    if (mode === 'dept') { scope.cohort_id = ''; cohortSourceFilters.value = []; clearAllVariableFilters(true); loadPatientsByDepartment(); return }
    if (!mode) { scope.cohort_id = ''; scope.patient_text = ''; basePatientIds.value = []; originalCohortCount.value = 0; cohortPreviewCount.value = 0; cohortSourceFilters.value = []; clearAllVariableFilters(true); researchSelectionStore.setCohort(null) }
  }, { immediate: true })
  watch(() => scope.patient_scope, async (val, oldVal) => { if (val !== oldVal && prepMode.value === 'dept') await loadPatientsByDepartment() })
  watch(openSessionDrawer, (val) => { if (val) void loadSessions() })

  return {
    // 状态
    tab, cohorts, cohortPreviewCount, patientLoadLoading, deptNameByCode, prepMode,
    cohortBuilderOpen, categoryFlash, expandedVariableField, basePatientIds,
    originalCohortCount, cohortSourceFilters, scope, loading,
    table1Result, survivalResult, regressionResult, rocResult, subgroupResult, trendResult, correlationResult, exports,
    survivalForm, regressionForm, rocForm, subgroupForm, trendForm, correlationForm, openConfigKeys,
    ai, aiPlanner, openSessionDrawer, sessionLoading, sessionListLoading, sessionListError, sessions,
    platformStatus, platformStatusLoading, platformStatusError,
    researchJobs, researchJobsSummary, researchJobsLoading, researchJobsError,
    researchArtifacts, researchArtifactsLoading, researchArtifactsError,
    respiratoryForecastStatus, mdroControlSummary, topicStatusLoading, topicTabs,
    icdSearch, appliedVariableFilters, variableFilterDrafts, analysisAutoSync,
    // Store
    selectedVariables, variableSummaries, selectedPatientIds, selectionCohort,
    // 路由
    routeDeptCode, routeDeptName, currentDeptCode, currentDeptName, currentDeptDisplay,
    // 计算属性
    cohortReady, appliedFilterCount, currentCohortSummary, variableGroups, cohortOptions,
    navCompletion, groupSummaryCards,
    groupByOptions, patientScopeOptions, variableOptions, continuousVariableOptions,
    binaryVariableOptions, correlationVariableOptions, trendIndicatorOptions,
    timeFieldOptions, eventFieldOptions,
    // 工具函数
    patientScopeLabel, typeLabelCN, variableTypeBadge, applicableLabel, apiErrorMessage,
    getVarSummary, variableMeta, analysisLabel, analysisTitle, correlationMethodLabel,
    platformKindLabel, platformStatusLabel, platformSourceLabel, platformArtifactTypeLabel,
    platformModuleLabel, platformJobTitle, platformArtifactTitle, platformAnalysisLabel,
    // 操作
    patientIds, scopedPatientIds, scopePayload, variablePayload,
    filterFieldAlias, inverseFilterField, clearAllVariableFilters, seedDraft, draftFilter,
    hasVariableFilter, filterSummary, isVariableSelected, toggleVariable, selectAllVariables,
    clearAllVariables, toggleCategory, toggleVariablePanel, disableAutoSync,
    togglePrepMode, openCohortBuilder, onCohortBuilderSaved, removeCohort,
    fetchVariableSummary, loadPatientsByDepartment, applyCohortSelection, patientIdsFromRow,
    runTable1, runSurvival, runRegression, runRoc, runTrend, runSubgroup, runCorrelation,
    addExport, exportFigure, exportTable, exportTableCsv,
    saveSession, loadSessions, restoreSession,
    loadPlatformStatus, runPlatformCheck, loadPlatformJobs, loadPlatformArtifacts,
    loadTopicStatuses, loadDeptNameMap, loadCohorts,
  }
}
