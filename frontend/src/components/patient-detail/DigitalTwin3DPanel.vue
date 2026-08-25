<template>
  <div class="twin-body-panel">
    <OrganHeatmapFigure
      :organ-states="organStateMap"
      :show-legend="true"
      :silhouette="'male'"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OrganHeatmapFigure from '../common/OrganHeatmapFigure.vue'
import type { OrganState } from '../../composables/useOrganSeverity'

const props = withDefaults(defineProps<{
  organStates: OrganState[]
  active?: boolean
}>(), {
  active: true,
})

const organStateMap = computed(() => {
  const map: Record<string, any> = {}
  for (const s of props.organStates) {
    map[s.key] = {
      severity: s.severity,
      sofa: s.sofa,
      source: s.source,
      metrics: s.metrics,
    }
  }
  return map
})
</script>

<style scoped>
.twin-body-panel {
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
}
</style>
