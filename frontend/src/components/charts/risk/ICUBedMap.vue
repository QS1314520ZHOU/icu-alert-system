<template>
  <div class="bed-map">
    <div class="bed-map__header">
      <span class="bed-map__title">{{ title ?? 'ICU床位概览' }}</span>
      <span class="bed-map__summary">
        <span class="bed-map__stat"><span class="bed-map__dot bed-map__dot--critical" />{{ criticalCount }} 危急</span>
        <span class="bed-map__stat"><span class="bed-map__dot bed-map__dot--high" />{{ highCount }} 高风险</span>
        <span class="bed-map__stat"><span class="bed-map__dot bed-map__dot--normal" />{{ normalCount }} 稳定</span>
        <span class="bed-map__stat"><span class="bed-map__dot bed-map__dot--empty" />{{ emptyCount }} 空床</span>
      </span>
    </div>

    <div class="bed-map__grid" :style="gridStyle">
      <div
        v-for="bed in beds"
        :key="bed.bedNo"
        class="bed-card"
        :class="[
          `bed-card--${bed.status}`,
          { 'bed-card--clickable': !!bed.patientId }
        ]"
        @click="bed.patientId && $emit('bedClick', bed)"
      >
        <!-- 状态色条 -->
        <div class="bed-card__rail" />

        <div class="bed-card__header">
          <span class="bed-card__bedno">{{ bed.bedNo }}</span>
          <span v-if="bed.alertCount" class="bed-card__alerts">
            <AlertOutlined /> {{ bed.alertCount }}
          </span>
        </div>

        <template v-if="bed.patientName">
          <div class="bed-card__patient">
            <span class="bed-card__name">{{ bed.patientName }}</span>
            <span class="bed-card__age">{{ bed.age }}{{ bed.gender }}</span>
          </div>

          <div class="bed-card__vitals">
            <span class="bed-card__vital" v-if="bed.hr !== undefined">
              <span class="bed-card__vital-label">HR</span>
              <span class="bed-card__vital-value" :style="{ color: getVitalColor('hr', bed.hr) }">{{ bed.hr }}</span>
            </span>
            <span class="bed-card__vital" v-if="bed.bp">
              <span class="bed-card__vital-label">BP</span>
              <span class="bed-card__vital-value">{{ bed.bp }}</span>
            </span>
            <span class="bed-card__vital" v-if="bed.spo2 !== undefined">
              <span class="bed-card__vital-label">SpO₂</span>
              <span class="bed-card__vital-value" :style="{ color: getVitalColor('spo2', bed.spo2) }">{{ bed.spo2 }}%</span>
            </span>
          </div>

          <div v-if="bed.device" class="bed-card__device">
            <ExperimentOutlined /> {{ bed.device }}
          </div>
        </template>

        <template v-else>
          <div class="bed-card__empty">空床</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { AlertOutlined, ExperimentOutlined } from '@ant-design/icons-vue'

export interface BedInfo {
  bedNo: string
  patientId?: string
  patientName?: string
  age?: number
  gender?: string
  status: 'critical' | 'high' | 'normal' | 'empty' | 'disconnected'
  hr?: number
  bp?: string
  spo2?: number
  device?: string
  alertCount?: number
  pendingTasks?: number
}

const props = withDefaults(defineProps<{
  title?: string
  beds: BedInfo[]
  columns?: number
}>(), {
  columns: 6,
})

defineEmits<{ bedClick: [BedInfo] }>()

const gridStyle = computed(() => ({
  display: 'grid',
  gridTemplateColumns: `repeat(${props.columns}, 1fr)`,
  gap: '12px',
}))

const criticalCount = computed(() => props.beds.filter(b => b.status === 'critical').length)
const highCount = computed(() => props.beds.filter(b => b.status === 'high').length)
const normalCount = computed(() => props.beds.filter(b => b.status === 'normal').length)
const emptyCount = computed(() => props.beds.filter(b => b.status === 'empty').length)

function getVitalColor(type: string, value: number): string {
  if (type === 'hr') {
    if (value < 50 || value > 130) return '#D92D20'
    if (value < 60 || value > 100) return '#F79009'
    return '#12A66A'
  }
  if (type === 'spo2') {
    if (value < 90) return '#D92D20'
    if (value < 95) return '#F79009'
    return '#12A66A'
  }
  return '#17233D'
}
</script>

<style scoped>
.bed-map {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
}

.bed-map__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.bed-map__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.bed-map__summary {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.bed-map__stat {
  display: flex;
  align-items: center;
  gap: 4px;
}

.bed-map__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.bed-map__dot--critical { background: var(--color-danger); }
.bed-map__dot--high { background: var(--color-high-risk); }
.bed-map__dot--normal { background: var(--color-normal); }
.bed-map__dot--empty { background: var(--color-border-strong); }

.bed-card {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--color-bg-surface);
  overflow: hidden;
  transition: all 0.2s;
}

.bed-card--clickable { cursor: pointer; }
.bed-card--clickable:hover { box-shadow: var(--shadow-md); }

.bed-card__rail {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
}

.bed-card--critical .bed-card__rail { background: var(--color-danger); }
.bed-card--high .bed-card__rail { background: var(--color-high-risk); }
.bed-card--normal .bed-card__rail { background: var(--color-normal); }
.bed-card--empty { border-style: dashed; border-color: var(--color-border-strong); }

.bed-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.bed-card__bedno {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.bed-card__alerts {
  font-size: 11px;
  color: var(--color-danger);
  display: flex;
  align-items: center;
  gap: 2px;
}

.bed-card__patient {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 6px;
}

.bed-card__name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.bed-card__age {
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.bed-card__vitals {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.bed-card__vital {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.bed-card__vital-label {
  font-size: 10px;
  color: var(--color-text-tertiary);
}

.bed-card__vital-value {
  font-family: 'Rajdhani', sans-serif;
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.bed-card__device {
  font-size: 10px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.bed-card__empty {
  font-size: 12px;
  color: var(--color-text-tertiary);
  text-align: center;
  padding: 12px 0;
}
</style>
