<template>
  <div class="evidence-timeline">
    <div v-if="!events.length" class="timeline-empty">暂无临床事件时间线</div>
    <div v-else class="timeline-list">
      <div v-for="(event, idx) in events" :key="idx" class="timeline-item">
        <div class="timeline-dot" :class="`severity-${event.severity}`"></div>
        <div class="timeline-line" v-if="idx < events.length - 1"></div>
        <div class="timeline-content">
          <div class="timeline-head">
            <span :class="['timeline-type', `type-${event.event_type}`]">{{ eventTypeLabel(event.event_type) }}</span>
            <span class="timeline-time">{{ formatTime(event.time) }}</span>
          </div>
          <div class="timeline-title">{{ event.title }}</div>
          <div v-if="event.detail" class="timeline-detail">{{ event.detail }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TimelineEvent } from '../../api/clinicalEvidence'

defineProps<{
  events: TimelineEvent[]
}>()

function eventTypeLabel(type: string): string {
  const map: Record<string, string> = {
    alert: '告警', medication: '用药', nursing: '护理',
    order: '医嘱', assessment: '评估', lab: '检验',
  }
  return map[type] || type
}

function formatTime(t: string | null): string {
  if (!t) return '—'
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.timeline-list {
  position: relative;
  padding-left: 20px;
}
.timeline-item {
  position: relative;
  padding-bottom: 16px;
}
.timeline-item:last-child { padding-bottom: 0; }
.timeline-dot {
  position: absolute;
  left: -20px;
  top: 4px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--color-border);
  z-index: 1;
}
.timeline-dot.severity-critical { background: var(--color-danger); }
.timeline-dot.severity-high { background: var(--color-high-risk); }
.timeline-dot.severity-warning { background: var(--color-warning); }
.timeline-dot.severity-info { background: var(--color-primary); }
.timeline-dot.severity-stable { background: var(--color-success); }
.timeline-line {
  position: absolute;
  left: -16px;
  top: 14px;
  bottom: 0;
  width: 2px;
  background: var(--color-border, #E5E7EB);
}
.timeline-content {
  padding: 4px 0;
}
.timeline-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}
.timeline-type {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}
.timeline-type.type-alert { background: var(--color-critical-bg); color: var(--color-critical); }
.timeline-type.type-medication { background: var(--color-primary-bg); color: var(--color-primary); }
.timeline-type.type-nursing { background: var(--color-normal-bg); color: var(--color-success); }
.timeline-type.type-order { background: var(--color-ai-light); color: var(--color-ai); }
.timeline-type.type-assessment { background: var(--color-warning-soft-bg); color: var(--color-warning); }
.timeline-time { font-size: 11px; color: var(--text-tertiary, #9CA3AF); }
.timeline-title { font-size: 13px; color: var(--text-primary, #182230); font-weight: 500; }
.timeline-detail { font-size: 12px; color: var(--text-secondary, #6B7280); margin-top: 2px; }
.timeline-empty {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary, #9CA3AF);
  font-size: 13px;
}
</style>
