<template>
  <header class="mdt-header">
    <div>
      <div class="mdt-kicker">ICU MDT</div>
      <h1>多学科会诊工作流</h1>
      <p>{{ patientHeadline || '先选择患者，再生成本轮 MDT 会诊。' }}</p>
    </div>
    <div class="mdt-header__badges">
      <span class="mdt-badge">{{ patientLabel }}</span>
      <span :class="['mdt-badge', `is-${severityTone}`]">风险 {{ severityLabel }}</span>
      <span class="mdt-badge">闭环 {{ closurePercent }}%</span>
      <span v-if="pendingConfirmationCount" class="mdt-badge is-warning">待确认 {{ pendingConfirmationCount }}</span>
      <span v-if="workspaceDirty" class="mdt-badge is-warning">未保存</span>
      <span v-if="isSessionClosed" class="mdt-badge is-closed">已归档只读</span>
      <a-button @click="$emit('open-session-drawer')">历史会话</a-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Button as AButton } from 'ant-design-vue'

defineProps<{
  patientLabel: string
  patientHeadline: string
  severityLabel: string
  severityTone: string
  closurePercent: number
  pendingConfirmationCount: number
  workspaceDirty: boolean
  isSessionClosed: boolean
}>()

defineEmits<{
  (event: 'open-session-drawer'): void
}>()

void AButton
</script>

<style scoped>
.mdt-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}
.mdt-kicker {
  color: rgba(125, 211, 252, 0.9);
  font-size: 12px;
  letter-spacing: 0;
  font-weight: 700;
}
h1 {
  margin: 4px 0 6px;
  color: #f8fafc;
  font-size: 26px;
  line-height: 1.15;
}
p {
  margin: 0;
  color: rgba(226, 232, 240, 0.72);
}
.mdt-header__badges {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
.mdt-badge {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  color: #e2e8f0;
  background: rgba(15, 23, 42, 0.54);
  font-size: 13px;
}
.mdt-badge.is-critical {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.45);
  background: rgba(127, 29, 29, 0.45);
}
.mdt-badge.is-warning {
  color: #fed7aa;
  border-color: rgba(251, 146, 60, 0.42);
  background: rgba(124, 45, 18, 0.38);
}
.mdt-badge.is-closed,
.mdt-badge.is-soft {
  color: #bbf7d0;
  border-color: rgba(74, 222, 128, 0.35);
  background: rgba(20, 83, 45, 0.32);
}
@media (max-width: 980px) {
  .mdt-header {
    flex-direction: column;
  }
  .mdt-header__badges {
    justify-content: flex-start;
  }
}

:global(html[data-theme='light']) .mdt-kicker {
  color: #0284c7;
}
:global(html[data-theme='light']) h1 {
  color: #0f172a;
}
:global(html[data-theme='light']) p {
  color: #475569;
}
:global(html[data-theme='light']) .mdt-badge {
  color: #334155;
  border-color: #cbd5e1;
  background: #f8fafc;
}
:global(html[data-theme='light']) .mdt-badge.is-critical {
  color: #991b1b;
  border-color: #fecaca;
  background: #fef2f2;
}
:global(html[data-theme='light']) .mdt-badge.is-warning {
  color: #9a3412;
  border-color: #fed7aa;
  background: #fff7ed;
}
:global(html[data-theme='light']) .mdt-badge.is-closed,
:global(html[data-theme='light']) .mdt-badge.is-soft {
  color: #166534;
  border-color: #bbf7d0;
  background: #f0fdf4;
}
</style>
