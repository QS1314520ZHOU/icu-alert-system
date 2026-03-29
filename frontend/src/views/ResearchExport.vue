<template>
  <div class="research-export">
    <h1 class="research-title">科研数据导出</h1>

    <a-card class="research-card" title="新建导出任务">
      <div class="form-grid">
        <div class="form-row">
          <div class="form-label">数据类型</div>
          <ACheckboxGroup v-model:value="form.data_types">
            <a-checkbox value="vitals">生命体征</a-checkbox>
            <a-checkbox value="labs">检验结果</a-checkbox>
            <a-checkbox value="alerts">预警记录</a-checkbox>
            <a-checkbox value="scores">评分数据</a-checkbox>
            <a-checkbox value="ai_logs">人工智能分析日志</a-checkbox>
          </ACheckboxGroup>
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
          <div class="form-label">科室筛选</div>
          <a-select
            v-model:value="form.department"
            class="w-420"
            :options="departmentOptions"
            :loading="departmentLoading"
            :show-search="true"
            option-filter-prop="label"
            allow-clear
            placeholder="全部科室"
          />
        </div>

        <div class="form-row">
          <div class="form-label">导出格式</div>
          <ARadioGroup v-model:value="form.format">
            <a-radio value="csv">逗号分隔文本（兼容表格软件）</a-radio>
            <a-radio value="parquet">列式二进制文件（适合编程分析）</a-radio>
          </ARadioGroup>
        </div>

        <div class="form-row">
          <div class="form-label">导出选项</div>
          <div class="form-options">
            <a-checkbox v-model:checked="form.desensitize">自动脱敏（隐藏姓名/身份证/手机号）</a-checkbox>
            <a-checkbox v-model:checked="form.include_data_dict">附带数据字典（会额外生成字段说明文件）</a-checkbox>
          </div>
        </div>

        <div class="form-row">
          <div class="form-label"></div>
          <a-button type="primary" :loading="submitting" @click="submitExport">提交导出任务</a-button>
        </div>
      </div>
    </a-card>

    <a-card v-if="activeTask" class="research-card" title="当前任务进度">
      <p class="task-meta">任务编号：{{ activeTask.task_id }}</p>
      <a-progress :percent="Number(activeTask.progress || 0)" :status="progressStatus" />
      <p class="task-meta">状态：{{ statusLabel(activeTask.status) }}</p>
      <a-button
        v-if="activeTask.status === 'completed'"
        type="primary"
        class="download-btn"
        @click="downloadTask(activeTask.task_id)"
      >
        下载文件
      </a-button>
    </a-card>

    <a-card class="research-card">
      <template #title>导出历史</template>
      <template #extra>
        <a-button size="small" @click="loadHistory">刷新</a-button>
      </template>
      <a-table
        :data-source="history"
        :columns="historyColumns"
        :pagination="{ pageSize: 8, hideOnSinglePage: true }"
        row-key="task_id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusTagColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'progress'">
            {{ Number(record.progress || 0) }}%
          </template>
          <template v-else-if="column.key === 'row_count'">
            <div v-if="taskSummaryItems(record).length" class="row-count-cell">
              <span class="row-count-total">{{ taskTotalRowCount(record) }} 行</span>
              <span class="row-count-meta">空文件 {{ taskEmptyFileCount(record) }}</span>
              <span class="row-count-detail">{{ taskSummaryText(record) }}</span>
            </div>
            <span v-else class="muted">—</span>
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button
              v-if="record.status === 'completed'"
              size="small"
              type="primary"
              @click="downloadTask(record.task_id)"
            >
              下载
            </a-button>
            <span v-else class="muted">—</span>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import dayjs from 'dayjs'
import {
  Button as AButton,
  Card as ACard,
  Checkbox as ACheckbox,
  DatePicker,
  Progress as AProgress,
  Radio as ARadio,
  Select as ASelect,
  Table as ATable,
  Tag as ATag,
  message,
} from 'ant-design-vue'
import { getDepartments } from '../api'

const ARangePicker = DatePicker.RangePicker
const ACheckboxGroup = ACheckbox.Group
const ARadioGroup = ARadio.Group

