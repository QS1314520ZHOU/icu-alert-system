<template>
  <a-drawer
    :open="open"
    width="460"
    root-class-name="mdt-session-drawer"
    title="MDT 历史会话"
    placement="right"
    @close="$emit('update:open', false)"
  >
    <div class="drawer-actions">
      <a-button size="small" @click="$emit('start-new-session')">新建会话</a-button>
      <a-button size="small" :disabled="!currentSessionId" @click="$emit('duplicate-current-session')">复制当前</a-button>
      <a-button size="small" :disabled="!currentSessionId" @click="$emit('export-current-session')">导出当前</a-button>
      <a-button size="small" @click="$emit('close-current-session')">关闭归档</a-button>
      <a-button size="small" @click="$emit('reopen-current-session')">复开会话</a-button>
    </div>

    <div class="drawer-filters">
      <input :value="sessionSearch" class="drawer-input" placeholder="搜索会话标题/摘要" @input="$emit('update:sessionSearch', ($event.target as HTMLInputElement).value)" />
      <select :value="sessionPhaseFilter" class="drawer-input" @change="$emit('update:sessionPhaseFilter', ($event.target as HTMLSelectElement).value)">
        <option value="">全部阶段</option>
        <option value="collecting">收集中</option>
        <option value="conflict_review">冲突评审</option>
        <option value="finalizing">裁决定稿</option>
        <option value="closed">已关闭</option>
      </select>
      <label class="drawer-check">
        <input :checked="sessionListOpenOnly" type="checkbox" @change="$emit('update:sessionListOpenOnly', ($event.target as HTMLInputElement).checked)" />
        <span>仅看未关闭</span>
      </label>
    </div>

    <div v-if="sessions.length" class="session-list">
      <article
        v-for="item in sessions"
        :key="item.session_id"
        :class="['session-card', { 'is-active': currentSessionId === item.session_id }]"
        @click="$emit('switch-session', String(item.session_id || ''))"
      >
        <div class="session-card__head">
          <strong>{{ item.title || 'MDT 会话' }}</strong>
          <span>{{ phaseLabel(item.phase) }}</span>
        </div>
        <p>{{ item.summary || item.final_summary || '暂无摘要' }}</p>
        <div class="session-tags">
          <em>{{ (item.decisions || []).length }} 条决议</em>
          <em>{{ formatDate(item.updated_at) }}</em>
          <em v-for="tag in (item.tags || []).slice(0, 3)" :key="`${item.session_id}-${tag}`">{{ tag }}</em>
        </div>
      </article>
    </div>
    <div v-else class="drawer-empty">暂无匹配会话。</div>
  </a-drawer>
</template>

<script setup lang="ts">
import { Button as AButton, Drawer as ADrawer } from 'ant-design-vue'
import { formatBeijingTime } from '../../utils/time'

defineProps<{
  open: boolean
  sessions: any[]
  currentSessionId: string
  sessionListOpenOnly: boolean
  sessionSearch: string
  sessionPhaseFilter: string
}>()

defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'update:sessionListOpenOnly', value: boolean): void
  (event: 'update:sessionSearch', value: string): void
  (event: 'update:sessionPhaseFilter', value: string): void
  (event: 'switch-session', sessionId: string): void
  (event: 'start-new-session'): void
  (event: 'duplicate-current-session'): void
  (event: 'export-current-session'): void
  (event: 'close-current-session'): void
  (event: 'reopen-current-session'): void
}>()

void AButton
void ADrawer

function phaseLabel(phase: any) {
  const key = String(phase || 'finalizing').toLowerCase()
  return ({ collecting: '收集中', conflict_review: '冲突评审', finalizing: '裁决定稿', closed: '已关闭' } as Record<string, string>)[key] || '裁决定稿'
}

function formatDate(value: any) {
  return formatBeijingTime(value)
}
</script>

<style scoped>
.drawer-actions,
.drawer-filters,
.session-list {
  display: grid;
  gap: 10px;
}
.drawer-actions {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.drawer-filters {
  margin: 14px 0;
}
.drawer-input {
  width: 100%;
  min-height: 38px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: var(--card-radius);
  padding: 0 10px;
  color: var(--text-secondary);
  background: var(--bg-surface);
}
.drawer-check {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}
.session-card {
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: var(--card-radius);
  cursor: pointer;
  background: var(--bg-surface), 0.78);
}
.session-card.is-active {
  border-color: var(--chart-1);
  box-shadow: var(--card-shadow);
}
.session-card__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.session-card strong {
  color: var(--text-primary);
}
.session-card span {
  color: var(--chart-1);
}
.session-card p {
  margin: 8px 0;
  color: rgba(203, 213, 225, 0.74);
  line-height: 1.45;
}
.session-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.session-tags em {
  padding: 4px 8px;
  border-radius: var(--card-radius);
  color: var(--text-secondary);
  font-size: 12px;
  font-style: normal;
  background: var(--bg-surface), 0.9);
}
.drawer-empty {
  color: var(--text-secondary);
}
:global(.ant-drawer-content),
:global(.ant-drawer-header) {
  background: var(--bg-surface) !important;
  color: var(--text-secondary) !important;
}
:global(.ant-drawer-title),
:global(.ant-drawer-close) {
  color: var(--text-primary) !important;
}
:global(html[data-theme='light'] .ant-drawer-content),
:global(html[data-theme='light'] .ant-drawer-header) {
  background: var(--bg-surface) !important;
  color: var(--text-primary) !important;
}
:global(html[data-theme='light'] .ant-drawer-title),
:global(html[data-theme='light'] .ant-drawer-close) {
  color: var(--text-primary) !important;
}
html[data-theme='light'] .drawer-input {
  background: var(--bg-surface);
  color: var(--text-primary);
  border-color: var(--text-secondary);
}
</style>
