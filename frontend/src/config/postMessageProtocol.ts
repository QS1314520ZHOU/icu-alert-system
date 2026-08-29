/**
 * ICU Alert System — 统一 PostMessage 协议
 *
 * 定义宿主(Host)与嵌入模块(Embed)之间的所有消息类型。
 * 禁止各模块自行定义任意消息。
 */

// ── 消息类型 ──────────────────────────────────────

/** 宿主 → iframe 发送的消息类型 */
export const HOST_MESSAGE_TYPES = {
  HOST_READY: 'HOST_READY',
  PATIENT_CONTEXT_CHANGED: 'PATIENT_CONTEXT_CHANGED',
  THEME_CHANGED: 'THEME_CHANGED',
  LOCALE_CHANGED: 'LOCALE_CHANGED',
  PERMISSION_CHANGED: 'PERMISSION_CHANGED',
  REFRESH_MODULE: 'REFRESH_MODULE',
  ROUTE_ACTIVATED: 'ROUTE_ACTIVATED',
} as const

/** iframe → 宿主 发送的消息类型 */
export const EMBED_MESSAGE_TYPES = {
  EMBED_READY: 'EMBED_READY',
  NAVIGATE_MODULE: 'NAVIGATE_MODULE',
  NAVIGATE_PATIENT: 'NAVIGATE_PATIENT',
  OPEN_PATIENT_DETAIL: 'OPEN_PATIENT_DETAIL',
  OPEN_ALERT: 'OPEN_ALERT',
  OPEN_EVIDENCE: 'OPEN_EVIDENCE',
  UPDATE_TITLE: 'UPDATE_TITLE',
  UPDATE_BREADCRUMB: 'UPDATE_BREADCRUMB',
  SET_DIRTY_STATE: 'SET_DIRTY_STATE',
  REQUEST_FULLSCREEN: 'REQUEST_FULLSCREEN',
  EXIT_FULLSCREEN: 'EXIT_FULLSCREEN',
  SHOW_NOTIFICATION: 'SHOW_NOTIFICATION',
  REPORT_ERROR: 'REPORT_ERROR',
  RESIZE: 'RESIZE',
} as const

export type HostMessageType = keyof typeof HOST_MESSAGE_TYPES
export type EmbedMessageType = keyof typeof EMBED_MESSAGE_TYPES

// ── 消息结构 ──────────────────────────────────────

export interface HostMessage<T = any> {
  source: 'icu-alert-host'
  version: '1.0'
  type: HostMessageType
  requestId: string
  timestamp: number
  payload: T
}

export interface EmbedMessage<T = any> {
  source: 'icu-alert-embed'
  version: '1.0'
  type: EmbedMessageType
  requestId: string
  timestamp: number
  payload: T
}

// ── Payload 类型 ──────────────────────────────────

export interface PatientContextPayload {
  patientId: string
  patientName?: string
  bed?: string
  dept?: string
  riskLevel?: string
  moduleKey?: string
}

export interface ThemePayload {
  mode: 'light' | 'dark'
  tokens?: Record<string, string>
}

export interface PermissionPayload {
  roles: string[]
  features: Record<string, boolean>
}

export interface RouteActivatedPayload {
  moduleKey: string
  path: string
}

export interface NavigateModulePayload {
  moduleKey: string
  patientId?: string
}

export interface ResizePayload {
  height: number
  width?: number
}

export interface ErrorPayload {
  code: string
  message: string
  details?: any
}

export interface NotificationPayload {
  type: 'info' | 'success' | 'warning' | 'error'
  title: string
  message?: string
}

export interface BreadcrumbPayload {
  items: Array<{ label: string; path?: string }>
}

export interface OpenEvidencePayload {
  contextType: string
  contextId?: string
  patientId: string
}

export interface OpenAlertPayload {
  alertId: string
  patientId: string
}

// ── 安全配置 ──────────────────────────────────────

export const ALLOWED_SOURCES = ['icu-alert-host', 'icu-alert-embed'] as const
export const PROTOCOL_VERSION = '1.0'

/** RESIZE 安全范围 */
export const RESIZE_MIN = 400
export const RESIZE_MAX = 2000

/** 通知文本最大长度 */
export const NOTIFICATION_TITLE_MAX = 200
export const NOTIFICATION_MESSAGE_MAX = 1000

/** requestId 去重窗口 (ms) */
export const REQUEST_ID_DEDUP_WINDOW = 5 * 60 * 1000

/** OPEN_EVIDENCE contextType 白名单 */
export const EVIDENCE_CONTEXT_TYPES = [
  'risk', 'alert', 'lab', 'medication', 'diagnosis', 'vital', 'treatment',
] as const

// ── 工具函数 ──────────────────────────────────────

let _requestIdCounter = 0

export function generateRequestId(): string {
  return `req_${Date.now()}_${++_requestIdCounter}`
}

/** 创建宿主消息 */
export function createHostMessage<T>(type: HostMessageType, payload: T): HostMessage<T> {
  return {
    source: 'icu-alert-host',
    version: PROTOCOL_VERSION,
    type,
    requestId: generateRequestId(),
    timestamp: Date.now(),
    payload,
  }
}

