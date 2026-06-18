<template>
  <section class="device-map-card">
    <div class="device-map-card__head">
      <div>
        <div class="device-map-card__kicker">装置位置图</div>
        <div class="device-map-card__title">留置装置 / 管路巡视</div>
      </div>
      <span class="device-map-card__count">{{ markers.length }} 项</span>
    </div>
    <div v-if="legendItems.length || riskLegendItems.length" class="device-map-card__legend-wrap">
      <div v-if="legendItems.length" class="device-map-card__legend-group">
        <span class="device-map-card__legend-label">管路类型</span>
        <div class="device-map-card__legend">
          <span v-for="item in legendItems" :key="item.kind" class="device-map-card__legend-item">
            <span :class="['device-map-card__legend-shape', item.shapeClass]" :style="{ '--legend-color': item.color }" />
            <span>{{ item.text }}</span>
          </span>
        </div>
      </div>
      <div v-if="riskLegendItems.length" class="device-map-card__legend-group">
        <span class="device-map-card__legend-label">风险等级</span>
        <div class="device-map-card__legend">
          <span
            v-for="item in riskLegendItems"
            :key="item.key"
            :class="['device-map-card__legend-item', 'device-map-card__legend-item--risk', `is-${item.key}`]"
          >
            <span class="device-map-card__risk-dot" :style="{ '--risk-color': item.color }" />
            <span>{{ item.text }}</span>
          </span>
        </div>
      </div>
    </div>

    <div v-if="markers.length" class="device-map-card__grid">
      <div class="device-map-card__figure">
        <OrganHeatmapFigure
          compact
          :organ-states="figureOrganStates"
          :silhouette="silhouette"
        />
        <button
          v-for="item in positionedMarkers"
          :key="item.key"
          type="button"
          :class="[
            'device-map-card__marker',
            `is-${item.severity}`,
            item.shapeClass,
            `dir-${item.lineDir}`,
            { 'is-active': activeMarkerKey === item.key },
          ]"
          :style="item.markerStyle"
          :aria-label="`${item.label} ${item.siteText}`"
          @mouseenter="hoveredMarkerKey = item.key"
          @mouseleave="hoveredMarkerKey = ''"
          @click="setSelectedMarker(item.key)"
        >
          <span class="device-map-card__marker-dot" />
          <span class="device-map-card__marker-line" />
          <div v-if="activeMarkerKey === item.key" class="device-map-card__tooltip">
            <div class="device-map-card__tooltip-head">
              <strong>{{ item.label }}</strong>
              <span>{{ item.daysText || '在位中' }}</span>
            </div>
            <div class="device-map-card__tooltip-body">{{ item.detail || '需要持续评估必要性与感染风险' }}</div>
            <div class="device-map-card__tooltip-meta">
              <span>{{ item.kindText }}</span>
              <span>{{ item.siteText }}</span>
            </div>
          </div>
        </button>
      </div>
      <div class="device-map-card__list">
        <button
          v-for="item in positionedMarkers"
          :key="item.key"
          :ref="(el) => setListItemRef(item.key, el)"
          type="button"
          :class="[
            'device-map-card__item',
            `is-${item.severity}`,
            { 'is-active': activeMarkerKey === item.key },
          ]"
          :style="{ '--item-accent': item.markerColor, '--item-ring': item.markerRing }"
          @mouseenter="hoveredMarkerKey = item.key"
          @mouseleave="hoveredMarkerKey = ''"
          @click="setSelectedMarker(item.key)"
        >
          <div class="device-map-card__item-top">
            <strong>{{ item.label }}</strong>
            <span>{{ item.daysText || '在位' }}</span>
          </div>
          <div class="device-map-card__item-tags">
            <span>{{ item.kindText }}</span>
            <span>{{ item.siteText }}</span>
          </div>
          <div class="device-map-card__item-meta">{{ item.detail || '需要持续评估必要性与感染风险' }}</div>
        </button>
      </div>
    </div>
    <div v-else class="device-map-card__empty">当前未识别到活动导管或装置。</div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import OrganHeatmapFigure from '../common/OrganHeatmapFigure.vue'
