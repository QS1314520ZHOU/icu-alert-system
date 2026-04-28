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
          <button
            v-for="item in navItems"
            :key="item.key"
            type="button"
            :class="['nav-btn', { active: navKey === item.key }]"
            @click="onNav(item.key)"
          >
            <span v-for="line in item.lines" :key="line">{{ line }}</span>
          </button>
        </nav>
        <div class="hdr-tools">
          <label class="operator-pill" title="用于记录告警查看 / 确认操作人">
            <span class="operator-pill__label">操作人</span>
            <input
              v-model.trim="operatorIdentity"
              class="operator-pill__input"
              type="text"
              maxlength="48"
              placeholder="请输入工号/姓名"
              @change="onOperatorIdentityChange"
            />
          </label>
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
import { getOperatorIdentity, setOperatorIdentity } from './utils/operatorIdentity'
import { setThemeMode } from './composables/themeMode'
const route = useRoute()
const router = useRouter()
const now = ref('')
const themeMode = ref<'dark' | 'light'>('dark')
const notifyEnabled = ref(false)
const operatorIdentity = ref('')
const antTheme = ref<any>(null)
const antThemeReady = ref(false)
const themeWrapper = shallowRef<any>('div')
let t: any
const THEME_KEY = 'icu_theme_mode'
let alertSocketModulePromise: Promise<typeof import('./services/alertSocket')> | null = null
const navItems = [
  { key: 'overview', lines: ['患者', '总览'] },
  { key: 'analytics', lines: ['质控', '分析'] },
  { key: 'rounding-sheet', lines: ['查房', '报告'] },
  { key: 'respiratory-dashboard', lines: ['呼吸', '治疗'] },
  { key: 'research-export', lines: ['科研', '导出'] },
  { key: 'research-workbench', lines: ['科研', '分析'] },
  { key: 'academic-research', lines: ['学术', '科研'] },
  { key: 'clinical-trials', lines: ['临床', '试验'] },
  { key: 'mdt', lines: ['MDT', '会诊'] },
  { key: 'bigscreen', lines: ['护士站', '大屏'] },
  { key: 'ai-consult', lines: ['AI', '问诊'] },
  { key: 'ai-ops', lines: ['AI', '运营'] },
]

const navKey = computed(() => {
  if (route.path.startsWith('/bigscreen')) return 'bigscreen'
  if (route.path.startsWith('/analytics')) return 'analytics'
  if (route.path.startsWith('/rounding-sheet')) return 'rounding-sheet'
  if (route.path.startsWith('/respiratory-dashboard')) return 'respiratory-dashboard'
  if (route.path.startsWith('/research-export')) return 'research-export'
  if (route.path.startsWith('/research-workbench')) return 'research-workbench'
  if (route.path.startsWith('/academic-research')) return 'academic-research'
  if (route.path.startsWith('/clinical-trials')) return 'clinical-trials'
  if (route.path.startsWith('/mdt')) return 'mdt'
  if (route.path.startsWith('/ai-consult')) return 'ai-consult'
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
      colorPrimary: dark ? '#22d3ee' : '#2563EB',
      colorInfo: dark ? '#38bdf8' : '#3B82F6',
      colorSuccess: dark ? '#34d399' : '#16A34A',
      colorWarning: dark ? '#f59e0b' : '#D97706',
      colorError: dark ? '#f87171' : '#DC2626',
      colorBgBase: dark ? '#07111d' : '#F5F7FA',
      colorBgContainer: dark ? '#0d1a2b' : '#ffffff',
      colorBgElevated: dark ? '#091827' : '#ffffff',
      colorText: dark ? '#d9e6f3' : '#0F172A',
      colorTextSecondary: dark ? '#7f93ab' : '#64748B',
      colorBorder: dark ? 'rgba(125, 167, 214, 0.14)' : 'rgba(0, 0, 0, 0.06)',
      borderRadius: 12,
      borderRadiusLG: 14,
      fontSize: 13,
      controlHeight: 32,
      controlHeightSM: 28,
      boxShadowSecondary: dark
        ? '0 18px 36px rgba(0,0,0,.34)'
        : '0 1px 4px rgba(0,0,0,.08)',
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
  const pathMap: Record<string, string> = {
    overview: '/',
    analytics: '/analytics',
    'rounding-sheet': '/rounding-sheet',
    'respiratory-dashboard': '/respiratory-dashboard',
    'research-export': '/research-export',
    'research-workbench': '/research-workbench',
    'academic-research': '/academic-research',
    'clinical-trials': '/clinical-trials',
    mdt: '/mdt',
    'ai-consult': '/ai-consult',
    'ai-ops': '/ai-ops',
    bigscreen: '/bigscreen',
  }
  const path = pathMap[key] || '/'
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
  setThemeMode(mode)
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

function onOperatorIdentityChange() {
  operatorIdentity.value = setOperatorIdentity(operatorIdentity.value)
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
  operatorIdentity.value = getOperatorIdentity()
  tick()
  t = setInterval(tick, 1000)
})
onUnmounted(() => clearInterval(t))
</script>

<style scoped>
@import url('./assets/fonts/rajdhani/rajdhani.css');

.root { min-height: 100vh; background: var(--app-bg); font-family: var(--app-display-font, 'Noto Sans SC', 'Segoe UI', sans-serif); }
.hdr {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  background: var(--hdr-bg-strong) !important;
  backdrop-filter: blur(14px);
  padding: 0 24px;
  min-height: 60px;
  height: auto !important;
  line-height: normal !important;
  overflow: visible;
  border-bottom: 1px solid var(--hdr-border);
  box-shadow: var(--hdr-shadow);
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
  color: var(--hdr-icon-text);
  background: var(--hdr-icon-bg);
  border: 1px solid var(--hdr-icon-border);
  box-shadow: var(--hdr-icon-shadow);
}
.hdr-title { font-size: 18px; font-weight: 800; color: var(--hdr-title); letter-spacing: -0.02em; line-height: 1.15; white-space: nowrap; }
.hdr-sub { font-size: 11px; color: var(--hdr-sub); letter-spacing: 0.06em; line-height: 1.2; margin-top: 2px; text-transform: uppercase; }
.hdr-menu {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 60px;
  overflow: visible;
  padding: 6px 2px;
}
.nav-btn {
  display: inline-grid;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  min-width: 58px;
  min-height: 42px;
  white-space: normal;
  user-select: none;
  border: 1px solid var(--nav-btn-border);
  background: var(--nav-btn-bg);
  color: var(--nav-btn-text);
  border-radius: 12px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 750;
  letter-spacing: 0;
  cursor: pointer;
  transition: all 0.15s ease;
  line-height: 1;
}
.nav-btn span {
  display: block;
  line-height: 1.15;
}
.nav-btn:hover { color: var(--nav-btn-hover-text); background: var(--nav-btn-hover-bg); border-color: var(--nav-btn-hover-border); }
.nav-btn.active {
  color: var(--nav-btn-active-text);
  background: var(--nav-btn-active-bg);
  border-color: var(--nav-btn-active-border);
  box-shadow: var(--nav-btn-active-shadow);
}
.hdr-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: max-content;
  justify-self: end;
}
.operator-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 4px 8px 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--hdr-tool-border);
  background: var(--hdr-tool-bg);
}
.operator-pill__label {
  color: var(--hdr-tool-text);
  font-size: 10px;
  letter-spacing: 0.08em;
  white-space: nowrap;
}
.operator-pill__input {
  width: clamp(88px, 8vw, 118px);
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--hdr-title);
  font-size: 12px;
  font-family: 'SF Mono','Consolas',monospace;
}
.operator-pill__input::placeholder {
  color: var(--hdr-sub);
}
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid var(--hdr-tool-border);
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
  font-size: 12px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.body { background: var(--app-bg); min-height: calc(100vh - 60px); }

