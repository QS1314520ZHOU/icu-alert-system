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

  function hydrateFromQuery(query: LocationQuery) {
    const nextUserId = firstQuery(query, ['user_id', 'userId'])
    const nextUserName = firstQuery(query, ['userName', 'useName', 'username'])
    const nextRole = firstQuery(query, ['role'])
    const nextDept = firstQuery(query, ['dept'])
    const nextDeptCode = firstQuery(query, ['dept_code', 'deptCode'])
    if (nextUserId) userId.value = nextUserId
    if (nextUserName) userName.value = nextUserName
    if (!nextUserId && nextUserName) userId.value = nextUserName
    if (nextRole) role.value = nextRole
    if (nextDept) dept.value = nextDept
    if (nextDeptCode) deptCode.value = nextDeptCode
    persist()
  }

  function updateAccount(account: any) {
    if (!account || typeof account !== 'object') return
    userId.value = String(account.user_id || account.userId || userId.value || '').trim()
    userName.value = String(account.userName || account.username || userName.value || '').trim()
    role.value = String(account.role || role.value || '').trim()
    dept.value = String(account.dept || dept.value || '').trim()
    deptCode.value = String(account.dept_code || account.deptCode || deptCode.value || '').trim()
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

  return { userId, userName, role, dept, deptCode, effectiveUserId, hydrateFromQuery, updateAccount, cleanIdentityQuery }
})