import {
  BODY_MAP_DEVICE_SITE_LABELS,
  BODY_MAP_ORGAN_ORDER,
  bodyMapSeverityColor,
  type BodyMapDeviceKind,
  type BodyMapDeviceSite,
} from '../../utils/bodyMap'

const props = withDefaults(defineProps<{
  markers: Array<{
    key: string
    label: string
    kind: BodyMapDeviceKind
    severity: string
    site: BodyMapDeviceSite
    daysText?: string
    detail?: string
    blink?: boolean
  }>
  silhouette?: 'female' | 'male'
}>(), {
  silhouette: 'female',
})

const figureOrganStates = computed(() =>
  Object.fromEntries(BODY_MAP_ORGAN_ORDER.map((key) => [key, 'normal']))
)

const hoveredMarkerKey = ref('')
const selectedMarkerKey = ref('')
const listItemRefs = ref<Record<string, HTMLButtonElement | null>>({})

const deviceKindText: Record<BodyMapDeviceKind, string> = {
  airway: '气道管路',
  centralLine: '中心静脉',
  arterialLine: '动脉监测',
  urinary: '尿路管路',
  feeding: '营养/消化道',
  drainage: '引流管路',
  dialysis: '透析通路',
  other: '其他装置',
}

const deviceKindColor: Record<BodyMapDeviceKind, string> = {
  airway: '#f97316',
  centralLine: '#38bdf8',
  arterialLine: '#f59e0b',
  urinary: '#a78bfa',
  feeding: '#22c55e',
  drainage: '#fb7185',
  dialysis: '#15558D',
  other: '#4E5969',
}

const markerShapeClass: Record<BodyMapDeviceKind, string> = {
  airway: 'shape-diamond',
  centralLine: 'shape-circle',
  arterialLine: 'shape-square',
  urinary: 'shape-triangle',
  feeding: 'shape-hex',
  drainage: 'shape-pill',
  dialysis: 'shape-cross',
  other: 'shape-circle',
}

const markerAnchors: Record<BodyMapDeviceSite, { left: number; top: number; lineDir: 'left' | 'right' }> = {
  mouth: { left: 50, top: 15.5, lineDir: 'right' },
  neck: { left: 61.5, top: 25.5, lineDir: 'right' },
  leftChest: { left: 35, top: 39, lineDir: 'left' },
  rightChest: { left: 66, top: 39, lineDir: 'right' },
  abdomen: { left: 61, top: 53, lineDir: 'right' },
  pelvis: { left: 52, top: 69, lineDir: 'right' },
  leftArm: { left: 21, top: 47.5, lineDir: 'left' },
  rightArm: { left: 79, top: 47.5, lineDir: 'right' },
}

const normalizedSelectedMarkerKey = computed(() =>
  props.markers.some((item) => item.key === selectedMarkerKey.value)
    ? selectedMarkerKey.value
    : ''
)

const activeMarkerKey = computed(() => hoveredMarkerKey.value || normalizedSelectedMarkerKey.value)

const positionedMarkers = computed(() =>
  props.markers.map((item) => {
    const anchor = resolveMarkerAnchor(item)
    const markerColor = deviceKindColor[item.kind] || deviceKindColor.other
    const markerRing = bodyMapSeverityColor(item.severity)
    return {
      ...item,
      kindText: deviceKindText[item.kind] || deviceKindText.other,
      siteText: BODY_MAP_DEVICE_SITE_LABELS[item.site] || BODY_MAP_DEVICE_SITE_LABELS.rightChest,
      shapeClass: markerShapeClass[item.kind] || markerShapeClass.other,
      lineDir: anchor.lineDir,
      markerColor,
      markerRing,
      markerStyle: {
        left: `${anchor.left}%`,
        top: `${anchor.top}%`,
        '--marker-color': markerColor,
        '--marker-ring': markerRing,
      },
    }
  })
)

const legendItems = computed(() => {
  const seen = new Set<BodyMapDeviceKind>()
  return positionedMarkers.value
    .filter((item) => {
      if (seen.has(item.kind)) return false
      seen.add(item.kind)
      return true
    })
    .map((item) => ({
      kind: item.kind,
      text: item.kindText,
      color: item.markerColor,
      shapeClass: item.shapeClass,
    }))
})

