<template>
  <span :class="['status-badge', `status-badge--${variant}`]">
    <span v-if="dot" class="status-badge__dot" />
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
interface Props {
  variant?: 'danger' | 'warning' | 'success' | 'info' | 'default'
  label?: string
  dot?: boolean
}

withDefaults(defineProps<Props>(), {
  variant: 'default',
  dot: false,
})
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-tag, 4px);
  font-size: var(--text-label, 12px);
  font-weight: var(--weight-medium, 500);
  line-height: 1.5;
  white-space: nowrap;
}

.status-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-badge--danger {
  background: var(--color-danger-bg, rgba(217, 45, 32, 0.08));
  color: var(--color-danger, #D92D20);
}

.status-badge--danger .status-badge__dot {
  background: var(--color-danger, #D92D20);
}

.status-badge--warning {
  background: var(--color-warning-bg, rgba(181, 71, 8, 0.08));
  color: var(--color-warning, #B54708);
}

.status-badge--warning .status-badge__dot {
  background: var(--color-warning, #B54708);
}

.status-badge--success {
  background: var(--color-success-bg, rgba(22, 132, 91, 0.08));
  color: var(--color-success, #16845B);
}

.status-badge--success .status-badge__dot {
  background: var(--color-success, #16845B);
}

.status-badge--info {
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  color: var(--color-primary, #2563EB);
}

.status-badge--info .status-badge__dot {
  background: var(--color-primary, #2563EB);
}

.status-badge--default {
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-secondary, #667085);
}

.status-badge--default .status-badge__dot {
  background: var(--color-text-secondary, #667085);
}
</style>
