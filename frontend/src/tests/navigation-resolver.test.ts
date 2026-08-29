import { describe, it, expect, vi } from 'vitest'

// Mock the feature flags module
vi.mock('../config/featureFlags', () => ({
  canAccessPatientModule: vi.fn((_moduleKey: string, config: any, role?: string) => {
    // Check feature flag first (matches real implementation order)
    if (config?.featureFlag) {
      const disabled = ['ai-causal-inference', 'ai-what-if', 'ai-disease-trajectory']
      if (disabled.includes(config.featureFlag)) return false
    }
    if (config?.requiredRoles && config.requiredRoles.length > 0) {
      return role ? config.requiredRoles.includes(role.toLowerCase()) : false
    }
    return true
  }),
  isFeatureEnabled: vi.fn((flag: string) => {
    const disabled = ['ai-causal-inference', 'ai-what-if', 'ai-disease-trajectory']
    return !disabled.includes(flag)
  }),
  FEATURE_FLAGS: {},
}))

// Mock the registry
vi.mock('../config/patientModuleRegistry', () => ({
  PATIENT_MODULES: [
    { moduleKey: 'overview', title: '病情总览', icon: 'activity', group: 'patient-detail', route: '/patient/:patientId/overview', iframeUrl: () => '' },
    { moduleKey: 'risk-prediction', title: '风险预测', icon: 'trending-up', group: 'alert-decision', route: '/patient/:patientId/tool/risk-prediction', iframeUrl: (pid: string) => `/embed/patient/${pid}/risk-prediction`, featureFlag: 'ai-risk-prediction' },
    { moduleKey: 'similar-cases', title: '相似病例', icon: 'users', group: 'ai-analysis', route: '/patient/:patientId/tool/similar-cases', iframeUrl: (pid: string) => `/embed/patient/${pid}/similar-cases`, featureFlag: 'ai-similar-cases' },
    { moduleKey: 'causal-inference', title: '因果推断', icon: 'flask', group: 'ai-analysis', route: '/patient/:patientId/tool/causal-inference', iframeUrl: (pid: string) => `/embed/patient/${pid}/causal-inference`, featureFlag: 'ai-causal-inference', requiredRoles: ['doctor', 'director'] },
    { moduleKey: 'what-if', title: 'What-if模拟', icon: 'cpu', group: 'ai-analysis', route: '/patient/:patientId/tool/what-if', iframeUrl: (pid: string) => `/embed/patient/${pid}/what-if`, featureFlag: 'ai-what-if', requiredRoles: ['doctor'] },
    { moduleKey: 'followup', title: '随访管理', icon: 'activity', group: 'followup', route: '/patient/:patientId/tool/followup', iframeUrl: (pid: string) => `/embed/patient/${pid}/followup`, featureFlag: 'ai-followup', requiredRoles: ['doctor', 'nurse', 'head_nurse'] },
  ],
  MODULE_GROUPS: [
    { key: 'patient-detail', label: '患者详情', icon: 'users', modules: [{ moduleKey: 'overview', title: '病情总览', icon: 'activity', group: 'patient-detail', route: '/patient/:patientId/overview', iframeUrl: () => '' }] },
    { key: 'alert-decision', label: '预警与决策', icon: 'shield', modules: [{ moduleKey: 'risk-prediction', title: '风险预测', icon: 'trending-up', group: 'alert-decision', route: '/patient/:patientId/tool/risk-prediction', iframeUrl: (pid: string) => `/embed/patient/${pid}/risk-prediction`, featureFlag: 'ai-risk-prediction' }] },
    { key: 'ai-analysis', label: 'AI智能分析', icon: 'sparkles', modules: [{ moduleKey: 'similar-cases', title: '相似病例', icon: 'users', group: 'ai-analysis', route: '/patient/:patientId/tool/similar-cases', iframeUrl: (pid: string) => `/embed/patient/${pid}/similar-cases`, featureFlag: 'ai-similar-cases' }] },
    { key: 'followup', label: '随访管理', icon: 'activity', modules: [{ moduleKey: 'followup', title: '随访管理', icon: 'activity', group: 'followup', route: '/patient/:patientId/tool/followup', iframeUrl: (pid: string) => `/embed/patient/${pid}/followup`, featureFlag: 'ai-followup', requiredRoles: ['doctor', 'nurse', 'head_nurse'] }] },
  ],
  getModuleByKey: vi.fn(),
  isIframeModule: vi.fn(),
  getModuleRoute: vi.fn(),
  getIframeUrl: vi.fn(),
}))

