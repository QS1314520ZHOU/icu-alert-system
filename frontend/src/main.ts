import { createApp } from 'vue'
import 'ant-design-vue/dist/reset.css'
import { registerSW } from 'virtual:pwa-register'
import { registerClinicalThemes } from './charts/clinicalThemes'
import './style.css'
import './styles/clinical-documents-dark.css'
import './mobile/mobile.css'

// 注册 ECharts 临床主题（必须在任何图表组件挂载前）
registerClinicalThemes()

/**
 * Patch fetch and XHR to inject embed token into API requests.
 * Called early in bootstrap before any Vue component mounts.
 */
function patchEmbedToken(token: string) {
  // Patch fetch
  const origFetch = window.fetch
  ;(window as any).fetch = function (input: RequestInfo, init?: RequestInit) {
    try {
      const url = typeof input === 'string' ? input : (input as Request).url || ''
      if (/^\/(api|health|ws)/.test(url)) {
        const headers = new Headers((init && init.headers) || {})
        if (!headers.has('Authorization')) {
          headers.set('Authorization', 'Bearer ' + token)
        }
        if (!headers.has('X-SmartCare-Token')) {
          headers.set('X-SmartCare-Token', token)
        }
        init = { ...(init || {}), headers }
      }
    } catch {}
    return origFetch.call(window, input, init)
  }

  // Patch XMLHttpRequest
  const origOpen = XMLHttpRequest.prototype.open
  const origSend = XMLHttpRequest.prototype.send
  XMLHttpRequest.prototype.open = function (_method: string, url: string) {
    ;(this as any).__embedUrl = url
    return origOpen.apply(this, arguments as any)
  }
  XMLHttpRequest.prototype.send = function () {
    try {
      if (/^\/(api|health|ws)/.test((this as any).__embedUrl || '')) {
        this.setRequestHeader('Authorization', 'Bearer ' + token)
        this.setRequestHeader('X-SmartCare-Token', token)
      }
    } catch {}
    return origSend.apply(this, arguments as any)
  }
}

function syncDisplayQualityClass() {
  const dpr = window.devicePixelRatio || 1
  const width = Math.max(window.innerWidth || 0, window.screen?.width || 0)
  const height = Math.max(window.innerHeight || 0, window.screen?.height || 0)
  const isLarge1080p = dpr <= 1.25 && width >= 1600 && height <= 1200
  document.documentElement.classList.toggle('display-large-1080p', isLarge1080p)
}

async function bootstrap() {
  // Extract embed token from URL (set by embed.html before iframe loads)
  // This must happen before any API calls or Vue component mounts
  try {
    const params = new URLSearchParams(window.location.search)
    const scToken = params.get('__sc_token')
    if (scToken) {
      (window as any).__SMARTCARE_TOKEN__ = scToken
      // Patch fetch/XHR immediately so all subsequent API calls carry the token
      patchEmbedToken(scToken)
      // Clean token from URL (don't leave it in address bar)
      params.delete('__sc_token')
      const cleanSearch = params.toString()
      const cleanUrl = window.location.pathname + (cleanSearch ? '?' + cleanSearch : '') + window.location.hash
      window.history.replaceState(null, '', cleanUrl)
    }
  } catch {}

  syncDisplayQualityClass()
  document.documentElement.classList.toggle('boot-mobile', window.location.pathname.startsWith('/m'))
  window.addEventListener('resize', syncDisplayQualityClass, { passive: true })

  const [{ createPinia }, { default: App }, { default: router }] = await Promise.all([
    import('pinia'),
    import('./App.vue'),
    import('./router'),
  ])

  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(router)

  // 初始化认证（必须在组件挂载前完成）
  try {
    const { useAuthStore } = await import('./stores/auth')
    const { setTokenProvider } = await import('./api/http')
    const authStore = useAuthStore()

    // 注入 Token 提供者到 HTTP 客户端
    setTokenProvider({
      getAccessToken: () => authStore.accessToken,
    })

    // 初始化 iframe 认证
    await authStore.initAuth()
  } catch (err) {
    console.warn('[Bootstrap] Auth init failed:', err)
  }

  await router.isReady()
  app.mount('#app')
  document.documentElement.classList.remove('boot-mobile')
}

bootstrap()

registerSW({
  immediate: true,
  onRegisteredSW(swUrl, registration) {
    if (!registration) return
    window.setInterval(() => {
      registration.update().catch((error) => {
        console.warn(`[pwa] failed to update service worker from ${swUrl}`, error)
      })
    }, 60 * 1000)
  },
})
