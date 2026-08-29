<template>
  <div class="patient-tool-view">
    <PatientModuleFrame
      :module-key="moduleKey"
      :patient-id="patientId"
      :show-toolbar="true"
      @navigate-module="onNavigateModule"
      @navigate-patient="onNavigatePatient"
      @update-title="onUpdateTitle"
      @error="onError"
      @ready="onReady"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PatientModuleFrame from '../../components/PatientModuleFrame.vue'
import { getPatientIdFromRoute } from '../../utils/patientRouteHelper'
import { buildContextQuery } from '../../navigation/routeContext'

const route = useRoute()
const router = useRouter()

const moduleKey = computed(() => String(route.params.moduleKey || ''))
const patientId = computed(() => getPatientIdFromRoute(route))

function onNavigateModule(targetModuleKey: string) {
  const query = buildContextQuery(route.query)
  router.push({ path: `/patient/${patientId.value}/tool/${targetModuleKey}`, query })
}

function onNavigatePatient(targetPatientId: string) {
  const query = buildContextQuery(route.query)
  router.push({ path: `/patient/${targetPatientId}/tool/${moduleKey.value}`, query })
}

function onUpdateTitle(title: string) {
  document.title = `${title} - SmartCare AI`
}

function onError(error: string) {
  console.error('[PatientToolView] Module error:', error)
}

function onReady() {
  console.log('[PatientToolView] Module ready:', moduleKey.value)
}
</script>

<style scoped>
.patient-tool-view {
  width: 100%;
  min-height: 0;
}
</style>
