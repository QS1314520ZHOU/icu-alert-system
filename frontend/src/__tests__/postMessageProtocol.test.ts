import { describe, it, expect } from 'vitest'
import {
  isValidMessage,
  isHostMessage,
  isEmbedMessage,
  isDuplicateRequestId,
  validateHostPayload,
  validateEmbedPayload,
  createHostMessage,
  createEmbedMessage,
  RESIZE_MIN,
  RESIZE_MAX,
  NOTIFICATION_TITLE_MAX,
} from '../config/postMessageProtocol'

describe('postMessageProtocol', () => {
  describe('isValidMessage', () => {
    it('rejects null/undefined', () => {
      expect(isValidMessage(null)).toBe(false)
      expect(isValidMessage(undefined)).toBe(false)
    })

    it('rejects non-object', () => {
      expect(isValidMessage('string')).toBe(false)
      expect(isValidMessage(42)).toBe(false)
    })

    it('rejects unknown source', () => {
      expect(isValidMessage({ source: 'unknown', version: '1.0', type: 'TEST', requestId: 'r1', timestamp: Date.now() })).toBe(false)
    })

    it('rejects wrong version', () => {
      expect(isValidMessage({ source: 'icu-alert-host', version: '2.0', type: 'TEST', requestId: 'r1', timestamp: Date.now() })).toBe(false)
    })

    it('rejects non-string type', () => {
      expect(isValidMessage({ source: 'icu-alert-host', version: '1.0', type: 123, requestId: 'r1', timestamp: Date.now() })).toBe(false)
    })

    it('rejects missing requestId', () => {
      expect(isValidMessage({ source: 'icu-alert-host', version: '1.0', type: 'TEST', timestamp: Date.now() })).toBe(false)
    })

    it('rejects invalid timestamp', () => {
      expect(isValidMessage({ source: 'icu-alert-host', version: '1.0', type: 'TEST', requestId: 'r1', timestamp: -1 })).toBe(false)
      expect(isValidMessage({ source: 'icu-alert-host', version: '1.0', type: 'TEST', requestId: 'r1', timestamp: 'now' })).toBe(false)
    })

    it('accepts valid host message', () => {
      expect(isValidMessage({ source: 'icu-alert-host', version: '1.0', type: 'HOST_READY', requestId: 'r1', timestamp: Date.now() })).toBe(true)
    })

    it('accepts valid embed message', () => {
      expect(isValidMessage({ source: 'icu-alert-embed', version: '1.0', type: 'EMBED_READY', requestId: 'r2', timestamp: Date.now() })).toBe(true)
    })
  })

  describe('isHostMessage / isEmbedMessage', () => {
    it('correctly identifies host messages', () => {
      const msg = { source: 'icu-alert-host', version: '1.0', type: 'HOST_READY', requestId: 'r1', timestamp: Date.now() }
      expect(isHostMessage(msg)).toBe(true)
      expect(isEmbedMessage(msg)).toBe(false)
    })

    it('correctly identifies embed messages', () => {
      const msg = { source: 'icu-alert-embed', version: '1.0', type: 'EMBED_READY', requestId: 'r2', timestamp: Date.now() }
      expect(isEmbedMessage(msg)).toBe(true)
      expect(isHostMessage(msg)).toBe(false)
    })
  })

  describe('isDuplicateRequestId', () => {
    it('returns false for first occurrence', () => {
      const id = `test_${Date.now()}_unique1`
      expect(isDuplicateRequestId(id)).toBe(false)
    })

    it('returns true for duplicate', () => {
      const id = `test_${Date.now()}_unique2`
      expect(isDuplicateRequestId(id)).toBe(false)
      expect(isDuplicateRequestId(id)).toBe(true)
    })

    it('different requestIds are not duplicates', () => {
      const id1 = `test_${Date.now()}_a`
      const id2 = `test_${Date.now()}_b`
      expect(isDuplicateRequestId(id1)).toBe(false)
      expect(isDuplicateRequestId(id2)).toBe(false)
    })
  })

  describe('validateHostPayload', () => {
    it('validates HOST_READY', () => {
      expect(validateHostPayload('HOST_READY', { moduleKey: 'risk-prediction' })).toBe(true)
      expect(validateHostPayload('HOST_READY', {})).toBe(false)
    })

    it('validates PATIENT_CONTEXT_CHANGED', () => {
      expect(validateHostPayload('PATIENT_CONTEXT_CHANGED', { patientId: 'p1' })).toBe(true)
      expect(validateHostPayload('PATIENT_CONTEXT_CHANGED', { patientId: '' })).toBe(false)
      expect(validateHostPayload('PATIENT_CONTEXT_CHANGED', {})).toBe(false)
    })

    it('validates THEME_CHANGED', () => {
      expect(validateHostPayload('THEME_CHANGED', { mode: 'light' })).toBe(true)
      expect(validateHostPayload('THEME_CHANGED', { mode: 'dark' })).toBe(true)
      expect(validateHostPayload('THEME_CHANGED', { mode: 'blue' })).toBe(false)
    })

    it('validates REFRESH_MODULE', () => {
      expect(validateHostPayload('REFRESH_MODULE', { moduleKey: 'evidence' })).toBe(true)
      expect(validateHostPayload('REFRESH_MODULE', {})).toBe(false)
    })

    it('rejects unknown type', () => {
      expect(validateHostPayload('UNKNOWN_TYPE', { foo: 'bar' })).toBe(false)
    })
  })

  describe('validateEmbedPayload', () => {
    it('validates EMBED_READY', () => {
      expect(validateEmbedPayload('EMBED_READY', { moduleKey: 'evidence' })).toBe(true)
      expect(validateEmbedPayload('EMBED_READY', {})).toBe(false)
    })

    it('validates NAVIGATE_MODULE', () => {
      expect(validateEmbedPayload('NAVIGATE_MODULE', { moduleKey: 'risk-prediction' })).toBe(true)
      expect(validateEmbedPayload('NAVIGATE_MODULE', { moduleKey: '' })).toBe(false)
    })

    it('validates RESIZE with bounds', () => {
      expect(validateEmbedPayload('RESIZE', { height: 600 })).toBe(true)
      expect(validateEmbedPayload('RESIZE', { height: RESIZE_MIN - 1 })).toBe(false)
      expect(validateEmbedPayload('RESIZE', { height: RESIZE_MAX + 1 })).toBe(false)
      expect(validateEmbedPayload('RESIZE', { height: -100 })).toBe(false)
    })

    it('validates SHOW_NOTIFICATION', () => {
      expect(validateEmbedPayload('SHOW_NOTIFICATION', { type: 'info', title: 'Test' })).toBe(true)
      expect(validateEmbedPayload('SHOW_NOTIFICATION', { type: 'invalid', title: 'Test' })).toBe(false)
      expect(validateEmbedPayload('SHOW_NOTIFICATION', { type: 'info', title: 'x'.repeat(NOTIFICATION_TITLE_MAX + 1) })).toBe(false)
    })

    it('validates REPORT_ERROR', () => {
      expect(validateEmbedPayload('REPORT_ERROR', { code: 'ERR', message: 'fail' })).toBe(true)
      expect(validateEmbedPayload('REPORT_ERROR', { code: 'ERR' })).toBe(false)
    })

    it('validates UPDATE_TITLE', () => {
      expect(validateEmbedPayload('UPDATE_TITLE', { title: 'My Title' })).toBe(true)
      expect(validateEmbedPayload('UPDATE_TITLE', { title: '' })).toBe(false)
      expect(validateEmbedPayload('UPDATE_TITLE', { title: 'x'.repeat(501) })).toBe(false)
    })

    it('validates OPEN_EVIDENCE with contextType whitelist', () => {
      expect(validateEmbedPayload('OPEN_EVIDENCE', { contextType: 'risk', patientId: 'p1' })).toBe(true)
      expect(validateEmbedPayload('OPEN_EVIDENCE', { contextType: 'invalid_type', patientId: 'p1' })).toBe(false)
      expect(validateEmbedPayload('OPEN_EVIDENCE', { contextType: 'risk' })).toBe(false) // missing patientId
    })

    it('validates OPEN_ALERT', () => {
      expect(validateEmbedPayload('OPEN_ALERT', { alertId: 'a1', patientId: 'p1' })).toBe(true)
      expect(validateEmbedPayload('OPEN_ALERT', { alertId: 'a1' })).toBe(false)
    })
  })

  describe('createHostMessage / createEmbedMessage', () => {
    it('creates valid host message', () => {
      const msg = createHostMessage('PATIENT_CONTEXT_CHANGED', { patientId: 'p1' })
      expect(msg.source).toBe('icu-alert-host')
      expect(msg.version).toBe('1.0')
      expect(msg.type).toBe('PATIENT_CONTEXT_CHANGED')
      expect(msg.requestId).toBeTruthy()
      expect(msg.timestamp).toBeGreaterThan(0)
      expect(msg.payload.patientId).toBe('p1')
    })

    it('creates valid embed message', () => {
      const msg = createEmbedMessage('EMBED_READY', { moduleKey: 'evidence' })
      expect(msg.source).toBe('icu-alert-embed')
      expect(msg.version).toBe('1.0')
      expect(msg.type).toBe('EMBED_READY')
      expect(msg.requestId).toBeTruthy()
      expect(msg.timestamp).toBeGreaterThan(0)
    })

    it('generates unique requestIds', () => {
      const msg1 = createHostMessage('HOST_READY', {})
      const msg2 = createHostMessage('HOST_READY', {})
      expect(msg1.requestId).not.toBe(msg2.requestId)
    })
  })
})
