<template>
  <section :class="['handoff-entry', { 'is-soon': shiftEndSoon }]">
    <div class="handoff-entry__content">
      <strong>交班入口</strong>
      <span v-if="shiftEndSoon">本班即将结束，建议提前准备交班单</span>
      <span v-else>下班前1小时自动生成交班单</span>
    </div>
    <div class="handoff-entry__actions">
      <button class="handoff-btn" :disabled="loading || !bedCount" @click="$emit('generate')">
        {{ loading ? '生成中...' : '生成交班单' }}
      </button>
      <button v-if="hasHandover" class="handoff-btn subtle" @click="$emit('goHandover')">
        查看完整交班
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  shiftEndSoon: boolean
  loading: boolean
  bedCount: number
  hasHandover: boolean
}>()

defineEmits<{
  generate: []
  goHandover: []
}>()
</script>

<style scoped>
.handoff-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: var(--card-padding, 16px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface);
  transition: border-color 0.2s;
}

.handoff-entry.is-soon {
  border-color: var(--color-warning);
  background: var(--color-warning-bg, rgba(181, 71, 8, 0.04));
}

.handoff-entry__content {
  display: grid;
  gap: 4px;
}

.handoff-entry__content strong {
  font-size: var(--text-card-title, 14px);
  font-weight: var(--text-card-title-weight, 650);
  color: var(--color-text-primary);
}

.handoff-entry__content span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary);
}

.handoff-entry.is-soon .handoff-entry__content span {
  color: var(--color-warning);
}

.handoff-entry__actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.handoff-btn {
  height: var(--button-height, 40px);
  padding: 0 16px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-button, 6px);
  background: var(--color-primary);
  color: var(--color-text-inverse);
  font-size: var(--text-body, 14px);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.handoff-btn:hover:not(:disabled) {
  background: var(--color-primary-hover, var(--color-primary));
}

.handoff-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.handoff-btn.subtle {
  background: transparent;
  border-color: var(--color-border);
  color: var(--color-text-primary);
}

.handoff-btn.subtle:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

@media (max-width: 640px) {
  .handoff-entry {
    flex-direction: column;
    align-items: stretch;
  }

  .handoff-entry__actions {
    justify-content: stretch;
  }

  .handoff-btn {
    flex: 1;
  }
}
</style>
