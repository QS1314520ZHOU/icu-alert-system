<template>
  <transition name="fade">
    <div v-if="open" class="cb-mask" @click.self="handleMask">
      <div class="cb-panel" ref="panelRef">
        <header class="cb-header">
          <div>
            <h3>队列构建器</h3>
            <p>根据筛选条件实时预览患者队列，保存后可直接用于数据准备</p>
          </div>
          <AButton type="text" class="cb-close" @click="emitClose">✕</AButton>
        </header>

        <section class="cb-section">
          <div class="cb-section-head">
            <span>常用筛选预设</span>
          </div>
          <div class="preset-row">
            <AButton
              v-for="preset in presets"
              :key="preset.key"
              size="small"
              type="default"
              :class="['preset-btn', { active: activePresetKey === preset.key }]"
              @click="applyPreset(preset)"
            >
              {{ preset.label }}
            </AButton>
          </div>
          <div class="filter-head">
            <span>筛选条件</span>
            <AButton size="small" type="default" class="add-btn" @click="addCondition()">+ 添加条件</AButton>
          </div>
          <transition-group name="row-fade" tag="div" class="filters">
            <div v-for="(row, idx) in rows" :key="row.id" class="filter-row">
              <div class="row-index">条件{{ idx + 1 }}</div>
              <ASelect
                v-model:value="row.field"
                :options="fieldOptions"
                placeholder="字段"
                style="width: 150px"
                :get-popup-container="getPopupContainer"
                @change="onFieldChange(row)"
              />
              <ASelect
                v-model:value="row.operator"
                :options="operatorOptions(row.field)"
                style="width: 120px"
                placeholder="操作符"
                :get-popup-container="getPopupContainer"
                @change="onOperatorChange(row)"
              />
              <div class="value-cell">
                <template v-if="valueType(row) === 'number'">
                  <AInputNumber v-model:value="row.value" style="width: 140px" />
                </template>
                <template v-else-if="valueType(row) === 'range'">
                  <div class="range-inputs">
                    <AInputNumber v-model:value="row.value[0]" placeholder="最小" style="width: 120px" />
                    <span>~</span>
                    <AInputNumber v-model:value="row.value[1]" placeholder="最大" style="width: 120px" />
                  </div>
                </template>
                <template v-else-if="valueType(row) === 'select'">
                  <ASelect
                    v-model:value="row.value"
                    :options="valueOptions(row.field)"
                    style="width: 160px"
                    :get-popup-container="getPopupContainer"
                  />
                </template>
                <template v-else-if="valueType(row) === 'bool'">
                  <ASelect
                    v-model:value="row.value"
                    :options="boolOptions"
                    style="width: 140px"
                    :get-popup-container="getPopupContainer"
                  />
                </template>
                <template v-else-if="valueType(row) === 'date-range'">
                  <ARangePicker v-model:value="row.value" show-time :get-popup-container="getPopupContainer" />
                </template>
                <template v-else>
                  <AInput v-model:value="row.value" placeholder="关键字" />
                </template>
              </div>
              <AButton type="text" size="small" class="remove-btn" @click="removeRow(row.id)">×</AButton>
            </div>
          </transition-group>
        </section>

        <section class="cb-section">
          <div class="cb-section-head">
            <span>队列预览</span>
            <small>符合条件：{{ preview.patient_count ?? 0 }} 例</small>
          </div>
          <div v-if="loading" class="cb-loading">正在计算...</div>
          <div v-else>
            <div v-if="!preview.patient_count" class="cb-empty">未找到符合条件的患者，请调整筛选条件</div>
            <template v-else>
              <div class="demo-grid">
                <div>
                  <div>年龄</div>
                  <strong>{{ formatStat(preview.demographics?.age_mean, preview.demographics?.age_std) }}</strong>
                </div>
                <div>
                  <div>男性比例</div>
                  <strong>{{ formatPercent(preview.demographics?.male_ratio) }}</strong>
                </div>
                <div>
                  <div>重症监护住院天数（四分位距）</div>
                  <strong>{{ formatLos(preview.demographics) }}</strong>
                </div>
                <div>
                  <div>器官衰竭评分（入科）</div>
                  <strong>{{ formatStat(preview.demographics?.sofa_mean, preview.demographics?.sofa_std) }}</strong>
                </div>
                <div>
                  <div>死亡率</div>
                  <strong>{{ formatPercent(preview.demographics?.mortality_rate) }}</strong>
                </div>
              </div>
              <ATable
                class="preview-table"
                size="small"
                :pagination="false"
                :columns="previewColumns"
                :data-source="preview.preview_patients || []"
                :row-key="previewRowKey"
              />
            </template>
          </div>
        </section>

        <footer class="cb-footer">
          <div class="cb-name-row">
            <span>队列名称：</span>
            <AInput v-model:value="cohortName" placeholder="请输入队列名称（如：脓毒症研究队列）" style="width: 360px" />
          </div>
          <div class="cb-footer-actions">
            <AButton @click="emitClose">取消</AButton>
            <AButton type="primary" :loading="saving" :disabled="!preview.patient_count" @click="saveCohort">
              保存并使用此队列
            </AButton>
          </div>
        </footer>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import {
  Button as AButton,
  DatePicker,
  Input as AInput,
  InputNumber as AInputNumber,
  Modal,
  Select as ASelect,
  Table as ATable,
  message,
} from 'ant-design-vue'
import { Dayjs } from 'dayjs'
import { postResearchCohortBuild, postResearchCohortSave } from '../api'

