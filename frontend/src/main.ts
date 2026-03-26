import { createApp } from 'vue'
import 'ant-design-vue/dist/reset.css'
import { registerSW } from 'virtual:pwa-register'
import './style.css'

async function bootstrap() {
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
