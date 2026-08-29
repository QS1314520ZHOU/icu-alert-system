import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock the API module
vi.mock('../api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  API_BASE: '/api',
  AI_API_BASE: '/ai',
}))

import { useAuthStore } from '../stores/auth'

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Clear localStorage between tests
    window.localStorage.clear()
  })

  describe('effectiveUserId', () => {
    it('should return userId when set', () => {
      const store = useAuthStore()
      store.userId = 'nurse001'
      store.userName = '张护士'

      expect(store.effectiveUserId).toBe('nurse001')
    })

    it('should fall back to userName when userId is empty', () => {
      const store = useAuthStore()
      store.userId = ''
      store.userName = '张护士'

      expect(store.effectiveUserId).toBe('张护士')
    })

    it('should return empty string when both are empty', () => {
      const store = useAuthStore()
      store.userId = ''
      store.userName = ''

      // effectiveUserId falls back to getOperatorIdentity() from localStorage
      expect(store.effectiveUserId).toBe('')
    })
  })

  describe('hydrateFromQuery', () => {
    it('should extract userId from URL query parameters (LocationQuery format)', () => {
      const store = useAuthStore()

      // LocationQuery is Record<string, string | string[]>
      store.hydrateFromQuery({
        userId: 'nurse001',
        userName: '张护士',
        dept: 'ICU',
        deptCode: 'ICU01',
      })

      expect(store.userId).toBe('nurse001')
      expect(store.userName).toBe('张护士')
      expect(store.dept).toBe('ICU')
      expect(store.deptCode).toBe('ICU01')
    })

    it('should handle array values in LocationQuery', () => {
      const store = useAuthStore()

      store.hydrateFromQuery({
        userId: ['nurse001', 'other'],
      })

      expect(store.userId).toBe('nurse001')
    })

    it('should not overwrite with empty strings', () => {
      const store = useAuthStore()
      store.userId = 'existing'

      store.hydrateFromQuery({})

      expect(store.userId).toBe('existing')
    })
  })

  describe('updateAccount', () => {
    it('should update all account fields', () => {
      const store = useAuthStore()
      store.updateAccount({
        userId: 'nurse002',
        userName: '李护士',
        role: 'nurse',
        dept: '外科ICU',
        deptCode: 'SICU01',
      })

      expect(store.userId).toBe('nurse002')
      expect(store.userName).toBe('李护士')
      expect(store.role).toBe('nurse')
      expect(store.dept).toBe('外科ICU')
      expect(store.deptCode).toBe('SICU01')
    })

    it('should use user_id fallback', () => {
      const store = useAuthStore()
      store.updateAccount({ user_id: 'from_his' })

      expect(store.userId).toBe('from_his')
    })

    it('should preserve existing values when fields not provided', () => {
      const store = useAuthStore()
      store.userId = 'existing'
      store.userName = 'existing_name'

      store.updateAccount({})

      expect(store.userId).toBe('existing')
      expect(store.userName).toBe('existing_name')
    })
  })
})
