<template>
  <component :is="themeWrapperComponent" v-bind="themeWrapperProps">
    <div class="root" :class="`theme-${themeMode}`">
      <header class="hdr">
        <div class="hdr-l">
          <span class="hdr-icon">✚</span>
          <div>
            <div class="hdr-title">ICU 智能预警系统</div>
            <div class="hdr-sub">重症监护智能预警平台</div>
          </div>
        </div>
        <nav class="hdr-menu">
          <button type="button" :class="['nav-btn', { active: navKey === 'overview' }]" @click="onNav('overview')">患者总览</button>
          <button type="button" :class="['nav-btn', { active: navKey === 'analytics' }]" @click="onNav('analytics')">质控分析</button>
          <button type="button" :class="['nav-btn', { active: navKey === 'mdt' }]" @click="onNav('mdt')">MDT会诊</button>
          <button type="button" :class="['nav-btn', { active: navKey === 'bigscreen' }]" @click="onNav('bigscreen')">护士站大屏</button>
          <button type="button" :class="['nav-btn', { active: navKey === 'ai-ops' }]" @click="onNav('ai-ops')">AI运营</button>
        </nav>
        <div class="hdr-tools">
          <div class="theme-toggle">
            <span class="toggle-text">{{ notifyEnabled ? '通知开' : '通知关' }}</span>
            <label class="switch">
              <input type="checkbox" :checked="notifyEnabled" @change="onNotifyToggle(($event.target as HTMLInputElement)?.checked)" />
              <span class="switch-slider"></span>
            </label>
          </div>
          <div class="theme-toggle" :title="themeMode === 'dark' ? '当前夜间模式' : '当前白天模式'">
            <span class="theme-lbl">🌞</span>
            <label class="switch switch--compact">
              <input type="checkbox" :checked="themeMode === 'dark'" @change="onThemeToggle(($event.target as HTMLInputElement)?.checked)" />
              <span class="switch-slider switch-slider--compact"></span>
            </label>
            <span class="theme-lbl">🌙</span>
          </div>
          <span class="hdr-clock">{{ now }}</span>
        </div>
      </header>
      <main class="body"><router-view /></main>
    </div>
  </component>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
const route = useRoute()
const router = useRouter()
const now = ref('')
const themeMode = ref<'dark' | 'light'>('dark')
const notifyEnabled = ref(false)
const antTheme = ref<any>(null)
const antThemeReady = ref(false)
const themeWrapper = shallowRef<any>('div')
let t: any
const THEME_KEY = 'icu_theme_mode'
let alertSocketModulePromise: Promise<typeof import('./services/alertSocket')> | null = null

const navKey = computed(() => {
  if (route.path.startsWith('/bigscreen')) return 'bigscreen'
  if (route.path.startsWith('/analytics')) return 'analytics'
  if (route.path.startsWith('/mdt')) return 'mdt'
  if (route.path.startsWith('/ai-ops')) return 'ai-ops'
  return 'overview'
})
const routeNeedsAntdTheme = computed(() => Boolean(route.meta?.useAntdTheme))
const themeConfig = computed(() => {
  if (!antThemeReady.value || !antTheme.value) return undefined
  const dark = themeMode.value === 'dark'
  return {
    algorithm: dark
      ? antTheme.value.darkAlgorithm
      : antTheme.value.defaultAlgorithm,
    token: {
      colorPrimary: dark ? '#22d3ee' : '#1d4ed8',
      colorInfo: dark ? '#38bdf8' : '#2563eb',
      colorSuccess: dark ? '#34d399' : '#059669',
      colorWarning: dark ? '#f59e0b' : '#d97706',
      colorError: dark ? '#f87171' : '#dc2626',
      colorBgBase: dark ? '#07111d' : '#eef4f8',
      colorBgContainer: dark ? '#0d1a2b' : '#ffffff',
      colorBgElevated: dark ? '#091827' : '#ffffff',
      colorText: dark ? '#d9e6f3' : '#223a54',
      colorTextSecondary: dark ? '#7f93ab' : '#6f8399',
      colorBorder: dark ? 'rgba(125, 167, 214, 0.14)' : 'rgba(187, 204, 220, 0.72)',
      borderRadius: 12,
      borderRadiusLG: 14,
      fontSize: 12,
      controlHeight: 32,
      controlHeightSM: 28,
      boxShadowSecondary: dark
        ? '0 18px 36px rgba(0,0,0,.34)'
        : '0 12px 28px rgba(15,23,42,.08)',
    },
  }
})
const themeWrapperComponent = computed(() =>
  routeNeedsAntdTheme.value && antThemeReady.value ? themeWrapper.value : 'div'
)
const themeWrapperProps = computed(() =>
  routeNeedsAntdTheme.value && antThemeReady.value && themeConfig.value
    ? { theme: themeConfig.value }
    : {}
)

function onNav(key: string) {
  const path = key === 'overview' ? '/' : key === 'analytics' ? '/analytics' : key === 'mdt' ? '/mdt' : key === 'ai-ops' ? '/ai-ops' : '/bigscreen'
  router.push({ path, query: route.query })
}

async function ensureAntdTheme() {
  if (antThemeReady.value) return
  const { ConfigProvider, theme } = await import('ant-design-vue')
  themeWrapper.value = markRaw(ConfigProvider)
  antTheme.value = theme
  antThemeReady.value = true
}

function loadAlertSocketModule() {
  if (!alertSocketModulePromise) {
    alertSocketModulePromise = import('./services/alertSocket')
  }
  return alertSocketModulePromise
}

