<template>
  <component :is="themeWrapperComponent" v-bind="themeWrapperProps">
    <div class="root" :class="[isMobileRoute ? 'theme-light' : `theme-${themeMode}`, { 'root--mobile': isMobileRoute }]">
      <template v-if="isMobileRoute">
        <router-view />
      </template>
      <template v-else>
      <header class="hdr">
        <div class="hdr-top">
          <div class="hdr-l">
            <span class="hdr-icon" aria-hidden="true"></span>
            <div>
              <div class="hdr-title">ICU智能协同工作台</div>
              <div class="hdr-sub">重症监护预警、交班、查房与质控协同平台</div>
            </div>
          </div>
          <div class="hdr-tools">
            <label class="operator-pill" title="用于记录告警查看 / 确认操作人">
              <span class="operator-pill__label">操作人</span>
              <span v-if="routeUserName" class="operator-pill__name">{{ operatorDisplayName || routeUserName }}</span>
              <input
                v-else
                v-model.trim="operatorIdentity"
                class="operator-pill__input"
                type="text"
                maxlength="48"
                placeholder="请输入工号/姓名"
                @change="onOperatorIdentityChange"
              />
            </label>
            <div v-if="false" class="theme-toggle">
              <span class="toggle-text">{{ notifyEnabled ? '通知开' : '通知关' }}</span>
              <label class="switch">
                <input type="checkbox" :checked="notifyEnabled" @change="onNotifyToggle(($event.target as HTMLInputElement)?.checked)" />
                <span class="switch-slider"></span>
              </label>
            </div>
            <div v-if="false" class="theme-toggle" :title="themeMode === 'dark' ? '当前夜间模式' : '当前白天模式'">
              <span class="theme-lbl">🌞</span>
              <label class="switch switch--compact">
                <input type="checkbox" :checked="themeMode === 'dark'" @change="onThemeToggle(($event.target as HTMLInputElement)?.checked)" />
                <span class="switch-slider switch-slider--compact"></span>
              </label>
              <span class="theme-lbl">🌙</span>
            </div>
            <span class="hdr-clock">{{ now }}</span>
          </div>
        </div>
        <div class="hdr-nav-shell">
          <nav class="hdr-menu" aria-label="主导航">
            <div v-for="group in navGroups" :key="group.key" class="nav-group">
              <span class="nav-group-label">{{ group.label }}</span>
              <div class="nav-group-items">
                <button
                  v-for="item in group.items"
                  :key="item.key"
                  type="button"
                  :class="['nav-btn', { active: navKey === item.key }]"
                  @mouseenter="preloadNav(item.key)"
                  @focus="preloadNav(item.key)"
                  @click="onNav(item.key)"
                >
                  <span v-for="line in item.lines" :key="line">{{ line }}</span>
                </button>
              </div>
            </div>
          </nav>
        </div>
      </header>
      <main class="body"><router-view /></main>
      <AiPulseFloater />
      </template>
    </div>
  </component>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getClinicalAccount } from './api'
