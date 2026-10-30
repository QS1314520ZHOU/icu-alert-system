<template>
  <a-config-provider :locale="zhCN">
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
                <span v-if="operatorDisplayName" class="operator-pill__name">{{ operatorDisplayName }}</span>
                <span v-else class="operator-pill__unauthenticated">未登录</span>
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
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider as AConfigProvider } from 'ant-design-vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
dayjs.locale('zh-cn')
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
      colorPrimary: dark ? '#3B82F6' : '#2F6FED',
      colorInfo: dark ? '#38BDF8' : '#0284C7',
      colorSuccess: dark ? '#22C55E' : '#16A34A',
      colorWarning: dark ? '#F59E0B' : '#D97706',
      colorError: dark ? '#EF4444' : '#DC2626',
      colorBgBase: dark ? '#0B1220' : '#F7F8FA',
      colorBgContainer: dark ? '#111A2B' : '#FFFFFF',
      colorBgElevated: dark ? '#16213A' : '#FFFFFF',
      colorText: dark ? '#E5E7EB' : '#111827',
      colorTextSecondary: dark ? '#9CA3AF' : '#4B5563',
      colorBorder: dark ? 'rgba(148, 163, 184, 0.16)' : '#E5E7EB',
      borderRadius: 6,
      borderRadiusLG: 10,
      fontSize: 13,
      controlHeight: 32,
      controlHeightSM: 28,
      boxShadowSecondary: dark
        ? '0 8px 24px rgba(0,0,0,.4)'
        : '0 8px 24px rgba(17,24,39,.12)',
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

/**
 * 从认证存储同步操作人身份。
 * 安全要求：操作人身份不得来自 URL 参数，必须来自登录会话/JWT。
 */
function syncOperatorFromRoute() {
  const authUserId = String(auth.userId || auth.userName || '').trim()
  if (authUserId) {
    operatorIdentity.value = setOperatorIdentity(authUserId)
  }
  // URL 中的 userName 仅用于显示，不写入 operator identity
}

/**
 * 解析操作人显示名称。
 * 安全要求：userId/role/dept_code 必须来自登录会话，不得从 URL 读取。
 */
async function resolveOperatorDisplayName() {
  const userName = String(auth.userId || auth.userName || '').trim()
  const deptCode = String(auth.deptCode || '').trim()
  const dept = String(auth.dept || '').trim()
  const role = String(auth.role || '').trim()
  const cacheKey = [userName, role, deptCode, dept].join('|')
  const seq = ++operatorResolveSeq
  if (!userName) {
    operatorDisplayName.value = ''
    return
  }

  operatorDisplayName.value = operatorNameCache.get(cacheKey) || auth.userName || userName
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

// 操作人身份仅从认证存储同步，不监听 URL 参数变化
// URL 参数变更不影响操作人身份和角色解析
watch(() => [auth.userId, auth.userName], () => {
  syncOperatorFromRoute()
  void resolveOperatorDisplayName()
}, { immediate: true })

onMounted(() => {
  // iframe 内非 embed 路由：模板已走无壳分支，仅提示
  if (window.self !== window.top && !route.path.startsWith('/embed/')) {
    console.info('[App] Running in iframe without full shell:', route.path)
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

/* Top bar - 精致临床工作台 */
.topbar {
  height: 52px; flex: 0 0 52px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px 0 24px; gap: 16px;
  background: var(--color-bg-surface, #FFFFFF);
  border-bottom: 1px solid var(--color-border, #E5E7EB);
  position: sticky; top: 0; z-index: 90;
}
.topbar__left { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.topbar__crumb {
  font-size: 14px; font-weight: 700; letter-spacing: -0.01em;
  color: var(--color-text-primary, #111827);
}
.topbar__crumb::before {
  content: ''; display: inline-block; width: 8px; height: 8px;
  border-radius: 2px; background: var(--color-primary, #2F6FED);
  margin-right: 8px; vertical-align: 1px;
}
.topbar__brand {
  font-size: 12px; font-weight: 400;
  color: var(--color-text-tertiary, #9CA3AF);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.topbar__right { display: flex; align-items: center; gap: 10px; }
.topbar__clock {
  font-family: var(--font-mono, 'SF Mono', monospace);
  color: var(--color-text-secondary, #4B5563);
  font-size: 12px; white-space: nowrap; letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
  padding: 4px 10px; border-radius: 6px;
  background: var(--color-bg-surface-secondary, #F1F4F8);
}

.body { flex: 1; background: var(--color-bg-page, #F6F8FB); min-height: 0; overflow: auto; }

.operator-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 999px;
  background: var(--color-bg-surface-secondary, #F1F4F8);
  border: 1px solid var(--color-border, #E5E7EB);
  font-size: 12px;
}
.operator-pill__label { color: var(--color-text-tertiary, #9CA3AF); font-size: 12px; }
.operator-pill__name { font-weight: 600; color: var(--color-text-primary, #111827); }
.operator-pill__unauthenticated {
  font-weight: 500; color: var(--color-text-tertiary, #9CA3AF); font-size: 12px;
  font-style: italic;
}

@media (max-width: 920px) {
  .topbar__brand { display: none; }
  .topbar__clock { display: none; }
  .operator-pill__label { display: none; }
}
</style>
