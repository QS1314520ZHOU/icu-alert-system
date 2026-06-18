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
  border-radius: 10px;
  text-align: left;
  cursor: pointer;
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.5);
}
.mdt-step::before {
  content: '';
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: 0;
  height: 3px;
  border-radius: 999px;
  background: rgba(51, 65, 85, 0.9);
}
.mdt-step.is-active {
  border-color: rgba(56, 189, 248, 0.6);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.18), 0 16px 36px rgba(8, 47, 73, 0.28);
  background: linear-gradient(135deg, rgba(14, 116, 144, 0.38), rgba(15, 23, 42, 0.72));
}
.mdt-step.is-active::before {
  background: #38bdf8;
}
.mdt-step.is-done::before {
  background: #22c55e;
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
  color: #f8fafc;
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
  color: #475569;
  border-color: #dbeafe;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
}
:global(html[data-theme='light']) .mdt-step::before {
  background: #cbd5e1;
}
:global(html[data-theme='light']) .mdt-step.is-active {
  border-color: #38bdf8;
  background: linear-gradient(135deg, #e0f2fe, #ffffff);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.22), 0 12px 28px rgba(14, 116, 144, 0.12);
}
:global(html[data-theme='light']) .mdt-step.is-done::before {
  background: #22c55e;
}
:global(html[data-theme='light']) .mdt-step span,
:global(html[data-theme='light']) .mdt-step em {
  color: #0284c7;
}
:global(html[data-theme='light']) .mdt-step strong {
  color: #0f172a;
}
:global(html[data-theme='light']) .mdt-step small {
  color: #64748b;
}
</style>
