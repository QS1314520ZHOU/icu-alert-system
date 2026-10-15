<template>
  <div class="handover-tasks">
    <PageHeader title="待办与未闭环" subtitle="未闭环危急值、待执行医嘱、逾期任务清单" />
    <div class="placeholder-card">
      <EmptyState description="未闭环危急值、待执行医嘱、逾期任务清单" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { PageHeader, EmptyState } from '../../components/common/design-system'
</script>

<style scoped>
.handover-tasks { padding: var(--page-padding, 24px); }
.placeholder-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}
.placeholder-text { color: var(--color-text-secondary); text-align: center; padding: 40px 0; }
</style>
