<template>
  <div class="saki-case-list">
    <div class="filter-bar">
      <a-select v-model:value="filters.aki_stage" placeholder="AKI分期" allowClear style="width:120px">
        <a-select-option :value="0">Stage 0</a-select-option>
        <a-select-option :value="1">Stage 1</a-select-option>
        <a-select-option :value="2">Stage 2</a-select-option>
        <a-select-option :value="3">Stage 3</a-select-option>
      </a-select>
      <a-select v-model:value="filters.review_status" placeholder="审核状态" allowClear style="width:120px">
        <a-select-option value="pending">待审</a-select-option>
        <a-select-option value="confirmed">已确认</a-select-option>
        <a-select-option value="rejected">已驳回</a-select-option>
      </a-select>
      <a-button type="primary" @click="loadCases">查询</a-button>
      <a-button @click="resetFilters">重置</a-button>
    </div>

    <a-table :dataSource="cases" :columns="columns" :loading="loading" :pagination="pagination" @change="handleTableChange" size="middle" rowKey="patient_id">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'aki_stage'">
          <a-tag :color="stageColor(record.aki_stage)">Stage {{ record.aki_stage }}</a-tag>
        </template>
        <template v-if="column.key === 'is_saki'">
          <a-tag :color="record.is_saki ? 'red' : 'green'">{{ record.is_saki ? 'S-AKI' : '否' }}</a-tag>
        </template>
        <template v-if="column.key === 'action'">
          <a-button type="link" size="small" @click="goDetail(record)">详情</a-button>
        </template>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getSakiCases } from '../../api/saki'

const router = useRouter()
const loading = ref(false)
const cases = ref<any[]>([])
const filters = reactive<{ aki_stage?: number; review_status?: string }>({})
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const columns = [
  { title: '患者ID', dataIndex: 'patient_id', key: 'patient_id', width: 120 },
  { title: '科室', dataIndex: 'department', key: 'department' },
  { title: 'AKI分期', key: 'aki_stage', width: 100 },
  { title: 'S-AKI', key: 'is_saki', width: 80 },
  { title: '概率', dataIndex: 'saki_probability', key: 'saki_probability', width: 80 },
  { title: '审核', dataIndex: 'review_status', key: 'review_status', width: 80 },
  { title: '操作', key: 'action', width: 80 },
]

const stageColor = (s: number) => ['green', 'orange', 'red', 'volcano'][s] || 'default'

const loadCases = async () => {
  loading.value = true
  try {
    const res = await getSakiCases({ page: pagination.current, page_size: pagination.pageSize, ...filters })
    cases.value = res.data?.cases || []
    pagination.total = res.data?.total || 0
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pag: any) => {
  pagination.current = pag.current
  loadCases()
}

const resetFilters = () => {
  Object.keys(filters).forEach(k => delete (filters as any)[k])
  pagination.current = 1
  loadCases()
}

const goDetail = (record: any) => {
  router.push({ name: 'saki-case-detail', params: { caseId: record.patient_id } })
}

onMounted(loadCases)
</script>

<style scoped>
.saki-case-list { display: flex; flex-direction: column; gap: 16px; }
.filter-bar { display: flex; gap: 12px; align-items: center; background: #fff; padding: 12px 16px; border-radius: 8px; }
</style>