const riskLegendItems = computed(() => {
  const severityMeta = [
    { key: 'warning', text: '关注', color: bodyMapSeverityColor('warning') },
    { key: 'high', text: '高危', color: bodyMapSeverityColor('high') },
    { key: 'critical', text: '危重', color: bodyMapSeverityColor('critical') },
  ]
  const present = new Set(positionedMarkers.value.map((item) => item.severity))
  return severityMeta.filter((item) => present.has(item.key))
})

function setSelectedMarker(key: string) {
  selectedMarkerKey.value = key
}

function setListItemRef(key: string, el: unknown) {
  listItemRefs.value[key] = el instanceof HTMLButtonElement ? el : null
}

async function scrollSelectedItemIntoView() {
  if (!normalizedSelectedMarkerKey.value) return
  await nextTick()
  listItemRefs.value[normalizedSelectedMarkerKey.value]?.scrollIntoView({
    block: 'nearest',
    inline: 'nearest',
    behavior: 'smooth',
  })
}

watch(normalizedSelectedMarkerKey, () => {
  void scrollSelectedItemIntoView()
})

watch(
  () => props.markers.map((item) => item.key).join('|'),
  () => {
    if (!selectedMarkerKey.value && props.markers[0]?.key) {
      selectedMarkerKey.value = props.markers[0].key
    }
  },
  { immediate: true },
)

function resolveMarkerAnchor(item: { key: string; label: string; kind: BodyMapDeviceKind; site: BodyMapDeviceSite; detail?: string }) {
  const base = markerAnchors[item.site] || markerAnchors.rightChest
  const haystack = `${item.label} ${item.detail || ''}`.toLowerCase()
  if (item.kind === 'airway') return { left: 50, top: 15.5, lineDir: 'right' as const }
  if (item.kind === 'feeding') return { left: 46.5, top: 18.5, lineDir: 'left' as const }
  if (item.kind === 'urinary') return { left: 51, top: 69, lineDir: 'right' as const }
  if (item.kind === 'drainage' && item.site === 'leftChest') return { left: 33, top: 43, lineDir: 'left' as const }
  if (item.kind === 'drainage' && item.site === 'rightChest') return { left: 67.5, top: 43, lineDir: 'right' as const }
  if (item.kind === 'centralLine' && /picc/.test(haystack) && item.site === 'leftArm') return { left: 23, top: 37, lineDir: 'left' as const }
  if (item.kind === 'centralLine' && /picc/.test(haystack) && item.site === 'rightArm') return { left: 77, top: 37, lineDir: 'right' as const }
  if (item.kind === 'arterialLine' && item.site === 'leftArm') return { left: 19, top: 52, lineDir: 'left' as const }
  if (item.kind === 'arterialLine' && item.site === 'rightArm') return { left: 81, top: 52, lineDir: 'right' as const }
  if (item.kind === 'dialysis' && item.site === 'neck') return { left: 60, top: 28.5, lineDir: 'right' as const }
  return base
}
</script>

