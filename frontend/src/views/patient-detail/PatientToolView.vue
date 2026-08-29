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

const route = useRoute()
const router = useRouter()

const moduleKey = computed(() => String(route.params.moduleKey || ''))
const patientId = computed(() => String(route.params.id || ''))

function onNavigateModule(targetModuleKey: string) {
  router.push(`/patient/${patientId.value}/tool/${targetModuleKey}`)
}

function onNavigatePatient(targetPatientId: string) {
  router.push(`/patient/${targetPatientId}/tool/${moduleKey.value}`)
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
