/**
 * 统一 HTTP 客户端
 *
 * 全项目使用统一 HTTP 客户端，Token 由 auth store 统一管理。
 * 不让各业务组件分别管理 Token。
 *
 * 401 行为规范：
 * 1. 收到 401 → 立即结束 loading，中止关联请求
 * 2. 同一时间多个 401 只处理一次
 * 3. 不对 401 自动无限重试
 * 4. 刷新成功后每个原请求最多重放一次
 * 5. 刷新失败立即进入退出登录流程
 * 6. 网络断开、超时、DNS、5xx 不得误判为 401
 */

import axios, { type AxiosInstance, type InternalAxiosRequestConfig, type AxiosError } from 'axios'

// ── Token Provider（避免循环依赖） ────────────────

export interface TokenProvider {
  getAccessToken(): string
}

let _tokenProvider: TokenProvider | null = null

export function setTokenProvider(provider: TokenProvider): void {
  _tokenProvider = provider
}

function getAccessToken(): string {
  if (_tokenProvider) {
    try {
      const token = _tokenProvider.getAccessToken()
      if (token) return token
    } catch {}
  }
  try {
    return localStorage.getItem('icu_jwt_access_token') || ''
  } catch {
    return ''
  }
}

// ── 401 事件系统 ──────────────────────────────────

export type AuthEventType = '401' | '403' | 'network_error'

export interface AuthEvent {
  type: AuthEventType
  message: string
  requestId?: string
  status?: number
}

type AuthEventListener = (event: AuthEvent) => void

const _authListeners = new Set<AuthEventListener>()

/**
 * 订阅认证事件（auth store、路由守卫、UI 组件均可订阅）。
 * 返回取消订阅函数。
 */
export function onAuthEvent(listener: AuthEventListener): () => void {
  _authListeners.add(listener)
  return () => { _authListeners.delete(listener) }
}

function _emitAuthEvent(event: AuthEvent): void {
  _authListeners.forEach(fn => {
    try { fn(event) } catch {}
  })
}

// ── Axios 实例 ────────────────────────────────────

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 10000 })
const analyticsApi = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 30000 })
const researchApi = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 180000 })
const bundleApi = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 30000 })
const alertsApi = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 30000 })
export const aiApi = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '', timeout: 120000 })

const ALL_INSTANCES = [api, analyticsApi, researchApi, bundleApi, alertsApi, aiApi]

// ── 登录/刷新/退出路径，不触发 401 拦截 ────────

const _AUTH_BYPASS_PATHS = ['/api/auth/login', '/api/auth/refresh', '/api/auth/iframe/exchange']

function _isAuthBypass(config: InternalAxiosRequestConfig | undefined): boolean {
  if (!config?.url) return false
  return _AUTH_BYPASS_PATHS.some(p => config.url!.includes(p))
}

// ── 请求拦截器 ────────────────────────────────────

function installAuthInterceptor(instance: AxiosInstance) {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getAccessToken()
    if (token && !config.headers.has('Authorization')) {
      config.headers.set('Authorization', `Bearer ${token}`)
    }
    if (!config.headers.has('X-Request-ID')) {
      config.headers.set('X-Request-ID', crypto.randomUUID?.() ?? Math.random().toString(36).slice(2))
    }
    return config
  })
}

// ── 401 刷新锁 ────────────────────────────────────

type RefreshWaiter = {
  resolve: (token: string) => void
  reject: (error: Error) => void
}

let _isRefreshing = false
let _refreshWaiters: RefreshWaiter[] = []
let _refreshAttempted = false // 每轮只允许一次刷新

/**
 * 判断错误是否为真正的 401（排除网络错误、超时、DNS 故障）。
 */
function _isReal401(error: AxiosError): boolean {
  if (error.response?.status !== 401) return false
  // 有 HTTP 响应且状态码 401 → 真正的认证失败
  // 无响应（网络错误/超时）不是 401
  return true
}

/**
 * 判断是否为网络层错误（非服务器响应）。
 */
function _isNetworkError(error: AxiosError): boolean {
  return !error.response && (
    error.code === 'ERR_NETWORK' ||
    error.code === 'ECONNABORTED' ||
    error.code === 'ERR_CANCELED' ||
    error.message?.includes('Network Error') ||
    error.message?.includes('timeout')
  )
}

/**
 * 把技术错误改写为用户可读文案。
 * 页面只允许展示友好文案，不得出现 "Request failed with status code xxx" 之类的原始信息。
 * 原始错误仍可通过 console（_logOriginalError）与 error.response 排查。
 */
