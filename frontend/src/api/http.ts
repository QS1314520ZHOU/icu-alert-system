/**
 * 统一 HTTP 客户端
 *
 * 全项目使用统一 HTTP 客户端，Token 由 auth store 统一管理。
 * 不让各业务组件分别管理 Token。
 */

import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

// ── Token 获取 ────────────────────────────────────

/**
 * 从 auth store 获取当前访问令牌。
 * 延迟导入避免循环依赖。
 */
function getAccessToken(): string {
  try {
    // 优先从 iframe auth 获取
    const { getAccessToken: getIframeToken } = require('../auth/iframeAuth')
    const iframeToken = getIframeToken()
    if (iframeToken) return iframeToken
  } catch {}

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

let isRefreshing = false
let refreshQueue: Array<(token: string) => void> = []

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
        return new Promise((resolve) => {
          refreshQueue.push((token: string) => {
            config.headers['Authorization'] = `Bearer ${token}`
            resolve(instance.request(config))
          })
        })
      }

      isRefreshing = true

      try {
        // 尝试通过 iframe auth 刷新
        const { refreshToken } = await import('../auth/iframeAuth')
        // refreshToken 内部会向宿主请求新 Token
        // 等待一小段时间让 Token 更新
        await new Promise(resolve => setTimeout(resolve, 500))

        const newToken = getAccessToken()
        if (!newToken) {
          throw new Error('Token refresh failed')
        }

        // 重放队列中的请求
        refreshQueue.forEach(cb => cb(newToken))
        refreshQueue = []

        config.headers['Authorization'] = `Bearer ${newToken}`
        return instance.request(config)
      } catch (err) {
        refreshQueue = []
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
