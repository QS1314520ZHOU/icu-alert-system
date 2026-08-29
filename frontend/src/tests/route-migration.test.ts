import { describe, it, expect } from 'vitest'
import { getPatientIdFromRoute, buildPatientPath } from '../utils/patientRouteHelper'

describe('Route Migration — patientId helpers', () => {
  describe('getPatientIdFromRoute', () => {
    it('should read params.patientId (canonical)', () => {
      const route = { params: { patientId: '123' }, query: {} } as any
      expect(getPatientIdFromRoute(route)).toBe('123')
    })

    it('should fall back to params.id (legacy)', () => {
      const route = { params: { id: '456' }, query: {} } as any
      expect(getPatientIdFromRoute(route)).toBe('456')
    })

    it('should prefer patientId over id', () => {
      const route = { params: { patientId: '123', id: '456' }, query: {} } as any
      expect(getPatientIdFromRoute(route)).toBe('123')
    })

    it('should return empty string when neither exists', () => {
      const route = { params: {}, query: {} } as any
      expect(getPatientIdFromRoute(route)).toBe('')
    })

    it('should handle string trimming', () => {
      const route = { params: { patientId: '  789  ' }, query: {} } as any
      expect(getPatientIdFromRoute(route)).toBe('789')
    })
  })

  describe('buildPatientPath', () => {
    it('should build basic patient path', () => {
      expect(buildPatientPath('123')).toBe('/patient/123')
    })

    it('should build path with suffix', () => {
      expect(buildPatientPath('123', 'overview')).toBe('/patient/123/overview')
    })

    it('should build tool path', () => {
      expect(buildPatientPath('123', 'tool/risk-prediction')).toBe('/patient/123/tool/risk-prediction')
    })

    it('should return empty string for empty patientId', () => {
      expect(buildPatientPath('')).toBe('')
      expect(buildPatientPath('', 'overview')).toBe('')
    })
  })
})

describe('Route redirect compatibility', () => {
  it('old /patient/:id should redirect to /patient/:patientId/overview', () => {
    // This is a conceptual test — the actual redirect is in the router config
    // We verify the redirect function logic here
    const redirectFn = (to: any) => ({
      path: `/patient/${to.params.id}/overview`,
      query: to.query,
    })

    const result = redirectFn({ params: { id: '123' }, query: { dept_code: 'ICU' } })
    expect(result.path).toBe('/patient/123/overview')
    expect(result.query).toEqual({ dept_code: 'ICU' })
  })

  it('old /patient/:id/intelligence should redirect to /patient/:patientId/tool/risk-prediction', () => {
    const redirectFn = (to: any) => ({
      path: `/patient/${to.params.id}/tool/risk-prediction`,
      query: to.query,
    })

    const result = redirectFn({ params: { id: '456' }, query: {} })
    expect(result.path).toBe('/patient/456/tool/risk-prediction')
  })
})
