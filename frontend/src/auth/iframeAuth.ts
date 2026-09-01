/**
 * iframe 宿主认证模块
 *
 * 复用项目现有 postMessage 握手机制，在此基础上增加：
 * - 认证令牌请求与验证
 * - 一次性授权码交换
 * - Token 生命周期管理
 * - 宿主退出/切换用户处理
 */

import { ref, readonly, type Ref } from 'vue'
import {
  createEmbedMessage,
  isHostMessage,
  isDuplicateRequestId,
  type HostMessage,
} from '../config/postMessageProtocol'

// ── 类型定义 ──────────────────────────────────────

export type IframeAuthStatus =
  | 'initializing'
  | 'requesting'
  | 'authenticated'
  | 'refreshing'
  | 'expired'
  | 'unauthorized'
  | 'host_unavailable'
  | 'error'

export interface HostAuthPayload {
  /** 宿主签发的访问令牌 */
  accessToken?: string
  /** 一次性授权码（用于向 ICU 后端交换 Token） */
  authorizationCode?: string
  /** 令牌过期时间（ISO 8601） */
  expiresAt?: string
  /** 宿主返回的请求 ID（用于关联请求-响应） */
  requestId?: string
  /** 一次性随机数（防重放） */
  nonce?: string
  /** 用户展示信息（仅用于界面显示，不作为认证依据） */
  userDisplay?: {
    userName?: string
    departmentName?: string
    userId?: string
    role?: string
  }
}

export interface IframeAuthState {
  status: IframeAuthStatus
  accessToken: string
  userId: string
  userName: string
  role: string
  dept: string
  deptCode: string
  expiresAt: number | null
  error: string | null
  requestId: string | null
  nonce: string | null
}

// ── 常量 ──────────────────────────────────────────

const AUTH_REQUEST_TYPE = 'ICU_IFRAME_AUTH_REQUEST'
const AUTH_RESPONSE_TYPE = 'ICU_IFRAME_AUTH_RESPONSE'
const HOST_LOGOUT_TYPE = 'ICU_HOST_LOGOUT'
const HOST_USER_CHANGED_TYPE = 'ICU_HOST_USER_CHANGED'
const HOST_TOKEN_REFRESHED_TYPE = 'ICU_HOST_TOKEN_REFRESHED'

const MAX_TIMESTAMP_DRIFT = 5 * 60 * 1000 // 5 minutes
const TOKEN_REFRESH_BUFFER = 60 * 1000 // 1 minute before expiry
const AUTH_REQUEST_TIMEOUT = 10 * 1000 // 10 seconds

// ── 全局状态 ──────────────────────────────────────

const authState: Ref<IframeAuthState> = ref({
  status: 'initializing',
  accessToken: '',
  userId: '',
  userName: '',
  role: '',
  dept: '',
  deptCode: '',
  expiresAt: null,
  error: null,
  requestId: null,
  nonce: null,
})

let messageHandler: ((event: MessageEvent) => void) | null = null
let refreshTimer: ReturnType<typeof setTimeout> | null = null
let authRequestTimer: ReturnType<typeof setTimeout> | null = null
let pendingResolve: ((value: HostAuthPayload | null) => void) | null = null

// ── 工具函数 ──────────────────────────────────────

function generateId(): string {
  return crypto.randomUUID?.() ?? Math.random().toString(36).slice(2) + Date.now().toString(36)
}

function isIframe(): boolean {
  try {
    return window.self !== window.top
  } catch {
    return true
  }
}

function getAllowedOrigins(): string[] {
  const env = import.meta.env.VITE_HOST_ORIGINS || ''
  if (env) {
    return env.split(',').map((s: string) => s.trim()).filter(Boolean)
  }
  // 开发模式允许所有 origin
  if (import.meta.env.DEV) return ['*']
  return []
}

function validateOrigin(origin: string): boolean {
  const allowed = getAllowedOrigins()
  if (allowed.includes('*')) return true
  return allowed.includes(origin)
}

// ── 核心认证逻辑 ──────────────────────────────────

