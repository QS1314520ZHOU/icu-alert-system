import { vi } from 'vitest'

class MockWebGLRenderer {
  domElement = document.createElement('canvas')
  setSize = vi.fn()
  setPixelRatio = vi.fn()
  render = vi.fn()
  dispose = vi.fn()
  forceContextLoss = vi.fn()
}

vi.mock('three', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('three')
  return {
    ...actual,
    WebGLRenderer: MockWebGLRenderer,
  }
})
