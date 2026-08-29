<template>
  <div class="module-frame" :class="{ 'module-frame--fullscreen': isFullscreen }">
    <!-- 加载状态 -->
    <div v-if="loading" class="frame-loading">
      <div class="frame-skeleton">
        <div class="skeleton-header"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row skeleton-row--short"></div>
        <div class="skeleton-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>
      </div>
      <span class="frame-loading-text">加载 {{ moduleTitle }}...</span>
    </div>

    <!-- 错误状态 -->
    <div v-if="error && !loading" class="frame-error">
      <div class="frame-error-icon">⚠</div>
      <h3 class="frame-error-title">加载失败</h3>
      <p class="frame-error-desc">{{ error }}</p>
      <div class="frame-error-actions">
        <button class="frame-btn frame-btn--primary" @click="retry">重试</button>
        <button class="frame-btn" @click="openInNewTab">在新标签页打开</button>
      </div>
    </div>

    <!-- 权限不足 -->
    <div v-if="noPermission && !loading" class="frame-error">
      <div class="frame-error-icon">🔒</div>
      <h3 class="frame-error-title">权限不足</h3>
      <p class="frame-error-desc">您没有权限访问此模块</p>
    </div>

    <!-- 工具栏 -->
    <div v-if="showToolbar && !loading && !error" class="frame-toolbar">
      <div class="frame-toolbar__left">
        <span class="frame-toolbar__title">{{ moduleTitle }}</span>
        <span v-if="lastUpdated" class="frame-toolbar__time">更新于 {{ lastUpdated }}</span>
      </div>
      <div class="frame-toolbar__right">
        <button class="frame-icon-btn" title="刷新" @click="refresh">↻</button>
        <button class="frame-icon-btn" :title="isFullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
          {{ isFullscreen ? '⊟' : '⊞' }}
        </button>
        <button class="frame-icon-btn" title="在新标签页打开" @click="openInNewTab">↗</button>
      </div>
    </div>

    <!-- iframe -->
    <iframe
      v-show="!loading && !error && !noPermission"
      ref="iframeRef"
      :src="iframeSrc"
      class="module-frame__iframe"
      :class="{ 'module-frame__iframe--with-toolbar': showToolbar }"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      @load="onIframeLoad"
      @error="onIframeError"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useHostBridge } from '../composables/useHostBridge'
