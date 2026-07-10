<template>
  <section :class="['body-map-panel', { 'body-map-panel--compact': compact }]">
    <div class="body-map-panel__head">
      <div>
        <div class="body-map-panel__kicker">器官热力图</div>
        <div class="body-map-panel__title">人体器官风险总览</div>
      </div>
      <div class="body-map-panel__stats">
        <span class="body-map-panel__pill">MODI {{ modi ?? '—' }}</span>
        <span class="body-map-panel__pill">{{ organCount || 0 }} 个系统</span>
      </div>
    </div>

    <div class="body-map-panel__grid">
      <OrganHeatmapFigure
        :compact="compact"
        :organ-states="organStates"
        :selected-organ="selectedOrgan"
        :organ-tooltips="organTooltips"
        :show-legend="false"
        :silhouette="silhouette"
        @organ-click="emit('organ-click', $event)"
      />

      <div class="body-map-panel__side">
        <button
          v-for="row in organRows"
          :key="row.key"
          type="button"
          :class="['body-map-panel__row', { 'is-active': row.key === selectedOrgan }]"
          @click="emit('organ-click', row.key)"
        >
          <div class="body-map-panel__row-top">
            <strong>{{ row.label }}</strong>
            <span :class="['body-map-panel__badge', `is-${row.severity}`]">{{ row.statusText }}</span>
          </div>
          <div class="body-map-panel__row-meta">{{ row.meta }}</div>
        </button>

        <div class="body-map-panel__actions">
          <button type="button" class="body-map-panel__action" @click="emit('open-alerts')">打开预警与审核</button>
          <div class="body-map-panel__hint">点击器官可切换到相关预警视图。</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OrganHeatmapFigure from '../common/OrganHeatmapFigure.vue'
import {
  BODY_MAP_ORGAN_LABELS,
  BODY_MAP_ORGAN_ORDER,
  bodyMapSeverityText,
  mergeOrganStateMaps,
  normalizeBodyMapSeverity,
} from '../../utils/bodyMap'

const props = withDefaults(defineProps<{
  organStates?: Record<string, any>
  organDetails?: Array<{ key: string; label?: string; evidence?: string; status_text?: string }>
  selectedOrgan?: string
  modi?: number | null
  organCount?: number | null
  silhouette?: 'female' | 'male'
  compact?: boolean
}>(), {
  organStates: () => ({}),
  organDetails: () => [],
  selectedOrgan: '',
  modi: null,
  organCount: null,
  silhouette: 'female',
  compact: false,
})

const emit = defineEmits<{
  (e: 'organ-click', key: string): void
  (e: 'open-alerts'): void
}>()

const detailsMap = computed(() => {
  const map = new Map<string, { evidence?: string; statusText?: string }>()
  for (const item of props.organDetails) {
    const key = String(item?.key || '').trim().toLowerCase()
    if (!key) continue
    map.set(key, {
      evidence: String(item?.evidence || '').trim(),
      statusText: String(item?.status_text || '').trim(),
    })
  }
  return map
})

const organStates = computed(() => mergeOrganStateMaps(props.organStates as any))

const organRows = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key) => {
    const detail = detailsMap.value.get(key)
    const severity = normalizeBodyMapSeverity(organStates.value[key])
    return {
      key,
      label: BODY_MAP_ORGAN_LABELS[key],
      severity,
      statusText: detail?.statusText || bodyMapSeverityText(severity),
      meta: detail?.evidence || `当前${BODY_MAP_ORGAN_LABELS[key]}系统处于${bodyMapSeverityText(severity)}状态`,
    }
  })
)

const organTooltips = computed(() =>
  Object.fromEntries(
    organRows.value.map((row) => [
      row.key,
      {
        label: row.label,
        detail: row.meta,
        statusText: row.statusText,
        severity: row.severity,
      },
    ])
  )
)
</script>

