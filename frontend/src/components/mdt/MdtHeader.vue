<template>
  <header class="mdt-header">
    <div class="mdt-header__left">
      <div class="mdt-kicker">ICU MDT</div>
      <h1>多学科会诊</h1>
    </div>
    <div class="mdt-header__right">
      <span v-if="patientLabel && patientLabel !== '未选择患者'" class="header-tag">{{ patientLabel }}</span>
      <span :class="['header-tag', `tone-${severityTone}`]">{{ severityLabel }}</span>
      <span v-if="closurePercent > 0" class="header-tag">闭环 {{ closurePercent }}%</span>
      <span v-if="pendingConfirmationCount" class="header-tag tone-warning">待确认 {{ pendingConfirmationCount }}</span>
      <a-button size="small" @click="$emit('open-session-drawer')">历史会话</a-button>
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
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.mdt-header__left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.mdt-kicker {
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 20px;
  font-weight: 700;
}
.mdt-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.header-tag {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  color: var(--text-secondary);
  background: var(--bg-surface);
  font-size: 12px;
}
.header-tag.tone-critical {
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}
.header-tag.tone-warning {
  border-color: rgba(245, 158, 11, 0.3);
  color: #f59e0b;
}
.header-tag.tone-soft {
  border-color: rgba(16, 185, 129, 0.3);
  color: #10b981;
}
@media (max-width: 720px) {
  .mdt-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .mdt-header__right {
    flex-wrap: wrap;
  }
}
</style>
