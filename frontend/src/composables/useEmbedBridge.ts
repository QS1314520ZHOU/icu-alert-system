/**
 * useEmbedBridge — iframe 侧 postMessage 桥接
 *
 * 在各嵌入模块中使用，负责：
 * - 向宿主发送导航请求、标题更新、错误报告
 * - 接收宿主的患者上下文、主题、权限等消息
 * - 校验消息来源和结构
 */

import { ref, onMounted, onBeforeUnmount, type Ref } from 'vue'
import {
  createEmbedMessage,
  isHostMessage,
  isDuplicateRequestId,
  validateHostPayload,
  EMBED_MESSAGE_TYPES,
  type EmbedMessage,
  type HostMessage,
  type PatientContextPayload,
  type ThemePayload,
  type PermissionPayload,
  type NavigateModulePayload,
  type BreadcrumbPayload,
  type ErrorPayload,
  type NotificationPayload,
} from '../config/postMessageProtocol'

export interface EmbedBridgeOptions {
  moduleKey: string
  targetOrigin: string
  onPatientContextChanged?: (payload: PatientContextPayload) => void
  onThemeChanged?: (payload: ThemePayload) => void
  onPermissionChanged?: (payload: PermissionPayload) => void
  onRefresh?: () => void
  onRouteActivated?: (moduleKey: string, path: string) => void
  onHostReady?: () => void
}

export function useEmbedBridge(options: EmbedBridgeOptions) {
  const {
    moduleKey,
    targetOrigin,
    onPatientContextChanged,
    onThemeChanged,
    onPermissionChanged,
    onRefresh,
    onRouteActivated,
    onHostReady,
  } = options

  const hostReady = ref(false)
  const patientId = ref('')
  const themeMode = ref<'light' | 'dark'>('light')

  // ── 消息处理 ────────────────────────────────────

  function handleMessage(event: MessageEvent) {
    // 校验 origin
    if (targetOrigin !== '*' && event.origin !== targetOrigin) return

    const data = event.data
    if (!isHostMessage(data)) return

    // requestId 去重（防重放）
    if (isDuplicateRequestId(data.requestId)) return

    // 逐类型 payload schema 校验
    if (!validateHostPayload(data.type, data.payload)) {
      console.warn('[EmbedBridge] Rejected invalid payload for type:', data.type)
      return
    }

    switch (data.type) {
      case 'HOST_READY':
        hostReady.value = true
        onHostReady?.()
        // 回复 EMBED_READY
        sendEmbedReady()
        break

      case 'PATIENT_CONTEXT_CHANGED':
        patientId.value = data.payload?.patientId || ''
        onPatientContextChanged?.(data.payload as PatientContextPayload)
        break

      case 'THEME_CHANGED':
        themeMode.value = data.payload?.mode || 'light'
        onThemeChanged?.(data.payload as ThemePayload)
        break

      case 'PERMISSION_CHANGED':
        onPermissionChanged?.(data.payload as PermissionPayload)
        break

      case 'REFRESH_MODULE':
        onRefresh?.()
        break

      case 'ROUTE_ACTIVATED':
        onRouteActivated?.(data.payload?.moduleKey, data.payload?.path)
        break
    }
  }

  // ── 发送消息 ────────────────────────────────────

  function postToHost(message: EmbedMessage) {
    try {
      window.parent.postMessage(message, targetOrigin)
    } catch (err) {
      console.warn('[EmbedBridge] Failed to post message:', err)
    }
  }

  function sendEmbedReady() {
    postToHost(createEmbedMessage('EMBED_READY', { moduleKey }))
  }

  function sendNavigateModule(targetModuleKey: string, targetPatientId?: string) {
    postToHost(createEmbedMessage('NAVIGATE_MODULE', {
      moduleKey: targetModuleKey,
      patientId: targetPatientId,
    } as NavigateModulePayload))
  }

  function sendNavigatePatient(targetPatientId: string) {
    postToHost(createEmbedMessage('NAVIGATE_PATIENT', { patientId: targetPatientId }))
  }

  function sendOpenPatientDetail(targetPatientId: string) {
    postToHost(createEmbedMessage('OPEN_PATIENT_DETAIL', { patientId: targetPatientId }))
  }

  function sendUpdateTitle(title: string) {
    postToHost(createEmbedMessage('UPDATE_TITLE', { title }))
  }

  function sendUpdateBreadcrumb(items: Array<{ label: string; path?: string }>) {
    postToHost(createEmbedMessage('UPDATE_BREADCRUMB', { items }))
  }

  function sendSetDirtyState(dirty: boolean) {
    postToHost(createEmbedMessage('SET_DIRTY_STATE', { dirty }))
  }

  function sendRequestFullscreen() {
    postToHost(createEmbedMessage('REQUEST_FULLSCREEN', {}))
  }

  function sendExitFullscreen() {
    postToHost(createEmbedMessage('EXIT_FULLSCREEN', {}))
  }

  function sendShowNotification(payload: NotificationPayload) {
    postToHost(createEmbedMessage('SHOW_NOTIFICATION', payload))
  }

  function sendReportError(code: string, message: string, details?: any) {
    postToHost(createEmbedMessage('REPORT_ERROR', { code, message, details } as ErrorPayload))
  }

  function sendResize(height: number, width?: number) {
    postToHost(createEmbedMessage('RESIZE', { height, width }))
  }

  // ── 生命周期 ────────────────────────────────────

  onMounted(() => {
    window.addEventListener('message', handleMessage)
    // 主动发送 EMBED_READY
    sendEmbedReady()
  })

  onBeforeUnmount(() => {
    window.removeEventListener('message', handleMessage)
  })

  return {
    hostReady,
    patientId,
    themeMode,
    sendEmbedReady,
    sendNavigateModule,
    sendNavigatePatient,
    sendOpenPatientDetail,
    sendUpdateTitle,
    sendUpdateBreadcrumb,
    sendSetDirtyState,
    sendRequestFullscreen,
    sendExitFullscreen,
    sendShowNotification,
    sendReportError,
    sendResize,
  }
}
