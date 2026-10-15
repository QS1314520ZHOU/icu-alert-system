<template>
  <div class="disease-cases-page">
    <!-- 筛选区 -->
    <div class="filter-bar">
      <!-- 疾病筛选 chips -->
      <div class="filter-section">
        <span class="filter-label">疾病筛查</span>
        <div class="chip-group">
          <span
            v-for="d in diseaseConditions"
            :key="d.code"
            :class="['filter-chip', { active: filterDiseaseCode === d.code }]"
            :style="filterDiseaseCode === d.code ? { background: d.color + '18', borderColor: d.color, color: d.color } : {}"
            @click="toggleDiseaseChip(d.code)"
          >
            <i class="chip-dot" :style="{ background: d.color }"></i>
            {{ d.label }}
          </span>
        </div>
      </div>

      <!-- 状态筛选 chips -->
      <div class="filter-section">
        <span class="filter-label">病例状态</span>
        <div class="chip-group">
          <span
            v-for="s in statusOptions"
            :key="s.value"
            :class="['filter-chip', { active: filterStatus === s.value }]"
            :style="filterStatus === s.value ? { background: s.color + '18', borderColor: s.color, color: s.color } : {}"
            @click="toggleStatusChip(s.value)"
          >
            <i class="chip-dot" :style="{ background: s.color }"></i>
            {{ s.label }}
          </span>
        </div>
      </div>

      <!-- 搜索 + 刷新 -->
      <div class="filter-actions">
        <a-input-search
          v-model:value="searchText"
          placeholder="搜索患者 ID"
          style="width: 220px"
          @search="handleFilter"
          allow-clear
        />
        <a-button @click="handleFilter">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
    </div>

    <!-- 病例表格 -->
    <a-table
      :columns="columns"
      :data-source="cases"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="middle"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'patient_id'">
          <a @click="goCaseDetail(record.id)">{{ record.patient_id }}</a>
        </template>

        <template v-if="column.key === 'disease_name'">
          <a-tag color="var(--color-primary-bg, #EFF6FF)">
            <span style="color: var(--color-primary, #2563EB)">{{ record.disease_name || record.disease_code }}</span>
          </a-tag>
        </template>

        <template v-if="column.key === 'status'">
          <a-tag :color="getStatusColor(record.status)">
            {{ getStatusLabel(record.status) }}
          </a-tag>
        </template>

        <template v-if="column.key === 'risk_level'">
          <span :class="getRiskClass(record.risk_level)">{{ record.risk_level || '-' }}</span>
        </template>

        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button type="link" size="small" @click="goCaseDetail(record.id)">详情</a-button>
            <a-button
              v-if="record.status === 'pending_review'"
              type="link"
              size="small"
              @click="handleConfirm(record)"
            >
              确认
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <!-- 快速确认对话框 -->
    <a-modal
      v-model:open="confirmModalVisible"
      title="确认纳入病例"
      @ok="handleConfirmSubmit"
      @cancel="confirmModalVisible = false"
      :confirm-loading="confirmLoading"
    >
      <a-form layout="vertical">
        <a-form-item label="患者 ID">
          <a-input :value="confirmTarget?.patient_id" disabled />
        </a-form-item>
        <a-form-item label="确认原因" required>
          <a-textarea
            v-model:value="confirmReason"
            placeholder="请输入确认原因（必填）"
            :rows="3"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { getAllCases, confirmCase } from '@/api/diseaseCenter'
import type { DiseaseCase } from '@/api/diseaseCenter'

const router = useRouter()

// --- filter state ---
const filterDiseaseCode = ref('')
const filterStatus = ref<string | undefined>(undefined)

// 8个疾病筛查条件（code 需与后端 disease_code / 种子数据完全一致）
const diseaseConditions = [
  { code: 'PE', label: '肺栓塞', color: '#D92D20' },
  { code: 'SAP', label: '重症急性胰腺炎', color: '#DC6803' },
  { code: 'MODS', label: '多器官功能障碍综合征', color: '#F04438' },
  { code: 'DIC', label: '弥散性血管内凝血', color: '#B42318' },
  { code: 'SEPTIC_SHOCK', label: '感染性休克', color: '#E04F1A' },
  { code: 'AKI', label: '急性肾损伤', color: '#93370D' },
  { code: 'ARDS', label: '急性呼吸窘迫综合征', color: '#B54708' },
  { code: 'SEPSIS', label: '脓毒症', color: '#C4320A' },
]

function toggleDiseaseChip(code: string) {
  filterDiseaseCode.value = filterDiseaseCode.value === code ? '' : code
  handleFilter()
}

