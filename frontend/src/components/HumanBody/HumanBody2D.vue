<template>
  <div ref="rootRef" class="human-body-2d">
    <svg class="human-body-2d__svg" viewBox="0 0 360 700" role="img" aria-label="ICU organ alarm body map">
      <path class="body-glow" d="M180 20c-34 0-56 24-56 58 0 9 2 18 6 25-8 3-12 9-11 17 1 9 7 14 16 15 7 19 22 33 45 33s38-14 45-33c9-1 15-6 16-15 1-8-3-14-11-17 4-7 6-16 6-25 0-34-22-58-56-58Zm-43 151c-34 5-58 25-66 63L39 386c-4 20 1 38 15 50l5 4-2 20c-1 9 4 15 12 17 7 2 14-2 18-10l8-17 8 3-3 29c-1 8 4 14 12 15 7 1 13-3 16-10l12-31 4-100 2 122 20 54-18 121c-2 14 7 25 21 25h22c10 0 18-7 20-17l17-99 17 99c2 10 10 17 20 17h22c14 0 23-11 21-25l-18-121 20-54 2-122 4 100 12 31c3 7 9 11 16 10 8-1 13-7 12-15l-3-29 8-3 8 17c4 8 11 12 18 10 8-2 13-8 12-17l-2-20 5-4c14-12 19-30 15-50l-32-152c-8-38-32-58-66-63-18 18-40 27-66 27s-48-9-66-27Z" />
      <path class="body-outline" d="M180 23c-32 0-52 22-52 55 0 10 2 20 7 28-8 2-13 8-12 15 1 8 7 12 16 12 6 20 20 33 41 33s35-13 41-33c9 0 15-4 16-12 1-7-4-13-12-15 5-8 7-18 7-28 0-33-20-55-52-55Zm-39 150c-34 5-56 24-64 61L45 387c-4 18 1 34 13 44l10 8-3 22c-1 6 2 10 7 11 5 1 9-2 12-8l10-22 16 7-4 32c-1 5 2 9 7 10 5 1 9-2 11-7l14-35 4-119 14 184 19 53-17 89c-2 10 4 18 14 18h20c8 0 13-5 15-13l23-132 23 132c2 8 7 13 15 13h20c10 0 16-8 14-18l-17-89 19-53 14-184 4 119 14 35c2 5 6 8 11 7 5-1 8-5 7-10l-4-32 16-7 10 22c3 6 7 9 12 8 5-1 8-5 7-11l-3-22 10-8c12-10 17-26 13-44l-32-153c-8-37-30-56-64-61-19 17-40 25-65 25s-46-8-65-25Z" />

      <path id="svg-brain" class="organ organ-brain" d="M151 82c0-18 13-31 30-31 16 0 29 12 29 29 8 4 12 13 8 22-4 10-15 14-27 11-7 7-18 8-28 3-11 3-22-2-27-12-5-11 1-20 15-22Z" data-organ="brain" @click="handleClick('brain')" />

      <g class="organ-lines">
        <path d="M180 150v54" />
        <path d="M180 184c-20 5-31 16-39 35" />
        <path d="M180 184c20 5 31 16 39 35" />
      </g>
      <path id="svg-l-lung" class="organ organ-lung" d="M145 207c-22 8-36 35-36 68 0 29 12 48 31 48 23 0 34-28 34-82 0-21-10-38-29-34Z" data-organ="left_lung" @click="handleClick('left_lung')" />
      <path id="svg-r-lung" class="organ organ-lung" d="M215 207c22 8 36 35 36 68 0 29-12 48-31 48-23 0-34-28-34-82 0-21 10-38 29-34Z" data-organ="right_lung" @click="handleClick('right_lung')" />
      <path id="svg-heart" class="organ organ-heart" d="M181 291c-18-15-31-28-35-43-4-17 5-32 20-35 8-1 14 2 18 9 4-9 12-13 22-10 16 5 23 21 17 39-5 15-20 28-42 40Z" data-organ="heart" @click="handleClick('heart')" />
      <path id="svg-liver" class="organ organ-liver" d="M180 339c27-23 66-30 92-16 0 24-19 43-51 48-31 4-58-6-73-23 8-3 18-6 32-9Z" data-organ="liver" @click="handleClick('liver')" />
      <path id="svg-stomach" class="organ organ-stomach" d="M141 323c25 5 38 24 35 48-3 25-22 42-45 39-20-3-31-20-28-41 2-15 12-25 25-31 8-4 9-10 13-15Z" data-organ="stomach" @click="handleClick('stomach')" />
      <path id="svg-spleen" class="organ organ-spleen" d="M103 333c14 7 20 22 16 42-4 18-15 30-27 27-11-3-15-18-10-37 5-18 12-28 21-32Z" data-organ="spleen" @click="handleClick('spleen')" />
      <path id="svg-pancreas" class="organ organ-pancreas" d="M125 399c42-17 79-15 111 3-12 15-35 21-62 20-24-1-42-8-49-23Z" data-organ="pancreas" @click="handleClick('pancreas')" />
      <path id="svg-l-kidney" class="organ organ-kidney" d="M141 428c15 4 23 18 20 36-3 18-15 31-29 28-14-3-21-19-17-37 4-17 14-29 26-27Z" data-organ="left_kidney" @click="handleClick('left_kidney')" />
      <path id="svg-r-kidney" class="organ organ-kidney" d="M219 428c-15 4-23 18-20 36 3 18 15 31 29 28 14-3 21-19 17-37-4-17-14-29-26-27Z" data-organ="right_kidney" @click="handleClick('right_kidney')" />
      <path id="svg-intestine" class="organ organ-intestine" d="M127 497c16-20 90-20 106 0 13 17 8 54-8 67-20 16-70 16-90 0-16-13-21-50-8-67Zm24 19c-7 9-8 22 2 28 13 8 41 8 54 0 10-6 9-19 2-28-18 8-40 8-58 0Z" data-organ="intestine" @click="handleClick('intestine')" />
      <path id="svg-bladder" class="organ organ-bladder" d="M159 586c0-17 9-30 21-30s21 13 21 30c0 16-9 27-21 27s-21-11-21-27Z" data-organ="bladder" @click="handleClick('bladder')" />

      <g v-if="showLabels" class="labels">
        <text x="180" y="88">脑</text>
        <text x="180" y="230">心脏</text>
        <text x="124" y="260">左肺</text>
        <text x="236" y="260">右肺</text>
        <text x="224" y="340">肝</text>
        <text x="137" y="343">胃</text>
        <text x="180" y="398">胰</text>
        <text x="137" y="439">左肾</text>
        <text x="223" y="439">右肾</text>
        <text x="180" y="527">肠</text>
        <text x="180" y="592">膀胱</text>
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useHumanBodyAlarmStore } from '../../stores/humanBodyAlarmStore'
import { connectHumanBodyAlarmAdapter } from '../../services/humanBodyAlarmAdapter'
import { ORGAN_MAP } from './constants/organMap'
import type { HumanBodyAlarmRecord } from '../../types/alarm'
import type { OrganBusinessName } from '../../types/organ'

