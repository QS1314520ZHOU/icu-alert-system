type AlertMessage = {
  type: string
  data: any
}

type Listener = (msg: AlertMessage) => void

const listeners = new Set<Listener>()
let socket: WebSocket | null = null
let reconnectTimer: number | null = null
const NOTIFY_KEY = 'icu_alert_notify_enabled'

function buildWsUrl() {
  const base = import.meta.env.VITE_WS_BASE_URL as string | undefined
  if (base && base.length > 0) return `${base.replace(/\/$/, '')}/ws/alerts`
  const { protocol, host } = window.location
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProto}//${host}/ws/alerts`
}

function canUseNotification() {
  return typeof window !== 'undefined' && 'Notification' in window
}

export function getAlertNotifyEnabled() {
  const v = localStorage.getItem(NOTIFY_KEY)
  return v !== '0'
}

export function setAlertNotifyEnabled(enabled: boolean) {
  localStorage.setItem(NOTIFY_KEY, enabled ? '1' : '0')
}

export async function requestAlertNotificationPermission() {
  if (!canUseNotification()) return 'unsupported'
  const permission = await Notification.requestPermission()
  if (permission === 'granted') {
    setAlertNotifyEnabled(true)
  }
  return permission
}

function notifyAlert(msg: AlertMessage) {
  if (!canUseNotification()) return
  if (!getAlertNotifyEnabled()) return
  if (Notification.permission !== 'granted') return
  const alert = msg?.data || {}
  if (msg?.type !== 'alert') return
  if (!document.hidden) return

  const title = alert?.name || 'ICU 新预警'
  const severity = String(alert?.severity || 'warning').toUpperCase()
  const body = `${alert?.bed || '--'}床 ${alert?.patient_name || '未知患者'} · ${severity}`
  const tag = String(alert?._id || `${alert?.patient_id || ''}:${alert?.rule_id || ''}`)

  try {
    new Notification(title, { body, tag })
  } catch {
    // ignore
  }
}

function connect() {
  if (socket) return
  const url = buildWsUrl()
  socket = new WebSocket(url)

  socket.onmessage = evt => {
    try {
      const data = JSON.parse(evt.data)
      notifyAlert(data)
      listeners.forEach(fn => fn(data))
    } catch {
      // ignore parse errors
    }
  }

  socket.onclose = () => {
    socket = null
    scheduleReconnect()
  }

  socket.onerror = () => {
    // Let the browser drive close/reconnect; closing while CONNECTING
    // produces noisy console warnings in devtools.
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    if (listeners.size > 0) connect()
  }, 3000)
}

export function onAlertMessage(listener: Listener) {
  listeners.add(listener)
  connect()
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0 && socket) {
      socket.close()
      socket = null
    }
  }
}