interface FilterCondition {
  field: string
  operator: string
  value: any
}

interface PreviewPayload {
  patient_count?: number
  demographics?: Record<string, any>
  preview_patients?: Array<Record<string, any>>
  patient_ids?: string[]
}

type RangeValue = [number | null, number | null]
type DateRange = [Dayjs | null, Dayjs | null]

const props = defineProps<{
  open: boolean
  department?: string | null
  deptCode?: string | null
  patientScope?: 'in_dept' | 'out_dept' | 'all' | null
  initialFilters?: Array<{ field: string; operator: string; value: any }>
}>()

const emit = defineEmits<{
  (e: 'update:open', val: boolean): void
  (e: 'saved', payload: { cohort: any; filters: FilterCondition[] }): void
}>()
const ARangePicker = DatePicker.RangePicker
const panelRef = ref<HTMLElement | null>(null)

const createRowId = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2))

const rows = ref<Array<{ id: string; field: string; operator: string; value: any }>>([
  { id: createRowId(), field: 'diagnosis', operator: 'contains', value: '' },
])
const preview = reactive<PreviewPayload>({ patient_count: 0, demographics: {}, preview_patients: [], patient_ids: [] })
const loading = ref(false)
const saving = ref(false)
const cohortName = ref('')
const activePresetKey = ref('')
let buildTimer: ReturnType<typeof setTimeout> | null = null
let presetTimer: ReturnType<typeof setTimeout> | null = null
let buildSeq = 0

const previewRowKey = (record: Record<string, any>) => String(record?.id || record?.name || Math.random().toString(36))

const presets = [
  { key: 'sepsis', label: '脓毒症患者', filter: { field: 'diagnosis', operator: 'contains', value: '脓毒症' } },
  { key: 'sofa', label: '高器官衰竭评分(≥8)', filter: { field: 'sofa_max', operator: 'gte', value: 8 } },
  { key: 'los', label: '长期重症监护(≥7天)', filter: { field: 'los_icu_days', operator: 'gte', value: 7 } },
  { key: 'crrt', label: '连续肾脏替代治疗患者', filter: { field: 'crrt', operator: 'eq', value: 'yes' } },
  { key: 'mv', label: '机械通气患者', filter: { field: 'mechanical_ventilation', operator: 'eq', value: 'yes' } },
  { key: 'elderly', label: '高龄(≥65岁)', filter: { field: 'age', operator: 'gte', value: 65 } },
]