function _friendlyMessage(error: AxiosError): string {
  if (!error.response) {
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      return '请求超时，请稍后重试'
    }
    return '网络连接失败，请检查网络后重试'
  }
  const detail = (error.response.data as any)?.detail
  if (typeof detail === 'string' && detail.trim() && !/^\d{3}/.test(detail.trim())) {
    // 后端返回的中文业务提示优先展示（过滤掉以状态码开头的技术信息）
    return detail.trim()
  }
  switch (error.response.status) {
    case 400: return '请求参数有误，请检查后重试'
    case 401: return '登录状态已失效，请重新登录'
    case 403: return '暂无权限执行此操作'
    case 404: return '请求的内容不存在或服务未启动'
    case 408: return '请求超时，请稍后重试'
    case 409: return '操作冲突，请刷新后重试'
    case 422: return '提交的数据不符合要求'
    case 429: return '操作过于频繁，请稍后重试'
    default:
      if (error.response.status >= 500) return '服务暂时不可用，请稍后重试'
      return '请求失败，请稍后重试'
  }
}

/** 统一 reject 出口：改写 message 为友好文案，并保留原始错误供控制台排查。 */
function _rejectFriendly(error: AxiosError): Promise<never> {
  const original = error.message
  try {
    error.message = _friendlyMessage(error)
    if (original !== error.message) {
      console.warn(`[http] ${error.config?.method?.toUpperCase()} ${error.config?.url} -> ${error.response?.status ?? error.code}: ${original}`)
    }
  } catch { /* 不阻断拒绝流程 */ }
  return Promise.reject(error)
}

/**
 * 安装响应拦截器：统一处理 401/403/网络错误。
 */
function installAutoRetryInterceptor(instance: AxiosInstance) {
  instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const config = error?.config as any

      // ── 网络错误：不误判为 401 ──
      if (_isNetworkError(error)) {
        _emitAuthEvent({
          type: 'network_error',
          message: '网络连接失败，请检查网络后重试',
          requestId: config?.headers?.['X-Request-ID'],
        })
        return _rejectFriendly(error)
      }

      // ── 403：无权访问，不清除登录状态 ──
      if (error.response?.status === 403) {
        _emitAuthEvent({
          type: '403',
          message: '无权访问该资源',
          requestId: config?.headers?.['X-Request-ID'],
          status: 403,
        })
        return _rejectFriendly(error)
      }

      // ── 非 401 或已重试过：直接拒绝 ──
      if (!_isReal401(error) || config?._retried) {
        return _rejectFriendly(error)
      }

      // ── 登录/刷新/交换接口的 401 不拦截（避免循环） ──
      if (_isAuthBypass(config)) {
        return _rejectFriendly(error)
      }

      // ── 写请求不自动重试（避免重复提交） ──
      const method = (config?.method || '').toLowerCase()
      if (['post', 'put', 'patch', 'delete'].includes(method)) {
        _handle401Final(config)
        return _rejectFriendly(error)
      }

      // ── 标记已重试 ──
      config._retried = true

      // ── 正在刷新中：加入等待队列 ──
      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          _refreshWaiters.push({
            resolve: (token: string) => {
              if (!token) { reject(new Error('登录状态已失效，请重新登录')); return }
              config.headers['Authorization'] = `Bearer ${token}`
              resolve(instance.request(config))
            },
            reject: (err: Error) => reject(err),
          })
        })
      }

      // ── 发起刷新（每轮只允许一次） ──
      if (_refreshAttempted) {
        _handle401Final(config)
        return _rejectFriendly(error)
      }

      _isRefreshing = true
      _refreshAttempted = true

      try {
        const { refreshToken } = await import('../auth/iframeAuth')
        const newToken = await refreshToken()

        if (!newToken) {
          _rejectAllWaiters(new Error('登录状态已失效，请重新登录'))
          _handle401Final(config)
          throw new Error('登录状态已失效，请重新登录')
        }

        // 刷新成功：resolve 所有等待者并重放
        _refreshWaiters.forEach(w => w.resolve(newToken))
        _refreshWaiters = []
        config.headers['Authorization'] = `Bearer ${newToken}`
        return instance.request(config)
      } catch {
        _rejectAllWaiters(new Error('登录状态已失效，请重新登录'))
        _handle401Final(config)
        return _rejectFriendly(error)
      } finally {
        _isRefreshing = false
      }
    }
  )
}

/**
 * 刷新失败或无法刷新时：通知所有等待者并触发 401 事件。
 */
function _rejectAllWaiters(err: Error): void {
  _refreshWaiters.forEach(w => w.reject(err))
  _refreshWaiters = []
}

/**
 * 最终 401 处理：立即结束 loading，发出事件让 auth store 清理状态。
 */
function _handle401Final(config?: any): void {
  _emitAuthEvent({
    type: '401',
    message: '登录状态已失效，请重新登录',
    requestId: config?.headers?.['X-Request-ID'],
    status: 401,
  })
}

/**
 * 重置刷新状态（跨标签页退出或手动登出时调用）。
 */
export function resetRefreshState(): void {
  _isRefreshing = false
  _refreshAttempted = false
  _rejectAllWaiters(new Error('登录状态已更新，请重试'))
}

// ── 安装拦截器 ────────────────────────────────────

ALL_INSTANCES.forEach(installAuthInterceptor)
ALL_INSTANCES.forEach(installAutoRetryInterceptor)

export { api, analyticsApi, researchApi, bundleApi, alertsApi }
export default api
