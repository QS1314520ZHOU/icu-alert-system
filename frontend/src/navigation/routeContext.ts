/**
 * Route context helpers — preserves work context across navigation.
 *
 * Only whitelisted keys are propagated:
 * - dept_code (canonical)
 * - dept
 * - ward
 * - shift
 *
 * Legacy `deptCode` is accepted as input but output always uses `dept_code`.
 */
import type { LocationQuery, RouteLocationNormalized } from 'vue-router'

/** Whitelisted context keys that propagate across navigation */
const ALLOWED_CONTEXT_KEYS = ['dept_code', 'dept', 'ward', 'shift'] as const

/** Legacy key mapping: deptCode → dept_code */
const LEGACY_KEY_MAP: Record<string, string> = {
  deptCode: 'dept_code',
}

/**
 * Extract whitelisted context from a route's query string.
 */
export function extractContextQuery(query: LocationQuery): LocationQuery {
  const result: LocationQuery = {}
  for (const key of ALLOWED_CONTEXT_KEYS) {
    const value = query[key]
    if (value !== undefined && value !== null && value !== '') {
      result[key] = value
    }
  }
  // Accept legacy deptCode as dept_code
  if (!result.dept_code && query.deptCode) {
    result.dept_code = query.deptCode
  }
  return result
}

/**
 * Build a context query object for navigation.
 * Merges current route context with optional extra params.
 */
export function buildContextQuery(
  currentQuery: LocationQuery,
  extra?: Record<string, string>
): LocationQuery {
  const context = extractContextQuery(currentQuery)
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      if (value) context[key] = value
    }
  }
  return context
}

/**
 * Preserve context when navigating from one route to another.
 * Copies whitelisted query params from `from` route to `to` route.
 */
export function preserveContextQuery(
  toQuery: LocationQuery,
  fromQuery: LocationQuery
): LocationQuery {
  const context = extractContextQuery(fromQuery)
  return { ...context, ...toQuery }
}

/**
 * Get the origin route for "back" navigation.
 * Reads from patientContext store, falls back to /patients.
 */
export function getOriginRoute(originFromStore?: string): string {
  if (originFromStore && !originFromStore.startsWith('/patient/')) {
    return originFromStore
  }
  return '/patients'
}
