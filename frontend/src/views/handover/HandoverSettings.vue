<template>
  <div class="handover-settings">
    <header class="hs-header">
      <div>
        <h1 class="hs-title">班次与数据诊断</h1>
        <p class="hs-subtitle">核对交班时间窗是否正确、交班单取数是否完整——数据缺失时交班内容会偏少，需人工补充</p>
      </div>
      <a-button :loading="shiftLoading" @click="loadShifts(true)">重新读取班次配置</a-button>
    </header>

    <div class="hs-grid">
      <section class="hs-card">
        <h3 class="hs-card__title">班次配置</h3>
        <a-alert v-if="shiftError" type="error" show-icon :message="shiftError" />
        <template v-else>
          <div class="hs-meta">
            来源 {{ shiftMeta.source || '—' }} · 读取于 {{ formatDateTime(shiftMeta.loaded_at) }} ·
            有效 {{ shiftMeta.valid_count ?? 0 }} / 原始 {{ shiftMeta.raw_count ?? 0 }}
            <span v-if="shiftMeta.invalid_count" class="hs-warning">（{{ shiftMeta.invalid_count }} 条配置无效被忽略）</span>
          </div>
          <a-table :data-source="shifts" :columns="shiftColumns" size="small" :pagination="false" row-key="code">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'current'">
                <a-tag v-if="currentShift && currentShift.code === record.code" color="blue">当前</a-tag>
              </template>
            </template>
          </a-table>
          <div v-if="currentShift" class="hs-meta">
            当前班次：{{ currentShift.name }}（{{ formatDateTime(currentShift.scheduled_start) }} — {{ formatDateTime(currentShift.scheduled_end) }}）
          </div>
        </template>
      </section>

      <section class="hs-card">
        <h3 class="hs-card__title">患者交班取数诊断</h3>
        <div class="hs-row">
          <a-select
            v-model:value="diagPatientId"
            show-search
            :filter-option="filterPatient"
            :options="patientOptions"
            placeholder="选择床位"
            style="width: 260px"
            :loading="loading"
          />
          <a-button type="primary" :disabled="!diagPatientId" :loading="diagLoading" @click="runDiag">诊断</a-button>
        </div>
        <a-alert v-if="diagError" type="error" show-icon :message="diagError" class="hs-gap" />
        <template v-if="diag">
          <div class="hs-meta">
            时间窗 {{ formatDateTime(diag.time_window?.start) }} — {{ formatDateTime(diag.time_window?.end) }} ·
            快照 {{ formatDateTime(diag.data_snapshot_at) }}
          </div>
          <a-table :data-source="diagRows" :columns="diagColumns" size="small" :pagination="false" row-key="key">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <a-tag :color="record.status === 'available' ? 'green' : record.status === 'failed' ? 'red' : 'default'">
                  {{ SOURCE_STATUS[record.status] || record.status }}
                </a-tag>
              </template>
            </template>
          </a-table>
          <ul v-if="diag.warnings?.length" class="hs-warnings">
            <li v-for="w in diag.warnings" :key="w">{{ w }}</li>
          </ul>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Alert as AAlert, Button as AButton, Select as ASelect, Table as ATable, Tag as ATag } from 'ant-design-vue'
import api from '../../api'
import { formatDateTime, useShiftSummary } from '../../composables/useShiftSummary'

const SOURCE_LABELS: Record<string, string> = {
  vitals: '生命体征', labs: '检验', io: '出入量', pumps: '泵入用药', medications: '泵入用药',
  airway_vent: '气道/呼吸机', ventilator: '气道/呼吸机', lines: '管路', assessments: '护理评估',
  events: '护理事件', orders: '医嘱', alerts: '告警',
}
const SOURCE_STATUS: Record<string, string> = { available: '有数据', empty: '无数据', failed: '读取失败' }

const { patients, loading, load } = useShiftSummary()

