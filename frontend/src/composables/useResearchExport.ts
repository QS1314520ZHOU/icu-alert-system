/**
 * useResearchExport — 科研数据导出逻辑
 *
 * 提取 ResearchExport.vue 的状态、API 调用和计算属性。
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  createResearchExportTask,
  getDepartments,
  getResearchExportTaskStatus,
  listResearchCohorts,
  listResearchExportHistory,
  previewResearchExport,
} from '../api'

type AnyRecord = Record<string, any>

export interface ExportForm {
  cohort_id: string
  department: string
  dept_code: string
  patient_scope: string
  time_range: [any, any] | undefined
  export_mode: string
  data_types: string[]
  format: string
  desensitize: boolean
  include_data_dict: boolean
}

export function useResearchExport() {
  const route = useRoute()

  /* ───── 表单状态 ───── */
  const form = ref<ExportForm>({
    cohort_id: '',
    department: '',
    dept_code: '',
    patient_scope: 'all',
    time_range: [dayjs().subtract(30, 'day'), dayjs()],
    export_mode: 'dataset',
    data_types: ['patients', 'outcomes', 'labs'],
    format: 'csv',
    desensitize: true,
    include_data_dict: true,
  })

  /* ───── 预览 ───── */
  const preview = ref<AnyRecord | null>(null)
  const previewLoading = ref(false)

  /* ───── 提交 ───── */
  const submitting = ref(false)

  /* ───── 活跃任务 ───── */
  const activeTask = ref<AnyRecord | null>(null)

  /* ───── 历史 ───── */
  const history = ref<AnyRecord[]>([])
  const historyLoading = ref(false)
  const historyFilters = ref({ status: undefined as string | undefined, export_mode: undefined as string | undefined })

  /* ───── 部门/队列 ───── */
  const departments = ref<AnyRecord[]>([])
  const cohorts = ref<AnyRecord[]>([])
  const departmentLoading = ref(false)
  const cohortLoading = ref(false)

  /* ───── 详情抽屉 ───── */
  const detailOpen = ref(false)
  const detailTask = ref<AnyRecord | null>(null)

  /* ───── 轮询 ───── */
  let pollTimer: ReturnType<typeof setInterval> | null = null

  /* ───── 路由参数 ───── */
  const routeDeptCode = computed(() => String(route.query.deptCode || route.query.dept_code || '').trim())
  const routeDepartment = computed(() => String(route.query.dept || route.query.department || '').trim())
  const departmentLocked = computed(() => Boolean(routeDeptCode.value || routeDepartment.value))
  const matchedLockedDepartment = computed(() =>
    departments.value.find((item) =>
      (routeDeptCode.value && String(item?.deptCode || item?.code || '').trim() === routeDeptCode.value) ||
      (routeDepartment.value && String(item?.dept || '').trim() === routeDepartment.value)
    ) || null
  )
  const lockedDepartmentLabel = computed(() => {
    if (matchedLockedDepartment.value?.dept) return String(matchedLockedDepartment.value.dept)
    if (routeDepartment.value) return routeDepartment.value
    if (routeDeptCode.value) return `当前科室 (${routeDeptCode.value})`
    return '当前科室'
  })

  /* ───── 计算属性 ───── */
  const departmentOptions = computed(() => departments.value
    .filter((item) => String(item?.dept || '').trim())
    .map((item) => ({
      value: item.dept,
      label: Number(item.patientCount || 0) > 0 ? `${item.dept} (${Number(item.patientCount || 0)})` : item.dept,
    })))

  const cohortOptions = computed(() => cohorts.value.map((item) => {
    const count = Number(item.n_patients || item.patient_count || item.patient_ids?.length || 0)
    const name = item.name || item.cohort_id || '未命名队列'
    return { value: item.cohort_id, label: `${name} (${count})` }
  }))

  const progressStatus = computed(() => {
    if (!activeTask.value) return 'active'
    if (activeTask.value.status === 'completed') return 'success'
    if (activeTask.value.status === 'failed') return 'exception'
    return 'active'
  })

  const previewRows = computed(() => (preview.value?.data_type_estimates || []).map((item: AnyRecord) => ({
    ...item,
    status_text: Number(item.row_count || 0) > 0 ? '已命中' : '空',
  })))

  const previewWarnings = computed(() => Array.isArray(preview.value?.warnings) ? preview.value.warnings : [])
  const previewPatients = computed(() => Array.isArray(preview.value?.preview_patients) ? preview.value.preview_patients : [])
  const previewTotalRows = computed(() => previewRows.value.reduce((sum: number, item: AnyRecord) => sum + Number(item.row_count || 0), 0))
  const previewNonEmptyCount = computed(() => previewRows.value.filter((item: AnyRecord) => Number(item.row_count || 0) > 0).length)
  const previewEmptyLabels = computed(() => previewRows.value.filter((item: AnyRecord) => Number(item.row_count || 0) === 0).map((item: AnyRecord) => String(item.label || item.data_type || '')))
  const completedCount = computed(() => history.value.filter((item) => String(item.status) === 'completed').length)
  const processingCount = computed(() => history.value.filter((item) => ['pending', 'processing'].includes(String(item.status))).length)
  const failedCount = computed(() => history.value.filter((item) => String(item.status) === 'failed').length)

  /* ───── 工具函数 ───── */
  function patientScopeLabel(value: any): string {
    const map: Record<string, string> = { all: '全部', in_dept: '在科', out_dept: '出科' }
    return map[String(value || 'all')] || '全部'
  }

  function exportModeLabel(value: any): string {
    return String(value || '') === 'raw' ? '原始明细' : '研究数据集'
  }

  function statusLabel(status: string) {
    return {
      pending: '待处理', processing: '处理中', completed: '已完成', failed: '失败',
    }[String(status || '').toLowerCase()] || String(status || '未知')
  }

  function statusTagColor(status: string) {
    return {
      pending: 'blue', processing: 'gold', completed: 'green', failed: 'red',
    }[String(status || '').toLowerCase()] || 'default'
  }

  function formatTime(value: any) {
    if (!value) return '—'
    const parsed = dayjs(typeof value === 'string' ? value.replace('Z', '+00:00') : value)
    return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : String(value)
  }

  function taskSummaryText(record: AnyRecord) {
    const rows = Array.isArray(record?.result_stats) ? record.result_stats : []
    return rows.map((item: AnyRecord) => `${item.label || item.data_type}:${Number(item.row_count || 0)}`).join(' / ')
  }

  function serializeRange() {
    const range = form.value.time_range
    if (!Array.isArray(range) || range.length < 2 || !range[0] || !range[1]) return null
    return {
      start: range[0].format('YYYY-MM-DDTHH:mm:ss'),
      end: range[1].format('YYYY-MM-DDTHH:mm:ss'),
    }
  }

  function buildPayload() {
    const timeRange = serializeRange()
    return {
      cohort_id: form.value.cohort_id || null,
      department: form.value.department || null,
      dept_code: form.value.dept_code || null,
      patient_scope: form.value.patient_scope,
      time_range: timeRange,
      export_mode: form.value.export_mode,
      data_types: form.value.data_types,
      format: form.value.format,
      desensitize: form.value.desensitize,
      include_data_dict: form.value.include_data_dict,
    }
  }

  /* ───── API 调用 ───── */
  async function runPreview() {
    if (!form.value.data_types.length) {
      message.warning('请至少选择一种数据类型')
      return
    }
    const payload = buildPayload()
    if (!payload.time_range) {
      message.warning('请选择时间范围')
      return
    }
    previewLoading.value = true
    try {
      const res = await previewResearchExport(payload)
      preview.value = res.data || {}
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '预览失败')
    } finally {
      previewLoading.value = false
    }
  }

  async function submitExport() {
    if (!form.value.data_types.length) {
      message.warning('请至少选择一种数据类型')
      return
    }
    const payload = buildPayload()
    if (!payload.time_range) {
      message.warning('请选择时间范围')
      return
    }
    submitting.value = true
    try {
      const res = await createResearchExportTask(payload)
      activeTask.value = { task_id: res.data.task_id, status: 'pending', progress: 0, scope_summary: preview.value?.scope_summary || null }
      message.success('导出任务已提交')
      startPolling(String(res.data.task_id))
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '提交失败')
    } finally {
      submitting.value = false
    }
  }

  function startPolling(taskId: string) {
    stopPolling()
    pollTimer = setInterval(async () => {
      try {
        const res = await getResearchExportTaskStatus(taskId)
        activeTask.value = res.data || {}
        if (['completed', 'failed'].includes(String(activeTask.value?.status || ''))) {
          stopPolling()
          void loadHistory()
        }
      } catch {
        // ignore transient errors
      }
    }, 2000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function downloadTask(taskId: string) {
    window.open(`/api/research/export/${taskId}/download`, '_blank')
  }

  function openDetail(record: AnyRecord) {
    detailTask.value = record
    detailOpen.value = true
  }

  async function loadHistory() {
    historyLoading.value = true
    try {
      const res = await listResearchExportHistory({
        status: historyFilters.value.status,
        export_mode: historyFilters.value.export_mode,
      })
      history.value = Array.isArray(res.data?.history) ? res.data.history : []
    } catch {
      history.value = []
    } finally {
      historyLoading.value = false
    }
  }

  async function loadDepartments() {
    departmentLoading.value = true
    try {
      const res = await getDepartments()
      departments.value = Array.isArray(res.data?.departments) ? res.data.departments : []
    } catch {
      departments.value = []
    } finally {
      departmentLoading.value = false
    }
  }

  async function loadCohorts() {
    cohortLoading.value = true
    try {
      const res = await listResearchCohorts({ limit: 200 })
      cohorts.value = Array.isArray(res.data?.cohorts) ? res.data.cohorts : []
    } catch {
      cohorts.value = []
    } finally {
      cohortLoading.value = false
    }
  }

  function applyRouteDepartmentLock() {
    if (!departmentLocked.value) return
    form.value.dept_code = routeDeptCode.value
    form.value.department = matchedLockedDepartment.value?.dept || routeDepartment.value || form.value.department
  }

  function onCohortChange(cohortId: any) {
    const matched = cohorts.value.find((item) => String(item.cohort_id) === String(cohortId))
    if (!matched) return
    if (!departmentLocked.value) {
      form.value.department = matched.department || ''
      form.value.dept_code = matched.dept_code || ''
    }
    form.value.patient_scope = matched.patient_scope || 'all'
  }

  /* ───── 监听 ───── */
  watch(() => [historyFilters.value.status, historyFilters.value.export_mode], () => {
    void loadHistory()
  })
  watch(() => form.value.export_mode, (mode) => {
    if (mode === 'dataset') {
      const required = ['patients', 'outcomes']
      form.value.data_types = Array.from(new Set([...required, ...form.value.data_types]))
      return
    }
    form.value.data_types = form.value.data_types.filter((item) => !['patients', 'outcomes'].includes(String(item)))
  })

  /* ───── 初始化 ───── */
  async function init() {
    applyRouteDepartmentLock()
    await Promise.all([loadHistory(), loadDepartments(), loadCohorts()])
    applyRouteDepartmentLock()
  }

  onUnmounted(stopPolling)

  return {
    // 状态
    form,
    preview,
    previewLoading,
    submitting,
    activeTask,
    history,
    historyLoading,
    historyFilters,
    departments,
    cohorts,
    departmentLoading,
    cohortLoading,
    detailOpen,
    detailTask,
    // 路由
    routeDeptCode,
    routeDepartment,
    departmentLocked,
    matchedLockedDepartment,
    lockedDepartmentLabel,
    // 计算属性
    departmentOptions,
    cohortOptions,
    progressStatus,
    previewRows,
    previewWarnings,
    previewPatients,
    previewTotalRows,
    previewNonEmptyCount,
    previewEmptyLabels,
    completedCount,
    processingCount,
    failedCount,
    // 工具函数
    patientScopeLabel,
    exportModeLabel,
    statusLabel,
    statusTagColor,
    formatTime,
    taskSummaryText,
    buildPayload,
    // API
    runPreview,
    submitExport,
    downloadTask,
    openDetail,
    loadHistory,
    loadDepartments,
    loadCohorts,
    applyRouteDepartmentLock,
    onCohortChange,
    init,
  }
}
