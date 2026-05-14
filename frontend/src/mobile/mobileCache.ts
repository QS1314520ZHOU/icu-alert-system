export const mobileAlertCacheKey = (scope: string) => `mobile_alerts:${scope || 'all'}`

export function mobileScopeKey(deptCode?: string, deptLabel?: string) {
  return deptCode || deptLabel || 'all'
}

export function readMobileCache<T>(key: string, fallback: T): T {
  const stores = [sessionStorage, localStorage]
  for (const store of stores) {
    try {
      const raw = store.getItem(key)
      if (!raw) continue
      return JSON.parse(raw) as T
    } catch {
      // Ignore malformed or unavailable cache.
    }
  }
  return fallback
}

export function writeMobileCache(key: string, value: unknown) {
  const raw = JSON.stringify(value)
  for (const store of [sessionStorage, localStorage]) {
    try {
      store.setItem(key, raw)
    } catch {
      // Storage may be unavailable in some embedded browsers.
    }
  }
}
