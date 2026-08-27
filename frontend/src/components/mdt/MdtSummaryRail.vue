<template>
  <a-card :bordered="false" class="mdt-rail-card">
    <div class="rail-patient">
      <span class="rail-label">患者</span>
      <strong>{{ patientHeadline }}</strong>
      <p>{{ patientSubline }}</p>
    </div>

    <div class="rail-meter">
      <div class="rail-meter__header">
        <span>{{ severityLabel }}</span>
        <b>{{ progressPercent }}%</b>
      </div>
      <div class="rail-meter__bar">
        <em :style="{ width: `${progressPercent}%` }"></em>
      </div>
      <small>{{ progressText }}</small>
    </div>

    <section class="rail-next">
      <span class="rail-label">下一步</span>
      <p>{{ nextActionText }}</p>
    </section>

    <section v-if="todoRows.length" class="rail-todos">
      <span class="rail-label">待办</span>
      <div class="rail-todo-list">
        <article v-for="(item, index) in todoRows.slice(0, 3)" :key="item.id || index">
          <strong>{{ shortAction(item.action) }}</strong>
          <small>{{ item.owner || '待定' }} · {{ item.deadline || '待定' }}</small>
        </article>
      </div>
    </section>
  </a-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Card as ACard } from 'ant-design-vue'

const props = defineProps<{
  patientHeadline: string
  patientSubline: string
  severityLabel: string
  decisionTotalCount: number
  pendingConfirmationCount: number
  completedDecisionCount: number
  closurePercent: number
  nextActionText: string
  todoRows: any[]
}>()

void ACard

const confirmationPercent = computed(() => {
  if (!props.decisionTotalCount) return 0
  const confirmed = Math.max(0, props.decisionTotalCount - props.pendingConfirmationCount)
  return Math.round((confirmed / props.decisionTotalCount) * 100)
})

const progressPercent = computed(() => {
  if (!props.decisionTotalCount) return 0
  return props.pendingConfirmationCount > 0 ? confirmationPercent.value : props.closurePercent
})

const progressText = computed(() => {
  if (!props.decisionTotalCount) return '尚未形成决议'
  if (props.pendingConfirmationCount > 0) return `医生确认 ${confirmationPercent.value}%（待确认 ${props.pendingConfirmationCount}）`
  return `闭环 ${props.closurePercent}%（${props.completedDecisionCount}/${props.decisionTotalCount}）`
})

function shortAction(text: any): string {
  const s = String(text || '').trim()
  return s.length > 36 ? `${s.slice(0, 36)}…` : s || '待补充'
}
</script>

<style scoped>
.mdt-rail-card {
  min-height: 100%;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.rail-label {
  display: block;
  color: var(--brand);
  font-size: 11px;
  font-weight: 700;
  margin-bottom: 4px;
}
.rail-patient strong {
  display: block;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 700;
}
.rail-patient p {
  margin: 2px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.rail-meter {
  margin: 14px 0;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.rail-meter__header {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 12px;
}
.rail-meter__header b {
  color: var(--text-primary);
  font-weight: 700;
}
.rail-meter__bar {
  height: 6px;
  margin: 8px 0;
  border-radius: 3px;
  background: var(--bg-surface-2);
  overflow: hidden;
}
.rail-meter__bar em {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--brand);
  transition: width 0.3s;
}
.rail-meter small {
  color: var(--text-secondary);
  font-size: 11px;
}
.rail-next {
  margin-bottom: 14px;
}
.rail-next p {
  margin: 0;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
}
.rail-todos {
  margin-top: 4px;
}
.rail-todo-list {
  display: grid;
  gap: 6px;
}
.rail-todo-list article {
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.rail-todo-list strong {
  display: block;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.4;
}
.rail-todo-list small {
  display: block;
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 11px;
}
</style>
