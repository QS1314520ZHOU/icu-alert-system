<template>
  <div class="handover-history">
    <PageHeader title="交班历史" subtitle="历史交班记录查询与回溯" />
    <div class="placeholder-card">
      <EmptyState description="历史交班记录查询与回溯" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { PageHeader, EmptyState } from '../../components/common/design-system'
</script>

<style scoped>
.handover-history { padding: var(--page-padding, 24px); }
.placeholder-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}
.placeholder-text { color: var(--color-text-secondary); text-align: center; padding: 40px 0; }
</style>
