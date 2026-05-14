type QueueItem = {
  id: string
  type: string
  payload: any
  createdAt: number
}

type ReplayHandler = (item: QueueItem) => Promise<void>

const QUEUE_KEY = 'mobile_offline_queue'

function readQueue(): QueueItem[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY)
    const rows = raw ? JSON.parse(raw) : []
    return Array.isArray(rows) ? rows : []
  } catch {
    return []
  }
}

function writeQueue(rows: QueueItem[]) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(rows.slice(-100)))
  } catch {
    // Embedded browsers may disable storage.
  }
}

export function makeIdempotencyKey(prefix: string) {
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

export function enqueueMobileAction(type: string, payload: any) {
  const rows = readQueue()
  rows.push({ id: makeIdempotencyKey(type), type, payload, createdAt: Date.now() })
  writeQueue(rows)
}

export function getQueuedMobileActions() {
  return readQueue()
}

export async function replayMobileQueue(handler: (item: QueueItem) => Promise<void>) {
  if (!navigator.onLine) return
  const rows = readQueue()
  const remaining: QueueItem[] = []
  for (const item of rows) {
    try {
      await handler(item)
    } catch {
      remaining.push(item)
    }
  }
  writeQueue(remaining)
}

export function createMobileQueueReplayer(handler: ReplayHandler) {
  let running = false
  const run = async () => {
    if (running || !navigator.onLine) return
    running = true
    try {
      await replayMobileQueue(handler)
    } finally {
      running = false
    }
  }
  window.addEventListener('online', run)
  void run()
  return () => window.removeEventListener('online', run)
}

export function registerMobileNotifications() {
  if (!('Notification' in window)) return
  if (Notification.permission === 'default') {
    void Notification.requestPermission().catch(() => undefined)
  }
}

export function scheduleMobileNotification(title: string, body: string, dueAt: string | Date) {
  if (!('Notification' in window)) return
  const due = new Date(dueAt).getTime()
  const delay = Math.max(due - Date.now(), 0)
  window.setTimeout(() => {
    if (Notification.permission === 'granted') {
      new Notification(title, { body, tag: title })
    }
    window.dispatchEvent(new CustomEvent('mobile:review-due', { detail: { title, body, dueAt } }))
  }, delay)
}
