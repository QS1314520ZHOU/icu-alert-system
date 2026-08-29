<template>
  <aside class="consult-sessions">
    <div class="consult-sessions__header">
      <span class="consult-sessions__title">会话</span>
      <a-button size="small" type="primary" @click="$emit('new-session')">新建</a-button>
    </div>
    <div class="consult-sessions__list">
      <div v-if="!sessions.length" class="consult-sessions__empty">
        暂无会话，点击新建开始
      </div>
      <div
        v-for="session in sessions"
        :key="session.id"
        :class="['consult-sessions__item', { 'is-active': session.id === currentSessionId }]"
        @click="$emit('switch-session', session.id)"
      >
        <div class="consult-sessions__label">{{ session.label }}</div>
        <div class="consult-sessions__meta">
          <span class="consult-sessions__patient">{{ session.patientLabel }}</span>
          <span class="consult-sessions__time">{{ formatRelativeTime(session.updatedAt) }}</span>
        </div>
        <button
          class="consult-sessions__delete"
          title="删除会话"
          @click.stop="$emit('delete-session', session.id)"
        >
          ×
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
interface Session {
  id: string
  label: string
  patientLabel: string
  updatedAt: string | number | Date
}

defineProps<{
  sessions: Session[]
  currentSessionId: string
}>()

defineEmits<{
  'new-session': []
  'switch-session': [id: string]
  'delete-session': [id: string]
}>()

function formatRelativeTime(time: string | number | Date): string {
  if (!time) return ''
  const d = new Date(time)
  if (isNaN(d.getTime())) return ''
  const now = Date.now()
  const diff = now - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.consult-sessions {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-right: 1px solid var(--color-border, #E3E7EC);
  background: var(--color-bg-surface, #FFFFFF);
}

.consult-sessions__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #E3E7EC);
}

.consult-sessions__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.consult-sessions__list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.consult-sessions__empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--color-text-secondary, #667085);
  font-size: 13px;
}

.consult-sessions__item {
  position: relative;
  padding: 10px 12px;
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: background 0.15s;
}

.consult-sessions__item:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.consult-sessions__item.is-active {
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  border-left: 3px solid var(--color-primary, #2563EB);
}

.consult-sessions__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.consult-sessions__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.consult-sessions__patient {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.consult-sessions__delete {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #667085);
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.consult-sessions__item:hover .consult-sessions__delete {
  opacity: 1;
}

.consult-sessions__delete:hover {
  background: var(--color-danger-bg, rgba(217, 45, 32, 0.08));
  color: var(--color-danger, #D92D20);
}

@media (max-width: 390px) {
  .consult-sessions {
    display: none;
  }
}
</style>
