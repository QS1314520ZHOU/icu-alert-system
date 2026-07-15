<template>
  <div class="evidence-panel">
    <h4 class="panel-title">📎 生成依据</h4>
    <div v-if="!items.length" class="empty-hint">暂无依据数据</div>
    <div v-for="item in items" :key="item.field + item.time" class="evidence-item">
      <span class="evidence-field">{{ item.field }}</span>
      <span class="evidence-source">{{ item.source }}</span>
      <span class="evidence-value">{{ item.value }}</span>
      <span class="evidence-time">{{ item.time }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  items: Array<{ field: string; source: string; value: string; time: string }>
}>()
</script>

<style scoped>
.evidence-panel {
  padding: 12px 16px;
  background: var(--bg-surface);
  border-radius: var(--card-radius);
  border: 1px solid var(--border-color, #334155);
  max-height: 400px;
  overflow-y: auto;
}
.panel-title {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--text-main);
}
.empty-hint {
  color: var(--text-secondary);
  font-size: 13px;
}
.evidence-item {
  display: grid;
  grid-template-columns: 120px 100px 1fr 130px;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid var(--border-color, #334155);
}
.evidence-field { color: var(--accent); font-weight: 600; }
.evidence-source { color: var(--text-secondary); }
.evidence-value { color: var(--text-main); }
.evidence-time { color: var(--text-secondary); text-align: right; }
</style>