const props = withDefaults(defineProps<{
  patientId?: string
  autoFocus?: boolean
  showLabels?: boolean
}>(), {
  autoFocus: true,
  showLabels: true,
})

const emit = defineEmits<{
  ready: [organs: OrganBusinessName[]]
  'organ-click': [businessName: OrganBusinessName, patientId?: string]
}>()

const rootRef = ref<HTMLElement | null>(null)
const store = useHumanBodyAlarmStore()
const visibleAlarms = computed(() => {
  return props.patientId ? store.getAlarmsByPatient(props.patientId) : store.getAggregatedAlarms()
})
let offAlarmAdapter: (() => void) | null = null

function resetClasses() {
  Object.values(ORGAN_MAP).forEach((entry) => {
    const node = rootRef.value?.querySelector(entry.svg)
    node?.classList.remove('alarm-critical', 'alarm-warning', 'alarm-info', 'organ-selected')
  })
}

function applyAlarms(records: HumanBodyAlarmRecord[]) {
  resetClasses()
  records.forEach((record) => {
    const selector = ORGAN_MAP[record.organ].svg
    rootRef.value?.querySelector(selector)?.classList.add(`alarm-${record.level}`)
  })
}

function handleClick(businessName: OrganBusinessName) {
  resetClasses()
  applyAlarms(visibleAlarms.value)
  rootRef.value?.querySelector(ORGAN_MAP[businessName].svg)?.classList.add('organ-selected')
  emit('organ-click', businessName, props.patientId)
}

onMounted(() => {
  offAlarmAdapter = connectHumanBodyAlarmAdapter()
  applyAlarms(visibleAlarms.value)
  emit('ready', Object.keys(ORGAN_MAP) as OrganBusinessName[])
})

