type AlertMessage = {
  type: string
  data: any
}

type Listener = (msg: AlertMessage) => void

const listeners = new Set<Listener>()
let socket: WebSocket | null = null
let reconnectTimer: number | null = null

function buildWsUrl() {
  const base = import.meta.env.VITE_WS_BASE_URL as string | undefined
  if (base && base.length > 0) return `${base.replace(/\/$/, '')}/ws/alerts`
  const { protocol, host } = window.location
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProto}//${host}/ws/alerts`
}

function connect() {
  if (socket) return
  const url = buildWsUrl()
  socket = new WebSocket(url)

  socket.onmessage = evt => {
    try {
      const data = JSON.parse(evt.data)
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
    socket?.close()
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
