<template>
  <section class="safety-checklist">
    <div class="panel-head">
      <strong>安全清单</strong>
      <span>闭环状态</span>
    </div>
    <div class="checklist-items">
      <article
        v-for="item in items"
        :key="item.code"
        :class="['checklist-row', `is-${item.tone || 'neutral'}`]"
      >
        <div class="checklist-row__left">
          <i :class="['tone-bar', `tone-${item.tone || 'neutral'}`]"></i>
          <div class="checklist-row__info">
            <strong>{{ displayName(item.name || item.code) }}</strong>
            <span v-if="item.data_state === 'missing'">暂无同步</span>
            <span v-else>{{ item.completed }}/{{ item.total }} 项完成</span>
          </div>
        </div>
        <span v-if="item.data_state !== 'missing'" :class="['checklist-rate', rateClass(item)]">
          {{ item.total > 0 ? Math.round(item.completed / item.total * 100) : 0 }}%
        </span>
      </article>
    </div>
    <div v-if="degraded && !items.length" class="empty-hint">{{ degraded }}</div>
    <div v-else-if="!items.length" class="empty-hint">本班安全清单暂无同步记录。</div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  items: Array<{ code: string; name?: string; completed: number; total: number; tone?: string; data_state?: string }>
  displayName: (v: any) => string
  degraded?: string
}>()

function rateClass(item: { completed: number; total: number; tone?: string }) {
  if (item.tone === 'red') return 'is-danger'
  if (item.tone === 'yellow') return 'is-warning'
  return 'is-success'
}
</script>

<style scoped>
.safety-checklist {
  display: grid;
  gap: 10px;
  padding: var(--card-padding, 16px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.panel-head strong {
  font-size: var(--text-card-title, 14px);
  font-weight: var(--text-card-title-weight, 650);
  color: var(--color-text-primary);
}

.panel-head span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary);
}

.checklist-items {
  display: grid;
  gap: 1px;
}

.checklist-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
}

.checklist-row__left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.tone-bar {
  width: 3px;
  height: 28px;
  border-radius: 2px;
  flex-shrink: 0;
}

.tone-bar.tone-green { background: var(--color-success); }
.tone-bar.tone-yellow { background: var(--color-warning); }
.tone-bar.tone-red { background: var(--color-danger); }
.tone-bar.tone-neutral { background: var(--color-border, var(--color-bg-inset)); }

.checklist-row__info {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.checklist-row__info strong {
  font-size: var(--text-body, 14px);
  font-weight: 500;
  color: var(--color-text-primary);
}

.checklist-row__info span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary);
}

.checklist-rate {
  font-size: var(--text-caption, 12px);
  font-weight: 600;
  flex-shrink: 0;
}

.checklist-rate.is-success { color: var(--color-success); }
.checklist-rate.is-warning { color: var(--color-warning); }
.checklist-rate.is-danger { color: var(--color-danger); }

.empty-hint {
  padding: 16px;
  text-align: center;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary);
}
</style>
