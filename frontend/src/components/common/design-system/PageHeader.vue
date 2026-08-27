<template>
  <div class="page-header">
    <div class="page-header__content">
      <div class="page-header__text">
        <h1 class="page-header__title">
          <slot name="title">{{ title }}</slot>
        </h1>
        <p v-if="subtitle || $slots.subtitle" class="page-header__subtitle">
          <slot name="subtitle">{{ subtitle }}</slot>
        </p>
      </div>
      <div v-if="$slots.actions" class="page-header__actions">
        <slot name="actions" />
      </div>
    </div>
    <div v-if="$slots.default" class="page-header__extra">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  title?: string
  subtitle?: string
}

defineProps<Props>()
</script>

<style scoped>
.page-header {
  margin-bottom: var(--section-gap, 24px);
}

.page-header__content {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.page-header__text {
  flex: 1;
  min-width: 0;
}

.page-header__title {
  font-size: var(--text-page-title, 24px);
  font-weight: var(--text-page-title-weight, 700);
  color: var(--color-text-primary, #18212B);
  line-height: 1.3;
  margin: 0;
}

.page-header__subtitle {
  font-size: var(--text-page-subtitle, 14px);
  font-weight: var(--text-page-subtitle-weight, 400);
  color: var(--color-text-secondary, #667085);
  line-height: 1.5;
  margin: 4px 0 0 0;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.page-header__extra {
  margin-top: 16px;
}

@media (max-width: 768px) {
  .page-header__content {
    flex-direction: column;
    align-items: stretch;
  }

  .page-header__actions {
    justify-content: flex-start;
  }
}
</style>
