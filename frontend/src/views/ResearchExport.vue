<template>
  <div class="research-export">
    <section class="hero">
      <div>
        <h1 class="research-title">科研数据导出</h1>
        <p class="research-sub">从研究队列直接导出原始明细或研究数据集，并在提交前预览样本范围与命中量。</p>
      </div>
      <a-space>
        <a-button size="small" :loading="historyLoading" @click="loadHistory">刷新历史</a-button>
        <a-button size="small" :loading="previewLoading" @click="runPreview">更新预览</a-button>
      </a-space>
    </section>

    <section class="history-kpis">
      <div class="kpi-card">
        <span>历史任务</span>
        <strong>{{ history.length }}</strong>
      </div>
      <div class="kpi-card">
        <span>已完成</span>
        <strong>{{ completedCount }}</strong>
      </div>
      <div class="kpi-card">
        <span>处理中</span>
        <strong>{{ processingCount }}</strong>
      </div>
      <div class="kpi-card">
        <span>失败</span>
        <strong>{{ failedCount }}</strong>
      </div>
    </section>

    <a-card class="research-card" title="导出配置">
      <div class="form-grid">
        <div class="form-row">
          <div class="form-label">已保存队列</div>
          <a-select
            v-model:value="form.cohort_id"
            class="w-420"
            :options="cohortOptions"
            :loading="cohortLoading"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="可选：直接复用科研队列"
            @change="onCohortChange"
          />
        </div>

        <div class="form-row">
          <div class="form-label">患者范围</div>
          <ARadioGroup v-model:value="form.patient_scope">
            <a-radio value="all">全部</a-radio>
            <a-radio value="in_dept">在科</a-radio>
            <a-radio value="out_dept">出科</a-radio>
          </ARadioGroup>
        </div>

        <div class="form-row">
          <div class="form-label">科室筛选</div>
          <div v-if="departmentLocked" class="locked-department">
            <strong>{{ lockedDepartmentLabel }}</strong>
            <span>已根据当前页面科室自动锁定</span>
          </div>
          <a-select
            v-else
            v-model:value="form.department"
            class="w-420"
            :options="departmentOptions"
            :loading="departmentLoading"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="可选：限定科室"
          />
        </div>

        <div class="form-row">
          <div class="form-label">时间范围</div>
          <a-range-picker
            v-model:value="form.time_range"
            class="w-420"
            :show-time="{ format: 'HH:mm' }"
            format="YYYY-MM-DD HH:mm"
            :allow-clear="true"
          />
        </div>

        <div class="form-row">
          <div class="form-label">导出模式</div>
          <ARadioGroup v-model:value="form.export_mode">
            <a-radio value="dataset">研究数据集</a-radio>
            <a-radio value="raw">原始明细</a-radio>
          </ARadioGroup>
        </div>

        <div class="form-row">
          <div class="form-label">数据类型</div>
          <ACheckboxGroup v-model:value="form.data_types">
            <a-checkbox value="patients">患者主表</a-checkbox>
            <a-checkbox value="outcomes">结局表</a-checkbox>
            <a-checkbox value="vitals">生命体征</a-checkbox>
            <a-checkbox value="labs">检验结果</a-checkbox>
            <a-checkbox value="alerts">预警记录</a-checkbox>
            <a-checkbox value="scores">评分数据</a-checkbox>
            <a-checkbox value="ai_logs">人工智能日志</a-checkbox>
          </ACheckboxGroup>
        </div>

        <div class="form-row">
          <div class="form-label">文件格式</div>
          <ARadioGroup v-model:value="form.format">
            <a-radio value="csv">CSV</a-radio>
            <a-radio value="parquet">Parquet</a-radio>
          </ARadioGroup>
        </div>

        <div class="form-row">
          <div class="form-label">导出选项</div>
          <div class="form-options">
            <a-checkbox v-model:checked="form.desensitize">自动脱敏</a-checkbox>
            <a-checkbox v-model:checked="form.include_data_dict">附带数据字典</a-checkbox>
          </div>
        </div>

        <div class="form-row">
          <div class="form-label"></div>
          <a-space>
            <a-button :loading="previewLoading" @click="runPreview">预览导出范围</a-button>
            <a-button type="primary" :loading="submitting" @click="submitExport">提交导出任务</a-button>
          </a-space>
        </div>
      </div>
    </a-card>

    <a-card class="research-card" title="导出预览">
      <template v-if="preview">
        <div class="preview-grid">
          <div class="preview-kpi">
            <span>患者数</span>
            <strong>{{ Number(preview.scope_summary?.patient_count || 0) }}</strong>
          </div>
          <div class="preview-kpi">
            <span>范围</span>
            <strong>{{ patientScopeLabel(preview.scope_summary?.patient_scope) }}</strong>
          </div>
          <div class="preview-kpi">
            <span>队列</span>
            <strong>{{ preview.scope_summary?.cohort_name || '未指定' }}</strong>
          </div>
          <div class="preview-kpi">
            <span>科室</span>
            <strong>{{ preview.scope_summary?.department || '全部科室' }}</strong>
          </div>
        </div>
        <div class="preview-highlights">
          <span class="highlight-chip">
            命中数据类型
            <b>{{ previewNonEmptyCount }}/{{ previewRows.length }}</b>
          </span>
          <span class="highlight-chip">
            预计总行数
            <b>{{ previewTotalRows }}</b>
          </span>
          <span class="highlight-chip" v-if="previewEmptyLabels.length">
            空类型
            <b>{{ previewEmptyLabels.join('、') }}</b>
          </span>
        </div>
        <div v-if="previewWarnings.length" class="warning-list">
          <div v-for="item in previewWarnings" :key="item" class="warning-item">{{ item }}</div>
        </div>
        <a-table
          :data-source="previewRows"
          :columns="previewColumns"
          :pagination="false"
          row-key="data_type"
          size="small"
        />
        <div v-if="previewPatients.length" class="preview-patient-block">
          <div class="section-title">队列样本预览</div>
          <a-table
            :data-source="previewPatients"
            :columns="previewPatientColumns"
            :pagination="false"
            row-key="patient_id"
            size="small"
          />
        </div>
      </template>
      <div v-else class="empty-block">先选择导出条件并点击“预览导出范围”</div>
    </a-card>

    <a-card v-if="activeTask" class="research-card" title="当前任务">
      <div class="task-head">
        <span>任务编号：{{ activeTask.task_id }}</span>
        <span>{{ statusLabel(activeTask.status) }}</span>
      </div>
      <a-progress :percent="Number(activeTask.progress || 0)" :status="progressStatus" />
      <div v-if="activeTask.scope_summary" class="task-summary">
        <span>患者数 {{ Number(activeTask.scope_summary.patient_count || 0) }}</span>
        <span>范围 {{ patientScopeLabel(activeTask.scope_summary.patient_scope) }}</span>
        <span>模式 {{ exportModeLabel(activeTask.scope_summary.export_mode) }}</span>
      </div>
      <div v-if="Array.isArray(activeTask.warnings) && activeTask.warnings.length" class="warning-list task-warnings">
        <div v-for="item in activeTask.warnings" :key="item" class="warning-item">{{ item }}</div>
      </div>
      <div v-if="activeTask.status === 'failed' && activeTask.error" class="error-panel">
        <div class="section-title">失败原因</div>
        <div class="error-text">{{ activeTask.error }}</div>
      </div>
      <div v-if="activeTask.status === 'completed'" class="download-row">
        <a-button type="primary" @click="downloadTask(activeTask.task_id)">下载文件</a-button>
      </div>
    </a-card>

    <a-card class="research-card">
      <template #title>导出历史</template>
      <template #extra>
        <a-space>
          <a-select v-model:value="historyFilters.status" style="width: 120px" :options="historyStatusOptions" allow-clear placeholder="任务状态" />
          <a-select v-model:value="historyFilters.export_mode" style="width: 140px" :options="historyModeOptions" allow-clear placeholder="导出模式" />
          <a-button size="small" :loading="historyLoading" @click="loadHistory">刷新</a-button>
        </a-space>
      </template>
      <a-table
        :data-source="history"
        :columns="historyColumns"
        :pagination="{ pageSize: 8, hideOnSinglePage: true }"
        row-key="task_id"
        size="small"
        :custom-row="historyRowProps"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusTagColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'scope'">
            <div class="history-scope">
              <div>{{ record.scope_summary?.cohort_name || '未指定队列' }}</div>
              <div class="muted">{{ patientScopeLabel(record.scope_summary?.patient_scope) }} / {{ Number(record.scope_summary?.patient_count || 0) }}例</div>
            </div>
          </template>
          <template v-else-if="column.key === 'summary'">
            <div class="history-summary">
              <div>{{ taskSummaryText(record) || '—' }}</div>
              <div class="muted">{{ exportModeLabel(record.scope_summary?.export_mode) }}</div>
              <div v-if="Array.isArray(record.warnings) && record.warnings.length" class="muted">风险 {{ record.warnings.length }} 条</div>
            </div>
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button size="small" @click="openDetail(record)">详情</a-button>
              <a-button v-if="record.status === 'completed'" size="small" type="primary" @click="downloadTask(record.task_id)">下载</a-button>
              <a-tag v-else-if="record.status === 'failed'" color="red">失败</a-tag>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-drawer v-model:open="detailOpen" title="导出任务详情" width="540">
      <template v-if="detailTask">
        <div class="detail-grid">
          <div class="detail-item"><span>任务编号</span><strong>{{ detailTask.task_id }}</strong></div>
          <div class="detail-item"><span>状态</span><strong>{{ statusLabel(detailTask.status) }}</strong></div>
          <div class="detail-item"><span>患者范围</span><strong>{{ patientScopeLabel(detailTask.scope_summary?.patient_scope) }}</strong></div>
          <div class="detail-item"><span>导出模式</span><strong>{{ exportModeLabel(detailTask.scope_summary?.export_mode) }}</strong></div>
          <div class="detail-item"><span>患者数</span><strong>{{ Number(detailTask.scope_summary?.patient_count || 0) }}</strong></div>
          <div class="detail-item"><span>科室</span><strong>{{ detailTask.scope_summary?.department || '全部科室' }}</strong></div>
          <div class="detail-item full"><span>队列</span><strong>{{ detailTask.scope_summary?.cohort_name || '未指定队列' }}</strong></div>
          <div class="detail-item full"><span>时间范围</span><strong>{{ detailTask.scope_summary?.time_range?.start || '—' }} ~ {{ detailTask.scope_summary?.time_range?.end || '—' }}</strong></div>
        </div>
        <div v-if="Array.isArray(detailTask.warnings) && detailTask.warnings.length" class="warning-list task-warnings">
          <div v-for="item in detailTask.warnings" :key="item" class="warning-item">{{ item }}</div>
        </div>
        <div v-if="Array.isArray(detailTask.preview_patients) && detailTask.preview_patients.length" class="preview-patient-block">
          <div class="section-title">样本预览</div>
          <a-table
            :data-source="detailTask.preview_patients"
            :columns="previewPatientColumns"
            :pagination="false"
            row-key="patient_id"
            size="small"
          />
        </div>
        <div v-if="detailTask.error" class="error-panel">
          <div class="section-title">失败原因</div>
          <div class="error-text">{{ detailTask.error }}</div>
        </div>
        <div class="preview-patient-block">
          <div class="section-title">导出文件摘要</div>
          <a-table
            :data-source="Array.isArray(detailTask.result_stats) ? detailTask.result_stats : []"
            :columns="detailResultColumns"
            :pagination="false"
            row-key="file_name"
            size="small"
          />
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import {
  Button as AButton,
  Card as ACard,
  Checkbox as ACheckbox,
  DatePicker,
  Drawer as ADrawer,
  Progress as AProgress,
  Radio as ARadio,
  Select as ASelect,
  Space as ASpace,
  Table as ATable,
  Tag as ATag,
  message,
} from 'ant-design-vue'
import {
  createResearchExportTask,
  getDepartments,
  getResearchExportTaskStatus,
  listResearchCohorts,
  listResearchExportHistory,
  previewResearchExport,
} from '../api'

