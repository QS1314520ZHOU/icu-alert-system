import { describe, it, expect } from 'vitest'

// Don't mock featureFlags — test the real implementation
import { canAccessPatientModule, isFeatureEnabled } from '../config/featureFlags'

describe('canAccessPatientModule', () => {
  describe('module with no restrictions', () => {
    it('should allow access when no featureFlag or requiredRoles', () => {
      const result = canAccessPatientModule('overview', {}, 'doctor')
      expect(result).toBe(true)
    })

    it('should allow access with undefined config', () => {
      const result = canAccessPatientModule('overview', undefined, 'nurse')
      expect(result).toBe(true)
    })
  })

  describe('module with requiredRoles', () => {
    it('should allow access for matching role', () => {
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor', 'director'],
      }, 'doctor')
      expect(result).toBe(true)
    })

    it('should deny access for non-matching role', () => {
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor', 'director'],
      }, 'nurse')
      expect(result).toBe(false)
    })

    it('should allow access when role is empty (dev mode)', () => {
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor'],
      }, '')
      expect(result).toBe(true)
    })

    it('should allow access when role is undefined (dev mode)', () => {
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor'],
      }, undefined)
      expect(result).toBe(true)
    })
  })

  describe('module with featureFlag', () => {
    it('should allow access when feature flag is enabled', () => {
      // ai-risk-prediction is enabled by default
      const result = canAccessPatientModule('risk-prediction', {
        featureFlag: 'ai-risk-prediction',
      }, 'doctor')
      expect(result).toBe(true)
    })

    it('should deny access when feature flag is disabled', () => {
      // ai-decision-assistants is disabled by default
      const result = canAccessPatientModule('decision-assistants', {
        featureFlag: 'ai-decision-assistants',
      }, 'doctor')
      expect(result).toBe(false)
    })
  })

  describe('module with both featureFlag and requiredRoles', () => {
    it('should deny when feature flag is disabled even if role matches', () => {
      const result = canAccessPatientModule('decision-assistants', {
        featureFlag: 'ai-decision-assistants',
        requiredRoles: ['doctor'],
      }, 'doctor')
      expect(result).toBe(false)
    })
  })
})

describe('isFeatureEnabled', () => {
  it('should return true for enabled flags', () => {
    expect(isFeatureEnabled('ai-risk-prediction')).toBe(true)
    expect(isFeatureEnabled('ai-similar-cases')).toBe(true)
    expect(isFeatureEnabled('ai-evidence')).toBe(true)
  })

  it('should return false for disabled flags', () => {
    expect(isFeatureEnabled('ai-decision-assistants')).toBe(false)
  })

  it('should return true for enabled flags', () => {
    expect(isFeatureEnabled('ai-disease-trajectory')).toBe(true)
  })

  it('should return false for unknown flags', () => {
    expect(isFeatureEnabled('nonexistent-flag')).toBe(false)
  })
})
