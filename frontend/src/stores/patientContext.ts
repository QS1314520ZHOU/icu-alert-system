/**
 * Patient context store — manages the active patient state for navigation.
 *
 * Rules:
 * - NEVER stores patient PHI in localStorage
 * - sessionStorage only stores patientId (no names, diagnoses, etc.)
 * - sessionStorage key is scoped by authenticatedUserId
 * - Does NOT depend on patient API response to generate menus
 * - Cleans up on leaving patient workflow
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'
import { getPatientIdFromRoute } from '../utils/patientRouteHelper'
import { useAuthStore } from './auth'

export interface PatientSnapshot {
  name?: string
  bed?: string
  dept?: string
  deptCode?: string
  gender?: string
  age?: number | string
}

/**
 * Generate user-scoped sessionStorage key.
 * Falls back to a global key if no user is authenticated.
 */
function getSessionKey(userId?: string): string {
  if (userId) return `icu_active_patient_id:${userId}`
  return 'icu_active_patient_id:anonymous'
}

export const usePatientContext = defineStore('patientContext', () => {
  const activePatientId = ref('')
  const patientSnapshot = ref<PatientSnapshot | null>(null)
  const originRoute = ref('')
  const lastModuleKey = ref('')
  const loading = ref(false)
  const pendingModuleKey = ref('')

  const hasPatient = computed(() => Boolean(activePatientId.value))

  /**
   * Get the current authenticated user ID from auth store.
   * Called inside functions (not at module level) to avoid circular dependency.
   */
  function getCurrentUserId(): string {
    try {
      const auth = useAuthStore()
      return String(auth.userId || auth.userName || '').trim()
    } catch {
      return ''
    }
  }

  /**
   * Sync activePatientId from route params.
   * Does NOT call any API — menu generation does not depend on patient data.
   */
  function syncFromRoute(route: RouteLocationNormalized) {
    const id = getPatientIdFromRoute(route)
    if (id && id !== activePatientId.value) {
      activePatientId.value = id
      // Save to sessionStorage with user-scoped key
      try {
        const userId = getCurrentUserId()
        sessionStorage.setItem(getSessionKey(userId), id)
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
   * Uses user-scoped key.
   */
  function restoreFromSession() {
    try {
      const userId = getCurrentUserId()
      const key = getSessionKey(userId)
      const stored = sessionStorage.getItem(key)
      if (stored) {
        activePatientId.value = stored
      } else {
        // Try legacy key for migration
        const legacyStored = sessionStorage.getItem('icu_active_patient_id')
        if (legacyStored) {
          activePatientId.value = legacyStored
          // Migrate to user-scoped key
          sessionStorage.setItem(key, legacyStored)
          sessionStorage.removeItem('icu_active_patient_id')
        }
      }
    } catch {}
  }

  /**
   * Set pending module key for patient selector flow.
   */
  function setPendingModule(moduleKey: string) {
    pendingModuleKey.value = moduleKey
  }

  /**
   * Consume (return and clear) the pending module key.
   */
  function consumePendingModule(): string {
    const key = pendingModuleKey.value
    pendingModuleKey.value = ''
    return key
  }

  /**
   * Clear pending module key without consuming.
   */
  function clearPendingModule() {
    pendingModuleKey.value = ''
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
    pendingModuleKey.value = ''
    try {
      const userId = getCurrentUserId()
      sessionStorage.removeItem(getSessionKey(userId))
    } catch {}
  }

  /**
   * Clear ALL patient session data (for logout / user switch).
   * Removes keys for all known users.
   */
  function clearAllSessionData() {
    activePatientId.value = ''
    patientSnapshot.value = null
    lastModuleKey.value = ''
    loading.value = false
    pendingModuleKey.value = ''
    try {
      // Remove current user's key
      const userId = getCurrentUserId()
      sessionStorage.removeItem(getSessionKey(userId))
      // Also remove legacy key
      sessionStorage.removeItem('icu_active_patient_id')
      // Remove any other user-scoped keys
      for (let i = sessionStorage.length - 1; i >= 0; i--) {
        const key = sessionStorage.key(i)
        if (key && key.startsWith('icu_active_patient_id')) {
          sessionStorage.removeItem(key)
        }
      }
    } catch {}
  }

  return {
    activePatientId,
    patientSnapshot,
    originRoute,
    lastModuleKey,
    loading,
    hasPatient,
    pendingModuleKey,
    syncFromRoute,
    setSnapshot,
    setOriginRoute,
    restoreFromSession,
    clearContext,
    clearAllSessionData,
    setPendingModule,
    consumePendingModule,
    clearPendingModule,
  }
})
