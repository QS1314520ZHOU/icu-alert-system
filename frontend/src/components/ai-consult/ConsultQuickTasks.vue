<template>
  <div class="consult-quick-tasks">
    <button
      v-for="task in tasks"
      :key="task.label"
      class="consult-quick-tasks__btn"
      type="button"
      :disabled="disabled"
      @click="$emit('select', task.prompt)"
    >
      {{ task.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
interface QuickTask {
  label: string
  prompt: string
}

defineProps<{
  tasks: QuickTask[]
  disabled?: boolean
}>()

defineEmits<{
  select: [prompt: string]
}>()
</script>

<style scoped>
.consult-quick-tasks {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.consult-quick-tasks__btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  background: var(--color-bg-surface, #FFFFFF);
  color: var(--color-primary, #2563EB);
  border: 1px solid var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  border-radius: var(--radius-md, 6px);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.consult-quick-tasks__btn:hover:not(:disabled) {
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  border-color: var(--color-primary, #2563EB);
}

.consult-quick-tasks__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 390px) {
  .consult-quick-tasks {
    gap: 6px;
  }

  .consult-quick-tasks__btn {
    height: 28px;
    padding: 0 10px;
    font-size: 12px;
  }
}
</style>
