/**
 * Unified patient ID extraction from route params.
 *
 * During migration, routes use `:patientId` as the canonical param name.
 * This helper provides a single read入口 so business components never
 * scatter `route.params.id` / `route.params.patientId` checks.
 */
import type { RouteLocationNormalized } from 'vue-router'

/** Canonical param name for patient routes */
export const PATIENT_ID_PARAM = 'patientId'

/**
 * Extract patient ID from any patient-related route.
 *
 * Checks `params.patientId` first (canonical), then falls back to `params.id`
 * for backward compatibility during migration.
 */
export function getPatientIdFromRoute(route: RouteLocationNormalized): string {
  return String(route.params[PATIENT_ID_PARAM] || route.params.id || '').trim()
}

/**
 * Build a patient path with the given module suffix.
 * Returns empty string if patientId is empty (prevents generating invalid paths).
 */
export function buildPatientPath(patientId: string, suffix: string = ''): string {
  if (!patientId) return ''
  const base = `/patient/${patientId}`
  return suffix ? `${base}/${suffix}` : base
}
