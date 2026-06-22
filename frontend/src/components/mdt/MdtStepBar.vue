<template>
  <nav class="mdt-step-bar">
    <button
      v-for="step in steps"
      :key="step.key"
      type="button"
      :class="['mdt-step', { 'is-active': modelValue === step.key, 'is-done': step.done }]"
      @click="$emit('update:modelValue', step.key)"
    >
      <span>{{ step.index }}</span>
      <strong>{{ step.title }}</strong>
      <small>{{ step.desc }}</small>
      <em>{{ step.done ? '已完成' : '待完成' }}</em>
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
  gap: 10px;
  margin-top: 18px;
}
.mdt-step {
  position: relative;
  min-height: 86px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: var(--card-radius);
  text-align: left;
  cursor: pointer;
  color: var(--text-secondary);
  background: var(--bg-surface), 0.5);
}
.mdt-step::before {
  content: '';
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: 0;
  height: 3px;
  border-radius: var(--card-radius);
  background: rgba(51, 65, 85, 0.9);
}
.mdt-step.is-active {
  border-color: rgba(56, 189, 248, 0.6);
  box-shadow: var(--card-shadow);
  background: var(--bg-surface), var(--bg-surface));
}
.mdt-step.is-active::before {
  background: var(--chart-1);
}
.mdt-step.is-done::before {
  background: var(--success);
}
.mdt-step span,
.mdt-step em {
  color: rgba(125, 211, 252, 0.88);
  font-size: 12px;
  font-style: normal;
}
.mdt-step strong {
  display: block;
  margin: 7px 0 4px;
  color: var(--text-primary);
  font-size: 16px;
}
.mdt-step small {
  display: block;
  color: rgba(203, 213, 225, 0.68);
  line-height: 1.4;
}
.mdt-step em {
  position: absolute;
  right: 12px;
  top: 12px;
}
@media (max-width: 980px) {
  .mdt-step-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

:global(html[data-theme='light']) .mdt-step {
  color: var(--text-secondary);
  border-color: var(--chart-1);
  background: var(--bg-surface);
  box-shadow: var(--card-shadow);
}
:global(html[data-theme='light']) .mdt-step::before {
  background: var(--border-color);
}
:global(html[data-theme='light']) .mdt-step.is-active {
  border-color: var(--chart-1);
  background: var(--bg-surface);
  box-shadow: var(--card-shadow);
}
:global(html[data-theme='light']) .mdt-step.is-done::before {
  background: var(--success);
}
:global(html[data-theme='light']) .mdt-step span,
:global(html[data-theme='light']) .mdt-step em {
  color: var(--brand);
}
:global(html[data-theme='light']) .mdt-step strong {
  color: var(--text-primary);
}
:global(html[data-theme='light']) .mdt-step small {
  color: var(--text-secondary);
}
</style>
