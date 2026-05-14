import { describe, expect, it } from 'vitest'
import { detectDeviceTier } from '../../src/components/HumanBody/composables/useDeviceTier'

function canvas(webgl: boolean, webgl2: boolean) {
  return () => ({
    getContext(name: string) {
      if (name === 'webgl') return webgl ? {} : null
      if (name === 'webgl2') return webgl2 ? {} : null
      return null
    },
  })
}

describe('detectDeviceTier', () => {
  it('detects high tier desktop devices', () => {
    expect(detectDeviceTier({
      userAgent: 'Mozilla/5.0 Chrome Desktop',
      deviceMemory: 16,
      hardwareConcurrency: 12,
      createCanvas: canvas(true, true),
    })).toBe('high')
  })

  it('detects low tier for mobile or weak devices', () => {
    expect(detectDeviceTier({
      userAgent: 'Mozilla/5.0 iPhone Mobile',
      deviceMemory: 8,
      hardwareConcurrency: 8,
      createCanvas: canvas(true, true),
    })).toBe('low')
    expect(detectDeviceTier({
      userAgent: 'Mozilla/5.0 Chrome Desktop',
      deviceMemory: 4,
      hardwareConcurrency: 4,
      createCanvas: canvas(true, true),
    })).toBe('low')
  })

  it('falls back when WebGL is unavailable', () => {
    expect(detectDeviceTier({
      userAgent: 'Mozilla/5.0 Chrome Desktop',
      deviceMemory: 16,
      hardwareConcurrency: 12,
      createCanvas: canvas(false, false),
    })).toBe('fallback')
  })

  it('uses low tier when WebGL2 is unavailable but WebGL exists', () => {
    expect(detectDeviceTier({
      userAgent: 'Mozilla/5.0 Chrome Desktop',
      deviceMemory: 16,
      hardwareConcurrency: 12,
      createCanvas: canvas(true, false),
    })).toBe('low')
  })
})
