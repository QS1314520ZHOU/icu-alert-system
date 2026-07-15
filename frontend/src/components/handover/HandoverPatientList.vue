<template>
  <div class="patient-list">
    <div class="list-toolbar">
      <a-input-search
        v-model:value="localSearch"
        placeholder="搜索姓名/床号..."
        size="small"
        style="width: 100%"
        @search="onSearch"
      />
    </div>
    <a-spin :spinning="loading">
      <div v-if="!patients.length && !loading" class="empty-hint">暂无患者数据</div>
      <div
        v-for="p in filteredPatients"
        :key="p.patient_id"
        class="patient-card"
        :class="{ active: p.patient_id === activePatientId }"
        @click="emit('select', p)"
      >
        <div class="card-top">
          <span class="bed-badge">{{ p.bed || '?' }}</span>
          <span class="patient-name">{{ p.name || '—' }}</span>
          <a-tag v-if="p.has_draft" color="blue" size="small">草稿</a-tag>
          <a-tag v-else-if="p.status === 'submitted'" color="orange" size="small">待签</a-tag>
          <a-tag v-else-if="p.status === 'acknowledged'" color="green" size="small">已签</a-tag>
        </div>
        <div class="card-meta">
          <span>{{ p.diagnosis || '—' }}</span>
        </div>
        <div v-if="p.has_critical" class="card-alert">
          ⚠️ {{ p.critical_count }}条危急值
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { InputSearch as AInputSearch, Spin as ASpin, Tag as ATag } from 'ant-design-vue'

export interface PatientBrief {
  patient_id: string
  bed: string
  name: string
  diagnosis: string
  has_draft: boolean
  status: string
  has_critical: boolean
  critical_count: number
}

const props = defineProps<{
  patients: PatientBrief[]
  activePatientId: string
  loading: boolean
  searchText: string
}>()

const emit = defineEmits<{
  select: [patient: PatientBrief]
  search: [text: string]
  'update:searchText': [text: string]
}>()

const localSearch = ref(props.searchText)
watch(() => props.searchText, (v) => { localSearch.value = v })

function onSearch(value: string) {
  localSearch.value = value
  emit('search', value)
  emit('update:searchText', value)
}

const filteredPatients = computed(() => {
  if (!localSearch.value) return props.patients
  const q = localSearch.value.toLowerCase()
  return props.patients.filter(
    (p) =>
      p.name?.toLowerCase().includes(q) ||
      p.bed?.toLowerCase().includes(q) ||
      p.patient_id?.toLowerCase().includes(q)
  )
})
</script>

<style scoped>
.patient-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 100%;
  overflow-y: auto;
}
.list-toolbar {
  padding: 8px;
  position: sticky;
  top: 0;
  background: var(--bg-base);
  z-index: 2;
}
.patient-card {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  background: var(--bg-surface);
  border: 1px solid transparent;
  transition: all 0.15s;
}
.patient-card:hover {
  border-color: var(--accent);
}
.patient-card.active {
  border-color: var(--accent);
  background: rgba(56, 189, 248, 0.08);
}
.card-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.bed-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 22px;
  border-radius: 4px;
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.patient-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-main);
}
.card-meta {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-alert {
  font-size: 11px;
  color: var(--danger, #ef4444);
  margin-top: 4px;
}
.empty-hint {
  text-align: center;
  color: var(--text-secondary);
  padding: 24px;
  font-size: 13px;
}
</style>
