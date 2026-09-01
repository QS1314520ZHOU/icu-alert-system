/**
 * 统一 HTTP 客户端
 *
 * 全项目使用统一 HTTP 客户端，Token 由 auth store 统一管理。
 * 不让各业务组件分别管理 Token。
 */

import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

// ── Token Provider（避免循环依赖） ────────────────

/**
 * Token 提供者接口。
 * 由 auth store 注入，避免循环依赖。
 */
export interface TokenProvider {
  getAccessToken(): string
}

let _tokenProvider: TokenProvider | null = null

/**
 * 注入 Token 提供者（由 auth store 调用）。
 */
export function setTokenProvider(provider: TokenProvider): void {
  _tokenProvider = provider
}

/**
 * 获取当前访问令牌。
 */
function getAccessToken(): string {
  // 优先使用注入的 provider
  if (_tokenProvider) {
    try {
      const token = _tokenProvider.getAccessToken()
      if (token) return token
    } catch {}
  }

  // 回退到 localStorage
  try {
    return localStorage.getItem('icu_jwt_access_token') || ''
  } catch {
    return ''
  }
}

// ── Axios 实例 ────────────────────────────────────

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 10000,
})

const analyticsApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

const researchApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 180000,
})

const bundleApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

const alertsApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

export const aiApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 120000,
})

// ── 请求拦截器 ────────────────────────────────────

/**
 * 统一添加 Authorization header 和 X-Request-ID。
 */
function installAuthInterceptor(instance: AxiosInstance) {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getAccessToken()
    if (token && !config.headers.has('Authorization')) {
      config.headers.set('Authorization', `Bearer ${token}`)
    }
    // 添加请求追踪 ID
    if (!config.headers.has('X-Request-ID')) {
      config.headers.set('X-Request-ID', crypto.randomUUID?.() ?? Math.random().toString(36).slice(2))
    }
    return config
  })
}

// ── 响应拦截器 ────────────────────────────────────

type RefreshWaiter = {
  resolve: (token: string) => void
  reject: (error: Error) => void
}

let isRefreshing = false
let refreshWaiters: RefreshWaiter[] = []

/**
 * 401 处理流程：
 * 1. 收到 401 → 暂停新的受保护请求
 * 2. 只触发一次宿主刷新握手
 * 3. 获取新 Token → 重放安全的读取请求
 * 4. 写请求不自动重试（避免重复提交）
 */
function installAutoRetryInterceptor(instance: AxiosInstance) {
  instance.interceptors.response.use(
    (response) => response,
    async (error) => {
      const config = error?.config
      if (error?.response?.status !== 401 || !config || config._retried) {
        return Promise.reject(error)
      }

      // 写请求不自动重试
      const method = (config.method || '').toLowerCase()
      if (['post', 'put', 'patch', 'delete'].includes(method)) {
        return Promise.reject(error)
      }

      config._retried = true

      if (isRefreshing) {
        // 等待刷新完成
        return new Promise((resolve, reject) => {
          refreshWaiters.push({
            resolve: (token: string) => {
              if (!token) {
                reject(new Error('Token refresh failed'))
                return
              }
              config.headers['Authorization'] = `Bearer ${token}`
              resolve(instance.request(config))
            },
            reject: (err: Error) => reject(err),
          })
        })
      }

      isRefreshing = true

      try {
        // 通过 iframe auth 刷新 Token（真正 await）
        const { refreshToken } = await import('../auth/iframeAuth')
        const newToken = await refreshToken()

        if (!newToken) {
          // 刷新失败，reject 所有等待者
          refreshWaiters.forEach(w => w.reject(new Error('Token refresh failed')))
          refreshWaiters = []
          throw new Error('Token refresh failed')
        }

        // 成功，resolve 所有等待者
        refreshWaiters.forEach(w => w.resolve(newToken))
        refreshWaiters = []

        config.headers['Authorization'] = `Bearer ${newToken}`
        return instance.request(config)
      } catch (err) {
        // 刷新失败，reject 所有等待者
        refreshWaiters.forEach(w => w.reject(err instanceof Error ? err : new Error(String(err))))
        refreshWaiters = []
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }
  )
}

// ── 安装拦截器 ────────────────────────────────────

;[api, analyticsApi, researchApi, bundleApi, alertsApi, aiApi].forEach(installAuthInterceptor)
;[api, analyticsApi, researchApi, bundleApi, alertsApi, aiApi].forEach(installAutoRetryInterceptor)

export { api, analyticsApi, researchApi, bundleApi, alertsApi }
export default api
