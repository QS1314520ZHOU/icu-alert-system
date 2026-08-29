import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the API module before importing handover functions
vi.mock('../api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  aiApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import api, { aiApi } from '../api/index'
import {
  generateHandover,
  getHandover,
  getPatientHandoverHistory,
  updateHandoverContent,
  confirmHandover,
  acknowledgeHandover,
  rejectHandover,
  getHandoverBrief,
  getForcedAlerts,
} from '../api/handover'

const mockApi = vi.mocked(api)
const mockAiApi = vi.mocked(aiApi)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Handover API', () => {
  describe('generateHandover', () => {
    it('should call POST via aiApi', async () => {
      const mockResponse = {
        data: {
          data: { _id: 'doc123', ai_status: { status: 'success' }, sections: {} },
        },
      }
      mockAiApi.post.mockResolvedValue(mockResponse)

      const result = await generateHandover({ patient_id: 'p1', mode: 'nurse_bedside' })

      expect(mockAiApi.post).toHaveBeenCalledWith(
        '/api/handover/generate',
        { patient_id: 'p1', mode: 'nurse_bedside' }
      )
      // Function returns raw axios response
      expect(result).toBe(mockResponse)
    })
  })

  describe('getHandover', () => {
    it('should call GET /api/handover/:id', async () => {
      const mockResponse = { data: { data: { _id: 'doc123' } } }
      mockApi.get.mockResolvedValue(mockResponse)

      await getHandover('doc123')

      expect(mockApi.get).toHaveBeenCalledWith('/api/handover/doc123')
    })
  })

  describe('getPatientHandoverHistory', () => {
    it('should call GET /api/handover/patients/:id/history', async () => {
      const mockResponse = { data: { data: { total: 0, items: [] } } }
      mockApi.get.mockResolvedValue(mockResponse)

      await getPatientHandoverHistory('p1', { limit: 20 })

      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/handover/patients/p1/history',
        { params: { limit: 20 } }
      )
    })
  })

  describe('updateHandoverContent', () => {
    it('should call PUT /api/handover/:id/content', async () => {
      const mockResponse = { data: { data: { _id: 'doc123' } } }
      mockApi.put.mockResolvedValue(mockResponse)

      await updateHandoverContent('doc123', { sections: {} })

      expect(mockApi.put).toHaveBeenCalledWith(
        '/api/handover/doc123/content',
        { sections: {} }
      )
    })
  })

  describe('confirmHandover', () => {
    it('should call POST /api/handover/:id/confirm', async () => {
      const mockResponse = { data: { data: { _id: 'doc123' } } }
      mockApi.post.mockResolvedValue(mockResponse)

      await confirmHandover('doc123', { confirmed: true })

      expect(mockApi.post).toHaveBeenCalledWith(
        '/api/handover/doc123/confirm',
        { confirmed: true }
      )
    })
  })

  describe('acknowledgeHandover', () => {
    it('should call POST /api/handover/:id/acknowledge', async () => {
      const mockResponse = { data: { data: { _id: 'doc123' } } }
      mockApi.post.mockResolvedValue(mockResponse)

      await acknowledgeHandover('doc123', { operator: 'nurse001' })

      expect(mockApi.post).toHaveBeenCalledWith(
        '/api/handover/doc123/acknowledge',
        { operator: 'nurse001' }
      )
    })
  })

  describe('rejectHandover', () => {
    it('should call POST /api/handover/:id/reject', async () => {
      const mockResponse = { data: { data: { _id: 'doc123' } } }
      mockApi.post.mockResolvedValue(mockResponse)

      await rejectHandover('doc123', { reason: '需补充' })

      expect(mockApi.post).toHaveBeenCalledWith(
        '/api/handover/doc123/reject',
        { reason: '需补充' }
      )
    })
  })

  describe('getHandoverBrief', () => {
    it('should call GET /api/handover/:id/brief with mode param', async () => {
      const mockResponse = { data: { data: { summary_text: '' } } }
      mockApi.get.mockResolvedValue(mockResponse)

      await getHandoverBrief('doc123', 'ward')

      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/handover/doc123/brief',
        { params: { mode: 'ward' } }
      )
    })
  })

  describe('getForcedAlerts', () => {
    it('should call GET /api/handover/patients/:id/forced-alerts', async () => {
      const mockResponse = { data: { data: [] } }
      mockApi.get.mockResolvedValue(mockResponse)

      await getForcedAlerts('p1', { since: '2024-01-01' })

      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/handover/patients/p1/forced-alerts',
        { params: { since: '2024-01-01' } }
      )
    })
  })
})
