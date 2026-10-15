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
  background: var(--color-bg-page, #F6F8FB);
  font-family: var(--font-primary, 'Microsoft YaHei', sans-serif);
  color: var(--color-text-primary, #111827);
}

/* 暗色主题：在 embed 容器作用域内覆写标准设计令牌，子视图自动适配 */
.embed-layout--dark {
  --color-bg-page: #0F172A;
  --color-bg-surface: #1E293B;
  --color-bg-surface-secondary: #1E293B;
  --color-bg-inset: #334155;
  --color-text-primary: #E2E8F0;
  --color-text-secondary: #94A3B8;
  --color-text-tertiary: #64748B;
  --color-border: #334155;
  --color-border-strong: #475569;
  --color-divider: #1E293B;
  --color-primary: #3B82F6;
  --color-primary-hover: #60A5FA;
  --color-primary-bg: rgba(59, 130, 246, 0.14);
  background: var(--color-bg-page);
  color: var(--color-text-primary);
}

.embed-breadcrumbs {
  padding: 8px 24px;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-tertiary, #9CA3AF);
  border-bottom: 1px solid var(--color-border, #E5E7EB);
  background: var(--color-bg-surface, #FFFFFF);
}

.embed-crumb--last {
  color: var(--color-text-primary, #111827);
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
  color: var(--color-text-tertiary, #9CA3AF);
  border-top: 1px solid var(--color-border, #E5E7EB);
  background: var(--color-bg-surface, #FFFFFF);
}

.embed-disclaimer {
  color: var(--color-warning, #B54708);
}

.embed-model-version {
  opacity: 0.6;
}
</style>