import { getModuleByKey, isIframeModule } from '../config/patientModuleRegistry'
import { canAccessPatientModule } from '../config/featureFlags'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{
  moduleKey: string
  patientId: string
  targetOrigin?: string
  showToolbar?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-module', moduleKey: string): void
  (e: 'navigate-patient', patientId: string): void
  (e: 'update-title', title: string): void
  (e: 'error', error: string): void
  (e: 'ready'): void
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const loading = ref(true)
const error = ref('')
const noPermission = ref(false)
const isFullscreen = ref(false)
const lastUpdated = ref('')

const auth = useAuthStore()

const module = computed(() => getModuleByKey(props.moduleKey))
const moduleTitle = computed(() => module.value?.title || props.moduleKey)

// Permission check
const hasPermission = computed(() => {
  if (!module.value) return true  // Unknown module — allow (will fail on iframe load)
  const userRole = String(auth.role || '').toLowerCase()
  return canAccessPatientModule(props.moduleKey, {
    featureFlag: module.value.featureFlag,
    requiredRoles: module.value.requiredRoles,
  }, userRole)
})

const iframeSrc = computed(() => {
  if (!hasPermission.value) return ''
  if (!module.value || !isIframeModule(props.moduleKey)) return ''
  return module.value.iframeUrl(props.patientId)
})

// ── Host Bridge ──────────────────────────────────

const origin = computed(() => {
  if (props.targetOrigin) return props.targetOrigin
  if (typeof window !== 'undefined') return window.location.origin
  return '*'
})

const moduleKeyRef = computed(() => props.moduleKey)
const patientIdRef = computed(() => props.patientId)

const { sendThemeChanged, sendRefresh: bridgeRefresh } = useHostBridge({
  iframeRef,
  moduleKey: moduleKeyRef,
  patientId: patientIdRef,
  targetOrigin: origin.value,
  onEmbedReady: () => {
    loading.value = false
    error.value = ''
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN')
    emit('ready')
  },
  onNavigateModule: (payload) => {
    emit('navigate-module', payload.moduleKey)
  },
  onNavigatePatient: (patientId) => {
    emit('navigate-patient', patientId)
  },
  onUpdateTitle: (title) => {
    emit('update-title', title)
  },
  onReportError: (payload) => {
    error.value = payload.message
    emit('error', payload.message)
  },
  onResize: (payload) => {
    const h = Number(payload.height)
    if (isFinite(h) && h >= 400 && h <= 2000 && iframeRef.value) {
      iframeRef.value.style.height = `${h}px`
    }
  },
})

// ── 操作 ─────────────────────────────────────────

function retry() {
  error.value = ''
  loading.value = true
  if (iframeRef.value) {
    iframeRef.value.src = iframeSrc.value
  }
}

function refresh() {
  bridgeRefresh()
  lastUpdated.value = new Date().toLocaleTimeString('zh-CN')
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function openInNewTab() {
  if (iframeSrc.value) {
    window.open(iframeSrc.value, '_blank')
  }
}

function onIframeLoad() {
  loading.value = false
}

function onIframeError() {
  loading.value = false
  error.value = '无法加载模块页面'
}

// ── 监听 ─────────────────────────────────────────

// Check permission on mount and when module changes
watch([hasPermission, () => props.moduleKey], () => {
  noPermission.value = !hasPermission.value
  if (hasPermission.value) {
    loading.value = true
    error.value = ''
  }
}, { immediate: true })

watch(() => props.patientId, () => {
  if (hasPermission.value) {
    loading.value = true
    error.value = ''
  }
})
</script>

<style scoped>
.module-frame {
  position: relative;
  width: 100%;
  min-height: 400px;
  background: var(--page-bg, #F4F7FB);
}

.module-frame--fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: #fff;
}

.module-frame__iframe {
  width: 100%;
  height: calc(100vh - 200px);
  min-height: 600px;
  border: none;
  display: block;
}

.module-frame__iframe--with-toolbar {
  height: calc(100vh - 240px);
}

/* Loading skeleton */
.frame-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  gap: 16px;
}

.frame-skeleton {
  width: 100%;
  max-width: 800px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-header {
  height: 24px;
  width: 40%;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s infinite;
  border-radius: 4px;
}

.skeleton-row {
  height: 16px;
  width: 100%;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s infinite;
  border-radius: 4px;
}

.skeleton-row--short { width: 60%; }

.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-top: 8px;
}

.skeleton-card {
  height: 120px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s infinite;
  border-radius: 8px;
}

@keyframes skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.frame-loading-text {
  font-size: 13px;
  color: var(--text-secondary, #52606D);
}

/* Error state */
.frame-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.frame-error-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.frame-error-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #182230);
}

.frame-error-desc {
  margin: 0 0 20px;
  font-size: 13px;
  color: var(--text-secondary, #52606D);
}

.frame-error-actions {
  display: flex;
  gap: 8px;
}

.frame-btn {
  padding: 6px 16px;
  font-size: 13px;
  border-radius: 6px;
  border: 1px solid var(--border, #DCE3EC);
  background: #fff;
  color: var(--text-primary, #182230);
  cursor: pointer;
  transition: all 0.15s;
}

.frame-btn:hover {
  background: var(--hover-bg, #F0F6FF);
}

.frame-btn--primary {
  background: var(--primary, #2563EB);
  color: #fff;
  border-color: var(--primary, #2563EB);
}

.frame-btn--primary:hover {
  background: var(--primary-hover, #3B82F6);
}

/* Toolbar */
.frame-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid var(--border, #DCE3EC);
}

.frame-toolbar__left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.frame-toolbar__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #182230);
}

.frame-toolbar__time {
  font-size: 11px;
  color: var(--text-tertiary, #94A3B8);
}

.frame-toolbar__right {
  display: flex;
  gap: 4px;
}

.frame-icon-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-secondary, #52606D);
  cursor: pointer;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.15s;
}

.frame-icon-btn:hover {
  background: var(--hover-bg, #F0F6FF);
  color: var(--primary, #2563EB);
}
</style>