import { preloadCoreRouteComponents, preloadRouteComponent } from './router'
import AiPulseFloater from './components/AiPulseFloater.vue'
import { getOperatorIdentity, setOperatorIdentity } from './utils/operatorIdentity'
import { setThemeMode } from './composables/themeMode'
import { navGroups, navItems, type NavItemKey } from './config/roleHomeConfig'
const route = useRoute()
const router = useRouter()
const now = ref('')
const themeMode = ref<'dark' | 'light'>('light')
const notifyEnabled = ref(false)
const operatorIdentity = ref('')
const operatorDisplayName = ref('')
const antTheme = ref<any>(null)
const antThemeReady = ref(false)
const themeWrapper = shallowRef<any>('div')
let t: any
const THEME_KEY = 'icu_theme_mode'
let alertSocketModulePromise: Promise<typeof import('./services/alertSocket')> | null = null
let operatorResolveSeq = 0
const operatorNameCache = new Map<string, string>()
const navComponentMap: Record<string, Parameters<typeof preloadRouteComponent>[0]> = {
  'doctor-home': 'doctorHome',
  'nurse-home': 'nurseHome',
  'clinical-workflow': 'clinicalWorkflow',
  overview: 'overview',
  analytics: 'analytics',
  'rounding-sheet': 'roundingSheet',
  'respiratory-dashboard': 'respiratoryDashboard',
  'nutrition-support': 'nutritionSupport',
  'research-export': 'researchExport',
  'research-workbench': 'researchWorkbench',
  'academic-research': 'academicResearch',
  'clinical-trials': 'clinicalTrials',
  mdt: 'mdtBoard',
  'ai-consult': 'aiConsult',
  'ai-ops': 'aiOps',
  'scanner-health': 'scannerHealth',
  'runtime-config': 'runtimeConfig',
  bigscreen: 'bigScreen',
  'patient-documents': 'overview',
}

const navKey = computed(() => {
  if (route.path.startsWith('/doctor-home')) return 'doctor-home'
  if (route.path.startsWith('/nurse-home')) return 'nurse-home'
  if (route.path.startsWith('/clinical-workflow')) return 'clinical-workflow'
  if (route.path.startsWith('/bigscreen')) return 'bigscreen'
  if (route.path.startsWith('/analytics')) return 'analytics'
  if (route.path.startsWith('/rounding-sheet')) return 'rounding-sheet'
  if (route.path.startsWith('/respiratory-dashboard')) return 'respiratory-dashboard'
  if (route.path.startsWith('/nutrition-support')) return 'nutrition-support'
  if (route.path.startsWith('/research-export')) return 'research-export'
  if (route.path.startsWith('/research-workbench')) return 'research-workbench'
  if (route.path.startsWith('/academic-research')) return 'academic-research'
  if (route.path.startsWith('/clinical-trials')) return 'clinical-trials'
  if (route.path.startsWith('/mdt')) return 'mdt'
  if (route.path.startsWith('/ai-consult')) return 'ai-consult'
  if (route.path.startsWith('/ai-ops')) return 'ai-ops'
  if (route.path.startsWith('/admin/scanner-health')) return 'scanner-health'
  if (route.path.startsWith('/admin/runtime-config')) return 'runtime-config'
  if (route.path.startsWith('/patient/') && route.query.tab === 'documents') return 'patient-documents'
  return 'overview'
})
function firstRouteQuery(...keys: string[]) {
  for (const key of keys) {
    const value = route.query[key]
    const text = String(Array.isArray(value) ? value[0] : value || '').trim()
    if (text) return text
  }
  return ''
}