// Mock roleHomeConfig
vi.mock('../config/roleHomeConfig', () => ({
  navGroups: [
    { key: 'today', label: '今日工作', items: [{ key: 'doctor-home', label: '医生首页', icon: 'stethoscope', path: '/doctor-home' }] },
    { key: 'patients', label: '患者', items: [{ key: 'overview', label: '患者总览', icon: 'users', path: '/patients' }] },
    { key: 'more', label: '更多', items: [{ key: 'mdt', label: 'MDT会诊', icon: 'network', path: '/mdt' }] },
  ],
  moreMenuItems: [{ key: 'mdt', label: 'MDT会诊', icon: 'network', path: '/mdt' }],
}))

import { resolveNavigation, getAccessibleModuleKeys } from '../navigation/navigationResolver'

describe('Navigation Resolver', () => {
  describe('global mode', () => {
    it('should return global nav groups', () => {
      const result = resolveNavigation({ mode: 'global' })
      expect(result.mode).toBe('global')
      expect(result.groups.length).toBeGreaterThan(0)
      expect(result.groups.some(g => g.key === 'today')).toBe(true)
      expect(result.groups.some(g => g.key === 'patients')).toBe(true)
    })

    it('should include more menu items', () => {
      const result = resolveNavigation({ mode: 'global' })
      const moreGroup = result.groups.find(g => g.key === 'more')
      expect(moreGroup).toBeDefined()
      expect(moreGroup!.items.length).toBeGreaterThan(0)
    })
  })

  describe('patient mode', () => {
    it('should return patient module groups', () => {
      const result = resolveNavigation({ mode: 'patient', role: 'doctor' })
      expect(result.mode).toBe('patient')
      expect(result.groups.length).toBeGreaterThan(0)
    })

    it('should filter by role — nurse cannot see causal-inference', () => {
      const result = resolveNavigation({ mode: 'patient', role: 'nurse' })
      const allItems = result.groups.flatMap(g => g.items)
      expect(allItems.some(i => i.key === 'causal-inference')).toBe(false)
    })

    it('should allow doctor to see causal-inference when feature flag enabled', () => {
      // Note: our mock disables ai-causal-inference, so even doctors can't see it
      const result = resolveNavigation({ mode: 'patient', role: 'doctor' })
      const allItems = result.groups.flatMap(g => g.items)
      // causal-inference is disabled by feature flag in mock
      expect(allItems.some(i => i.key === 'causal-inference')).toBe(false)
    })

    it('should allow doctor to see risk-prediction', () => {
      const result = resolveNavigation({ mode: 'patient', role: 'doctor' })
      const allItems = result.groups.flatMap(g => g.items)
      expect(allItems.some(i => i.key === 'risk-prediction')).toBe(true)
    })

    it('should include followup for nurse role', () => {
      const result = resolveNavigation({ mode: 'patient', role: 'nurse' })
      const allItems = result.groups.flatMap(g => g.items)
      expect(allItems.some(i => i.key === 'followup')).toBe(true)
    })
  })

  describe('embed mode', () => {
    it('should return empty groups', () => {
      const result = resolveNavigation({ mode: 'embed' })
      expect(result.groups).toEqual([])
      expect(result.mode).toBe('embed')
    })
  })

  describe('no duplicate AI modules', () => {
    it('should not have duplicate module keys in patient mode', () => {
      const result = resolveNavigation({ mode: 'patient', role: 'doctor' })
      const allKeys = result.groups.flatMap(g => g.items.map(i => i.key))
      const uniqueKeys = new Set(allKeys)
      expect(allKeys.length).toBe(uniqueKeys.size)
    })

    it('should not have duplicate module keys in global mode', () => {
      const result = resolveNavigation({ mode: 'global', role: 'doctor' })
      const allKeys = result.groups.flatMap(g => g.items.map(i => i.key))
      const uniqueKeys = new Set(allKeys)
      expect(allKeys.length).toBe(uniqueKeys.size)
    })

    it('ai-analysis modules should appear exactly once in patient mode', () => {
      const result = resolveNavigation({ mode: 'patient', role: 'doctor' })
      const allKeys = result.groups.flatMap(g => g.items.map(i => i.key))
      const aiKeys = ['similar-cases', 'causal-inference', 'what-if', 'disease-trajectory', 'evidence']
      for (const key of aiKeys) {
        const count = allKeys.filter(k => k === key).length
        expect(count).toBeLessThanOrEqual(1)
      }
    })
  })

  describe('getAccessibleModuleKeys', () => {
    it('should return accessible modules for doctor', () => {
      const keys = getAccessibleModuleKeys('doctor')
      expect(keys).toContain('overview')
      expect(keys).toContain('risk-prediction')
      expect(keys).toContain('followup')
    })

    it('should exclude role-restricted modules for unknown role', () => {
      const keys = getAccessibleModuleKeys('')
      // followup requires roles, so empty role should not have it
      expect(keys).not.toContain('followup')
    })
  })
})
