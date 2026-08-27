<template>
  <div class="empty-state">
    <div class="empty-state__icon">
      <slot name="icon">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <path d="M24 4C12.96 4 4 12.96 4 24s8.96 20 20 20 20-8.96 20-20S35.04 4 24 4zm0 36c-8.84 0-16-7.16-16-16S15.16 8 24 8s16 7.16 16 16-7.16 16-16 16zm-2-22h4v12h-4V18zm0 16h4v4h-4v-4z" fill="currentColor"/>
        </svg>
      </slot>
    </div>
    <div class="empty-state__content">
      <h3 class="empty-state__title">
        <slot name="title">{{ title }}</slot>
      </h3>
      <p v-if="description || $slots.description" class="empty-state__description">
        <slot name="description">{{ description }}</slot>
      </p>
    </div>
    <div v-if="$slots.action" class="empty-state__action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  title?: string
  description?: string
}

defineProps<Props>()
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-state__icon {
  color: var(--color-text-secondary, #667085);
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state__content {
  max-width: 400px;
}

.empty-state__title {
  font-size: var(--text-section-title, 16px);
  font-weight: var(--weight-semibold, 600);
  color: var(--color-text-primary, #18212B);
  margin: 0 0 8px 0;
}

.empty-state__description {
  font-size: var(--text-body, 14px);
  color: var(--color-text-secondary, #667085);
  line-height: 1.5;
  margin: 0;
}

.empty-state__action {
  margin-top: 24px;
}
</style>
