/**
 * useAcademicResearch — 学术科研支撑逻辑
 *
 * 提取 AcademicResearchDashboard.vue 的状态、API 调用和计算属性。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getDataQuality,
  getResearchProjects,
  getTopicSuggestions,
  postGenerateTopicSuggestions,
  postOmopExport,
  postResearchProject,
  type ResearchScopeParams,
} from '../api/researchSupport'
import { getDepartments } from '../api'
import { useAuthStore } from '../stores/auth'

export function useAcademicResearch() {
  const route = useRoute()
  const auth = useAuthStore()

  /* ───── 基础状态 ───── */
  const deptNameByCode = ref<Record<string, string>>({})
  const loading = ref(false)
  const topicLoading = ref(false)
  const omopLoading = ref(false)
  const saving = ref(false)
  const drawerOpen = ref(false)

  /* ───── 数据 ───── */
  const projects = ref<any[]>([])
  const portfolio = ref<any>({})
  const topics = ref<any[]>([])
  const quality = ref<any>({})
  const governance = ref<any[]>([])
  const topicIsFallback = ref(false)

  /* ───── 表单 ───── */
  const form = reactive<any>({
    title: '',
    type: '课题',
    owner: '',
    status: '计划中',
    journal_or_funding_source: '',
    remarks: '',
  })

  /* ───── 选项 ───── */
  const typeOptions = ['论文', '课题', '基金', '伦理', '专利', '指南共识'].map((value) => ({ value, label: value }))
  const statusOptions = ['计划中', '进行中', '投稿中', '已发表', '结题'].map((value) => ({ value, label: value }))

  /* ───── 路由参数 ───── */
  const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim())
  const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
  const resolvedDeptName = computed(() => deptNameByCode.value[routeDeptCode.value] || '')
  const scopeLabel = computed(() => routeDeptName.value || resolvedDeptName.value || routeDeptCode.value || '全部 ICU 患者')

  const researchScopeParams = computed<ResearchScopeParams>(() => {
    const params: ResearchScopeParams = { patient_scope: routeDeptCode.value || routeDeptName.value ? 'in_dept' : 'all' }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDeptName.value) params.department = routeDeptName.value
    return params
  })

  /* ───── 计算属性 ───── */
  const missingRows = computed(() => Object.entries(quality.value?.missing_rate || {}).map(([field, rate]) => ({ field, rate: `${Math.round(Number(rate) * 100)}%` })))
  const topicSourceLabel = computed(() => topicIsFallback.value ? '系统内置兜底建议' : 'AI / 数据摘要生成')
  const statusRows = computed(() => Object.entries(portfolio.value?.by_status || {}).map(([key, value]) => ({ key, value })))
  const milestones = computed(() => portfolio.value?.upcoming_milestones || [])

  /* ───── 翻译映射 ───── */
  const titleMap: Record<string, string> = {
    'Prone Positioning Effectiveness in ARDS Patients': 'ARDS 患者俯卧位治疗效果研究',
    'Prone Positioning Efficacy in ARDS Patients within the ICU': 'ICU 内 ARDS 患者俯卧位疗效研究',
    'Compliance with Sepsis 3-Hour Bundle and Patient Outcomes': '脓毒症 3 小时救治清单依从性与预后研究',
    'Sepsis Bundle Compliance and Patient Outcomes': '脓毒症救治清单依从性与患者结局研究',
    'High Driving Pressure as a Predictor of Ventilator-Associated Lung Injury': '高驱动压暴露预测呼吸机相关肺损伤研究',
    'Impact of High Driving Pressure on Ventilator-Associated Outcomes': '高驱动压对机械通气相关结局的影响研究',
    'Impact of Data Quality Issues on Quality-Signal Reporting Accuracy': '数据质量问题对重症质控信号准确性的影响研究',
  }
  const questionMap: Record<string, string> = {
    'Does early prone positioning improve 28-day mortality among ICU patients diagnosed with ARDS?': '早期俯卧位治疗是否改善 ARDS ICU 患者 28 天结局？',
    'Does early implementation of prone positioning improve 28-day mortality among ARDS patients identified by ARDS/prone related alerts?': '对 ARDS 或俯卧位相关预警患者，早期实施俯卧位是否可降低 28 天全因死亡率？',
    'Is higher compliance with the sepsis care bundle associated with reduced ICU mortality among patients flagged by sepsis bundle alerts?': '在脓毒症救治清单预警患者中，更高的清单依从性是否与 ICU 死亡率下降相关？',
    'Does exposure to high driving pressure (>15 cmH₂O) increase the risk of ventilator-associated lung injury and mortality in ICU patients?': 'ICU 患者暴露于高驱动压（>15 cmH₂O）是否增加呼吸机相关肺损伤和死亡风险？',
    'Does exposure to high driving pressure (>15 cmH2O) increase the risk of ventilator-associated lung injury and mortality in ICU patients?': 'ICU 患者暴露于高驱动压（>15 cmH2O）是否增加呼吸机相关肺损伤和死亡风险？',
  }
  const studyDesignMap: Record<string, string> = {
    'Retrospective cohort study': '回顾性队列研究',
    'Retrospective cohort': '回顾性队列研究',
    'Retrospective case-control study': '回顾性病例对照研究',
    'Retrospective cross-sectional analysis': '回顾性横断面分析',
    'Quality improvement project': '质量改进项目',
    'QI project': '质量改进项目',
  }
  const outcomeMap: Record<string, string> = {
    '28-day all-cause mortality': '28 天全因死亡率',
    'ICU mortality': 'ICU 死亡率',
    'Mortality during ICU stay': 'ICU 期间死亡率',
    'Ventilator-associated lung injury': '呼吸机相关肺损伤',
  }
  const ethicalRiskMap: Record<string, string> = {
    'Low risk, using existing anonymized clinical data, no intervention required.': '低风险，使用既往匿名化临床数据，无需干预。',
    'Low risk, based on observational study using existing data.': '低风险，基于既往数据的观察性研究。',
    'Low to moderate risk; requires protection of respiratory parameters integrity; if key variables are missing, analysis may be limited.': '低至中等风险，需确保呼吸机参数完整性；若关键变量缺失，分析能力会受限。',
  }
  const fieldMap: Record<string, string> = {
    _id: '患者主键', hisPid: 'HIS 患者号', derived_age: '年龄', birthday: '出生日期',
    gender_combined: '性别', clinicalDiagnosis: '临床诊断', icuAdmissionTime: 'ICU 入科时间',
  }

  /* ───── 翻译函数 ───── */
  function localizeTitle(text: string) { return titleMap[text] || text || '未命名课题建议' }
  function showOriginalTitle(text: string) { return Boolean(text && titleMap[text] && titleMap[text] !== text) }
  function localizeQuestion(text: string) { return questionMap[text] || text || '待明确临床问题' }
  function localizeStudyDesign(text: string) { return studyDesignMap[text] || text || '研究设计待定' }
  function localizeOutcome(text: string) { return outcomeMap[text] || text || '待 PI 确认' }
  function localizeEthicalRisk(text: string) { return ethicalRiskMap[text] || localizeText(text) || '需伦理秘书评估' }
  function localizeText(text: string) {
    if (!text) return '暂无数据依据'
    return String(text)
      .replace(/Based on\s+(\d+)\s+patients/i, '基于 $1 名患者')
      .replace(/(\d+)\s+patients/i, '$1 名患者')
      .replace(/records?/i, '条记录')
      .replace(/ARDS or prone related alerts/gi, 'ARDS 或俯卧位相关预警')
      .replace(/sepsis bundle related alerts/gi, '脓毒症救治清单相关预警')
      .replace(/high driving pressure alerts/gi, '高驱动压预警')
      .replace(/clinical diagnosis missing rate/gi, '临床诊断缺失率')
      .replace(/age and gender missing rate/gi, '年龄和性别缺失率')
      .replace(/requires further validation/i, '需要进一步验证')
      .replace('identified in the dataset', '条相关信号来自当前数据集')
      .replace('total ICU admissions', '例 ICU 入院记录')
      .replace('supports risk adjustment', '支持风险校正')
  }
  function fieldLabel(field: string) { return fieldMap[field] || field }
  function ownerLabel(value: any) {
    const text = String(value || '').trim()
    if (!text || text.toLowerCase() === 'anonymous') return '待填写'
    return text
  }
  function statusColor(status: string) {
    return status === '已发表' || status === '结题' ? 'green' : status === '投稿中' ? 'purple' : status === '进行中' ? 'blue' : 'gold'
  }
  function confidenceLabel(value: string) {
    return ({ high: '置信度较高', medium: '置信度中等', low: '置信度较低' } as any)[value] || '需人工复核'
  }

  /* ───── 表单操作 ───── */
  function resetForm() {
    Object.assign(form, { title: '', type: '课题', owner: '', status: '计划中', journal_or_funding_source: '', remarks: '' })
  }
  function openProjectDrawer() {
    resetForm()
    drawerOpen.value = true
  }
  function createProjectFromTopic(topic: any) {
    Object.assign(form, {
      title: localizeTitle(topic.title),
      type: topic.study_design?.includes('QI') || topic.study_design?.includes('质量') ? '课题' : '论文',
      owner: '',
      status: '计划中',
      journal_or_funding_source: '',
      remarks: [
        `临床问题：${localizeQuestion(topic.clinical_question)}`,
        `数据依据：${localizeText(topic.data_basis)}`,
        `主要结局：${localizeOutcome(topic.primary_outcome)}`,
        `伦理提示：${localizeEthicalRisk(topic.ethical_risk)}`,
      ].join('\n'),
    })
    drawerOpen.value = true
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
      const [p, t, q] = await Promise.all([getResearchProjects(), getTopicSuggestions(researchScopeParams.value), getDataQuality(researchScopeParams.value)])
      projects.value = p.data?.projects || []
      portfolio.value = p.data?.portfolio || {}
      topics.value = t.data?.topic_suggestions || []
      topicIsFallback.value = Boolean(t.data?.is_mock)
      quality.value = q.data?.report || {}
      governance.value = q.data?.recommendations || []
    } finally {
      loading.value = false
    }
  }

  async function generateTopics() {
    topicLoading.value = true
    try {
      const res = await postGenerateTopicSuggestions(researchScopeParams.value)
      topics.value = res.data?.topic_suggestions || []
      topicIsFallback.value = Boolean(res.data?.degraded)
      message.success(res.data?.degraded ? 'AI 暂不可用，已展示规则兜底建议' : '已生成课题建议')
    } finally {
      topicLoading.value = false
    }
  }

  async function exportOmop() {
    omopLoading.value = true
    try {
      const payload: Record<string, any> = { ...researchScopeParams.value }
      const res = await postOmopExport(payload)
      message.success(`OMOP 脱敏导出完成：${res.data?.task?.task_id || ''}`)
    } finally {
      omopLoading.value = false
    }
  }

  async function saveProject() {
    if (!form.title?.trim()) {
      message.warning('请先填写项目标题')
      return
    }
    saving.value = true
    try {
      await postResearchProject({ ...form })
      message.success('科研项目已保存')
      drawerOpen.value = false
      resetForm()
      await loadAll()
    } finally {
      saving.value = false
    }
  }

  /* ───── 初始化 ───── */
  onMounted(() => { void loadDeptNameMap(); void loadAll() })

  return {
    // 状态
    loading, topicLoading, omopLoading, saving, drawerOpen,
    projects, portfolio, topics, quality, governance, topicIsFallback,
    form, typeOptions, statusOptions,
    // 路由
    routeDeptCode, routeDeptName, scopeLabel, researchScopeParams,
    // 计算属性
    missingRows, topicSourceLabel, statusRows, milestones,
    // 翻译
    localizeTitle, showOriginalTitle, localizeQuestion, localizeStudyDesign,
    localizeOutcome, localizeEthicalRisk, localizeText, fieldLabel,
    ownerLabel, statusColor, confidenceLabel,
    // 操作
    resetForm, openProjectDrawer, createProjectFromTopic,
    loadAll, generateTopics, exportOmop, saveProject,
  }
}
