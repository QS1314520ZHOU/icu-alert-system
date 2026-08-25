<template>
  <component :is="themeWrapperComponent" v-bind="themeWrapperProps">
    <div class="root" :class="[isMobileRoute ? 'theme-light' : `theme-${themeMode}`, { 'root--mobile': isMobileRoute }]">
      <template v-if="isMobileRoute">
        <router-view />
      </template>
      <template v-else>
      <div class="shell">
        <SideNav />
        <div class="shell-main">
          <div class="topbar">
            <div class="topbar__left">
              <span class="topbar__crumb">SmartCare AI</span>
              <span class="topbar__brand">重症监护协同平台</span>
            </div>
            <div class="topbar__right">
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
              <span class="topbar__clock">{{ now }}</span>
            </div>
          </div>
          <main class="body"><router-view /></main>
          <AiPulseFloater />
        </div>
      </div>
      </template>
    </div>
  </component>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getClinicalAccount } from './api'
import { preloadCoreRouteComponents } from './router'
import AiPulseFloater from './components/AiPulseFloater.vue'
import SideNav from './components/common/SideNav.vue'
import { getOperatorIdentity, setOperatorIdentity } from './utils/operatorIdentity'
import { setThemeMode } from './composables/themeMode'
const route = useRoute()
const now = ref('')
const themeMode = ref<'dark' | 'light'>('light')
const operatorIdentity = ref('')
const operatorDisplayName = ref('')
const antTheme = ref<any>(null)
const antThemeReady = ref(false)
const themeWrapper = shallowRef<any>('div')
let t: any
const THEME_KEY = 'icu_theme_mode'
let operatorResolveSeq = 0
const operatorNameCache = new Map<string, string>()
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
      colorPrimary: dark ? '#15558D' : '#1D6F63',
      colorInfo: dark ? '#15558D' : '#2F7E72',
      colorSuccess: dark ? '#1A9C5B' : '#2F7A58',
      colorWarning: dark ? '#E8901C' : '#8A5E1B',
      colorError: dark ? '#D9342B' : '#B5483F',
      colorBgBase: dark ? '#07111d' : '#F3F1EA',
      colorBgContainer: dark ? '#0d1a2b' : '#FFFDF7',
      colorBgElevated: dark ? '#091827' : '#FFFDF7',
      colorText: dark ? '#d9e6f3' : '#16241E',
      colorTextSecondary: dark ? '#7f93ab' : '#3F564B',
      colorBorder: dark ? 'rgba(125, 167, 214, 0.14)' : '#D7DED3',
      borderRadius: 6,
      borderRadiusLG: 6,
      fontSize: 13,
      controlHeight: 32,
      controlHeightSM: 28,
      boxShadowSecondary: dark
        ? '0 18px 36px rgba(0,0,0,.34)'
        : '0 8px 22px rgba(54,69,58,.08)',
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



async function ensureAntdTheme() {
  if (antThemeReady.value) return
  const { ConfigProvider, theme } = await import('ant-design-vue')
  themeWrapper.value = markRaw(ConfigProvider)
  antTheme.value = theme
  antThemeReady.value = true
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

/* Shell layout */
.shell { display: flex; min-height: 100vh; }
.shell-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }

/* Top bar */
.topbar {
  height: 48px; flex: 0 0 48px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 18px; gap: 16px;
  background: var(--hdr-bg-strong);
  border-bottom: 1px solid var(--hdr-border);
  position: sticky; top: 0; z-index: 90;
}
.topbar__left { display: flex; align-items: center; gap: 16px; }
.topbar__crumb { font-size: 15px; font-weight: 800; color: var(--hdr-title); }
.topbar__brand { font-size: 12px; font-weight: 600; color: var(--hdr-sub, #7f93ab); }
.topbar__right { display: flex; align-items: center; gap: 12px; }
.topbar__clock {
  font-family: 'SF Mono','Consolas',monospace;
  color: var(--hdr-clock, #7f93ab);
  font-size: 12px; white-space: nowrap; letter-spacing: 0.02em;
}

.body { flex: 1; background: var(--app-bg); min-height: 0; overflow: auto; }

.operator-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: var(--card-radius);
  background: var(--hdr-tool-bg); border: 1px solid var(--hdr-tool-border); font-size: 12px;
}
.operator-pill__label { color: var(--text-secondary); font-size: 11px; }
.operator-pill__name { font-weight: 700; color: var(--text-primary); }
.operator-pill__input {
  width: 110px; background: transparent; border: none; outline: none;
  font-weight: 600; color: var(--text-primary); font-size: 12px;
}

/* Theme light overrides */
.theme-light .topbar {
  background: rgba(255,253,247,0.96) !important;
  border-bottom-color: var(--border-color);
}
.theme-light .topbar__crumb { color: var(--text-primary); }
.theme-light .topbar__brand { color: var(--text-secondary); }
.theme-light .operator-pill {
  background: rgba(255,253,247,0.78);
  border-color: rgba(168,177,163,0.34);
}
.theme-light .operator-pill__label { color: var(--text-secondary); }
.theme-light .operator-pill__input { font-weight: 600; color: var(--text-primary); }
.theme-light .operator-pill__name { color: var(--text-primary); }
.theme-light .topbar__clock { color: var(--text-secondary); }
.theme-light .body { background: var(--bg-base); }

@media (max-width: 920px) {
  .topbar__brand { display: none; }
  .topbar__clock { display: none; }
  .operator-pill__label { display: none; }
  .operator-pill__input { width: 88px; }
}
</style>
