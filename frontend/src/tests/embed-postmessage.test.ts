import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/**
 * Tests for the embed.html PostMessage protocol.
 *
 * The embed.html file defines a message event listener that handles:
 * - { type: 'SmartCareNavigate', page: '...' }
 * - { type: 'SmartCareNavigate', payload: { page: '...' } }
 *
 * It maps page keys to URL paths via PAGE_MAP.
 */

// Simulate the PAGE_MAP from embed.html
const PAGE_MAP: Record<string, string> = {
  // Patient workbench
  'patient-overview': '/patient-detail/overview',
  'patient-lab': '/patient-detail/lab',
  'patient-orders': '/patient-detail/orders',
  'patient-monitors': '/patient-detail/monitors',
  'patient-nursing': '/patient-detail/nursing',
  'patient-score': '/patient-detail/score',
  'patient-events': '/patient-detail/events',
  'patient-intelligence': '/patient-detail/intelligence',
  'patient-followup': '/patient-detail/followup',
  // Disease center
  'disease-ai': '/disease/ai',
  'disease-center': '/disease',
  // Handover center
  'handover-center': '/handover',
  'handover-overview': '/handover/overview',
  'handover-isbar': '/handover/patients',
  'handover-tasks': '/handover/tasks',
  'handover-history': '/handover/history',
}

describe('Embed PostMessage Protocol', () => {
  describe('PAGE_MAP coverage', () => {
    it('should include all 7 patient workbench tabs', () => {
      const patientTabs = Object.keys(PAGE_MAP).filter(k => k.startsWith('patient-'))
      expect(patientTabs.length).toBeGreaterThanOrEqual(7)
      expect(patientTabs).toContain('patient-overview')
      expect(patientTabs).toContain('patient-lab')
      expect(patientTabs).toContain('patient-orders')
      expect(patientTabs).toContain('patient-monitors')
      expect(patientTabs).toContain('patient-nursing')
      expect(patientTabs).toContain('patient-score')
      expect(patientTabs).toContain('patient-events')
    })

    it('should include disease center pages', () => {
      expect(PAGE_MAP).toHaveProperty('disease-ai')
      expect(PAGE_MAP).toHaveProperty('disease-center')
    })

    it('should include handover center pages', () => {
      expect(PAGE_MAP).toHaveProperty('handover-center')
      expect(PAGE_MAP).toHaveProperty('handover-overview')
      expect(PAGE_MAP).toHaveProperty('handover-isbar')
    })
  })

  describe('Message parsing', () => {
    function parseNavigateMessage(data: any): string | null {
      if (!data) return null
      if (data.type === 'SmartCareNavigate') {
        const page = data.page || data?.payload?.page
        if (page && PAGE_MAP[page]) {
          return PAGE_MAP[page]
        }
      }
      return null
    }

    it('should parse { type, page } format', () => {
      const result = parseNavigateMessage({
        type: 'SmartCareNavigate',
        page: 'handover-overview',
      })
      expect(result).toBe('/handover/overview')
    })

    it('should parse { type, payload: { page } } format', () => {
      const result = parseNavigateMessage({
        type: 'SmartCareNavigate',
        payload: { page: 'patient-lab' },
      })
      expect(result).toBe('/patient-detail/lab')
    })

    it('should return null for unknown page', () => {
      const result = parseNavigateMessage({
        type: 'SmartCareNavigate',
        page: 'nonexistent-page',
      })
      expect(result).toBeNull()
    })

    it('should return null for non-navigate messages', () => {
      const result = parseNavigateMessage({
        type: 'OtherMessage',
        page: 'handover-overview',
      })
      expect(result).toBeNull()
    })

    it('should return null for null data', () => {
      expect(parseNavigateMessage(null)).toBeNull()
      expect(parseNavigateMessage(undefined)).toBeNull()
    })
  })

  describe('URL building', () => {
    function buildUrl(base: string, path: string, token?: string): string {
      const cleanBase = base.replace(/\/+$/, '')
      const cleanPath = path.replace(/^\/+/, '')
      let url = `${cleanBase}/${cleanPath}`
      if (token) {
        const sep = url.includes('?') ? '&' : '?'
        url += `${sep}__sc_token=${encodeURIComponent(token)}`
      }
      return url
    }

    it('should build URL with base and path', () => {
      const result = buildUrl('http://localhost:5173', '/handover/overview')
      expect(result).toBe('http://localhost:5173/handover/overview')
    })

    it('should strip trailing slashes from base', () => {
      const result = buildUrl('http://localhost:5173/', '/handover/overview')
      expect(result).toBe('http://localhost:5173/handover/overview')
    })

    it('should append token as query parameter', () => {
      const result = buildUrl('http://localhost:5173', '/handover', 'test-token-123')
      expect(result).toBe('http://localhost:5173/handover?__sc_token=test-token-123')
    })

    it('should use & separator when URL already has query params', () => {
      const result = buildUrl('http://localhost:5173', '/handover?foo=bar', 'token')
      expect(result).toBe('http://localhost:5173/handover?foo=bar&__sc_token=token')
    })

    it('should encode special characters in token', () => {
      const result = buildUrl('http://localhost:5173', '/handover', 'token with spaces')
      expect(result).toContain('__sc_token=token%20with%20spaces')
    })
  })
})