watch(visibleAlarms, records => applyAlarms(records), { deep: true })

onBeforeUnmount(() => {
  offAlarmAdapter?.()
  resetClasses()
})
</script>

<style scoped>
.human-body-2d {
  width: 100%;
  height: 100%;
  min-height: 320px;
  display: grid;
  place-items: center;
  background: radial-gradient(circle at 50% 26%, rgba(27, 67, 98, 0.72), #05070a 64%);
}

.human-body-2d__svg {
  width: min(100%, 440px);
  height: 100%;
  min-height: 320px;
}

.body-glow {
  fill: rgba(92, 206, 219, 0.18);
  filter: drop-shadow(0 0 22px rgba(91, 218, 232, 0.34));
}

.body-outline {
  fill: rgba(90, 159, 177, 0.28);
  stroke: rgba(126, 226, 238, 0.8);
  stroke-width: 4;
  stroke-linejoin: round;
  filter: drop-shadow(0 0 12px rgba(91, 218, 232, 0.46));
}

.organ {
  cursor: pointer;
  fill: rgba(246, 195, 202, 0.12);
  stroke: rgba(255, 205, 214, 0.78);
  stroke-width: 3;
  stroke-linejoin: round;
  stroke-linecap: round;
  filter: drop-shadow(0 0 8px rgba(255, 196, 208, 0.3));
  transition: filter 160ms ease, opacity 160ms ease, stroke-width 160ms ease, fill 160ms ease;
}

.organ:hover,
.organ-selected {
  stroke: #5ff3ff;
  stroke-width: 4;
  fill: rgba(95, 243, 255, 0.18);
  filter: drop-shadow(0 0 14px rgba(95, 243, 255, 0.86));
}

.organ-lines {
  fill: none;
  stroke: rgba(255, 205, 214, 0.72);
  stroke-width: 4;
  stroke-linecap: round;
  filter: drop-shadow(0 0 8px rgba(255, 196, 208, 0.36));
  pointer-events: none;
}

.organ-brain { fill: rgba(124, 226, 238, 0.14); stroke: rgba(126, 226, 238, 0.72); }
.organ-heart { fill: rgba(255, 183, 197, 0.2); stroke: rgba(255, 205, 214, 0.92); }
.organ-lung { fill: rgba(255, 205, 214, 0.12); stroke: rgba(255, 205, 214, 0.78); }
.organ-liver { fill: rgba(255, 190, 166, 0.14); stroke: rgba(255, 205, 214, 0.76); }
.organ-stomach { fill: rgba(146, 238, 188, 0.12); stroke: rgba(146, 238, 188, 0.68); }
.organ-kidney { fill: rgba(146, 238, 188, 0.12); stroke: rgba(146, 238, 188, 0.68); }
.organ-intestine,
.organ-bladder { fill: rgba(124, 226, 238, 0.12); stroke: rgba(126, 226, 238, 0.72); }
.organ-spleen,
.organ-pancreas { fill: rgba(255, 205, 214, 0.1); stroke: rgba(255, 205, 214, 0.64); }

.labels text,
.labels {
  fill: #e8f7ff;
  font-size: 14px;
  font-weight: 700;
  text-anchor: middle;
  pointer-events: none;
}

@keyframes blink-critical {
  0%, 100% { fill: #ff2222; opacity: 1; filter: drop-shadow(0 0 18px rgba(255, 34, 34, 0.9)); }
  50% { fill: #ff8888; opacity: 0.62; filter: drop-shadow(0 0 8px rgba(255, 34, 34, 0.5)); }
}

@keyframes blink-warning {
  0%, 100% { fill: #ffaa00; opacity: 1; filter: drop-shadow(0 0 14px rgba(255, 170, 0, 0.86)); }
  50% { fill: #ffd27a; opacity: 0.7; filter: drop-shadow(0 0 6px rgba(255, 170, 0, 0.45)); }
}

@keyframes blink-info {
  0%, 100% { fill: #ffee44; opacity: 0.94; filter: drop-shadow(0 0 10px rgba(255, 238, 68, 0.72)); }
  50% { fill: #fff6a8; opacity: 0.74; filter: none; }
}

.alarm-critical { animation: blink-critical 0.5s infinite; }
.alarm-warning { animation: blink-warning 1s infinite; }
.alarm-info { animation: blink-info 2s infinite; }
</style>