const ARangePicker = DatePicker.RangePicker
const ACheckboxGroup = ACheckbox.Group
const ARadioGroup = ARadio.Group
const route = useRoute()

type AnyRecord = Record<string, any>

const form = ref({
  cohort_id: '',
  department: '',
  dept_code: '',
  patient_scope: 'all',
  time_range: [dayjs().subtract(30, 'day'), dayjs()] as [any, any],
  export_mode: 'dataset',
  data_types: ['patients', 'outcomes', 'labs'],
  format: 'csv',
  desensitize: true,
  include_data_dict: true,
})

const preview = ref<AnyRecord | null>(null)
const previewLoading = ref(false)
const submitting = ref(false)
const historyLoading = ref(false)
const activeTask = ref<AnyRecord | null>(null)
const history = ref<AnyRecord[]>([])
const departments = ref<AnyRecord[]>([])
const cohorts = ref<AnyRecord[]>([])
const departmentLoading = ref(false)
const cohortLoading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null
const detailOpen = ref(false)
const detailTask = ref<AnyRecord | null>(null)
const historyFilters = ref({ status: undefined as string | undefined, export_mode: undefined as string | undefined })

const previewColumns = [
  { title: '数据类型', dataIndex: 'label', key: 'label' },
  { title: '预估行数', dataIndex: 'row_count', key: 'row_count' },
  { title: '状态', dataIndex: 'status_text', key: 'status_text' },
]
const previewPatientColumns = [
  { title: '患者ID', dataIndex: 'patient_id', key: 'patient_id', width: 220 },
  { title: '住院号', dataIndex: 'hisPid', key: 'hisPid', width: 160 },
  { title: '科室', dataIndex: 'department', key: 'department', width: 140 },
  { title: '科室编码', dataIndex: 'dept_code', key: 'dept_code', width: 120 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
]

const historyColumns = [
  { title: '任务编号', dataIndex: 'task_id', key: 'task_id', width: 280 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 110 },
  { title: '范围', key: 'scope', width: 220 },
  { title: '导出摘要', key: 'summary', width: 320 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 100 },
]
const historyStatusOptions = [
  { label: '待处理', value: 'pending' },
  { label: '处理中', value: 'processing' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
]
const historyModeOptions = [
  { label: '研究数据集', value: 'dataset' },
  { label: '原始明细', value: 'raw' },
]
const detailResultColumns = [
  { title: '数据类型', dataIndex: 'label', key: 'label' },
  { title: '文件名', dataIndex: 'file_name', key: 'file_name' },
  { title: '行数', dataIndex: 'row_count', key: 'row_count' },
  { title: '是否为空', dataIndex: 'is_empty', key: 'is_empty' },
]

const departmentOptions = computed(() => departments.value
  .filter((item) => String(item?.dept || '').trim())
  .map((item) => ({
    value: item.dept,
    label: Number(item.patientCount || 0) > 0 ? `${item.dept} (${Number(item.patientCount || 0)})` : item.dept,
  })))

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

function patientScopeLabel(value: any): string {
  const map: Record<string, string> = { all: '全部', in_dept: '在科', out_dept: '出科' }
  return map[String(value || 'all')] || '全部'
}

function exportModeLabel(value: any): string {
  return String(value || '') === 'raw' ? '原始明细' : '研究数据集'
}

function statusLabel(status: string) {
  return {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
  }[String(status || '').toLowerCase()] || String(status || '未知')
}

function statusTagColor(status: string) {
  return {
    pending: 'blue',
    processing: 'gold',
    completed: 'green',
    failed: 'red',
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

function historyRowProps(record: AnyRecord) {
  return {
    style: { cursor: 'pointer' },
    onClick: () => openDetail(record),
  }
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

function applyRouteDepartmentLock() {
  if (!departmentLocked.value) return
  form.value.dept_code = routeDeptCode.value
  form.value.department = matchedLockedDepartment.value?.dept || routeDepartment.value || form.value.department
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

function onCohortChange(cohortId: any) {
  const matched = cohorts.value.find((item) => String(item.cohort_id) === String(cohortId))
  if (!matched) return
  if (!departmentLocked.value) {
    form.value.department = matched.department || ''
    form.value.dept_code = matched.dept_code || ''
  }
  form.value.patient_scope = matched.patient_scope || 'all'
}

watch(() => [form.value.cohort_id, form.value.department, form.value.dept_code, form.value.patient_scope, form.value.export_mode, form.value.format, form.value.desensitize, form.value.include_data_dict, form.value.data_types.join('|'), String(form.value.time_range?.[0] || ''), String(form.value.time_range?.[1] || '')], () => {
  preview.value = null
})
watch(() => [historyFilters.value.status, historyFilters.value.export_mode], () => {
  void loadHistory()
})
watch([routeDeptCode, routeDepartment, matchedLockedDepartment], () => {
  applyRouteDepartmentLock()
})

watch(() => form.value.export_mode, (mode) => {
  if (mode === 'dataset') {
    const required = ['patients', 'outcomes']
    form.value.data_types = Array.from(new Set([...required, ...form.value.data_types]))
    return
  }
  form.value.data_types = form.value.data_types.filter((item) => !['patients', 'outcomes'].includes(String(item)))
})

onMounted(() => {
  applyRouteDepartmentLock()
  void Promise.all([loadHistory(), loadDepartments(), loadCohorts()]).then(() => {
    applyRouteDepartmentLock()
  })
})

onUnmounted(stopPolling)
</script>

<style scoped>
.research-export {
  padding: 24px;
  display: grid;
  gap: 16px;
  font-family: var(--app-display-font);
}
.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.research-title {
  margin: 0;
  font-size: 24px;
  color: var(--text-primary);
}
.research-sub {
  margin: 6px 0 0;
  color: #95b7d1;
}
.research-card {
  background: var(--bg-surface), 0.86);
  border: 1px solid rgba(125, 211, 252, 0.18);
}
.history-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.kpi-card {
  padding: 14px 16px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.72);
  border: 1px solid rgba(125, 211, 252, 0.16);
}
.kpi-card span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}
.kpi-card strong {
  display: block;
  margin-top: 6px;
  color: var(--text-primary);
  font-size: 22px;
}
.research-card :deep(.ant-card-head-title),
.research-card :deep(.ant-card-extra),
.research-card :deep(.ant-checkbox-wrapper),
.research-card :deep(.ant-radio-wrapper),
.research-card :deep(.ant-select-selection-item),
.research-card :deep(.ant-select-selection-placeholder),
.research-card :deep(.ant-picker-input > input),
.research-card :deep(.ant-table),
.research-card :deep(.ant-table-thead > tr > th),
.research-card :deep(.ant-table-tbody > tr > td) {
  color: rgba(232, 247, 255, 0.92) !important;
}
.research-card :deep(.ant-select-selector),
.research-card :deep(.ant-picker) {
  background: var(--bg-surface), 0.72) !important;
  border-color: rgba(125, 211, 252, 0.28) !important;
}
.form-grid {
  display: grid;
  gap: 14px;
}
.form-row {
  display: grid;
  grid-template-columns: 96px 1fr;
  align-items: center;
  gap: 10px;
}
.form-label {
  color: var(--text-secondary);
  font-size: 12px;
}
.form-options {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
}
.w-420 {
  max-width: 420px;
  width: 100%;
}
.locked-department {
  max-width: 420px;
  width: 100%;
  display: grid;
  gap: 4px;
  padding: 10px 14px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.72);
  border: 1px solid rgba(125, 211, 252, 0.16);
}
.locked-department strong {
  color: var(--text-primary);
  font-size: 14px;
}
.locked-department span {
  color: var(--text-secondary);
  font-size: 12px;
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.preview-kpi {
  padding: 12px 14px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.72);
  border: 1px solid rgba(125, 211, 252, 0.16);
}
.preview-kpi span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}
.preview-kpi strong {
  display: block;
  margin-top: 6px;
  color: var(--text-primary);
  font-size: 18px;
}
.warning-list {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
}
.preview-highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}
.highlight-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.9);
  border: 1px solid rgba(125, 211, 252, 0.18);
  color: var(--text-primary);
  font-size: 12px;
}
.highlight-chip b {
  color: #8ff3ff;
  font-weight: 700;
}
.task-warnings {
  margin-top: 12px;
  margin-bottom: 0;
}
.error-panel {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--card-radius);
  background: rgba(127, 29, 29, 0.28);
  border: 1px solid rgba(248, 113, 113, 0.34);
}
.error-text {
  color: var(--danger-soft);
  white-space: pre-wrap;
  line-height: 1.6;
}
.warning-item {
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: rgba(255, 196, 61, 0.12);
  border: 1px solid rgba(255, 196, 61, 0.24);
  color: #ffe29a;
}
.preview-patient-block {
  margin-top: 14px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.detail-item {
  padding: 10px 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.72);
  border: 1px solid rgba(125, 211, 252, 0.16);
}
.detail-item span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}
.detail-item strong {
  display: block;
  margin-top: 6px;
  color: var(--text-primary);
  line-height: 1.5;
}
.detail-item.full {
  grid-column: 1 / -1;
}
.section-title {
  margin-bottom: 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}