const historyColumns = [
  { title: '任务编号', dataIndex: 'task_id', key: 'task_id', width: 320 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
  { title: '进度', dataIndex: 'progress', key: 'progress', width: 100 },
  { title: '数据量', key: 'row_count', width: 260 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 220 },
  { title: '操作', key: 'action', width: 100 },
]

const form = ref({
  data_types: ['vitals'],
  department: '',
  time_range: undefined as [any, any] | undefined,
  format: 'csv',
  desensitize: true,
  include_data_dict: true,
})

const submitting = ref(false)
const activeTask = ref<any>(null)
const history = ref<any[]>([])
const departmentLoading = ref(false)
const departments = ref<Array<{ dept: string; patientCount?: number }>>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const progressStatus = computed(() => {
  if (!activeTask.value) return 'active'
  if (activeTask.value.status === 'completed') return 'success'
  if (activeTask.value.status === 'failed') return 'exception'
  return 'active'
})

function statusTagColor(status: string) {
  return {
    pending: 'blue',
    processing: 'gold',
    completed: 'green',
    failed: 'red',
  }[String(status || '').toLowerCase()] || 'default'
}

function statusLabel(status: string) {
  return {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
  }[String(status || '').toLowerCase()] || String(status || '未知')
}

function taskSummaryItems(record: any) {
  return Array.isArray(record?.result_stats)
    ? record.result_stats.filter((item: any) => item && typeof item === 'object')
    : []
}

function taskTotalRowCount(record: any) {
  return taskSummaryItems(record).reduce((sum: number, item: any) => {
    const rows = Number(item?.row_count)
    return Number.isFinite(rows) ? sum + rows : sum
  }, 0)
}

function taskEmptyFileCount(record: any) {
  return taskSummaryItems(record).reduce((sum: number, item: any) => {
    const empty = item?.is_empty === true || Number(item?.row_count || 0) === 0
    return sum + (empty ? 1 : 0)
  }, 0)
}

function taskSummaryText(record: any) {
  const labels: Record<string, string> = {
    vitals: '生命体征',
    labs: '检验',
    alerts: '预警',
    scores: '评分',
    ai_logs: '人工智能日志',
  }
  return taskSummaryItems(record)
    .map((item: any) => {
      const key = String(item?.data_type || '')
      const text = labels[key] || key || '数据'
      const rows = Number(item?.row_count || 0)
      return `${text}:${rows}`
    })
    .join(' / ')
}

const departmentOptions = computed(() =>
  departments.value
    .filter((item) => String(item?.dept || '').trim())
    .map((item) => {
      const count = Number(item?.patientCount || 0)
      return {
        value: item.dept,
        label: count > 0 ? `${item.dept} (${count})` : item.dept,
      }
    })
)

function formatTime(value: any) {
  if (!value) return '—'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : String(value)
}

function serializeRange(range: [any, any] | undefined) {
  if (!Array.isArray(range) || range.length < 2) return null
  const [start, end] = range
  if (!start || !end || typeof start.format !== 'function' || typeof end.format !== 'function') return null
  return {
    start: start.format('YYYY-MM-DDTHH:mm:ss'),
    end: end.format('YYYY-MM-DDTHH:mm:ss'),
  }
}

async function submitExport() {
  if (!form.value.data_types.length) {
    message.warning('请至少选择一种数据类型')
    return
  }
  const timeRange = serializeRange(form.value.time_range)
  if (!timeRange) {
    message.warning('请选择时间范围')
    return
  }

  submitting.value = true
  try {
    const payload = {
      data_types: form.value.data_types,
      department: form.value.department || null,
      time_range: timeRange,
      format: form.value.format,
      desensitize: form.value.desensitize,
      include_data_dict: form.value.include_data_dict,
    }
    const res = await axios.post('/api/research/export', payload)
    activeTask.value = { task_id: res.data.task_id, status: 'pending', progress: 0 }
    message.success('导出任务已提交')
    startPolling(res.data.task_id)
  } catch (error: any) {
    message.error(`提交失败：${error?.response?.data?.detail || error?.message || '未知错误'}`)
  } finally {
    submitting.value = false
  }
}

function startPolling(taskId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await axios.get(`/api/research/export/${taskId}/status`)
      activeTask.value = res.data
      if (['completed', 'failed'].includes(String(res.data?.status || ''))) {
        stopPolling()
        loadHistory()
      }
    } catch {
      // Keep polling for transient network errors.
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

async function loadHistory() {
  try {
    const res = await axios.get('/api/research/export/history')
    history.value = Array.isArray(res.data?.history) ? res.data.history : []
  } catch {
    history.value = []
  }
}

async function loadDepartments() {
  departmentLoading.value = true
  try {
    const res = await getDepartments()
    const rows = Array.isArray(res?.data?.departments) ? res.data.departments : []
    departments.value = rows
  } catch {
    departments.value = []
  } finally {
    departmentLoading.value = false
  }
}

onMounted(() => {
  loadHistory()
  loadDepartments()
})
onUnmounted(stopPolling)
</script>

<style scoped>
.research-export {
  padding: 24px;
  display: grid;
  gap: 16px;
}
.research-title {
  margin: 0;
  font-size: 22px;
  color: #e8f7ff;
  letter-spacing: 0.04em;
}
.research-card {
  background: rgba(10, 26, 44, 0.86);
  border: 1px solid rgba(125, 211, 252, 0.18);
}
.research-card :deep(.ant-card-head-title),
.research-card :deep(.ant-card-extra),
.research-card :deep(.ant-checkbox-wrapper),
.research-card :deep(.ant-radio-wrapper),
.research-card :deep(.ant-form-item-label > label),
.research-card :deep(.ant-select-selection-item),
.research-card :deep(.ant-select-selection-placeholder),
.research-card :deep(.ant-picker-input > input),
.research-card :deep(.ant-picker-separator),
.research-card :deep(.ant-picker-suffix),
.research-card :deep(.ant-table),
.research-card :deep(.ant-table-thead > tr > th),
.research-card :deep(.ant-table-tbody > tr > td) {
  color: rgba(232, 247, 255, 0.92) !important;
}
.research-card :deep(.ant-input),
.research-card :deep(.ant-select-selector),
.research-card :deep(.ant-picker) {
  background: rgba(5, 20, 35, 0.72) !important;
  border-color: rgba(125, 211, 252, 0.28) !important;
}
.research-card :deep(.ant-picker-input > input::placeholder) {
  color: rgba(180, 210, 230, 0.65) !important;
}
.research-card :deep(.ant-table-thead > tr > th) {
  background: rgba(8, 30, 48, 0.88) !important;
}
.research-card :deep(.ant-table-tbody > tr > td) {
  background: rgba(7, 24, 40, 0.7) !important;
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
  color: #8bb8d6;
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
.task-meta {
  margin: 8px 0;
  color: #9ab8cf;
}
.download-btn {
  margin-top: 12px;
}
.muted {
  color: #8da4bb;
}
.row-count-cell {
  display: grid;
  gap: 2px;
}
.row-count-total {
  color: #d8f5ff;
  font-weight: 600;
}
.row-count-meta {
  color: #8bb8d6;
  font-size: 12px;
}
.row-count-detail {
  color: #9ab8cf;
  font-size: 12px;
}
</style>
