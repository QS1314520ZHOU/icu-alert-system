<template>
  <div class="disease-cases-page">
    <!-- 筛选区 -->
    <div class="filter-bar">
      <a-select
        v-model:value="filterDisease"
        placeholder="筛选病种"
        allow-clear
        style="width: 180px"
        @change="handleFilter"
      >
        <a-select-option v-for="d in diseaseOptions" :key="d.id" :value="d.id">
          {{ d.name }}
        </a-select-option>
      </a-select>

      <a-select
        v-model:value="filterStatus"
        placeholder="病例状态"
        allow-clear
        style="width: 150px"
        @change="handleFilter"
      >
        <a-select-option v-for="s in statusOptions" :key="s.value" :value="s.value">
          {{ s.label }}
        </a-select-option>
      </a-select>

      <a-input-search
        v-model:value="searchText"
        placeholder="搜索患者 ID"
        style="width: 220px"
        @search="handleFilter"
      />

      <div class="filter-spacer" />

      <a-button @click="handleFilter">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
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
          <a-tag color="var(--color-primary-light, #e6f7f5)">
            <span style="color: var(--color-primary)">{{ record.disease_name || record.disease_code }}</span>
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
import { getDiseases, getAllCases, confirmCase } from '@/api/diseaseCenter'
import type { DiseaseCase, Disease } from '@/api/diseaseCenter'

const router = useRouter()

// --- filter state ---
const filterDisease = ref<string | undefined>(undefined)
const filterStatus = ref<string | undefined>(undefined)
const searchText = ref('')
const loading = ref(false)
const cases = ref<DiseaseCase[]>([])
const diseases = ref<Disease[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

const diseaseOptions = computed(() =>
  diseases.value.map((d: Disease) => ({ id: d.id, name: d.name }))
)

const statusOptions = [
  { value: 'screening', label: '筛查中' },
  { value: 'screen_positive', label: '筛查阳性' },
  { value: 'pending_review', label: '待临床确认' },
  { value: 'confirmed', label: '已纳入确认' },
  { value: 'excluded', label: '已排除' },
  { value: 'pathway_active', label: '路径执行中' },
  { value: 'completed', label: '已完成' },
  { value: 'reconsideration_pending', label: '待复核' },
  { value: 'reopened', label: '已重新打开' },
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
  screening: 'default',
  screen_positive: 'orange',
  pending_review: 'var(--color-primary-light)',
  confirmed: 'var(--color-success-light)',
  excluded: 'default',
  pathway_active: 'var(--color-primary)',
  completed: 'var(--color-success)',
  reconsideration_pending: 'orange',
  reopened: 'orange',
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
  return statusColorMap[status] || 'default'
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
async function loadDiseases() {
  try {
    const res = await getDiseases()
    diseases.value = res
  } catch {
    // diseases list optional
  }
}

async function loadCases() {
  loading.value = true
  try {
    const res = await getAllCases({
      disease_id: filterDisease.value,
      status: filterStatus.value,
      patient_id: searchText.value || undefined,
      page: currentPage.value,
      page_size: pageSize.value,
    })
    cases.value = res.items || []
    total.value = res.total || 0
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
  loadDiseases()
  loadCases()
})
</script>

<style scoped>
.disease-cases-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 12px);
}

.filter-spacer {
  flex: 1;
}

.risk-high {
  color: var(--color-error, #D92D20);
  font-weight: 600;
}

.risk-medium {
  color: var(--color-warning, #DC6803);
  font-weight: 500;
}

.risk-low {
  color: var(--color-success, #16845B);
}

:deep(.ant-table) {
  background: var(--color-bg-surface, #fff);
  border-radius: var(--radius-lg, 12px);
}

:deep(.ant-tag) {
  border-radius: var(--radius-md, 8px);
}
</style>
