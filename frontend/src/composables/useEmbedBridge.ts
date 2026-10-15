/**
 * useEmbedBridge — iframe 侧 postMessage 桥接
 *
 * 在各嵌入模块中使用，负责：
 * - 向宿主发送导航请求、标题更新、错误报告
 * - 接收宿主的患者上下文、主题、权限等消息
 * - 校验消息来源和结构
 */

import { ref, onMounted, onBeforeUnmount, getCurrentInstance } from 'vue'
import { useRouter } from 'vue-router'
import { message as antdMessage } from 'ant-design-vue'
import {
  createEmbedMessage,
  isHostMessage,
  isDuplicateRequestId,
  validateHostPayload,
  type EmbedMessage,
  type PatientContextPayload,
  type ThemePayload,
  type PermissionPayload,
  type NavigateModulePayload,
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

/** 是否在 iframe 内运行 */
function isInIframe(): boolean {
  try { return window.self !== window.top } catch { return true }
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

  // 非 iframe 环境（直接渲染模式）：跳过所有 postMessage 逻辑
  const inIframe = isInIframe()

  // 直渲模式下 OPEN_PATIENT_DETAIL 需要宿主路由（仅组件 setup 内可用）
  const router = getCurrentInstance() ? useRouter() : null

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
      return
    }

    switch (data.type) {
      case 'HOST_READY':
        hostReady.value = true
        onHostReady?.()
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

  /**
   * 直接渲染模式（无 iframe）下的本地等价处理：
   * postMessage 无宿主可送达，改为在宿主页面内直接执行对应行为。
   * 仅处理有明确宿主语义的消息；SET_DIRTY_STATE / RESIZE /
   * NAVIGATE_MODULE / NAVIGATE_PATIENT 在直渲下没有对应的
   * iframe 宿主对象（高度自适应与脏标记无接收方，导航由模块
   * 内部路由或宿主组件自行处理），故不处理。
   */
  function handleDirect(message: EmbedMessage) {
    switch (message.type) {
      case 'UPDATE_TITLE': {
        const title = message.payload?.title
        if (title) document.title = `${title} - SmartCare AI`
        break
      }
      case 'UPDATE_BREADCRUMB': {
        const labels = (message.payload?.items || [])
          .map((item: { label?: string }) => item?.label)
          .filter(Boolean)
        if (labels.length) document.title = `${labels.join(' · ')} - SmartCare AI`
        break
      }
      case 'REQUEST_FULLSCREEN':
        document.documentElement.requestFullscreen?.().catch(() => undefined)
        break
      case 'EXIT_FULLSCREEN':
        if (document.fullscreenElement) document.exitFullscreen?.().catch(() => undefined)
        break
      case 'SHOW_NOTIFICATION': {
        const payload = message.payload as NotificationPayload
        const text = payload?.message ? `${payload.title}：${payload.message}` : payload?.title
        if (!text) break
        if (payload.type === 'success') antdMessage.success(text)
        else if (payload.type === 'error') antdMessage.error(text)
        else if (payload.type === 'warning') antdMessage.warning(text)
        else antdMessage.info(text)
        break
      }
      case 'OPEN_PATIENT_DETAIL': {
        const pid = message.payload?.patientId
        if (pid && router) void router.push(`/patient/${pid}/overview`)
        break
      }
    }
  }

  function postToHost(message: EmbedMessage) {
    if (!inIframe) {
      // 直接渲染模式：无 iframe 可通信，在宿主页面本地执行等价处理
      handleDirect(message)
      return
    }
    try {
      window.parent.postMessage(message, targetOrigin)
    } catch {}
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
    if (inIframe) {
      window.addEventListener('message', handleMessage)
      sendEmbedReady()
    } else {
      // 直接渲染模式：无需握手，立即就绪
      hostReady.value = true
      onHostReady?.()
    }
  })

  onBeforeUnmount(() => {
    if (inIframe) {
      window.removeEventListener('message', handleMessage)
    }
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
