<template>
  <div class="action-bar">
    <div class="action-bar__content">
      <slot />
    </div>
    <div v-if="$slots.secondary" class="action-bar__secondary">
      <slot name="secondary" />
    </div>
  </div>
</template>

<script setup lang="ts">
// ActionBar 用于页面底部或区域底部的操作按钮组
</script>

<style scoped>
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 0;
  border-top: 1px solid var(--color-border, #E3E7EC);
  margin-top: 24px;
}

.action-bar__content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-bar__secondary {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 768px) {
  .action-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .action-bar__content,
  .action-bar__secondary {
    justify-content: center;
  }
}
</style>