.theme-light .hdr {
  backdrop-filter: none;
  position: sticky;
}

.theme-light .hdr-l {
  padding-right: 8px;
}

.theme-light .hdr::after {
  content: '';
  position: absolute;
  left: 24px;
  right: 24px;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, rgba(59,130,246,.22), rgba(59,130,246,.04), rgba(59,130,246,.18));
}

.theme-light .nav-btn {
  font-weight: 600;
}

.theme-light .nav-btn.active {
  color: var(--nav-btn-active-text);
  background: var(--nav-btn-active-bg);
  border-color: var(--nav-btn-active-border);
  transform: translateY(-1px);
}

.theme-light .operator-pill,
.theme-light .theme-toggle {
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.06);
}

.theme-light .operator-pill__input {
  font-weight: 600;
}

.theme-light .switch-slider::before {
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.18);
}

.theme-light .body {
  background: #F5F7FA;
}

@media (max-width: 1200px) {
  .hdr { gap: 12px; padding: 0 12px; }
  .hdr-sub { display: none; }
  .nav-btn { min-width: 54px; min-height: 40px; font-size: 12px; padding: 5px 8px; }
  .operator-pill__label,
  .toggle-text {
    display: none;
  }
  .operator-pill__input {
    width: 88px;
  }
}

@media (max-width: 920px) {
  .hdr {
    grid-template-columns: auto auto;
    grid-template-areas:
      "brand tools"
      "nav nav";
    align-items: center;
    overflow: visible;
  }
  .hdr-l { grid-area: brand; }
  .hdr-menu {
    grid-area: nav;
    width: 100%;
    min-height: 48px;
    justify-content: flex-start;
    border-top: 1px solid var(--hdr-border);
  }
  .hdr-tools { grid-area: tools; }
  .hdr-tools { margin-left: auto; }
  .hdr-clock { display: none; }
}

@media (max-width: 600px) {
  .hdr-title { font-size: 13px; }
  .hdr-icon { font-size: 16px; }
  .theme-toggle { padding: 3px 6px; }
  .operator-pill {
    width: 100%;
    justify-content: space-between;
  }
  .operator-pill__input {
    width: 132px;
  }
}

@media (max-width: 1920px) {
  .hdr {
    padding: 0 20px;
    gap: 14px;
  }
  .hdr-title {
    font-size: 18px;
    letter-spacing: 0;
  }
  .hdr-sub {
    font-size: 11px;
    letter-spacing: 0.06em;
  }
  .nav-btn {
    min-width: 58px;
    min-height: 42px;
    font-size: 12px;
    padding: 6px 10px;
    letter-spacing: 0;
  }
  .operator-pill__label,
  .toggle-text,
  .hdr-clock {
    font-size: 11px;
  }
  .operator-pill__input {
    font-size: 12px;
  }
}
</style>