/** 创建嵌入消息 */
export function createEmbedMessage<T>(type: EmbedMessageType, payload: T): EmbedMessage<T> {
  return {
    source: 'icu-alert-embed',
    version: PROTOCOL_VERSION,
    type,
    requestId: generateRequestId(),
    timestamp: Date.now(),
    payload,
  }
}

/** 校验消息来源和结构 */
export function isValidMessage(data: any): boolean {
  if (!data || typeof data !== 'object') return false
  if (!ALLOWED_SOURCES.includes(data.source)) return false
  if (data.version !== PROTOCOL_VERSION) return false
  if (typeof data.type !== 'string') return false
  if (typeof data.requestId !== 'string' || !data.requestId) return false
  if (typeof data.timestamp !== 'number' || data.timestamp <= 0) return false
  return true
}

/** 判断是否为宿主消息 */
export function isHostMessage(data: any): data is HostMessage {
  return isValidMessage(data) && data.source === 'icu-alert-host'
}

/** 判断是否为嵌入消息 */
export function isEmbedMessage(data: any): data is EmbedMessage {
  return isValidMessage(data) && data.source === 'icu-alert-embed'
}

// ── requestId 去重 ──────────────────────────────────

const _seenRequestIds = new Map<string, number>()

/**
 * Check if a requestId has been seen recently (replay protection).
 * Returns true if this is a duplicate (should be rejected).
 */
export function isDuplicateRequestId(requestId: string): boolean {
  const now = Date.now()
  // Clean up old entries
  for (const [id, ts] of _seenRequestIds) {
    if (now - ts > REQUEST_ID_DEDUP_WINDOW) {
      _seenRequestIds.delete(id)
    }
  }
  if (_seenRequestIds.has(requestId)) return true
  _seenRequestIds.set(requestId, now)
  return false
}

// ── 逐类型 Schema 校验 ──────────────────────────────

/** String with max length check */
function isStringWithMax(val: any, maxLen: number): boolean {
  return typeof val === 'string' && val.length <= maxLen && val.length > 0
}

/** Validate host message payload by type */
export function validateHostPayload(type: string, payload: any): boolean {
  if (!payload || typeof payload !== 'object') return false
  switch (type) {
    case 'HOST_READY':
      return typeof payload.moduleKey === 'string' || typeof payload.patientId === 'string'
    case 'PATIENT_CONTEXT_CHANGED':
      return typeof payload.patientId === 'string' && payload.patientId.length > 0
    case 'THEME_CHANGED':
      return payload.mode === 'light' || payload.mode === 'dark'
    case 'LOCALE_CHANGED':
      return typeof payload.locale === 'string'
    case 'PERMISSION_CHANGED':
      return Array.isArray(payload.roles)
    case 'REFRESH_MODULE':
      return typeof payload.moduleKey === 'string'
    case 'ROUTE_ACTIVATED':
      return typeof payload.moduleKey === 'string' && typeof payload.path === 'string'
    default:
      return false
  }
}

/** Validate embed message payload by type */
export function validateEmbedPayload(type: string, payload: any): boolean {
  if (!payload || typeof payload !== 'object') return false
  switch (type) {
    case 'EMBED_READY':
      return typeof payload.moduleKey === 'string'
    case 'NAVIGATE_MODULE':
      return typeof payload.moduleKey === 'string' && payload.moduleKey.length > 0
    case 'NAVIGATE_PATIENT':
      return typeof payload.patientId === 'string' && payload.patientId.length > 0
    case 'OPEN_PATIENT_DETAIL':
      return typeof payload.patientId === 'string' && payload.patientId.length > 0
    case 'OPEN_ALERT':
      return typeof payload.alertId === 'string' && typeof payload.patientId === 'string'
    case 'OPEN_EVIDENCE':
      return (
        typeof payload.contextType === 'string' &&
        (EVIDENCE_CONTEXT_TYPES as readonly string[]).includes(payload.contextType) &&
        typeof payload.patientId === 'string' &&
        payload.patientId.length > 0
      )
    case 'UPDATE_TITLE':
      return isStringWithMax(payload.title, 500)
    case 'UPDATE_BREADCRUMB':
      return Array.isArray(payload.items) && payload.items.length <= 20
    case 'SET_DIRTY_STATE':
      return typeof payload.dirty === 'boolean'
    case 'REQUEST_FULLSCREEN':
    case 'EXIT_FULLSCREEN':
      return true
    case 'SHOW_NOTIFICATION':
      return (
        ['info', 'success', 'warning', 'error'].includes(payload.type) &&
        isStringWithMax(payload.title, NOTIFICATION_TITLE_MAX) &&
        (payload.message == null || (typeof payload.message === 'string' && payload.message.length <= NOTIFICATION_MESSAGE_MAX))
      )
    case 'REPORT_ERROR':
      return typeof payload.code === 'string' && typeof payload.message === 'string'
    case 'RESIZE':
      return (
        typeof payload.height === 'number' &&
        isFinite(payload.height) &&
        payload.height >= RESIZE_MIN &&
        payload.height <= RESIZE_MAX
      )
    default:
      return false
  }
}