const shiftLoading = ref(false)
const shiftError = ref('')
const shifts = ref<any[]>([])
const shiftMeta = ref<any>({})
const currentShift = ref<any>(null)
const shiftColumns = [
  { title: '编码', dataIndex: 'code', key: 'code', width: 90 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '开始', dataIndex: 'start_time', key: 'start_time', width: 80 },
  { title: '结束', dataIndex: 'end_time', key: 'end_time', width: 80 },
  { title: '', key: 'current', width: 60 },
]

async function loadShifts(refresh = false) {
  shiftLoading.value = true
  shiftError.value = ''
  try {
    const [list, cur] = await Promise.allSettled([
      api.get('/api/handover/shifts', { params: { refresh } }),
      api.get('/api/handover/shifts/current'),
    ])
    if (list.status === 'fulfilled') {
      shiftMeta.value = list.value.data || {}
      shifts.value = list.value.data?.shifts || []
    } else {
      const e: any = list.reason
      const d = e?.response?.data?.detail
      shiftError.value = (typeof d === 'object' ? d?.message : d) || e?.message || '读取班次配置失败'
    }
    currentShift.value = cur.status === 'fulfilled' ? cur.value.data : null
  } finally {
    shiftLoading.value = false
  }
}

const patientOptions = computed(() =>
  patients.value.map((p) => ({ value: p.patient_id, label: `${p.bed || '—'} 床 · ${p.name || ''}` })),
)
function filterPatient(input: string, option: any) {
  return String(option?.label || '').toLowerCase().includes(input.toLowerCase())
}

const diagPatientId = ref<string>()
const diagLoading = ref(false)
const diagError = ref('')
const diag = ref<any>(null)
const diagColumns = [
  { title: '数据源', dataIndex: 'label', key: 'label', width: 120 },
  { title: '状态', key: 'status', width: 90 },
  { title: '条数', dataIndex: 'count', key: 'count', width: 70 },
  { title: '来源表', dataIndex: 'source', key: 'source' },
]
const diagRows = computed(() =>
  Object.entries(diag.value?.sources || {}).map(([key, v]: [string, any]) => ({
    key,
    label: SOURCE_LABELS[key] || key,
    status: v?.status || 'empty',
    count: v?.count ?? '—',
    source: v?.source || '—',
  })),
)

async function runDiag() {
  if (!diagPatientId.value) return
  diagLoading.value = true
  diagError.value = ''
  try {
    const res = await api.get(`/api/handover/patients/${diagPatientId.value}/context-preview`, { params: { shift_code: 'auto' } })
    diag.value = res.data
  } catch (e: any) {
    const d = e?.response?.data?.detail
    diagError.value = (typeof d === 'object' ? d?.message : d) || e?.message || '诊断失败'
    diag.value = null
  } finally {
    diagLoading.value = false
  }
}

onMounted(() => {
  loadShifts()
  load()
})
</script>

<style scoped>
.handover-settings { padding: var(--page-padding, 24px); max-width: 1400px; margin: 0 auto; width: 100%; }
.hs-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.hs-title { margin: 0; font-size: var(--text-page-title, 20px); font-weight: 600; color: var(--color-text-primary); }
.hs-subtitle { margin: 4px 0 0; font-size: var(--text-body, 13px); color: var(--color-text-secondary); }
.hs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.hs-card { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg, 10px); padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.hs-card__title { margin: 0; font-size: var(--text-section-title, 15px); font-weight: 600; }
.hs-meta { font-size: var(--text-caption, 12px); color: var(--color-text-secondary); }
.hs-warning { color: var(--color-warning, #B54708); }
.hs-row { display: flex; gap: 8px; }
.hs-gap { margin-top: 4px; }
.hs-warnings { margin: 0; padding-left: 18px; font-size: var(--text-caption, 12px); color: var(--color-warning, #B54708); }
@media (max-width: 1024px) { .hs-grid { grid-template-columns: 1fr; } }
</style>
