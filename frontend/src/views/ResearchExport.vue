<template>
  <div class="research-export">
    <PageHeader title="科研数据导出" subtitle="选择范围、字段、脱敏后预览并提交导出任务">
      <template #actions>
        <a-button size="small" :loading="historyLoading" @click="loadHistory">刷新历史</a-button>
      </template>
    </PageHeader>

    <MetricStrip :metrics="kpiMetrics" />

    <!-- 导出就绪度 -->
    <div class="export-viz-row">
      <div class="export-viz-card export-viz-card--ring">
        <h4>导出就绪度</h4>
        <DataCompletenessRing :percent="exportReadiness" :size="100" />
        <span class="export-viz-ring-label">{{ form.data_types.length }} 类数据已选</span>
      </div>
      <div class="export-viz-card">
        <h4>已选数据类型</h4>
        <div class="export-type-chips">
          <span v-for="dt in form.data_types" :key="dt" class="export-type-chip">{{ dataTypeLabel(dt) }}</span>
          <span v-if="!form.data_types.length" class="export-type-empty">未选择</span>
        </div>
      </div>
    </div>

    <!-- 步骤式流程 -->
    <div class="step-card">
      <a-steps :current="currentStep" size="small" :items="stepItems" />
    </div>

    <!-- 步骤1：选择数据范围 -->
    <div v-show="currentStep === 0" class="step-panel">
      <SectionHeader title="数据范围" description="选择队列、科室和患者范围" />
      <div class="form-grid">
        <div class="form-row">
          <div class="form-label">已保存队列</div>
          <a-select
            v-model:value="form.cohort_id"
            class="w-full"
            :options="cohortOptions"
            :loading="cohortLoading"
            allow-clear show-search option-filter-prop="label"
            placeholder="可选：直接复用科研队列"
            @change="onCohortChange"
          />
        </div>
        <div class="form-row">
          <div class="form-label">患者范围</div>
          <a-radio-group v-model:value="form.patient_scope">
            <a-radio-button value="all">全部</a-radio-button>
            <a-radio-button value="in_dept">在科</a-radio-button>
            <a-radio-button value="out_dept">出科</a-radio-button>
          </a-radio-group>
        </div>
        <div class="form-row">
          <div class="form-label">科室筛选</div>
          <div v-if="departmentLocked" class="locked-hint">
            <strong>{{ lockedDepartmentLabel }}</strong>
            <span>已锁定</span>
          </div>
          <a-select v-else v-model:value="form.department" class="w-full" :options="departmentOptions" :loading="departmentLoading" allow-clear show-search option-filter-prop="label" placeholder="可选：限定科室" />
        </div>
        <div class="form-row">
          <div class="form-label">时间范围</div>
          <a-range-picker v-model:value="form.time_range" class="w-full" :show-time="{ format: 'HH:mm' }" format="YYYY-MM-DD HH:mm" :allow-clear="true" />
        </div>
      </div>
      <ActionBar>
        <a-button type="primary" @click="nextStep">下一步</a-button>
      </ActionBar>
    </div>

    <!-- 步骤2：选择字段 -->
    <div v-show="currentStep === 1" class="step-panel">
      <SectionHeader title="导出字段" description="选择导出模式、数据类型和文件格式" />
      <div class="form-grid">
        <div class="form-row">
          <div class="form-label">导出模式</div>
          <a-radio-group v-model:value="form.export_mode">
            <a-radio-button value="dataset">研究数据集</a-radio-button>
            <a-radio-button value="raw">原始明细</a-radio-button>
          </a-radio-group>
        </div>
        <div class="form-row">
          <div class="form-label">数据类型</div>
          <a-checkbox-group v-model:value="form.data_types" class="checkbox-grid">
            <a-checkbox value="patients">患者主表</a-checkbox>
            <a-checkbox value="outcomes">结局表</a-checkbox>
            <a-checkbox value="vitals">生命体征</a-checkbox>
            <a-checkbox value="labs">检验结果</a-checkbox>
            <a-checkbox value="alerts">预警记录</a-checkbox>
            <a-checkbox value="scores">评分数据</a-checkbox>
            <a-checkbox value="ai_logs">AI 日志</a-checkbox>
          </a-checkbox-group>
        </div>
        <div class="form-row">
          <div class="form-label">文件格式</div>
          <a-radio-group v-model:value="form.format">
            <a-radio-button value="csv">CSV</a-radio-button>
            <a-radio-button value="parquet">Parquet</a-radio-button>
          </a-radio-group>
        </div>
      </div>
      <ActionBar>
        <a-button @click="prevStep">上一步</a-button>
        <a-button type="primary" @click="nextStep">下一步</a-button>
      </ActionBar>
    </div>

    <!-- 步骤3：脱敏检查 -->
    <div v-show="currentStep === 2" class="step-panel">
      <SectionHeader title="脱敏设置" description="配置数据脱敏和数据字典选项" />
      <div class="form-grid">
        <div class="form-row">
          <div class="form-label">脱敏选项</div>
          <div class="check-list">
            <a-checkbox v-model:checked="form.desensitize">自动脱敏（去除姓名、身份证等）</a-checkbox>
            <a-checkbox v-model:checked="form.include_data_dict">附带数据字典</a-checkbox>
          </div>
        </div>
      </div>
      <ActionBar>
        <a-button @click="prevStep">上一步</a-button>
        <a-button type="primary" :loading="previewLoading" @click="runPreview">预览导出范围</a-button>
      </ActionBar>
    </div>

    <!-- 步骤4：预览 -->
    <div v-show="currentStep === 3" class="step-panel">
      <SectionHeader title="导出预览" description="确认数据范围和命中量后提交" />
      <template v-if="preview">
        <MetricStrip :metrics="previewMetrics" />
        <div v-if="previewWarnings.length" class="warning-strip">
          <div v-for="item in previewWarnings" :key="item" class="warning-item">{{ item }}</div>
        </div>
        <div class="preview-table-card">
          <a-table :data-source="previewRows" :columns="previewColumns" :pagination="false" row-key="data_type" size="small" />
        </div>
        <div v-if="previewPatients.length" class="preview-table-card">
          <div class="table-title">队列样本预览</div>
          <a-table :data-source="previewPatients" :columns="previewPatientColumns" :pagination="false" row-key="patient_id" size="small" />
        </div>
      </template>
      <EmptyState v-else title="尚未预览" description="请先在上一步点击预览导出范围" />
      <ActionBar>
        <a-button @click="prevStep">上一步</a-button>
        <a-button type="primary" :loading="submitting" :disabled="!preview" @click="submitExport">提交导出任务</a-button>
      </ActionBar>
    </div>

    <!-- 步骤5：任务跟踪 -->
    <div v-show="currentStep === 4" class="step-panel">
      <SectionHeader title="导出任务" description="查看任务进度和下载结果" />
      <template v-if="activeTask">
        <div class="task-status-row">
          <span>任务编号：{{ activeTask.task_id }}</span>
          <a-tag :color="statusTagColor(activeTask.status)">{{ statusLabel(activeTask.status) }}</a-tag>
        </div>
        <a-progress :percent="Number(activeTask.progress || 0)" :status="progressStatus" />
        <div v-if="activeTask.status === 'completed'" class="task-actions">
          <a-button type="primary" @click="downloadTask(activeTask.task_id)">下载文件</a-button>
        </div>
        <div v-if="activeTask.status === 'failed' && activeTask.error" class="error-panel">
          <div class="error-text">{{ activeTask.error }}</div>
        </div>
      </template>
      <EmptyState v-else title="暂无活跃任务" description="提交导出后在此查看进度" />
    </div>

    <!-- 历史记录（折叠） -->
    <div class="history-section">
      <div class="history-toggle" @click="showHistory = !showHistory">
        <span>导出历史（{{ history.length }}）</span>
        <span>{{ showHistory ? '▲' : '▼' }}</span>
      </div>
      <div v-show="showHistory" class="history-content">
        <a-table :data-source="history" :columns="historyColumns" :pagination="{ pageSize: 8, hideOnSinglePage: true }" row-key="task_id" size="small" :custom-row="historyRowProps">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-tag :color="statusTagColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'scope'">
              <div>{{ record.scope_summary?.cohort_name || '未指定队列' }}</div>
              <div class="muted">{{ patientScopeLabel(record.scope_summary?.patient_scope) }} / {{ Number(record.scope_summary?.patient_count || 0) }}例</div>
            </template>
            <template v-else-if="column.key === 'created_at'">{{ formatTime(record.created_at) }}</template>
            <template v-else-if="column.key === 'action'">
              <a-space>
                <a-button size="small" @click="openDetail(record)">详情</a-button>
                <a-button v-if="record.status === 'completed'" size="small" type="primary" @click="downloadTask(record.task_id)">下载</a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </div>
    </div>

    <!-- 详情抽屉 -->
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
        <div v-if="Array.isArray(detailTask.warnings) && detailTask.warnings.length" class="warning-strip">
          <div v-for="item in detailTask.warnings" :key="item" class="warning-item">{{ item }}</div>
        </div>
        <div v-if="detailTask.error" class="error-panel">
          <div class="error-text">{{ detailTask.error }}</div>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button as AButton, Checkbox as ACheckbox, DatePicker, Drawer as ADrawer, Progress as AProgress, Radio as ARadio, Select as ASelect, Space as ASpace, Steps as ASteps, Table as ATable, Tag as ATag } from 'ant-design-vue'
