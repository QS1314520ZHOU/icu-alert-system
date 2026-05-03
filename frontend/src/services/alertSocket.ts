type AlertMessage = {
  type: string
  data: any
}

type Listener = (msg: AlertMessage) => void

const listeners = new Set<Listener>()
let socket: WebSocket | null = null
let reconnectTimer: number | null = null
const NOTIFY_KEY = 'icu_alert_notify_enabled'
const pendingMessages: any[] = []

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

  socket.onopen = () => {
    while (pendingMessages.length && socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(pendingMessages.shift()))
    }
  }

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

// ── 全局语音播报（护士站大屏 / 广播） ─────────────────────────
const SPEECH_ENABLED_KEY = 'icu_alert_speech_enabled'

export function getAlertSpeechEnabled() {
  return localStorage.getItem(SPEECH_ENABLED_KEY) !== '0'
}

export function setAlertSpeechEnabled(enabled: boolean) {
  localStorage.setItem(SPEECH_ENABLED_KEY, enabled ? '1' : '0')
}

/**
 * 对 critical 级别预警执行语音播报。
 * 供护士站大屏等全局视图注册，内网音箱/广播通过浏览器 Web Speech API 输出。
 */
export function speakCriticalAlert(msg: AlertMessage) {
  if (msg?.type !== 'alert') return
  const alert = msg?.data || {}
  if (String(alert.severity || '').toLowerCase() !== 'critical') return
  if (!getAlertSpeechEnabled()) return
  if (!('speechSynthesis' in window)) return

  const bed = alert.bed || '--'
  const name = alert.patient_name || '患者'
  const ruleName = alert.name || '危急预警'
  const text = `危急预警：${bed}床，${name}，${ruleName}，请立即处置`

  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = 0.92
  utter.volume = 1
  // 不中断：排队播报，避免多条同时触发时互相打断
  window.speechSynthesis.speak(utter)
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

export function sendAlertSocketMessage(message: Record<string, any>) {
  connect()
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message))
    return
  }
  pendingMessages.push(message)
}
