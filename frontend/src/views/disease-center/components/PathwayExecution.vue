<template>
  <div class="pathway-execution">
    <div v-if="loading" class="pathway-loading">
      <a-spin tip="加载临床路径..." />
    </div>

    <template v-else>
      <div v-if="!pathwayData" class="pathway-empty">
        <a-empty description="暂无临床路径实例" />
      </div>

      <template v-else>
        <!-- 路径概览 -->
        <div class="pathway-overview">
          <div class="overview-item">
            <span class="overview-label">路径名称</span>
            <span class="overview-value">{{ pathwayData.instance?.pathway_name || pathwayData.instance?.pathway_id || '-' }}</span>
          </div>
          <div class="overview-item">
            <span class="overview-label">开始时间</span>
            <span class="overview-value">{{ formatTime(pathwayData.instance?.started_at) }}</span>
          </div>
          <div class="overview-item">
            <span class="overview-label">状态</span>
            <a-tag :color="getStatusColor(pathwayData.instance?.status)">
              {{ getStatusLabel(pathwayData.instance?.status) }}
            </a-tag>
          </div>
          <div class="overview-item">
            <span class="overview-label">合规率</span>
            <span class="overview-value compliance" :class="getComplianceClass(pathwayData.instance?.compliance_rate)">
              {{ pathwayData.instance?.compliance_rate != null ? (pathwayData.instance.compliance_rate * 100).toFixed(0) + '%' : '-' }}
            </span>
          </div>
        </div>

        <!-- 任务列表 -->
        <div class="task-list">
          <div class="task-header">
            <span class="task-title">路径任务</span>
            <span class="task-count">共 {{ tasks.length }} 项</span>
          </div>

          <a-table
            :columns="taskColumns"
            :data-source="tasks"
            :pagination="false"
            row-key="id"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'task_name'">
                <span>{{ record.task_name || record.task_id }}</span>
              </template>

              <template v-if="column.key === 'applicability'">
                <a-tag :color="getApplicabilityColor(record.applicability)" size="small">
                  {{ getApplicabilityLabel(record.applicability) }}
                </a-tag>
              </template>

              <template v-if="column.key === 'execution_status'">
                <a-tag :color="getExecStatusColor(record.execution_status)" size="small">
                  {{ getExecStatusLabel(record.execution_status) }}
                </a-tag>
              </template>

              <template v-if="column.key === 'condition_met'">
                <span v-if="record.condition_met === true" class="condition-yes">✓ 满足</span>
                <span v-else-if="record.condition_met === false" class="condition-no">✗ 不满足</span>
                <span v-else class="condition-na">-</span>
              </template>

              <template v-if="column.key === 'actions'">
                <a-button
                  v-if="canComplete(record)"
                  type="link"
                  size="small"
                  @click="handleComplete(record)"
                >
                  标记完成
                </a-button>
              </template>
            </template>
          </a-table>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { getCasePathway, completeCaseTask } from '@/api/diseaseCenter'
import type { PathwayInstanceData } from '@/api/diseaseCenter'

const props = defineProps<{
  caseId: string
}>()

const loading = ref(false)
const pathwayData = ref<PathwayInstanceData | null>(null)

const tasks = ref<any[]>([])

const taskColumns = [
  { title: '任务', key: 'task_name', dataIndex: 'task_name', width: 200 },
  { title: '适用性', key: 'applicability', dataIndex: 'applicability', width: 120 },
  { title: '执行状态', key: 'execution_status', dataIndex: 'execution_status', width: 120 },
  { title: '条件满足', key: 'condition_met', dataIndex: 'condition_met', width: 100 },
  { title: '临床审查', dataIndex: 'clinical_review', width: 150,
    customRender: ({ text }: { text: string }) => text || '-' },
  { title: '操作', key: 'actions', width: 100 },
]

