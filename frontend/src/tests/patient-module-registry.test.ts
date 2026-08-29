import { describe, it, expect } from 'vitest'
import {
  PATIENT_MODULES,
  MODULE_GROUPS,
  getModuleByKey,
  isIframeModule,
  getModuleRoute,
  getIframeUrl,
} from '../config/patientModuleRegistry'

describe('Patient Module Registry', () => {
  describe('PATIENT_MODULES', () => {
    it('should have at least 12 modules', () => {
      expect(PATIENT_MODULES.length).toBeGreaterThanOrEqual(12)
    })

    it('should have unique moduleKeys', () => {
      const keys = PATIENT_MODULES.map(m => m.moduleKey)
      const unique = new Set(keys)
      expect(unique.size).toBe(keys.length)
    })

    it('should include all required modules', () => {
      const keys = PATIENT_MODULES.map(m => m.moduleKey)
      expect(keys).toContain('overview')
      expect(keys).toContain('monitoring')
      expect(keys).toContain('treatment')
      expect(keys).toContain('alerts')
      expect(keys).toContain('risk-prediction')
      expect(keys).toContain('integrated-risk')
      expect(keys).toContain('similar-cases')
      expect(keys).toContain('causal-inference')
      expect(keys).toContain('what-if')
      expect(keys).toContain('disease-trajectory')
      expect(keys).toContain('evidence')
      expect(keys).toContain('documents')
      expect(keys).toContain('followup')
      expect(keys).toContain('decision-assistants')
    })

    it('each module should have required fields', () => {
      for (const mod of PATIENT_MODULES) {
        expect(mod.moduleKey).toBeTruthy()
        expect(mod.title).toBeTruthy()
        expect(mod.icon).toBeTruthy()
        expect(mod.group).toBeTruthy()
        expect(mod.route).toBeTruthy()
        expect(typeof mod.iframeUrl).toBe('function')
      }
    })
  })

  describe('MODULE_GROUPS', () => {
    it('should have 5 groups', () => {
      expect(MODULE_GROUPS.length).toBe(5)
    })

    it('should have unique group keys', () => {
      const keys = MODULE_GROUPS.map(g => g.key)
      const unique = new Set(keys)
      expect(unique.size).toBe(keys.length)
    })

    it('each group should have at least one module', () => {
      for (const group of MODULE_GROUPS) {
        expect(group.modules.length).toBeGreaterThan(0)
      }
    })

    it('should include patient-detail group', () => {
      const group = MODULE_GROUPS.find(g => g.key === 'patient-detail')
      expect(group).toBeTruthy()
      expect(group!.modules.length).toBeGreaterThanOrEqual(3)
    })

    it('should include alert-decision group', () => {
      const group = MODULE_GROUPS.find(g => g.key === 'alert-decision')
      expect(group).toBeTruthy()
      expect(group!.modules.length).toBeGreaterThanOrEqual(3)
    })

    it('should include ai-analysis group', () => {
      const group = MODULE_GROUPS.find(g => g.key === 'ai-analysis')
      expect(group).toBeTruthy()
      expect(group!.modules.length).toBeGreaterThanOrEqual(4)
    })
  })

  describe('getModuleByKey', () => {
    it('should return module for valid key', () => {
      const mod = getModuleByKey('risk-prediction')
      expect(mod).toBeTruthy()
      expect(mod!.title).toBe('风险预测')
    })

    it('should return undefined for invalid key', () => {
      expect(getModuleByKey('nonexistent')).toBeUndefined()
    })
  })

  describe('isIframeModule', () => {
    it('should return true for iframe modules', () => {
      expect(isIframeModule('risk-prediction')).toBe(true)
      expect(isIframeModule('similar-cases')).toBe(true)
      expect(isIframeModule('causal-inference')).toBe(true)
    })

    it('should return false for native modules', () => {
      expect(isIframeModule('overview')).toBe(false)
      expect(isIframeModule('monitoring')).toBe(false)
      expect(isIframeModule('treatment')).toBe(false)
    })
  })

  describe('getModuleRoute', () => {
    it('should return correct route for valid module', () => {
      const route = getModuleRoute('risk-prediction', 'p123')
      expect(route).toBe('/patient/p123/tool/risk-prediction')
    })

    it('should return overview route for invalid module', () => {
      const route = getModuleRoute('nonexistent', 'p123')
      expect(route).toBe('/patient/p123/overview')
    })
  })

  describe('getIframeUrl', () => {
    it('should return correct iframe URL', () => {
      const url = getIframeUrl('risk-prediction', 'p123')
      expect(url).toBe('/embed/patient/p123/risk-prediction')
    })

    it('should return empty string for native modules', () => {
      const url = getIframeUrl('overview', 'p123')
      expect(url).toBe('')
    })
  })
})