function toggleStatusChip(value: string) {
  filterStatus.value = filterStatus.value === value ? undefined : value
  handleFilter()
}
const searchText = ref('')
const loading = ref(false)
const cases = ref<DiseaseCase[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

const statusOptions = [
  { value: 'screening', label: '筛查中', color: '#667085' },
  { value: 'screen_positive', label: '筛查阳性', color: '#DC6803' },
  { value: 'pending_review', label: '待临床确认', color: '#2563EB' },
  { value: 'confirmed', label: '已纳入确认', color: '#16845B' },
  { value: 'excluded', label: '已排除', color: '#98A2B3' },
  { value: 'pathway_active', label: '路径执行中', color: '#1D6F63' },
  { value: 'completed', label: '已完成', color: '#0D7C66' },
  { value: 'reconsideration_pending', label: '待复核', color: '#B54708' },
  { value: 'reopened', label: '已重新打开', color: '#F04438' },
]

const columns = [
  { title: '患者 ID', key: 'patient_id', dataIndex: 'patient_id', width: 140 },
  { title: '关联病种', key: 'disease_name', dataIndex: 'disease_name', width: 150 },
  { title: '状态', key: 'status', dataIndex: 'status', width: 110 },
  { title: '风险等级', key: 'risk_level', dataIndex: 'risk_level', width: 100 },
  { title: '筛查时间', dataIndex: 'first_detected_at', width: 170,
    customRender: ({ text }: { text: string }) => text ? new Date(text).toLocaleString('zh-CN') : '-' },
  { title: '临床确认时间', dataIndex: 'confirmed_at', width: 170,
    customRender: ({ text }: { text: string }) => text ? new Date(text).toLocaleString('zh-CN') : '-' },
  { title: '操作', key: 'actions', width: 120, fixed: 'right' as const },
]

const pagination = computed(() => ({
  current: currentPage.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
}))

// --- helpers ---
const statusColorMap: Record<string, string> = {
  screening: '#d9d9d9',
  screen_positive: '#faad14',
  pending_review: '#1677ff',
  confirmed: '#52c41a',
  excluded: '#d9d9d9',
  pathway_active: '#1677ff',
  completed: '#389e0d',
  reconsideration_pending: '#fa8c16',
  reopened: '#fa541c',
}

const statusLabelMap: Record<string, string> = {
  screening: '筛查中',
  screen_positive: '筛查阳性',
  pending_review: '待临床确认',
  confirmed: '已纳入确认',
  excluded: '已排除',
  pathway_active: '路径执行中',
  completed: '已完成',
  reconsideration_pending: '待复核',
  reopened: '已重新打开',
}

function getStatusColor(status: string) {
  return statusColorMap[status] || '#d9d9d9'
}

function getStatusLabel(status: string) {
  return statusLabelMap[status] || status
}

function getRiskClass(level: string) {
  if (level === 'high' || level === 'critical') return 'risk-high'
  if (level === 'medium') return 'risk-medium'
  return 'risk-low'
}

// --- data loading ---
async function loadCases() {
  loading.value = true
  try {
    const res = await getAllCases({
      disease_code: filterDiseaseCode.value || undefined,
      status: filterStatus.value,
      patient_id: searchText.value || undefined,
      page: currentPage.value,
      page_size: pageSize.value,
    })
    cases.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (err: any) {
    message.error('加载病例失败: ' + (err.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function handleFilter() {
  currentPage.value = 1
  loadCases()
}

function handleTableChange(pag: any) {
  currentPage.value = pag.current || 1
  pageSize.value = pag.pageSize || 20
  loadCases()
}

function goCaseDetail(caseId: string) {
  router.push({ name: 'disease-center-case-detail', params: { caseId } })
}

// 确认对话框状态
const confirmModalVisible = ref(false)
const confirmLoading = ref(false)
const confirmTarget = ref<DiseaseCase | null>(null)
const confirmReason = ref('')

function handleConfirm(record: DiseaseCase) {
  confirmTarget.value = record
  confirmReason.value = ''
  confirmModalVisible.value = true
}

async function handleConfirmSubmit() {
  if (!confirmReason.value.trim()) {
    message.warning('请输入确认原因')
    return
  }
  if (!confirmTarget.value) return
  confirmLoading.value = true
  try {
    await confirmCase(confirmTarget.value.id, {
      action: 'confirm',
      reason: confirmReason.value.trim(),
    })
    message.success('已确认纳入')
    confirmModalVisible.value = false
    loadCases()
  } catch (err: any) {
    message.error('确认失败: ' + (err.message || '未知错误'))
  } finally {
    confirmLoading.value = false
  }
}

onMounted(() => {
  loadCases()
})
</script>

<style scoped>.disease-cases-page { display: flex; flex-direction: column; gap: 16px }
.filter-bar { display: flex; flex-direction: column; gap: 14px; padding: 16px; background: var(--color-bg-surface, #FFFFFF); border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-lg, 10px) }
.filter-section { display: flex; align-items: flex-start; gap: 10px }
.filter-label { flex-shrink: 0; min-width: 64px; font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); line-height: 28px }
.chip-group { display: flex; flex-wrap: wrap; gap: 8px }
.filter-chip { display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 10px; border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB); background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-secondary, #4B5563); font-size: var(--text-caption, 12px); font-weight: 500; cursor: pointer; transition: all 0.15s ease; white-space: nowrap }
.filter-chip:hover { border-color: var(--color-primary, #2563EB); color: var(--color-primary, #2563EB) }
.filter-chip.active { font-weight: 600 }
.chip-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0 }
.filter-actions { display: flex; align-items: center; gap: 10px }
.risk-high { color: var(--color-danger, #D92D20); font-weight: 600 }
.risk-medium { color: var(--color-warning, #B54708); font-weight: 500 }
.risk-low { color: var(--color-success, #16845B) }
:deep(.ant-table) { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px) }
:deep(.ant-tag) { border-radius: var(--radius-md, 6px) }


/* ── 表格规范 §7 ── */
:deep(.ant-table-thead > tr > th) {
  background: var(--color-bg-surface-secondary, #F1F4F8);
  color: var(--color-text-secondary, #4B5563);
  font-size: var(--text-label, 12px);
  font-weight: var(--text-table-header-weight, 600);
}
:deep(.ant-table-thead > tr > th::before) { display: none !important }
:deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--color-divider, #F0F2F5);
  font-size: var(--text-table, 13px);
  color: var(--color-text-primary, #111827);
}
:deep(.ant-table-tbody > tr:hover > td) { background: var(--color-bg-inset, #E9EEF5) }
:deep(.ant-table-tbody > tr > td) { font-variant-numeric: tabular-nums }
:deep(.ant-table-pagination) { margin-bottom: 0 !important }
</style>