import { PageHeader, SectionHeader, MetricStrip, ActionBar, EmptyState } from '../components/common/design-system'
import { useResearchExport } from '../composables/useResearchExport'
import DataCompletenessRing from '../components/charts/risk/DataCompletenessRing.vue'

const ARangePicker = DatePicker.RangePicker
const ACheckboxGroup = ACheckbox.Group
const ARadioGroup = ARadio.Group

const {
  form, preview, previewLoading, submitting, activeTask,
  history, historyLoading, 
  departmentLoading, cohortLoading, detailOpen, detailTask,
  departmentLocked, lockedDepartmentLabel,
  departmentOptions, cohortOptions, progressStatus,
  previewRows, previewWarnings, previewPatients,
  previewTotalRows, previewNonEmptyCount, 
  completedCount, processingCount, failedCount,
  patientScopeLabel, exportModeLabel, statusLabel, statusTagColor,
  formatTime, 
  runPreview, submitExport, downloadTask, openDetail,
  loadHistory,  onCohortChange, init,
} = useResearchExport()

const showHistory = ref(false)
const currentStep = ref(0)

const stepItems = [
  { title: '数据范围' },
  { title: '选择字段' },
  { title: '脱敏设置' },
  { title: '预览确认' },
  { title: '任务跟踪' },
]

