import { describe, it, expect } from 'vitest'
import {
  createHostMessage,
  createEmbedMessage,
  isValidMessage,
  isHostMessage,
  isEmbedMessage,
  generateRequestId,
  HOST_MESSAGE_TYPES,
  EMBED_MESSAGE_TYPES,
  ALLOWED_SOURCES,
  PROTOCOL_VERSION,
} from '../config/postMessageProtocol'

describe('PostMessage Protocol', () => {
  describe('generateRequestId', () => {
    it('should generate unique request IDs', () => {
      const id1 = generateRequestId()
      const id2 = generateRequestId()
      expect(id1).not.toBe(id2)
      expect(id1).toMatch(/^req_\d+_\d+$/)
    })
  })

  describe('createHostMessage', () => {
    it('should create a valid host message', () => {
      const msg = createHostMessage('HOST_READY', { moduleKey: 'test', patientId: 'p1' })
      expect(msg.source).toBe('icu-alert-host')
      expect(msg.version).toBe(PROTOCOL_VERSION)
      expect(msg.type).toBe('HOST_READY')
      expect(msg.requestId).toBeTruthy()
      expect(msg.timestamp).toBeGreaterThan(0)
      expect(msg.payload).toEqual({ moduleKey: 'test', patientId: 'p1' })
    })

    it('should create PATIENT_CONTEXT_CHANGED message', () => {
      const msg = createHostMessage('PATIENT_CONTEXT_CHANGED', { patientId: 'p123' })
      expect(msg.type).toBe('PATIENT_CONTEXT_CHANGED')
      expect(msg.payload.patientId).toBe('p123')
    })

    it('should create THEME_CHANGED message', () => {
      const msg = createHostMessage('THEME_CHANGED', { mode: 'dark' })
      expect(msg.type).toBe('THEME_CHANGED')
      expect(msg.payload.mode).toBe('dark')
    })
  })

  describe('createEmbedMessage', () => {
    it('should create a valid embed message', () => {
      const msg = createEmbedMessage('EMBED_READY', { moduleKey: 'risk-prediction' })
      expect(msg.source).toBe('icu-alert-embed')
      expect(msg.version).toBe(PROTOCOL_VERSION)
      expect(msg.type).toBe('EMBED_READY')
      expect(msg.requestId).toBeTruthy()
      expect(msg.timestamp).toBeGreaterThan(0)
    })

    it('should create NAVIGATE_MODULE message', () => {
      const msg = createEmbedMessage('NAVIGATE_MODULE', { moduleKey: 'similar-cases', patientId: 'p1' })
      expect(msg.type).toBe('NAVIGATE_MODULE')
      expect(msg.payload.moduleKey).toBe('similar-cases')
    })

    it('should create REPORT_ERROR message', () => {
      const msg = createEmbedMessage('REPORT_ERROR', { code: 'LOAD_FAILED', message: 'test error' })
      expect(msg.type).toBe('REPORT_ERROR')
      expect(msg.payload.code).toBe('LOAD_FAILED')
    })

    it('should create RESIZE message', () => {
      const msg = createEmbedMessage('RESIZE', { height: 800 })
      expect(msg.type).toBe('RESIZE')
      expect(msg.payload.height).toBe(800)
    })
  })

  describe('isValidMessage', () => {
    it('should return true for valid host message', () => {
      const msg = createHostMessage('HOST_READY', {})
      expect(isValidMessage(msg)).toBe(true)
    })

    it('should return true for valid embed message', () => {
      const msg = createEmbedMessage('EMBED_READY', {})
      expect(isValidMessage(msg)).toBe(true)
    })

    it('should return false for null', () => {
      expect(isValidMessage(null)).toBe(false)
    })

    it('should return false for undefined', () => {
      expect(isValidMessage(undefined)).toBe(false)
    })

    it('should return false for empty object', () => {
      expect(isValidMessage({})).toBe(false)
    })

    it('should return false for invalid source', () => {
      expect(isValidMessage({ source: 'invalid', version: '1.0', type: 'TEST' })).toBe(false)
    })

    it('should return false for invalid version', () => {
      expect(isValidMessage({ source: 'icu-alert-host', version: '2.0', type: 'TEST' })).toBe(false)
    })

    it('should return false for missing type', () => {
      expect(isValidMessage({ source: 'icu-alert-host', version: '1.0' })).toBe(false)
    })
  })

  describe('isHostMessage', () => {
    it('should return true for host messages', () => {
      const msg = createHostMessage('HOST_READY', {})
      expect(isHostMessage(msg)).toBe(true)
    })

    it('should return false for embed messages', () => {
      const msg = createEmbedMessage('EMBED_READY', {})
      expect(isHostMessage(msg)).toBe(false)
    })

    it('should return false for invalid data', () => {
      expect(isHostMessage(null)).toBe(false)
      expect(isHostMessage({})).toBe(false)
    })
  })

  describe('isEmbedMessage', () => {
    it('should return true for embed messages', () => {
      const msg = createEmbedMessage('EMBED_READY', {})
      expect(isEmbedMessage(msg)).toBe(true)
    })

    it('should return false for host messages', () => {
      const msg = createHostMessage('HOST_READY', {})
      expect(isEmbedMessage(msg)).toBe(false)
    })

    it('should return false for invalid data', () => {
      expect(isEmbedMessage(null)).toBe(false)
      expect(isEmbedMessage({})).toBe(false)
    })
  })

  describe('Message types coverage', () => {
    it('should have all host message types', () => {
      expect(HOST_MESSAGE_TYPES.HOST_READY).toBe('HOST_READY')
      expect(HOST_MESSAGE_TYPES.PATIENT_CONTEXT_CHANGED).toBe('PATIENT_CONTEXT_CHANGED')
      expect(HOST_MESSAGE_TYPES.THEME_CHANGED).toBe('THEME_CHANGED')
      expect(HOST_MESSAGE_TYPES.LOCALE_CHANGED).toBe('LOCALE_CHANGED')
      expect(HOST_MESSAGE_TYPES.PERMISSION_CHANGED).toBe('PERMISSION_CHANGED')
      expect(HOST_MESSAGE_TYPES.REFRESH_MODULE).toBe('REFRESH_MODULE')
      expect(HOST_MESSAGE_TYPES.ROUTE_ACTIVATED).toBe('ROUTE_ACTIVATED')
    })

    it('should have all embed message types', () => {
      expect(EMBED_MESSAGE_TYPES.EMBED_READY).toBe('EMBED_READY')
      expect(EMBED_MESSAGE_TYPES.NAVIGATE_MODULE).toBe('NAVIGATE_MODULE')
      expect(EMBED_MESSAGE_TYPES.NAVIGATE_PATIENT).toBe('NAVIGATE_PATIENT')
      expect(EMBED_MESSAGE_TYPES.OPEN_PATIENT_DETAIL).toBe('OPEN_PATIENT_DETAIL')
      expect(EMBED_MESSAGE_TYPES.UPDATE_TITLE).toBe('UPDATE_TITLE')
      expect(EMBED_MESSAGE_TYPES.UPDATE_BREADCRUMB).toBe('UPDATE_BREADCRUMB')
      expect(EMBED_MESSAGE_TYPES.SET_DIRTY_STATE).toBe('SET_DIRTY_STATE')
      expect(EMBED_MESSAGE_TYPES.REQUEST_FULLSCREEN).toBe('REQUEST_FULLSCREEN')
      expect(EMBED_MESSAGE_TYPES.EXIT_FULLSCREEN).toBe('EXIT_FULLSCREEN')
      expect(EMBED_MESSAGE_TYPES.SHOW_NOTIFICATION).toBe('SHOW_NOTIFICATION')
      expect(EMBED_MESSAGE_TYPES.REPORT_ERROR).toBe('REPORT_ERROR')
      expect(EMBED_MESSAGE_TYPES.RESIZE).toBe('RESIZE')
    })
  })

  describe('ALLOWED_SOURCES', () => {
    it('should contain host and embed sources', () => {
      expect(ALLOWED_SOURCES).toContain('icu-alert-host')
      expect(ALLOWED_SOURCES).toContain('icu-alert-embed')
    })
  })
})
