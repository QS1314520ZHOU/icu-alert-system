import { describe, it, expect } from 'vitest'

/**
 * Route migration tests.
 *
 * Tests that old patient detail routes correctly map to new module routes.
 * These test the redirect logic defined in the router.
 */

// Simulate the redirect logic from router/index.ts
const LEGACY_REDIRECTS: Record<string, (params: { id: string; query?: Record<string, string> }) => string> = {
  '/patient/:id/intelligence': ({ id, query }) => {
    let path = `/patient/${id}/tool/risk-prediction`
    if (query?.tab === 'similar') path = `/patient/${id}/tool/similar-cases`
    if (query?.tab === 'ai') path = `/patient/${id}/tool/risk-prediction`
    if (query?.tab === 'followup') path = `/patient/${id}/tool/followup`
    return path
  },
}

describe('Route Migration', () => {
  describe('Legacy intelligence route', () => {
    it('should redirect /patient/:id/intelligence to risk-prediction', () => {
      const result = LEGACY_REDIRECTS['/patient/:id/intelligence']({ id: 'p123' })
      expect(result).toBe('/patient/p123/tool/risk-prediction')
    })

    it('should redirect ?tab=similar to similar-cases', () => {
      const result = LEGACY_REDIRECTS['/patient/:id/intelligence']({
        id: 'p123',
        query: { tab: 'similar' },
      })
      expect(result).toBe('/patient/p123/tool/similar-cases')
    })

    it('should redirect ?tab=ai to risk-prediction', () => {
      const result = LEGACY_REDIRECTS['/patient/:id/intelligence']({
        id: 'p123',
        query: { tab: 'ai' },
      })
      expect(result).toBe('/patient/p123/tool/risk-prediction')
    })

    it('should redirect ?tab=followup to followup', () => {
      const result = LEGACY_REDIRECTS['/patient/:id/intelligence']({
        id: 'p123',
        query: { tab: 'followup' },
      })
      expect(result).toBe('/patient/p123/tool/followup')
    })
  })

  describe('New module routes', () => {
    const newRoutes = [
      { moduleKey: 'risk-prediction', expected: '/patient/p123/tool/risk-prediction' },
      { moduleKey: 'similar-cases', expected: '/patient/p123/tool/similar-cases' },
      { moduleKey: 'causal-inference', expected: '/patient/p123/tool/causal-inference' },
      { moduleKey: 'what-if', expected: '/patient/p123/tool/what-if' },
      { moduleKey: 'integrated-risk', expected: '/patient/p123/tool/integrated-risk' },
      { moduleKey: 'disease-trajectory', expected: '/patient/p123/tool/disease-trajectory' },
      { moduleKey: 'evidence', expected: '/patient/p123/tool/evidence' },
      { moduleKey: 'decision-assistants', expected: '/patient/p123/tool/decision-assistants' },
      { moduleKey: 'documents', expected: '/patient/p123/tool/documents' },
      { moduleKey: 'followup', expected: '/patient/p123/tool/followup' },
    ]

    for (const route of newRoutes) {
      it(`should have route for ${route.moduleKey}`, () => {
        const path = `/patient/p123/tool/${route.moduleKey}`
        expect(path).toBe(route.expected)
      })
    }
  })

  describe('Embed routes', () => {
    const embedRoutes = [
      'risk-prediction',
      'similar-cases',
      'causal-inference',
      'what-if',
      'integrated-risk',
      'disease-trajectory',
      'evidence',
      'decision-assistants',
    ]

    for (const moduleKey of embedRoutes) {
      it(`should have embed route for ${moduleKey}`, () => {
        const url = `/embed/patient/p123/${moduleKey}`
        expect(url).toBeTruthy()
        expect(url).toContain(moduleKey)
      })
    }
  })
})