/**
 * 向宿主发送认证请求并等待响应。
 */
function requestAuthFromHost(targetOrigin: string): Promise<HostAuthPayload | null> {
  return new Promise((resolve) => {
    if (!isIframe()) {
      // 非 iframe 环境，尝试使用本地开发模式
      if (import.meta.env.DEV) {
        console.warn('[IframeAuth] Not in iframe, using dev mode')
        resolve(null)
        return
      }
      resolve(null)
      return
    }

    const requestId = generateId()
    const nonce = generateId()
    const timestamp = Date.now()

    authState.value.requestId = requestId
    authState.value.nonce = nonce
    authState.value.status = 'requesting'

    pendingResolve = resolve

    // 发送认证请求
    const message = createEmbedMessage(AUTH_REQUEST_TYPE as any, {
      requestId,
      nonce,
      timestamp,
    })

    try {
      window.parent.postMessage(message, targetOrigin)
    } catch (err) {
      console.error('[IframeAuth] Failed to send auth request:', err)
      authState.value.status = 'error'
      authState.value.error = '无法向宿主系统发送认证请求'
      resolve(null)
      return
    }

    // 超时处理
    authRequestTimer = setTimeout(() => {
      if (pendingResolve === resolve) {
        console.warn('[IframeAuth] Auth request timed out')
        authState.value.status = 'host_unavailable'
        authState.value.error = '宿主系统未响应认证请求'
        pendingResolve = null
        resolve(null)
      }
    }, AUTH_REQUEST_TIMEOUT)
  })
}

/**
 * 处理宿主返回的认证响应。
 */
function handleAuthResponse(data: HostMessage<HostAuthPayload>): void {
  // 验证 requestId
  if (data.payload?.requestId && data.payload.requestId !== authState.value.requestId) {
    console.warn('[IframeAuth] RequestId mismatch')
    return
  }

  // 验证 nonce
  if (data.payload?.nonce && data.payload.nonce !== authState.value.nonce) {
    console.warn('[IframeAuth] Nonce mismatch')
    return
  }

  // 验证时间戳
  if (data.timestamp) {
    const drift = Math.abs(Date.now() - data.timestamp)
    if (drift > MAX_TIMESTAMP_DRIFT) {
      console.warn('[IframeAuth] Timestamp drift too large:', drift)
      return
    }
  }

  const payload = data.payload

  if (payload?.accessToken) {
    authState.value.accessToken = payload.accessToken
    authState.value.status = 'authenticated'

    // 解析用户信息
    if (payload.userDisplay) {
      authState.value.userId = payload.userDisplay.userId || ''
      authState.value.userName = payload.userDisplay.userName || ''
      authState.value.role = payload.userDisplay.role || ''
    }

    // 解析过期时间
    if (payload.expiresAt) {
      authState.value.expiresAt = new Date(payload.expiresAt).getTime()
      scheduleTokenRefresh()
    }
  } else if (payload?.authorizationCode) {
    // 需要向 ICU 后端交换 Token
    exchangeAuthorizationCode(payload.authorizationCode, payload)
  } else {
    authState.value.status = 'unauthorized'
    authState.value.error = '宿主未提供有效的认证凭证'
  }

  // 清除超时定时器
  if (authRequestTimer) {
    clearTimeout(authRequestTimer)
    authRequestTimer = null
  }

  // 解析用户展示信息
  if (payload?.userDisplay) {
    authState.value.userName = payload.userDisplay.userName || authState.value.userName
    authState.value.dept = payload.userDisplay.departmentName || authState.value.dept
  }

  // resolve pending promise
  if (pendingResolve) {
    const resolve = pendingResolve
    pendingResolve = null
    resolve(payload || null)
  }
}

/**
 * 向 ICU 后端交换一次性授权码为访问令牌。
 */
