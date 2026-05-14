import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import HumanBody from '../../src/components/HumanBody/index.vue'
import HumanBody2D from '../../src/components/HumanBody/HumanBody2D.vue'
import { useHumanBodyAlarmStore } from '../../src/stores/humanBodyAlarmStore'

vi.mock('../../src/services/humanBodyAlarmAdapter', () => ({
  connectHumanBodyAlarmAdapter: vi.fn(() => vi.fn()),
}))

vi.mock('../../src/components/HumanBody/HumanBody3D.vue', () => ({
  __isTeleport: false,
  __isKeepAlive: false,
  name: 'HumanBody3D',
  default: {
    name: 'HumanBody3D',
    props: ['model', 'patientId', 'autoFocus', 'showLabels'],
    emits: ['organ-click', 'ready', 'load-failed', 'performance-degraded'],
    template: '<div class="mock-human-body-3d" :data-model="model" />',
  },
}))

describe('HumanBody components', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders the 2D fallback when forceTier is 2d', async () => {
    const wrapper = mount(HumanBody, {
      props: { forceTier: '2d' },
    })

    await flushPromises()

    expect(wrapper.find('.human-body-2d').exists()).toBe(true)
  })

  it('renders the low 3D renderer when forceTier is low', async () => {
    const wrapper = mount(HumanBody, {
      props: { forceTier: 'low' },
    })

    await flushPromises()

    const renderer = wrapper.find('.mock-human-body-3d')
    expect(renderer.exists()).toBe(true)
    expect(renderer.attributes('data-model')).toBe('low')
  })

  it('emits organ-click from the 2D SVG with the scoped patient id', async () => {
    const wrapper = mount(HumanBody2D, {
      props: { patientId: 'patient-1' },
    })

    await wrapper.find('#svg-heart').trigger('click')

    expect(wrapper.emitted('organ-click')?.[0]).toEqual(['heart', 'patient-1'])
  })

  it('applies alarm classes to SVG organs from the alarm store', async () => {
    const store = useHumanBodyAlarmStore()
    store.setAlarm('heart', { level: 'critical', patientId: 'patient-1' })

    const wrapper = mount(HumanBody2D, {
      props: { patientId: 'patient-1' },
    })

    await flushPromises()

    expect(wrapper.find('#svg-heart').classes()).toContain('alarm-critical')
  })
})
