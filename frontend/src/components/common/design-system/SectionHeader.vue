<template>
  <div class="section-header">
    <div class="section-header__content">
      <h2 class="section-header__title">
        <slot name="title">{{ title }}</slot>
      </h2>
      <p v-if="description || $slots.description" class="section-header__description">
        <slot name="description">{{ description }}</slot>
      </p>
    </div>
    <div v-if="$slots.actions" class="section-header__actions">
      <slot name="actions" />
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
.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.section-header__content {
  flex: 1;
  min-width: 0;
}

.section-header__title {
  font-size: var(--text-section-title, 16px);
  font-weight: var(--text-section-title-weight, 650);
  color: var(--color-text-primary, #18212B);
  line-height: 1.4;
  margin: 0;
}

.section-header__description {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  line-height: 1.45;
  margin: 4px 0 0 0;
}

.section-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .section-header {
    flex-direction: column;
    align-items: stretch;
  }

  .section-header__actions {
    justify-content: flex-start;
  }
}
</style>
