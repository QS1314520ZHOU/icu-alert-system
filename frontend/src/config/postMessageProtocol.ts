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

// ── 安全配置 ──────────────────────────────────────

export const ALLOWED_SOURCES = ['icu-alert-host', 'icu-alert-embed'] as const
export const PROTOCOL_VERSION = '1.0'

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
