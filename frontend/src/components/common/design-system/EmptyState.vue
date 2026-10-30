<template>
  <div class="empty-state">
    <div class="empty-state__icon">
      <slot name="icon">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 13h5l1.5 2.5h5L16 13h5" /><path d="M5.5 5h13L21 13v6H3v-6z" />
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
  padding: 20px 16px;
  text-align: center;
}

.empty-state__icon {
  color: var(--color-text-secondary, #667085);
  margin-bottom: 6px;
  opacity: 0.6;
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