const fieldOptions = [
  {
    label: '人口学',
    options: [
      { label: '年龄', value: 'age' },
      { label: '性别', value: 'sex' },
    ],
  },
  {
    label: '评分',
    options: [
      { label: '器官衰竭评分最高分（SOFA）', value: 'sofa_max' },
      { label: '急性生理与慢性健康评分最高分（APACHE II）', value: 'apache2_max' },
    ],
  },
  {
    label: '治疗',
    options: [
      { label: '是否机械通气', value: 'mechanical_ventilation' },
      { label: '是否连续肾脏替代治疗（CRRT）', value: 'crrt' },
      { label: '是否使用血管活性药', value: 'vasopressor' },
    ],
  },
  {
    label: '住院信息',
    options: [
      { label: '诊断', value: 'diagnosis' },
      { label: '主要诊断分类', value: 'primary_category' },
      { label: '重症监护住院天数', value: 'los_icu_days' },
      { label: '入科时间', value: 'admission_time' },
    ],
  },
  { label: '结局', options: [{ label: '结局', value: 'outcome' }] },
  { label: '预警', options: [{ label: '预警类型', value: 'alert_type' }] },
]

const boolOptions = [
  { label: '是', value: 'yes' },
  { label: '否', value: 'no' },
]

const previewColumns = [
  { title: '患者编号', dataIndex: 'id' },
  {
    title: '年龄',
    dataIndex: 'age',
    customRender: ({ text }: any) => (text != null ? Math.floor(Number(text)) : '--'),
  },
  { title: '性别', dataIndex: 'sex' },
  { title: '诊断', dataIndex: 'diagnosis' },
  {
    title: '重症监护天数',
    dataIndex: 'los_days',
    customRender: ({ text }: any) => {
      const num = Number(text)
      return Number.isFinite(num) ? num.toFixed(1) : '--'
    },
  },
  { title: '结局', dataIndex: 'outcome' },
]

function operatorOptions(field: string): Array<{ label: string; value: string }> {
  const numeric = ['age', 'los_icu_days', 'sofa_max', 'apache2_max']
  if (numeric.includes(field)) {
    return [
      { label: '=', value: 'eq' },
      { label: '>', value: 'gt' },
      { label: '<', value: 'lt' },
      { label: '>=', value: 'gte' },
      { label: '<=', value: 'lte' },
      { label: '范围', value: 'range' },
    ]
  }
  if (field === 'admission_time') return [{ label: '范围', value: 'range' }]
  if (field === 'diagnosis') return [{ label: '包含', value: 'contains' }, { label: '不包含', value: 'not_contains' }]
  if (field === 'primary_category') return [{ label: '包含', value: 'contains' }, { label: '等于', value: 'eq' }]
  if (field === 'alert_type') return [{ label: '存在', value: 'exists' }, { label: '不存在', value: 'not_exists' }]
  return [{ label: '等于', value: 'eq' }]
}

function valueType(row: { field: string; operator: string }): string {
  if (row.field === 'admission_time') return 'date-range'
  if (['mechanical_ventilation', 'crrt', 'vasopressor'].includes(row.field)) return 'bool'
  if (['sex', 'outcome', 'alert_type'].includes(row.field)) return 'select'
  if (row.field === 'primary_category') return row.operator === 'contains' ? 'text' : 'select'
  if (['age', 'los_icu_days', 'sofa_max', 'apache2_max'].includes(row.field)) return row.operator === 'range' ? 'range' : 'number'
  return 'text'
}

function valueOptions(field: string) {
  if (field === 'sex') return [{ label: '男', value: 'M' }, { label: '女', value: 'F' }]
  if (field === 'outcome') return [{ label: '重症监护内死亡', value: 'dead' }, { label: '存活出科', value: 'alive' }]
  if (field === 'alert_type') return [
    { label: '脓毒症预警器', value: 'SepsisScanner' },
    { label: '急性肾损伤预警器', value: 'AkiScanner' },
    { label: '休克预警器', value: 'ShockScanner' },
  ]
  return []
}

function addCondition() {
  rows.value.push({ id: createRowId(), field: 'diagnosis', operator: 'contains', value: '' })
}

function getPopupContainer(trigger?: HTMLElement): HTMLElement {
  if (panelRef.value) return panelRef.value
  if (trigger?.parentElement) return trigger.parentElement
  return document.body
}

