import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock sessionStorage
const sessionStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]) }),
  }
})()

Object.defineProperty(window, 'sessionStorage', {
  value: sessionStorageMock,
  writable: true,
})

import { usePatientContext } from '../stores/patientContext'

describe('Patient Context Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorageMock.clear()
    vi.clearAllMocks()
  })

  describe('syncFromRoute', () => {
    it('should extract patientId from route params', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { patientId: '123' },
        query: {},
      } as any)

      expect(store.activePatientId).toBe('123')
    })

    it('should fall back to params.id', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { id: '456' },
        query: {},
      } as any)

      expect(store.activePatientId).toBe('456')
    })

    it('should save patientId to sessionStorage', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { patientId: '789' },
        query: {},
      } as any)

      expect(sessionStorageMock.setItem).toHaveBeenCalledWith('icu_active_patient_id', '789')
    })

    it('should NOT store PHI in sessionStorage', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { patientId: '123' },
        query: {},
      } as any)

      // Only patientId should be stored
      const calls = sessionStorageMock.setItem.mock.calls
      for (const call of calls) {
        expect(call[0]).toBe('icu_active_patient_id')
        expect(call[1]).toMatch(/^\d+$/)  // Only numeric IDs
      }
    })

    it('should track moduleKey from route', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { patientId: '123', moduleKey: 'risk-prediction' },
        query: {},
      } as any)

      expect(store.lastModuleKey).toBe('risk-prediction')
    })
  })

  describe('restoreFromSession', () => {
    it('should restore patientId from sessionStorage', () => {
      sessionStorageMock.getItem.mockReturnValueOnce('999')
      const store = usePatientContext()
      store.restoreFromSession()

      expect(store.activePatientId).toBe('999')
    })

    it('should handle missing sessionStorage gracefully', () => {
      sessionStorageMock.getItem.mockReturnValueOnce(null)
      const store = usePatientContext()
      store.restoreFromSession()

      expect(store.activePatientId).toBe('')
    })
  })

  describe('clearContext', () => {
    it('should clear all patient context', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { patientId: '123', moduleKey: 'risk-prediction' },
        query: {},
      } as any)
      store.clearContext()

      expect(store.activePatientId).toBe('')
      expect(store.lastModuleKey).toBe('')
      expect(store.patientSnapshot).toBeNull()
    })

    it('should remove sessionStorage entry', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { patientId: '123' },
        query: {},
      } as any)
      store.clearContext()

      expect(sessionStorageMock.removeItem).toHaveBeenCalledWith('icu_active_patient_id')
    })
  })

  describe('hasPatient', () => {
    it('should be false when no patient is set', () => {
      const store = usePatientContext()
      expect(store.hasPatient).toBe(false)
    })

    it('should be true when patient is set', () => {
      const store = usePatientContext()
      store.syncFromRoute({
        params: { patientId: '123' },
        query: {},
      } as any)
      expect(store.hasPatient).toBe(true)
    })
  })

  describe('setOriginRoute', () => {
    it('should record origin route', () => {
      const store = usePatientContext()
      store.setOriginRoute('/patients?dept_code=ICU')
      expect(store.originRoute).toBe('/patients?dept_code=ICU')
    })

    it('should not record patient routes as origin', () => {
      const store = usePatientContext()
      store.setOriginRoute('/patient/123/overview')
      expect(store.originRoute).toBe('')
    })
  })
})