const routeUserName = computed(() => firstRouteQuery('userName', 'useName', 'username', 'user_id', 'userId'))
const isBootMobilePath = typeof window !== 'undefined' && (window.location.pathname === '/m' || window.location.pathname.startsWith('/m/'))
const isMobileRoute = computed(() => Boolean(route.meta?.mobile) || (route.path === '/' && isBootMobilePath))
const routeNeedsAntdTheme = computed(() => Boolean(route.meta?.useAntdTheme))
const themeConfig = computed(() => {
  if (!antThemeReady.value || !antTheme.value) return undefined
  const dark = !isMobileRoute.value && themeMode.value === 'dark'
  return {
    algorithm: dark
      ? antTheme.value.darkAlgorithm
      : antTheme.value.defaultAlgorithm,
    token: {
      colorPrimary: dark ? '#15558D' : '#15558D',
      colorInfo: dark ? '#15558D' : '#15558D',
      colorSuccess: dark ? '#1A9C5B' : '#1A9C5B',
      colorWarning: dark ? '#E8901C' : '#A65A0C',
      colorError: dark ? '#D9342B' : '#D9342B',
      colorBgBase: dark ? '#07111d' : '#F2F3F5',
      colorBgContainer: dark ? '#0d1a2b' : '#ffffff',
      colorBgElevated: dark ? '#091827' : '#ffffff',
      colorText: dark ? '#d9e6f3' : '#1D2129',
      colorTextSecondary: dark ? '#7f93ab' : '#4E5969',
      colorBorder: dark ? 'rgba(125, 167, 214, 0.14)' : '#E5E6EB',
      borderRadius: 6,
      borderRadiusLG: 6,
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

function onNav(key: NavItemKey) {
  const item = navItems.find((row) => row.key === key)
  const path = item?.path || '/'
  const query = navIdentityQuery()
  if (key === 'patient-documents') {
    if (route.path.startsWith('/patient/')) {
      router.push({ path: route.path, query: { ...query, tab: 'documents' } })
      return
    }
    query.next = 'documents'
  }
  router.push({ path, query })
}

function navIdentityQuery() {
  const allowed = ['user_id', 'userId', 'userName', 'useName', 'username', 'role', 'dept', 'dept_code', 'deptCode', 'department']
  const next: Record<string, any> = {}
  for (const key of allowed) {
    const value = route.query[key]
    if (value != null && value !== '') next[key] = value
  }
  return next
}

function preloadNav(key: string) {
  const componentKey = navComponentMap[key]
  if (componentKey) void preloadRouteComponent(componentKey)
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
  // 展会默认浅色，忽略旧的 dark 偏好
  themeMode.value = 'light'
  localStorage.setItem(THEME_KEY, 'light')
  applyTheme(themeMode.value)
}

function onThemeToggle(_checked: any) {
  // 展会锁定浅色模式
  themeMode.value = 'light'
  localStorage.setItem(THEME_KEY, 'light')
  applyTheme('light')
}

function onOperatorIdentityChange() {
  operatorIdentity.value = setOperatorIdentity(operatorIdentity.value)
}

function syncOperatorFromRoute() {
  const normalized = routeUserName.value
  if (normalized) {
    operatorIdentity.value = setOperatorIdentity(normalized)
  }
}

async function resolveOperatorDisplayName() {
  const userName = routeUserName.value
  const deptCode = String(route.query.dept_code || route.query.deptCode || '').trim()
  const dept = String(route.query.dept || route.query.department || '').trim()
  const role = String(route.query.role || route.query.userRole || '').trim()
  const cacheKey = [userName, role, deptCode, dept].join('|')
  const seq = ++operatorResolveSeq
  if (!userName) {
    operatorDisplayName.value = ''
    return
  }

  // 账号识别先用地址栏工号即时展示，后台姓名查询只做增强，避免卡住首页/工作台渲染。
  operatorDisplayName.value = operatorNameCache.get(cacheKey) || userName
  if (operatorNameCache.has(cacheKey)) return

  try {
    const { data } = await getClinicalAccount({
      userName,
      role: role || undefined,
      dept_code: deptCode || undefined,
      dept: dept || undefined,
    })
    if (seq !== operatorResolveSeq) return
    const account = data?.account || {}
    const displayName = String(account.trueName || account.display_name || userName).trim()
    operatorNameCache.set(cacheKey, displayName)
    operatorDisplayName.value = displayName
  } catch {
    // 静默降级：接口慢/超时时继续显示地址栏账号，不再影响页面可用性。
    if (seq === operatorResolveSeq) operatorDisplayName.value = userName
  }
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

watch(() => [route.query.userName, route.query.useName, route.query.username, route.query.user_id, route.query.userId, route.query.dept_code, route.query.deptCode, route.query.dept, route.query.department], () => {
  syncOperatorFromRoute()
  void resolveOperatorDisplayName()
}, { immediate: true })

onMounted(() => {
  initTheme()
  preloadCoreRouteComponents()
  void initNotify()
  operatorIdentity.value = getOperatorIdentity()
  syncOperatorFromRoute()
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
  grid-template-columns: 1fr;
  gap: 0;
  background:
    var(--bg-surface), transparent 34%),
    var(--bg-surface) 0%, rgba(5, 15, 26, 0.96) 58%, rgba(3, 12, 22, 0.98) 100%) !important;
  backdrop-filter: blur(14px);
  padding: 0;
  min-height: 104px;
  height: auto !important;
  line-height: normal !important;
  overflow: hidden;
  border-bottom: 1px solid var(--hdr-border);
  box-shadow: var(--card-shadow);
  position: sticky; top: 0; z-index: 100;
}
.hdr-top {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 20px;
  padding: 16px 24px 10px;
}
.hdr-l { display: flex; align-items: center; gap: 12px; min-width: 270px; }
.hdr-l > div { display: flex; flex-direction: column; justify-content: center; }
.hdr-icon {
  position: relative;
  width: 34px;
  height: 34px;
  border-radius: var(--card-radius);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--hdr-icon-text);
  background: var(--hdr-icon-bg);
  border: 1px solid var(--hdr-icon-border);
  box-shadow: var(--card-shadow);
}
.hdr-icon::before,
.hdr-icon::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 17px;
  height: 4px;
  border-radius: var(--card-radius);
  background: currentColor;
  transform: translate(-50%, -50%);
}
.hdr-icon::after {
  width: 4px;
  height: 17px;
}
.hdr-title { font-size: 18px; font-weight: 800; color: var(--hdr-title); letter-spacing: -0.02em; line-height: 1.15; white-space: nowrap; }
.hdr-sub { font-size: 11px; color: var(--hdr-sub); letter-spacing: 0.06em; line-height: 1.2; margin-top: 2px; }
.hdr-nav-shell {
  min-width: 0;
  padding: 0 24px 14px;
  position: relative;
}
.hdr-nav-shell::before {
  content: '';
  position: absolute;
  left: 24px;
  right: 24px;
  top: 0;
  height: 1px;
  background: var(--border-color);
}
.hdr-menu {
  min-width: 0;
  display: flex;
  align-items: stretch;
  justify-content: flex-start;
  flex-wrap: nowrap;
  gap: 10px;
  min-height: 66px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 12px 2px 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(125, 211, 252, 0.32) transparent;
  mask-image: linear-gradient(to right, transparent, var(--bg-surface) 24px, var(--bg-surface) calc(100% - 24px), transparent);
}
.hdr-menu::-webkit-scrollbar {
  height: 4px;
}
.hdr-menu::-webkit-scrollbar-thumb {
  background: rgba(125, 211, 252, 0.28);
  border-radius: var(--card-radius);
}
.nav-group {
  flex: 0 0 auto;
  display: grid;
  gap: 7px;
  align-content: start;
  padding: 0 14px 8px 0;
  border-right: 1px solid rgba(125, 211, 252, 0.12);
}
.nav-group:last-child {
  border-right: 0;
}
.nav-group-label {
  color: var(--chart-1);
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
  white-space: nowrap;
  padding-left: 2px;
}
.nav-group-items {
  display: flex;
  align-items: center;
  gap: 7px;
}
.nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  min-width: 0;
  min-height: 42px;
  white-space: nowrap;
  user-select: none;
  border: 1px solid var(--nav-btn-border);
  background: var(--bg-surface), 0.76);
  color: var(--nav-btn-text);
  border-radius: var(--card-radius);
  padding: 0 16px;
  font-size: 14px;
  font-weight: 850;
  letter-spacing: 0;
  cursor: pointer;
  transition: all 0.15s ease;
  line-height: 1;
}
.nav-btn span {
  display: inline;
  line-height: 1;
}
.nav-btn span + span::before {
  content: '';
  display: none;
}
.nav-btn:hover { color: var(--nav-btn-hover-text); background: var(--nav-btn-hover-bg); border-color: var(--nav-btn-hover-border); }
.nav-btn.active {
  color: var(--text-primary);
  background: var(--bg-surface), rgba(14, 116, 144, 0.72));
  border-color: rgba(34, 211, 238, 0.82);
  box-shadow: var(--card-shadow);
  transform: translateY(-1px);
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
  border-radius: var(--card-radius);
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
.operator-pill__name {
  max-width: 128px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--hdr-title);
  font-size: 12px;
  font-weight: 800;
}
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--card-radius);
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
  border-radius: var(--card-radius);
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
  background: var(--bg-surface);
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
.body { background: var(--app-bg); min-height: calc(100vh - 104px); }

