import type { HumanBodyTier } from '../../../types/organ'

export type DeviceTierInput = {
  userAgent?: string
  deviceMemory?: number
  hardwareConcurrency?: number
  createCanvas?: () => Pick<HTMLCanvasElement, 'getContext'>
}

function defaultCanvas() {
  return document.createElement('canvas')
}

function hasWebGlContext(contextName: 'webgl' | 'webgl2', createCanvas: () => Pick<HTMLCanvasElement, 'getContext'>) {
  try {
    return Boolean(createCanvas().getContext(contextName))
  } catch {
    return false
  }
}

export function detectDeviceTier(input: DeviceTierInput = {}): HumanBodyTier {
  if (typeof window === 'undefined' || typeof document === 'undefined') return 'fallback'
  const nav = navigator as Navigator & { deviceMemory?: number }
  const userAgent = String(input.userAgent ?? nav.userAgent ?? '').toLowerCase()
  const deviceMemory = Number(input.deviceMemory ?? nav.deviceMemory ?? 0)
  const hardwareConcurrency = Number(input.hardwareConcurrency ?? nav.hardwareConcurrency ?? 0)
  const createCanvas = input.createCanvas || defaultCanvas
  const webgl = hasWebGlContext('webgl', createCanvas)
  if (!webgl) return 'fallback'
  const webgl2 = hasWebGlContext('webgl2', createCanvas)
  const isMobile = /mobile|android|iphone|ipad|ipod|micromessenger|dingtalk/.test(userAgent)
  if (!webgl2 || isMobile || (deviceMemory > 0 && deviceMemory <= 4) || (hardwareConcurrency > 0 && hardwareConcurrency <= 4)) {
    return 'low'
  }
  if (deviceMemory >= 8) return 'high'
  return 'low'
}

export function useDeviceTier() {
  return { detectDeviceTier }
}
