<template>
  <div class="patient-tool-view">
    <!-- embed 模块：直接渲染（消除 iframe 开销） -->
    <component
      :is="directComponent"
      v-if="isEmbedModule && directComponent"
    />
    <!-- iframe 模块回退（仅当直接渲染不可用时） -->
    <PatientModuleFrame
      v-else-if="isEmbedModule"
      :module-key="moduleKey"
      :patient-id="patientId"
      :show-toolbar="true"
      @navigate-module="onNavigateModule"
      @navigate-patient="onNavigatePatient"
      @update-title="onUpdateTitle"
      @error="onError"
      @ready="onReady"
    />
    <!-- native 模块 -->
    <div v-else class="patient-tool-native-fallback">
      <p>模块 "{{ moduleKey }}" 为原生模块，请通过专用路由访问。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
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

// 直接渲染映射：跳过 iframe，消除 5s+ 加载延迟
const DIRECT_COMPONENT_MAP: Record<string, () => Promise<any>> = {
  'risk-prediction': () => import('../embed/risk-prediction/RiskPredictionView.vue'),
  'similar-cases': () => import('../embed/similar-cases/SimilarCasesView.vue'),
  'causal-inference': () => import('../embed/causal-inference/CausalInferenceView.vue'),
  'what-if': () => import('../embed/what-if/WhatIfView.vue'),
  'integrated-risk': () => import('../embed/integrated-risk/IntegratedRiskView.vue'),
  'disease-trajectory': () => import('../embed/disease-trajectory/DiseaseTrajectoryView.vue'),
  'evidence': () => import('../embed/evidence/EvidenceView.vue'),
  'decision-assistants': () => import('../embed/decision-assistants/DecisionAssistantsView.vue'),
}

const directComponent = computed(() => {
  const loader = DIRECT_COMPONENT_MAP[moduleKey.value]
  return loader ? defineAsyncComponent(loader) : null
})

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
