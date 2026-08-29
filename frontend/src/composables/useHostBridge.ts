/**
 * useHostBridge — 宿主侧 postMessage 桥接
 *
 * 在 PatientModuleFrame 中使用，负责：
 * - 向 iframe 发送患者上下文、主题、权限等消息
 * - 接收 iframe 的导航请求、标题更新、错误报告
 * - 校验消息来源和结构
 */

import { ref, onMounted, onBeforeUnmount, watch, toValue, type Ref, type ComputedRef } from 'vue'
import {
  createHostMessage,
  isEmbedMessage,
  isDuplicateRequestId,
  validateEmbedPayload,
  EMBED_MESSAGE_TYPES,
  type HostMessage,
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
  moduleKey: Ref<string> | ComputedRef<string>
  patientId: Ref<string> | ComputedRef<string>
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

/** RESIZE height bounds */
const RESIZE_MIN_HEIGHT = 400
const RESIZE_MAX_HEIGHT = 2000

/** Maximum allowed message timestamp drift (ms) */
const MAX_TIMESTAMP_DRIFT = 5 * 60 * 1000 // 5 minutes

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

  /** Read current values reactively */
  const currentModuleKey = () => toValue(moduleKey)
  const currentPatientId = () => toValue(patientId)

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

    // 4. 校验 source 字段
    if (data.source !== 'icu-alert-embed') return

    // 5. 校验 version
    if (data.version !== '1.0') return

    // 6. 校验 type 白名单
    if (!Object.values(EMBED_MESSAGE_TYPES).includes(data.type)) return

    // 7. 校验 timestamp 格式和偏差
    if (typeof data.timestamp !== 'number' || data.timestamp <= 0) return
    const now = Date.now()
    if (Math.abs(now - data.timestamp) > MAX_TIMESTAMP_DRIFT) {
      console.warn('[HostBridge] Rejected message with stale timestamp:', data.type)
      return
    }

    // 8. 校验 requestId 存在且格式正确
    if (!data.requestId || typeof data.requestId !== 'string') return

    // 8b. requestId 短期去重（防重放）
    if (isDuplicateRequestId(data.requestId)) {
      console.warn('[HostBridge] Rejected duplicate requestId:', data.requestId)
      return
    }

    // 8c. 逐类型 payload schema 校验
    if (!validateEmbedPayload(data.type, data.payload)) {
      console.warn('[HostBridge] Rejected invalid payload for type:', data.type)
      return
    }

    // 9. 校验 moduleKey（防止其他 iframe 的消息混入）
    if (data.payload?.moduleKey && data.payload.moduleKey !== currentModuleKey()) return

    // 10-11. 校验 patientId（防止跨患者操作）
    if (data.payload?.patientId && data.payload.patientId !== currentPatientId()) {
      console.warn('[HostBridge] Rejected message with mismatched patientId:', data.payload.patientId)
      return
    }

    // 12-14. 导航类消息的权限二次校验
    if (data.type === 'NAVIGATE_MODULE') {
      const payload = data.payload as NavigateModulePayload
      const targetKey = payload?.moduleKey
      if (targetKey) {
        const targetMod = getModuleByKey(targetKey)
        if (!targetMod) {
          console.warn('[HostBridge] Rejected NAVIGATE_MODULE — unknown module:', targetKey)
          return
        }
        // 12. 校验 moduleKey 存在于 registry
        if (!targetMod) {
          console.warn('[HostBridge] Rejected NAVIGATE_MODULE — module not in registry:', targetKey)
          return
        }
        // 13. 校验 featureFlag 开启 + 14. 角色满足 requiredRoles
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

    // NAVIGATE_PATIENT: 不能信任 iframe 传来的 patientId
    // 校验已在步骤10-11完成（必须等于当前 patientId）
    // 如果需要切换患者，必须通过后端权限校验（此处不执行切换）

    // RESIZE: 安全范围校验
    if (data.type === 'RESIZE') {
      const payload = data.payload as ResizePayload
      if (payload?.height !== undefined) {
        const h = Number(payload.height)
        if (!isFinite(h) || h < RESIZE_MIN_HEIGHT || h > RESIZE_MAX_HEIGHT) {
          console.warn('[HostBridge] Rejected RESIZE — height out of bounds:', payload.height)
          return
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
        // patientId 已在校验10-11中确认匹配当前患者
        // 不执行切换 — 切换患者需要后端权限校验
        onNavigatePatient?.(currentPatientId())
        break

      case 'OPEN_PATIENT_DETAIL':
        onOpenPatientDetail?.(currentPatientId())
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
      patientId: currentPatientId(),
      moduleKey: currentModuleKey(),
    } as PatientContextPayload))
  }

  function sendThemeChanged(mode: 'light' | 'dark', tokens?: Record<string, string>) {
    postToEmbed(createHostMessage('THEME_CHANGED', { mode, tokens } as ThemePayload))
  }

  function sendPermissionChanged(roles: string[], features: Record<string, boolean>) {
    postToEmbed(createHostMessage('PERMISSION_CHANGED', { roles, features } as PermissionPayload))
  }

  function sendRefresh() {
    postToEmbed(createHostMessage('REFRESH_MODULE', { moduleKey: currentModuleKey() }))
  }

  function sendRouteActivated(moduleKey: string, path: string) {
    postToEmbed(createHostMessage('ROUTE_ACTIVATED', { moduleKey, path }))
  }

  function sendHostReady() {
    postToEmbed(createHostMessage('HOST_READY', { moduleKey: currentModuleKey(), patientId: currentPatientId() }))
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
  watch(
    () => toValue(patientId),
    (newPatientId, oldPatientId) => {
      if (newPatientId === oldPatientId) return
      embedReady.value = false
      if (iframeRef.value) {
        sendPatientContext()
      }
    }
  )

  // 模块切换时重新发送上下文
  watch(
    () => toValue(moduleKey),
    (newModuleKey, oldModuleKey) => {
      if (newModuleKey === oldModuleKey) return
      embedReady.value = false
      if (iframeRef.value) {
        sendPatientContext()
      }
    }
  )

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
