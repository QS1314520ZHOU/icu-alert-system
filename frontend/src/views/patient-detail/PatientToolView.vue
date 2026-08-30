<template>
  <div class="patient-tool-view">
    <!-- embed 模块：通过 iframe 加载 -->
    <PatientModuleFrame
      v-if="isEmbedModule"
      :module-key="moduleKey"
      :patient-id="patientId"
      :show-toolbar="true"
      @navigate-module="onNavigateModule"
      @navigate-patient="onNavigatePatient"
      @update-title="onUpdateTitle"
      @error="onError"
      @ready="onReady"
    />
    <!-- native 模块：直接渲染（不应走到这里，由独立路由处理） -->
    <div v-else class="patient-tool-native-fallback">
      <p>模块 "{{ moduleKey }}" 为原生模块，请通过专用路由访问。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PatientModuleFrame from '../../components/PatientModuleFrame.vue'
import { isIframeModule } from '../../config/patientModuleRegistry'
import { getPatientIdFromRoute } from '../../utils/patientRouteHelper'
import { buildContextQuery } from '../../navigation/routeContext'

const route = useRoute()
const router = useRouter()

const moduleKey = computed(() => String(route.params.moduleKey || ''))
const patientId = computed(() => getPatientIdFromRoute(route))
const isEmbedModule = computed(() => isIframeModule(moduleKey.value))

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