function nextStep() { if (currentStep.value < 4) currentStep.value++ }
function prevStep() { if (currentStep.value > 0) currentStep.value-- }

/* 提交后自动跳到步骤5 */
watch(activeTask, (task) => { if (task?.task_id) currentStep.value = 4 })

const kpiMetrics = computed(() => [
  { label: '历史任务', value: history.value.length },
  { label: '已完成', value: completedCount.value, variant: 'success' as const },
  { label: '处理中', value: processingCount.value, variant: 'info' as const },
  { label: '失败', value: failedCount.value, variant: 'danger' as const },
])

const previewMetrics = computed(() => [
  { label: '患者数', value: Number(preview.value?.scope_summary?.patient_count || 0) },
  { label: '命中类型', value: `${previewNonEmptyCount.value}/${previewRows.value.length}` },
  { label: '预计总行数', value: previewTotalRows.value },
  { label: '科室', value: preview.value?.scope_summary?.department || '全部' },
])

const previewColumns = [
  { title: '数据类型', dataIndex: 'label', key: 'label' },
  { title: '预估行数', dataIndex: 'row_count', key: 'row_count' },
  { title: '状态', dataIndex: 'status_text', key: 'status_text' },
]
const previewPatientColumns = [
  { title: '患者ID', dataIndex: 'patient_id', key: 'patient_id', width: 220 },
  { title: '住院号', dataIndex: 'hisPid', key: 'hisPid', width: 160 },
  { title: '科室', dataIndex: 'department', key: 'department', width: 140 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
]
const historyColumns = [
  { title: '任务编号', dataIndex: 'task_id', key: 'task_id', width: 280 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 110 },
  { title: '范围', key: 'scope', width: 220 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 140 },
]
function historyRowProps(record: any) {
  return { style: { cursor: 'pointer' }, onClick: () => openDetail(record) }
}

// ── 导出就绪度 ──────────────────────────────────────────────────────
const exportReadiness = computed(() => {
  let total = 4
  let filled = 0
  if (form.cohort_id || form.department || form.patient_scope !== 'all') filled++
  if (form.data_types.length > 0) filled++
  if (form.format) filled++
  if (form.desensitize || form.include_data_dict) filled++
  return Math.round((filled / total) * 100)
})

function dataTypeLabel(dt: string): string {
  const map: Record<string, string> = {
    patients: '患者主表', outcomes: '结局表', vitals: '生命体征',
    labs: '检验结果', alerts: '预警记录', scores: '评分数据', ai_logs: 'AI日志',
  }
  return map[dt] || dt
}

init()
</script>

<style scoped>
.research-export {
  padding: var(--page-padding, 24px);
  display: flex;
  flex-direction: column;
  gap: var(--section-gap, 24px);
  max-width: 1200px;
}

/* 导出就绪度 */
.export-viz-row {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 16px;
}

.export-viz-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: 14px 16px;
}

