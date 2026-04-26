<template>
  <section class="device-map-card">
    <div class="device-map-card__head">
      <div>
        <div class="device-map-card__kicker">装置位置图</div>
        <div class="device-map-card__title">留置装置 / 管路巡视</div>
      </div>
      <span class="device-map-card__count">{{ markers.length }} 项</span>
    </div>

    <div v-if="markers.length" class="device-map-card__grid">
      <HumanBodyDiagram compact :device-markers="markers" />
      <div class="device-map-card__list">
        <div v-for="item in markers" :key="item.key" :class="['device-map-card__item', `is-${item.severity}`]">
          <div class="device-map-card__item-top">
            <strong>{{ item.label }}</strong>
            <span>{{ item.daysText || '在位' }}</span>
          </div>
          <div class="device-map-card__item-meta">{{ item.detail || '需要持续评估必要性与感染风险' }}</div>
        </div>
      </div>
    </div>
    <div v-else class="device-map-card__empty">当前未识别到活动导管或装置。</div>
  </section>
</template>

<script setup lang="ts">
import HumanBodyDiagram from '../common/HumanBodyDiagram.vue'

defineProps<{
  markers: Array<{
    key: string
    label: string
    severity: string
    site: string
    daysText?: string
    detail?: string
    blink?: boolean
  }>
}>()
</script>

<style scoped>
.device-map-card {
  display: grid;
  gap: 12px;
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
  font-size: 18px;
  font-weight: 800;
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
.device-map-card__grid {
  display: grid;
  grid-template-columns: minmax(184px, 206px) minmax(0, 1fr);
  gap: 16px;
  align-items: center;
}
.device-map-card__grid :deep(.human-body__frame) {
  width: min(100%, 182px);
}
.device-map-card__grid :deep(.human-body__svg) {
  filter: drop-shadow(0 0 14px rgba(99, 233, 255, 0.16));
}
.device-map-card__list {
  display: grid;
  gap: 10px;
  align-self: stretch;
}
.device-map-card__item {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(8, 28, 44, 0.72);
  border: 1px solid rgba(80,199,255,.12);
}
.device-map-card__item.is-warning { border-color: rgba(245,158,11,.22); }
.device-map-card__item.is-high { border-color: rgba(249,115,22,.24); }
.device-map-card__item.is-critical { border-color: rgba(244,63,94,.28); }
.device-map-card__item strong {
  color: #effcff;
  font-size: 13px;
}
.device-map-card__item-top span,
.device-map-card__item-meta,
.device-map-card__empty {
  color: #8fb8ca;
  font-size: 12px;
}
.device-map-card__item-meta {
  margin-top: 3px;
  line-height: 1.45;
}
.device-map-card__empty {
  padding: 14px;
  border-radius: 12px;
  background: rgba(8, 28, 44, 0.72);
  border: 1px dashed rgba(80,199,255,.16);
}
html[data-theme='light'] .device-map-card__title,
html[data-theme='light'] .device-map-card__item strong {
  color: #17324a;
}
html[data-theme='light'] .device-map-card__count,
html[data-theme='light'] .device-map-card__item,
html[data-theme='light'] .device-map-card__empty {
  background: rgba(255,255,255,.94);
  border-color: rgba(130, 170, 194, 0.24);
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
html[data-theme='light'] .device-map-card__grid :deep(.human-body__svg) {
  filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.12));
}
@media (max-width: 680px) {
  .device-map-card__grid {
    grid-template-columns: 1fr;
  }
  .device-map-card__grid :deep(.human-body__frame) {
    width: min(100%, 180px);
  }
}
</style>
