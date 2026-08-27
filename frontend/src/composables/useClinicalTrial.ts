/**
 * useClinicalTrial — 临床试验筛选逻辑
 *
 * 提取 ClinicalTrialScreening.vue 的状态、API 调用和计算属性。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Modal as AModal,
  message,
} from 'ant-design-vue'
import {
  deleteClinicalTrial,
  getClinicalTrials,
  getTrialCandidates,
  postActivateTrial,
  postCandidateStatus,
  postClinicalTrial,
  postParseCriteria,
  postScreenTrials,
  putClinicalTrial,
  type ClinicalTrialScopeParams,
} from '../api/clinicalTrials'
import { getDepartments } from '../api'
import { useAuthStore } from '../stores/auth'

export function useClinicalTrial() {
  const route = useRoute()
  const auth = useAuthStore()

  /* ───── 基础状态 ───── */
  const deptNameByCode = ref<Record<string, string>>({})
  const loading = ref(false)
  const screening = ref(false)
  const saving = ref(false)
  const demoLoading = ref(false)

  /* ───── 数据 ───── */
  const trials = ref<any[]>([])
  const candidates = ref<any[]>([])
  const lastScreenResult = ref<any>(null)

  /* ───── 抽屉/弹窗 ───── */
  const trialDrawer = ref(false)
  const parseOpen = ref(false)
  const candidateOpen = ref(false)
  const selectedTrial = ref<any>(null)
  const editingTrialId = ref('')
  const selectedCandidate = ref<any>(null)

  /* ───── 表单 ───── */
  const trialForm = reactive<any>({
    trial_name: '', registration_no: '', pi: '', status: '准备中',
    inclusionText: '[]', exclusionText: '[]',
  })
  const parseForm = reactive<any>({
    inclusion_text: '年龄 ≥18 岁；ICU 在科；诊断包含重症肺炎、脓毒症或感染性休克。',
    exclusion_text: '年龄 <18 岁；已明确拒绝研究；临终照护或治疗限制。',
  })

  /* ───── 选项 ───── */
  const statusOptions = ['准备中', '招募中', '暂停', '结束'].map((value) => ({ value, label: value }))

  /* ───── 路由参数 ───── */
  const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim())
  const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
  const resolvedDeptName = computed(() => deptNameByCode.value[routeDeptCode.value] || '')
  const scopeLabel = computed(() => routeDeptName.value || resolvedDeptName.value || routeDeptCode.value || '全部 ICU 在科患者')

  /* ───── 计算属性 ───── */
  const activeTrialCount = computed(() => trials.value.filter((trial) => trial.status === '招募中').length)
  const pendingCount = computed(() => candidates.value.filter((item) => item.status === 'pending').length)
  const candidateEmptyText = computed(() => {
    if (!trials.value.length) return '当前没有试验配置，因此无法筛选候选患者。'
    if (!activeTrialCount.value) return '已有试验但尚未启用招募，请先点击"启用招募"。'
    return '已扫描但未发现满足条件且未触发排除标准的患者，可查看规则是否过严或数据是否缺失。'
  })
  const screenDiagnosticText = computed(() => {
    const diagnostics = Array.isArray(lastScreenResult.value?.diagnostics) ? lastScreenResult.value.diagnostics : []
    const first = diagnostics.find((item: any) => item?.trial_name) || diagnostics[0]
    if (!first) return ''
    if (first.matched > 0) return `${first.trial_name || '当前试验'}已有 ${first.matched} 名患者进入候选，列表刷新后可查看。`
    const parts = []
    if (first.unmet) parts.push(`${first.unmet} 人未满足入组规则`)
    if (first.missing_only) parts.push(`${first.missing_only} 人仅缺少确认数据`)
    if (first.excluded) parts.push(`${first.excluded} 人触发排除标准`)
    return parts.length ? `${first.trial_name || '当前试验'}：${parts.join('，')}。` : ''
  })

  /* ───── 工具函数 ───── */
  function requestParams(): ClinicalTrialScopeParams {
    const params: ClinicalTrialScopeParams = { patient_scope: 'in_dept' }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDeptName.value) params.dept = routeDeptName.value
    return params
  }

  function demoRules() {
    return {
      inclusion: [
        { field: 'age', operator: 'gte', value: 18, source_text: '年龄 ≥18 岁' },
        { field: 'diagnosis', operator: 'regex', value: '肺炎|脓毒|感染|ARDS|呼吸衰竭', source_text: '诊断包含肺炎/脓毒症/ARDS/呼吸衰竭' },
      ],
      exclusion: [
        { field: 'age', operator: 'lt', value: 18, source_text: '年龄 <18 岁' },
      ],
    }
  }

  function resetForm() {
    Object.assign(trialForm, { trial_name: '', registration_no: '', pi: '', status: '准备中', inclusionText: '[]', exclusionText: '[]' })
    editingTrialId.value = ''
  }

  function openNewTrial() {
    resetForm()
    trialDrawer.value = true
  }

  function fillDemoRules() {
    const rules = demoRules()
    trialForm.inclusionText = JSON.stringify(rules.inclusion, null, 2)
    trialForm.exclusionText = JSON.stringify(rules.exclusion, null, 2)
  }

  function editTrial(row: any) {
    editingTrialId.value = row.trial_id
    Object.assign(trialForm, {
      trial_name: row.trial_name || '',
      registration_no: row.registration_no || '',
      pi: row.pi || '',
      status: row.status || '准备中',
      inclusionText: JSON.stringify(row.inclusion_rules || [], null, 2),
      exclusionText: JSON.stringify(row.exclusion_rules || [], null, 2),
    })
    trialDrawer.value = true
  }

  function statusLabel(v: string) {
    return ({
      pending: '待确认', notified: '已通知', doctor_confirmed_suitable: '医生确认适合',
      doctor_confirmed_not_suitable: '医生确认不适合', research_team_contacted: '已联系研究团队',
      enrolled: '已入组', not_enrolled: '不入组',
    } as any)[v] || v
  }

  function parseJson(text: string) {
    try {
      const v = JSON.parse(text || '[]')
      return Array.isArray(v) ? v : []
    } catch {
      message.warning('规则 JSON 格式不正确，请检查后再保存')
      return []
    }
  }

  function openCandidate(record: any) {
    selectedCandidate.value = record
    candidateOpen.value = true
  }

  function ruleText(item: any) {
    const rule = item.rule || {}
    return `${rule.source_text || rule.field || '规则'}：${item.evidence || item.actual || ''}`
  }

  /* ───── API ───── */
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
    try {
      const [t, c] = await Promise.all([getClinicalTrials(), getTrialCandidates(requestParams())])
      trials.value = t.data?.trials || []
      candidates.value = c.data?.candidates || []
    } finally {
      loading.value = false
    }
  }

  async function saveTrial() {
    if (!trialForm.trial_name?.trim()) {
      message.warning('请填写试验名称')
      return
    }
    saving.value = true
    try {
      const payload = { ...trialForm, inclusion_rules: parseJson(trialForm.inclusionText), exclusion_rules: parseJson(trialForm.exclusionText) }
      if (editingTrialId.value) await putClinicalTrial(editingTrialId.value, payload)
      else await postClinicalTrial(payload)
      message.success(editingTrialId.value ? '试验已更新' : '试验已保存')
      trialDrawer.value = false
      editingTrialId.value = ''
      await loadAll()
    } finally {
      saving.value = false
    }
  }

  function removeTrial(row: any) {
    AModal.confirm({
      title: '删除临床试验配置',
      content: `确认删除"${row.trial_name || '未命名试验'}"？候选记录不会自动入组，删除后该试验不再参与筛选。`,
      okText: '删除', okType: 'danger', cancelText: '取消',
      async onOk() {
        await deleteClinicalTrial(row.trial_id)
        message.success('试验已删除')
        await loadAll()
      },
    })
  }

  async function createDemoTrial() {
    demoLoading.value = true
    try {
      const rules = demoRules()
      const res = await postClinicalTrial({
        trial_name: '重症肺炎/脓毒症 ICU 观察性队列研究（示例）',
        registration_no: 'DEMO-ICU-SEPSIS-PNEUMONIA',
        pi: '示例 PI', department: 'ICU',
        study_type: '前瞻性观察 / 回顾性队列', status: '招募中',
        inclusion_rules: rules.inclusion, exclusion_rules: rules.exclusion,
        remarks: '示例试验用于演示规则筛选流程，请按真实伦理批件和方案修改后再用于正式提醒。',
      })
      const trialId = res.data?.trial?.trial_id
      if (trialId) await postActivateTrial(trialId)
      await postScreenTrials(requestParams())
      message.success('已创建示例试验并完成一次筛选')
      await loadAll()
    } finally {
      demoLoading.value = false
    }
  }

  async function activate(row: any) {
    await postActivateTrial(row.trial_id)
    message.success('试验已启用招募')
    await loadAll()
  }

  function openParse(row: any) {
    selectedTrial.value = row
    parseOpen.value = true
  }

  async function parseCriteria() {
    if (!selectedTrial.value) return
    await postParseCriteria(selectedTrial.value.trial_id, parseForm)
    message.success('解析草案已保存，需人工确认后启用')
  }

  async function screen() {
    screening.value = true
    try {
      const res = await postScreenTrials(requestParams())
      lastScreenResult.value = res.data || null
      const count = res.data?.candidates?.length || 0
      const scannedPatients = res.data?.scanned_patients ?? 0
      const scannedTrials = res.data?.scanned_trials ?? 0
      if (count > 0) {
        message.success(`筛选完成：扫描 ${scannedTrials} 个试验 / ${scannedPatients} 名患者，候选 ${count} 人`)
      } else {
        message.warning(`筛选完成但暂无候选：扫描 ${scannedTrials} 个试验 / ${scannedPatients} 名患者`)
      }
      await loadAll()
    } finally {
      screening.value = false
    }
  }

  async function setCandidateStatus(status: string) {
    if (!selectedCandidate.value) return
    await postCandidateStatus(selectedCandidate.value.candidate_id, { status })
    message.success('候选状态已更新')
    await loadAll()
  }

  /* ───── 监听 ───── */
  watch(() => [route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
    void loadAll()
  })

  /* ───── 初始化 ───── */
  onMounted(() => { void loadDeptNameMap(); void loadAll() })

  return {
    // 状态
    loading, screening, saving, demoLoading,
    trials, candidates, lastScreenResult,
    trialDrawer, parseOpen, candidateOpen,
    selectedTrial, editingTrialId, selectedCandidate,
    trialForm, parseForm, statusOptions,
    // 路由
    routeDeptCode, routeDeptName, scopeLabel,
    // 计算属性
    activeTrialCount, pendingCount, candidateEmptyText, screenDiagnosticText,
    // 工具函数
    requestParams, demoRules, resetForm, openNewTrial, fillDemoRules,
    editTrial, statusLabel, parseJson, openCandidate, ruleText,
    // API
    loadAll, saveTrial, removeTrial, createDemoTrial,
    activate, openParse, parseCriteria, screen, setCandidateStatus,
  }
}
