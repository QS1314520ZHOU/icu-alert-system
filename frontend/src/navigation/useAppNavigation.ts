/**
 * useAppNavigation — composable for context-aware navigation.
 *
 * All navigation in the app should go through this composable
 * to ensure context is preserved and patientId is valid.
 */
import { useRouter, useRoute } from 'vue-router'
import { usePatientContext } from '../stores/patientContext'
import { buildContextQuery, getOriginRoute } from './routeContext'
import { buildPatientPath } from '../utils/patientRouteHelper'

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
   */
  function navigateToModule(moduleKey: string) {
    const patientId = patientCtx.activePatientId
    if (!patientId) return

    // Check if it's a native page (overview, monitoring, treatment, alerts)
    const nativePages = ['overview', 'monitoring', 'treatment', 'alerts']
    if (nativePages.includes(moduleKey)) {
      navigateToPatient(patientId, moduleKey)
      return
    }

    // Otherwise it's a tool module
    const path = buildPatientPath(patientId, `tool/${moduleKey}`)
    if (!path) return
    const query = buildContextQuery(route.query)
    router.push({ path, query })
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

  /**
   * Navigate with patient selector fallback.
   * If no active patient, opens the patient selector.
   * If patient exists, navigates directly.
   * Returns true if navigated, false if selector was opened.
   */
  function navigateWithPatientSelector(targetPath: string): boolean {
    const patientId = patientCtx.activePatientId
    if (!patientId) {
      // Open patient selector — for now, navigate to patient list with return path
      const query = buildContextQuery(route.query, { returnTo: targetPath })
      router.push({ path: '/patients', query })
      return false
    }

    // Replace :patientId placeholder in target path
    const resolvedPath = targetPath.replace(':patientId', patientId)
    const query = buildContextQuery(route.query)
    router.push({ path: resolvedPath, query })
    return true
  }

  return {
    navigateToPatient,
    navigateToModule,
    navigateBack,
    navigateWithPatientSelector,
  }
}
