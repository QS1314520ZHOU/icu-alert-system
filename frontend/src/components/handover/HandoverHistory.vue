<template>
  <div class="history-panel">
    <h4 class="history-title">📜 交班历史</h4>
    <a-spin :spinning="loading">
      <div v-if="!items.length && !loading" class="empty-hint">暂无交班记录</div>
      <div v-for="item in items" :key="item.handover_id" class="history-item" @click="emit('select', item)">
        <div class="history-top">
          <span class="history-shift">{{ item.shift?.name || '—' }}</span>
          <span class="history-time">{{ fmtTime(item.created_at) }}</span>
          <a-tag :color="statusColor(item.status)" size="small">{{ statusLabel(item.status) }}</a-tag>
        </div>
        <div class="history-meta">
          <span>交班: {{ item.submitted_by || '—' }}</span>
          <span v-if="item.acknowledged_by">接班: {{ item.acknowledged_by }}</span>
        </div>
        <div class="history-versions" v-if="item.versions?.length">
          版本: {{ item.versions.length }}
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { Spin as ASpin, Tag as ATag } from 'ant-design-vue'

defineProps<{
  items: Array<Record<string, any>>
  loading: boolean
}>()

const emit = defineEmits<{
  select: [item: Record<string, any>]
}>()

function fmtTime(ts: string) {
  if (!ts) return ''
  return ts.slice(0, 16).replace('T', ' ')
}

function statusColor(s: string) {
  const map: Record<string, string> = { draft: 'blue', submitted: 'orange', acknowledged: 'green' }
  return map[s] || 'default'
}

function statusLabel(s: string) {
  const map: Record<string, string> = {
    not_created: '未创建', draft: '草稿', pending: '待交班',
    submitted: '已提交', acknowledged: '已签收',
  }
  return map[s] || s
}
</script>

<style scoped>
.history-panel {
  padding: 12px 16px;
  background: var(--bg-surface);
  border-radius: var(--card-radius);
  border: 1px solid var(--border-color, #334155);
}
.history-title {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--text-main);
}
.history-item {
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-color, #334155);
  transition: background 0.15s;
}
.history-item:hover {
  background: var(--bg-elevated, #1e293b);
}
.history-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.history-shift {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-main);
}
.history-time {
  font-size: 12px;
  color: var(--text-secondary);
}
.history-meta {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
  display: flex;
  gap: 12px;
}
.history-versions {
  font-size: 11px;
  color: var(--accent);
  margin-top: 2px;
}
.empty-hint {
  text-align: center;
  color: var(--text-secondary);
  padding: 16px;
  font-size: 13px;
}
</style>
