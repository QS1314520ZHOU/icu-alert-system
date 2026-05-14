<template>
  <div ref="rootRef" class="human-body-2d">
    <svg class="human-body-2d__svg" viewBox="0 0 320 620" role="img" aria-label="ICU organ alarm body map">
      <path class="body-outline" d="M160 24c-38 0-68 30-68 68 0 23 11 44 29 56v38c-52 16-82 62-82 122v126c0 35 23 62 58 69l18 4v72h90v-72l18-4c35-7 58-34 58-69V308c0-60-30-106-82-122v-38c18-12 29-33 29-56 0-38-30-68-68-68Z" />

      <ellipse id="svg-brain" class="organ organ-brain" cx="160" cy="83" rx="42" ry="30" data-organ="brain" @click="handleClick('brain')" />
      <path id="svg-l-lung" class="organ organ-lung" d="M108 188c-24 19-37 56-30 98 5 32 22 52 44 50 18-2 27-18 27-42V181c-14 0-28 2-41 7Z" data-organ="left_lung" @click="handleClick('left_lung')" />
      <path id="svg-r-lung" class="organ organ-lung" d="M212 188c24 19 37 56 30 98-5 32-22 52-44 50-18-2-27-18-27-42V181c14 0 28 2 41 7Z" data-organ="right_lung" @click="handleClick('right_lung')" />
      <path id="svg-heart" class="organ organ-heart" d="M160 267c-34-24-51-43-51-66 0-18 13-31 31-31 9 0 16 4 20 11 4-7 11-11 20-11 18 0 31 13 31 31 0 23-17 42-51 66Z" data-organ="heart" @click="handleClick('heart')" />
      <path id="svg-liver" class="organ organ-liver" d="M162 318c25-28 67-40 101-27 4 31-15 58-55 66-28 5-54-5-73-23 7-5 16-11 27-16Z" data-organ="liver" @click="handleClick('liver')" />
      <ellipse id="svg-stomach" class="organ organ-stomach" cx="116" cy="329" rx="35" ry="48" transform="rotate(-15 116 329)" data-organ="stomach" @click="handleClick('stomach')" />
      <ellipse id="svg-spleen" class="organ organ-spleen" cx="73" cy="338" rx="17" ry="38" transform="rotate(-10 73 338)" data-organ="spleen" @click="handleClick('spleen')" />
      <path id="svg-pancreas" class="organ organ-pancreas" d="M97 385c43-22 82-21 126 1-10 20-36 25-63 24-27-1-51-7-63-25Z" data-organ="pancreas" @click="handleClick('pancreas')" />
      <ellipse id="svg-l-kidney" class="organ organ-kidney" cx="106" cy="420" rx="22" ry="38" transform="rotate(18 106 420)" data-organ="left_kidney" @click="handleClick('left_kidney')" />
      <ellipse id="svg-r-kidney" class="organ organ-kidney" cx="214" cy="420" rx="22" ry="38" transform="rotate(-18 214 420)" data-organ="right_kidney" @click="handleClick('right_kidney')" />
      <path id="svg-intestine" class="organ organ-intestine" d="M105 461c16-16 94-16 110 0 16 16 10 64-6 78-19 17-79 17-98 0-16-14-22-62-6-78Zm26 25c-9 14-5 30 12 33 18 4 38 4 56 0 17-3 21-19 12-33-23 8-57 8-80 0Z" data-organ="intestine" @click="handleClick('intestine')" />
      <ellipse id="svg-bladder" class="organ organ-bladder" cx="160" cy="555" rx="26" ry="22" data-organ="bladder" @click="handleClick('bladder')" />

      <g v-if="showLabels" class="labels">
        <text x="160" y="86">脑</text>
        <text x="160" y="219">心脏</text>
        <text x="95" y="265">左肺</text>
        <text x="225" y="265">右肺</text>
        <text x="207" y="329">肝</text>
        <text x="113" y="333">胃</text>
        <text x="160" y="391">胰</text>
        <text x="101" y="424">左肾</text>
        <text x="219" y="424">右肾</text>
        <text x="160" y="506">肠</text>
        <text x="160" y="560">膀胱</text>
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
  width: min(100%, 420px);
  height: 100%;
  min-height: 320px;
}

.body-outline {
  fill: rgba(38, 69, 94, 0.34);
  stroke: rgba(133, 211, 255, 0.45);
  stroke-width: 2;
}

.organ {
  cursor: pointer;
  fill: rgba(106, 160, 190, 0.62);
  stroke: rgba(210, 241, 255, 0.7);
  stroke-width: 2;
  transition: filter 160ms ease, opacity 160ms ease, stroke-width 160ms ease;
}

.organ:hover,
.organ-selected {
  stroke: #00e5ff;
  stroke-width: 4;
  filter: drop-shadow(0 0 12px rgba(0, 229, 255, 0.85));
}

.organ-heart { fill: rgba(255, 107, 122, 0.7); }
.organ-lung { fill: rgba(127, 213, 255, 0.58); }
.organ-liver { fill: rgba(197, 139, 74, 0.72); }
.organ-stomach { fill: rgba(230, 161, 198, 0.68); }
.organ-kidney { fill: rgba(211, 107, 75, 0.66); }

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
