<template>
  <nav class="mdt-step-bar">
    <button
      v-for="step in steps"
      :key="step.key"
      type="button"
      :class="[
        'mdt-step',
        {
          'is-active': modelValue === step.key,
          'is-done': step.done,
          'is-pending': !step.done && modelValue !== step.key,
        },
      ]"
      @click="$emit('update:modelValue', step.key)"
    >
      <span class="mdt-step__index">{{ step.index }}</span>
      <span class="mdt-step__title">{{ step.title }}</span>
      <span v-if="step.done" class="mdt-step__check">✓</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
export interface MdtStepRow {
  key: 'patient' | 'review' | 'decision' | 'archive'
  index: string
  title: string
  desc: string
  done: boolean
}

defineProps<{
  modelValue: MdtStepRow['key']
  steps: MdtStepRow[]
}>()

defineEmits<{
  (event: 'update:modelValue', value: MdtStepRow['key']): void
}>()
</script>

<style scoped>
.mdt-step-bar {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}
.mdt-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.mdt-step__index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-surface-2);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.mdt-step__title {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
}
.mdt-step__check {
  margin-left: auto;
  color: #10b981;
  font-size: 14px;
}
.mdt-step.is-active {
  border-color: var(--brand);
  background: var(--bg-surface);
}
.mdt-step.is-active .mdt-step__index {
  background: var(--brand);
  color: #fff;
}
.mdt-step.is-active .mdt-step__title {
  color: var(--text-primary);
  font-weight: 600;
}
.mdt-step.is-done .mdt-step__index {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}
.mdt-step.is-done .mdt-step__title {
  color: var(--text-primary);
}
@media (max-width: 720px) {
  .mdt-step-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
