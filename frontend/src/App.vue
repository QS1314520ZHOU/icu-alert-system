<template>
  <component :is="themeWrapperComponent" v-bind="themeWrapperProps">
    <div class="root" :class="[isMobileRoute ? 'theme-light' : `theme-${themeMode}`, { 'root--mobile': isMobileRoute }]">
      <template v-if="isEmbedRoute || (isInIframe && route.path.startsWith('/embed/'))">
        <router-view />
      </template>
      <template v-else-if="isInIframe">
        <!-- iframe 内非 embed 路由：不渲染完整 shell -->
        <router-view />
      </template>
      <template v-else-if="isMobileRoute">
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
                <span v-if="operatorDisplayName || routeUserName" class="operator-pill__name">{{ operatorDisplayName || routeUserName }}</span>
                <input
                  v-if="!operatorDisplayName && !routeUserName"
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
import { useAuthStore } from './stores/auth'
import { usePatientContext } from './stores/patientContext'
import { getClinicalAccount } from './api'
import { preloadCoreRouteComponents } from './router'
import AiPulseFloater from './components/AiPulseFloater.vue'
import SideNav from './components/common/SideNav.vue'
import { getOperatorIdentity, setOperatorIdentity } from './utils/operatorIdentity'
import { setThemeMode } from './composables/themeMode'
const route = useRoute()
const auth = useAuthStore()
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
const isEmbedRoute = computed(() => Boolean(route.meta?.embed))
const isInIframe = typeof window !== 'undefined' && window.self !== window.top
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
  const userName = routeUserName.value || auth.effectiveUserId || operatorIdentity.value
  const deptCode = String(route.query.dept_code || route.query.deptCode || auth.deptCode || '').trim()
  const dept = String(route.query.dept || route.query.department || auth.dept || '').trim()
  const role = String(route.query.role || route.query.userRole || auth.role || '').trim()
  const cacheKey = [userName, role, deptCode, dept].join('|')
  const seq = ++operatorResolveSeq
  if (!userName) {
    operatorDisplayName.value = ''
    return
  }

  // 账号识别先用地址栏工号即时展示，后台姓名查询只做增强，避免卡住首页/工作台渲染。
  operatorDisplayName.value = operatorNameCache.get(cacheKey) || auth.userName || userName
  if (operatorNameCache.has(cacheKey)) return

  try {
    const { data } = await getClinicalAccount({
      userName,
      role: role || auth.role || undefined,
      dept_code: deptCode || auth.deptCode || undefined,
      dept: dept || auth.dept || undefined,
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
  // 运行时 iframe 保护：阻止完整 App Shell 在 iframe 中渲染
  if (window.self !== window.top && !route.path.startsWith('/embed/')) {
    console.warn('[App] Blocked full App Shell inside iframe, redirecting to embed route')
    // 不渲染完整 shell，让 embed 路由接管
  }
  initTheme()
  preloadCoreRouteComponents()
  operatorIdentity.value = getOperatorIdentity()
  syncOperatorFromRoute()
  // Restore patient context from sessionStorage
  try { usePatientContext().restoreFromSession() } catch {}
  tick()
  t = setInterval(tick, 1000)
})
onUnmounted(() => clearInterval(t))
</script>

<style scoped>
.root { min-height: 100vh; background: var(--bg-base, #F6F7F9); font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; }

/* Shell layout */
.shell { display: flex; min-height: 100vh; }
.shell-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }

/* Top bar - 简洁浅色风格 */
.topbar {
  height: 48px; flex: 0 0 48px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; gap: 16px;
  background: #FFFFFF;
  border-bottom: 1px solid var(--color-border, #E3E7EC);
  position: sticky; top: 0; z-index: 90;
}
.topbar__left { display: flex; align-items: center; gap: 16px; }
.topbar__crumb { font-size: 15px; font-weight: 700; color: var(--color-text-primary, #18212B); }
.topbar__brand { font-size: 12px; font-weight: 400; color: var(--color-text-secondary, #667085); }
.topbar__right { display: flex; align-items: center; gap: 12px; }
.topbar__clock {
  font-family: 'SF Mono','Consolas',monospace;
  color: var(--color-text-secondary, #667085);
  font-size: 12px; white-space: nowrap; letter-spacing: 0.02em;
}

.body { flex: 1; background: var(--bg-base, #F6F7F9); min-height: 0; overflow: auto; }

.operator-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 6px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border: 1px solid var(--color-border, #E3E7EC);
  font-size: 12px;
}
.operator-pill__label { color: var(--color-text-secondary, #667085); font-size: 12px; }
.operator-pill__name { font-weight: 600; color: var(--color-text-primary, #18212B); }
.operator-pill__input {
  width: 110px; background: transparent; border: none; outline: none;
  font-weight: 600; color: var(--color-text-primary, #18212B); font-size: 12px;
}

@media (max-width: 920px) {
  .topbar__brand { display: none; }
  .topbar__clock { display: none; }
  .operator-pill__label { display: none; }
  .operator-pill__input { width: 88px; }
}
</style>
