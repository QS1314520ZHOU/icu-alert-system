import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { LocationQuery } from 'vue-router'
import { getOperatorIdentity, setOperatorIdentity } from '../utils/operatorIdentity'

const AUTH_KEY = 'icu_auth_identity'

export type AuthIdentity = {
  userId: string
  userName: string
  role: string
  dept: string
  deptCode: string
}

function readStored(): Partial<AuthIdentity> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(AUTH_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function writeStored(value: AuthIdentity) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(AUTH_KEY, JSON.stringify(value))
}

function firstQuery(query: LocationQuery, keys: string[]) {
  for (const key of keys) {
    const raw = query[key]
    const value = Array.isArray(raw) ? raw[0] : raw
    const text = String(value || '').trim()
    if (text) return text
  }
  return ''
}

export const useAuthStore = defineStore('auth', () => {
  const stored = readStored()
  const userId = ref(String(stored.userId || getOperatorIdentity() || '').trim())
  const userName = ref(String(stored.userName || '').trim())
  const role = ref(String(stored.role || '').trim())
  const dept = ref(String(stored.dept || '').trim())
  const deptCode = ref(String(stored.deptCode || '').trim())

  const effectiveUserId = computed(() => userId.value || userName.value || getOperatorIdentity())

  function persist() {
    writeStored({ userId: userId.value, userName: userName.value, role: role.value, dept: dept.value, deptCode: deptCode.value })
    if (userId.value || userName.value) setOperatorIdentity(userId.value || userName.value)
  }

  /**
   * Sync identity from route query parameters.
   *
   * Rules:
   * - Identity (userId, userName) from URL is used as FALLBACK only —
   *   if we already have a session identity, URL params don't overwrite it.
   * - dept_code from URL is accepted if present, but NEVER cleared if absent.
   * - role from URL is accepted if present, but NEVER cleared if absent.
   * - URL params are for legacy system compatibility, not as auth source.
   */
  function hydrateFromQuery(query: LocationQuery) {
    const nextUserId = firstQuery(query, ['user_id', 'userId'])
    const nextUserName = firstQuery(query, ['userName', 'useName', 'username'])
    const nextRole = firstQuery(query, ['role'])
    const nextDept = firstQuery(query, ['dept'])
    const nextDeptCode = firstQuery(query, ['dept_code', 'deptCode'])

    // Identity: only set from URL if no session identity exists
    if (!userId.value && !userName.value) {
      if (nextUserId) userId.value = nextUserId
      if (nextUserName) userName.value = nextUserName
      if (!nextUserId && nextUserName) userId.value = nextUserName
    }

    // Role: accept from URL if present, don't clear if absent
    if (nextRole) role.value = nextRole

    // Department: accept from URL if present, NEVER clear if absent
    if (nextDept) dept.value = nextDept
    if (nextDeptCode) deptCode.value = nextDeptCode

    persist()
  }

  function updateAccount(account: any) {
    if (!account || typeof account !== 'object') return
    const has = (key: string) => Object.prototype.hasOwnProperty.call(account, key)
    userId.value = String(account.user_id || account.userId || userId.value || '').trim()
    userName.value = String(account.userName || account.username || userName.value || '').trim()
    role.value = String(account.role || role.value || '').trim()
    if (has('dept')) dept.value = String(account.dept || '').trim()
    if (has('dept_code') || has('deptCode')) deptCode.value = String(account.dept_code || account.deptCode || '').trim()
    persist()
  }

  function cleanIdentityQuery(query: LocationQuery) {
    const next: Record<string, any> = { ...query }
    // 保留地址栏身份参数，供跨页面导航和刷新后快速识别当前账号。
    // 仅去掉兼容旧拼写产生的重复项，避免首页进入临床工作台时 userName 丢失。
    if (next.user_id) delete next.userId
    if (next.userName) delete next.useName
    if (next.userName) delete next.username
    return next
  }

  /**
   * 登出：清除所有身份信息和患者上下文。
   */
  function logout() {
    userId.value = ''
    userName.value = ''
    role.value = ''
    dept.value = ''
    deptCode.value = ''
    persist()
    setOperatorIdentity('')
    // 清除患者上下文 sessionStorage
    try { sessionStorage.removeItem('icu_active_patient_id') } catch {}
  }

  /**
   * 切换科室：更新 dept/deptCode 并清除患者上下文（避免跨科室数据泄漏）。
   */
  function switchDepartment(newDept: string, newDeptCode: string) {
    dept.value = newDept
    deptCode.value = newDeptCode
    persist()
    // 科室切换后清除患者上下文
    try { sessionStorage.removeItem('icu_active_patient_id') } catch {}
  }

  /**
   * 切换用户：清除旧身份，设置新身份，清除患者上下文。
   */
  function switchUser(newUserId: string, newUserName: string, newRole?: string) {
    userId.value = newUserId
    userName.value = newUserName
    if (newRole) role.value = newRole
    dept.value = ''
    deptCode.value = ''
    persist()
    setOperatorIdentity(newUserId || newUserName)
    // 用户切换后清除患者上下文
    try { sessionStorage.removeItem('icu_active_patient_id') } catch {}
  }

  return { userId, userName, role, dept, deptCode, effectiveUserId, hydrateFromQuery, updateAccount, cleanIdentityQuery, logout, switchDepartment, switchUser }
})
