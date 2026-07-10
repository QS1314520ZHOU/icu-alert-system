export function preferredChartPixelRatio() {
  if (typeof window === 'undefined') return 1
  const dpr = window.devicePixelRatio || 1
  const width = Math.max(window.innerWidth || 0, window.screen?.width || 0)
  const height = Math.max(window.innerHeight || 0, window.screen?.height || 0)
  const isLarge1080p = dpr <= 1.25 && width >= 1600 && height <= 1200
  return isLarge1080p ? 2 : Math.max(dpr, width <= 1920 ? 1.5 : 1)
}

export function chartInitOptions() {
  return {
    devicePixelRatio: preferredChartPixelRatio(),
  }
}
