<template>
  <a-config-provider :theme="themeConfig">
    <a-layout class="root" :class="`theme-${themeMode}`">
      <a-layout-header class="hdr">
        <div class="hdr-l">
          <span class="hdr-icon">🏥</span>
          <div>
            <div class="hdr-title">ICU 智能预警系统</div>
            <div class="hdr-sub">Intelligent Early Warning System</div>
          </div>
        </div>
        <a-menu mode="horizontal" :selected-keys="[navKey]" :theme="themeMode === 'dark' ? 'dark' : 'light'" class="hdr-menu"
                @click="({ key }: any) => onNav(key)">
          <a-menu-item key="overview">📋 患者总览</a-menu-item>
          <a-menu-item key="bigscreen">🖥 护士站大屏</a-menu-item>
        </a-menu>
        <div class="hdr-tools">
          <div class="theme-toggle" :title="themeMode === 'dark' ? '当前夜间模式' : '当前白天模式'">
            <span class="theme-lbl">🌞</span>
            <a-switch
              size="small"
              :checked="themeMode === 'dark'"
              checked-children="夜"
              un-checked-children="日"
              @change="onThemeToggle"
            />
            <span class="theme-lbl">🌙</span>
          </div>
          <span class="hdr-clock">{{ now }}</span>
        </div>
      </a-layout-header>
      <a-layout-content class="body"><router-view /></a-layout-content>
    </a-layout>
  </a-config-provider>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { theme } from 'ant-design-vue'

const { darkAlgorithm, defaultAlgorithm } = theme
const route = useRoute()
const router = useRouter()
const now = ref('')
const themeMode = ref<'dark' | 'light'>('dark')
let t: any
const THEME_KEY = 'icu_theme_mode'

const navKey = computed(() => route.path.startsWith('/bigscreen') ? 'bigscreen' : 'overview')
const themeConfig = computed(() => ({
  algorithm: themeMode.value === 'dark' ? darkAlgorithm : defaultAlgorithm,
}))

function onNav(key: string) {
  const path = key === 'overview' ? '/' : '/bigscreen'
  router.push({ path, query: route.query })
}

function applyTheme(mode: 'dark' | 'light') {
  document.documentElement.setAttribute('data-theme', mode)
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY)
  themeMode.value = saved === 'light' ? 'light' : 'dark'
  applyTheme(themeMode.value)
}

function onThemeToggle(checked: boolean) {
  themeMode.value = checked ? 'dark' : 'light'
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

onMounted(() => {
  initTheme()
  tick()
  t = setInterval(tick, 1000)
})
onUnmounted(() => clearInterval(t))
</script>

<style scoped>
.root { min-height: 100vh; background: var(--app-bg); }
.hdr {
  display: flex; align-items: center; gap: 20px;
  background: var(--hdr-bg) !important;
  padding: 8px 20px;
  min-height: 60px;
  height: auto !important;
  line-height: normal !important;
  overflow: visible;
  border-bottom: 1px solid var(--hdr-border);
}
.hdr-l { display: flex; align-items: center; gap: 8px; }
.hdr-l > div { display: flex; flex-direction: column; justify-content: center; }
.hdr-icon { font-size: 20px; }
.hdr-title { font-size: 15px; font-weight: 700; color: var(--hdr-title); letter-spacing: 0.5px; line-height: 1.25; }
.hdr-sub { font-size: 10px; color: var(--hdr-sub); letter-spacing: 0.3px; line-height: 1.2; margin-top: 2px; }
.hdr-menu { flex: 1; }
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
  border: 1px solid var(--hdr-border);
  background: var(--panel-soft);
}
.theme-lbl {
  font-size: 12px;
  line-height: 1;
  opacity: 0.8;
}
.hdr-clock { font-family: 'SF Mono','Consolas',monospace; color: var(--hdr-sub); font-size: 12px; white-space: nowrap; }
.body { background: var(--app-bg); min-height: calc(100vh - 60px); }

@media (max-width: 1200px) {
  .hdr { gap: 12px; padding: 8px 12px; }
  .hdr-sub { display: none; }
}

@media (max-width: 920px) {
  .hdr { flex-wrap: wrap; align-items: center; }
  .hdr-menu { order: 3; width: 100%; flex: 0 0 100%; }
  .hdr-tools { margin-left: auto; }
  .hdr-clock { display: none; }
}
</style>