<style scoped>
.device-map-card {
  display: grid;
  gap: 10px;
}
.device-map-card__head,
.device-map-card__item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.device-map-card__kicker {
  color: #7ed6eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.device-map-card__title {
  margin-top: 4px;
  color: #effcff;
  font-size: 16px;
  font-weight: 700;
}
.device-map-card__count {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(8, 28, 44, 0.82);
  border: 1px solid rgba(80,199,255,.14);
  color: #dffbff;
  font-size: 12px;
}
.device-map-card__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.device-map-card__legend-wrap {
  display: grid;
  gap: 8px;
}
.device-map-card__legend-group {
  display: grid;
  gap: 6px;
}
.device-map-card__legend-label {
  color: #6fbfd4;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
}
.device-map-card__legend-item,
.device-map-card__item-tags span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(8, 28, 44, 0.72);
  border: 1px solid rgba(80,199,255,.1);
  color: #8fb8ca;
  font-size: 11px;
}
.device-map-card__legend-item--risk.is-warning,
.device-map-card__legend-item--risk.is-high,
.device-map-card__legend-item--risk.is-critical {
  border-color: rgba(80,199,255,.12);
}
.device-map-card__legend-shape {
  width: 11px;
  height: 11px;
  background: var(--legend-color);
  box-shadow: 0 0 0 1px rgba(7,20,34,.78);
}
.device-map-card__risk-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--risk-color);
  box-shadow: 0 0 0 1px rgba(7,20,34,.72), 0 0 10px color-mix(in srgb, var(--risk-color) 50%, transparent);
}
.device-map-card__legend-shape.shape-circle { border-radius: 999px; }
.device-map-card__legend-shape.shape-square { border-radius: 3px; }
.device-map-card__legend-shape.shape-diamond { border-radius: 3px; transform: rotate(45deg); }
.device-map-card__legend-shape.shape-triangle {
  width: 0;
  height: 0;
  background: transparent;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 10px solid var(--legend-color);
  box-shadow: none;
}
.device-map-card__legend-shape.shape-pill { width: 13px; border-radius: 999px; }
.device-map-card__legend-shape.shape-hex {
  clip-path: polygon(25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%, 0 50%);
}
.device-map-card__legend-shape.shape-cross {
  position: relative;
  width: 12px;
  height: 12px;
  background: transparent;
  box-shadow: none;
}
.device-map-card__legend-shape.shape-cross::before,
.device-map-card__legend-shape.shape-cross::after {
  content: '';
  position: absolute;
  inset: 0;
  margin: auto;
  border-radius: 3px;
  background: var(--legend-color);
}
.device-map-card__legend-shape.shape-cross::before {
  width: 12px;
  height: 4px;
}
.device-map-card__legend-shape.shape-cross::after {
  width: 4px;
  height: 12px;
}
.device-map-card__grid {
  display: grid;
  grid-template-columns: minmax(184px, 206px) minmax(0, 1fr);
  gap: 16px;
  align-items: center;
}
.device-map-card__figure {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 360px;
}
.device-map-card__figure :deep(.organ-heatmap__frame) {
  width: min(100%, 230px);
}
.device-map-card__figure :deep(.organ-heatmap__svg) {
  filter: drop-shadow(0 0 14px rgba(99, 233, 255, 0.16));
}
.device-map-card__marker {
  position: absolute;
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  background: transparent;
  transform: translate(-50%, -50%);
  z-index: 2;
  cursor: pointer;
}
.device-map-card__marker::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 999px;
  border: 1px solid transparent;
  opacity: 0;
  transform: scale(.94);
  transition: opacity .18s ease, transform .18s ease, border-color .18s ease;
  pointer-events: none;
}
.device-map-card__marker-line {
  position: absolute;
  top: 50%;
  width: 18px;
  height: 2px;
  border-radius: 999px;
  background: var(--marker-color);
  opacity: 0.7;
  transform: translateY(-50%);
}
.device-map-card__marker.dir-left .device-map-card__marker-line {
  right: 100%;
}
.device-map-card__marker.dir-right .device-map-card__marker-line {
  left: 100%;
}
.device-map-card__marker-dot {
  display: block;
  width: 16px;
  height: 16px;
  background: var(--marker-color);
  border: 2px solid var(--marker-ring);
  box-shadow: 0 0 0 3px rgba(7,20,34,.88), 0 0 16px color-mix(in srgb, var(--marker-color) 65%, transparent);
  transition: box-shadow .18s ease, opacity .18s ease, transform .18s ease;
}
.device-map-card__marker.shape-circle .device-map-card__marker-dot { border-radius: 999px; }
.device-map-card__marker.shape-square .device-map-card__marker-dot { border-radius: 4px; }
.device-map-card__marker.shape-diamond .device-map-card__marker-dot { border-radius: 4px; transform: rotate(45deg); }
.device-map-card__marker.shape-triangle .device-map-card__marker-dot {
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-bottom: 16px solid var(--marker-color);
  border-top: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  position: relative;
}
.device-map-card__marker.shape-triangle .device-map-card__marker-dot::after {
  content: '';
  position: absolute;
  left: -7px;
  top: 2px;
  border-left: 7px solid transparent;
  border-right: 7px solid transparent;
  border-bottom: 12px solid rgba(7,20,34,.92);
}
.device-map-card__marker.shape-pill .device-map-card__marker-dot { border-radius: 999px; width: 18px; }
.device-map-card__marker.shape-hex .device-map-card__marker-dot {
  clip-path: polygon(25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%, 0 50%);
}
.device-map-card__marker.shape-cross .device-map-card__marker-dot {
  position: relative;
  background: transparent;
  border: none;
  box-shadow: none;
}
.device-map-card__marker.shape-cross .device-map-card__marker-dot::before,
.device-map-card__marker.shape-cross .device-map-card__marker-dot::after {
  content: '';
  position: absolute;
  inset: 0;
  margin: auto;
  background: var(--marker-color);
  border: 2px solid var(--marker-ring);
  box-shadow: 0 0 0 2px rgba(7,20,34,.88);
}
.device-map-card__marker.shape-cross .device-map-card__marker-dot::before {
  width: 16px;
  height: 6px;
  border-radius: 4px;
}
.device-map-card__marker.shape-cross .device-map-card__marker-dot::after {
  width: 6px;
  height: 16px;
  border-radius: 4px;
}
.device-map-card__marker.is-high::after,
.device-map-card__marker.is-critical::after {
  border-color: color-mix(in srgb, var(--marker-ring) 45%, transparent);
  animation: device-map-halo 2.8s ease-in-out infinite;
}
.device-map-card__marker.is-critical::after {
  animation-duration: 2.2s;
}
.device-map-card__marker.is-active {
  z-index: 4;
}
.device-map-card__marker.is-active::after {
  opacity: .58;
  transform: scale(1.08);
  border-color: color-mix(in srgb, var(--marker-ring) 70%, transparent);
  animation: none;
}
.device-map-card__marker.is-active .device-map-card__marker-line {
  width: 22px;
  opacity: 1;
}
.device-map-card__marker.is-active .device-map-card__marker-dot {
  box-shadow:
    0 0 0 3px rgba(7,20,34,.92),
    0 0 0 6px color-mix(in srgb, var(--marker-ring) 18%, transparent),
    0 0 18px color-mix(in srgb, var(--marker-color) 72%, transparent);
}
.device-map-card__tooltip {
  position: absolute;
  min-width: 170px;
  max-width: 220px;
  padding: 10px 12px;
  border-radius: 4px;
  border: 1px solid rgba(80,199,255,.16);
  background: rgba(7,20,34,.96);
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
  color: #dffbff;
  pointer-events: none;
}
.device-map-card__marker.dir-left .device-map-card__tooltip {
  right: calc(100% + 12px);
  top: 50%;
  transform: translateY(-50%);
}
.device-map-card__marker.dir-right .device-map-card__tooltip {
  left: calc(100% + 12px);
  top: 50%;
  transform: translateY(-50%);
}
.device-map-card__tooltip-head,
.device-map-card__tooltip-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.device-map-card__tooltip-head strong {
  color: #effcff;
  font-size: 13px;
}
.device-map-card__tooltip-head span,
.device-map-card__tooltip-meta {
  color: #8fb8ca;
  font-size: 11px;
}
.device-map-card__tooltip-body {
  margin-top: 6px;
  color: #d9f6ff;
  font-size: 12px;
  line-height: 1.5;
}
.device-map-card__tooltip-meta {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(80,199,255,.1);
}
.device-map-card__list {
  display: grid;
  gap: 10px;
  align-self: stretch;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}
