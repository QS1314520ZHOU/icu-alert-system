/**
 * useNavigationContext — composable for reading/writing work context.
 *
 * Only propagates whitelisted context keys:
 * - dept_code (canonical, NOT deptCode)
 * - dept
 * - ward
 * - shift
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { extractContextQuery } from './routeContext'

export function useNavigationContext() {
  const route = useRoute()

  /** Current department code from route query */
  const deptCode = computed(() => {
    const ctx = extractContextQuery(route.query)
    return String(ctx.dept_code || '')
  })

  /** Current department name from route query */
  const dept = computed(() => {
    const ctx = extractContextQuery(route.query)
    return String(ctx.dept || '')
  })

  /** Current ward from route query */
  const ward = computed(() => {
    const ctx = extractContextQuery(route.query)
    return String(ctx.ward || '')
  })

  /** Current shift from route query */
  const shift = computed(() => {
    const ctx = extractContextQuery(route.query)
    return String(ctx.shift || '')
  })

  /** All context as a query object */
  const contextQuery = computed(() => extractContextQuery(route.query))

  return {
    deptCode,
    dept,
    ward,
    shift,
    contextQuery,
  }
}
