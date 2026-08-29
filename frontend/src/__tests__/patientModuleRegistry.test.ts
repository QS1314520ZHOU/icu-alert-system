import { describe, it, expect } from 'vitest'
import {
  MODULE_GROUPS,
  getModuleByKey,
  getModuleRenderMode,
  isIframeModule,
  getModuleRoute,
  getIframeUrl,
} from '../config/patientModuleRegistry'

describe('patientModuleRegistry', () => {
  describe('getModuleByKey', () => {
    it('finds existing modules', () => {
      expect(getModuleByKey('overview')).toBeDefined()
      expect(getModuleByKey('overview')?.title).toBe('病情总览')
    })

    it('returns undefined for unknown key', () => {
      expect(getModuleByKey('nonexistent')).toBeUndefined()
    })
  })

  describe('renderMode', () => {
    it('documents is native', () => {
      expect(getModuleRenderMode('documents')).toBe('native')
    })

    it('followup is native', () => {
      expect(getModuleRenderMode('followup')).toBe('native')
    })

    it('overview is native (no iframeUrl)', () => {
      expect(getModuleRenderMode('overview')).toBe('native')
    })

    it('risk-prediction is embed', () => {
      expect(getModuleRenderMode('risk-prediction')).toBe('embed')
    })

    it('evidence is embed', () => {
      expect(getModuleRenderMode('evidence')).toBe('embed')
    })

    it('unknown module defaults to native', () => {
      expect(getModuleRenderMode('nonexistent')).toBe('native')
    })
  })

  describe('isIframeModule', () => {
    it('documents is NOT an iframe module', () => {
      expect(isIframeModule('documents')).toBe(false)
    })

    it('followup is NOT an iframe module', () => {
      expect(isIframeModule('followup')).toBe(false)
    })

    it('risk-prediction IS an iframe module', () => {
      expect(isIframeModule('risk-prediction')).toBe(true)
    })

    it('overview is NOT an iframe module', () => {
      expect(isIframeModule('overview')).toBe(false)
    })
  })

  describe('documents module config', () => {
    it('has native route', () => {
      const mod = getModuleByKey('documents')
      expect(mod?.route).toBe('/patient/:patientId/documents')
    })

    it('has empty iframeUrl', () => {
      const mod = getModuleByKey('documents')
      expect(mod?.iframeUrl('any-id')).toBe('')
    })

    it('has renderMode native', () => {
      const mod = getModuleByKey('documents')
      expect(mod?.renderMode).toBe('native')
    })
  })

  describe('followup module config', () => {
    it('has native route', () => {
      const mod = getModuleByKey('followup')
      expect(mod?.route).toBe('/patient/:patientId/followup')
    })

    it('has empty iframeUrl', () => {
      const mod = getModuleByKey('followup')
      expect(mod?.iframeUrl('any-id')).toBe('')
    })

    it('has renderMode native', () => {
      const mod = getModuleByKey('followup')
      expect(mod?.renderMode).toBe('native')
    })
  })

  describe('MODULE_GROUPS', () => {
    it('each moduleKey appears only once across all groups', () => {
      const allKeys: string[] = []
      for (const group of MODULE_GROUPS) {
        for (const mod of group.modules) {
          allKeys.push(mod.moduleKey)
        }
      }
      const uniqueKeys = new Set(allKeys)
      expect(allKeys.length).toBe(uniqueKeys.size)
    })

    it('has all required groups', () => {
      const groupKeys = MODULE_GROUPS.map(g => g.key)
      expect(groupKeys).toContain('patient-detail')
      expect(groupKeys).toContain('alert-decision')
      expect(groupKeys).toContain('ai-analysis')
      expect(groupKeys).toContain('clinical-docs')
      expect(groupKeys).toContain('followup')
    })
  })

  describe('getModuleRoute', () => {
    it('returns correct route for documents', () => {
      expect(getModuleRoute('documents', 'p123')).toBe('/patient/p123/documents')
    })

    it('returns correct route for followup', () => {
      expect(getModuleRoute('followup', 'p123')).toBe('/patient/p123/followup')
    })

    it('returns overview route for unknown module', () => {
      expect(getModuleRoute('nonexistent', 'p123')).toBe('/patient/p123/overview')
    })
  })

  describe('getIframeUrl', () => {
    it('returns empty for native modules', () => {
      expect(getIframeUrl('documents', 'p123')).toBe('')
      expect(getIframeUrl('followup', 'p123')).toBe('')
      expect(getIframeUrl('overview', 'p123')).toBe('')
    })

    it('returns correct url for embed modules', () => {
      expect(getIframeUrl('risk-prediction', 'p123')).toBe('/embed/patient/p123/risk-prediction')
    })
  })
})