.theme-light .hdr {
  background: #FFFFFF !important;
  backdrop-filter: none;
  position: sticky;
  border-bottom: 1px solid #E5E6EB;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
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
  background: var(--bg-surface), rgba(59,130,246,.04), rgba(59,130,246,.18));
}

.theme-light .nav-btn {
  font-weight: 600;
  background: rgba(255, 255, 255, 0.82);
  color: var(--text-primary);
  border-color: rgba(148, 163, 184, 0.28);
  box-shadow: var(--card-shadow);
}

.theme-light .nav-btn:hover {
  color: var(--brand);
  background: rgba(239, 246, 255, 0.98);
  border-color: rgba(59, 130, 246, 0.28);
}

.theme-light .nav-btn.active {
  color: #15558D;
  background: #E8F3FF;
  border-bottom: 2px solid #15558D;
  border-radius: 6px 6px 0 0;
  box-shadow: none;
}

.theme-light .hdr-title {
  color: var(--text-primary);
}

.theme-light .hdr-sub,
.theme-light .operator-pill__label,
.theme-light .toggle-text,
.theme-light .hdr-clock,
.theme-light .theme-lbl {
  color: var(--text-secondary);
}

.theme-light .hdr-icon {
  color: var(--brand);
  background: var(--bg-surface);
  border-color: rgba(59, 130, 246, 0.24);
  box-shadow: var(--card-shadow);
}