<style scoped>
.body-map-panel {
  display: grid;
  gap: 12px;
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface) 0%, var(--bg-surface) 100%);
  border: 1px solid rgba(80,199,255,.14);
  box-shadow: var(--card-shadow);
}
.body-map-panel__head,
.body-map-panel__row-top,
.body-map-panel__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.body-map-panel__kicker {
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.body-map-panel__title {
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 700;
}
.body-map-panel__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.body-map-panel__pill,
.body-map-panel__badge,
.body-map-panel__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: var(--card-radius);
  font-size: 12px;
}
.body-map-panel__pill {
  background: var(--bg-surface), 0.82);
  border: 1px solid rgba(80,199,255,.14);
  color: var(--text-primary);
}
.body-map-panel__grid {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
}
.body-map-panel__side {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  align-content: start;
}
.body-map-panel__row {
  width: 100%;
  text-align: left;
  border: 1px solid rgba(80,199,255,.12);
  background: var(--bg-surface), 0.7);
  border-radius: var(--card-radius);
  min-height: 82px;
  padding: 11px 12px;
  cursor: pointer;
  transition: border-color .2s ease, transform .2s ease, box-shadow .2s ease;
}
.body-map-panel__row:hover,
.body-map-panel__row.is-active {
  transform: translateY(-1px);
  border-color: rgba(110,231,249,.28);
  box-shadow: var(--card-shadow);
}
.body-map-panel__row strong {
  color: var(--text-primary);
  font-size: 14px;
}
.body-map-panel__actions {
  grid-column: 1 / -1;
  margin-top: 2px;
  padding: 9px 12px;
  border-radius: var(--card-radius);
  border: 1px dashed rgba(80,199,255,.14);
  background: var(--bg-surface), 0.5);
}
.body-map-panel__row-meta,
.body-map-panel__hint {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.body-map-panel__badge {
  border: 1px solid rgba(80,199,255,.14);
  background: var(--bg-surface), 0.9);
  color: var(--text-primary);
}
.body-map-panel__badge.is-warning { color: var(--warning-soft); border-color: rgba(245,158,11,.22); }
.body-map-panel__badge.is-high { color: var(--warning-soft); border-color: rgba(249,115,22,.24); }
.body-map-panel__badge.is-critical { color: var(--danger-soft); border-color: rgba(244,63,94,.24); }
.body-map-panel__action {
  border: 1px solid rgba(110,231,249,.28);
  background: var(--bg-surface) 0%, var(--bg-surface) 100%);
  color: var(--text-primary);
  cursor: pointer;
}
.body-map-panel--compact .body-map-panel__title {
  font-size: 15px;
}
.body-map-panel--compact .body-map-panel__grid {
  grid-template-columns: 1fr;
}
.body-map-panel--compact .body-map-panel__side {
  grid-template-columns: 1fr;
}
.body-map-panel--compact .body-map-panel__row {
  min-height: 0;
}
.body-map-panel--compact .body-map-panel__row-meta {
  line-height: 1.5;
}
@media (max-width: 1180px) {
  .body-map-panel__grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 760px) {
  .body-map-panel__side {
    grid-template-columns: 1fr;
  }
}
html[data-theme='light'] .body-map-panel {
  background: var(--bg-surface) 0%, rgba(239,246,250,.98) 100%);
  border-color: rgba(130, 170, 194, 0.24);
}
html[data-theme='light'] .body-map-panel__title,
html[data-theme='light'] .body-map-panel__row strong {
  color: var(--text-secondary);
}
html[data-theme='light'] .body-map-panel__kicker,
html[data-theme='light'] .body-map-panel__row-meta,
html[data-theme='light'] .body-map-panel__hint {
  color: var(--text-secondary);
}
html[data-theme='light'] .body-map-panel__row,
html[data-theme='light'] .body-map-panel__pill,
html[data-theme='light'] .body-map-panel__badge {
  background: rgba(255,255,255,.94);
  border-color: rgba(130, 170, 194, 0.24);
  color: var(--text-secondary);
}
html[data-theme='light'] .body-map-panel__actions {
  background: rgba(255,255,255,.9);
  border-color: rgba(130, 170, 194, 0.32);
}
html[data-theme='light'] .body-map-panel__action {
  background: var(--bg-surface) 0%, rgba(29,78,216,.98) 100%);
  border-color: rgba(59,130,246,.28);
  color: var(--text-primary);
}
html[data-theme='light'] .body-map-panel__row:hover,
html[data-theme='light'] .body-map-panel__row.is-active {
  border-color: rgba(59,130,246,.3);
  box-shadow: var(--card-shadow);
}
</style>
