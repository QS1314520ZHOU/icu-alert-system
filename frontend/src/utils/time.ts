const BEIJING_TIME_ZONE = 'Asia/Shanghai'

export function formatBeijingTime(value: unknown, fallback = '时间未记载'): string {
  if (!value) return fallback
  const date = value instanceof Date ? value : new Date(String(value))
  if (Number.isNaN(date.getTime())) return fallback
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-')
}

export function formatBeijingClock(value: unknown, fallback = '—'): string {
  if (!value) return fallback
  const date = value instanceof Date ? value : new Date(String(value))
  if (Number.isNaN(date.getTime())) return fallback
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}
