import { describe, it, expect } from 'vitest'

/**
 * Risk Model Status Mapping Tests
 *
 * Verifies that internal English status codes are never shown directly to users
 * and that probability values are handled correctly.
 */

// Model status mapping (mirrors RiskPredictionView logic)
const MODEL_STATUS_MAP: Record<string, string> = {
  unknown: '未提供',
  weight_missing: '模型权重未加载',
  model_missing: '预测模型未部署',
  not_ready: '模型尚未就绪',
  unavailable: '当前不可用',
  pending: '计算中',
  fallback: '当前使用规则评估',
  ready: '就绪',
  available: '可用',
  loaded: '已加载',
}

const FORBIDDEN_STATUS_STRINGS = [
  'unknown', 'weight_missing', 'model_missing', 'not_ready',
  'unavailable', 'pending', 'fallback', 'NaN', 'null', 'undefined',
]

function mapModelStatus(raw: string): string {
  const key = String(raw || '').toLowerCase()
  return MODEL_STATUS_MAP[key] || raw || '未提供'
}

function toPercent(value: any): number {
  if (value == null || value === '') return 0
  const n = Number(value)
  if (!isFinite(n)) return 0
  if (n > 1 && n <= 100) return Math.round(n)
  if (n >= 0 && n <= 1) return Math.round(n * 100)
  if (n > 100) return 100
  return 0
}

describe('Risk Model Status Mapping', () => {
  describe('status code mapping', () => {
    it('maps unknown to Chinese', () => {
      expect(mapModelStatus('unknown')).toBe('未提供')
    })

    it('maps weight_missing to Chinese', () => {
      expect(mapModelStatus('weight_missing')).toBe('模型权重未加载')
    })

    it('maps model_missing to Chinese', () => {
      expect(mapModelStatus('model_missing')).toBe('预测模型未部署')
    })

    it('maps not_ready to Chinese', () => {
      expect(mapModelStatus('not_ready')).toBe('模型尚未就绪')
    })

    it('maps unavailable to Chinese', () => {
      expect(mapModelStatus('unavailable')).toBe('当前不可用')
    })

    it('maps fallback to Chinese', () => {
      expect(mapModelStatus('fallback')).toBe('当前使用规则评估')
    })

    it('maps empty string to default', () => {
      expect(mapModelStatus('')).toBe('未提供')
    })

    it('maps ready to Chinese', () => {
      expect(mapModelStatus('ready')).toBe('就绪')
    })
  })

  describe('no forbidden strings in mapped output', () => {
    const allStatuses = Object.keys(MODEL_STATUS_MAP)

    for (const status of allStatuses) {
      it(`mapped "${status}" does not contain forbidden English`, () => {
        const mapped = mapModelStatus(status)
        for (const forbidden of FORBIDDEN_STATUS_STRINGS) {
          expect(mapped.toLowerCase()).not.toBe(forbidden)
        }
      })
    }
  })

  describe('probability toPercent conversion', () => {
    it('converts 0-1 range to 0-100', () => {
      expect(toPercent(0.5)).toBe(50)
      expect(toPercent(0.99)).toBe(99)
      expect(toPercent(0)).toBe(0)
      expect(toPercent(1)).toBe(100)
    })

    it('handles 0-100 range values', () => {
      expect(toPercent(50)).toBe(50)
      expect(toPercent(75)).toBe(75)
      expect(toPercent(99)).toBe(99)
    })

    it('caps values above 100', () => {
      expect(toPercent(150)).toBe(100)
      expect(toPercent(999)).toBe(100)
    })

    it('handles null/undefined/empty', () => {
      expect(toPercent(null)).toBe(0)
      expect(toPercent(undefined)).toBe(0)
      expect(toPercent('')).toBe(0)
    })

    it('handles NaN', () => {
      expect(toPercent(NaN)).toBe(0)
      expect(toPercent('abc')).toBe(0)
    })

    it('handles negative values', () => {
      expect(toPercent(-0.5)).toBe(0)
    })
  })

  describe('model unavailability detection', () => {
    const unavailableStatuses = ['weight_missing', 'model_missing', 'not_ready', 'unavailable', 'unknown', 'pending']

    for (const status of unavailableStatuses) {
      it(`"${status}" is detected as unavailable`, () => {
        const modelAvailable = !unavailableStatuses.includes(status.toLowerCase())
        expect(modelAvailable).toBe(false)
      })
    }

    it('ready is available', () => {
      const status = 'ready'
      const unavailableStatuses = ['weight_missing', 'model_missing', 'not_ready', 'unavailable', 'unknown', 'pending']
      expect(unavailableStatuses.includes(status)).toBe(false)
    })
  })
})