function applyTheme(mode: 'dark' | 'light') {
  document.documentElement.setAttribute('data-theme', mode)
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY)
  themeMode.value = saved === 'light' ? 'light' : 'dark'
  applyTheme(themeMode.value)
}

function onThemeToggle(checked: any) {
  const enabled = checked === true || checked === 'true'
  themeMode.value = enabled ? 'dark' : 'light'
}

async function initNotify() {
  const mod = await loadAlertSocketModule()
  notifyEnabled.value = mod.getAlertNotifyEnabled()
}

async function onNotifyToggle(checked: any) {
  const mod = await loadAlertSocketModule()
  const enabled = checked === true || checked === 'true'
  if (!enabled) {
    notifyEnabled.value = false
    mod.setAlertNotifyEnabled(false)
    return
  }
  const permission = await mod.requestAlertNotificationPermission()
  const ok = permission === 'granted'
  notifyEnabled.value = ok
  mod.setAlertNotifyEnabled(ok)
}

function tick() {
  now.value = new Date().toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

watch(themeMode, (mode) => {
  localStorage.setItem(THEME_KEY, mode)
  applyTheme(mode)
})

watch(routeNeedsAntdTheme, (needs) => {
  if (needs) void ensureAntdTheme()
}, { immediate: true })

onMounted(() => {
  initTheme()
  void initNotify()
  tick()
  t = setInterval(tick, 1000)
})
onUnmounted(() => clearInterval(t))
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&display=swap');

.root { min-height: 100vh; background: var(--app-bg); font-family: 'Rajdhani', 'Noto Sans SC', sans-serif; }
.hdr {
  display: flex; align-items: center; gap: 20px;
  background: var(--hdr-bg-strong) !important;
  backdrop-filter: blur(14px);
  padding: 10px 20px;
  min-height: 64px;
  height: auto !important;
  line-height: normal !important;
  overflow: visible;
  border-bottom: 1px solid rgba(80, 199, 255, 0.16);
  box-shadow: 0 8px 24px rgba(2, 8, 20, 0.22), inset 0 -1px 0 rgba(125, 241, 255, 0.04);
  position: sticky; top: 0; z-index: 100;
}
.hdr-l { display: flex; align-items: center; gap: 12px; }
.hdr-l > div { display: flex; flex-direction: column; justify-content: center; }
.hdr-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: #ecfeff;
  background: linear-gradient(180deg, #0b4e74 0%, #07273f 100%);
  border: 1px solid rgba(103, 232, 249, 0.22);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), 0 0 16px rgba(34, 211, 238, 0.08);
}
.hdr-title { font-size: 15px; font-weight: 700; color: var(--hdr-title); letter-spacing: 0.08em; line-height: 1.15; }
.hdr-sub { font-size: 9px; color: var(--hdr-sub); letter-spacing: 0.16em; line-height: 1.2; margin-top: 2px; text-transform: uppercase; }
.hdr-menu { flex: 1; display: flex; align-items: center; gap: 8px; }
.nav-btn {
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: var(--nav-btn-bg);
  color: var(--nav-btn-text);
  border-radius: 10px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: all 0.15s ease;
}
.nav-btn:hover { color: var(--nav-btn-hover-text); background: var(--nav-btn-hover-bg); border-color: rgba(103, 232, 249, 0.22); }
.nav-btn.active {
  color: var(--nav-btn-active-text);
  background: var(--nav-btn-active-bg);
  border-color: rgba(110, 231, 249, 0.32);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 0 14px rgba(34, 211, 238, 0.08);
}
.hdr-tools {
  display: flex;
  align-items: center;
  gap: 12px;
}
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: var(--hdr-tool-bg);
}
.theme-lbl {
  font-size: 12px;
  line-height: 1;
  opacity: 0.8;
}
.toggle-text {
  font-size: 10px;
  color: var(--hdr-tool-text);
}
.switch {
  position: relative;
  display: inline-flex;
  width: 34px;
  height: 20px;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.switch-slider {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: var(--switch-off-bg);
  transition: 0.2s ease;
}
.switch-slider::before {
  content: '';
  position: absolute;
  width: 14px;
  height: 14px;
  left: 3px;
  top: 3px;
  border-radius: 50%;
  background: #fff;
  transition: 0.2s ease;
}
.switch input:checked + .switch-slider {
  background: var(--switch-on-bg);
}
.switch input:checked + .switch-slider::before {
  transform: translateX(14px);
}
.switch--compact { width: 30px; height: 18px; }
.switch-slider--compact::before {
  width: 12px;
  height: 12px;
}
.switch--compact input:checked + .switch-slider--compact::before {
  transform: translateX(12px);
}
.hdr-clock {
  font-family: 'SF Mono','Consolas',monospace;
  color: var(--hdr-clock);
  font-size: 11px;
  white-space: nowrap;
  letter-spacing: 0.08em;
}
.body { background: var(--app-bg); min-height: calc(100vh - 60px); }

@media (max-width: 1200px) {
  .hdr { gap: 12px; padding: 8px 12px; }
  .hdr-sub { display: none; }
  .nav-btn { padding: 7px 10px; font-size: 12px; }
}

@media (max-width: 920px) {
  .hdr { flex-wrap: wrap; align-items: center; }
  .hdr-menu { order: 3; width: 100%; flex: 0 0 100%; }
  .hdr-tools { margin-left: auto; }
  .hdr-clock { display: none; }
}

@media (max-width: 600px) {
  .hdr-title { font-size: 13px; }
  .hdr-icon { font-size: 16px; }
  .theme-toggle { padding: 3px 6px; }
}
</style>