.export-viz-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
}

.export-viz-card--ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.export-viz-ring-label {
  margin-top: 8px;
  font-size: 12px;
  color: #8c8c8c;
}

.export-type-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.export-type-chip {
  display: inline-block;
  padding: 4px 12px;
  background: #E6F4FF;
  color: #2563EB;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.export-type-empty {
  color: #8c8c8c;
  font-size: 12px;
}
.step-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
}
.step-panel {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.form-grid { display: flex; flex-direction: column; gap: 16px; }
.form-row { display: grid; grid-template-columns: 100px 1fr; align-items: center; gap: 12px; }
.form-label { font-size: var(--text-label, 12px); font-weight: var(--weight-medium, 500); color: var(--color-text-secondary, #667085); }
.w-full { width: 100%; max-width: 480px; }
.check-list { display: flex; flex-direction: column; gap: 8px; }
.checkbox-grid { display: flex; flex-wrap: wrap; gap: 8px 16px; }
.locked-hint { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.locked-hint strong { color: var(--color-text-primary, #18212B); }
.locked-hint span { color: var(--color-text-secondary, #667085); font-size: 12px; }
.warning-strip { display: flex; flex-direction: column; gap: 8px; }
.warning-item {
  padding: 8px 12px;
  border-radius: var(--radius-md, 6px);
  background: var(--color-warning-bg, rgba(181,71,8,0.08));
  border: 1px solid rgba(245,158,11,0.24);
  color: var(--color-warning, #B54708);
  font-size: var(--text-caption, 12px);
}
.preview-table-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
}
.table-title { font-size: var(--text-card-title, 14px); font-weight: var(--weight-semibold, 600); color: var(--color-text-primary, #18212B); margin-bottom: 12px; }
.task-status-row { display: flex; align-items: center; gap: 12px; }
.task-actions { margin-top: 16px; }
.error-panel {
  margin-top: 12px; padding: 12px;
  border-radius: var(--radius-md, 6px);
  background: var(--color-danger-bg, rgba(217,45,32,0.08));
  border: 1px solid rgba(251,113,133,0.3);
}
.error-text { color: var(--color-danger, #D92D20); font-size: 13px; white-space: pre-wrap; }
.history-section {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}
.history-toggle {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px var(--card-padding, 16px);
  cursor: pointer;
  font-size: var(--text-card-title, 14px);
  font-weight: var(--weight-semibold, 600);
  color: var(--color-text-primary, #18212B);
}
.history-toggle:hover { background: var(--color-bg-surface-secondary, #F1F3F5); }
.history-content { padding: 0 var(--card-padding, 16px) var(--card-padding, 16px); }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.detail-item {
  padding: 10px 12px;
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border: 1px solid var(--color-border, #E3E7EC);
}
.detail-item span { display: block; font-size: 12px; color: var(--color-text-secondary, #667085); }
.detail-item strong { display: block; margin-top: 4px; color: var(--color-text-primary, #18212B); line-height: 1.5; }
.detail-item.full { grid-column: 1 / -1; }
.muted { color: var(--color-text-secondary, #667085); font-size: 12px; }
@media (max-width: 768px) {
  .form-row { grid-template-columns: 1fr; }
  .form-row .form-label { margin-bottom: 4px; }
}
</style>
