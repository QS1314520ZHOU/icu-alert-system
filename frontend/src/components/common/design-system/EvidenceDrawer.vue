<template>
  <a-drawer
    :open="open"
    :title="title"
    :width="width"
    :placement="placement"
    @close="$emit('close')"
  >
    <template #title>
      <div class="evidence-drawer__title">
        <slot name="title">{{ title }}</slot>
      </div>
    </template>

    <div class="evidence-drawer__content">
      <slot />
    </div>

    <template v-if="$slots.footer" #footer>
      <div class="evidence-drawer__footer">
        <slot name="footer" />
      </div>
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
interface Props {
  open: boolean
  title?: string
  width?: number | string
  placement?: 'left' | 'right' | 'top' | 'bottom'
}

withDefaults(defineProps<Props>(), {
  width: 400,
  placement: 'right',
})

defineEmits<{
  close: []
}>()
</script>

<style scoped>
.evidence-drawer__title {
  font-size: var(--text-section-title, 16px);
  font-weight: var(--weight-semibold, 600);
  color: var(--color-text-primary, #18212B);
}

.evidence-drawer__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.evidence-drawer__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border, #E3E7EC);
}

/* 覆盖 Ant Design Drawer 样式 */
:deep(.ant-drawer-content) {
  background: var(--color-bg-surface, #FFFFFF) !important;
}

:deep(.ant-drawer-header) {
  background: transparent !important;
  border-bottom: 1px solid var(--color-border, #E3E7EC) !important;
}

:deep(.ant-drawer-title) {
  color: var(--color-text-primary, #18212B) !important;
  font-size: var(--text-section-title, 16px) !important;
  font-weight: var(--weight-semibold, 600) !important;
}

:deep(.ant-drawer-close) {
  color: var(--color-text-secondary, #667085) !important;
}

:deep(.ant-drawer-body) {
  padding: 16px !important;
}
</style>
