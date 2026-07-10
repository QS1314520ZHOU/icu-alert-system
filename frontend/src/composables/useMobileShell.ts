import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getClinicalAccount } from '../api'
import { useAuthStore } from '../stores/auth'
import { normalizeMobileRole } from '../mobile/mobileNav'

function detectContainer() {
  if (typeof navigator === 'undefined') return 'browser'
  const ua = navigator.userAgent.toLowerCase()
  if (ua.includes('micromessenger') || ua.includes('wxwork')) return 'wechat'
  if (ua.includes('dingtalk')) return 'dingtalk'
  if (window.matchMedia?.('(display-mode: standalone)').matches) return 'pwa'
  return 'browser'
}

const width = ref(typeof window === 'undefined' ? 390 : window.innerWidth)
const height = ref(typeof window === 'undefined' ? 844 : window.innerHeight)
const container = ref(detectContainer())
const departments = ref<any[]>([])
const resolvingIdentity = ref(false)
let resolvePromise: Promise<void> | null = null
let shellMounted = 0

export function useMobileShell() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()

  function syncViewport() {
    width.value = window.innerWidth
    height.value = window.innerHeight
    container.value = detectContainer()
  }

  function deptCodeTokens(value: any) {
    return String(value || '').split(',').map((item) => item.trim()).filter(Boolean)
  }

  function deptNameTokens(value: any) {
    return String(value || '').split(/[、,]/).map((item) => item.trim()).filter(Boolean)
  }

  function departmentsFromAccount(account: any) {
    const rows = Array.isArray(account?.departments) ? account.departments : []
    if (rows.length) return rows
    const codes = deptCodeTokens(account?.dept_code || account?.deptCode)
    const names = deptNameTokens(account?.dept)
    if (!codes.length && names.length) return names.map((dept) => ({ dept, deptCode: '' }))
    return codes.map((deptCode, index) => ({ deptCode, dept: names[index] || deptCode }))
  }

  async function loadDepartments() {
    return departments.value
  }

  async function resolveIdentity() {
    if (resolvePromise) return resolvePromise
    resolvePromise = doResolveIdentity().finally(() => {
      resolvePromise = null
    })
    return resolvePromise
  }

  async function doResolveIdentity() {
    auth.hydrateFromQuery(route.query)
    resolvingIdentity.value = true
    try {
      const userName = String(auth.effectiveUserId || route.query.userName || route.query.user_id || '').trim()
      const deptCode = String(route.query.deptCode || route.query.dept_code || auth.deptCode || '').trim()
      const dept = String(route.query.dept || route.query.department || auth.dept || '').trim()
      if (userName) {
        const { data } = await getClinicalAccount({
          userName,
          role: String(route.query.role || auth.role || '').trim() || undefined,
          dept_code: deptCode || undefined,
          dept: dept || undefined,
        })
        if (data?.account) {
          const accountDepartments = departmentsFromAccount(data.account)
          departments.value = accountDepartments
          const firstDept = accountDepartments[0]
          auth.updateAccount({
            ...data.account,
            dept: String(firstDept?.dept || data.account.dept || '').trim(),
            dept_code: String(firstDept?.deptCode || firstDept?.code || data.account.dept_code || '').trim(),
          })
        }
      }
      const rows = departments.value
      const nextCode = String(route.query.deptCode || route.query.dept_code || auth.deptCode || '').trim()
      if (nextCode && !auth.dept) {
        const hit = rows.find((item: any) => String(item?.deptCode || item?.code || '').trim() === nextCode)
        if (hit?.dept) auth.updateAccount({ dept: hit.dept, dept_code: nextCode })
      }
      if (route.query.dept || route.query.department || route.query.dept_code || route.query.deptCode || route.query.role || route.query.user_id) {
        router.replace({ path: route.path, query: publicIdentityQuery() })
      }
    } finally {
      resolvingIdentity.value = false
    }
  }

  onMounted(() => {
    shellMounted += 1
    void resolveIdentity()
    syncViewport()
    if (shellMounted === 1) window.addEventListener('resize', syncViewport, { passive: true })
  })

  onUnmounted(() => {
    shellMounted = Math.max(0, shellMounted - 1)
    if (!shellMounted) window.removeEventListener('resize', syncViewport)
  })

  const role = computed(() => normalizeMobileRole(auth.role || route.query.role))
  const isCompact = computed(() => width.value < 420)
  const actor = computed(() => String(auth.effectiveUserId || '').trim() || 'mobile_h5')
  watch(() => [route.query.userName, route.query.user_id, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department, route.query.role], () => {
    void resolveIdentity()
  })

  const deptLabel = computed(() => {
    const dept = String(auth.dept || route.query.dept || route.query.department || '').trim()
    if (dept) return dept
    const code = String(auth.deptCode || route.query.dept_code || route.query.deptCode || '').trim()
    if (code) {
      const hit = departments.value.find((item: any) => String(item?.deptCode || item?.code || '').trim() === code)
      if (hit?.dept) return String(hit.dept).trim()
    }
    return '全院'
  })
  const deptCode = computed(() => String(auth.deptCode || route.query.dept_code || route.query.deptCode || '').trim())

  function identityQuery(extra?: Record<string, any>) {
    return auth.cleanIdentityQuery({
      userName: auth.userName || auth.effectiveUserId || route.query.userName || undefined,
      ...(extra || {}),
    } as any)
  }

  function publicIdentityQuery(extra?: Record<string, any>) {
    return identityQuery(extra)
  }

  function scopedQuery(extra?: Record<string, any>) {
    const next = auth.cleanIdentityQuery({
      user_id: auth.effectiveUserId || undefined,
      role: auth.role || undefined,
      dept: auth.dept || undefined,
      dept_code: auth.deptCode || undefined,
      ...route.query,
      ...(extra || {}),
    } as any)
    for (const key of ['dept', 'dept_code', 'deptCode', 'role', 'user_id']) {
      if (next[key] == null || next[key] === '') delete next[key]
    }
    if (next.deptCode && !next.dept_code) {
      next.dept_code = next.deptCode
      delete next.deptCode
    }
    return next
  }

  function setDepartment(row: any) {
    const dept = String(row?.dept || row?.name || '').trim()
    const code = String(row?.deptCode || row?.code || '').trim()
    auth.updateAccount({ dept, dept_code: code })
    return publicIdentityQuery()
  }

  function clearDepartment() {
    auth.updateAccount({ dept: '', dept_code: '' })
    return publicIdentityQuery()
  }

  return { width, height, container, role, isCompact, actor, deptLabel, deptCode, departments, resolvingIdentity, resolveIdentity, loadDepartments, setDepartment, clearDepartment, identityQuery, scopedQuery }
}
