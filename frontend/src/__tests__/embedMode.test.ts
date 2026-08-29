import { describe, it, expect } from 'vitest'

/**
 * Embed Mode Tests
 *
 * Verifies the architectural rules for embed vs native modules.
 */

import {
  PATIENT_MODULES,
  getModuleByKey,
  getModuleRenderMode,
  isIframeModule,
} from '../config/patientModuleRegistry'

describe('Embed Mode Architecture', () => {
  describe('native modules', () => {
    const nativeModules = ['overview', 'monitoring', 'treatment', 'alerts', 'documents', 'followup']

    for (const key of nativeModules) {
      it(`"${key}" is native (not iframe)`, () => {
        expect(isIframeModule(key)).toBe(false)
        expect(getModuleRenderMode(key)).toBe('native')
      })
    }
  })

  describe('embed modules', () => {
    const embedModules = [
      'risk-prediction', 'similar-cases', 'causal-inference',
      'what-if', 'integrated-risk', 'disease-trajectory',
      'evidence', 'decision-assistants',
    ]

    for (const key of embedModules) {
      it(`"${key}" is embed (iframe)`, () => {
        expect(isIframeModule(key)).toBe(true)
        expect(getModuleRenderMode(key)).toBe('embed')
      })
    }
  })

  describe('documents and followup native routing', () => {
    it('documents route points to native path', () => {
      const mod = getModuleByKey('documents')
      expect(mod?.route).toContain('/patient/:patientId/documents')
      expect(mod?.route).not.toContain('/tool/')
    })

    it('followup route points to native path', () => {
      const mod = getModuleByKey('followup')
      expect(mod?.route).toContain('/patient/:patientId/followup')
      expect(mod?.route).not.toContain('/tool/')
    })

    it('documents has empty iframeUrl', () => {
      const mod = getModuleByKey('documents')
      expect(mod?.iframeUrl('any')).toBe('')
    })

    it('followup has empty iframeUrl', () => {
      const mod = getModuleByKey('followup')
      expect(mod?.iframeUrl('any')).toBe('')
    })
  })

  describe('no duplicate moduleKeys', () => {
    it('all moduleKeys are unique', () => {
      const keys = PATIENT_MODULES.map(m => m.moduleKey)
      const uniqueKeys = new Set(keys)
      expect(keys.length).toBe(uniqueKeys.size)
    })
  })

  describe('embed modules have valid iframeUrl', () => {
    const embedModules = PATIENT_MODULES.filter(m => getModuleRenderMode(m.moduleKey) === 'embed')

    for (const mod of embedModules) {
      it(`"${mod.moduleKey}" has iframeUrl starting with /embed/`, () => {
        const url = mod.iframeUrl('test-patient-id')
        expect(url).toContain('/embed/patient/')
        expect(url).toContain('test-patient-id')
      })
    }
  })
})