.device-map-card__list::-webkit-scrollbar {
  width: 6px;
}
.device-map-card__list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(80,199,255,.18);
}
.device-map-card__list::-webkit-scrollbar-track {
  background: transparent;
}
.device-map-card__item {
  min-width: 0;
  width: 100%;
  padding: 10px 12px;
  border-radius: 4px;
  background: rgba(8, 28, 44, 0.72);
  border: 1px solid rgba(80,199,255,.12);
  text-align: left;
  cursor: pointer;
  position: relative;
  transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}
.device-map-card__item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 999px;
  background: var(--item-accent, rgba(80,199,255,.24));
  opacity: .7;
}
.device-map-card__item.is-warning { border-color: rgba(245,158,11,.22); }
.device-map-card__item.is-high { border-color: rgba(249,115,22,.24); }
.device-map-card__item.is-critical { border-color: rgba(244,63,94,.28); }
.device-map-card__item:hover,
.device-map-card__item.is-active {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--item-ring) 58%, rgba(80,199,255,.14));
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}
.device-map-card__item strong {
  color: #effcff;
  font-size: 13px;
}
.device-map-card__item-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.device-map-card__item-top span,
.device-map-card__item-meta,
.device-map-card__empty {
  color: #8fb8ca;
  font-size: 12px;
}
.device-map-card__item-meta {
  margin-top: 6px;
  line-height: 1.45;
}
.device-map-card__empty {
  padding: 14px;
  border-radius: 4px;
  background: rgba(8, 28, 44, 0.72);
  border: 1px dashed rgba(80,199,255,.16);
}
html[data-theme='light'] .device-map-card__title,
html[data-theme='light'] .device-map-card__item strong {
  color: #17324a;
}
html[data-theme='light'] .device-map-card__legend-label {
  color: #4c7088;
}
html[data-theme='light'] .device-map-card__legend-item,
html[data-theme='light'] .device-map-card__item-tags span {
  background: rgba(255,255,255,.94);
  border-color: rgba(130, 170, 194, 0.24);
  color: #56748d;
}
html[data-theme='light'] .device-map-card__list::-webkit-scrollbar-thumb {
  background: rgba(130, 170, 194, 0.5);
}
html[data-theme='light'] .device-map-card__count,
html[data-theme='light'] .device-map-card__item,
html[data-theme='light'] .device-map-card__empty {
  background: rgba(255,255,255,.94);
  border-color: rgba(130, 170, 194, 0.24);
}
html[data-theme='light'] .device-map-card__item.is-active,
html[data-theme='light'] .device-map-card__item:hover {
  box-shadow: 0 8px 16px rgba(37,99,235,.12);
}
html[data-theme='light'] .device-map-card__count {
  color: #27445b;
}
html[data-theme='light'] .device-map-card__item-top span,
html[data-theme='light'] .device-map-card__item-meta,
html[data-theme='light'] .device-map-card__empty,
html[data-theme='light'] .device-map-card__kicker {
  color: #56748d;
}
html[data-theme='light'] .device-map-card__figure :deep(.organ-heatmap__svg) {
  filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.12));
}
html[data-theme='light'] .device-map-card__tooltip {
  background: rgba(255,255,255,.98);
  border-color: rgba(130, 170, 194, 0.34);
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
  color: #27445b;
}
html[data-theme='light'] .device-map-card__tooltip-head strong {
  color: #17324a;
}
html[data-theme='light'] .device-map-card__tooltip-head span,
html[data-theme='light'] .device-map-card__tooltip-meta {
  color: #56748d;
}
html[data-theme='light'] .device-map-card__tooltip-body {
  color: #27445b;
}
html[data-theme='light'] .device-map-card__tooltip-meta {
  border-top-color: rgba(130, 170, 194, 0.2);
}
@media (max-width: 680px) {
  .device-map-card__legend {
    gap: 6px;
  }
  .device-map-card__grid {
    grid-template-columns: 1fr;
  }
  .device-map-card__figure {
    min-height: 320px;
  }
  .device-map-card__figure :deep(.organ-heatmap__frame) {
    width: min(100%, 210px);
  }
  .device-map-card__tooltip {
    min-width: 150px;
    max-width: 180px;
  }
  .device-map-card__list {
    max-height: none;
    overflow: visible;
    padding-right: 0;
  }
}

@keyframes device-map-halo {
  0%, 100% {
    opacity: .16;
    transform: scale(.96);
  }
  50% {
    opacity: .34;
    transform: scale(1.08);
  }
}
</style>
