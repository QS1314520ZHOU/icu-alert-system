import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import { registerSW } from 'virtual:pwa-register'
import App from './App.vue'
import router from './router'
import VChart from 'vue-echarts'
import './echarts'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(Antd)
app.component('VChart', VChart)
app.mount('#app')

registerSW({ immediate: true })
