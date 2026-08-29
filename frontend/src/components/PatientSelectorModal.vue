<template>
  <a-modal
    :open="open"
    title="选择患者"
    :width="560"
    :footer="null"
    @cancel="onCancel"
  >
    <div class="selector-body">
      <!-- 搜索框 -->
      <div class="selector-search">
        <input
          v-model.trim="searchQuery"
          class="selector-input"
          type="text"
          placeholder="输入患者姓名、床号搜索..."
          @input="onSearch"
        />
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="selector-loading">加载中...</div>

      <!-- 患者列表 -->
      <div v-else-if="filteredPatients.length > 0" class="selector-list">
        <button
          v-for="p in filteredPatients"
          :key="p._id || p.id"
          class="selector-item"
          @click="onSelectPatient(p)"
        >
          <span class="selector-item__bed">{{ p.bed || '-' }}床</span>
          <span class="selector-item__name">{{ p.name || p.patient_name || '未知' }}</span>
          <span class="selector-item__meta">
            {{ p.gender || '' }} {{ p.age ? p.age + '岁' : '' }}
          </span>
          <span class="selector-item__dept">{{ p.dept || '' }}</span>
        </button>
      </div>

      <!-- 空状态 -->
      <div v-else class="selector-empty">
        {{ searchQuery ? '未找到匹配患者' : '暂无患者数据' }}
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { getPatients } from '../api'
import { useAuthStore } from '../stores/auth'
import { useNavigationContext } from '../navigation/useNavigationContext'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'select', patientId: string): void
  (e: 'cancel'): void
}>()

const auth = useAuthStore()
const navCtx = useNavigationContext()

const searchQuery = ref('')
const loading = ref(false)
const patients = ref<any[]>([])

const filteredPatients = computed(() => {
  if (!searchQuery.value) return patients.value
  const q = searchQuery.value.toLowerCase()
  return patients.value.filter(p => {
    const name = (p.name || p.patient_name || '').toLowerCase()
    const bed = String(p.bed || '').toLowerCase()
    return name.includes(q) || bed.includes(q)
  })
})

async function loadPatients() {
  loading.value = true
  try {
    const params: any = {}
    if (navCtx.deptCode.value) params.dept_code = navCtx.deptCode.value
    else if (auth.deptCode) params.dept_code = auth.deptCode
    const res = await getPatients(params)
    patients.value = res.data?.patients || res.data || []
  } catch (err) {
    console.error('[PatientSelectorModal] Failed to load patients:', err)
    patients.value = []
  } finally {
    loading.value = false
  }
}

function onSearch() {
  // Filtering is reactive via computed
}

function onSelectPatient(patient: any) {
  const patientId = patient._id || patient.id || ''
  if (patientId) {
    emit('select', String(patientId))
  }
}

function onCancel() {
  emit('cancel')
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    searchQuery.value = ''
    loadPatients()
  }
})
</script>

<style scoped>
.selector-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 480px;
}

.selector-search {
  position: sticky;
  top: 0;
  z-index: 1;
}

.selector-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-border, #DCE3EC);
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}

.selector-input:focus {
  border-color: var(--color-primary, #2563EB);
}

.selector-loading {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary, #52606D);
  font-size: 13px;
}

.selector-list {
  overflow-y: auto;
  max-height: 400px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.selector-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s;
  text-align: left;
  width: 100%;
  font-size: 13px;
}

.selector-item:hover {
  background: var(--color-bg-hover, #F0F6FF);
}

.selector-item__bed {
  min-width: 40px;
  font-weight: 600;
  color: var(--color-primary, #2563EB);
  font-size: 12px;
}

.selector-item__name {
  font-weight: 600;
  color: var(--text-primary, #182230);
  flex: 1;
}

.selector-item__meta {
  font-size: 12px;
  color: var(--text-tertiary, #94A3B8);
}

.selector-item__dept {
  font-size: 11px;
  color: var(--text-tertiary, #94A3B8);
  padding: 1px 6px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border-radius: 3px;
}

.selector-empty {
  padding: 32px;
  text-align: center;
  color: var(--text-tertiary, #94A3B8);
  font-size: 13px;
}
</style>