function formatTime(t?: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

function getStatusColor(status?: string) {
  const map: Record<string, string> = {
    active: 'var(--color-primary)',
    completed: 'var(--color-success)',
    paused: 'var(--color-warning)',
    cancelled: 'default',
  }
  return map[status || ''] || 'default'
}

function getStatusLabel(status?: string) {
  const map: Record<string, string> = {
    active: '执行中',
    completed: '已完成',
    paused: '暂停',
    cancelled: '已取消',
  }
  return map[status || ''] || status || '-'
}

function getApplicabilityColor(app?: string) {
  const map: Record<string, string> = {
    required: 'var(--color-error-light)',
    conditional: 'var(--color-warning-light)',
    individualized: 'var(--color-primary-light)',
    not_applicable: 'default',
    contraindicated: 'var(--color-error-light)',
    review_pending: 'var(--color-warning-light)',
  }
  return map[app || ''] || 'default'
}

function getApplicabilityLabel(app?: string) {
  const map: Record<string, string> = {
    required: '必需',
    conditional: '条件性',
    individualized: '个体化',
    not_applicable: '不适用',
    contraindicated: '禁忌',
    review_pending: '待审查',
  }
  return map[app || ''] || app || '-'
}

function getExecStatusColor(status?: string) {
  const map: Record<string, string> = {
    pending: 'default',
    in_progress: 'var(--color-primary-light)',
    completed: 'var(--color-success-light)',
    completed_late: 'var(--color-warning-light)',
    overdue: 'var(--color-error-light)',
    skipped: 'default',
    cancelled: 'default',
    not_applicable: 'default',
  }
  return map[status || ''] || 'default'
}

function getExecStatusLabel(status?: string) {
  const map: Record<string, string> = {
    pending: '待执行',
    in_progress: '执行中',
    completed: '已完成',
    completed_late: '延迟完成',
    overdue: '已超时',
    skipped: '已跳过',
    cancelled: '已取消',
    not_applicable: '不适用',
  }
  return map[status || ''] || status || '-'
}

function getComplianceClass(rate?: number | null) {
  if (rate == null) return ''
  if (rate >= 0.8) return 'compliance-high'
  if (rate >= 0.5) return 'compliance-medium'
  return 'compliance-low'
}

function canComplete(record: any) {
  return ['pending', 'in_progress'].includes(record.execution_status)
}

async function handleComplete(record: any) {
  try {
    await completeCaseTask(props.caseId, record.id || record.task_id, {
      completion_note: '医生标记完成',
    })
    message.success('任务已标记完成')
    loadPathway()
  } catch (err: any) {
    message.error('操作失败: ' + (err.message || '未知错误'))
  }
}

async function loadPathway() {
  loading.value = true
  try {
    pathwayData.value = await getCasePathway(props.caseId)
    tasks.value = pathwayData.value?.tasks || []
  } catch {
    pathwayData.value = null
    tasks.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.caseId, () => {
  if (props.caseId) loadPathway()
}, { immediate: true })

onMounted(() => {
  if (props.caseId) loadPathway()
})
</script>

<style scoped>
.pathway-execution {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pathway-loading {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

/* Overview */
.pathway-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: var(--radius-md, 8px);
}

.overview-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.overview-label {
  font-size: 12px;
  color: var(--color-text-tertiary, #98A2B3);
}

.overview-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

.compliance-high {
  color: var(--color-success, #16845B);
}

.compliance-medium {
  color: var(--color-warning, #DC6803);
}

.compliance-low {
  color: var(--color-error, #D92D20);
}

/* Tasks */
.task-list {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 8px);
  padding: 12px;
}

.task-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.task-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.task-count {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.condition-yes {
  color: var(--color-success, #16845B);
  font-weight: 500;
}

.condition-no {
  color: var(--color-error, #D92D20);
  font-weight: 500;
}

.condition-na {
  color: var(--color-text-tertiary, #98A2B3);
}
</style>
