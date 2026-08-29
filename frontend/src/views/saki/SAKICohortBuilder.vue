<template>
  <div class="saki-cohort-builder">
    <div class="builder-panel">
      <h3>构建 S-AKI 队列</h3>
      <a-form layout="inline">
        <a-form-item label="队列名称">
          <a-input v-model:value="cohortName" style="width:200px" />
        </a-form-item>
        <a-form-item label="AKI分期">
          <a-select v-model:value="filters.aki_stage" placeholder="全部" allowClear style="width:120px">
            <a-select-option :value="1">Stage 1</a-select-option>
            <a-select-option :value="2">Stage 2</a-select-option>
            <a-select-option :value="3">Stage 3</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="仅S-AKI">
          <a-switch v-model:checked="filters.is_saki" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" @click="buildCohort" :loading="building">构建队列</a-button>
        </a-form-item>
      </a-form>
    </div>

    <div class="cohorts-list">
      <h3>已有队列</h3>
      <a-table :dataSource="cohorts" :columns="columns" :pagination="false" size="small" rowKey="cohort_id">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action'">
            <a-button type="link" size="small" @click="viewPatients(record)">查看</a-button>
            <a-popconfirm title="确认删除?" @confirm="deleteCohort(record.cohort_id)">
              <a-button type="link" size="small" danger>删除</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { buildSakiCohort, getSakiCohorts, deleteSakiCohort as apiDeleteCohort } from '../../api/saki'

const cohortName = ref('S-AKI 研究队列')
const filters = reactive<{ aki_stage?: number; is_saki?: boolean }>({})
const building = ref(false)
const cohorts = ref<any[]>([])

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '病例数', dataIndex: 'patient_count', key: 'patient_count', width: 100 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 120 },
]

const loadCohorts = async () => {
  try {
    const res = await getSakiCohorts()
    cohorts.value = res.data || []
  } catch (e) { console.warn(e) }
}

const buildCohort = async () => {
  building.value = true
  try {
    await buildSakiCohort({ name: cohortName.value, filters: { ...filters } })
    message.success('队列构建成功')
    loadCohorts()
  } catch (e) {
    message.error('构建失败')
  } finally {
    building.value = false
  }
}

const deleteCohort = async (id: string) => {
  try {
    await apiDeleteCohort(id)
    message.success('已删除')
    loadCohorts()
  } catch (e) {
    message.error('删除失败')
  }
}

const viewPatients = (record: any) => {
  message.info(`队列 ${record.name} 共 ${record.patient_count} 例`)
}

onMounted(loadCohorts)
</script>

<style scoped>
.saki-cohort-builder { display: flex; flex-direction: column; gap: 16px; }
.builder-panel { background: #fff; border-radius: 8px; padding: 16px; }
.builder-panel h3 { margin: 0 0 12px; }
.cohorts-list { background: #fff; border-radius: 8px; padding: 16px; }
.cohorts-list h3 { margin: 0 0 12px; }
</style>
