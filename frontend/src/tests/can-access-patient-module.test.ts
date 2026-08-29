import { describe, it, expect, vi, beforeEach } from 'vitest'

// Don't mock featureFlags — test the real implementation
import { canAccessPatientModule, isFeatureEnabled, FEATURE_FLAGS } from '../config/featureFlags'

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

    it('should deny access when role is empty', () => {
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor'],
      }, '')
      expect(result).toBe(false)
    })

    it('should deny access when role is undefined', () => {
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor'],
      }, undefined)
      expect(result).toBe(false)
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
      // ai-causal-inference is disabled by default
      const result = canAccessPatientModule('causal-inference', {
        featureFlag: 'ai-causal-inference',
      }, 'doctor')
      expect(result).toBe(false)
    })
  })

  describe('module with both featureFlag and requiredRoles', () => {
    it('should deny when feature flag is disabled even if role matches', () => {
      const result = canAccessPatientModule('causal-inference', {
        featureFlag: 'ai-causal-inference',
        requiredRoles: ['doctor'],
      }, 'doctor')
      // Feature flag disabled → denied
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
    expect(isFeatureEnabled('ai-causal-inference')).toBe(false)
    expect(isFeatureEnabled('ai-what-if')).toBe(false)
    expect(isFeatureEnabled('ai-decision-assistants')).toBe(false)
  })

  it('should return true for enabled flags', () => {
    expect(isFeatureEnabled('ai-disease-trajectory')).toBe(true)
  })

  it('should return false for unknown flags', () => {
    expect(isFeatureEnabled('nonexistent-flag')).toBe(false)
  })
})
