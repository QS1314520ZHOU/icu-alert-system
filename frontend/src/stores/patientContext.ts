/**
 * Patient context store — manages the active patient state for navigation.
 *
 * Rules:
 * - NEVER stores patient PHI in localStorage
 * - sessionStorage only stores patientId (no names, diagnoses, etc.)
 * - Does NOT depend on patient API response to generate menus
 * - Cleans up on leaving patient workflow
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'
import { getPatientIdFromRoute } from '../utils/patientRouteHelper'

const SESSION_KEY = 'icu_active_patient_id'

export interface PatientSnapshot {
  name?: string
  bed?: string
  dept?: string
  deptCode?: string
  gender?: string
  age?: number | string
}

export const usePatientContext = defineStore('patientContext', () => {
  const activePatientId = ref('')
  const patientSnapshot = ref<PatientSnapshot | null>(null)
  const originRoute = ref('')
  const lastModuleKey = ref('')
  const loading = ref(false)

  const hasPatient = computed(() => Boolean(activePatientId.value))

  /**
   * Sync activePatientId from route params.
   * Does NOT call any API — menu generation does not depend on patient data.
   */
  function syncFromRoute(route: RouteLocationNormalized) {
    const id = getPatientIdFromRoute(route)
    if (id && id !== activePatientId.value) {
      activePatientId.value = id
      // Save to sessionStorage (patientId only, no PHI)
      try {
        sessionStorage.setItem(SESSION_KEY, id)
      } catch {}
    }
    // Track module key from route
    const moduleKey = String(route.params.moduleKey || '')
    if (moduleKey) {
      lastModuleKey.value = moduleKey
    }
  }

  /**
   * Set a lightweight patient snapshot for display purposes.
   * This is NOT used for menu generation or auth.
   */
  function setSnapshot(data: PatientSnapshot) {
    patientSnapshot.value = { ...data }
  }

  /**
   * Record where the user came from before entering patient workflow.
   */
  function setOriginRoute(path: string) {
    if (path && !path.startsWith('/patient/') && !path.startsWith('/embed/patient/')) {
      originRoute.value = path
    }
  }

  /**
   * Restore patientId from sessionStorage on app init.
   */
  function restoreFromSession() {
    try {
      const stored = sessionStorage.getItem(SESSION_KEY)
      if (stored) {
        activePatientId.value = stored
      }
    } catch {}
  }

  /**
   * Clear patient context when leaving patient workflow.
   * Called on route changes that leave patient routes.
   */
  function clearContext() {
    activePatientId.value = ''
    patientSnapshot.value = null
    lastModuleKey.value = ''
    loading.value = false
    try {
      sessionStorage.removeItem(SESSION_KEY)
    } catch {}
  }

  return {
    activePatientId,
    patientSnapshot,
    originRoute,
    lastModuleKey,
    loading,
    hasPatient,
    syncFromRoute,
    setSnapshot,
    setOriginRoute,
    restoreFromSession,
    clearContext,
  }
})
