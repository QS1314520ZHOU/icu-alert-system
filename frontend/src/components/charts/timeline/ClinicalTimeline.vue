<template>
  <div class="clinical-timeline">
    <div class="clinical-timeline__header">
      <span class="clinical-timeline__title">{{ title ?? '临床事件时间线' }}</span>
      <div v-if="typeFilters?.length" class="clinical-timeline__filters">
        <a-checkbox-group v-model:value="visibleTypes" :options="typeFilters" size="small" />
      </div>
    </div>

    <div v-if="filteredEvents.length" class="clinical-timeline__body" :class="[`clinical-timeline__body--${direction}`]">
      <div
        v-for="(event, index) in filteredEvents"
        :key="event.id ?? index"
        class="clinical-timeline__event"
        :class="[`clinical-timeline__event--${event.type}`]"
        @click="$emit('eventClick', event)"
      >
        <div class="clinical-timeline__marker">
          <span class="clinical-timeline__dot" :style="{ background: getEventColor(event.type) }" />
          <span v-if="index < filteredEvents.length - 1" class="clinical-timeline__line" />
        </div>
        <div class="clinical-timeline__content">
          <div class="clinical-timeline__time">{{ formatTime(event.time) }}</div>
          <div class="clinical-timeline__label">
            <span class="clinical-timeline__type-badge" :style="{ background: getEventColor(event.type) + '15', color: getEventColor(event.type) }">
              {{ event.type }}
            </span>
            {{ event.title }}
          </div>
          <div v-if="event.description" class="clinical-timeline__desc">{{ event.description }}</div>
          <div v-if="event.source" class="clinical-timeline__source">来源: {{ event.source }}</div>
        </div>
      </div>
    </div>

    <ClinicalEmptyState
      v-else
      :type="loading ? 'loading' : 'no-data'"
      :message="loading ? '加载中' : emptyMessage ?? '过去24小时无记录事件'"
      size="small"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { CHART_SERIES } from '../../../styles/tokens/colors'
import ClinicalEmptyState from '../base/ClinicalEmptyState.vue'

export interface TimelineEvent {
  id?: string
  time: string
  type: string
  title: string
  description?: string
  source?: string
  severity?: 'critical' | 'warning' | 'info' | 'normal'
}

export interface TypeFilter {
  label: string
  value: string
}

const props = withDefaults(defineProps<{
  title?: string
  events: TimelineEvent[]
  direction?: 'vertical' | 'horizontal'
  typeFilters?: TypeFilter[]
  loading?: boolean
  emptyMessage?: string
}>(), {
  direction: 'vertical',
})

defineEmits<{ eventClick: [TimelineEvent] }>()

const visibleTypes = ref(props.typeFilters?.map(f => f.value) ?? [])

const filteredEvents = computed(() => {
  if (!visibleTypes.value.length) return props.events
  return props.events.filter(e => visibleTypes.value.includes(e.type))
})

const typeColorMap = new Map<string, string>()
let colorIndex = 0

function getEventColor(type: string): string {
  if (!typeColorMap.has(type)) {
    typeColorMap.set(type, CHART_SERIES[colorIndex % CHART_SERIES.length] ?? '#1677FF')
    colorIndex++
  }
  return typeColorMap.get(type)!
}

function formatTime(time: string): string {
  try {
    const d = new Date(time)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return time
  }
}
</script>

<style scoped>
.clinical-timeline {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 8px;
  padding: 16px;
}

.clinical-timeline__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.clinical-timeline__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
}

.clinical-timeline__filters {
  display: flex;
  gap: 4px;
}

.clinical-timeline__body--vertical {
  display: flex;
  flex-direction: column;
}

.clinical-timeline__body--horizontal {
  display: flex;
  overflow-x: auto;
  gap: 0;
  padding-bottom: 8px;
}

.clinical-timeline__body--horizontal .clinical-timeline__event {
  flex-direction: column;
  min-width: 120px;
}

.clinical-timeline__body--horizontal .clinical-timeline__marker {
  flex-direction: row;
  align-items: center;
}

.clinical-timeline__body--horizontal .clinical-timeline__line {
  width: 100%;
  height: 2px;
}

.clinical-timeline__event {
  display: flex;
  gap: 12px;
  cursor: pointer;
  padding: 6px 0;
  transition: background 0.15s;
  border-radius: 6px;
}

.clinical-timeline__event:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.clinical-timeline__marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 16px;
}

.clinical-timeline__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 2px solid var(--color-bg-surface, #fff);
  box-shadow: 0 0 0 1px var(--color-border, #DCE5EF);
}

.clinical-timeline__line {
  flex: 1;
  width: 2px;
  background: var(--color-border, #DCE5EF);
  margin: 2px 0;
}

.clinical-timeline__content {
  flex: 1;
  min-width: 0;
}

.clinical-timeline__time {
  font-size: 11px;
  color: var(--color-text-tertiary, #8A94A6);
  font-family: 'Rajdhani', monospace;
}

.clinical-timeline__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary, #17233D);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}

.clinical-timeline__type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
  white-space: nowrap;
}

.clinical-timeline__desc {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  margin-top: 2px;
}

.clinical-timeline__source {
  font-size: 11px;
  color: var(--color-text-disabled, #B6BEC9);
  margin-top: 2px;
}
</style>
