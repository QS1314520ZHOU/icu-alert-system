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
  border: 2px solid #fff;
  z-index: 1;
}
.timeline-dot.severity-critical { background: #DC2626; }
.timeline-dot.severity-high { background: #EA580C; }
.timeline-dot.severity-warning { background: #D97706; }
.timeline-dot.severity-info { background: #2563EB; }
.timeline-dot.severity-stable { background: #16A34A; }
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
.timeline-type.type-alert { background: #FEF2F2; color: #991B1B; }
.timeline-type.type-medication { background: #EFF6FF; color: #1E40AF; }
.timeline-type.type-nursing { background: #F0FDF4; color: #166534; }
.timeline-type.type-order { background: #F5F3FF; color: #5B21B6; }
.timeline-type.type-assessment { background: #FFFBEB; color: #92400E; }
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
