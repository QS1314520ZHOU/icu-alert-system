<template>
  <div class="data-completeness">
    <div class="completeness-header">
      <h3 class="completeness-title">数据来源完整度</h3>
    </div>
    <div class="completeness-grid">
      <div
        v-for="item in items"
        :key="item.label"
        class="completeness-item"
        :class="statusClass(item.status)"
      >
        <span class="item-label">{{ item.label }}</span>
        <span class="item-status">
          <span v-if="item.status === 'available'" class="status-icon status-icon--ok">✓</span>
          <span v-else-if="item.status === 'empty'" class="status-icon status-icon--empty">0</span>
          <span v-else-if="item.status === 'stale'" class="status-icon status-icon--stale">⟳</span>
          <span v-else class="status-icon status-icon--fail">✗</span>
        </span>
        <span class="item-count">{{ item.count }}条</span>
      </div>
    </div>
    <div class="completeness-caption">
      展示各数据源的查询状态。✓有数据 · 0无数据 · ⟳陈旧 · ✗获取失败。
      获取失败与"无数据"不是同一种状态。
    </div>
  </div>
</template>

<script setup lang="ts">
interface CompletenessItem {
  label: string
  status: 'available' | 'empty' | 'stale' | 'failed'
  count: number
  source?: string
}

defineProps<{ items: CompletenessItem[] }>()

function statusClass(status: string) {
  return `completeness-item--${status}`
}
</script>

<style scoped>
.data-completeness { background: var(--color-bg-surface); border-radius: var(--radius-lg); border: 1px solid var(--color-border); padding: 16px; }
.completeness-header { margin-bottom: 12px; }
.completeness-title { font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin: 0; }

.completeness-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.completeness-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: var(--radius-md); border: 1px solid var(--color-border);
  font-size: 12px;
}
.completeness-item--available { border-color: var(--color-normal); background: var(--color-normal-bg); }
.completeness-item--empty { border-color: var(--color-unknown); background: var(--color-bg-page); }
.completeness-item--stale { border-color: var(--color-high-risk); background: var(--color-warning-bg); }
.completeness-item--failed { border-color: var(--color-danger); background: var(--color-danger-bg); }

.item-label { flex: 1; color: var(--color-text-primary); font-weight: 500; }
.item-count { color: var(--color-text-secondary); }
.status-icon { font-size: 14px; font-weight: 600; }
.status-icon--ok { color: var(--color-normal); }
.status-icon--empty { color: var(--color-unknown); }
.status-icon--stale { color: var(--color-high-risk); }
.status-icon--fail { color: var(--color-danger); }

.completeness-caption { font-size: 12px; color: var(--color-text-tertiary); margin-top: 12px; border-top: 1px solid var(--color-divider); padding-top: 8px; }
</style>
