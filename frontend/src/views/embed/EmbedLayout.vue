<template>
  <div class="embed-layout" :class="`embed-layout--${themeMode}`">
    <!-- 面包屑 -->
    <div v-if="breadcrumbs.length" class="embed-breadcrumbs">
      <span
        v-for="(crumb, idx) in breadcrumbs"
        :key="idx"
        class="embed-crumb"
        :class="{ 'embed-crumb--last': idx === breadcrumbs.length - 1 }"
      >
        <span v-if="idx > 0" class="embed-crumb-sep">/</span>
        {{ crumb.label }}
      </span>
    </div>

    <!-- 内容区 -->
    <main class="embed-content">
      <router-view />
    </main>

    <!-- 临床决策支持声明 -->
    <footer class="embed-footer">
      <span class="embed-disclaimer">⚠ 仅供临床决策支持，不替代医生判断</span>
      <span v-if="modelVersion" class="embed-model-version">模型 {{ modelVersion }}</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../composables/useEmbedBridge'
import type { ThemePayload } from '../../config/postMessageProtocol'

const route = useRoute()
const themeMode = ref<'light' | 'dark'>('light')
const modelVersion = ref('')
const breadcrumbs = ref<Array<{ label: string; path?: string }>>([])

// 从路由 meta 或 query 获取 moduleKey
const moduleKey = computed(() => (route.meta?.moduleKey as string) || (route.params?.moduleKey as string) || '')

const { sendUpdateTitle, sendResize } = useEmbedBridge({
  moduleKey: moduleKey.value,
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => {
    // 模块可以通过 watch patientId 来响应患者切换
  },
  onThemeChanged: (payload: ThemePayload) => {
    themeMode.value = payload.mode
    document.documentElement.setAttribute('data-theme', payload.mode)
  },
  onRefresh: () => {
    window.location.reload()
  },
})

// 自动调整高度
function adjustHeight() {
  const height = document.documentElement.scrollHeight
  sendResize(height)
}

onMounted(() => {
  // 初始高度调整
  setTimeout(adjustHeight, 500)
  // 监听内容变化
  const observer = new ResizeObserver(() => adjustHeight())
  observer.observe(document.body)
})

// 路由变化时更新标题
watch(() => route.meta?.title, (title) => {
  if (title) sendUpdateTitle(String(title))
}, { immediate: true })
</script>

<style scoped>
.embed-layout {
  min-height: 100vh;
  background: var(--page-bg, #F4F7FB);
  font-family: var(--font-primary, 'Microsoft YaHei', sans-serif);
  color: var(--text-primary, #182230);
}

.embed-layout--dark {
  --page-bg: #0F172A;
  --text-primary: #E2E8F0;
  --text-secondary: #94A3B8;
  --text-tertiary: #64748B;
  --border: #1E293B;
  --card-bg: #1E293B;
  --primary: #3B82F6;
  background: #0F172A;
  color: #E2E8F0;
}

.embed-breadcrumbs {
  padding: 8px 24px;
  font-size: 12px;
  color: var(--text-tertiary, #94A3B8);
  border-bottom: 1px solid var(--border, #DCE3EC);
  background: var(--card-bg, #fff);
}

.embed-crumb--last {
  color: var(--text-primary, #182230);
  font-weight: 500;
}

.embed-crumb-sep {
  margin: 0 6px;
  opacity: 0.4;
}

.embed-content {
  padding: 16px 24px 32px;
  max-width: 1400px;
  margin: 0 auto;
}

.embed-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 24px;
  font-size: 11px;
  color: var(--text-tertiary, #94A3B8);
  border-top: 1px solid var(--border, #DCE3EC);
  background: var(--card-bg, #fff);
}

.embed-disclaimer {
  color: var(--warning, #F59E0B);
}

.embed-model-version {
  opacity: 0.6;
}
</style>