function removeRow(id: string) {
  rows.value = rows.value.filter((row) => row.id !== id)
  scheduleBuild()
}

function onFieldChange(row: { field: string; operator: string; value: any }) {
  row.operator = operatorOptions(row.field)[0]?.value || 'eq'
  resetRowValue(row)
}

function onOperatorChange(row: { field: string; operator: string; value: any }) {
  resetRowValue(row)
}

function resetRowValue(row: { field: string; operator: string; value: any }) {
  const type = valueType(row)
  if (type === 'range') {
    row.value = [null, null] as RangeValue
    return
  }
  if (type === 'date-range') {
    row.value = [null, null] as DateRange
    return
  }
  row.value = ''
}

function normalizeValue(row: { field: string; operator: string; value: any }) {
  const numeric = ['age', 'los_icu_days', 'sofa_max', 'apache2_max']
  if (numeric.includes(row.field)) {
    if (row.operator === 'range' && Array.isArray(row.value)) return row.value
    return row.value == null || row.value === '' ? null : Number(row.value)
  }
  if (valueType(row) === 'range' && Array.isArray(row.value)) {
    return row.value
  }
  if (valueType(row) === 'date-range' && Array.isArray(row.value) && row.value.length === 2) {
    return row.value.map((d: Dayjs) => d?.toISOString())
  }
  return row.value
}

function buildFilters(): FilterCondition[] {
  return rows.value
    .filter((row) => row.field)
    .map((row) => ({ field: row.field, operator: row.operator, value: normalizeValue(row) }))
}

function scheduleBuild() {
  if (!props.open) return
  if (buildTimer) clearTimeout(buildTimer)
  buildTimer = setTimeout(runBuild, 800)
}

function apiErrorMessage(error: any, fallback: string): string {
  return error?.response?.data?.detail || error?.message || fallback
}

async function runBuild() {
  if (!props.open) return
  const seq = ++buildSeq
  loading.value = true
  try {
    const res = await postResearchCohortBuild({
      department: props.department,
      dept_code: props.deptCode,
      patient_scope: props.patientScope || 'all',
      filters: buildFilters(),
    })
    const data = res.data || {}
    if (seq !== buildSeq) return
    preview.patient_count = data.patient_count || 0
    preview.demographics = data.demographics || {}
    preview.preview_patients = data.preview_patients || []
    preview.patient_ids = data.patient_ids || []
  } catch (e: any) {
    message.error(apiErrorMessage(e, '队列预览失败'))
  } finally {
    if (seq === buildSeq) loading.value = false
  }
}

