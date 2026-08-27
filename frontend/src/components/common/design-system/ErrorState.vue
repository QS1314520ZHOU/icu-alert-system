<template>
  <div class="error-state">
    <div class="error-state__icon">
      <slot name="icon">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <path d="M24 4C12.96 4 4 12.96 4 24s8.96 20 20 20 20-8.96 20-20S35.04 4 24 4zm0 36c-8.84 0-16-7.16-16-16S15.16 8 24 8s16 7.16 16 16-7.16 16-16 16zm-2-28h4v16h-4V12zm0 20h4v4h-4v-4z" fill="currentColor"/>
        </svg>
      </slot>
    </div>
    <div class="error-state__content">
      <h3 class="error-state__title">
        <slot name="title">{{ title }}</slot>
      </h3>
      <p v-if="description || $slots.description" class="error-state__description">
        <slot name="description">{{ description }}</slot>
      </p>
    </div>
    <div v-if="$slots.action" class="error-state__action">
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
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.error-state__icon {
  color: var(--color-danger, #D92D20);
  margin-bottom: 16px;
  opacity: 0.8;
}

.error-state__content {
  max-width: 400px;
}

.error-state__title {
  font-size: var(--text-section-title, 16px);
  font-weight: var(--weight-semibold, 600);
  color: var(--color-text-primary, #18212B);
  margin: 0 0 8px 0;
}

.error-state__description {
  font-size: var(--text-body, 14px);
  color: var(--color-text-secondary, #667085);
  line-height: 1.5;
  margin: 0;
}

.error-state__action {
  margin-top: 24px;
}
</style>