async function exchangeAuthorizationCode(
  code: string,
  payload: HostAuthPayload
): Promise<void> {
  try {
    const response = await fetch('/api/auth/iframe/exchange', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        authorization_code: code,
        nonce: authState.value.nonce,
      }),
    })

    if (!response.ok) {
      throw new Error(`Exchange failed: ${response.status}`)
    }

    const data = await response.json()
    authState.value.accessToken = data.access_token || ''
    authState.value.status = 'authenticated'
    authState.value.userId = data.user_id || payload.userDisplay?.userId || ''
    authState.value.userName = data.user_name || payload.userDisplay?.userName || ''
    authState.value.role = data.role || payload.userDisplay?.role || ''

    if (data.expires_at) {
      authState.value.expiresAt = new Date(data.expires_at).getTime()
      scheduleTokenRefresh()
    }
  } catch (err) {
    console.error('[IframeAuth] Authorization code exchange failed:', err)
    authState.value.status = 'error'
    authState.value.error = '授权码交换失败'
  }
}

/**
 * 安排 Token 刷新。
 */
function scheduleTokenRefresh(): void {
  if (refreshTimer) {
    clearTimeout(refreshTimer)
  }

  if (!authState.value.expiresAt) return

  const now = Date.now()
  const refreshAt = authState.value.expiresAt - TOKEN_REFRESH_BUFFER

  if (refreshAt <= now) {
    // Token 已过期或即将过期
    refreshToken()
    return
  }

  refreshTimer = setTimeout(() => {
    refreshToken()
  }, refreshAt - now)
}

/**
 * 刷新 Token。
 *
 * 在 iframe 模式下，向宿主请求新 Token 并等待响应。
 * 返回新 Token 或抛出异常。
 */
export async function refreshToken(): Promise<string> {
  if (authState.value.status === 'refreshing') {
    // 等待当前刷新完成
    return new Promise((resolve, reject) => {
      const check = setInterval(() => {
        if (authState.value.status !== 'refreshing') {
          clearInterval(check)
          if (authState.value.accessToken) {
            resolve(authState.value.accessToken)
          } else {
            reject(new Error('Token refresh failed'))
          }
        }
      }, 100)
      // 超时
      setTimeout(() => {
        clearInterval(check)
        reject(new Error('Token refresh timeout'))
      }, AUTH_REQUEST_TIMEOUT)
    })
  }

  authState.value.status = 'refreshing'

  try {
    if (isIframe()) {
      // 向宿主请求新 Token 并等待响应
      return new Promise((resolve, reject) => {
        const requestId = generateId()
        const nonce = generateId()

        const timeout = setTimeout(() => {
          authState.value.status = 'expired'
          authState.value.error = 'Token 刷新超时'
          pendingResolve = null
          reject(new Error('Token refresh timeout'))
        }, AUTH_REQUEST_TIMEOUT)

        pendingResolve = (payload: HostAuthPayload | null) => {
          clearTimeout(timeout)
          pendingResolve = null

          if (payload?.accessToken) {
            authState.value.accessToken = payload.accessToken
            authState.value.status = 'authenticated'
            if (payload.expiresAt) {
              authState.value.expiresAt = new Date(payload.expiresAt).getTime()
              scheduleTokenRefresh()
            }
            resolve(payload.accessToken)
          } else if (payload?.authorizationCode) {
            exchangeAuthorizationCode(payload.authorizationCode, payload)
              .then(() => resolve(authState.value.accessToken))
              .catch(reject)
          } else {
            authState.value.status = 'expired'
            authState.value.error = '宿主未提供新的Token'
            reject(new Error('No token from host'))
          }
        }

        const targetOrigin = getAllowedOrigins()[0] || '*'
        const message = createEmbedMessage(AUTH_REQUEST_TYPE as any, {
          requestId,
          nonce,
          timestamp: Date.now(),
          action: 'refresh',
        })

        authState.value.requestId = requestId
        authState.value.nonce = nonce

        try {
          window.parent.postMessage(message, targetOrigin)
        } catch (err) {
          clearTimeout(timeout)
          pendingResolve = null
          authState.value.status = 'expired'
          reject(err)
        }
      })
    } else {
      // 非 iframe 环境，尝试使用 refresh token
      const rt = localStorage.getItem('icu_jwt_refresh_token')
      if (rt) {
        const response = await fetch('/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
        })

        if (response.ok) {
          const data = await response.json()
          authState.value.accessToken = data.access_token
          authState.value.status = 'authenticated'
          if (data.expires_at) {
            authState.value.expiresAt = new Date(data.expires_at).getTime()
            scheduleTokenRefresh()
          }
          return data.access_token
        }
      }
      authState.value.status = 'expired'
      authState.value.error = 'Token 已过期，请重新认证'
      throw new Error('Token expired')
    }
  } catch (err) {
    console.error('[IframeAuth] Token refresh failed:', err)
    authState.value.status = 'expired'
    authState.value.error = 'Token 刷新失败'
    throw err
  }
}

