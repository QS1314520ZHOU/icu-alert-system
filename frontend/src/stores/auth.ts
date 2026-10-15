/**
 * 认证状态管理
 *
 * 整合 iframe 宿主认证与本地认证。
 * 优先使用宿主 Token，本地认证作为开发/测试回退。
 *
 * 401 行为：
 * - 立即清除认证状态
 * - 通知所有标签页退出
 * - 显示明确提示
 * - 不触发 401 循环
 *
 * 403 行为：
 * - 不清除有效登录状态
 * - 仅显示"无权访问"提示
 */

import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { LocationQuery } from 'vue-router'
import {
  initIframeAuth,
  useIframeAuth,
  getAccessToken,
  isAuthenticated as isIframeAuthenticated,
  type IframeAuthStatus,
} from '../auth/iframeAuth'
import { getOperatorIdentity, setOperatorIdentity } from '../utils/operatorIdentity'
import { usePatientContext } from './patientContext'
import { onAuthEvent, resetRefreshState, type AuthEvent } from '../api/http'

const AUTH_KEY = 'icu_auth_identity'
const LOGOUT_BROADCAST_KEY = 'icu_logout_broadcast'

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

  // iframe 认证状态
  const iframeAuthStatus = ref<IframeAuthStatus>('initializing')
  const iframeAuthError = ref<string | null>(null)
  const iframeInitialized = ref(false)

  // 401/403 通知状态（供 UI 层读取）
  const authNotification = ref<{ type: '401' | '403' | 'network_error'; message: string } | null>(null)

  const effectiveUserId = computed(() => userId.value || userName.value || getOperatorIdentity())

  const isAuthenticated = computed(() => {
    if (iframeInitialized.value) {
      return isIframeAuthenticated()
    }
    return !!userId.value || !!userName.value
  })

  const accessToken = computed(() => {
    if (iframeInitialized.value) {
      return getAccessToken()
    }
    try {
      return localStorage.getItem('icu_jwt_access_token') || ''
    } catch {
      return ''
    }
  })

  function persist() {
    writeStored({ userId: userId.value, userName: userName.value, role: role.value, dept: dept.value, deptCode: deptCode.value })
    if (userId.value || userName.value) setOperatorIdentity(userId.value || userName.value)
  }

  /**
   * 处理 401：清除认证状态，通知用户，广播给其他标签页。
   */
  function handle401(): void {
    // 避免重复处理
    if (!isAuthenticated.value && !userId.value) return

    authNotification.value = { type: '401', message: '登录状态已失效，请重新登录' }

    // 清除认证状态
    userId.value = ''
    userName.value = ''
    role.value = ''
    dept.value = ''
    deptCode.value = ''
    persist()
    setOperatorIdentity('')
    clearSensitiveData()

    // 重置 HTTP 客户端的刷新状态
    resetRefreshState()

    // 广播给其他标签页
    _broadcastLogout('401')
  }

  /**
   * 处理 403：不清除登录状态，仅通知。
   */
  function handle403(): void {
    authNotification.value = { type: '403', message: '无权访问该资源' }
  }

  /**
   * 处理网络错误：不清除登录状态，仅通知。
   */
  function handleNetworkError(): void {
    authNotification.value = { type: 'network_error', message: '网络连接失败，请检查网络后重试' }
  }

  /**
   * 清除通知。
   */
  function clearNotification(): void {
    authNotification.value = null
  }

  /**
   * 初始化 iframe 认证。
   */
  async function initAuth(): Promise<void> {
    // 订阅 HTTP 层的认证事件
    onAuthEvent((event: AuthEvent) => {
      switch (event.type) {
        case '401': handle401(); break
        case '403': handle403(); break
        case 'network_error': handleNetworkError(); break
      }
    })

    // 监听跨标签页退出
    _listenCrossTabLogout()

    try {
      const state = await initIframeAuth()
      iframeInitialized.value = true
      iframeAuthStatus.value = state.status
      iframeAuthError.value = state.error

      if (state.status === 'authenticated') {
        if (state.userId) userId.value = state.userId
        if (state.userName) userName.value = state.userName
        if (state.role) role.value = state.role
        if (state.dept) dept.value = state.dept
        persist()
      }

      const iframeAuth = useIframeAuth()
      watch(iframeAuth, (newState) => {
        iframeAuthStatus.value = newState.status
        iframeAuthError.value = newState.error

        if (newState.status === 'authenticated') {
          if (newState.userId) userId.value = newState.userId
          if (newState.userName) userName.value = newState.userName
          if (newState.role) role.value = newState.role
          if (newState.dept) dept.value = newState.dept
          persist()
        }

        if (newState.status === 'unauthorized' || newState.status === 'expired') {
          handle401()
        }
      })
    } catch (err) {
      console.warn('[AuthStore] Iframe auth init failed, falling back to local auth:', err)
      iframeAuthStatus.value = 'error'
    }
  }

  function clearSensitiveData(): void {
    try {
      usePatientContext().clearAllSessionData()
    } catch {
      try {
        for (let i = sessionStorage.length - 1; i >= 0; i--) {
          const key = sessionStorage.key(i)
          if (key && key.startsWith('icu_active_patient_id')) {
            sessionStorage.removeItem(key)
          }
        }
      } catch {}
    }
  }

  // ── 跨标签页退出 ────────────────────────────────

  let _logoutChannel: BroadcastChannel | null = null

  function _broadcastLogout(reason: string): void {
    try {
      if (typeof BroadcastChannel !== 'undefined') {
        if (!_logoutChannel) _logoutChannel = new BroadcastChannel(LOGOUT_BROADCAST_KEY)
        _logoutChannel.postMessage({ type: 'logout', reason, timestamp: Date.now() })
      }
      // 同时用 localStorage 事件作为降级（BroadcastChannel 不可用时）
      localStorage.setItem(LOGOUT_BROADCAST_KEY, JSON.stringify({ type: 'logout', reason, timestamp: Date.now() }))
    } catch {}
  }

  function _listenCrossTabLogout(): void {
    try {
      if (typeof BroadcastChannel !== 'undefined') {
        if (!_logoutChannel) _logoutChannel = new BroadcastChannel(LOGOUT_BROADCAST_KEY)
        _logoutChannel.onmessage = (event) => {
          if (event.data?.type === 'logout') {
            // 收到其他标签页的退出通知
            userId.value = ''
            userName.value = ''
            role.value = ''
            dept.value = ''
            deptCode.value = ''
            persist()
            setOperatorIdentity('')
            clearSensitiveData()
            authNotification.value = { type: '401', message: '您的账号已在其他标签页退出，请重新登录' }
          }
        }
      }
      // 降级：监听 localStorage 变化
      window.addEventListener('storage', (event) => {
        if (event.key === LOGOUT_BROADCAST_KEY && event.newValue) {
          try {
            const data = JSON.parse(event.newValue)
            if (data?.type === 'logout') {
              userId.value = ''
              userName.value = ''
              role.value = ''
              dept.value = ''
              deptCode.value = ''
              persist()
              setOperatorIdentity('')
              clearSensitiveData()
              authNotification.value = { type: '401', message: '您的账号已在其他标签页退出，请重新登录' }
            }
          } catch {}
        }
      })
    } catch {}
  }

  // ── URL 参数同步 ────────────────────────────────

  function hydrateFromQuery(query: LocationQuery) {
    const nextUserId = firstQuery(query, ['user_id', 'userId'])
    const nextUserName = firstQuery(query, ['userName', 'useName', 'username'])
    const nextRole = firstQuery(query, ['role'])
    const nextDept = firstQuery(query, ['dept'])
    const nextDeptCode = firstQuery(query, ['dept_code', 'deptCode'])

    if (!userId.value && !userName.value) {
      if (nextUserId) userId.value = nextUserId
      if (nextUserName) userName.value = nextUserName
      if (!nextUserId && nextUserName) userId.value = nextUserName
    }

    if (nextRole) role.value = nextRole
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
    if (next.user_id) delete next.userId
    if (next.userName) delete next.useName
    if (next.userName) delete next.username
    return next
  }

  /**
   * 登出：清除所有身份信息和患者上下文，广播给其他标签页。
   */
  function logout() {
    userId.value = ''
    userName.value = ''
    role.value = ''
    dept.value = ''
    deptCode.value = ''
    persist()
    setOperatorIdentity('')
    clearSensitiveData()
    resetRefreshState()
    _broadcastLogout('manual')
  }

  function switchDepartment(newDept: string, newDeptCode: string) {
    dept.value = newDept
    deptCode.value = newDeptCode
    persist()
    clearSensitiveData()
  }

  function switchUser(newUserId: string, newUserName: string, newRole?: string) {
    userId.value = newUserId
    userName.value = newUserName
    if (newRole) role.value = newRole
    dept.value = ''
    deptCode.value = ''
    persist()
    setOperatorIdentity(newUserId || newUserName)
    clearSensitiveData()
  }

  return {
    userId,
    userName,
    role,
    dept,
    deptCode,
    effectiveUserId,
    isAuthenticated,
    accessToken,
    iframeAuthStatus,
    iframeAuthError,
    iframeInitialized,
    authNotification,
    initAuth,
    hydrateFromQuery,
    updateAccount,
    cleanIdentityQuery,
    logout,
    switchDepartment,
    switchUser,
    handle401,
    handle403,
    clearNotification,
  }
})
