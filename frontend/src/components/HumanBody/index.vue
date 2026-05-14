<template>
  <HumanBody2D
    v-if="resolvedTier === 'fallback'"
    :patient-id="patientId"
    :auto-focus="autoFocus"
    :show-labels="showLabels"
    @organ-click="emitOrganClick"
    @ready="emit('ready')"
  />
  <HumanBody3D
    v-else
    :model="resolvedTier === 'low' ? 'low' : 'high'"
    :patient-id="patientId"
    :auto-focus="autoFocus"
    :show-labels="showLabels"
    @organ-click="emitOrganClick"
    @ready="emit('ready')"
    @load-failed="handleLoadFailed"
    @performance-degraded="handlePerformanceDegraded"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import HumanBody3D from './HumanBody3D.vue'
import HumanBody2D from './HumanBody2D.vue'
import { detectDeviceTier } from './composables/useDeviceTier'
import type { HumanBodyForceTier, HumanBodyTier, OrganBusinessName } from '../../types/organ'

const props = withDefaults(defineProps<{
  patientId?: string
  autoFocus?: boolean
  showLabels?: boolean
  forceTier?: HumanBodyForceTier
}>(), {
  autoFocus: true,
  showLabels: true,
})

const emit = defineEmits<{
  'organ-click': [businessName: OrganBusinessName, patientId?: string]
  ready: []
  'load-failed': [reason: string]
  'performance-degraded': [fps: number]
}>()

function tierFromForce(value?: HumanBodyForceTier | null): HumanBodyTier | null {
  if (value === '2d') return 'fallback'
  if (value === 'high' || value === 'low') return value
  return null
}

function forceFromQuery(): HumanBodyForceTier | null {
  if (typeof window === 'undefined') return null
  const raw = new URLSearchParams(window.location.search).get('force')
  if (raw === 'high' || raw === 'low' || raw === '2d') return raw
  return null
}

const detectedTier = ref<HumanBodyTier>(tierFromForce(props.forceTier) || tierFromForce(forceFromQuery()) || detectDeviceTier())
const degraded = ref(false)
const resolvedTier = computed<HumanBodyTier>(() => degraded.value ? 'fallback' : detectedTier.value)

function emitOrganClick(businessName: OrganBusinessName) {
  emit('organ-click', businessName, props.patientId)
}

function handleLoadFailed(reason: string) {
  degraded.value = true
  emit('load-failed', reason)
}

function handlePerformanceDegraded(fps: number) {
  degraded.value = true
  emit('performance-degraded', fps)
}
</script>
