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

registerSW({ immediate: true })
