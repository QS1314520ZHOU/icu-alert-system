import { describe, it, expect, beforeEach, afterEach } from 'vitest'

// Don't mock featureFlags — test the real implementation
import {
  canAccessPatientModule,
  isFeatureEnabled,
  isModuleRoleGuardEnabled,
} from '../config/featureFlags'

const GUARD_KEY = 'VITE_ENABLE_MODULE_ROLE_GUARD' as const
const originalGuardValue = import.meta.env[GUARD_KEY]

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

  describe('module with requiredRoles（严格模式 VITE_ENABLE_MODULE_ROLE_GUARD=true）', () => {
    beforeEach(() => {
      import.meta.env[GUARD_KEY] = 'true'
    })
    afterEach(() => {
      import.meta.env[GUARD_KEY] = originalGuardValue
    })

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

  describe('默认模式（角色开关关闭：所有角色可打开全部模块）', () => {
    beforeEach(() => {
      import.meta.env[GUARD_KEY] = 'false'
    })
    afterEach(() => {
      import.meta.env[GUARD_KEY] = originalGuardValue
    })

    it('should allow non-matching role when guard disabled', () => {
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor', 'director'],
      }, 'nurse')
      expect(result).toBe(true)
    })

    it('should allow non-matching role when env unset (default off)', () => {
      delete import.meta.env[GUARD_KEY]
      expect(isModuleRoleGuardEnabled()).toBe(false)
      const result = canAccessPatientModule('causal-inference', {
        requiredRoles: ['doctor', 'director'],
      }, 'nurse')
      expect(result).toBe(true)
    })

    it('featureFlag gating still applies when guard disabled', () => {
      delete import.meta.env[GUARD_KEY]
      const result = canAccessPatientModule('decision-assistants', {
        featureFlag: 'ai-decision-assistants',
        requiredRoles: ['doctor'],
      }, 'nurse')
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
      // ai-decision-assistants is disabled by default
      const result = canAccessPatientModule('decision-assistants', {
        featureFlag: 'ai-decision-assistants',
      }, 'doctor')
      expect(result).toBe(false)
    })
  })

  describe('module with both featureFlag and requiredRoles', () => {
    beforeEach(() => {
      import.meta.env[GUARD_KEY] = 'true'
    })
    afterEach(() => {
      import.meta.env[GUARD_KEY] = originalGuardValue
    })

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
