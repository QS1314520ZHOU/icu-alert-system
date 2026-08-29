import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

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

describe('Auth Store — hydrateFromQuery fixes', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
  })

  describe('dept_code preservation', () => {
    it('should NOT clear deptCode when URL lacks dept_code', () => {
      const store = useAuthStore()
      store.deptCode = 'ICU01'
      store.dept = 'ICU'

      store.hydrateFromQuery({})

      expect(store.deptCode).toBe('ICU01')
      expect(store.dept).toBe('ICU')
    })

    it('should accept dept_code from URL when present', () => {
      const store = useAuthStore()
      store.deptCode = 'ICU01'

      store.hydrateFromQuery({ dept_code: 'SICU02' })

      expect(store.deptCode).toBe('SICU02')
    })

    it('should accept legacy deptCode param', () => {
      const store = useAuthStore()

      store.hydrateFromQuery({ deptCode: 'NICU03' })

      expect(store.deptCode).toBe('NICU03')
    })
  })

  describe('identity preservation', () => {
    it('should NOT overwrite existing identity from URL', () => {
      const store = useAuthStore()
      store.userId = 'session_user'
      store.userName = 'Session User'

      store.hydrateFromQuery({ userId: 'url_user', userName: 'URL User' })

      // Identity should NOT be overwritten since session already has one
      expect(store.userId).toBe('session_user')
      expect(store.userName).toBe('Session User')
    })

    it('should set identity from URL when no session identity exists', () => {
      const store = useAuthStore()

      store.hydrateFromQuery({ userId: 'new_user', userName: 'New User' })

      expect(store.userId).toBe('new_user')
      expect(store.userName).toBe('New User')
    })

    it('should NOT clear role when URL lacks role param', () => {
      const store = useAuthStore()
      store.role = 'nurse'

      store.hydrateFromQuery({})

      expect(store.role).toBe('nurse')
    })

    it('should accept role from URL when present', () => {
      const store = useAuthStore()
      store.role = 'nurse'

      store.hydrateFromQuery({ role: 'doctor' })

      expect(store.role).toBe('doctor')
    })
  })

  describe('updateAccount', () => {
    it('should update all fields from account object', () => {
      const store = useAuthStore()
      store.updateAccount({
        user_id: 'acc001',
        userName: 'Account User',
        role: 'doctor',
        dept: 'SICU',
        dept_code: 'SICU01',
      })

      expect(store.userId).toBe('acc001')
      expect(store.userName).toBe('Account User')
      expect(store.role).toBe('doctor')
      expect(store.dept).toBe('SICU')
      expect(store.deptCode).toBe('SICU01')
    })
  })
})
