/**
 * useHostBridge — 宿主侧 postMessage 桥接
 *
 * 在 PatientModuleFrame 中使用，负责：
 * - 向 iframe 发送患者上下文、主题、权限等消息
 * - 接收 iframe 的导航请求、标题更新、错误报告
 * - 校验消息来源和结构
 */

import { ref, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import {
  createHostMessage,
  isEmbedMessage,
  isValidMessage,
  HOST_MESSAGE_TYPES,
  type HostMessage,
  type EmbedMessage,
  type PatientContextPayload,
  type ThemePayload,
  type PermissionPayload,
  type NavigateModulePayload,
  type ResizePayload,
  type ErrorPayload,
  type NotificationPayload,
  type BreadcrumbPayload,
} from '../config/postMessageProtocol'
import { getModuleByKey } from '../config/patientModuleRegistry'
import { canAccessPatientModule } from '../config/featureFlags'
import { useAuthStore } from '../stores/auth'

export interface HostBridgeOptions {
  iframeRef: Ref<HTMLIFrameElement | null>
  moduleKey: string
  patientId: string
  targetOrigin: string
  onNavigateModule?: (payload: NavigateModulePayload) => void
  onNavigatePatient?: (patientId: string) => void
  onOpenPatientDetail?: (patientId: string) => void
  onUpdateTitle?: (title: string) => void
  onUpdateBreadcrumb?: (payload: BreadcrumbPayload) => void
  onSetDirtyState?: (dirty: boolean) => void
  onRequestFullscreen?: () => void
  onExitFullscreen?: () => void
  onShowNotification?: (payload: NotificationPayload) => void
  onReportError?: (payload: ErrorPayload) => void
  onResize?: (payload: ResizePayload) => void
  onEmbedReady?: () => void
}

export function useHostBridge(options: HostBridgeOptions) {
  const {
    iframeRef,
    moduleKey,
    patientId,
    targetOrigin,
    onNavigateModule,
    onNavigatePatient,
    onOpenPatientDetail,
    onUpdateTitle,
    onUpdateBreadcrumb,
    onSetDirtyState,
    onRequestFullscreen,
    onExitFullscreen,
    onShowNotification,
    onReportError,
    onResize,
    onEmbedReady,
  } = options

  const embedReady = ref(false)
  const lastError = ref<ErrorPayload | null>(null)

  // ── 消息处理 ────────────────────────────────────

  function handleMessage(event: MessageEvent) {
    // ── 安全校验 ──
    // 1. 校验 origin
    if (targetOrigin !== '*' && event.origin !== targetOrigin) return
    // 2. 校验 source：只接受来自目标 iframe 的消息
    if (iframeRef.value && event.source !== iframeRef.value.contentWindow) return

    const data = event.data
    // 3. 校验 schema（基本结构）
    if (!isEmbedMessage(data)) return

    // 4. 校验 moduleKey（防止其他 iframe 的消息混入）
    if (data.payload?.moduleKey && data.payload.moduleKey !== moduleKey) return

    // 5. 校验 patientId（防止跨患者操作）
    if (data.payload?.patientId && data.payload.patientId !== patientId) {
      console.warn('[HostBridge] Rejected message with mismatched patientId:', data.payload.patientId)
      return
    }

    // 6. 导航类消息的权限二次校验
    if (data.type === 'NAVIGATE_MODULE') {
      const payload = data.payload as NavigateModulePayload
      const targetKey = payload?.moduleKey
      if (targetKey) {
        const targetMod = getModuleByKey(targetKey)
        if (targetMod) {
          const auth = useAuthStore()
          const userRole = String(auth.role || '').toLowerCase()
          if (!canAccessPatientModule(targetKey, {
            featureFlag: targetMod.featureFlag,
            requiredRoles: targetMod.requiredRoles,
          }, userRole)) {
            console.warn('[HostBridge] Rejected NAVIGATE_MODULE — no permission:', targetKey)
            return
          }
        }
      }
    }

    switch (data.type) {
      case 'EMBED_READY':
        embedReady.value = true
        onEmbedReady?.()
        // 立即发送患者上下文
        sendPatientContext()
        break

      case 'NAVIGATE_MODULE':
        onNavigateModule?.(data.payload as NavigateModulePayload)
        break

      case 'NAVIGATE_PATIENT':
        // patientId 已在校验5中确认匹配
        onNavigatePatient?.(data.payload?.patientId)
        break

      case 'OPEN_PATIENT_DETAIL':
        onOpenPatientDetail?.(data.payload?.patientId)
        break

      case 'UPDATE_TITLE':
        onUpdateTitle?.(data.payload?.title)
        break

      case 'UPDATE_BREADCRUMB':
        onUpdateBreadcrumb?.(data.payload as BreadcrumbPayload)
        break

      case 'SET_DIRTY_STATE':
        onSetDirtyState?.(Boolean(data.payload?.dirty))
        break

      case 'REQUEST_FULLSCREEN':
        onRequestFullscreen?.()
        break

      case 'EXIT_FULLSCREEN':
        onExitFullscreen?.()
        break

      case 'SHOW_NOTIFICATION':
        onShowNotification?.(data.payload as NotificationPayload)
        break

      case 'REPORT_ERROR':
        lastError.value = data.payload as ErrorPayload
        onReportError?.(data.payload as ErrorPayload)
        break

      case 'RESIZE':
        onResize?.(data.payload as ResizePayload)
        break
    }
  }

  // ── 发送消息 ────────────────────────────────────

  function postToEmbed(message: HostMessage) {
    const iframe = iframeRef.value
    if (!iframe?.contentWindow) return
    try {
      iframe.contentWindow.postMessage(message, targetOrigin)
    } catch (err) {
      console.warn('[HostBridge] Failed to post message:', err)
    }
  }

  function sendPatientContext() {
    postToEmbed(createHostMessage('PATIENT_CONTEXT_CHANGED', {
      patientId,
      moduleKey,
    } as PatientContextPayload))
  }

  function sendThemeChanged(mode: 'light' | 'dark', tokens?: Record<string, string>) {
    postToEmbed(createHostMessage('THEME_CHANGED', { mode, tokens } as ThemePayload))
  }

  function sendPermissionChanged(roles: string[], features: Record<string, boolean>) {
    postToEmbed(createHostMessage('PERMISSION_CHANGED', { roles, features } as PermissionPayload))
  }

  function sendRefresh() {
    postToEmbed(createHostMessage('REFRESH_MODULE', { moduleKey }))
  }

  function sendRouteActivated(moduleKey: string, path: string) {
    postToEmbed(createHostMessage('ROUTE_ACTIVATED', { moduleKey, path }))
  }

  function sendHostReady() {
    postToEmbed(createHostMessage('HOST_READY', { moduleKey, patientId }))
  }

  // ── 生命周期 ────────────────────────────────────

  onMounted(() => {
    window.addEventListener('message', handleMessage)
    // 如果 iframe 已经加载，发送 ready
    setTimeout(() => {
      if (!embedReady.value) sendHostReady()
    }, 1000)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('message', handleMessage)
  })

  // 患者切换时重新发送上下文
  watch(() => patientId, () => {
    embedReady.value = false
    if (iframeRef.value) {
      sendPatientContext()
    }
  })

  return {
    embedReady,
    lastError,
    sendPatientContext,
    sendThemeChanged,
    sendPermissionChanged,
    sendRefresh,
    sendRouteActivated,
    sendHostReady,
  }
}