.task-head,
.task-summary,
.download-row {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-top: 10px;
  flex-wrap: wrap;
}
.history-scope,
.history-summary {
  display: grid;
  gap: 2px;
}
.research-card :deep(.ant-table-tbody > tr) {
  transition: background-color 0.18s ease;
}
.research-card :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--bg-surface), 0.88) !important;
}
.muted {
  color: #8da4bb;
}
.empty-block {
  padding: 28px 0;
  text-align: center;
  color: #8da4bb;
}
html[data-theme='light'] .research-export {
  background:
    var(--bg-surface), rgba(59, 130, 246, 0) 34%),
    var(--bg-surface);
  color: var(--text-secondary);
}
html[data-theme='light'] .research-title { color: var(--text-secondary); }
html[data-theme='light'] .research-sub,
html[data-theme='light'] .form-label,
html[data-theme='light'] .kpi-card span,
html[data-theme='light'] .preview-kpi span,
html[data-theme='light'] .locked-department span,
html[data-theme='light'] .detail-item span,
html[data-theme='light'] .muted,
html[data-theme='light'] .empty-block { color: var(--text-secondary); }
html[data-theme='light'] .research-card,
html[data-theme='light'] .kpi-card,
html[data-theme='light'] .locked-department,
html[data-theme='light'] .preview-kpi,
html[data-theme='light'] .highlight-chip,
html[data-theme='light'] .detail-item {
  border-color: rgba(187, 204, 220, 0.72);
  background: rgba(241, 246, 251, 0.98);
}
html[data-theme='light'] .kpi-card strong,
html[data-theme='light'] .preview-kpi strong,
html[data-theme='light'] .locked-department strong,
html[data-theme='light'] .detail-item strong,
html[data-theme='light'] .section-title { color: var(--text-secondary); }
html[data-theme='light'] .highlight-chip { color: var(--text-secondary); }
html[data-theme='light'] .highlight-chip b { color: var(--brand); }
html[data-theme='light'] .warning-item {
  color: var(--warning);
  background: rgba(254, 243, 199, 0.98);
  border-color: rgba(245, 158, 11, 0.28);
}
html[data-theme='light'] .error-panel {
  background: rgba(255, 241, 242, 0.98);
  border-color: rgba(251, 113, 133, 0.3);
}
html[data-theme='light'] .error-text { color: var(--danger-strong); }
html[data-theme='light'] .research-card :deep(.ant-card-head-title),
html[data-theme='light'] .research-card :deep(.ant-card-extra),
html[data-theme='light'] .research-card :deep(.ant-checkbox-wrapper),
html[data-theme='light'] .research-card :deep(.ant-radio-wrapper),
html[data-theme='light'] .research-card :deep(.ant-select-selection-item),
html[data-theme='light'] .research-card :deep(.ant-select-selection-placeholder),
html[data-theme='light'] .research-card :deep(.ant-picker-input > input),
html[data-theme='light'] .research-card :deep(.ant-table),
html[data-theme='light'] .research-card :deep(.ant-table-thead > tr > th),
html[data-theme='light'] .research-card :deep(.ant-table-tbody > tr > td) {
  color: var(--text-secondary) !important;
}
html[data-theme='light'] .research-card :deep(.ant-select-selector),
html[data-theme='light'] .research-card :deep(.ant-picker) {
  background: rgba(241, 246, 251, 0.98) !important;
  border-color: rgba(187, 204, 220, 0.72) !important;
}
html[data-theme='light'] .research-card :deep(.ant-table-tbody > tr:hover > td) {
  background: rgba(231, 241, 249, 0.98) !important;
}
@media (max-width: 1200px) {
  .preview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .history-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
