<template>
  <a-card :bordered="false" class="mdt-rail-card">
    <span class="rail-label">当前患者</span>
    <strong>{{ patientHeadline }}</strong>
    <p>{{ patientSubline }}</p>

    <div class="rail-meter">
      <div>
        <span>风险</span>
        <b>{{ severityLabel }}</b>
      </div>
      <i><em :style="{ width: `${progressPercent}%` }"></em></i>
      <small>{{ progressText }}</small>
    </div>

    <section class="rail-next">
      <span class="rail-label">下一步</span>
      <p>{{ nextActionText }}</p>
    </section>

    <section>
      <span class="rail-label">待办</span>
      <div v-if="todoRows.length" class="rail-todo-list">
        <article v-for="(item, index) in todoRows.slice(0, 5)" :key="item.id || index">
          <strong>{{ item.action || '待补充决议内容' }}</strong>
          <small>{{ item.owner || '负责人待定' }} / {{ item.deadline || '时限待定' }}</small>
        </article>
      </div>
      <div v-else class="rail-empty">暂无待办，进入决议确认后会显示。</div>
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
  if (props.pendingConfirmationCount > 0) {
    return `医生确认 ${confirmationPercent.value}%（待确认 ${props.pendingConfirmationCount} 条）`
  }
  return `决议闭环 ${props.closurePercent}%（已完成 ${props.completedDecisionCount}/${props.decisionTotalCount}）`
})
</script>

<style scoped>
.mdt-rail-card {
  min-height: 100%;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.66);
}
.rail-label {
  display: block;
  color: rgba(125, 211, 252, 0.82);
  font-size: 12px;
  font-weight: 700;
}
strong {
  display: block;
  margin-top: 6px;
  color: #f8fafc;
  font-size: 20px;
}
p {
  margin: 8px 0 0;
  color: rgba(203, 213, 225, 0.76);
  line-height: 1.55;
}
.rail-meter {
  margin: 18px 0;
  padding: 14px;
  border-radius: 10px;
  background: rgba(30, 41, 59, 0.58);
}
.rail-meter div {
  display: flex;
  justify-content: space-between;
  color: rgba(203, 213, 225, 0.76);
}
.rail-meter b {
  color: #f8fafc;
}
.rail-meter i {
  display: block;
  height: 8px;
  margin: 12px 0 8px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(51, 65, 85, 0.9);
}
.rail-meter em {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #38bdf8, #22c55e);
}
.rail-meter small,
.rail-todo-list small {
  color: rgba(148, 163, 184, 0.8);
}
.rail-next {
  margin-bottom: 18px;
}
.rail-todo-list {
  display: grid;
  gap: 10px;
}
.rail-todo-list article {
  padding: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.26);
}
.rail-todo-list strong {
  margin: 0 0 4px;
  font-size: 14px;
}
.rail-empty {
  margin-top: 8px;
  color: rgba(148, 163, 184, 0.8);
}

:global(html[data-theme='light']) .mdt-rail-card {
  border-color: #dbeafe;
  background: #ffffff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
:global(html[data-theme='light']) .rail-label {
  color: #0284c7;
}
:global(html[data-theme='light']) strong,
:global(html[data-theme='light']) .rail-meter b,
:global(html[data-theme='light']) .rail-todo-list strong {
  color: #0f172a;
}
:global(html[data-theme='light']) p {
  color: #475569;
}
:global(html[data-theme='light']) .rail-meter {
  border: 1px solid #dbeafe;
  background: #f8fafc;
}
:global(html[data-theme='light']) .rail-meter div {
  color: #475569;
}
:global(html[data-theme='light']) .rail-meter i {
  background: #dbeafe;
}
:global(html[data-theme='light']) .rail-meter small,
:global(html[data-theme='light']) .rail-todo-list small,
:global(html[data-theme='light']) .rail-empty {
  color: #64748b;
}
:global(html[data-theme='light']) .rail-todo-list article {
  border-color: #e2e8f0;
  background: #f8fafc;
}
</style>
