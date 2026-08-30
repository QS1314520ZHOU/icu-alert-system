/**
 * useAppNavigation — composable for context-aware navigation.
 *
 * All navigation in the app should go through this composable
 * to ensure context is preserved and patientId is valid.
 */
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { usePatientContext } from '../stores/patientContext'
import { buildContextQuery, getOriginRoute } from './routeContext'
import { buildPatientPath } from '../utils/patientRouteHelper'
import { getModuleByKey, getModuleRoute } from '../config/patientModuleRegistry'

/** Global state for patient selector modal */
const showPatientSelector = ref(false)

export function useAppNavigation() {
  const router = useRouter()
  const route = useRoute()
  const patientCtx = usePatientContext()

  /**
   * Navigate to a patient page with context preservation.
   * If patientId is empty, does nothing (prevents invalid paths).
   */
  function navigateToPatient(patientId: string, suffix: string = 'overview') {
    const path = buildPatientPath(patientId, suffix)
    if (!path) return
    const query = buildContextQuery(route.query)
    router.push({ path, query })
  }

  /**
   * Navigate to a patient module (tool or native page).
   * If no active patient, opens the patient selector modal.
   * Uses registry to determine correct route for all modules.
   */
  function navigateToModule(moduleKey: string) {
    const patientId = patientCtx.activePatientId
    if (!patientId) {
      // Open patient selector, remember the target module
      patientCtx.setPendingModule(moduleKey)
      showPatientSelector.value = true
      return
    }

    navigateResolvedModule(patientId, moduleKey)
  }

  /**
   * Resolve and navigate to the correct route for a module using the registry.
   */
  function navigateResolvedModule(patientId: string, moduleKey: string) {
    const module = getModuleByKey(moduleKey)
    if (!module) {
      // Fallback: unknown module → overview
      navigateToPatient(patientId, 'overview')
      return
    }

    const path = getModuleRoute(moduleKey, patientId)
    const query = buildContextQuery(route.query)
    router.push({ path, query })
  }

  /**
   * Called when a patient is selected from the PatientSelectorModal.
   * Navigates to the pending module for the selected patient.
   */
  async function onPatientSelected(patientId: string) {
    showPatientSelector.value = false
    const moduleKey = patientCtx.consumePendingModule()

    if (!patientId) return

    // Sync patient context
    patientCtx.activePatientId = patientId
    try {
      const { useAuthStore } = await import('../stores/auth')
      const auth = useAuthStore()
      const userId = String(auth.userId || auth.userName || '').trim()
      const key = userId ? `icu_active_patient_id:${userId}` : 'icu_active_patient_id:anonymous'
      sessionStorage.setItem(key, patientId)
    } catch {}

    // Navigate using registry-based resolution
    if (moduleKey) {
      navigateResolvedModule(patientId, moduleKey)
    } else {
      navigateToPatient(patientId, 'overview')
    }
  }

  /**
   * Cancel patient selector.
   */
  function onCancelPatientSelector() {
    showPatientSelector.value = false
    patientCtx.clearPendingModule()
  }

  /**
   * Navigate back to origin route with context preservation.
   * Falls back to /patients if no origin is recorded.
   */
  function navigateBack() {
    const origin = getOriginRoute(patientCtx.originRoute)
    const query = buildContextQuery(route.query)
    router.push({ path: origin, query })
  }

  return {
    navigateToPatient,
    navigateToModule,
    navigateBack,
    onPatientSelected,
    onCancelPatientSelector,
    showPatientSelector,
    pendingModuleKey: patientCtx.pendingModuleKey,
  }
}
