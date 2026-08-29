<template>
  <div class="ack-panel">
    <h4 class="ack-title">✅ 接班签收</h4>

    <!-- Forced confirmations -->
    <div v-if="forcedItems.length" class="forced-section">
      <div class="forced-header">
        <span>⚠️ 强制确认项（{{ confirmedCount }}/{{ forcedItems.length }}）</span>
      </div>
      <a-checkbox-group v-model:value="checkedIds" @change="onCheckChange">
        <div v-for="item in forcedItems" :key="item.item_id" class="forced-item">
          <a-checkbox :value="item.item_id">
            <span :class="{ 'text-danger': item.item_type === 'critical_value' }">
              {{ item.description }}
            </span>
          </a-checkbox>
        </div>
      </a-checkbox-group>
    </div>

    <div v-else class="no-forced">无强制确认项</div>

    <div class="ack-actions">
      <span class="operator-label">签收人：{{ operator || '未登录' }}</span>
      <a-button
        type="primary"
        :disabled="!canAcknowledge"
        :loading="loading"
        @click="emit('acknowledge')"
      >
        确认签收
      </a-button>
      <a-button
        v-if="status === 'submitted'"
        :loading="loading"
        @click="emit('reject')"
      >
        退回修改
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Checkbox as ACheckbox,
  CheckboxGroup as ACheckboxGroup,
  Button as AButton,
} from 'ant-design-vue'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

const props = defineProps<{
  forcedItems: Array<{
    item_id: string
    item_type: string
    description: string
    confirmed: boolean
  }>
  status: string
  loading: boolean
}>()

const emit = defineEmits<{
  acknowledge: []
  reject: []
  'update:forcedItems': [items: any[]]
}>()

const operator = computed(() => authStore.effectiveUserId || authStore.userName || '')
const checkedIds = ref<(string | number | boolean)[]>(
  props.forcedItems.filter((f) => f.confirmed).map((f) => f.item_id)
)

const confirmedCount = computed(() => checkedIds.value.length)
const canAcknowledge = computed(
  () => operator.value && confirmedCount.value === props.forcedItems.length
)

function onCheckChange(ids: (string | number | boolean)[]) {
  checkedIds.value = ids
  const idSet = new Set(ids.map(String))
  const updated = props.forcedItems.map((f) => ({
    ...f,
    confirmed: idSet.has(f.item_id),
  }))
  emit('update:forcedItems', updated)
}
</script>

<style scoped>
.ack-panel {
  padding: 12px 16px;
  background: var(--bg-surface);
  border-radius: var(--card-radius);
  border: 1px solid var(--border-color, #334155);
}
.ack-title {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--text-main);
}
.forced-section {
  margin-bottom: 12px;
}
.forced-header {
  font-size: 13px;
  color: #f59e0b;
  margin-bottom: 6px;
  font-weight: 600;
}
.forced-item {
  padding: 4px 0;
}
.text-danger { color: var(--danger, #ef4444); }
.no-forced {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}
.ack-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.operator-label {
  font-size: 13px;
  color: var(--text-secondary, #5F6B7A);
  padding: 4px 8px;
  background: var(--bg-elevated, #F4F7FB);
  border-radius: 4px;
}
</style>
