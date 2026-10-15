<template>
  <div class="handover-patients">
    <PageHeader title="患者交班" subtitle="每个患者的ISBAR交班状态与进度" />
    <div class="placeholder-card">
      <EmptyState description="每个患者的ISBAR交班状态与进度" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { PageHeader, EmptyState } from '../../components/common/design-system'
</script>

<style scoped>
.handover-patients { padding: var(--page-padding, 24px); }
.placeholder-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}
.placeholder-text { color: var(--color-text-secondary); text-align: center; padding: 40px 0; }
</style>