async function saveCohort() {
  if (!preview.patient_count) {
    message.warning('没有可保存的队列')
    return
  }
  saving.value = true
  try {
    const res = await postResearchCohortSave({
      name: cohortName.value || '自定义队列',
      department: props.department,
      dept_code: props.deptCode,
      patient_scope: props.patientScope || 'all',
      filters: buildFilters(),
    })
    emit('saved', { cohort: res.data, filters: buildFilters() })
    message.success('队列已保存')
    emitClose()
  } catch (e: any) {
    message.error(apiErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

function emitClose() {
  emit('update:open', false)
}

function handleMask() {
  Modal.confirm({
    title: '确定要关闭队列构建器吗？',
    content: '未保存的筛选条件将会丢失',
    onOk() {
      emitClose()
    },
  })
}

function formatStat(mean?: number, std?: number) {
  if (mean == null) return '--'
  return `${mean?.toFixed(1)} ± ${std?.toFixed(1) ?? 0}`
}

function formatPercent(value?: number) {
  if (value == null) return '--'
  return `${(value * 100).toFixed(1)}%`
}

function formatLos(demo: Record<string, any> | undefined) {
  if (!demo) return '--'
  const fmt = (value: any) => {
    const num = Number(value)
    return Number.isFinite(num) ? num.toFixed(1) : '--'
  }
  return `${fmt(demo.los_median)}（四分位距 ${fmt(demo.los_q1)}-${fmt(demo.los_q3)}）`
}

function applyPreset(preset: { key: string; filter: FilterCondition }) {
  const exists = rows.value.some((row) => row.field === preset.filter.field && row.operator === preset.filter.operator)
  if (!exists) rows.value.push({ id: createRowId(), ...preset.filter })
  activePresetKey.value = preset.key
  if (presetTimer) clearTimeout(presetTimer)
  presetTimer = setTimeout(() => {
    activePresetKey.value = ''
  }, 1000)
  scheduleBuild()
}

function hydrateRowsFromFilters(filters: Array<{ field: string; operator: string; value: any }> | undefined): void {
  const incoming = Array.isArray(filters) ? filters : []
  if (!incoming.length) {
    rows.value = [{ id: createRowId(), field: 'diagnosis', operator: 'contains', value: '' }]
    return
  }
  rows.value = incoming.map((item) => ({
    id: createRowId(),
    field: String(item.field || 'diagnosis'),
    operator: String(item.operator || 'eq'),
    value: Array.isArray(item.value) ? [...item.value] : item.value,
  }))
}

watch(
  () => props.open,
  (val) => {
    if (val) {
      hydrateRowsFromFilters(props.initialFilters)
      scheduleBuild()
    }
  },
)

watch(
  rows,
  () => {
    scheduleBuild()
  },
  { deep: true },
)
</script>

<style scoped>
.cb-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.cb-panel {
  width: 900px;
  max-height: 80vh;
  overflow-y: auto;
  background: linear-gradient(180deg, #0a1628 0%, #081224 100%);
  border: 1px solid rgba(0, 210, 210, 0.22);
  border-radius: 14px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.45);
  position: relative;
  pointer-events: auto;
}
.cb-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.cb-header h3 {
  margin: 0;
  color: #e5fbff;
}
.cb-header p {
  margin: 4px 0 0;
  color: rgba(255, 255, 255, 0.72);
}
.cb-close {
  color: rgba(255, 255, 255, 0.72);
  font-size: 18px;
}
.cb-close:hover {
  color: #9ceeff;
}
.cb-section {
  background: rgba(8, 24, 40, 0.58);
  border: 1px solid rgba(0, 210, 210, 0.15);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cb-section-head {
  display: flex;
  justify-content: space-between;
  color: rgba(255, 255, 255, 0.85);
}
.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.preset-btn {
  height: 28px;
  border-color: rgba(0, 210, 210, 0.25);
  background: rgba(0, 210, 210, 0.04);
  color: rgba(220, 244, 255, 0.92);
}
.preset-row :deep(.ant-btn.active) {
  border-color: rgba(0, 210, 210, 0.7);
  color: #8ef6ff;
  box-shadow: 0 0 0 2px rgba(0, 210, 210, 0.15);
}
.filter-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: rgba(255, 255, 255, 0.85);
}
.add-btn {
  border-color: rgba(0, 210, 210, 0.3);
  color: #9eeeff;
  background: rgba(0, 210, 210, 0.06);
}
.filters {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.filter-row {
  display: flex;
  gap: 12px;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 4px 0 12px;
  pointer-events: auto;
}
.row-index {
  width: 56px;
  color: rgba(170, 220, 240, 0.82);
  font-size: 12px;
}
.filter-row :deep(.ant-select-selector),
.filter-row :deep(.ant-input-number),
.filter-row :deep(.ant-input),
.cb-footer :deep(.ant-input) {
  background: rgba(0, 0, 0, 0.3) !important;
  border-color: rgba(0, 210, 210, 0.24) !important;
}
.filter-row :deep(.ant-select-selection-item),
.filter-row :deep(.ant-select-selection-placeholder),
.filter-row :deep(.ant-input-number-input),
.filter-row :deep(.ant-input),
.cb-footer :deep(.ant-input) {
  color: rgba(255, 255, 255, 0.9) !important;
}
.value-cell {
  flex: 1;
  pointer-events: auto;
}
.remove-btn {
  min-width: 28px;
  height: 28px;
  border-radius: 6px;
  color: rgba(255, 180, 180, 0.9);
}
.remove-btn:hover {
  background: rgba(255, 77, 79, 0.12);
  color: #ffb3b3;
}
.range-inputs {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cb-loading,
.cb-empty {
  padding: 20px;
  text-align: center;
  color: rgba(255, 255, 255, 0.7);
}
.cb-empty {
  color: #ffb970;
}
.demo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.demo-grid div {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 10px;
  color: rgba(255, 255, 255, 0.75);
}
.row-fade-enter-active,
.row-fade-leave-active {
  transition: all 0.2s ease;
}
.row-fade-enter-from,
.row-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
.demo-grid strong {
  display: block;
  color: #fff;
  margin-top: 4px;
}
.preview-table :deep(.ant-table-thead > tr > th),
.preview-table :deep(.ant-table-tbody > tr > td) {
  font-size: 12px;
  height: 32px;
  padding-top: 6px;
  padding-bottom: 6px;
}
.cb-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  position: sticky;
  bottom: 0;
  background: rgba(7, 18, 32, 0.95);
  backdrop-filter: blur(6px);
  padding-bottom: 4px;
}
.cb-name-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: rgba(220, 244, 255, 0.92);
}
.cb-footer-actions {
  display: flex;
  gap: 12px;
}
.cb-panel :deep(.ant-select-dropdown),
.cb-panel :deep(.ant-picker-dropdown) {
  z-index: 2300;
}

/* Light mode overrides */
html[data-theme='light'] .cb-panel { background: #ffffff; border-color: rgba(187,204,220,0.72); box-shadow: 0 14px 40px rgba(15,23,42,0.1); }
html[data-theme='light'] .cb-header h3 { color: #16324f; }
html[data-theme='light'] .cb-header p { color: #6a8098; }
html[data-theme='light'] .cb-close { color: #6a8098; }
html[data-theme='light'] .cb-close:hover { color: #16324f; }
html[data-theme='light'] .cb-section { background: rgba(243, 248, 252, 0.96); border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .cb-section-head { color: #16324f; }
html[data-theme='light'] .preset-btn { background: #ffffff; border-color: rgba(187,204,220,0.72); color: #47627e; }
html[data-theme='light'] .preset-row :deep(.ant-btn.active) { border-color: #3b82f6; color: #1d4ed8; box-shadow: 0 0 0 2px rgba(59,130,246,0.15); }
html[data-theme='light'] .filter-head { color: #16324f; }
html[data-theme='light'] .add-btn { background: #ffffff; border-color: rgba(187,204,220,0.72); color: #2563eb; }
html[data-theme='light'] .filter-row { border-bottom-color: rgba(187,204,220,0.4); }
html[data-theme='light'] .row-index { color: #6f8399; }
html[data-theme='light'] .filter-row :deep(.ant-select-selector), html[data-theme='light'] .filter-row :deep(.ant-input-number), html[data-theme='light'] .filter-row :deep(.ant-input), html[data-theme='light'] .cb-footer :deep(.ant-input) { background: #ffffff !important; border-color: rgba(187,204,220,0.72) !important; color: #223a54 !important; }
html[data-theme='light'] .filter-row :deep(.ant-select-selection-item), html[data-theme='light'] .filter-row :deep(.ant-select-selection-placeholder), html[data-theme='light'] .filter-row :deep(.ant-input-number-input), html[data-theme='light'] .filter-row :deep(.ant-input), html[data-theme='light'] .cb-footer :deep(.ant-input) { color: #223a54 !important; }
html[data-theme='light'] .remove-btn { color: #ef4444; }
html[data-theme='light'] .remove-btn:hover { background: rgba(239,68,68,0.12); color: #b91c1c; }
html[data-theme='light'] .cb-loading, html[data-theme='light'] .cb-empty { color: #6a8098; }
html[data-theme='light'] .cb-empty { color: #d97706; }
html[data-theme='light'] .demo-grid div { background: #ffffff; border: 1px solid rgba(187,204,220,0.72); color: #6f8399; }
html[data-theme='light'] .demo-grid strong { color: #16324f; }
html[data-theme='light'] .cb-footer { border-top-color: rgba(187,204,220,0.4); background: rgba(255,255,255,0.95); }
html[data-theme='light'] .cb-name-row { color: #47627e; }
</style>
