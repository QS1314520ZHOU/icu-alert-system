<template>
  <a-dropdown :trigger="trigger" placement="bottomRight">
    <button class="more-menu__trigger" @click.prevent>
      <slot name="trigger">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="4" r="1.5" fill="currentColor"/>
          <circle cx="8" cy="8" r="1.5" fill="currentColor"/>
          <circle cx="8" cy="12" r="1.5" fill="currentColor"/>
        </svg>
      </slot>
    </button>
    <template #overlay>
      <a-menu>
        <slot />
      </a-menu>
    </template>
  </a-dropdown>
</template>

<script setup lang="ts">
interface Props {
  trigger?: ('click' | 'hover' | 'contextmenu')[]
}

withDefaults(defineProps<Props>(), {
  trigger: () => ['click'],
})
</script>

<style scoped>
.more-menu__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md, 6px);
  color: var(--color-text-secondary, #667085);
  cursor: pointer;
  transition: all 0.2s ease;
}

.more-menu__trigger:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border-color: var(--color-border, #E3E7EC);
  color: var(--color-text-primary, #18212B);
}

/* 覆盖 Ant Design Menu 样式 */
:deep(.ant-dropdown-menu) {
  background: var(--color-bg-surface, #FFFFFF) !important;
  border: 1px solid var(--color-border, #E3E7EC) !important;
  border-radius: var(--radius-lg, 8px) !important;
  box-shadow: var(--shadow-lg, 0 10px 15px -3px rgba(0, 0, 0, 0.1)) !important;
  padding: 4px !important;
}

:deep(.ant-dropdown-menu-item) {
  border-radius: var(--radius-md, 6px) !important;
  color: var(--color-text-primary, #18212B) !important;
  font-size: var(--text-body, 14px) !important;
  padding: 8px 12px !important;
}

:deep(.ant-dropdown-menu-item:hover) {
  background: var(--color-bg-surface-secondary, #F1F3F5) !important;
}

:deep(.ant-dropdown-menu-item-danger) {
  color: var(--color-danger, #D92D20) !important;
}

:deep(.ant-dropdown-menu-item-danger:hover) {
  background: var(--color-danger-bg, rgba(217, 45, 32, 0.08)) !important;
}
</style>
