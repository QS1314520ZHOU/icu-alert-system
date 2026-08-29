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
.data-completeness { background: #fff; border-radius: 8px; border: 1px solid #DCE5EF; padding: 16px; }
.completeness-header { margin-bottom: 12px; }
.completeness-title { font-size: 14px; font-weight: 600; color: #17233D; margin: 0; }

.completeness-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.completeness-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: 6px; border: 1px solid #DCE5EF;
  font-size: 12px;
}
.completeness-item--available { border-color: #12A66A; background: #ECFDF3; }
.completeness-item--empty { border-color: #98A2B3; background: #F9FAFB; }
.completeness-item--stale { border-color: #F79009; background: #FFFAEB; }
.completeness-item--failed { border-color: #D92D20; background: #FEF3F2; }

.item-label { flex: 1; color: #17233D; font-weight: 500; }
.item-count { color: #5F6B7A; }
.status-icon { font-size: 14px; font-weight: 600; }
.status-icon--ok { color: #12A66A; }
.status-icon--empty { color: #98A2B3; }
.status-icon--stale { color: #F79009; }
.status-icon--fail { color: #D92D20; }

.completeness-caption { font-size: 12px; color: #8A94A6; margin-top: 12px; border-top: 1px solid #F0F3F7; padding-top: 8px; }
</style>