.theme-light .hdr-nav-shell::before {
  background: var(--bg-surface);
}

.theme-light .hdr-menu {
  scrollbar-color: rgba(37, 99, 235, 0.28) transparent;
}

.theme-light .hdr-menu::-webkit-scrollbar-thumb {
  background: rgba(37, 99, 235, 0.24);
}

.theme-light .operator-pill,
.theme-light .theme-toggle {
  background: rgba(255, 255, 255, 0.82);
  border-color: rgba(148, 163, 184, 0.28);
  box-shadow: var(--card-shadow);
}

.theme-light .operator-pill__input {
  font-weight: 600;
  color: var(--text-primary);
}

.theme-light .operator-pill__name {
  color: var(--text-primary);
}

.theme-light .switch-slider {
  background: rgba(148, 163, 184, 0.36);
}

.theme-light .switch input:checked + .switch-slider {
  background: var(--brand);
}

.theme-light .switch-slider::before {
  box-shadow: var(--card-shadow);
}

.theme-light .body {
  background: var(--bg-base);
}

@media (max-width: 1200px) {
  .hdr-top { gap: 12px; padding: 14px 14px 8px; }
  .hdr-nav-shell { padding: 0 14px 12px; }
  .hdr-nav-shell::before { left: 14px; right: 14px; }
  .hdr-sub { display: none; }
  .nav-btn { min-height: 32px; font-size: 12px; padding: 0 10px; }
  .nav-group-label { display: none; }
  .hdr-menu { min-height: 42px; gap: 6px; }
  .operator-pill__label,
  .toggle-text {
    display: none;
  }
  .operator-pill__input {
    width: 88px;
  }
}

@media (max-width: 920px) {
  .hdr { overflow: hidden; }
  .hdr-top {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
  .hdr-l { min-width: 0; }
  .hdr-menu { width: 100%; min-height: 42px; justify-content: flex-start; }
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
    min-width: auto;
    min-height: 34px;
    font-size: 12px;
    padding: 0 10px;
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



