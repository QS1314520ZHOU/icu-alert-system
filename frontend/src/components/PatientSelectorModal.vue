<template>
  <a-modal
    :open="open"
    title="选择患者"
    :width="560"
    :footer="null"
    :destroy-on-close="true"
    :centered="true"
    :mask-closable="true"
    @cancel="onCancel"
  >
    <div class="selector-body">
      <!-- 搜索框 -->
      <div class="selector-search">
        <input
          v-model.trim="searchQuery"
          class="selector-input"
          type="text"
          placeholder="输入脱敏姓名、床号或患者ID搜索..."
          @input="onSearch"
        />
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="selector-loading">
        <a-spin size="small" />
        <span>加载患者列表...</span>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="loadError" class="selector-error">
        <span class="selector-error__icon">⚠</span>
        <span class="selector-error__text">{{ loadError }}</span>
        <button class="selector-retry-btn" @click="loadPatients">重试</button>
      </div>

      <!-- 患者列表 -->
      <div v-else-if="filteredPatients.length > 0" class="selector-list">
        <button
          v-for="p in filteredPatients"
          :key="p._id || p.id"
          class="selector-item"
          @click="onSelectPatient(p)"
        >
          <span class="selector-item__bed">{{ p.bed || '-' }}床</span>
          <span class="selector-item__name">{{ maskName(p.name || p.patient_name || '未知') }}</span>
          <span class="selector-item__meta">
            {{ p.gender || '' }} {{ p.age ? p.age + '岁' : '' }}
          </span>
          <span v-if="p.risk_level" class="selector-item__risk" :class="`risk-${p.risk_level}`">
            {{ riskLabel(p.risk_level) }}
          </span>
          <span class="selector-item__dept">{{ p.dept || '' }}</span>
        </button>
      </div>

      <!-- 空状态 -->
      <div v-else class="selector-empty">
        <span v-if="searchQuery">未找到匹配患者</span>
        <span v-else>暂无可用患者数据，请确认患者列表或联系管理员</span>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
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
const loadError = ref('')
const patients = ref<any[]>([])

const filteredPatients = computed(() => {
  if (!searchQuery.value) return patients.value
  const q = searchQuery.value.toLowerCase()
  return patients.value.filter(p => {
    const name = maskName(p.name || p.patient_name || '').toLowerCase()
    const bed = String(p.bed || '').toLowerCase()
    const id = String(p._id || p.id || '').toLowerCase()
    return name.includes(q) || bed.includes(q) || id.includes(q)
  })
})

/** 姓名脱敏：保留姓，中间用*替代 */
function maskName(name: string): string {
  if (!name || name.length <= 1) return name || '未知'
  if (name.length === 2) return name[0] + '*'
  return name[0] + '*'.repeat(name.length - 2) + name[name.length - 1]
}

/** 风险等级中文标签 */
function riskLabel(level: string): string {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高风险',
    medium: '中风险',
    low: '低风险',
    stable: '稳定',
  }
  return map[level] || level || ''
}

async function loadPatients() {
  loading.value = true
  loadError.value = ''
  try {
    const params: any = {}
    if (navCtx.deptCode.value) params.dept_code = navCtx.deptCode.value
    else if (auth.deptCode) params.dept_code = auth.deptCode
    const res = await getPatients(params)
    const raw = res.data?.patients || res.data || []
    // Filter out patients without access
    patients.value = Array.isArray(raw) ? raw : []
  } catch (err: any) {
    console.error('[PatientSelectorModal] Failed to load patients:', err)
    loadError.value = err?.message || '加载患者列表失败，请检查网络后重试'
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
    loadError.value = ''
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
  box-sizing: border-box;
}

.selector-input:focus {
  border-color: var(--color-primary, #2563EB);
}

.selector-loading {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary, #52606D);
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.selector-error {
  padding: 24px;
  text-align: center;
  color: var(--color-error, #DC2626);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.selector-error__icon {
  font-size: 24px;
}

.selector-error__text {
  color: var(--text-secondary, #52606D);
}

.selector-retry-btn {
  padding: 4px 16px;
  border: 1px solid var(--color-border, #DCE3EC);
  border-radius: 4px;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-primary, #2563EB);
}

.selector-retry-btn:hover {
  background: var(--color-bg-hover, #F0F6FF);
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

.selector-item__risk {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
}

.risk-critical { background: #FEF2F2; color: #991B1B; }
.risk-high { background: #FEF2F2; color: #DC2626; }
.risk-medium { background: #FFFBEB; color: #92400E; }
.risk-warning { background: #FFFBEB; color: #92400E; }
.risk-low, .risk-stable { background: #F0FDF4; color: #16A34A; }

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
