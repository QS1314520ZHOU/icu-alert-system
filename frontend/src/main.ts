import { createApp } from 'vue'
import 'ant-design-vue/dist/reset.css'
import { registerSW } from 'virtual:pwa-register'
import './style.css'

function syncDisplayQualityClass() {
  const dpr = window.devicePixelRatio || 1
  const width = Math.max(window.innerWidth || 0, window.screen?.width || 0)
  const height = Math.max(window.innerHeight || 0, window.screen?.height || 0)
  const isLarge1080p = dpr <= 1.25 && width >= 1600 && height <= 1200
  document.documentElement.classList.toggle('display-large-1080p', isLarge1080p)
}

async function bootstrap() {
  syncDisplayQualityClass()
  window.addEventListener('resize', syncDisplayQualityClass, { passive: true })

  const [{ createPinia }, { default: App }, { default: router }] = await Promise.all([
    import('pinia'),
    import('./App.vue'),
    import('./router'),
  ])

  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')
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