// ── 消息监听 ──────────────────────────────────────

function handleMessage(event: MessageEvent): void {
  // 验证 origin
  if (!validateOrigin(event.origin)) {
    return
  }

  const data = event.data
  if (!isHostMessage(data)) return

  // 验证 source
  if (isIframe() && event.source !== window.parent) return

  // 去重
  if (isDuplicateRequestId(data.requestId)) return

  switch (data.type as string) {
    case AUTH_RESPONSE_TYPE:
      handleAuthResponse(data as HostMessage<HostAuthPayload>)
      break

    case HOST_LOGOUT_TYPE:
      handleHostLogout()
      break

    case HOST_USER_CHANGED_TYPE:
      handleHostUserChanged(data.payload)
      break

    case HOST_TOKEN_REFRESHED_TYPE:
      if (data.payload?.accessToken) {
        authState.value.accessToken = data.payload.accessToken
        authState.value.status = 'authenticated'
        if (data.payload.expiresAt) {
          authState.value.expiresAt = new Date(data.payload.expiresAt).getTime()
          scheduleTokenRefresh()
        }
      }
      break
  }
}

/**
 * 处理宿主退出。
 */
function handleHostLogout(): void {
  clearAuthState()
  authState.value.status = 'unauthorized'
  authState.value.error = '宿主用户已退出'
}

/**
 * 处理宿主切换用户。
 */
function handleHostUserChanged(_payload: any): void {
  clearAuthState()
  authState.value.status = 'initializing'
  // 重新请求认证
  const targetOrigin = getAllowedOrigins()[0] || '*'
  requestAuthFromHost(targetOrigin)
}

/**
 * 清除认证状态。
 */
function clearAuthState(): void {
  authState.value.accessToken = ''
  authState.value.userId = ''
  authState.value.userName = ''
  authState.value.role = ''
  authState.value.dept = ''
  authState.value.deptCode = ''
  authState.value.expiresAt = null
  authState.value.error = null

  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
}

// ── 公开 API ──────────────────────────────────────

/**
 * 初始化 iframe 认证。
 * 应在应用启动时调用。
 */
export async function initIframeAuth(targetOrigin?: string): Promise<IframeAuthState> {
  const origin = targetOrigin || getAllowedOrigins()[0] || '*'

  // 注册消息监听
  if (!messageHandler) {
    messageHandler = handleMessage
    window.addEventListener('message', messageHandler)
  }

  // 请求认证
  await requestAuthFromHost(origin)

  return authState.value
}

/**
 * 获取当前认证状态（只读）。
 */
export function useIframeAuth(): Readonly<Ref<IframeAuthState>> {
  return readonly(authState)
}

/**
 * 获取当前访问令牌。
 */
export function getAccessToken(): string {
  return authState.value.accessToken
}

/**
 * 检查是否已认证。
 */
export function isAuthenticated(): boolean {
  return authState.value.status === 'authenticated' && !!authState.value.accessToken
}

/**
 * 清理认证模块。
 */
export function destroyIframeAuth(): void {
  if (messageHandler) {
    window.removeEventListener('message', messageHandler)
    messageHandler = null
  }
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
  if (authRequestTimer) {
    clearTimeout(authRequestTimer)
    authRequestTimer = null
  }
  clearAuthState()
}

export default {
  initIframeAuth,
  useIframeAuth,
  getAccessToken,
  isAuthenticated,
  destroyIframeAuth,
}
